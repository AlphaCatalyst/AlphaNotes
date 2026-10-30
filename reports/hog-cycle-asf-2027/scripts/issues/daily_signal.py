"""Issue #9: what a one-day drop in Mysteel's key-farm hog sales, plus a firmer Henan quote, can and cannot say
about prices, supply and the cycle.

  fetch     (network) Mysteel's free daily posts "重点养殖企业日度出栏量统计情况" (2025-03-17 onward). For
            visitors the post shows an AI summary with that day's national total and change, and the first
            row of the table, i.e. the previous working day by region. The post of day t therefore gives the
            regional split of the working day before t. Also caches the Mysteel posts cited in the answer
            (plans, weekly and regional dailies, spreads), every 中国养猪网 provincial table since September
            (the regular crawl samples two days a week) and the 中国养猪网 Henan city pages as they stood
            when fetched (the pages only show the latest day), and Tencent daily bars of Muyuan and Wens.
            Raw pages -> research/daily_signal/_raw/; parsed series -> data/processed/mysteel_sales_daily.csv
            and zhuwang_province_recent.csv (local only, like the other third-party series).
  build     claim check, size of daily moves by region, calendar effects, month turns, price after large
            drops, Henan signals, the author's dated calls, Q3 official data against Issue #6, hog stocks
            around the drops and since the author's calls.

Inputs (data/processed/): nbs_quarterly.csv, moa_sows_monthly.csv, moa_weekly_prices.csv; local only:
mysteel_sales_daily.csv, nxin_province_daily.csv, nxin_region_weekly.csv, zhuwang_province_daily.csv,
zhuwang_province_recent.csv, futures_lh_daily.csv, csi_index_daily.csv (run scripts/fetch_csi_index.py
20261030 first); research/daily_signal/calls.csv; Issue #6's outputs (ad_supply_schedule.csv) and functions
(autumn_dip.py).
Outputs: data/processed/issues/ds_*.csv (derived only), charts/i09_*.png.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
OUT = PROC / "issues"
RES = ROOT / "research" / "daily_signal"
RAW = RES / "_raw" / "mysteel"
ZW_RAW = RES / "_raw" / "zhuwang"
STOCK_RAW = RES / "_raw" / "stocks"
SALES = PROC / "mysteel_sales_daily.csv"
ZW_RECENT = PROC / "zhuwang_province_recent.csv"
sys.path.insert(0, str(ROOT / "scripts"))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
LIST = "https://zhuye.mysteel.com/shengzhu/article/p-{col}----070705---------{page}.html?keyWord={kw}"
REGIONS = ["东北", "华北", "西北", "华东", "华中", "华南", "西南"]
# (column, keyword, title pattern, pages) of the Mysteel lists crawled; the list stops after 10 pages
LISTS = [
    ("4118", "重点养殖企业日度出栏量", "重点养殖企业日度出栏量统计", 10),
    ("4118", "计划出栏", "计划出栏", 2),
    ("4267", "周报", "Mysteel周报", 1),
    ("4115", "标肥价差", "标肥价差", 1),
    ("4115", "二次育肥", "二次育肥", 1),
    ("4116", "批发市场到货量", "到货量", 1),
    ("4115", "解读", "生猪", 1),
    ("4115", "前瞻", "前瞻", 1),
    ("4266", "生猪", "Mysteel日报", 2),
    ("4266", "豫皖", "豫皖", 3),
]
HENAN_CITIES = [f"41{c:02d}00" for c in range(1, 18)]
STOCKS = {"002714": "牧原股份", "300498": "温氏股份"}

ASOF = pd.Timestamp("2026-10-30")
# the post in the issue: national, East China and Southwest changes on 10-30
CLAIM = {"全国": -0.045, "华东": -0.082, "西南": -0.1308}
DROP = -0.045
HORIZONS = (2, 7, 14, 30, 91)  # calendar days: the weekend, 1 week, 2 weeks, 1 month, 3 months


# ---------------------------------------------------------------------------
# fetch and parse
# ---------------------------------------------------------------------------
def session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    return s


def get(s: requests.Session, url: str, path: Path, force: bool = False) -> str:
    if path.exists() and not force:
        return path.read_bytes().decode("utf-8", "ignore")
    for i in range(3):
        try:
            r = s.get(url, timeout=30)
            if r.status_code == 200 and len(r.content) > 2000:
                path.write_bytes(r.content)
                time.sleep(0.6)
                return r.content.decode("utf-8", "ignore")
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"failed: {url}")


def list_items(html: str) -> list[tuple[str, str]]:
    return re.findall(r'href="(https?://ncp\.mysteel\.com/a/\d{8}/[0-9A-F]+\.html)"[^>]*>([^<]+)<', html)


def article_name(url: str) -> str:
    m = re.search(r"/a/(\d{8})/([0-9A-F]+)\.html", url)
    return f"{m.group(1)}_{m.group(2)}.html"


def fetch():
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "lists").mkdir(exist_ok=True)
    s = session()
    rows = []
    for col, kw, pat, pages in LISTS:
        for p in range(1, pages + 1):
            url = LIST.format(col=col, page=p, kw=quote(kw))
            html = get(s, url, RAW / "lists" / f"p{col}_{kw}_{p}.html", force=True)
            for u, title in list_items(html):
                if pat in title:
                    rows.append(dict(list=f"{col}:{kw}", url=u, title=title.strip()))
    idx = pd.DataFrame(rows).drop_duplicates("url")
    idx.to_csv(RAW / "_index.csv", index=False)
    print("articles", len(idx), idx.groupby("list").size().to_dict())
    for u in idx.url:
        get(s, u, RAW / article_name(u))
    parse_sales(idx)
    fetch_zhuwang(s)
    fetch_stocks()


def fetch_stocks():
    """Backward-adjusted and raw closes; Tencent's adjusted series can lag the raw one by a day."""
    from common import save_json, tx_kline
    for code in STOCKS:
        for fq in ("hfq", ""):
            save_json(tx_kline(code, fq, beg="2025-01-01", end=f"{ASOF:%Y-%m-%d}"), STOCK_RAW / f"{code}_{fq or 'raw'}.json")


def fetch_zhuwang(s: requests.Session):
    sys.path.insert(0, str(ROOT / "scripts" / "industry"))
    import zhuwang_prices as zw
    idx = pd.read_csv(ROOT / "data" / "raw" / "industry" / "zhuwang" / "article_index.csv", parse_dates=["date"])
    idx = idx[idx["date"] >= "2026-09-01"]
    rows = [r for u, d in zip(idx["url"], idx["date"]) for r in zw.parse(u, d)]
    pd.DataFrame(rows).to_csv(ZW_RECENT, index=False, encoding="utf-8")
    ZW_RAW.mkdir(parents=True, exist_ok=True)
    stamp = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M")
    out = []
    for c in ["410000"] + HENAN_CITIES:
        page = "areapriceinfo" if c == "410000" else "pigprice"
        x = flat(get(s, f"https://zhujia.zhuwang.com.cn/{page}-{c}.shtml", ZW_RAW / f"{page}-{c}.shtml", force=True))
        head = re.search(r"返回旧版 (\S+) (\d{4}/\d{1,2}/\d{1,2})", x)
        for breed, price, chg in re.findall(r"生猪\((外三元|内三元|土杂猪)\) ([\d.]+) ([-\d.]+)元", x):
            out.append(dict(code=c, area=head.group(1), date=pd.Timestamp(head.group(2)).date(), breed=breed,
                            price=float(price), chg_day=float(chg), fetched=stamp))
    pd.DataFrame(out).drop_duplicates(["code", "breed"]).to_csv(ZW_RAW / "henan_cities.csv", index=False)
    print("zhuwang: provinces", len(rows), "henan pages", len(out), stamp)


