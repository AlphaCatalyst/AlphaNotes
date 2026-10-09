"""MOA monthly breeding-sow (能繁母猪) data -> moa_sows_monthly.csv

Three sources, kept apart by the `scope` column because they are not the same statistic:
  A. 全国畜牧总站 生产形势 "X月份400个监测县生猪存栏信息" (2017-01 .. 2019-09; 2015-2016 pages are the
     earlier "4000个监测点"): month-on-month / year-on-year % of the monitored sample only.
  B. www.moa.gov.cn/ztzl/szcpxx/jdsj/<year>/<yyyymm>/ 月度数据 (2021-12 ..): national absolute stock
     (万头) with 环比/同比. Quarter-end months print "N季度末" values; after 2025-10 only quarter-end
     values are given.
  C. MOA press releases / interviews (2019-10 .. 2021-11 and 2025-11 ..): figures quoted in the text.
     Extracted with regular expressions; every row keeps the sentence it came from (`evidence`).
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ind_common import (PROC, RAW, SITE_MOA, decode, fetch, flat_text, sogov_search, soup,  # noqa: E402
                        table_rows, to_float, write_csv)

SUB = "moa_sows"
QN = {"1": 1, "2": 2, "3": 3, "4": 4, "一": 1, "二": 2, "三": 3, "四": 4}
CN_MONTH = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "十一": 11, "十二": 12}


def pct(x):
    if x is None:
        return None
    x = str(x).replace("％", "%")
    if x.strip() in ("—", "-", "", "--"):
        return None
    return to_float(x)


def rel_date_from(flat: str, url: str):
    m = re.search(r"(?:日期|发布时间|时间)[：:](20\d{2}-\d{2}-\d{2})", flat)
    if m:
        return m.group(1)
    m = re.search(r"/t(20\d{2})(\d{2})(\d{2})_", url)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


# ---------------------------------------------------------------------------
# A. NAHS 400-county (and 4000-point) monitoring pages
# ---------------------------------------------------------------------------
def nahs_sample() -> pd.DataFrame:
    base = "https://www.nahs.org.cn/jcyj/scxs/"
    b = fetch(base + "index.htm", f"{SUB}/lists", name="nahs_scxs_index.htm", force=True)
    m = re.search(r"createPageHTML\((\d+)", decode(b))
    n = int(m.group(1)) if m else 1
    links = {}
    for p in range(n):
        u = base + ("index.htm" if p == 0 else f"index_{p}.htm")
        bb = b if p == 0 else fetch(u, f"{SUB}/lists", name=f"nahs_scxs_index_{p}.htm", force=True)
        for a in soup(bb).find_all("a"):
            t = re.sub(r"\s+", "", a.get_text(""))
            h = a.get("href") or ""
            if re.search(r"(400个监测县|4000个监测点)生猪存栏信息", t) and re.search(r"t20\d{6}_\d+\.htm", h):
                links[urljoin(u, h)] = t
    rows = []
    for u, t in links.items():
        bb = fetch(u, f"{SUB}/nahs_400")
        if not bb:
            continue
        s = soup(bb)
        flat = flat_text(soup(bb))
        rel = rel_date_from(flat, u)
        scope = "400县样本" if "400个监测县" in t else "4000个监测点样本"
        note = ""
        mm = re.search(r"[※*]([^※*]{0,160}?(样本|回溯)[^※*]{0,120}?。)", flat)
        if mm:
            note = mm.group(1)
        ym = re.search(r"(20\d\d)年(\d{1,2})(?:—(\d{1,2}))?月份", t)
        year = int(ym.group(1))
        tables = [table_rows(tb) for tb in s.find_all("table")]
        got = False
        for rws in tables:
            head = rws[0] if rws else []
            if len(head) >= 5 and "能繁母猪存栏环比" in "".join(head):
                cols = {c: i for i, c in enumerate(head)}
                for r in rws[1:]:
                    mo = re.match(r"(\d{1,2})月", r[0])
                    if not mo or len(r) < 5:
                        continue
                    rows.append(dict(month=f"{year}-{int(mo.group(1)):02d}", sow_wan=None,
                                     sow_mom_pct=pct(r[cols["能繁母猪存栏环比"]]),
                                     sow_yoy_pct=pct(r[cols["能繁母猪存栏同比"]]),
                                     hog_mom_pct=pct(r[cols["生猪存栏环比"]]),
                                     hog_yoy_pct=pct(r[cols["生猪存栏同比"]]),
                                     scope=scope, release_date=rel, url=u, title=t, note=note,
                                     evidence="多月汇总表"))
                got = True
                break
        if not got:
            mom = yoy = None
            for rws in tables:
                for r in rws:
                    if r and r[0].startswith("比上月增减") and len(r) >= 3:
                        mom = (pct(r[1]), pct(r[2]))
                    if r and r[0].startswith("比去年同期增减") and len(r) >= 3:
                        yoy = (pct(r[1]), pct(r[2]))
                if mom and yoy:
                    break
            if mom or yoy:
                rows.append(dict(month=f"{year}-{int(ym.group(2)):02d}", sow_wan=None,
                                 sow_mom_pct=mom[1] if mom else None, sow_yoy_pct=yoy[1] if yoy else None,
                                 hog_mom_pct=mom[0] if mom else None, hog_yoy_pct=yoy[0] if yoy else None,
                                 scope=scope, release_date=rel, url=u, title=t, note=note, evidence="单月表"))
    df = pd.DataFrame(rows)
    # the same release is posted twice (old jchsjcm path and new jcyj path); later revisions
    # (2018-03 sample re-basing) supersede earlier figures -> keep latest release, record others
    out = []
    for mth, g in df.sort_values("release_date").groupby("month"):
        last = g.iloc[-1].to_dict()
        vals = ["sow_mom_pct", "sow_yoy_pct", "hog_mom_pct", "hog_yoy_pct"]
        diffs = []
        for _, o in g.iloc[:-1].iterrows():
            if any(pd.notna(o[v]) and pd.notna(last[v]) and abs(o[v] - last[v]) > 1e-9 for v in vals):
                diffs.append(f"{o['release_date']}版:" + ",".join(f"{v}={o[v]}" for v in vals))
        if diffs:
            last["note"] = (str(last.get("note") or "") + " 被后续发布修订,早期版本→" + "; ".join(diffs)).strip()
        last["alt_urls"] = " ".join(u for u in g["url"].iloc[:-1] if u != last["url"])
        out.append(last)
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# B. MOA 生猪产品信息 月度数据 pages
# ---------------------------------------------------------------------------
def moa_jdsj() -> pd.DataFrame:
    rows = []
    today = dt.date.today()
    for y in range(2021, today.year + 1):
        for m in range(1, 13):
            if (y, m) >= (today.year, today.month):
                break
            u = f"https://www.moa.gov.cn/ztzl/szcpxx/jdsj/{y}/{y}{m:02d}/"
            b = fetch(u, f"{SUB}/jdsj", name=f"jdsj_{y}{m:02d}.html", ok_min_bytes=1000)
            if not b:
                continue
            s = soup(b)
            tb = s.select("table.data_table")
            if not tb:
                continue
            xls = s.find("a", string=re.compile("表格下载"))
            for r in table_rows(tb[0]):
                if len(r) < 5 or "能繁母猪" not in r[1]:
                    continue
                lab, val, mom, yoy = r[1], r[2], r[3], r[4]
                qm = re.search(r"(20\d\d)年([1-4一二三四])季度末", lab)
                mm = re.search(r"(20\d\d)年(\d{1,2})月末", lab)
                if qm:
                    month = f"{qm.group(1)}-{QN[qm.group(2)] * 3:02d}"
                    scope = "全国绝对量(季末)"
                elif mm:
                    month = f"{mm.group(1)}-{int(mm.group(2)):02d}"
                    scope = "全国绝对量(月末)"
                else:
                    continue
                ratio = re.search(r"相当于(正常保有量|调控目标)的(\d+\.?\d*)%", val)
                rows.append(dict(month=month, sow_wan=to_float(val.split("（")[0]), sow_mom_pct=pct(mom),
                                 sow_yoy_pct=pct(yoy), hog_mom_pct=None, hog_yoy_pct=None, scope=scope,
                                 release_date=None, url=u, title=lab,
                                 note=(f"{ratio.group(1)}比例{ratio.group(2)}%" if ratio else ""),
                                 evidence=f"{lab}|{val}|{mom}|{yoy}",
                                 xlsx=urljoin(u, xls["href"]) if xls and xls.get("href") else None))
            # quarter-end hog stock printed on the same page
            for r in table_rows(tb[0]):
                if len(r) >= 5 and re.search(r"季度末生猪存栏", r[1]):
                    qm = re.search(r"(20\d\d)年([1-4一二三四])季度末", r[1])
                    if not qm:
                        continue
                    month = f"{qm.group(1)}-{QN[qm.group(2)] * 3:02d}"
                    for row in rows:
                        if row["month"] == month and row["url"] == u:
                            row["hog_wan"] = to_float(r[2])
                            row["hog_mom_pct"] = pct(r[3])
                            row["hog_yoy_pct"] = pct(r[4])
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# C. press releases
# ---------------------------------------------------------------------------
OK_PATH = re.compile(r"moa\.gov\.cn/(xw/(zwdt|bmdt|tpxw|zxfb|shipin)|hd/|ztzl/szcpxx|gk/|govpublic/)|"
                     r"xmsyj\.moa\.gov\.cn/(gzdt|zcjd|jcyj)|jhs\.moa\.gov\.cn/|scs\.moa\.gov\.cn/tpxw|"
                     r"hzjjs\.moa\.gov\.cn/|scio\.gov\.cn/|www\.gov\.cn/")
NUM = r"(\d+(?:\.\d+)?)"
MONTH_RE = re.compile(r"(?<![\d年])(?:(20\d\d)年)?(\d{1,2})月(?:份|末|底)")
PROVINCES = ("北京|天津|河北|山西|内蒙古|辽宁|吉林|黑龙江|上海|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|广西|"
             "海南|重庆|四川|贵州|云南|西藏|陕西|甘肃|青海|宁夏|新疆")
SUBSET = re.compile(r"规模猪场|规模场|规模以上猪场|500头以上|5000头以上|定点监测村|散养|小散|养殖场户|省份|南方|北方|"
                    r"种猪场|" + PROVINCES)
FIELDS = [
    ("sow_wan", r"能繁母猪存栏(?:量)?(?:为|达到|达|是)?" + NUM + r"万头", 1, None),
    ("sow_mom_pct", r"能繁母猪存栏(?:量)?(?:" + NUM + r"万头)?[^。；，]{0,12}?环比(增长|增加|上升|下降|减少)" + NUM + "%", 3, 2),
    ("sow_yoy_pct", r"能繁母猪存栏(?:量)?(?:" + NUM + r"万头)?[^。；]{0,40}?同比(增长|增加|上升|下降|减少)" + NUM + "%", 3, 2),
    ("hog_wan", r"生猪存栏(?:量)?(?:为|达到|达|是)?" + NUM + r"(亿|万)头", 1, None),
    ("hog_mom_pct", r"生猪存栏(?:量)?(?:" + NUM + r"(?:亿|万)头)?[^。；，]{0,12}?环比(增长|增加|上升|下降|减少)" + NUM + "%", 3, 2),
    ("hog_yoy_pct", r"生猪存栏(?:量)?(?:" + NUM + r"(?:亿|万)头)?[^。；]{0,40}?同比(增长|增加|上升|下降|减少)" + NUM + "%", 3, 2),
]


def _valid_months(clause: str):
    """Month mentions that name the reporting month (not '自去年10月份以来', '比9月份', ...)."""
    out = []
    for mm in MONTH_RE.finditer(clause):
        m = int(mm.group(2))
        if not 1 <= m <= 12:
            continue
        pre = clause[max(0, mm.start() - 3):mm.start()]
        post = clause[mm.end():mm.end() + 3]
        if re.search(r"[自从比较于]|去年|上年|今年|前年|较去|与去", pre) or post.startswith(("以来", "的", "相比", "增")):
            continue
        out.append((mm.start(), mm.group(1), m))
    return out


def extract_news(flat: str, pub: str):
    """Yield dicts (month, field, value, evidence, nbs) from MOA press text.

    Sentences end at 。！？ and clauses at ；. A figure's month is the nearest valid month mention
    at most 25 characters before it in the same clause; a clause without any month mention inherits
    the single month of the previous clause of the same sentence. Sentences about sub-samples
    (规模猪场, 散养户, provinces) are skipped; nbs=True when the sentence cites 国家统计局.
    """
    py, pm = int(pub[:4]), int(pub[5:7])

    def ym(y, m):
        if y:
            return f"{int(y)}-{m:02d}"
        return f"{py if m <= pm else py - 1}-{m:02d}"
    for sent in re.split(r"(?<=[。！？])", flat):
        if ("能繁母猪" not in sent and "生猪存栏" not in sent) or SUBSET.search(sent):
            continue
        nbs = "国家统计局" in sent
        carry = None
        for clause in re.split(r"(?<=；)", sent):
            months = _valid_months(clause)
            pair = re.search(r"能繁母猪存栏量?环比分别(增长|下降)" + NUM + r"%和" + NUM + r"%[，,]同比分别(增长|下降)"
                             + NUM + r"%和" + NUM + "%", clause)
            if pair and len(months) >= 2:
                sg1 = -1 if pair.group(1) == "下降" else 1
                sg2 = -1 if pair.group(4) == "下降" else 1
                for k, (_, y, m) in enumerate(months[:2]):
                    yield dict(month=ym(y, m), field="sow_mom_pct", value=sg1 * float(pair.group(2 + k)), evidence=sent, nbs=nbs)
                    yield dict(month=ym(y, m), field="sow_yoy_pct", value=sg2 * float(pair.group(5 + k)), evidence=sent, nbs=nbs)
                carry = None
                continue
            for fld, pat, gval, gsign in FIELDS:
                for mt in re.finditer(pat, clause):
                    before = [(y, m) for pos, y, m in months if pos < mt.start() and mt.start() - pos <= 25]
                    if before:
                        y, m = before[-1]
                    elif not MONTH_RE.search(clause[:mt.start()]) and carry:
                        y, m = carry
                    else:
                        continue
                    v = float(mt.group(gval))
                    if gsign is not None and mt.group(gsign) in ("下降", "减少"):
                        v = -v
                    if fld == "hog_wan" and mt.group(2) == "亿":
                        v *= 10000
                    yield dict(month=ym(y, m), field=fld, value=v, evidence=sent, nbs=nbs)
            distinct = {(y, m) for _, y, m in months}
            carry = next(iter(distinct)) if len(distinct) == 1 else (None if months else carry)


def news_months():
    out = []
    for y, m in [(2019, mm) for mm in range(10, 13)] + [(2020, mm) for mm in range(1, 13)] + \
                [(2021, mm) for mm in range(1, 12)] + [(2025, mm) for mm in range(11, 13)] + \
                [(2026, mm) for mm in range(1, 10)]:
        out.append((y, m))
    return out


def press() -> pd.DataFrame:
    cands = {}
    for y, m in news_months():
        start = dt.date(y + (m == 12), m % 12 + 1, 1)
        end = start + dt.timedelta(days=60)
        for qt, kp in ((f"{m}月份 能繁母猪", 0), (f"{m}月末 能繁母猪存栏", 0), ("能繁母猪存栏", 1),
                       ("生猪生产", 1), ("能繁母猪", 0), ("生猪存栏", 0), ("能繁母猪存栏量", 0),
                       ("农业农村经济运行", 1), ("新闻发布会 农业农村", 1)):
            for d in sogov_search(SITE_MOA, qt, start.isoformat(), end.isoformat(), key_place=kp,
                                  max_pages=2, cache_subdir=f"{SUB}/search"):
                if OK_PATH.search(d["url"]) and "/xw/qg/" not in d["url"]:
                    cands[d["url"].split("#")[0]] = d
    print(f"press candidates: {len(cands)}")
    rows = []
    for u, d in sorted(cands.items(), key=lambda x: x[1]["date"] or ""):
        b = fetch(u, f"{SUB}/press", sleep=0.4)
        if not b:
            continue
        flat = flat_text(soup(b))
        dates = [x for x in (rel_date_from(flat, u), d["date"]) if x]
        if not dates:
            continue
        pub = min(dates)
        for r in extract_news(flat, pub):
            r.update(url=u, release_date=pub, title=d["title"])
            rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(RAW / SUB / "_press_extractions.csv", index=False)
    return df


def main():
    a = nahs_sample()
    print("A nahs sample:", len(a), a.month.min(), a.month.max())
    b = moa_jdsj()
    print("B jdsj:", len(b), b.month.min() if len(b) else None, b.month.max() if len(b) else None)
    c = press()
    print("C press extractions:", len(c))
    # collapse press extractions: one row per (month, scope), earliest release stating each field
    crow = []
    if len(c):
        c = c[(c.month >= "2019-10") & ~((c.month >= "2021-12") & (c.month <= "2025-10"))].copy()
        c["scope"] = c.apply(lambda r: "国家统计局(经农业农村部稿件转述)" if r.nbs else (
            "400县样本(新闻稿)" if "400个" in r.evidence else "全国(新闻稿)"), axis=1)
        for (mth, sc), g in c.sort_values("release_date").groupby(["month", "scope"]):
            rec = dict(month=mth, scope=sc, sow_wan=None, sow_mom_pct=None, sow_yoy_pct=None,
                       hog_mom_pct=None, hog_yoy_pct=None, hog_wan=None)
            ev, urls, rels, conflicts = [], [], [], []
            for fld, gg in g.groupby("field"):
                first = gg.iloc[0]
                rec[fld] = first.value
                if gg.value.nunique() > 1:
                    conflicts.append(f"{fld}:{sorted(gg.value.unique().tolist())}")
                ev.append(f"[{fld}] {first.evidence[:180]}")
                urls.append(first.url)
                rels.append(first.release_date)
            rec["url"] = " ".join(dict.fromkeys(urls))
            rec["release_date"] = min(rels)
            rec["evidence"] = " || ".join(dict.fromkeys(ev))
            rec["note"] = ("同月多稿数值不一:" + ";".join(conflicts)) if conflicts else "新闻稿正文提取"
            crow.append(rec)
    cdf = pd.DataFrame(crow)
    out = pd.concat([a, b, cdf], ignore_index=True)
    cols = ["month", "sow_wan", "sow_mom_pct", "sow_yoy_pct", "hog_mom_pct", "hog_yoy_pct", "scope",
            "release_date", "url", "hog_wan", "title", "note", "evidence", "alt_urls", "xlsx"]
    for c_ in cols:
        if c_ not in out.columns:
            out[c_] = None
    out = out[cols].sort_values(["month", "scope"]).reset_index(drop=True)
    write_csv(out, PROC / "moa_sows_monthly.csv")
    print(out.groupby("scope").month.agg(["min", "max", "count"]))


if __name__ == "__main__":
    main()
