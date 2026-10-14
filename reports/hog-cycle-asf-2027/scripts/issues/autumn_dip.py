"""Issue #6: was the October 2026 dip the spring restocking reaching market, and when could hog prices
bottom?

  calibers  April 2026 low vs the latest print on every national price series held here, and how far
            each province's latest quote is from its own April low (新牧网 daily quotes);
  october   usual move from the last full week of September to mid-October (新牧网 weekly 2015-2025,
            MOA weekly 2016-2025, NBS ten-day 2025);
  piglets   MOA weekly 集贸 piglet and hog prices (元/公斤): March-May vs August-October and the
            piglet/hog ratio by year; listed companies' monthly piglet sales read from their
            announcements;
  supply    breeding sows (MOA month-end where published, log-linear between quarter-ends otherwise)
            lagged LAG_M months against NBS quarterly slaughter. Slaughter per lagged sow bundles
            productivity, survival and timing; the forward schedule applies a range of its year-on-year
            change to the known sow path and to two scenarios for sows after 2026-06;
  margins   expected margin on a 7 kg piglet bought on date t and sold HOLD_M months later at the
            futures price quoted on t for the sale month (linear between the two nearest contracts),
            under the cost assumptions below; 7 kg prices are third-party quotes.

Inputs (data/processed/): moa_weekly_prices.csv, moa_sows_monthly.csv, nbs_quarterly.csv,
nbs_tenday_hog_2025_2026.csv, sales_ann_text.csv, monthly_sales.csv; local only: nxin_province_daily.csv,
nxin_region_weekly.csv, futures_lh_daily.csv; raw caches: MOA monthly data pages
(data/raw/industry/moa_sows/jdsj) and MOA weekly bulletins (data/raw/industry/moa_weekly/articles);
research/autumn_dip/market_signals.csv (third-party figures quoted by brokers and media, with links).
Outputs: data/processed/issues/ad_*.csv (derived only), charts/i06_*.png.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
OUT = PROC / "issues"
RAW = ROOT / "data" / "raw" / "industry"
SIGNALS = ROOT / "research" / "autumn_dip" / "market_signals.csv"
sys.path.insert(0, str(ROOT / "scripts"))

ASOF = pd.Timestamp("2026-10-14")
LAG_M = 10
# purchased 7 kg piglet fattened to 125 kg (assumptions)
W_IN, W_OUT, FCR, OTHER, HOLD_M = 7.0, 125.0, 2.6, 180.0, 6
# sows after 2026-06 (month-on-month), the slow and fast scenarios
SOW_PATHS = {"缓降": -0.005, "快降": -0.015}
PLACEMENTS = [("2026-03-10", 326.0), ("2026-04-14", 206.0), ("2026-09-15", 144.0)]


def write(df: pd.DataFrame, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / name, index=False, encoding="utf-8")


def flat(path) -> str:
    from bs4 import BeautifulSoup
    return re.sub(r"\s+", " ", BeautifulSoup(open(path, "rb").read(), "html.parser").get_text(" "))


def pct(s: str) -> float:
    s = s.strip().rstrip("%")
    try:
        return float(s) / 100
    except ValueError:
        return np.nan


# ---------------------------------------------------------------------------
# price series
# ---------------------------------------------------------------------------
def nxin_daily(province: str | None = "全国"):
    d = pd.read_csv(PROC / "nxin_province_daily.csv", parse_dates=["date"])
    d = d[d["date"] <= ASOF]
    if province is None:
        return d.pivot_table(index="date", columns="province", values="price").sort_index()
    return d[d["province"] == province].set_index("date")["price"].sort_index()


def nxin_weekly() -> pd.Series:
    w = pd.read_csv(PROC / "nxin_region_weekly.csv")
    w = w[w["region"] == "全国"].dropna(subset=["price"])
    # a value labelled Monday L covers L-7..L-1; dated to that week's Friday
    s = pd.Series(w["price"].values, index=pd.to_datetime(w["week_label"]) - pd.Timedelta(days=3))
    return s[~s.index.duplicated(keep="last")].sort_index()


def moa_weekly() -> pd.DataFrame:
    m = pd.read_csv(PROC / "moa_weekly_prices.csv")
    d = pd.to_datetime(m["collect_date"], errors="coerce")
    iso = pd.to_datetime(m["year"].astype(str) + "-W" + m["week"].astype(int).map("{:02d}".format) + "-3",
                         format="%G-W%V-%u", errors="coerce")
    m["date"] = d.fillna(iso)
    m = m.dropna(subset=["date"]).sort_values("date").drop_duplicates("date")
    return m[m["date"] <= ASOF].set_index("date")


def moa_feed(mw: pd.DataFrame) -> pd.Series:
    """育肥猪配合饲料 (元/公斤) from the cached weekly bulletins, 2025-."""
    adir = RAW / "moa_weekly" / "articles"
    man = pd.read_csv(adir / "_manifest.csv")
    m = mw.loc["2025-01-01":, ["url"]].reset_index().merge(man[["url", "file"]], on="url", how="left")
    out = {}
    for _, r in m.dropna(subset=["file"]).iterrows():
        t = flat(adir / r["file"]).replace(" ", "")
        mm = re.search(r"育肥猪配合饲料平均价格(\d+\.\d+)元", t)
        if mm:
            out[r["date"]] = float(mm.group(1))
    return pd.Series(out, dtype=float).sort_index()


def nbs_tenday() -> pd.Series:
    n = pd.read_csv(PROC / "nbs_tenday_hog_2025_2026.csv").dropna(subset=["price_yuan_kg"])
    day = {"上旬": 5, "中旬": 15, "下旬": 25}
    d = n["period"].map(lambda p: pd.Timestamp(f"{p[:7]}-{day[p[7:]]:02d}"))
    return pd.Series(n["price_yuan_kg"].values, index=d).sort_index()


ROW = re.compile(r"(\d{4})年(\d{1,2}(?:-\d{1,2})?)月份?([^（）\d]{2,40}?)（([^）]{1,12})） "
                 r"([\d.]+) ([-\d.]+%|—|-) ([-\d.]+%|—|-)")
MOA_KEYS = {"生猪定点屠宰企业屠宰量": "slaughter", "仔猪价格": "piglet", "生猪出场价格": "hog_farm",
            "二元母猪销售价格": "gilt", "累计进口猪肉": "import_cum"}


def moa_monthly() -> pd.DataFrame:
    """MOA monthly data pages: designated slaughter, piglet / farm-gate hog / gilt prices, pork imports."""
    rows = {}
    for f in sorted((RAW / "moa_sows" / "jdsj").glob("jdsj_*.html")):
        for y, mo, lab, _unit, v, _mom, yoy in ROW.findall(flat(f)):
            key = next((k2 for k, k2 in MOA_KEYS.items() if k in lab), None)
            if key is None or ("-" in mo) != (key == "import_cum"):
                continue
            mon = f"{y}-{int(mo.split('-')[-1]):02d}"
            r = rows.setdefault(mon, {"month": mon})
            r[key], r[key + "_yoy"] = float(v), pct(yoy)
            if key == "slaughter":
                r["slaughter_scope"] = "规模以上" if lab.startswith("规模以上") else "全部定点"
    return pd.DataFrame(sorted(rows.values(), key=lambda r: r["month"]))


# ---------------------------------------------------------------------------
# 1. calibers: April low vs latest
# ---------------------------------------------------------------------------
def calibers(nd, nw, mw, mm, nt):
    hog_m = pd.Series(mm["hog_farm"].values, index=pd.to_datetime(mm["month"] + "-15")).dropna()
    series = [("新牧网 全国日度报价", "C", nd), ("新牧网 全国周度成交均价", "C", nw),
              ("农业农村部 500 县集贸市场（周）", "A", mw["live_hog"].dropna()),
              ("农业农村部 生猪出场价（月均）", "A", hog_m), ("国家统计局 外三元（旬）", "A", nt)]
    rows = []
    for name, grade, s in series:
        a = s.loc["2026-04-01":"2026-04-30"]
        rows.append(dict(series=name, grade=grade, april_low=a.min(), april_low_date=a.idxmin().date(),
                         latest=s.iloc[-1], latest_date=s.index[-1].date(),
                         latest_vs_april_low=s.iloc[-1] / a.min() - 1,
                         sep_high=s.loc["2026-08-15":"2026-09-30"].max(),
                         latest_vs_sep_high=s.iloc[-1] / s.loc["2026-08-15":"2026-09-30"].max() - 1))
    return pd.DataFrame(rows)


def province_distance(P: pd.DataFrame) -> pd.DataFrame:
    low = P.loc["2026-04-01":"2026-04-30"].min()
    last = P.iloc[-3:].mean()
    r = (last / low - 1).drop("全国", errors="ignore").dropna().sort_values()
    return r.rename("latest3_vs_april_low").rename_axis("province").reset_index()


# ---------------------------------------------------------------------------
# 2. the usual late-September -> mid-October move
# ---------------------------------------------------------------------------
def _win(s, y, a, b):
    return s[(s.index >= pd.Timestamp(f"{y}-{a}")) & (s.index <= pd.Timestamp(f"{y}-{b}"))]


def october_moves(nw, mw, nt, nd) -> pd.DataFrame:
    rows = []
    for src, s, years in (("新牧网周度", nw, range(2015, 2026)), ("农业农村部集贸周度", mw["live_hog"].dropna(),
                                                                  range(2016, 2027))):
        for y in years:
            base, mid, octw = _win(s, y, "09-22", "09-28"), _win(s, y, "10-13", "10-19"), _win(s, y, "10-06", "11-02")
            if base.empty or octw.empty:
                continue
            b = base.mean()
            rows.append(dict(source=src, year=y, base=b, mid_oct_chg=mid.mean() / b - 1 if len(mid) else np.nan,
                             oct_min_chg=octw.min() / b - 1, oct_min_date=octw.idxmin().date(),
                             latest_chg=octw.iloc[-1] / b - 1, latest_date=octw.index[-1].date()))
    b26 = _win(nd, 2026, "09-21", "09-27").mean()
    last = nd.iloc[-3:]
    rows.append(dict(source="新牧网日度", year=2026, base=b26, mid_oct_chg=last.mean() / b26 - 1,
                     oct_min_chg=nd.loc["2026-10-06":].min() / b26 - 1, oct_min_date=nd.loc["2026-10-06":].idxmin().date(),
                     latest_chg=nd.iloc[-1] / b26 - 1, latest_date=nd.index[-1].date()))
    for y in (2025, 2026):
        base, mid = nt.get(pd.Timestamp(f"{y}-09-25")), nt.get(pd.Timestamp(f"{y}-10-15"))
        if base is None:
            continue
        rows.append(dict(source="国家统计局旬度", year=y, base=base,
                         mid_oct_chg=mid / base - 1 if mid is not None else np.nan))
    out = pd.DataFrame(rows)
    out.loc[out.source.str.startswith("新牧网"), "base"] = np.nan  # third-party levels stay local
    return out


# ---------------------------------------------------------------------------
# 3. piglets
# ---------------------------------------------------------------------------
def piglet_monthly(mw) -> pd.DataFrame:
    m = mw[["piglet", "live_hog"]].dropna().copy()
    g = m.groupby([m.index.year.rename("year"), m.index.month.rename("month")]).agg(
        piglet=("piglet", "mean"), live_hog=("live_hog", "mean"), weeks=("piglet", "size")).reset_index()
    g["ratio"] = g["piglet"] / g["live_hog"]
    return g


def piglet_seasons(pm: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for y, g in pm.groupby("year"):
        g = g.set_index("month")
        sp, au = g.loc[g.index.isin([3, 4, 5])], g.loc[g.index.isin([8, 9, 10])]
        if len(sp) < 3 or len(au) < 2 or 4 not in g.index or 9 not in g.index:
            continue
        rows.append(dict(year=y, piglet_spring=sp["piglet"].mean(), piglet_autumn=au["piglet"].mean(),
                         hog_spring=sp["live_hog"].mean(), hog_autumn=au["live_hog"].mean(),
                         ratio_spring=sp["ratio"].mean(), ratio_autumn=au["ratio"].mean(),
                         piglet_apr=g.loc[4, "piglet"], piglet_sep=g.loc[9, "piglet"],
                         ratio_apr=g.loc[4, "ratio"], ratio_sep=g.loc[9, "ratio"], autumn_months=len(au)))
    d = pd.DataFrame(rows)
    d["piglet_spring_vs_autumn"] = d["piglet_spring"] / d["piglet_autumn"] - 1
    d["hog_spring_vs_autumn"] = d["hog_spring"] / d["hog_autumn"] - 1
    d["ratio_spring_vs_autumn"] = d["ratio_spring"] / d["ratio_autumn"] - 1
    d["piglet_apr_vs_sep"] = d["piglet_apr"] / d["piglet_sep"] - 1
    d["ratio_apr_vs_sep"] = d["ratio_apr"] / d["ratio_sep"] - 1
    return d


CUM = re.compile(r"累计|\d{1,2}\s*[-—~至]\s*\d{1,2}\s*月")
PIG = re.compile(r"(?:销售)?仔猪(?:销售|销量)?\s*(?:为)?\s*([\d,]+(?:\.\d+)?)\s*(万\s*头|头)")


def company_piglets() -> pd.DataFrame:
    """First non-cumulative piglet count in each monthly sales announcement (万头)."""
    t = pd.read_csv(PROC / "sales_ann_text.csv", dtype={"code": str})
    t["text"] = t["text"].fillna("").astype(str)
    ms = pd.read_csv(PROC / "monthly_sales.csv", dtype={"code": str})
    ms = ms[ms["months_covered"] == 1].drop_duplicates(["code", "month_key"]).set_index(["code", "month_key"])
    rows = []
    for _, r in t[t["year"] >= 2024].iterrows():
        month = f"{int(r['year'])}-{int(r['month']):02d}"
        if (r["code"], month) not in ms.index:
            continue
        s = re.sub(r"\s+", " ", r["text"])
        for m in PIG.finditer(s):
            if CUM.search(s[max(0, m.start() - 40):m.start()]):
                continue
            v = float(m.group(1).replace(",", ""))
            v = v if "万" in m.group(2) else v / 1e4
            total = ms.loc[(r["code"], month), "total_heads"]
            if pd.notna(total) and v > total:
                break
            rows.append(dict(code=r["code"], name=r["sec_name"].replace(" ", ""), month=month, piglet_wan=v,
                             total_wan=total, url=r["url"]))
            break
    return pd.DataFrame(rows).drop_duplicates(["code", "month"]).sort_values(["code", "month"])


def piglet_panel(cp: pd.DataFrame) -> pd.DataFrame:
    """Companies that report piglets in the same month of both 2025 and 2026."""
    w = cp.pivot_table(index="month", columns="code", values="piglet_wan")
    name = cp.sort_values("month").groupby("code")["name"].last().str.replace(r"^\*?ST", "", regex=True)
    rows = []
    for m in [f"2026-{i:02d}" for i in range(3, 10)]:
        p = m.replace("2026", "2025")
        if m not in w.index or p not in w.index:
            continue
        both = w.loc[[m, p]].dropna(axis=1)
        rows.append(dict(month=m, n_companies=both.shape[1], companies="、".join(name[both.columns]),
                         piglets_2026=both.loc[m].sum(), piglets_2025=both.loc[p].sum(),
                         yoy=both.loc[m].sum() / both.loc[p].sum() - 1))
    return pd.DataFrame(rows)


def listed_sales() -> pd.DataFrame:
    """Monthly hog sales of listed companies that report the same month in both years."""
    ms = pd.read_csv(PROC / "monthly_sales.csv", dtype={"code": str})
    ms = ms[ms["months_covered"] == 1].drop_duplicates(["code", "month_key"])
    w = ms.pivot_table(index="month_key", columns="code", values="total_heads")
    rows = []
    # January and February are often reported together, so single-month samples miss the largest firms
    for m in [f"2026-{i:02d}" for i in range(3, 10)]:
        p = m.replace("2026", "2025")
        if m not in w.index or p not in w.index:
            continue
        both = w.loc[[m, p]].dropna(axis=1)
        rows.append(dict(month=m, n_companies=both.shape[1], heads_2026=both.loc[m].sum(),
                         heads_2025=both.loc[p].sum(), yoy=both.loc[m].sum() / both.loc[p].sum() - 1))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. supply: sows lagged against slaughter
# ---------------------------------------------------------------------------
def sows_monthly() -> tuple[pd.Series, pd.Index]:
    s = pd.read_csv(PROC / "moa_sows_monthly.csv")
    s = s[s["scope"].astype(str).str.startswith("全国绝对量")].dropna(subset=["sow_wan"])
    known = pd.Series(s["sow_wan"].values, index=pd.PeriodIndex(s["month"], freq="M")).sort_index()
    known = known[~known.index.duplicated()]
    idx = pd.period_range(known.index.min(), known.index.max(), freq="M")
    return np.exp(np.log(known.reindex(idx)).interpolate()), known.index


def extend_sows(sows: pd.Series, mom: float, to="2026-11") -> pd.Series:
    idx = pd.period_range(sows.index.max() + 1, to, freq="M")
    ext = pd.Series(sows.iloc[-1] * (1 + mom) ** np.arange(1, len(idx) + 1), index=idx)
    return pd.concat([sows, ext])


def lagged(sows: pd.Series, q: pd.Period) -> float:
    months = [pd.Period(q.start_time, "M") + i - LAG_M for i in range(3)]
    return float(sows.reindex(months).mean()) if all(m in sows.index for m in months) else np.nan


def per_sow(sows: pd.Series) -> pd.DataFrame:
    q = pd.read_csv(PROC / "nbs_quarterly.csv").dropna(subset=["hog_slaughter_q_wan"])
    d = pd.DataFrame({"slaughter": q["hog_slaughter_q_wan"].values, "pork": q["pork_output_q_wan_t"].values,
                      "carcass": q["carcass_wt_kg_est"].values}, index=pd.PeriodIndex(q["period"], freq="Q"))
    d["sows_lag"] = [lagged(sows, p) for p in d.index]
    d["per_sow"] = d["slaughter"] / d["sows_lag"]
    for c in ("slaughter", "pork", "carcass", "sows_lag", "per_sow"):
        d[c + "_yoy"] = d[c] / d[c].shift(4) - 1
    return d.dropna(subset=["sows_lag"])


def schedule(sows: pd.Series, ps: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    g = ps["per_sow_yoy"].dropna().iloc[-4:]
    rng = dict(low=float(g.min()), base=float(g.median()), high=float(g.max()))
    rows = []
    for path, mom in SOW_PATHS.items():
        sw = extend_sows(sows, mom)
        for q in pd.period_range("2026Q3", "2027Q3", freq="Q"):
            cur, prev = lagged(sw, q), lagged(sw, q - 4)
            months = [pd.Period(q.start_time, "M") + i - LAG_M for i in range(3)]
            r = dict(quarter=str(q), sow_path=path, sows_lag=cur, sows_lag_yoy=cur / prev - 1,
                     sow_months=f"{months[0]}~{months[-1]}",
                     uses_scenario=bool(max(months) > sows.index.max()))
            for k, gk in rng.items():
                r[f"slaughter_yoy_{k}"] = (1 + r["sows_lag_yoy"]) * (1 + gk) - 1
            rows.append(r)
    return pd.DataFrame(rows), rng


# ---------------------------------------------------------------------------
# 5. margins on a purchased piglet
# ---------------------------------------------------------------------------
def futures() -> pd.DataFrame:
    f = pd.read_csv(PROC / "futures_lh_daily.csv", parse_dates=["trade_date"])
    f = f[f["contract"].str.fullmatch(r"LH\d{4}") & (f["trade_date"] <= ASOF)].copy()
    f["dm"] = f["contract"].str[2:].map(lambda x: pd.Period(f"20{x[:2]}-{x[2:]}", "M"))
    return f


def curve(f: pd.DataFrame, d) -> tuple[pd.Series, pd.Timestamp]:
    td = f.loc[f["trade_date"] <= pd.Timestamp(d), "trade_date"].max()
    c = f[f["trade_date"] == td]
    return c.set_index("dm")["settle_kg"].sort_index(), td


def price_at(c: pd.Series, m: pd.Period) -> float:
    if m in c.index:
        return float(c[m])
    lo, hi = c[c.index < m], c[c.index > m]
    if lo.empty or hi.empty:
        return np.nan
    a, b = lo.index[-1], hi.index[0]
    w = (m - a).n / (b - a).n
    return float(lo.iloc[-1] * (1 - w) + hi.iloc[0] * w)


def margins(f, feed, nt) -> pd.DataFrame:
    rows = []
    for d, piglet in PLACEMENTS + [("2026-10-13", 144.0)]:
        d = pd.Timestamp(d)
        c, td = curve(f, d)
        fp = float(feed[feed.index <= d].iloc[-1])
        sale = pd.Period(d, "M") + HOLD_M
        fut = price_at(c, sale)
        cost = piglet + FCR * (W_OUT - W_IN) * fp + OTHER
        be = cost / W_OUT
        spot = nt[(nt.index.to_period("M") == sale)]
        if spot.empty and sale == pd.Period(ASOF, "M"):
            spot = nt.iloc[-1:]
        rows.append(dict(placed=d.date(), piglet_7kg=piglet, feed=fp, futures_date=td.date(), sale_month=str(sale),
                         futures_sale=fut, breakeven=be, exp_margin_head=(fut - be) * W_OUT,
                         spot_sale=spot.mean() if len(spot) else np.nan,
                         spot_basis=", ".join(f"{x:%m-%d}" for x in spot.index),
                         realised_margin_head=(spot.mean() - be) * W_OUT if len(spot) else np.nan,
                         sens_fcr_0p2=0.2 * (W_OUT - W_IN) * fp))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# facts and charts
# ---------------------------------------------------------------------------
def signals() -> pd.DataFrame:
    s = pd.read_csv(SIGNALS)
    s["d"] = pd.to_datetime(s["date"].str.slice(0, 10), errors="coerce")
    return s


def chart_calibers(nd, mw, mm, nt, cal, pdist):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.4), gridspec_kw=dict(width_ratios=[1.9, 1]))
    ax = axes[0]
    a, b = "2026-01-01", ASOF
    hog_m = pd.Series(mm["hog_farm"].values, index=pd.to_datetime(mm["month"] + "-15")).dropna()
    lines = [("新牧网 全国日度（C）", nd.loc[a:b], C["spot"], "-", None),
             ("农业农村部 集贸周度（A）", mw["live_hog"].loc[a:b], C["nat"], "-", "o"),
             ("国家统计局 外三元旬度（A）", nt.loc[a:b], C["fut1"], "--", "s"),
             ("农业农村部 出场价月均（A）", hog_m.loc[a:b], C["fut3"], ":", "D")]
    for lab, s, col, ls, mk in lines:
        ax.plot(s.index, s.values, ls, color=col, lw=1.6 if mk is None else 1.2, marker=mk, ms=3.5, label=lab)
        lo = s.loc["2026-04-01":"2026-04-30"]
        ax.axhline(lo.min(), color=col, lw=0.8, ls=(0, (2, 3)), alpha=0.8)
    for _, r in cal.iterrows():
        if r["series"].startswith("新牧网 全国日度"):
            ax.annotate(f"4-14 低点 {r['april_low']:.2f}", (pd.Timestamp(r["april_low_date"]), r["april_low"]),
                        xytext=(-92, -4), textcoords="offset points", fontsize=8.5, color=C["spot"])
            ax.annotate(f"{r['latest_date']:%m-%d} {r['latest']:.2f}\n高于 4 月低点 {r['latest_vs_april_low']:.0%}",
                        (pd.Timestamp(r["latest_date"]), r["latest"]), xytext=(-110, -34), textcoords="offset points",
                        fontsize=8.5, color=C["spot"], arrowprops=dict(arrowstyle="-", color=C["spot"], lw=0.6))
    ax.axvspan(pd.Timestamp("2026-10-01"), ASOF, color=C["light"], alpha=0.5, lw=0)
    ax.set_ylim(8.4, None)
    ax.set_ylabel("元/公斤")
    ax.set_title("2026 年各口径生猪价格；虚线为各自 4 月最低值")
    ax.legend(loc="upper right", fontsize=8)
    ax = axes[1]
    c = cal.iloc[::-1]
    ax.barh(range(len(c)), c["latest_vs_april_low"], color=[C["nat"] if g == "A" else C["spot"] for g in c["grade"]])
    for i, (_, r) in enumerate(c.iterrows()):
        ax.text(r["latest_vs_april_low"] + 0.003, i, f"{r['latest_vs_april_low']:+.1%}（{r['latest_date']:%m-%d}）",
                va="center", fontsize=8.5)
    ax.set_yticks(range(len(c)))
    ax.set_yticklabels([s.replace(" ", "\n", 1) for s in c["series"]], fontsize=8)
    d = pdist["latest3_vs_april_low"]
    above = "全部高于" if (d > 0).all() else f"{int((d > 0).sum())} 个高于"
    ax.set_title(f"最新值高于 4 月低点的幅度\n省份：{len(d)} 个{above}各自 4 月低点，"
                 f"最小 {d.min():+.1%}，中位数 {d.median():+.0%}", fontsize=10.5)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_xlim(0, max(0.25, c["latest_vs_april_low"].max() + 0.08))
    lo_hi = cal["latest_vs_april_low"].agg(["min", "max"])
    title(fig, f"10 月没有跌破 4 月低点：各全国口径都还高 {lo_hi['min']:.0%}—{lo_hi['max']:.0%}",
          "同一口径前后比较；新牧网为第三方行情，日度最新值与周度、旬度、月度的时点不同")
    source(fig, "新牧网日度/周度报价（C）；农业农村部 500 个县集贸市场周报、月度数据页；国家统计局流通领域生产资料旬度价格。"
                "省份为新牧网省级报价最近 3 日均值相对各自 4 月日度最低值。", y=-0.04)
    fig.tight_layout()
    return save(fig, "i06_calibers.png")


def chart_piglets(pm, mw, cp_panel, sig):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2))
    ax = axes[0]
    hist = pm[(pm["year"] >= 2016) & (pm["year"] <= 2025)]
    q = hist.groupby("month")["ratio"].quantile([0.25, 0.5, 0.75]).unstack()
    ax.fill_between(q.index, q[0.25], q[0.75], color=C["light"], alpha=0.8, label="2016—2025 四分位区间")
    ax.plot(q.index, q[0.5], color=C["grey"], lw=1.6, label="2016—2025 中位数")
    for y, col in ((2025, C["fut1"]), (2026, C["gd"])):
        g = pm[pm["year"] == y]
        ax.plot(g["month"], g["ratio"], "-o", color=col, ms=3.5, lw=1.6, label=str(y))
    ax.set_xticks(range(1, 13))
    ax.set_xlabel("月")
    ax.set_title("仔猪价 ÷ 生猪价（同为元/公斤）")
    ax.legend(fontsize=8)
    ax = axes[1]
    s = mw.loc["2026-01-01":, ["piglet", "live_hog"]]
    ax.plot(s.index, s["piglet"], "-o", ms=2.5, color=C["gd"], label="仔猪（元/公斤）")
    ax.plot(s.index, s["live_hog"], "-o", ms=2.5, color=C["nat"], label="生猪（元/公斤）")
    for a, b in (("2026-03-01", "2026-05-31"), ("2026-08-01", "2026-10-31")):
        ax.axvspan(pd.Timestamp(a), min(pd.Timestamp(b), ASOF), color=C["light"], alpha=0.45, lw=0)
    ax2 = ax.twinx()
    p7 = sig[sig["metric"].str.startswith("7kg仔猪价格（规模场）")]
    ax2.plot(p7["d"], p7["value"].astype(float), "D", color=C["small"], ms=6, label="7kg 仔猪（元/头，右轴，C）")
    for _, r in p7.iterrows():
        ax2.annotate(f"{float(r['value']):.0f}", (r["d"], float(r["value"])), xytext=(5, 4), textcoords="offset points",
                     fontsize=8, color=C["spot2"])
    ax2.set_ylim(0, 420)
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8)
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m月"))
    ax.set_title("2026 年农业农村部集贸周度价格；阴影为 3—5 月、8—10 月")
    ax = axes[2]
    x = np.arange(len(cp_panel))
    ax.bar(x - 0.2, cp_panel["piglets_2025"], 0.4, color=C["grey"], label="2025 年同月")
    ax.bar(x + 0.2, cp_panel["piglets_2026"], 0.4, color=C["small"], label="2026 年")
    for i, r in cp_panel.iterrows():
        ax.text(i + 0.2, r["piglets_2026"] + 0.5, f"{r['yoy']:+.0%}", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([m[5:] + "月" for m in cp_panel["month"]])
    ax.set_ylabel("万头")
    ax.set_title("上市公司仔猪外销（两年同月都披露的公司）")
    ax.legend(fontsize=8, loc="upper left")
    title(fig, "春季仔猪比秋季贵是季节常态，2026 年春季的比价并不高",
          "左：仔猪/生猪比价每年春高秋低，2026 年春季低于往年中位数，6 月以后低于往年区间；中：2026 年集贸价格；"
          "右：能逐月核对的中型公司外销仔猪同比翻倍")
    source(fig, "农业农村部 500 个县集贸市场周报（A）；7kg 仔猪为涌益咨询报价，经券商报告转述（C）；"
                "仔猪外销为各公司月度销售公告（A），只统计 2025、2026 年同月均单列仔猪的公司，牧原、温氏 2026 年未单列。", y=-0.04)
    fig.tight_layout()
    return save(fig, "i06_piglets.png")


def chart_timeline():
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    rows = [("外购仔猪育肥（3—5 月补 7kg 仔猪）", [("2026-03-01", "2026-05-31", "补栏")], ("2026-08-15", "2026-11-30")),
            ("外购仔猪育肥（6—8 月补栏）", [("2026-06-01", "2026-08-31", "补栏")], ("2026-11-15", "2027-02-28")),
            ("二次育肥（4 月中下旬入场）", [("2026-04-10", "2026-04-30", "入场")], ("2026-05-25", "2026-07-15")),
            ("二次育肥（7—8 月入场）", [("2026-07-01", "2026-08-31", "入场")], ("2026-08-25", "2026-10-31")),
            ("自繁自养扩产（3—5 月配种）", [("2026-03-01", "2026-05-31", "配种"), ("2026-06-25", "2026-09-25", "产仔")],
             ("2026-12-20", "2027-03-31")),
            ("集团 9 月未完成计划", [("2026-09-01", "2026-09-30", "积压")], ("2026-10-01", "2026-10-31"))]
    fig, ax = plt.subplots(figsize=(14, 5.2))
    for i, (lab, pre, sale) in enumerate(rows[::-1]):
        for a, b, t in pre:
            ax.barh(i, pd.Timestamp(b) - pd.Timestamp(a), left=pd.Timestamp(a), color=C["light"], height=0.5)
            ax.text(pd.Timestamp(a) + (pd.Timestamp(b) - pd.Timestamp(a)) / 2, i, t, ha="center", va="center", fontsize=8)
        ax.barh(i, pd.Timestamp(sale[1]) - pd.Timestamp(sale[0]), left=pd.Timestamp(sale[0]), color=C["spot"], height=0.5,
                alpha=0.85)
        ax.text(pd.Timestamp(sale[0]) + (pd.Timestamp(sale[1]) - pd.Timestamp(sale[0])) / 2, i, "出栏", ha="center",
                va="center", fontsize=8, color="white")
    ax.axvspan(pd.Timestamp("2026-10-01"), pd.Timestamp("2026-10-31"), color=C["gd"], alpha=0.12, lw=0)
    ax.text(pd.Timestamp("2026-10-16"), len(rows) - 0.35, "2026 年 10 月", ha="center", fontsize=9, color=C["gd"])
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows[::-1]], fontsize=9)
    ax.set_xlim(pd.Timestamp("2026-02-15"), pd.Timestamp("2027-04-15"))
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y-%m"))
    ax.grid(axis="y", visible=False)
    title(fig, "春季补栏的三条路径里只有外购仔猪育肥落在 10 月；夏季二育和 9 月积压也在 10 月出栏",
          "示意图：7kg→125kg 约 165—180 天；二育 1.5—2.5 个月；配种→产仔 114 天，产仔→出栏约 180 天")
    source(fig, "本文按常用生产参数推算（推断）；二育入场时点据涌益、东兴证券描述（C）；集团积压据 Mysteel 9 月完成率与 10 月计划（C）。",
           y=-0.06)
    fig.tight_layout()
    return save(fig, "i06_timeline.png")


def chart_supply(ps, sch, rng, f, nt):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.4), gridspec_kw=dict(width_ratios=[1.45, 1]))
    ax = axes[0]
    h = ps.loc[pd.Period("2024Q1", "Q"):]
    xs = [str(p) for p in h.index]
    fut = sch[sch["sow_path"] == "缓降"]
    fut_f = sch[sch["sow_path"] == "快降"]
    allx = xs + list(fut["quarter"])
    pos = {q: i for i, q in enumerate(allx)}
    ax.bar([pos[q] for q in xs], h["slaughter_yoy"], color=C["light"], label="统计局出栏同比（实际）")
    ax.plot([pos[q] for q in xs], h["sows_lag_yoy"], "-o", ms=3.5, color=C["nat"], label=f"能繁母猪（滞后 {LAG_M} 个月）同比")
    ax.plot([pos[q] for q in xs], h["per_sow_yoy"], "-s", ms=3.5, color=C["small"], label="每头滞后母猪对应出栏同比")
    fx = [pos[q] for q in fut["quarter"]]
    ax.plot(fx, fut["sows_lag_yoy"], "--o", ms=3.5, color=C["nat"], mfc="white")
    ax.fill_between(fx, np.minimum(fut["slaughter_yoy_low"], fut_f["slaughter_yoy_low"].values),
                    np.maximum(fut["slaughter_yoy_high"], fut_f["slaughter_yoy_high"].values),
                    color=C["spot"], alpha=0.25, lw=0, label="出栏同比推算区间")
    ax.plot(fx, fut["slaughter_yoy_base"], "o", color=C["spot2"], ms=5, label="推算基准（母猪缓降）")
    ax.axhline(0, color=C["dark"], lw=0.8)
    ax.axvline(len(xs) - 0.5, color=C["grey"], lw=0.8, ls=":")
    ax.set_xticks(range(len(allx)))
    ax.set_xticklabels([q.replace("Q", "\nQ") for q in allx], fontsize=8)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.0%}"))
    ax.set_title(f"出栏同比 = 滞后母猪同比 × 每头产出同比；产出同比取近 4 季的最小、中位、最大值 "
                 f"{rng['low']:+.1%}、{rng['base']:+.1%}、{rng['high']:+.1%}", fontsize=10.5)
    ax.legend(fontsize=7.5, loc="lower left")
    ax = axes[1]
    for d, col in (("2026-04-14", C["grey"]), ("2026-09-15", C["fut1"]), ("2026-10-13", C["gd"])):
        c, td = curve(f, d)
        c = c[c.index >= pd.Period(td, "M")]
        ax.plot(c.index.to_timestamp() + pd.Timedelta(days=14), c.values, "-o", ms=4, color=col, label=f"{td:%m-%d} 期货曲线")
    sp = nt.loc["2026-01-01":]
    ax.plot(sp.index, sp.values, "-", color=C["dark"], lw=1.2, label="统计局外三元旬度（现货）")
    ax.set_ylabel("元/公斤")
    ax.set_title("期货曲线：2027 年 3 月仍贴近 10.5 元，5 月以后才明显抬升")
    ax.legend(fontsize=8, loc="upper left")
    import matplotlib.dates as mdates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y-%m"))
    title(fig, "供给时间表：2026 年四季度同比大致持平，2027 年二季度起才明显收缩",
          "左图为本文推算，未包含需求和冻品；右图为大商所生猪期货各合约结算价（交割标准品）")
    source(fig, "农业农村部能繁母猪存栏（月末/季末，A）；国家统计局季度出栏（A）；2026-06 以后母猪按每月 −0.5%（缓降）与 −1.5%（快降）"
                "两种情景；大商所期货结算价（新浪财经，C）。", y=-0.05)
    fig.tight_layout()
    return save(fig, "i06_supply.png")


def chart_signals(sig):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    import matplotlib.dates as mdates
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.4))
    ax = axes[0]
    s = sig[sig["metric"] == "冻品库容率"].sort_values("d")
    ax.plot(s["d"], s["value"].astype(float), "-o", color=C["nat"])
    for _, r in s.iterrows():
        yoy = r["change"] if isinstance(r["change"], str) and r["change"].startswith("同比") else ""
        ax.annotate(f"{float(r['value']):.1f}% {yoy}", (r["d"], float(r["value"])), xytext=(6, -12),
                    textcoords="offset points", fontsize=7.5)
    ax.set_ylim(10, 36)
    ax.set_title("冻品库容率（%）")
    ax = axes[1]
    w = sig[sig["metric"] == "出栏均重（全国/集团/散户）"].sort_values("d")
    labs = [f"{d:%m-%d}" for d in w["d"]]
    vals = np.array([[float(x) for x in v.split("/")] for v in w["value"]])
    x = np.arange(len(w))
    ax.bar(x - 0.2, vals[:, 1], 0.4, color=C["muyuan"], label="集团")
    ax.bar(x + 0.2, vals[:, 2], 0.4, color=C["small"], label="散户")
    for i in x:
        ax.text(i - 0.2, vals[i, 1] + 0.6, f"{vals[i, 1]:.1f}", ha="center", fontsize=8)
        ax.text(i + 0.2, vals[i, 2] + 0.6, f"{vals[i, 2]:.1f}", ha="center", fontsize=8)
    ax.text(1, 152, "8-20 同比：集团 +0.81kg，散户 +5.14kg", ha="center", fontsize=8)
    ax.set_ylim(110, 156)
    ax.set_xticks(x)
    ax.set_xticklabels(labs)
    ax.grid(axis="x", visible=False)
    ax.set_title("出栏均重（公斤）")
    ax.legend(fontsize=8, loc="upper left")
    ax = axes[2]
    s = sig[sig["metric"] == "二育栏舍利用率"].sort_values("d")
    ax.plot(s["d"], s["value"].astype(float), "-o", color=C["fut3"])
    for _, r in s.iterrows():
        ax.annotate(f"{float(r['value']):.1f}%", (r["d"], float(r["value"])), xytext=(4, 4), textcoords="offset points",
                    fontsize=8)
    ax.set_ylim(30, 48)
    ax.set_title("二育栏舍利用率（%）")
    ax = axes[3]
    b = sig[sig["metric"].isin(["新生仔猪数（定点样本）", "仔猪销量（定点样本）"])].copy()
    for m, col in (("新生仔猪数（定点样本）", C["nat"]), ("仔猪销量（定点样本）", C["gd"])):
        s = b[b["metric"] == m].sort_values("d")
        v = s["value"].astype(float).values
        ax.plot(["6 月", "9 月"], v / v[0] * 100, "-o", color=col, label=f"{m[:-6]} {v[-1] / v[0] - 1:+.1%}")
    ax.set_ylim(90, 102)
    ax.set_title("Mysteel 定点样本（6 月 = 100）")
    ax.legend(fontsize=8, loc="lower left")
    for ax in (axes[0], axes[2]):
        ax.set_xlim(pd.Timestamp("2026-03-01"), pd.Timestamp("2026-10-15"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[3, 5, 7, 9]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m月"))
    title(fig, "四个现场信号：冻品高库存、散户压栏、二育出多入少、仔猪外销比出生量降得快",
          "均为第三方样本数据（C 级），口径与样本各家不同，只看方向和量级")
    source(fig, "Mysteel、涌益咨询，经开源证券、长江期货、大有期货与媒体转述；逐条出处见 research/autumn_dip/market_signals.csv。", y=-0.06)
    fig.tight_layout()
    return save(fig, "i06_signals.png")


if __name__ == "__main__":
    nd, nw, mw, nt = nxin_daily(), nxin_weekly(), moa_weekly(), nbs_tenday()
    mm = moa_monthly()
    feed = moa_feed(mw)
    cal = calibers(nd, nw, mw, mm, nt)
    pdist = province_distance(nxin_daily(None))
    om = october_moves(nw, mw, nt, nd)
    pm = piglet_monthly(mw)
    pseas = piglet_seasons(pm)
    cp = company_piglets()
    panel = piglet_panel(cp)
    sows, known = sows_monthly()
    ps = per_sow(sows)
    sch, rng = schedule(sows, ps)
    f = futures()
    mg = margins(f, feed, nt)
    ls = listed_sales()
    sig = signals()

    write(cal, "ad_calibers.csv")
    write(pdist.round(4), "ad_province_vs_april.csv")
    write(om.round(4), "ad_october_moves.csv")
    write(pm.round(3), "ad_moa_piglet_monthly.csv")
    write(pseas.round(4), "ad_piglet_seasons.csv")
    write(cp, "ad_company_piglets.csv")
    write(panel.round(4), "ad_company_piglet_panel.csv")
    write(mm.round(4), "ad_moa_monthly.csv")
    write(feed.rename("feed_yuan_kg").rename_axis("date").reset_index(), "ad_moa_feed.csv")
    pso = ps.copy()
    pso.index = pso.index.astype(str)
    write(pso.rename_axis("quarter").reset_index().round(4), "ad_per_sow.csv")
    write(sch.round(4), "ad_supply_schedule.csv")
    write(mg.round(3), "ad_placement_margins.csv")
    write(ls.round(4), "ad_listed_sales.csv")
    for p in (chart_calibers(nd, mw, mm, nt, cal, pdist), chart_piglets(pm, mw, panel, sig), chart_timeline(),
              chart_supply(ps, sch, rng, f, nt), chart_signals(sig)):
        print("chart", p.name)
    if "-v" in sys.argv:
        pd.set_option("display.width", 250)
        pd.set_option("display.max_columns", 30)
        print(cal.round(3).to_string())
        print(pdist.describe().round(3).to_string())
        print(om.round(3).to_string())
        print(pseas.round(3).to_string())
        print(panel.round(3).to_string())
        print(cp.pivot_table(index="month", columns="name", values="piglet_wan").loc["2025-01":].round(2).to_string())
        print(mm.tail(16).to_string())
        print(ps.round(4).to_string())
        print(rng)
        print(sch.round(4).to_string())
        print(mg.round(3).to_string())
        print(ls.round(4).to_string())
        print(feed.tail(8).to_string())