def flat(html: str) -> str:
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def summary(html: str) -> str:
    m = re.search(r'data-ai-content-summary="([^"]*)"', html)
    return m.group(1).strip() if m else ""


def published(html: str) -> str:
    m = re.search(r'name="publish" content="published at ([\d\- :]+)', html)
    return m.group(1).strip() if m else ""


def parse_sales(idx: pd.DataFrame):
    """One row per (date, field source): the summary's national total for the post date and the table's
    previous-working-day row; the two are compared in build()."""
    out = []
    num = r"(\d{4})年(\d{1,2})月(\d{1,2})日"
    for u, title in idx.loc[idx.title.str.contains("出栏量统计"), ["url", "title"]].itertuples(index=False):
        html = (RAW / article_name(u)).read_bytes().decode("utf-8", "ignore")
        post = re.search(r"（(\d{8})）", title).group(1)
        post = f"{post[:4]}-{post[4:6]}-{post[6:]}"
        pub, summ = published(html), summary(html)
        m = re.search(num + r"重点养殖企业全国生猪日度出栏量为(\d+)头[，,]\s*(?:较上一工作日|较昨日|较前一日|环比)?"
                      r"(增量|减量|增加|减少|上涨|下跌|上升|下降|增长|持平)?(\d+(?:\.\d+)?)?%?", summ)
        if m:
            d = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            sign = -1 if m.group(5) in ("减量", "减少", "下跌", "下降") else 1
            chg = sign * float(m.group(6)) / 100 if m.group(6) else (0.0 if m.group(5) == "持平" else None)
            out.append(dict(date=d, kind="summary", total=int(m.group(4)), chg_summary=chg, post=post,
                            published=pub, url=u, summary=summ))
        text = flat(html)
        m = re.search(r"日期 东北 华北 西北 华东 华中 华南 西南 总计 " + num + r"((?: \d+){8})", text)
        if m:
            d = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            v = [int(x) for x in m.group(4).split()]
            out.append(dict(date=d, kind="table", total=v[-1], **dict(zip(REGIONS, v[:-1])), post=post,
                            published=pub, url=u))
    df = pd.DataFrame(out).sort_values(["date", "kind"])
    df.to_csv(SALES, index=False, encoding="utf-8")
    print("parsed", len(df), df.groupby("kind").date.agg(["min", "max", "count"]).to_dict())


# ---------------------------------------------------------------------------
# series
# ---------------------------------------------------------------------------
def write(df: pd.DataFrame, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / name, index=False, encoding="utf-8")


def nxin(province: str = "全国") -> pd.Series:
    d = pd.read_csv(PROC / "nxin_province_daily.csv", parse_dates=["date"])
    return d[(d["province"] == province) & (d["date"] <= ASOF)].set_index("date")["price"].sort_index()


def nxin_weekly() -> pd.Series:
    w = pd.read_csv(PROC / "nxin_region_weekly.csv")
    w = w[w["region"] == "全国"].dropna(subset=["price"])
    # a value labelled Monday L covers L-7..L-1; dated to that week's Friday
    s = pd.Series(w["price"].values, index=pd.to_datetime(w["week_label"]) - pd.Timedelta(days=3))
    return s[~s.index.duplicated(keep="last")].sort_index()


def fwd(s: pd.Series, t: pd.Timestamp, days: int, tol: int = 3) -> float:
    """Change from the last value on or before t to the first value in [t+days, t+days+tol]."""
    base = s.loc[:t]
    tgt = s.loc[t + pd.Timedelta(days=days):t + pd.Timedelta(days=days + tol)]
    return float(tgt.iloc[0] / base.iloc[-1] - 1) if len(base) and len(tgt) else np.nan


def off_days(a, b) -> float:
    """Weekdays strictly between two consecutive working days: a holiday, or a post missing from the crawl."""
    if pd.isna(a) or pd.isna(b):
        return np.nan
    return float((pd.date_range(a, b)[1:-1].weekday < 5).sum())


