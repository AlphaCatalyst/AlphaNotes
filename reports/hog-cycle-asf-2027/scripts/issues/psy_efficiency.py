"""Issue #11: how fast does output per breeding sow grow, is the current high PSY a bottom-of-cycle
effect, and how much can efficiency offset the 2025-2026 sow cuts?

  claims     PSY/MSY figures quoted by officials, researchers, consultancies, brokers and media
             (research/psy_efficiency/claims.csv) on one basis: change, years, annualised rate.
  official   NBS quarterly slaughter against breeding sows lagged LAG_M months. Sows are monthly:
             NBS quarter-ends 2020-2022, NBS/MOA releases, MOA month-ends from 2021-12 and
             quarter-ends from 2025-11, log-linear in between. The ratio bundles PSY, wean-to-market
             survival, sows counted before they farrow and timing, so it is not PSY. The naive ratio
             divides by the sows at the end of the slaughter quarter. 2016-2019: NBS slaughter against
             the MOA sample's year-on-year sow changes (no national level was published).
  reconcile  claimed PSY x lagged sows x wean-to-market survival against NBS slaughter.
  cycle      year-on-year change of slaughter per lagged sow against the MOA hog price k quarters
             earlier; the monitored-farm PSY series; piglet feed against sow feed (#7, ft_stages.csv).
  culling    how much output per sow rises when the sows removed are less productive than those kept,
             or when smaller, less productive farms exit.
  scenarios  one sow path (published to the latest quarter-end, then SOW_MOM a month) and three paths
             for slaughter per lagged sow; piglets born (sows lagged 4 months) and slaughter (10 months).

Inputs (data/processed/): moa_sows_monthly.csv, nbs_quarterly.csv, moa_weekly_prices.csv,
issues/ft_stages.csv; research/psy_efficiency/claims.csv.
Outputs: data/processed/issues/psy_*.csv (derived only), charts/i11_*.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
OUT = PROC / "issues"
CLAIMS = ROOT / "research" / "psy_efficiency" / "claims.csv"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import autumn_dip as ad  # noqa: E402

LAG_M = ad.LAG_M
PIGLET_LAG_M = 4      # mating -> farrowing
SOW_MOM = -0.005      # sows after the last published quarter-end (#6/#9 "缓降")
SURVIVAL = 0.9267     # wean-to-market survival quoted by 涌益 for July 2026 (育肥出栏成活率)
SCALE_SHARE = 0.73    # 规模化率 2025 (MOA estimate quoted by 第一财经, 2026-07-05)
FIRST_Q, LAST_Q = pd.Period("2026Q4", "Q"), pd.Period("2027Q4", "Q")
# year-on-year change of slaughter per lagged sow, 2026Q4 .. 2027Q4
SCENARIOS = {
    "效率持续快速提升": [0.045] * 5,
    "回归长期增速": [0.01] * 5,
    "随猪价上行回落": [0.025, 0.01, -0.02, -0.03, -0.03],
}
NAIVE_10 = 0.10
FLEX = (2, 5, 9)      # price flexibility used in #1 and #3
FUT_2027 = ("LH2701", "LH2703", "LH2705", "LH2707", "LH2709")


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------
def sows_long() -> tuple[pd.Series, pd.Index]:
    m = pd.read_csv(PROC / "moa_sows_monthly.csv").dropna(subset=["sow_wan"])
    pts = pd.Series(m["sow_wan"].values, index=pd.PeriodIndex(m["month"], freq="M"))
    q = pd.read_csv(PROC / "nbs_quarterly.csv").dropna(subset=["sow_inventory_wan"])
    qp = pd.Series(q["sow_inventory_wan"].values,
                   index=pd.PeriodIndex(q["period"], freq="Q").asfreq("M", "end"))
    pts = pd.concat([qp, pts])
    pts = pts[~pts.index.duplicated(keep="last")].sort_index()
    idx = pd.period_range(pts.index.min(), pts.index.max(), freq="M")
    return np.exp(np.log(pts.reindex(idx)).interpolate()), pts.index


def nbs_slaughter() -> pd.DataFrame:
    """Quarterly slaughter with year-on-year changes; 2016 changes come from the cumulative ones."""
    n = pd.read_csv(PROC / "nbs_quarterly.csv").dropna(subset=["hog_slaughter_q_wan"])
    d = n.set_index(pd.PeriodIndex(n["period"], freq="Q"))[["hog_slaughter_q_wan", "hog_slaughter_cum_wan",
                                                           "hog_slaughter_cum_yoy_pct"]]
    d.columns = ["q", "cum", "cum_yoy"]
    prev_cum = d["cum"] / (1 + d["cum_yoy"] / 100)
    prev_q = prev_cum - prev_cum.groupby(d.index.year).shift().fillna(0)
    d["yoy"] = d["q"] / d["q"].shift(4) - 1
    d["yoy"] = d["yoy"].fillna(d["q"] / prev_q - 1)
    return d


def hog_price_q() -> pd.Series:
    m = pd.read_csv(PROC / "moa_weekly_prices.csv")
    d = pd.to_datetime(m["collect_date"], errors="coerce")
    s = pd.Series(m["live_hog"].values, index=d).dropna().sort_index()
    return s.groupby(s.index.to_period("Q")).mean()


# ---------------------------------------------------------------------------
# 1. claims on one basis
# ---------------------------------------------------------------------------
def claims() -> pd.DataFrame:
    c = pd.read_csv(CLAIMS)
    num = c[c["from_value"].notna() & c["to_value"].notna() & c["from_year"].notna()].copy()
    num["change"] = num["to_value"] / num["from_value"] - 1
    num["years"] = num["to_year"] - num["from_year"]
    num["annualised"] = (1 + num["change"]) ** (1 / num["years"]) - 1
    return c.merge(num[["id", "change", "years", "annualised"]], on="id", how="left")


# ---------------------------------------------------------------------------
# 2. official ratios
# ---------------------------------------------------------------------------
def official(sows: pd.Series) -> pd.DataFrame:
    d = ad.per_sow(sows)
    d["ttm_slaughter"] = d["slaughter"].rolling(4).sum()
    d["ttm_sows_lag"] = d["sows_lag"].rolling(4).mean()
    d["per_lagged_sow"] = d["ttm_slaughter"] / d["ttm_sows_lag"]
    d["sows_end"] = [sows.get(p.asfreq("M", "end"), np.nan) for p in d.index]
    d["per_end_sow"] = d["ttm_slaughter"] / d["sows_end"]
    d["sows_end_yoy"] = d["sows_end"] / d["sows_end"].shift(4) - 1
    d["naive_yoy"] = (1 + d["slaughter_yoy"]) / (1 + d["sows_end_yoy"]) - 1
    d["per_lagged_sow_ttm_yoy"] = d["per_lagged_sow"] / d["per_lagged_sow"].shift(4) - 1
    d["per_end_sow_ttm_yoy"] = d["per_end_sow"] / d["per_end_sow"].shift(4) - 1
    return d


def sample_era() -> pd.DataFrame:
    """2016-2019: MOA sample sow changes (lagged) against NBS slaughter changes."""
    m = pd.read_csv(PROC / "moa_sows_monthly.csv")
    m = m[m["scope"].astype(str).str.contains("样本")].dropna(subset=["sow_yoy_pct"])
    yoy = pd.Series(m["sow_yoy_pct"].values / 100, index=pd.PeriodIndex(m["month"], freq="M"))
    yoy = yoy[~yoy.index.duplicated()]
    s = nbs_slaughter()
    rows = []
    for q in pd.period_range("2016Q1", "2019Q2", freq="Q"):
        months = [pd.Period(q.start_time, "M") + i - LAG_M for i in range(3)]
        if not all(mm in yoy.index for mm in months):
            continue
        sy = float(yoy.reindex(months).mean())
        rows.append({"quarter": str(q), "slaughter_yoy": s.at[q, "yoy"], "sample_sows_lag_yoy": sy,
                     "implied_per_sow_yoy": (1 + s.at[q, "yoy"]) / (1 + sy) - 1,
                     "sow_scope": m.set_index("month").loc[str(months[0]), "scope"]})
    return pd.DataFrame(rows)


def reconcile(d: pd.DataFrame, cl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for lab, q in (("2025 年", pd.Period("2025Q4", "Q")), ("截至 2026Q3 的 4 个季度", d.index.max())):
        sl, sw = d.at[q, "ttm_slaughter"], d.at[q, "ttm_sows_lag"]
        for _, r in cl[cl["metric"].isin(["PSY", "窝均健仔折 PSY"]) & cl["to_value"].notna()
                       & cl["scope"].str.contains("全国|监测")].iterrows():
            implied = sw * r["to_value"] * SURVIVAL
            rows.append({"window": lab, "claim": r["id"], "scope": r["scope"], "psy": r["to_value"],
                         "sows_lag": sw, "slaughter": sl, "implied_slaughter": implied,
                         "gap": sl / implied - 1, "required_survival": sl / (sw * r["to_value"]),
                         "implied_psy_at_survival": sl / sw / SURVIVAL})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. cycle: per-sow changes against earlier prices; feed ratio
# ---------------------------------------------------------------------------
def cycle(d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = hog_price_q()
    py = p / p.shift(4) - 1
    x = d[["per_sow_yoy"]].dropna()
    rows = []
    for k in range(0, 9):
        z = pd.concat([x["per_sow_yoy"], py.shift(k).reindex(x.index)], axis=1).dropna()
        rows.append({"lag_q": k, "n": len(z), "corr": z.corr().iloc[0, 1]})
    cor = pd.DataFrame(rows)
    k = int(cor.loc[cor["corr"].idxmin(), "lag_q"])
    x["price"] = p.reindex(x.index)
    x["price_yoy_lag"] = py.shift(k).reindex(x.index)
    x["lag_q"] = k
    return x, cor


def feed_ratio() -> pd.DataFrame:
    f = pd.read_csv(OUT / "ft_stages.csv")
    f = f.dropna(subset=["piglet_yoy", "sow_feed_yoy"])
    f["piglet_over_sow_feed"] = (1 + f["piglet_yoy"] / 100) / (1 + f["sow_feed_yoy"] / 100) - 1
    return f[["period", "window", "piglet_yoy", "sow_feed_yoy", "piglet_over_sow_feed", "source_form"]]


# ---------------------------------------------------------------------------
# 4. culling and exit arithmetic
# ---------------------------------------------------------------------------
def culling(cut: float) -> pd.DataFrame:
    rows = []
    for r in (1.0, 0.9, 0.8, 0.6):
        rows.append({"kind": "场内淘汰", "sow_cut": cut, "removed_rel_productivity": r,
                     "per_sow_change": (1 - cut * r) / (1 - cut) - 1, "output_change": -cut * r})
    for s in (0.8, 0.6):
        for share in (0.5, 0.8):
            small0, big0 = 1 - SCALE_SHARE, SCALE_SHARE
            small1, big1 = small0 - cut * share, big0 - cut * (1 - share)
            p0, p1 = small0 * s + big0, small1 * s + big1
            rows.append({"kind": "中小场退出", "sow_cut": cut, "removed_rel_productivity": s,
                         "small_share_of_cut": share,
                         "per_sow_change": (p1 / (small1 + big1)) / (p0 / (small0 + big0)) - 1,
                         "output_change": p1 / p0 - 1})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. scenarios on one sow path
# ---------------------------------------------------------------------------
def lagged_m(sows: pd.Series, q: pd.Period, lag: int) -> float:
    months = [pd.Period(q.start_time, "M") + i - lag for i in range(3)]
    return float(sows.reindex(months).mean()) if all(m in sows.index for m in months) else np.nan


def scenarios(sows: pd.Series, d: pd.DataFrame) -> pd.DataFrame:
    sw = ad.extend_sows(sows, SOW_MOM, to="2027-12")
    qs = pd.period_range(FIRST_Q, LAST_Q, freq="Q")
    base = d["slaughter"].copy()
    rows = []
    paths = {**SCENARIOS, "参照：每头产出 +10%": [NAIVE_10] * len(qs)}
    for name, g in paths.items():
        lvl = base.copy()
        gq = dict(zip(qs, g))
        for q in qs:
            s_yoy = lagged_m(sw, q, LAG_M) / lagged_m(sw, q - 4, LAG_M) - 1
            y = (1 + s_yoy) * (1 + gq[q]) - 1
            lvl[q] = lvl[q - 4] * (1 + y)
            p_q = q
            p_yoy = lagged_m(sw, p_q, PIGLET_LAG_M) / lagged_m(sw, p_q - 4, PIGLET_LAG_M) - 1
            g_p = gq.get(p_q + 2, g[-1])
            rows.append({"scenario": name, "quarter": str(q), "per_sow_yoy": gq[q], "sows_lag_yoy": s_yoy,
                         "slaughter_yoy": y, "slaughter": lvl[q], "slaughter_prev_year": lvl[q - 4],
                         "sow_months": f"{pd.Period(q.start_time, 'M') - LAG_M}~{pd.Period(q.start_time, 'M') - LAG_M + 2}",
                         "uses_sow_extension": bool(pd.Period(q.start_time, "M") - LAG_M + 2 > sows.index.max()),
                         "piglets_sows_lag_yoy": p_yoy, "piglets_yoy": (1 + p_yoy) * (1 + g_p) - 1,
                         "piglet_uses_sow_extension": bool(pd.Period(q.start_time, "M") - PIGLET_LAG_M + 2
                                                           > sows.index.max())})
    out = pd.DataFrame(rows)
    ref = out[out["scenario"] == "回归长期增速"].set_index("quarter")["slaughter"]
    out["gap_vs_longrun"] = out["slaughter"] - out["quarter"].map(ref)
    return out


def market_check(sc: pd.DataFrame) -> pd.DataFrame:
    """#3's rough map: 2027 Jan-Sep price = 2026 Jan-Sep spot x (1 - flexibility x supply change), with
    demand, imports, frozen stock and carcass weight held constant; read both ways."""
    base = float(pd.read_csv(OUT / "xueqiu_supply_price_map.csv")["base_px_2026q1_q3"].iloc[0])
    fu = pd.read_csv(PROC / "futures_lh_daily.csv", parse_dates=["trade_date"])
    fu = fu[fu["contract"].isin(FUT_2027)].pivot_table(index="trade_date", columns="contract",
                                                       values="settle").dropna()
    q123 = [f"2027Q{i}" for i in (1, 2, 3)]
    rows = []
    for name, g in sc.groupby("scenario", sort=False):
        s = g.set_index("quarter").loc[q123]
        sup = s["slaughter"].sum() / s["slaughter_prev_year"].sum() - 1
        rows.append({"case": name, "supply_change_2027q1_q3": sup,
                     **{f"px_flex{fl}": base * (1 - fl * sup) for fl in FLEX}})
    for when in (pd.Timestamp("2026-10-08"), fu.index.max()):
        day = fu.loc[:when].index[-1]
        px = float(fu.loc[day].mean()) / 1000
        rows.append({"case": f"期货 2701—2709 结算价均值（{day:%Y-%m-%d}）", "futures_mean": px,
                     **{f"implied_supply_flex{fl}": (1 - px / base) / fl for fl in FLEX}})
    out = pd.DataFrame(rows)
    out["base_px_2026_jan_sep"] = base
    return out


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------
def chart_claims(cl: pd.DataFrame, d: pd.DataFrame):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title

    rows = []
    for _, r in cl.dropna(subset=["annualised"]).iterrows():
        lab = f"{r['id']} {r['speaker'].split('（')[0]}：{int(r['from_year'])}→{int(r['to_year'])}（{r['scope']}）"
        rows.append((lab, r["annualised"], r["change"], "claim"))
    q = d.index.max()
    v = d["per_lagged_sow"]
    rows += [
        (f"官方：每头滞后母猪出栏 2021→{q}", (v[q] / v[pd.Period('2021Q4', 'Q')]) ** (1 / ((q - pd.Period('2021Q4', 'Q')).n / 4)) - 1, np.nan, "off"),
        (f"官方：同上 2022→{q}", (v[q] / v[pd.Period('2022Q4', 'Q')]) ** (1 / ((q - pd.Period('2022Q4', 'Q')).n / 4)) - 1, np.nan, "off"),
        ("官方：同上 2025 年单年", d.at[pd.Period("2025Q4", "Q"), "per_lagged_sow_ttm_yoy"], np.nan, "off"),
        (f"官方：同上 {q} 单季同比", d.at[q, "per_sow_yoy"], np.nan, "off"),
        (f"错配：除以期末母猪 {q} 单季同比", d.at[q, "naive_yoy"], np.nan, "naive"),
    ]
    rows = rows[::-1]
    fig, ax = plt.subplots(figsize=(12, 6.2))
    col = {"claim": C["spot"], "off": C["stock"], "naive": C["fut4"]}
    ax.barh([r[0] for r in rows], [r[1] * 100 for r in rows], color=[col[r[3]] for r in rows])
    for i, r in enumerate(rows):
        ax.text(r[1] * 100 + 0.2, i, f"{r[1]:+.1%}" + (f"（累计 {r[2]:+.0%}）" if r[2] == r[2] else ""),
                va="center", fontsize=8)
    ax.axvline(0, color=C["dark"], lw=0.8)
    ax.axvline(10, color=C["fut4"], lw=0.8, ls=":")
    ax.set_xlabel("年均增速，%（单年、单季为当期同比）")
    title(fig, "“提升 10%”与“每年 1%”：口径不同",
          "各方 PSY 说法多是 7—10 年累计，年化 3%—5%；官方出栏与滞后母猪之比跨周期年化不到 1%；单季 10% 以上只在除以期末母猪时出现")
    source(fig, "说法见 research/psy_efficiency/claims.csv；官方 = 国家统计局季度出栏 ÷ 滞后 10 个月的能繁母猪（农业农村部、统计局），"
                "滚动 4 个季度。本文计算。")
    return save(fig, "i11_claims.png")


def chart_official(d: pd.DataFrame, cl: pd.DataFrame, x: pd.DataFrame, fr: pd.DataFrame):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2))
    ax = axes[0]
    z = d.dropna(subset=["per_lagged_sow"])
    t = [p.end_time for p in z.index]
    ax.plot(t, z["per_lagged_sow"], "-o", ms=3, color=C["stock"], label="出栏 ÷ 滞后 10 个月能繁（滚动 4 季）")
    ax.plot(t, z["per_end_sow"], "--", color=C["fut4"], label="出栏 ÷ 期末能繁（错配）")
    mon = cl[cl["id"].isin(["P01", "P02"])]
    yrs = {int(r["to_year"]): r["to_value"] for _, r in mon.iterrows()}
    yrs.update({int(r["from_year"]): r["from_value"] for _, r in mon.iterrows()})
    yrs = {y: v for y, v in sorted(yrs.items()) if y >= 2021}
    ax.plot([pd.Timestamp(f"{y}-12-31") for y in yrs], list(yrs.values()), "s", color=C["spot"], ms=7,
            label="微猪监测场 PSY（断奶仔猪）")
    ax.axhline(25, color=C["spot"], ls=":", lw=0.8)
    ax.text(t[0], 25.1, "农业农村部口径：2025 年行业平均 PSY 约 25", fontsize=8, color=C["spot"])
    ax.set_ylabel("头 / 母猪·年")
    ax.legend(loc="center right")
    ax.set_title("水平：样本场 PSY 约 24—25，官方出栏 ÷ 滞后能繁约 18")

    ax = axes[1]
    price = hog_price_q().loc[pd.Period("2020Q1", "Q"):x.index.max()]
    qs = list(price.index)
    pos = {q: i for i, q in enumerate(qs)}
    ax.bar([pos[q] for q in x.index], x["per_sow_yoy"] * 100,
           color=[C["stock"] if v >= 0 else C["spot"] for v in x["per_sow_yoy"]], label="出栏 ÷ 滞后能繁，同比")
    ax.plot([pos[q] for q in x.index], d.loc[x.index, "naive_yoy"] * 100, "--", color=C["fut4"], lw=1.2,
            label="除以期末能繁（错配），同比")
    ax2 = ax.twinx()
    ax2.plot(range(len(qs)), price.values, color=C["dark"], lw=1.3, label="活猪价格（季均，元/公斤）")
    ax2.set_ylabel("元/公斤")
    ax2.spines["right"].set_visible(True)
    ax.set_xticks(range(0, len(qs), 4))
    ax.set_xticklabels([str(qs[i])[:4] for i in range(0, len(qs), 4)])
    ax.axhline(0, color=C["dark"], lw=0.6)
    ax.set_ylabel("同比，%")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=7.5)
    ax.set_title("变化：价格高位后 1—2 年每头产出放慢，低位淘汰后加快")
    title(fig, "PSY、能繁母猪与出栏为什么对不上",
          "样本场 PSY 不是全国平均；能繁母猪要按约 10 个月的生产周期滞后，除以期末已去化的母猪会把每头产出同比高估 10 个百分点以上")
    source(fig, "国家统计局季度出栏；能繁母猪：统计局季末（2020—2022）、农业农村部月末/季末，月间对数插值；"
                "微猪科技年报（中国养猪网转载）；活猪价格为农业农村部集贸市场周价的季均值。本文计算。")
    return save(fig, "i11_official.png")


def chart_scenarios(sc: pd.DataFrame, d: pd.DataFrame):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.0))
    cols = {"效率持续快速提升": C["spot"], "回归长期增速": C["stock"], "随猪价上行回落": C["fut4"],
            "参照：每头产出 +10%": C["grey"]}
    ax = axes[0]
    hist = d.loc[pd.Period("2025Q1", "Q"):, "slaughter_yoy"]
    hx = [str(q) for q in hist.index]
    ax.plot(hx, hist * 100, "-o", color=C["dark"], ms=3.5, label="统计局实际")
    for name, g in sc.groupby("scenario", sort=False):
        ax.plot([hx[-1]] + list(g["quarter"]), [hist.iloc[-1] * 100] + list(g["slaughter_yoy"] * 100), "-o", ms=3.5,
                color=cols[name], ls=":" if name.startswith("参照") else "-", label=name)
    ax.axhline(0, color=C["dark"], lw=0.6)
    ax.set_ylabel("出栏同比，%")
    ax.tick_params(axis="x", labelsize=7.5, rotation=45)
    ax.legend(loc="lower left", fontsize=8)
    ax.set_title("出栏同比（同一条能繁路径）")

    ax = axes[1]
    g = sc[sc["scenario"] != "参照：每头产出 +10%"]
    piv = g.pivot_table(index="quarter", columns="scenario", values="gap_vs_longrun", sort=False)
    piv = piv[[c for c in SCENARIOS if c in piv]]
    w = 0.38
    xs = np.arange(len(piv))
    for i, c in enumerate([c for c in piv.columns if c != "回归长期增速"]):
        ax.bar(xs + (i - 0.5) * w, piv[c], w, color=cols[c], label=f"{c} − 回归长期")
    ax.set_xticks(xs)
    ax.set_xticklabels(piv.index, fontsize=8)
    ax.axhline(0, color=C["dark"], lw=0.6)
    ax.set_ylabel("万头 / 季度")
    ax.legend(loc="lower left", fontsize=8)
    ax.set_title("与“回归长期增速”相比，每季度多出或少出的头数")
    title(fig, "三种效率情景：2027 年二、三季度出栏差 3—7 个百分点",
          f"能繁母猪按已公布数据，2026 年 9 月后每月 {SOW_MOM:+.1%}；每头滞后母猪出栏同比分别取 +4.5%、+1%、先 +2.5% 后 −3%")
    source(fig, "国家统计局季度出栏；农业农村部、统计局能繁母猪（滞后 10 个月）。情景为假设，不是预测。本文计算。")
    return save(fig, "i11_scenarios.png")


# ---------------------------------------------------------------------------
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sows, known = sows_long()
    cl = claims()
    d = official(sows)
    se = sample_era()
    rec = reconcile(d, cl)
    x, cor = cycle(d)
    fr = feed_ratio()
    cut = float(sows[pd.Period("2026-09", "M")] / sows[pd.Period("2025-09", "M")] - 1)
    cu = culling(-cut)
    sc = scenarios(sows, d)
    mk = market_check(sc)

    cl.to_csv(OUT / "psy_claims.csv", index=False, float_format="%.4f")
    mk.to_csv(OUT / "psy_market.csv", index=False, float_format="%.4f")
    cols = ["slaughter", "sows_lag", "per_sow", "slaughter_yoy", "sows_lag_yoy", "per_sow_yoy", "ttm_slaughter",
            "ttm_sows_lag", "per_lagged_sow", "per_lagged_sow_ttm_yoy", "sows_end", "sows_end_yoy", "naive_yoy",
            "per_end_sow", "per_end_sow_ttm_yoy"]
    d[cols].rename_axis("quarter").reset_index().to_csv(OUT / "psy_official.csv", index=False, float_format="%.4f")
    se.to_csv(OUT / "psy_sample_era.csv", index=False, float_format="%.4f")
    rec.to_csv(OUT / "psy_reconcile.csv", index=False, float_format="%.4f")
    x.rename_axis("quarter").reset_index().to_csv(OUT / "psy_cycle.csv", index=False, float_format="%.4f")
    cor.to_csv(OUT / "psy_cycle_lag_corr.csv", index=False, float_format="%.4f")
    fr.to_csv(OUT / "psy_feed_ratio.csv", index=False, float_format="%.4f")
    cu.to_csv(OUT / "psy_culling.csv", index=False, float_format="%.4f")
    sc.to_csv(OUT / "psy_scenarios.csv", index=False, float_format="%.4f")
    pd.Series({"sows_known_last": str(known.max()), "sows_last": float(sows.iloc[-1]), "sow_cut_yoy": cut,
               "survival": SURVIVAL, "scale_share": SCALE_SHARE, "sow_mom": SOW_MOM}).to_csv(
        OUT / "psy_facts.csv", header=["value"], index_label="key")

    chart_claims(cl, d)
    chart_official(d, cl, x, fr)
    chart_scenarios(sc, d)

    with pd.option_context("display.width", 220, "display.max_columns", 30):
        print(cl.dropna(subset=["annualised"])[["id", "speaker", "scope", "from_year", "to_year", "change", "years",
                                                "annualised"]].round(4).to_string(index=False))
        print(d[cols].round(4).to_string())
        print(se.round(4).to_string(index=False))
        print(rec.round(3).to_string(index=False))
        print(cor.round(3).to_string(index=False))
        print(x.round(3).to_string())
        print(fr.round(4).to_string(index=False))
        print(cu.round(4).to_string(index=False))
        print(sc.drop(columns=["sow_months"]).round(4).to_string(index=False))
        print(mk.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
