"""MOA national live-hog prices before 2016 -> moa_hist_hog_prices.csv (Issue #5)

Two kinds of 农业部 releases in the old 监测预警 column (www.moa.gov.cn/gk/jcyj/):
  - monthly reports (2005-2010): "<月>部分经济作物和畜产品价格变动情况" (160 物价信息网点县, 生猪 in
    元/50公斤, converted to 元/公斤) and from 2006/2007 "全国主要畜产品价格走势" / "全国畜产品和饲料价格情况"
    (450-470 price points, 活猪 元/公斤);
  - weekly 集贸市场 bulletins (2009-2015): "全国活猪平均价格X元/公斤" with the collection date
    ("采集日为M月D日"), the week-on-week change and, from 2010, the year-on-year change.

URLs come from the frozen listing pages of the 畜牧 sub-column (www.moa.gov.cn/gk/jcyj/xm/, 2004-2015),
the government site search (so-gov.cn; cache only when the API blocks the IP) and each article's
相关新闻 links. Every value
keeps its URL. Year-earlier values implied by a printed year-on-year change are kept as separate,
flagged rows (value_basis) and never overwrite a directly published value.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ind_common import (PROC, RAW, SITE_MOA, fetch, flat_text, sogov_search, soup, table_rows,  # noqa: E402
                        write_csv)

SUB = "moa_hist"
TITLE_RE = re.compile(r"^(?=.*(?:价格|价))(?=.*(?:猪|畜))")
QUERIES = ["集贸市场价格情况", "生猪价格", "活猪价格", "畜产品价格", "畜产品和饲料价格情况", "价格变动情况",
           "畜产品价格走势", "猪肉价格"]
NUM = r"(\d+(?:\.\d+)?)"


def windows():
    out = []
    for y in range(2005, 2016):
        for q in range(4):
            a = dt.date(y, 3 * q + 1, 1)
            b = dt.date(y + (q == 3), (3 * q + 3) % 12 + 1, 1) - dt.timedelta(days=1)
            out.append((a.isoformat(), b.isoformat()))
    return out


def _cached_search(qt: str, a: str, b: str, max_pages: int = 4) -> list[dict]:
    """Read sogov_search results from its cache only (the API bans an IP after bursts of queries)."""
    out = []
    for page in range(1, max_pages + 1):
        params = dict(siteCode=SITE_MOA, qt=qt, page=page, pageSize=20, sort="dateDesc", keyPlace=1,
                      timeOption=2, startDateStr=a, endDateStr=b)
        key = hashlib.md5(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        fp = RAW / SUB / "search" / f"sogov_{SITE_MOA}_{key}.json"
        if not fp.exists():
            break
        j = json.loads(fp.read_text(encoding="utf-8"))
        docs = j.get("resultDocs") or []
        out += [x.get("data") or {} for x in docs]
        if len(docs) < 20:
            break
    return out


def _api_banned() -> bool:
    try:
        r = requests.post("https://api.so-gov.cn/query/s", timeout=20,
                          data=dict(siteCode=SITE_MOA, qt="生猪", page=1, pageSize=1, ie=str(uuid.uuid4())),
                          headers={"Referer": "https://www.moa.gov.cn/", "Origin": "https://www.moa.gov.cn"})
        j = r.json()
        return j.get("ok") is not True and "禁用" in str(j.get("msg"))
    except Exception:  # noqa: BLE001
        return True


def list_column(col: str = "xm") -> dict[str, str]:
    """Walk the frozen listing pages of an old 监测预警 sub-column (index.htm, index_1.htm, ...)."""
    base = f"https://www.moa.gov.cn/gk/jcyj/{col}/"
    found, n_pages, p = {}, 1, 0
    while p < n_pages:
        url = base + ("" if p == 0 else f"index_{p}.htm")
        b = fetch(url, f"{SUB}/list", name=f"{col}_{p}.html")
        if not b:
            break
        h = b.decode("utf-8", "ignore")
        m = re.search(r"countPage\s*=\s*(\d+)", h)
        n_pages = int(m.group(1)) if m else n_pages
        for href, t in re.findall(r'href="(\./[^"]+t20\d{6}_\d+\.htm)"[^>]*title="([^"]*)"', h):
            t = re.sub(r"\s+", "", t)
            if TITLE_RE.search(t):
                found[urljoin(base, href).replace("https://", "http://", 1)] = t
        p += 1
    print(f"listing {col}: {n_pages} pages, {len(found)} matching titles")
    return found


def discover() -> dict[str, str]:
    found = list_column("xm")
    banned = _api_banned()
    print("search API banned -> cache only" if banned else "search API available")
    for a, b in windows():
        for qt in (QUERIES if a < "2011" else QUERIES[:1] + ["畜产品和饲料价格情况"]):
            docs = (_cached_search(qt, a, b) if banned else
                    sogov_search(SITE_MOA, qt, a, b, key_place=1, max_pages=4, cache_subdir=f"{SUB}/search"))
            for d in docs:
                u, t = d.get("url") or "", re.sub(r"<[^>]+>|\s+", "", d.get("title") or "")
                if "moa.gov.cn" in u and TITLE_RE.search(t):
                    found[u.replace("https://", "http://", 1)] = t
    return found


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------
def _sign(word: str) -> int:
    return -1 if word in ("下降", "下跌", "回落", "降低", "减少", "降") else 1


def _list_pct(text: str, items: list[str], key: str) -> float | None:
    """'仔猪、活猪、猪肉价格分别上涨17.1%、15.4%、17.1%' -> value for key ('活猪')."""
    m = re.search(r"((?:仔猪|活猪|生猪|猪肉)(?:[、和及与](?:仔猪|活猪|生猪|猪肉))+)(?:平均)?价格(?:分别)?"
                  r"(上涨|下降|上升|下跌)(?:了)?((?:\d+(?:\.\d+)?%[、和及]?)+)", text)
    if not m:
        return None
    names = re.split(r"[、和及与]", m.group(1))
    vals = re.findall(r"(\d+(?:\.\d+)?)%", m.group(3))
    names = ["活猪" if n == "生猪" else n for n in names]
    if key in names and len(vals) == len(names):
        return _sign(m.group(2)) * float(vals[names.index(key)])
    return None


def parse(b: bytes, url: str) -> dict | None:
    s = soup(b)
    title = ""
    mt = s.find("meta", attrs={"name": "ArticleTitle"})
    if mt and mt.get("content"):
        title = mt["content"].strip()
    if not title and s.title:
        title = s.title.get_text(strip=True)
    title = re.sub(r"\s+", "", title)
    flat = flat_text(s)
    m = re.search(r"日期[：:]\s*(20\d{2}-\d{2}-\d{2})", flat) or re.search(r"(20\d{2}-\d{2}-\d{2})\d{2}:\d{2}", flat)
    rel = m.group(1) if m else None
    i0 = flat.find("打印本页")
    body = flat[i0 + 4:] if i0 >= 0 else flat
    body = body[:6000]
    rec = dict(url=url, title=title, release_date=rel, related=[])
    for a in s.find_all("a"):
        t = re.sub(r"\s+", "", a.get_text(""))
        h = a.get("href") or ""
        if TITLE_RE.search(t) and re.search(r"t20\d{6}_\d+\.htm", h):
            rec["related"].append(urljoin(url, h).replace("https://", "http://", 1))
    if not rel:
        return rec

    # weekly bulletin
    mc = re.search(r"采集日为(\d{1,2})月(\d{1,2})日", body)
    mh = re.search(r"全国(?:活猪|生猪)(?:平均)?价格(?:为)?" + NUM + r"元", body)
    if mc and mh:
        ry, rm = int(rel[:4]), int(rel[5:7])
        cm, cd = int(mc.group(1)), int(mc.group(2))
        cy = ry - 1 if cm - rm > 6 else ry
        rec.update(freq="W", obs=dt.date(cy, cm, cd).isoformat(), live_hog=float(mh.group(1)),
                   unit_note="元/公斤")
        tail = body[mh.end(): mh.end() + 160]
        mw = (re.match(r"/公斤[，,]?(?:比(?:前一周|上周)|环比)(?:略)?(上涨|下降|上升|下跌|涨|降)" + NUM + "%", tail)
              or re.match(r"/公斤[，,]?比(?:前一周|上周)(?:略)?(涨|降)\d+(?:\.\d+)?元[，,](?:涨|降)幅" + NUM + "%", tail))
        rec["wow_pct"] = (_sign(mw.group(1)) * float(mw.group(2)) if mw else
                          (0.0 if re.match(r"/公斤[，,]?(?:与(?:前一周|上周)|环比)(?:基本)?持平", tail) else None))
        my = re.search(r"(?:同比|与去年同期相比（简称同比，下同）|与去年同期相比)[，,]?(上涨|下降|上升|下跌)" + NUM + "%",
                       tail.split("。")[0])
        yoy = _sign(my.group(1)) * float(my.group(2)) if my else None
        if yoy is None:
            seg = re.search(r"与去年同期相比[^。]*?。", body)
            yoy = _list_pct(seg.group(0), [], "活猪") if seg else None
        rec["yoy_pct"] = yoy
        for tb in s.find_all("table"):
            rows = table_rows(tb)
            head = next((r for r in rows if "本周" in "".join(r)), None)
            if not head:
                continue
            jy = next((j for j, c in enumerate(head) if re.search(r"(去年|上年|20\d{2}年)同期", c)), None)
            for r in rows:
                if r and r[0] in ("活猪", "生猪") and jy is not None and jy < len(r):
                    try:
                        rec["last_year_tab"] = float(r[jy])
                    except ValueError:
                        pass
        return rec

    # monthly report
    mm = re.search(r"(20\d{2})年(\d{1,2})月", title) or re.search(r"(20\d{2})年(\d{1,2})月", body[:200])
    if mm:
        py, pm = int(mm.group(1)), int(mm.group(2))
    else:
        m2 = (re.search(r"(\d{1,2}|十[一二]?|[一二三四五六七八九])月份", title)
              or re.search(r"^(\d{1,2})月份?", body[:60]))
        if not m2:
            return rec
        pm = int(m2.group(1)) if m2.group(1).isdigit() else CN_MONTH[m2.group(1)]
        ry, rm = int(rel[:4]), int(rel[5:7])
        py = ry - 1 if pm > rm else ry
    if re.search(r"第[1-5一二三四五]周|最后一周", title):
        return rec  # weekly note without collection date: not used
    v, series, unit = None, "450/470个监测点", "元/公斤"
    m_old = re.search(r"生猪[：:]国合商业收购价" + NUM + r"元[^，,。]*[，,]市场价(?:为)?" + NUM + r"元", body)
    i_sec = body.find("生猪产品价格") if "生猪产品价格" in body else body.find("生猪价格")
    sec = body[max(i_sec, 0):]
    m_list = re.search(r"全国((?:仔猪|活猪|猪肉)(?:[、和](?:仔猪|活猪|猪肉))+)(?:的)?平均价格(?:分别)?为每公斤"
                       r"((?:\d+(?:\.\d+)?元(?:（[^）]*）)?[、和]?)+)", sec)
    m_one = (re.search(r"从全国月度平均价格看[，,]活猪" + NUM + r"元", sec)
             or re.search(r"活猪(?:全国)?(?:月度|月)?(?:平均)?价格(?:为)?(?:每公斤)?" + NUM + r"元", sec))
    if m_list and "活猪" in m_list.group(1):
        names = re.split(r"[、和]", m_list.group(1))
        vals = re.findall(NUM + r"元", re.sub(r"（[^）]*）", "", m_list.group(2)))
        if len(vals) == len(names):
            k = names.index("活猪")
            v = float(vals[k])
            tail = sec[m_list.end(): m_list.end() + 200]
            sm = re.search(r"(?:环比|比上月|比\d{1,2}月份(?:（[^）]*）)?)分别([^，,。；]*)", tail)
            sy = re.search(r"(?:同比|比去年同期(?:（[^）]*）)?|与去年同期相比)分别([^，,。；]*)", tail)
            moms = _signed_list(sm.group(1)) if sm else []
            yoys = _signed_list(sy.group(1)) if sy else []
            rec["mom_pct"] = moms[k] if len(moms) == len(names) else None
            rec["yoy_pct"] = yoys[k] if len(yoys) == len(names) else None
    if v is None and m_one:
        v = float(m_one.group(1))
        tail = sec[m_one.end(): m_one.end() + 120].split("。")[0]
        sm = re.search(r"(?:环比|比上月|月环比)(上涨|下降|上升|下跌|增长|持平)(?:" + NUM + "%)?", tail)
        sy = re.search(r"(?:同比|比去年同期(?:（[^）]*）)?)(上涨|下降|上升|下跌|增长)" + NUM + "%", tail)
        if sm:
            rec["mom_pct"] = 0.0 if sm.group(1) == "持平" else _sign(sm.group(1)) * float(sm.group(2))
        rec["yoy_pct"] = _sign(sy.group(1)) * float(sy.group(2)) if sy else None
    if v is None and m_old:
        v = float(m_old.group(2)) / 50.0
        series, unit = "160个物价信息网点县", "元/50公斤 市场价 ÷ 50"
        seg = body[m_old.end(): m_old.end() + 160]
        mom = re.search(r"与上月相比[，,]?分别(?:为)?(上升|上涨|下降)" + NUM + r"%和(?:下)?(上升|上涨|下降)?" + NUM + "%", seg)
        yoy = re.search(r"与上年同期相比[，,]?分别(?:为)?(上升|上涨|下降)" + NUM + r"%和(?:下)?(上升|上涨|下降)?" + NUM + "%",
                        seg)
        rec["mom_pct"] = _sign(mom.group(3) or mom.group(1)) * float(mom.group(4)) if mom else None
        rec["yoy_pct"] = _sign(yoy.group(3) or yoy.group(1)) * float(yoy.group(4)) if yoy else None
    if v is None:
        ml = re.search(r"(?:仔猪|活猪|生猪|猪肉)(?:[、和及与](?:仔猪|活猪|生猪|猪肉))+(?:的)?平均价格分别为((?:\d+(?:\.\d+)?元/公斤[、和及]?)+)",
                       body)
        if ml:
            names = re.findall(r"(仔猪|活猪|生猪|猪肉)", ml.group(0).split("平均价格")[0])
            vals = re.findall(r"(\d+(?:\.\d+)?)元/公斤", ml.group(1))
            names = ["活猪" if n == "生猪" else n for n in names]
            if "活猪" in names and len(vals) == len(names):
                v = float(vals[names.index("活猪")])
        if v is None:
            m1 = re.search(r"(?:全国)?(?:活猪|生猪)(?:出栏)?平均价格(?:为)?" + NUM + r"元/公斤", body)
            v = float(m1.group(1)) if m1 else None
        unit = "元/公斤"
        if v is not None:
            seg = body[:3000]
            mom = re.search(r"(?:活猪|生猪)(?:平均)?价格(?:为)?\d+(?:\.\d+)?元/公斤[，,](?:环比|比上月|与上月相比)(上涨|下降|上升|下跌)" + NUM + "%", seg)
            rec["mom_pct"] = _sign(mom.group(1)) * float(mom.group(2)) if mom else None
            if rec["mom_pct"] is None:
                s1 = re.search(r"与上月相比[，,][^。]*?。", seg)
                rec["mom_pct"] = _list_pct(s1.group(0), [], "活猪") if s1 else None
            s2 = re.search(r"与(?:去年|上年|20\d{2}年)同期相比[，,]?[^。]*?。", seg)
            rec["yoy_pct"] = _list_pct(s2.group(0), [], "活猪") if s2 else None
            if rec["yoy_pct"] is None and s2:
                m3 = re.search(r"(?:活猪|生猪)(?:平均)?价格[^。；]*?(上涨|下降|上升|下跌)" + NUM + "%", s2.group(0))
                rec["yoy_pct"] = _sign(m3.group(1)) * float(m3.group(2)) if m3 else None
    if v is None:
        return rec
    rec.update(freq="M", obs=f"{py}-{pm:02d}", live_hog=round(v, 4), unit_note=unit, series=series)
    return rec


CN_MONTH = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "十一": 11, "十二": 12}


def _signed_list(seg: str) -> list[float]:
    """'下降11.9%、7%和4.6%' -> [-11.9, -7, -4.6]; a sign word carries over to the following numbers."""
    out, sign = [], 1
    for w, n in re.findall(r"(上涨|下降|增长|上升|下跌|减少)?(\d+(?:\.\d+)?)[%％]", seg):
        if w:
            sign = _sign(w)
        out.append(sign * float(n))
    return out


def main():
    found = discover()
    print("search hits:", len(found))
    parsed, seen, queue = {}, set(), list(found)
    for rnd in range(6):
        batch = [u for u in dict.fromkeys(queue) if u not in seen]
        if not batch:
            break
        seen.update(batch)
        with ThreadPoolExecutor(4) as ex:
            blobs = list(ex.map(lambda u: (u, fetch(u, f"{SUB}/articles")), batch))
        queue = []
        for u, b in blobs:
            if not b:
                continue
            r = parse(b, u)
            parsed[u] = r
            if r:
                queue += [x for x in r.pop("related") if x not in seen and "/gk/jcyj/" in x]
        print(f"round {rnd + 1}: fetched {len(batch)}, related {len(queue)}")
    recs = [r for r in parsed.values() if r and r.get("freq")]
    df = pd.DataFrame(recs)
    print("observations:", df["freq"].value_counts().to_dict())

    rows = []
    df["series"] = df["series"].fillna("全国集贸市场周度监测") if "series" in df else "全国集贸市场周度监测"
    df["rank"] = (df["series"] == "160个物价信息网点县").astype(int)
    for freq, g in df.groupby("freq"):
        for obs, gg in g.sort_values(["rank", "release_date"]).groupby("obs"):
            r = gg.iloc[0].to_dict()
            gg = gg[gg["rank"] == gg["rank"].min()]
            vals = gg["live_hog"].round(2).unique()
            r["note"] = "" if len(vals) == 1 else "同期多篇数值不同:" + "/".join(map(str, vals))
            r["alt_urls"] = " ".join(gg["url"].iloc[1:])
            r["value_basis"] = "本期(原文)"
            rows.append(r)
    main_df = pd.DataFrame(rows)
    have = set(zip(main_df["freq"], main_df["obs"]))
    back = []
    for _, r in main_df.iterrows():
        ly = r.get("last_year_tab")
        yoy = r.get("yoy_pct")
        if r["freq"] == "W":
            d = dt.date.fromisoformat(r["obs"]) - dt.timedelta(days=364)
            key = ("W", d.isoformat())
        else:
            y, m = map(int, r["obs"].split("-"))
            key = ("M", f"{y - 1}-{m:02d}")
        if key in have:
            continue
        if pd.notna(ly):
            val, basis = float(ly), "去年同期列(次年同期报告)"
        elif pd.notna(yoy):
            val, basis = float(r["live_hog"]) / (1 + float(yoy) / 100), "由次年同期报告的同比反推"
        else:
            continue
        back.append(dict(freq=key[0], obs=key[1], live_hog=round(val, 4), unit_note=r["unit_note"],
                         series=r["series"], value_basis=basis, url=r["url"], title=r["title"],
                         release_date=None))
        have.add(key)
    out = pd.concat([main_df, pd.DataFrame(back)], ignore_index=True)
    out = out.sort_values(["freq", "obs", "value_basis"]).reset_index(drop=True)
    cols = ["freq", "obs", "live_hog", "unit_note", "series", "value_basis", "wow_pct", "mom_pct", "yoy_pct",
            "last_year_tab", "release_date", "title", "url", "alt_urls", "note"]
    for c in cols:
        if c not in out:
            out[c] = None
    write_csv(out[cols], PROC / "moa_hist_hog_prices.csv")
    for f, g in out.groupby("freq"):
        print(f, len(g), g["obs"].min(), g["obs"].max(), g["value_basis"].value_counts().to_dict())


if __name__ == "__main__":
    main()