def sales() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Working-day sales from the table rows, plus the summary total for the last post day, whose table row
    is not out yet. `regular` marks days compared with the working day just before (no holiday between)."""
    s = pd.read_csv(SALES, parse_dates=["date"])
    tab = s[s["kind"] == "table"].sort_values("post").drop_duplicates("date", keep="last").set_index("date")
    summ = s[s["kind"] == "summary"].sort_values("post").drop_duplicates("date", keep="last").set_index("date")
    d = tab[REGIONS + ["total"]].astype(float)
    d = pd.concat([d, summ.loc[summ.index.difference(d.index), ["total"]].astype(float)]).sort_index()
    d = d[d.index <= ASOF]
    dates = d.index.to_series()
    d["gap_before"] = [off_days(a, b) for a, b in zip(dates.shift(), dates)]
    d["gap_after"] = [off_days(a, b) for a, b in zip(dates, dates.shift(-1))]
    d.loc[ASOF, "gap_after"] = 0.0  # 10-30 is a Friday and 11-02 a working day
    d["regular"] = d["gap_before"] == 0
    d["chg"] = d["total"].pct_change()
    for r in REGIONS:
        d[r + "_chg"] = d[r].pct_change(fill_method=None)
    mon = d.index.to_period("M")
    d["pos_end"] = d.groupby(mon).cumcount(ascending=False) + 1
    d["pos_start"] = (d.groupby(mon).cumcount() + 1).where(d.index >= "2025-04-01")
    both = summ.index.intersection(tab.index)
    rev = pd.DataFrame({"date": both.date, "same_day_summary": summ.loc[both, "total"].values,
                        "next_post_table": tab.loc[both, "total"].values,
                        "stated_chg": summ.loc[both, "chg_summary"].values,
                        "computed_chg": d.loc[both, "chg"].values})
    return d, rev


# ---------------------------------------------------------------------------
# 1. the claim and the size of daily moves
# ---------------------------------------------------------------------------
def claim_check(d: pd.DataFrame, rev: pd.DataFrame, nat: pd.Series) -> pd.DataFrame:
    t, prev = d.loc[ASOF], d.loc[d.index[-2]]
    y26 = d.loc["2026-01-01":, "total"]
    ly = d.loc["2025-10-20":"2025-11-07", "total"]
    oct26, sep26, oct25 = (d.loc[a:b, "total"].mean() for a, b in
                           (("2026-10-08", "2026-10-29"), ("2026-09-01", "2026-09-30"), ("2025-10-09", "2025-10-31")))
    late26, late25, early25 = (d.loc[a:b, "total"].mean() for a, b in
                               (("2026-10-19", "2026-10-30"), ("2025-10-20", "2025-10-31"), ("2025-11-03", "2025-11-14")))
    wk, wk_prev, wk_ly = (d.loc[a:b, "total"] for a, b in
                          (("2026-10-26", "2026-10-30"), ("2026-10-19", "2026-10-23"), ("2025-10-27", "2025-10-31")))
    p0 = nat.loc[:ASOF]
    rows = [
        dict(item="全国 10-30 出栏（头）", value=t["total"], note=f"较 {d.index[-2]:%m-%d} 的 {prev['total']:.0f} 头 {t['chg']:+.2%}"),
        dict(item="全国 10-30 减少（头）", value=prev["total"] - t["total"], note=""),
        dict(item="10-30 水平在 2026 年工作日中的分位", value=(y26 < t["total"]).mean(),
             note=f"2026 年最高 {y26.max():.0f}（{y26.idxmax():%m-%d}），10 月均值 {d.loc['2026-10', 'total'].mean():.0f}"),
        dict(item="10-30 较 2025-10-30 同比", value=t["total"] / d.loc["2025-10-30", "total"] - 1,
             note=f"2025-10-30 为 {d.loc['2025-10-30', 'total']:.0f} 头"),
        dict(item="2025-10-20 至 11-07 出栏区间（头）", value=ly.max() - ly.min(),
             note=f"最高 {ly.max():.0f}（{ly.idxmax():%m-%d}），最低 {ly.min():.0f}（{ly.idxmin():%m-%d}）"),
        dict(item="10 月样本日均（10-08 至 10-29）较 9 月", value=oct26 / sep26 - 1, note=f"10 月 {oct26:.0f} 头，9 月 {sep26:.0f} 头"),
        dict(item="10 月样本日均较 2025 年 10 月", value=oct26 / oct25 - 1, note=f"2025 年 10 月 {oct25:.0f} 头"),
        dict(item="10-19 至 10-30 样本日均的同比", value=late26 / late25 - 1,
             note=f"{late26:.0f} 头；2025-10-20 至 10-31 为 {late25:.0f} 头，2025-11-03 至 11-14 为 {early25:.0f} 头"
                  f"（较前两周 {early25 / late25 - 1:+.1%}）"),
        dict(item="10-26 至 10-30 一周日均较前一周", value=wk.mean() / wk_prev.mean() - 1,
             note=f"{wk.mean():.0f} 头（{len(wk)} 天）；10-19 至 10-23 为 {wk_prev.mean():.0f} 头（{len(wk_prev)} 天）"),
        dict(item="10-26 至 10-30 一周日均较 2025 年同一周", value=wk.mean() / wk_ly.mean() - 1,
             note=f"2025-10-27 至 10-31 为 {wk_ly.mean():.0f} 头（{len(wk_ly)} 天）"),
        dict(item="10-29 全国均价较 30 天前（新牧网）", value=p0.iloc[-1] / p0.loc[:p0.index[-1] - pd.Timedelta(days=30)].iloc[-1] - 1,
             note=f"{p0.index[-1]:%m-%d} 为 {p0.iloc[-1]:.2f} 元/公斤"),
    ]
    for r in ("华东", "西南"):
        drop = prev[r] * -CLAIM[r]
        rows.append(dict(item=f"{r} 按 {CLAIM[r]:.2%} 推算的减少（头）", value=drop,
                         note=f"10-29 为 {prev[r]:.0f} 头，推算 10-30 约 {prev[r] + drop * -1:.0f} 头；分区数要等 11-02 的帖子"))
    other = (prev["total"] - t["total"]) - sum(prev[r] * -CLAIM[r] for r in ("华东", "西南"))
    rows.append(dict(item="其余五区合计变化（头，推算）", value=-other, note="全国减少量减去华东、西南的推算减少量"))
    same = rev.dropna(subset=["next_post_table"])
    rows.append(dict(item="当日摘要总量与次日表格总量一致的天数", value=int((same["same_day_summary"] == same["next_post_table"]).sum()),
                     note=f"共 {len(same)} 天可比"))
    return pd.DataFrame(rows)


def change_stats(d: pd.DataFrame) -> pd.DataFrame:
    reg = d[d["regular"]]
    rows = []
    for name in ["全国"] + REGIONS:
        x = reg["chg" if name == "全国" else name + "_chg"].dropna()
        claim = CLAIM.get(name)
        rows.append(dict(series=name, n=len(x), sd=x.std(), q01=x.quantile(0.01), q05=x.quantile(0.05),
                         q95=x.quantile(0.95), share_unchanged=(x == 0).mean(),
                         share_of_total=1.0 if name == "全国" else (reg[name] / reg["total"]).mean(),
                         claim=claim, claim_rank=(x <= claim).mean() if claim else np.nan,
                         days_at_or_below_claim=(x <= claim).sum() if claim else np.nan))
    return pd.DataFrame(rows)


def calendar(d: pd.DataFrame) -> pd.DataFrame:
    reg = d[d["regular"] & (d.index >= "2025-04-01")].dropna(subset=["chg"])
    wd = reg.index.weekday
    groups = [("全部常规工作日", reg)] + [(f"周{'一二三四五'[i]}", reg[wd == i]) for i in range(5)] + [
        ("月末最后一个工作日", reg[reg["pos_end"] == 1]),
        ("月末倒数第 2—4 个工作日", reg[reg["pos_end"].between(2, 4)]),
        ("月初第 1 个工作日", reg[reg["pos_start"] == 1]),
        ("月初第 2—4 个工作日", reg[reg["pos_start"].between(2, 4)]),
        ("长假前最后一个工作日", reg[reg["gap_after"] > 0]),
        ("长假后第一个工作日（与节前比）", d[(d["gap_before"] > 0) & (d.index >= "2025-04-01")].dropna(subset=["chg"])),
    ]
    return pd.DataFrame([dict(group=k, n=len(g), mean=g["chg"].mean(), median=g["chg"].median(),
                              share_down=(g["chg"] < 0).mean(), share_le_drop=(g["chg"] <= DROP).mean())
                         for k, g in groups])


def month_turns(d: pd.DataFrame, nat: pd.Series) -> pd.DataFrame:
    rows = []
    for mon, g in d[d.index >= "2025-04-01"].groupby(d[d.index >= "2025-04-01"].index.to_period("M")):
        nxt = d[d.index > g.index[-1]].head(5)
        last = g.iloc[-1]
        rows.append(dict(month=str(mon), last_day=g.index[-1].date(), last_chg=last["chg"],
                         last_two_days=last["total"] / g["total"].iloc[-3] - 1,
                         last_vs_month_mean=last["total"] / g["total"].mean() - 1,
                         holiday_after=bool(last["gap_after"] > 0),
                         first_day=nxt.index[0].date() if len(nxt) else None,
                         first_chg=nxt["chg"].iloc[0] if len(nxt) else np.nan,
                         first5_vs_last=nxt["total"].mean() / last["total"] - 1 if len(nxt) == 5 else np.nan,
                         first5_vs_prev_month_mean=nxt["total"].mean() / g["total"].mean() - 1 if len(nxt) == 5 else np.nan,
                         **{f"national_{h}d": fwd(nat, g.index[-1], h) for h in (2, 7, 14)}))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. what followed large drops
# ---------------------------------------------------------------------------
def drop_events(d: pd.DataFrame, nat: pd.Series, hn: pd.Series) -> pd.DataFrame:
    reg = d[d["regular"]]
    tot = d["total"]
    rows = []
    for t, r in reg[reg["chg"] <= -0.03].iterrows():
        i = d.index.get_loc(t)
        nxt = tot.iloc[i + 1:i + 6]
        rec = dict(date=t.date(), weekday=t.weekday() + 1, chg=r["chg"], total=r["total"], pos_end=r["pos_end"],
                   holiday_after=bool(r["gap_after"] > 0),
                   next_chg=d["chg"].iloc[i + 1] if i + 1 < len(d) else np.nan,
                   next5_vs_before=nxt.mean() / tot.iloc[i - 1] - 1 if len(nxt) == 5 else np.nan)
        for h in HORIZONS:
            rec[f"national_{h}d"] = fwd(nat, t, h)
        for h in (2, 7, 14):
            rec[f"henan_{h}d"] = fwd(hn, t, h)
        rows.append(rec)
    return pd.DataFrame(rows)


def new_low(s: pd.Series, t: pd.Timestamp, days: int) -> float:
    """1.0 if within `days` days after t the series falls below its low of the 30 days up to t."""
    if s.index[-1] < t + pd.Timedelta(days=days):
        return np.nan
    after = s.loc[t + pd.Timedelta(days=1):t + pd.Timedelta(days=days)]
    return float(after.min() < s.loc[t - pd.Timedelta(days=30):t].min())


def event_study(d: pd.DataFrame, nat: pd.Series, nw: pd.Series, hn: pd.Series) -> pd.DataFrame:
    reg = d[d["regular"]].dropna(subset=["chg"])
    big = reg["chg"] <= -0.03
    prior = pd.Series([nat.loc[:t].iloc[-1] / nat.loc[:t - pd.Timedelta(days=30)].iloc[-1] - 1 for t in reg.index],
                      index=reg.index)
    slump = prior <= -0.05
    # drops cluster (6-26, 6-30, 7-03); keep a drop only if the previous one is at least 10 working days back
    at = pd.Series(np.arange(len(d)), index=d.index)[reg.index[big]]
    spaced = reg.index.isin(at.index[at.diff().fillna(np.inf) >= 10])
    henan_up = pd.Series([t in hn.index and hn[t] > hn.loc[:t - pd.Timedelta(days=1)].iloc[-1] for t in reg.index],
                         index=reg.index)
    sets = [("出栏单日降幅 ≥ 4.5%", reg[reg["chg"] <= DROP]),
            ("出栏单日降幅 ≥ 3%", reg[big]),
            ("　其中与上一次相隔 ≥ 10 个工作日", reg[spaced]),
            ("　其中当天河南均价上涨", reg[big & henan_up]),
            ("　其中月末最后一个工作日", reg[big & (reg["pos_end"] == 1)]),
            ("　其中非月末、非节前", reg[big & (reg["pos_end"] > 1) & ~(reg["gap_after"] > 0)]),
            ("　其中此前 30 天全国均价已跌 ≥ 5%", reg[big & slump]),
            ("　其中此前 30 天跌幅不到 5% 或上涨", reg[big & ~slump]),
            ("此前 30 天全国均价已跌 ≥ 5% 的全部工作日", reg[slump]),
            ("月末最后一个工作日（不论降幅）", reg[reg["pos_end"] == 1]),
            ("出栏单日增幅 ≥ 3%", reg[reg["chg"] >= 0.03]),
            ("全部常规工作日", reg),
            ("10—11 月常规工作日", reg[reg.index.month.isin([10, 11])])]
    rows = []
    for name, g in sets:
        for h in HORIZONS:
            x = pd.Series([fwd(nat, t, h) for t in g.index], dtype=float).dropna()
            low = pd.Series([new_low(nat, t, h) for t in g.index], dtype=float).dropna()
            rows.append(dict(set=name, horizon_days=h, n=len(x), mean=x.mean(), median=x.median(),
                             share_up=(x > 0).mean(), share_up_5pct=(x >= 0.05).mean(),
                             share_new_low=low.mean(), sample="新牧网全国日度"))
    for h in HORIZONS[1:]:
        x = pd.Series([fwd(nw, pd.Timestamp(f"{y}-10-30"), h, tol=6) for y in range(2015, 2026)]).dropna()
        rows.append(dict(set="季节基准：2015—2025 年各年 10-30 起", horizon_days=h, n=len(x), mean=x.mean(),
                         median=x.median(), share_up=(x > 0).mean(), share_up_5pct=(x >= 0.05).mean(),
                         sample="新牧网全国周度"))
    return pd.DataFrame(rows)


def seasonal_years(nw: pd.Series) -> pd.DataFrame:
    rows = []
    for y in range(2015, 2026):
        t = pd.Timestamp(f"{y}-10-30")
        rows.append(dict(year=y, price=nw.loc[:t].iloc[-1], **{f"chg_{h}d": fwd(nw, t, h, tol=6) for h in HORIZONS[1:]}))
    return pd.DataFrame(rows)


def lead_lag(d: pd.DataFrame, nat: pd.Series) -> pd.DataFrame:
    """Correlation of the day's sales change with the price change k working days later (k > 0: sales first)."""
    p = nat.reindex(d.index)
    dp = p / p.shift(1) - 1
    rows = []
    for k in range(-5, 6):
        x = pd.DataFrame({"s": d["chg"], "p": dp.shift(-k)})[d["regular"]].dropna()
        rows.append(dict(window=f"单日价格变化，第 {k:+d} 个工作日", lag=k, n=len(x), corr=x["s"].corr(x["p"])))
    for name, ser in (("此前 5 个工作日价格累计变化", p / p.shift(5) - 1), ("此后 5 个工作日价格累计变化", p.shift(-5) / p - 1),
                      ("此后 10 个工作日价格累计变化", p.shift(-10) / p - 1)):
        x = pd.DataFrame({"s": d["chg"], "p": ser})[d["regular"]].dropna()
        rows.append(dict(window=name, lag=np.nan, n=len(x), corr=x["s"].corr(x["p"])))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. Henan
