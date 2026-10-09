"""MOA weekly 《畜产品和饲料集贸市场价格情况》 (500 county fairs) -> moa_weekly_prices.csv

Discovery (all list pages / search responses are cached under data/raw/industry/moa_weekly/):
  1. xmsyj.moa.gov.cn/jcyj/            畜牧兽医局 监测预警 (static list reaches back to 2021-12)
  2. www.nahs.org.cn/jcyj/jghq/        全国畜牧总站 价格行情 (2019-09 onward, same text as MOA)
  3. www.moa.gov.cn/gk/jcyj/ + /ztzl/nybrl/rlxx/   old MOA columns (2016-2018); their list pages
     now redirect to the home page, so URLs are found through the MOA site search (so-gov.cn)
     and by following each article's 相关新闻 links.

Each article gives national averages (元/公斤) for 仔猪, 活猪(=生猪 from 2021), 猪肉, 玉米, 豆粕. Values are
taken from the article's summary table when present, otherwise from the text; both are parsed and
compared. Weeks without any surviving article are left missing in the main rows; separately flagged
backfill rows use the "去年同期"/"前一周" columns printed in later articles' tables.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from ind_common import (PROC, RAW, SITE_MOA, decode, fetch, flat_text, sogov_search, soup,  # noqa: E402
                        table_rows, to_float, write_csv)

SUB = "moa_weekly"
TITLE_KEY = "集贸市场价格情况"
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------
def _list_items(base: str, n_pages: int, page_fmt: str) -> list[dict]:
    items = []
    for p in range(n_pages):
        u = base + ("index.htm" if p == 0 else page_fmt.format(p))
        b = fetch(u, f"{SUB}/lists", force=True)
        if not b:
            continue
        s = soup(b)
        for a in s.find_all("a"):
            h = a.get("href") or ""
            t = re.sub(r"\s+", "", a.get_text(""))
            if TITLE_KEY in t and re.search(r"t20\d{6}_\d+\.htm", h):
                items.append(dict(url=urljoin(u, h), list_title=t, origin=base))
    return items


def _count_pages(base: str) -> int:
    b = fetch(base + "index.htm", f"{SUB}/lists", force=True)
    html = decode(b)
    m = re.search(r"countPage\s*=\s*(\d+)", html) or re.search(r"createPageHTML\((\d+)", html)
    return int(m.group(1)) if m else 1


def discover() -> list[dict]:
    items = []
    for base in ["https://xmsyj.moa.gov.cn/jcyj/", "https://www.nahs.org.cn/jcyj/jghq/"]:
        n = _count_pages(base)
        got = _list_items(base, n, "index_{}.htm")
        print(f"{base}: {n} pages, {len(got)} weekly items")
        items += got
    # old MOA columns through site search
    found = {}
    windows = [("2016-12-01", "2017-03-31"), ("2017-04-01", "2017-06-30"), ("2017-07-01", "2017-09-30"),
               ("2017-10-01", "2017-12-31"), ("2018-01-01", "2018-06-30"), ("2018-07-01", "2018-12-31"),
               ("2019-01-01", "2019-06-30"), ("2019-07-01", "2019-12-31"), ("2020-01-01", "2020-12-31"),
               ("2021-01-01", "2021-12-31")]
    for s_, e_ in windows:
        for qt in ["畜产品和饲料集贸市场价格情况", "集贸市场价格情况"]:
            for kp in (1, 0):
                for d in sogov_search(SITE_MOA, qt, s_, e_, key_place=kp, max_pages=5,
                                      cache_subdir=f"{SUB}/search"):
                    if TITLE_KEY in d["title"]:
                        found[d["url"]] = d
    # exact-title queries for 2016-12 .. 2018-06 to raise recall
    for yr, months in [(2017, range(1, 13)), (2018, range(1, 7))]:
        for m in months:
            for wk in ["第1周", "第2周", "第3周", "第4周", "第5周", "最后一周"]:
                qt = f"{m}月份{wk}畜产品和饲料集贸市场价格情况"
                s_ = dt.date(yr, m, 1)
                e_ = (dt.date(yr + (m == 12), m % 12 + 1, 1) + dt.timedelta(days=12))
                for d in sogov_search(SITE_MOA, qt, s_.isoformat(), e_.isoformat(), key_place=1,
                                      max_pages=1, cache_subdir=f"{SUB}/search"):
                    if TITLE_KEY in d["title"]:
                        found[d["url"]] = d
    for u, d in found.items():
        items.append(dict(url=u.replace("http://", "https://", 1), list_title=d["title"], origin="moa_search"))
    print(f"moa search: {len(found)} weekly items")
    return items


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------
_P = r"(?:平均)?(?:价格)?(?:为)?(\d+\.?\d*)元"
TEXT_PATS = {
    "piglet": r"全国仔猪" + _P,
    "live_hog": r"全国(?:出栏)?(?:活猪|生猪)" + _P,
    "pork": r"全国猪肉" + _P,
    "corn": r"全国玉米" + _P,
    "soymeal": r"全国豆粕" + _P,
}
ROW_LABELS = {"piglet": ["仔猪"], "live_hog": ["活猪", "生猪"], "pork": ["猪肉"], "corn": ["玉米"],
              "soymeal": ["豆粕"]}


def parse_article(b: bytes, url: str) -> dict | None:
    s = soup(b)
    title = ""
    mt = s.find("meta", attrs={"name": "ArticleTitle"})
    if mt and mt.get("content"):
        title = mt["content"].strip()
    if not title and s.title:
        title = s.title.get_text(strip=True)
    tables = s.find_all("table")
    flat = flat_text(s)
    title = re.sub(r"\s+", "", title)
    if TITLE_KEY not in title and TITLE_KEY not in flat[:3000]:
        return None
    rec = dict(url=url, title=title)
    m = re.search(r"(\d{1,2})月份?(第[1-5一二三四五]周|最后一周)", title)
    rec["period_text"] = (m.group(1) + "月" + m.group(2)) if m else ""
    m = (re.search(r"(?:日期|发布时间|时间)[：:](20\d{2}-\d{2}-\d{2})", flat)
         or re.search(r"(20\d{2}-\d{2}-\d{2})\d{2}:\d{2}", flat))
    rel = m.group(1) if m else None
    if not rel:
        m = re.search(r"/t(20\d{2})(\d{2})(\d{2})_", url)
        rel = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
    rec["release_date"] = rel
    m = re.search(r"采集日为(\d{1,2})月(\d{1,2})日", flat)
    collect = None
    if m and rel:
        ry = int(rel[:4])
        cm, cd = int(m.group(1)), int(m.group(2))
        cy = ry - 1 if cm - int(rel[5:7]) > 6 else ry
        try:
            collect = dt.date(cy, cm, cd)
        except ValueError:
            collect = None
    rec["collect_date"] = collect.isoformat() if collect else None
    # summary table
    tab_year = tab_week = None
    tab_vals = {}
    for tb in tables:
        rows = table_rows(tb)
        joined = "".join("".join(r) for r in rows)
        if "仔猪" not in joined or "玉米" not in joined:
            continue
        head_idx = None
        for i, r in enumerate(rows):
            if "本周" in "".join(r):
                head_idx = i
                break
        if head_idx is None:
            continue
        head = rows[head_idx]
        cols = {}
        for j, c in enumerate(head):
            for key, lab in [("this", "本周"), ("last_year", "去年同期"), ("last_year", "上年同期"),
                             ("prev_week", "前一周"), ("prev_week", "上周")]:
                if c.startswith(lab) and key not in cols:
                    cols[key] = j
        for r in rows[head_idx + 1:]:
            if not r:
                continue
            lab = r[0]
            for var, names in ROW_LABELS.items():
                if lab in names and var not in tab_vals:
                    tab_vals[var] = {k: to_float(r[j]) if j < len(r) else None for k, j in cols.items()}
        break
    m = re.search(r"(20\d{2})年(\d{1,2})月(?:份)?(?:第\d周|最后一周)?（总第(\d+)周）", flat)
    if m:
        tab_year, tab_week = int(m.group(1)), int(m.group(3))
    # text values
    txt_vals = {}
    for var, pat in TEXT_PATS.items():
        mm = re.search(pat, flat)
        txt_vals[var] = float(mm.group(1)) if mm else None
    notes = []
    for var in TEXT_PATS:
        tv = (tab_vals.get(var) or {}).get("this")
        xv = txt_vals.get(var)
        rec[var] = tv if tv is not None else xv
        rec[f"{var}_src"] = "table" if tv is not None else ("text" if xv is not None else "")
        if tv is not None and xv is not None and abs(tv - xv) > 0.005:
            notes.append(f"{var}:table {tv}!=text {xv}")
        rec[f"{var}_prev_week"] = (tab_vals.get(var) or {}).get("prev_week")
        rec[f"{var}_last_year"] = (tab_vals.get(var) or {}).get("last_year")
    rec["has_table"] = bool(tab_vals)
    rec["live_hog_label"] = "活猪" if "活猪平均价格" in flat else ("生猪" if "生猪平均价格" in flat else "")
    rec["tab_year"], rec["tab_week"] = tab_year, tab_week
    if collect:
        iso = collect.isocalendar()
        rec["iso_year"], rec["iso_week"] = iso[0], iso[1]
    else:
        rec["iso_year"] = rec["iso_week"] = None
    rec["check_note"] = "; ".join(notes)
    # related-news links (old MOA pages) used to discover more weeks
    rel_links = []
    for a in s.find_all("a"):
        t = re.sub(r"\s+", "", a.get_text(""))
        h = a.get("href") or ""
        if TITLE_KEY in t and re.search(r"t20\d{6}_\d+\.htm", h):
            rel_links.append(urljoin(url, h))
    rec["_related"] = rel_links
    return rec


def site_of(url: str) -> str:
    if "xmsyj.moa.gov.cn" in url:
        return "xmsyj"
    if "nahs.org.cn" in url:
        return "nahs"
    if "/ztzl/nybrl/rlxx/" in url:
        return "moa_rlxx"
    return "moa_gk"


def main():
    items = discover()
    urls = list(dict.fromkeys(i["url"] for i in items))
    parsed, seen = {}, set()
    queue = list(urls)
    rounds = 0
    while queue and rounds < 6:
        rounds += 1
        batch = [u for u in queue if u not in seen]
        seen.update(batch)
        with ThreadPoolExecutor(6) as ex:
            blobs = list(ex.map(lambda u: (u, fetch(u, f"{SUB}/articles")), batch))
        queue = []
        for u, b in blobs:
            if not b:
                parsed[u] = None
                continue
            rec = parse_article(b, u)
            parsed[u] = rec
            if rec:
                for r in rec.pop("_related"):
                    r = r.replace("http://", "https://", 1)
                    if r not in seen:
                        queue.append(r)
        print(f"round {rounds}: fetched {len(batch)}, new related {len(queue)}")
    recs = [r for r in parsed.values() if r]
    failed = [u for u, r in parsed.items() if r is None]
    print(f"parsed {len(recs)} articles; failed/non-weekly {len(failed)}")
    df = pd.DataFrame(recs)
    df["source_site"] = df["url"].map(site_of)
    df.to_csv(RAW / SUB / "_parsed_all_articles.csv", index=False)

    # one row per collection date. Values/URL from the preferred site (xmsyj > moa_gk > moa_rlxx >
    # nahs); the week number and the 前一周/去年同期 columns come from whichever copy carries the
    # summary table (xmsyj pages have none, the NAHS copy of the same report usually does).
    pref = {"xmsyj": 0, "moa_gk": 1, "moa_rlxx": 2, "nahs": 3}
    df["pref"] = df["source_site"].map(pref)
    df = df[df["collect_date"].notna()].copy()
    rows = []
    for cd, g in df.sort_values("pref").groupby("collect_date"):
        best = g.iloc[0].to_dict()
        others = g.iloc[1:]
        diffs = []
        for _, o in others.iterrows():
            for v in TEXT_PATS:
                a, b2 = best.get(v), o.get(v)
                if pd.notna(a) and pd.notna(b2) and abs(a - b2) > 0.005:
                    diffs.append(f"{v}:{o['source_site']}={b2}")
        for v in TEXT_PATS:
            if pd.isna(best.get(v)):
                for _, o in others.iterrows():
                    if pd.notna(o.get(v)):
                        best[v] = o[v]
                        best["check_note"] = (str(best.get("check_note") or "") +
                                              f" {v}取自同期副本{o['source_site']}").strip()
                        break
        tab = g[g["has_table"] & g["tab_week"].notna()]
        if len(tab):
            t0 = tab.iloc[0]
            best["year"], best["week"], best["week_src"] = int(t0["tab_year"]), int(t0["tab_week"]), "表头总第N周"
            for v in TEXT_PATS:
                best[f"{v}_prev_week"] = t0[f"{v}_prev_week"]
                best[f"{v}_last_year"] = t0[f"{v}_last_year"]
            best["table_url"] = t0["url"]
        else:
            best["year"], best["week"], best["week_src"] = best["iso_year"], best["iso_week"], "采集日ISO周"
            best["table_url"] = None
        best["alt_urls"] = " ".join(others["url"].tolist())
        best["cross_check"] = ("一致" if not diffs else "不一致:" + ",".join(diffs)) if len(others) else ""
        best["value_basis"] = "本周(原文)"
        rows.append(best)
    main_df = pd.DataFrame(rows)
    dup = main_df.duplicated(["year", "week"], keep=False)
    main_df.loc[dup, "check_note"] = (main_df.loc[dup, "check_note"].fillna("") + " 周次重复(节假日顺延采集,周次为ISO推算)").str.strip()

    # flagged backfill from later reports' 前一周 / 去年同期 columns (validated: every overlapping
    # pair in this dataset matches the directly published value exactly)
    have = set(zip(main_df["year"].astype(int), main_df["week"].astype(int)))
    back = {}
    for _, r in main_df.iterrows():
        if pd.isna(r.get("table_url")) or pd.isna(r["week"]) or r["week_src"] != "表头总第N周":
            continue
        y, w = int(r["year"]), int(r["week"])
        targets = [((y - 1, w), "last_year", "去年同期列(次年同周周报)")]
        if w > 1:
            targets.insert(0, ((y, w - 1), "prev_week", "前一周列(下一周周报)"))
        for key, col, basis in targets:
            if key in have or key in back:
                continue
            if key[1] > dt.date(key[0], 12, 28).isocalendar()[1]:
                continue  # e.g. 2020W53's 去年同期 repeats 2019W52; 2019 has no week 53
            vals = {v: r.get(f"{v}_{col}") for v in TEXT_PATS}
            if all(pd.isna(x) for x in vals.values()):
                continue
            back[key] = dict(year=key[0], week=key[1], period_text="", release_date=None, collect_date=None,
                             url=r["table_url"], title=r["title"], source_site=site_of(r["table_url"]),
                             value_basis=basis, week_src="来源周报表头周次推算", **vals)
    back_df = pd.DataFrame(list(back.values()))
    out = pd.concat([main_df, back_df], ignore_index=True)
    out["year"] = out["year"].astype(int)
    out["week"] = out["week"].astype(int)
    out = out.sort_values(["year", "week", "value_basis"]).reset_index(drop=True)
    cols = ["year", "week", "period_text", "release_date", "live_hog", "piglet", "pork", "corn", "soymeal",
            "url", "collect_date", "week_src", "value_basis", "source_site", "title", "live_hog_label",
            "cross_check", "alt_urls", "table_url", "check_note"]
    out = out[(out["year"] >= 2016)]
    write_csv(out[cols], PROC / "moa_weekly_prices.csv")
    m = out[out["value_basis"] == "本周(原文)"]
    print("direct weeks:", len(m), m["collect_date"].min(), m["collect_date"].max())
    print("backfill weeks:", len(out) - len(m))
    print(m.groupby("year").size())


if __name__ == "__main__":
    main()