# ---------------------------------------------------------------------------
def henan_signal(nat: pd.Series, hn: pd.Series) -> pd.DataFrame:
    n, h = nat.asfreq("D").ffill(), hn.asfreq("D").ffill()
    dn, dh = n.diff(), h.diff()
    h7 = h / h.shift(7) - 1
    rows = []
    cases = {"河南上涨、全国下跌（同一天）": (dh > 0) & (dn < 0),
             "河南上涨，此前 7 天累计跌 ≥ 3%": (dh > 0) & (h7.shift(1) <= -0.03),
             "全部日子": dh.notna()}
    for name, mask in cases.items():
        idx = mask[mask].index
        for hz in (1, 2, 7, 14, 30):
            x = pd.Series([n.get(t + pd.Timedelta(days=hz), np.nan) / n[t] - 1 for t in idx]).dropna()
            rows.append(dict(sample="新牧网日度，2025-01—2026-10", case=name, horizon_days=hz, n=len(x),
                             median=x.median(), share_up=(x > 0).mean(), target="全国"))
    z = pd.read_csv(PROC / "zhuwang_province_daily.csv", parse_dates=["date"])
    zh = z[z["province"] == "河南"].set_index("date").sort_index()
    wk = zh["chg_week"] / (zh["price"] - zh["chg_week"])
    nw = nxin_weekly()
    up = (zh["chg_day"] > 0) & (wk <= -0.03)
    autumn = zh.index.month.isin([10, 11])
    cases = {"河南单日上涨，一周累计跌 ≥ 3%": up, "　其中 10—11 月": up & autumn,
             "全部样本日": zh["chg_day"].notna(), "10—11 月样本日": zh["chg_day"].notna() & autumn}
    for name, mask in cases.items():
        idx = mask[mask].index
        for hz in (14, 30, 91):
            for target, s, tol in (("河南", zh["price"], 5), ("全国", nw, 7)):
                x = pd.Series([fwd(s, t, hz, tol=tol) for t in idx]).dropna()
                rows.append(dict(sample="中国养猪网每周两天，2015-12—2026-10", case=name, horizon_days=hz,
                                 n=len(x), median=x.median(), share_up=(x > 0).mean(), target=target))
    return pd.DataFrame(rows)


def henan_snapshot() -> pd.DataFrame:
    zr = pd.read_csv(ZW_RECENT, parse_dates=["date"])
    day = zr[zr["date"] == ASOF]
    c = pd.read_csv(ZW_RAW / "henan_cities.csv")
    cities = c[(c["code"] != 410000) & (c["breed"] == "外三元")]
    prov = c[c["code"] == 410000].set_index("breed")
    rows = [dict(item="中国养猪网各省外三元（10-30 早间表）", n=len(day), up=int((day["chg_day"] > 0).sum()),
                 flat=int((day["chg_day"] == 0).sum()), down=int((day["chg_day"] < 0).sum()),
                 henan=float(day.loc[day["province"] == "河南", "chg_day"].iloc[0]) if (day["province"] == "河南").any() else np.nan,
                 note="河南一列为河南省均价的单日变化（元/公斤）"),
            dict(item="中国养猪网河南 17 个地市外三元（页面）", n=len(cities), up=int((cities["chg_day"] > 0).sum()),
                 flat=int((cities["chg_day"] == 0).sum()), down=int((cities["chg_day"] < 0).sum()),
                 henan=float(cities["chg_day"].median()),
                 note=f"河南一列为地市中位数；上涨的地市：{'、'.join(cities.loc[cities['chg_day'] > 0, 'area'])}；页面取于 {c['fetched'].iloc[0]}")]
    for breed in ("外三元", "内三元", "土杂猪"):
        if breed in prov.index:
            rows.append(dict(item=f"中国养猪网河南省 {breed}（页面）", n=1, up=int(prov.loc[breed, "chg_day"] > 0), flat=0,
                             down=int(prov.loc[breed, "chg_day"] < 0), henan=float(prov.loc[breed, "chg_day"]),
                             note=f"价格 {prov.loc[breed, 'price']:.2f} 元/公斤"))
    return pd.DataFrame(rows)


def mysteel_henan() -> pd.DataFrame:
    """Henan price lines in Mysteel's 豫皖 daily summaries (free part)."""
    idx = pd.read_csv(RAW / "_index.csv")
    rows = []
    for u, title in idx.loc[idx["title"].str.contains("豫皖"), ["url", "title"]].itertuples(index=False):
        p = RAW / article_name(u)
        if not p.exists():
            continue
        s = summary(p.read_bytes().decode("utf-8", "ignore"))
        day = re.search(r"（(\d{8})）", title).group(1)
        m = re.search(r"河南(?:市场)?(?:外三元)?(?:标猪)?(?:生猪)?出栏均价(?:为)?(\d+\.\d+)元/公斤[，,]?\s*较?(?:昨日|上个工作日|前一日)?"
                      r"(上涨|下跌|上调|下调|涨|跌|持稳|稳定|持平)(\d+\.\d+)?", s)
        if m:
            sign = -1 if m.group(2) in ("下跌", "下调", "跌") else 1
            chg = sign * float(m.group(3)) if m.group(3) else 0.0
            word = "涨" if chg > 0 else ("跌" if chg < 0 else "平")
            rows.append(dict(date=pd.Timestamp(day).date(), price=float(m.group(1)), chg=chg, word=word, basis="摘要", url=u))
        else:
            # Older posts have no free summary; the headline still carries the direction for 豫皖 as a whole.
            text = s or title
            word = ("涨" if re.search(r"上调|上涨|走高|走强|偏强|小涨|微涨|反弹", text)
                    else "跌" if re.search(r"下调|下跌|走低|偏弱|小降|微降|下滑|回落|走弱", text) else "")
            rows.append(dict(date=pd.Timestamp(day).date(), price=np.nan, chg=np.nan, word=word,
                             basis="摘要（无价格）" if s else "标题", url=u))
    return pd.DataFrame(rows).sort_values("date")


# ---------------------------------------------------------------------------
# 4. the author's calls, and the official quarter
# ---------------------------------------------------------------------------
def calls(nat: pd.Series) -> pd.DataFrame:
    c = pd.read_csv(RES / "calls.csv", dtype=str)
    out = []
    for _, r in c.iterrows():
        t = pd.Timestamp(r["date"])
        after = nat.loc[t + pd.Timedelta(days=1):]
        p0 = nat.loc[:t].iloc[-1]
        out.append(dict(id=r["id"], price_at_call=p0,
                        max_after=after.max() if len(after) else np.nan,
                        max_date=after.idxmax().date() if len(after) else None,
                        min_after=after.min() if len(after) else np.nan,
                        min_date=after.idxmin().date() if len(after) else None,
                        latest=nat.iloc[-1], latest_date=nat.index[-1].date(), latest_vs_call=nat.iloc[-1] / p0 - 1))
    return c[["id", "date", "post_id", "layer", "quote"]].merge(pd.DataFrame(out), on="id")


def supply() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Issue #6's sow-lag schedule rerun with the September sows and NBS Q3; #6's published figures alongside."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import autumn_dip as ad
    sows, _ = ad.sows_monthly()
    ps = ad.per_sow(sows)
    sch, rng = ad.schedule(sows, ps)
    old = pd.read_csv(OUT / "ad_supply_schedule.csv")
    keep = ["quarter", "sow_path", "slaughter_yoy_low", "slaughter_yoy_base", "slaughter_yoy_high", "uses_scenario"]
    sch = sch.merge(old[keep], on=["quarter", "sow_path"], how="left", suffixes=("", "_i06"))
    q = ps.loc[ps.index >= pd.Period("2025Q1", "Q"), ["slaughter", "pork", "carcass", "sows_lag", "per_sow",
                                                       "slaughter_yoy", "pork_yoy", "carcass_yoy", "per_sow_yoy"]]
    q = q.reset_index(names="quarter")
    q["quarter"] = q["quarter"].astype(str)
    sch["per_sow_range"] = f"{rng['low']:+.4f}/{rng['base']:+.4f}/{rng['high']:+.4f}"
    return sch, q


def futures_curve() -> pd.DataFrame:
    f = pd.read_csv(PROC / "futures_lh_daily.csv", parse_dates=["trade_date"])
    f = f[f["contract"].str.fullmatch(r"LH\d{4}") & f["trade_date"].isin(
        [pd.Timestamp(x) for x in ("2026-10-09", "2026-10-19", "2026-10-29", "2026-10-30")])]
    return f.pivot_table(index="contract", columns=f["trade_date"].dt.strftime("%m-%d"), values="settle").reset_index()


# ---------------------------------------------------------------------------
# 5. hog stocks
# ---------------------------------------------------------------------------
def stock_prices() -> pd.DataFrame:
    from common import load_json
    csi = pd.read_csv(PROC / "csi_index_daily.csv", dtype={"index": str}, parse_dates=["date"])
    px = csi.pivot(index="date", columns="name", values="close")[["中证畜牧养殖", "中证全指"]].loc["2025-01-01":ASOF]
    for code, name in STOCKS.items():
        adj, raw = (pd.Series({pd.Timestamp(x["date"]): x["close"] for x in load_json(STOCK_RAW / f"{code}_{fq}.json")})
                    for fq in ("hfq", "raw"))
        for t in raw.index[raw.index > adj.index[-1]]:
            adj[t] = adj.iloc[-1] * raw[t] / raw[raw.index < t].iloc[-1]
        px[name] = adj
    return px


def stock_reaction(d: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    """中证畜牧养殖 relative to the CSI All Share around sales-drop days. The national total is out at about 14:20,
    before the 15:00 close, so 当天 is the close-to-close move of the release day."""
    rel = px["中证畜牧养殖"] / px["中证全指"]
    at = pd.Series(np.arange(len(rel)), index=rel.index)
    reg = d[d["regular"]].dropna(subset=["chg"])
    reg = reg[reg.index.isin(rel.index)]
    sets = [("出栏单日降幅 ≥ 4.5%", reg[reg["chg"] <= DROP]), ("出栏单日降幅 ≥ 3%", reg[reg["chg"] <= -0.03]),
            ("月末最后一个工作日", reg[reg["pos_end"] == 1]), ("全部常规工作日", reg)]
    rows = []
    for name, g in sets:
        i = at[g.index].values
        for k in (0, 1, 5, 10):
            ok = (i >= 1) & (i + k < len(rel))
            a, b = (i[ok] - 1, i[ok]) if k == 0 else (i[ok], i[ok] + k)
            x = pd.Series(rel.values[b] / rel.values[a] - 1)
            rows.append(dict(set=name, window="当天" if k == 0 else f"此后 {k} 个交易日", n=len(x), mean=x.mean(),
                             median=x.median(), share_up=(x > 0).mean()))
    return pd.DataFrame(rows)


def stock_snapshot(px: pd.DataFrame, nat: pd.Series) -> pd.DataFrame:
    """Moves from the June low and the dates of the author's calls to ASOF: stocks, spot and futures side by side."""
    f = pd.read_csv(PROC / "futures_lh_daily.csv", parse_dates=["trade_date"])
    fut = f[f["contract"].isin(["LH2701", "LH2709"])].pivot_table(index="trade_date", columns="contract", values="settle")
    rel = px["中证畜牧养殖"] / px["中证全指"]
    starts = {"2026-06-26": "Issue #5 的检验基准（股价 6 月低点）", "2026-09-29": "作者：明天就是本轮拉升的起点",
              "2026-10-09": "作者：拐点就是现在", "2026-10-19": "统计局三季度数据；作者：已经企稳",
              "2026-10-29": "作者前序帖：估计这几天要开始缩量"}
    rows = []
    for t, label in starts.items():
        t = pd.Timestamp(t)
        r = dict(start=t.date(), event=label)
        r.update({c: px[c].iloc[-1] / px[c].loc[:t].iloc[-1] - 1 for c in px.columns})
        r["畜牧养殖相对中证全指"] = rel.iloc[-1] / rel.loc[:t].iloc[-1] - 1
        r["全国现货（新牧网，到 10-29）"] = nat.iloc[-1] / nat.loc[:t].iloc[-1] - 1
        r.update({c: fut[c].loc[:ASOF].iloc[-1] / fut[c].loc[:t].iloc[-1] - 1 for c in fut.columns})
        rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------
def chart_sales(d: pd.DataFrame, cal: pd.DataFrame, st: pd.DataFrame):
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6), gridspec_kw=dict(width_ratios=[1.6, 1, 1]))
    ax = axes[0]
    a, b = pd.Timestamp("2026-09-01"), pd.Timestamp("2026-11-30")
    cur = d.loc[a:b, "total"] / 1e4
    last = d.loc[a - pd.DateOffset(years=1):b - pd.DateOffset(years=1), "total"] / 1e4
    last.index = last.index + pd.DateOffset(years=1)
    ax.plot(last.index, last.values, "-", color=C["grey"], lw=1.2, label="2025 年同期（日期平移一年）")
    ax.plot(cur.index, cur.values, "-o", color=C["nat"], lw=1.4, ms=2.5, label="2026 年")
    for m in ("2026-09-30", "2026-10-31"):
        ax.axvline(pd.Timestamp(m), color=C["light"], lw=1, ls="--")
    ax.annotate(f"10-30：{d.loc[ASOF, 'total'] / 1e4:.1f} 万头\n{d.loc[ASOF, 'chg']:+.1%}", (ASOF, d.loc[ASOF, "total"] / 1e4),
                xytext=(14, -26), textcoords="offset points", fontsize=8.5, color=C["gd"],
                arrowprops=dict(arrowstyle="-", color=C["gd"], lw=0.6))
    ax.set_ylabel("万头/日")
    ax.set_xlim(a, b)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m月"))
    ax.set_title("钢联重点养殖企业全国日度出栏（虚线为月末）")
    ax.legend(loc="lower left", fontsize=8)
    ax = axes[1]
    x = d.loc[d["regular"], "chg"].dropna() * 100
    ax.hist(x, bins=np.arange(-12, 12.5, 0.75), color=C["light"], edgecolor="white")
    nat = st.set_index("series").loc["全国"]
    ax.axvline(CLAIM["全国"] * 100, color=C["gd"], lw=1.2)
    ax.text(CLAIM["全国"] * 100 - 0.4, ax.get_ylim()[1] * 0.92, f"−4.5%：约 {nat['claim_rank']:.0%} 的\n工作日跌得更多或一样多",
            ha="right", fontsize=8.5, color=C["gd"])
    ax.set_xlabel("较上一工作日变化（%）")
    ax.set_title(f"单日变化分布（{int(nat['n'])} 个工作日，标准差 {nat['sd']:.1%}）")
    ax = axes[2]
    keep = ["月末最后一个工作日", "月末倒数第 2—4 个工作日", "月初第 1 个工作日", "月初第 2—4 个工作日", "长假前最后一个工作日", "周五", "全部常规工作日"]
    c = cal.set_index("group").loc[keep]
    y = np.arange(len(c))[::-1]
    cols = [C["gd"] if v < 0 else C["fut3"] for v in c["mean"]]
    ax.barh(y, c["mean"] * 100, color=cols, height=0.6)
    for yi, (k, r) in zip(y, c.iterrows()):
        ax.text(r["mean"] * 100 + (0.15 if r["mean"] >= 0 else -0.15), yi, f"{r['mean']:+.1%}（{int(r['n'])}）",
                va="center", ha="left" if r["mean"] >= 0 else "right", fontsize=8)
    ax.set_yticks(y)
    ax.set_yticklabels(keep, fontsize=8.5)
    ax.axvline(0, color=C["dark"], lw=0.6)
    ax.set_xlim(-12, 8)
    ax.set_xlabel("平均单日变化（%），括号内为天数")
    ax.set_title("日历效应")
    title(fig, "10-30 的 −4.5%：月末最后一个工作日，单日幅度在常见范围的边缘",
          "钢联样本 2025-03 至 2026-10 的常规工作日（不含长假后首日）；10-30 当日只有全国数，分区数次一工作日公布")
    source(fig, "Mysteel 重点养殖企业日度出栏量（公开页面的摘要与表格首行，C）；本文统计。", y=-0.04)
    fig.tight_layout()
    return save(fig, "i09_sales.png")


def chart_events(ev: pd.DataFrame, es: pd.DataFrame, sy: pd.DataFrame):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6), gridspec_kw=dict(width_ratios=[1.3, 1]))
    ax = axes[0]
    hz = [2, 7, 14, 30]
    base = es[es["set"] == "全部常规工作日"].set_index("horizon_days")
    rng = np.random.default_rng(9)
    for i, h in enumerate(hz):
        allx = ev[f"national_{h}d"].dropna() * 100
        ax.scatter(i + rng.uniform(-0.18, 0.18, len(allx)), allx, s=16, color=C["nat"], alpha=0.65,
                   label="出栏单日降幅 ≥ 3% 之后" if i == 0 else None, zorder=3)
        big = ev.loc[ev["chg"] <= DROP, f"national_{h}d"].dropna() * 100
        ax.scatter(i + rng.uniform(-0.18, 0.18, len(big)), big, s=34, facecolor="none", edgecolor=C["gd"], lw=1.2,
                   label="其中降幅 ≥ 4.5%" if i == 0 else None, zorder=4)
        ax.hlines(base.loc[h, "median"] * 100, i - 0.32, i + 0.32, color=C["spot"], lw=2.2,
                  label="全部工作日的中位数" if i == 0 else None, zorder=5)
        med = es[(es["set"] == "出栏单日降幅 ≥ 3%") & (es["horizon_days"] == h)]["median"].iloc[0] * 100
        ax.hlines(med, i - 0.32, i + 0.32, color=C["nat"], lw=2.2, ls=":", label="降幅 ≥ 3% 之后的中位数" if i == 0 else None, zorder=5)
    ax.axhline(0, color=C["dark"], lw=0.6)
    ax.set_ylim(-25, 25)
    ax.set_xticks(range(len(hz)))
    ax.set_xticklabels([f"{h} 天后" for h in hz])
    ax.set_ylabel("全国均价变化（%）")
    ax.set_title("出栏大幅下降之后，全国猪价怎么走（新牧网日度，2025-03 起）")
    ax.legend(fontsize=8, loc="lower left")
    ax = axes[1]
    x = np.arange(len(sy))
    ax.bar(x - 0.2, sy["chg_14d"] * 100, 0.4, color=C["spot"], label="两周后")
    ax.bar(x + 0.2, sy["chg_91d"] * 100, 0.4, color=C["nat"], label="三个月后")
    ax.axhline(0, color=C["dark"], lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y)[2:] for y in sy["year"]])
    ax.set_xlabel("年份（20xx）")
    ax.set_ylabel("%")
    ax.set_title("季节基准：每年 10 月 30 日之后全国均价的变化")
    ax.legend(fontsize=8)
    title(fig, "单日缩量之后猪价没有系统性上涨；10 月底之后的走势各年差别很大",
          "左：每个点是一个出栏单日降幅 ≥ 3% 的工作日（不含长假后首日）；右：新牧网全国周度均价，2015—2025 年")
    source(fig, "Mysteel 重点养殖企业日度出栏量（C）；新牧网全国生猪均价（日度、周度，C）；本文统计。", y=-0.04)
    fig.tight_layout()
    return save(fig, "i09_events.png")


def chart_calls(d: pd.DataFrame, nat: pd.Series, cl: pd.DataFrame):
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    fig, (ax, bx) = plt.subplots(2, 1, figsize=(14, 7.2), sharex=True, gridspec_kw=dict(height_ratios=[2.2, 1]))
    a = pd.Timestamp("2026-06-01")
    p = nat.loc[a:]
    ax.plot(p.index, p.values, color=C["spot"], lw=1.6)
    for y, lab in ((12.5, "12.5：作者给的规模场成本；“年内高点规模场全盈利”"), (13.0, "13：作者“四季度均价约 13 元”")):
        ax.axhline(y, color=C["grey"], ls="--", lw=0.8)
        ax.text(a + pd.Timedelta(days=2), y + 0.06, lab, fontsize=8, color=C["grey"])
    lab = cl.dropna(subset=["chart_label"])
    for i, (_, r) in enumerate(lab.iterrows()):
        t = pd.Timestamp(r["date"])
        y0 = p.loc[:t].iloc[-1]
        off = (0, 34 + 22 * (i % 3)) if i % 2 == 0 else (0, -40 - 20 * (i % 3))
        ax.annotate(r["chart_label"], (t, y0), xytext=off, textcoords="offset points", ha="center", fontsize=7.8,
                    arrowprops=dict(arrowstyle="-", color=C["dark"], lw=0.5),
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=C["light"], lw=0.6))
        ax.plot(t, y0, "o", color=C["gd"], ms=4)
    ax.set_ylabel("元/公斤")
    ax.set_ylim(8.4, 13.6)
    ax.set_title("全国生猪均价（新牧网日度）与作者的定时判断")
    s = d.loc[a:, "total"] / 1e4
    bx.plot(s.index, s.values, color=C["nat"], lw=1)
    big = d.loc[a:][d.loc[a:, "chg"] <= -0.04]
    bx.scatter(big.index, big["total"] / 1e4, color=C["gd"], s=18, zorder=3, label="单日降幅 ≥ 4%")
    for t, r in big.iterrows():
        bx.text(t, r["total"] / 1e4 - 1.1, f"{t:%m-%d}\n{r['chg']:+.0%}", ha="center", fontsize=7, color=C["gd"])
    bx.set_ylabel("万头/日")
    bx.set_ylim(19, 36)
    bx.legend(loc="upper left", fontsize=8)
    bx.set_title("钢联重点养殖企业全国日度出栏")
    bx.xaxis.set_major_locator(mdates.MonthLocator())
    bx.xaxis.set_major_formatter(mdates.DateFormatter("%-m月"))
    title(fig, "6 月那次判断之后有过一轮 +19% 的反弹；9 月下旬以来的判断之后，价格最多涨 1.9%，到 10-29 都低于判断当天",
          "上图标注作者帖子的日期（帖子编号见 research/daily_signal/calls.csv）；下图红点为出栏单日降幅 ≥ 4% 的工作日")
    source(fig, "雪球 _春风_ 公开帖子；新牧网全国均价（C）；Mysteel 重点养殖企业日度出栏量（C）。", y=-0.02)
    fig.tight_layout()
    return save(fig, "i09_calls.png")


def chart_henan(nat: pd.Series, hn: pd.Series, mh: pd.DataFrame):
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.6), gridspec_kw=dict(width_ratios=[1.5, 1]))
    ax = axes[0]
    a = pd.Timestamp("2026-09-01")
    ax.plot(nat.loc[a:].index, nat.loc[a:].values, color=C["nat"], lw=1.5, label="全国")
    ax.plot(hn.loc[a:].index, hn.loc[a:].values, color=C["spot"], lw=1.5, label="河南")
    up = mh[(mh["word"] == "涨") & (pd.to_datetime(mh["date"]) >= a)]
    for t, priced in zip(pd.to_datetime(up["date"]), up["chg"].notna()):
        ax.axvline(t, color=C["fut3"], lw=0.9, alpha=0.7, ls="-" if priced else ":")
    ax.text(pd.Timestamp("2026-09-03"), 9.0, "绿线：钢联豫皖日报写上涨的日子（虚线为只看标题）", fontsize=8, color=C["fut3"])
    for t, lab, dy in (("2026-10-09", "10-09 作者：河南重要猪企挺价意愿比较明显，拐点就是现在", 34), ("2026-10-29", "10-30 作者：河南猪价居然涨了", 30)):
        t = pd.Timestamp(t)
        y0 = hn.loc[:t].iloc[-1]
        ax.annotate(lab, (t, y0), xytext=(-20, dy), textcoords="offset points", ha="right", fontsize=8,
                    arrowprops=dict(arrowstyle="-", color=C["dark"], lw=0.5),
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=C["light"], lw=0.6))
    ax.set_ylabel("元/公斤")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m月"))
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title("河南与全国均价（新牧网日度，到 10-29）")
    ax = axes[1]
    c = pd.read_csv(ZW_RAW / "henan_cities.csv")
    cc = c[(c["code"] != 410000) & (c["breed"] == "外三元")].sort_values("chg_day")
    y = np.arange(len(cc))
    ax.barh(y, cc["chg_day"], color=[C["fut3"] if v > 0 else C["gd"] for v in cc["chg_day"]], height=0.65)
    ax.set_yticks(y)
    ax.set_yticklabels(cc["area"].str.replace("市", ""), fontsize=8)
    ax.axvline(0, color=C["dark"], lw=0.6)
    prov = c[c["code"] == 410000].set_index("breed")
    txt = "；".join(f"{b} {prov.loc[b, 'chg_day']:+.2f}" for b in ("外三元", "内三元", "土杂猪") if b in prov.index)
    ax.set_title(f"10-30 河南各地市外三元单日变化（元/公斤）\n全省：{txt}", fontsize=10.5)
    title(fig, "“河南涨了”取决于看哪个报价：多数地市外三元在跌，涨的是肥猪品种和个别地市",
          "左：新牧网日度均价；右：中国养猪网 10-30 页面（当晚抓取）")
    source(fig, "新牧网（C）；中国养猪网（C）；Mysteel 豫皖日报公开摘要（C）。", y=-0.04)
    fig.tight_layout()
    return save(fig, "i09_henan.png")


def build():
    d, rev = sales()
    nat, hn, nw = nxin("全国"), nxin("河南省"), nxin_weekly()
    cc = claim_check(d, rev, nat)
    st = change_stats(d)
    cal = calendar(d)
    mt = month_turns(d, nat)
    ev = drop_events(d, nat, hn)
    es = event_study(d, nat, nw, hn)
    sy = seasonal_years(nw)
    ll = lead_lag(d, nat)
    hs = henan_signal(nat, hn)
    snap = henan_snapshot()
    mh = mysteel_henan()
    cl = calls(nat)
    sch, q = supply()
    fc = futures_curve()
    px = stock_prices()
    sr, ss = stock_reaction(d, px), stock_snapshot(px, nat)

    write(cc.round(4), "ds_claim_check.csv")
    write(st.round(4), "ds_daily_changes.csv")
    write(cal.round(4), "ds_calendar.csv")
    write(mt.round(4), "ds_month_turns.csv")
    write(ev.drop(columns=["total"]).round(4), "ds_drop_events.csv")
    write(es.round(4), "ds_event_study.csv")
    write(sy.round(4), "ds_seasonal_years.csv")
    write(ll.round(4), "ds_lead_lag.csv")
    write(hs.round(4), "ds_henan_signal.csv")
    write(snap, "ds_henan_1030.csv")
    write(mh.loc[pd.to_datetime(mh["date"]) >= "2026-09-01"].drop(columns=["url"]), "ds_mysteel_henan.csv")
    write(cl.round(4), "ds_calls.csv")
    write(sch.round(4), "ds_supply_schedule.csv")
    write(q.round(4), "ds_quarterly.csv")
    write(fc, "ds_futures_curve.csv")
    write(sr.round(4), "ds_stock_reaction.csv")
    write(ss.round(4), "ds_stock_snapshot.csv")
    cl_chart = cl.merge(pd.read_csv(RES / "calls.csv", dtype=str)[["id", "chart_label"]], on="id")
    for p in (chart_sales(d, cal, st), chart_events(ev, es, sy), chart_calls(d, nat, cl_chart),
              chart_henan(nat, hn, mh)):
        print("chart", p.name)
    if "-v" in sys.argv:
        pd.set_option("display.width", 250)
        pd.set_option("display.max_columns", 30)
        for df in (cc, st, cal, mt, ev, es, sy, ll, hs, snap, mh, cl, sch, q, fc, sr, ss):
            print(df.round(4).to_string(), "\n")


if __name__ == "__main__":
    if "fetch" in sys.argv[1:]:
        fetch()
    elif "parse" in sys.argv[1:]:
        parse_sales(pd.read_csv(RAW / "_index.csv"))
    else:
        build()
