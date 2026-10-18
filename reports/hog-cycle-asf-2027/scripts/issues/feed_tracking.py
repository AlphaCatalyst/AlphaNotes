"""Issue #7: can industrial pig-feed volumes (sow / piglet / finishing) track the herd, destocking and
future slaughter, nationally and for listed hog producers?

  annual    CFIA annual pig feed against NBS slaughter, pork and year-end inventory and MOA sows:
            the year-on-year gap ("drift") and industrial feed per slaughtered hog;
  monthly   CFIA monthly pig feed (revised series read off the official charts; first releases where
            the text gave them) against MOA sows, NBS quarterly slaughter and inventory; quarterly
            lead/lag correlations and the dates on which each year-on-year series changed sign;
  vintage   first release vs revised value and year-on-year change; release lags;
  stages    every published stage year-on-year (仔猪/母猪/育肥) next to sows, slaughter and carcass
            weight for the same window and slaughter in the two following quarters; the ratio of
            that later slaughter change to the piglet-feed change, applied to July 2026;
  model     steady-state full-ration feed per head by stage (low / mid / high), the share of each
            stage, and what the July 2026 readings imply for heads under per-head and coverage
            assumptions;
  company   东瑞 (annual report production/sales tables) and 牧原 (ESG reports, convertible-bond
            prospectus): feed per hog sold.

Inputs (data/processed/): cfia_pig_feed_monthly.csv, cfia_pig_feed_stage.csv,
cfia_pig_feed_annual.csv, cfia_feed_releases.csv (scripts/industry/cfia_feed.py), moa_sows_monthly.csv,
nbs_quarterly.csv, nbs_annual_bulletin.csv; research/feed_tracking/company_feed.csv.
Outputs: data/processed/issues/ft_*.csv (derived only), charts/i07_*.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
OUT = PROC / "issues"
RES = ROOT / "research" / "feed_tracking"
sys.path.insert(0, str(ROOT / "scripts"))

# Stage windows of the published stage YoY (first and last month covered).
WINDOWS = {"2019": ("2019-01", "2019-12"), "2021-01~05": ("2021-01", "2021-05"), "2022Q1": ("2022-01", "2022-03"),
           "2023Q1-Q3": ("2023-01", "2023-09"), "2024H1": ("2024-01", "2024-06"),
           "2024Q1-Q3": ("2024-01", "2024-09"), "2025": ("2025-01", "2025-12"), "2026H1": ("2026-01", "2026-06")}
# 全国畜牧总站 (2026-08), July 2026: physical vs full-ration-equivalent YoY (%).
NAHS_2026_07 = {"sow": (-2.1, -5.8), "piglet": (-4.1, -9.8), "finishing": (6.2, 1.7)}

# Steady-state full-ration feed (kg) with (low, mid, high); see the Issue #7 note for sources.
PARAMS = {
    "sow_t_per_year": (1.00, 1.10, 1.20),        # breeding sow, gestation + lactation, t per sow-year
    "replacement_rate": (0.35, 0.40, 0.45),      # gilts entering per sow-year
    "gilt_kg": (240, 270, 300),                  # rearing feed per gilt
    "boar_kg_per_sow": (15, 25, 35),             # boars, per sow-year
    "piglet_kg": (21, 33, 46),                   # creep + nursery to 25-30 kg, per weaned piglet
    "finish_fcr": (2.5, 2.75, 3.0),              # 30 kg to slaughter
    "slaughter_live_kg": (120, 125, 130),
    "hogs_per_sow_year": (19.5, 18.0, 16.5),     # NBS slaughter / breeding sows (high -> less sow feed per hog)
    "nursery_finish_survival": (0.97, 0.945, 0.92),
}
MARGINAL_FCR = (3.0, 3.5, 4.0)  # feed per extra kg of live weight above ~120 kg
LIVE_PER_CARCASS = 1 / 0.74


def write(df: pd.DataFrame, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / name, index=False, encoding="utf-8")


def pct(a, b):
    return (a / b - 1) * 100


# ---------------------------------------------------------------------------
def load():
    mon = pd.read_csv(PROC / "cfia_pig_feed_monthly.csv")
    stage = pd.read_csv(PROC / "cfia_pig_feed_stage.csv")
    annual = pd.read_csv(PROC / "cfia_pig_feed_annual.csv")
    rel = pd.read_csv(PROC / "cfia_feed_releases.csv")
    sows = pd.read_csv(PROC / "moa_sows_monthly.csv")
    national = ~sows.scope.astype(str).str.contains("400县")
    sows = sows.assign(_n=national).sort_values(["month", "_n"]).drop_duplicates("month", keep="last")
    nbsq = pd.read_csv(PROC / "nbs_quarterly.csv")
    bull = pd.read_csv(PROC / "nbs_annual_bulletin.csv")
    comp = pd.read_csv(RES / "company_feed.csv", dtype={"code": str})
    return mon, stage, annual, rel, sows, nbsq, bull, comp


def sow_series(sows: pd.DataFrame, nbsq: pd.DataFrame) -> pd.DataFrame:
    """Monthly breeding-sow level and YoY: MOA where published, NBS quarter-ends to fill 2020-2022."""
    s = sows.set_index("month")[["sow_wan", "sow_yoy_pct"]].copy()
    q = nbsq.dropna(subset=["sow_inventory_wan"]).copy()
    q["month"] = q.period.str[:4] + "-" + q.period.str[-1].astype(int).mul(3).map("{:02d}".format)
    q = q.set_index("month").sow_inventory_wan
    idx = pd.period_range("2019-01", "2026-09", freq="M").astype(str)
    s = s.reindex(idx)
    s["sow_wan"] = s.sow_wan.fillna(q.reindex(idx))
    lvl_yoy = pct(s.sow_wan, s.sow_wan.shift(12))
    s["sow_yoy"] = s.sow_yoy_pct.fillna(lvl_yoy)
    return s.rename_axis("month")


def quarterly_nbs(nbsq: pd.DataFrame) -> pd.DataFrame:
    q = nbsq.set_index("period")[["hog_slaughter_q_wan", "pork_output_q_wan_t", "carcass_wt_kg_est",
                                  "hog_inventory_wan", "release_date"]].copy()
    q["slaughter_yoy"] = pct(q.hog_slaughter_q_wan, q.hog_slaughter_q_wan.shift(4))
    q["pork_yoy"] = pct(q.pork_output_q_wan_t, q.pork_output_q_wan_t.shift(4))
    q["inventory_yoy"] = pct(q.hog_inventory_wan, q.hog_inventory_wan.shift(4))
    q["carcass_chg_kg"] = q.carcass_wt_kg_est - q.carcass_wt_kg_est.shift(4)
    return q


# ---------------------------------------------------------------------------
def annual_table(annual, bull, sows_m, mon):
    b = bull.set_index("year")
    a = annual.set_index("year")[["pig_10kt", "pig_yoy", "release_date"]].copy()
    a.index = a.index.astype(int)
    a["slaughter_wan"] = b.b_slaughter
    a["pork_10kt"] = b.b_pork
    a["inventory_end_wan"] = b.b_hog_inv
    a["slaughter_yoy"] = pct(b.b_slaughter, b.b_slaughter.shift(1)).reindex(a.index)
    a["pork_yoy"] = pct(b.b_pork, b.b_pork.shift(1)).reindex(a.index)
    a["inventory_end_yoy"] = pct(b.b_hog_inv, b.b_hog_inv.shift(1)).reindex(a.index)
    dec = sows_m[sows_m.index.str.endswith("-12")]
    a["sow_dec_yoy"] = pd.Series(dec.sow_yoy.values, index=dec.index.str[:4].astype(int)).reindex(a.index)
    a["gap_vs_slaughter_pp"] = a.pig_yoy - a.slaughter_yoy
    a["gap_vs_pork_pp"] = a.pig_yoy - a.pork_yoy
    a["feed_kg_per_hog"] = a.pig_10kt / a.slaughter_wan * 1000
    a["feed_t_per_t_pork"] = a.pig_10kt / a.pork_10kt
    lo, mid, hi = whole_herd_need()
    a["coverage_mid"] = a.feed_kg_per_hog / mid
    a["coverage_low"] = a.feed_kg_per_hog / hi
    a["coverage_high"] = a.feed_kg_per_hog / lo
    mon = mon.assign(year=mon.month.str[:4].astype(int))
    msum = mon.groupby("year").revised_10kt.agg(["sum", "count"])
    a["monthly_chart_sum_10kt"] = msum["sum"].where(msum["count"] == 12).reindex(a.index)
    a["monthly_vs_annual_pct"] = pct(a.monthly_chart_sum_10kt, a.pig_10kt)
    return a.reset_index().round(3)


def whole_herd_need():
    """Full-ration feed per slaughtered hog for the whole herd (low, mid, high), kg."""
    out = []
    for k in range(3):
        p = {n: v[k] for n, v in PARAMS.items()}
        sow_sys = p["sow_t_per_year"] * 1000 + p["replacement_rate"] * p["gilt_kg"] + p["boar_kg_per_sow"]
        per_hog_sow = sow_sys / p["hogs_per_sow_year"]
        piglet = p["piglet_kg"] / p["nursery_finish_survival"]
        finish = (p["slaughter_live_kg"] - 30) * p["finish_fcr"]
        out.append(per_hog_sow + piglet + finish)
    return tuple(out)


def model_tables(nbsq_q):
    rows = []
    for k, name in enumerate(["低", "中", "高"]):
        p = {n: v[k] for n, v in PARAMS.items()}
        sow_sys = p["sow_t_per_year"] * 1000 + p["replacement_rate"] * p["gilt_kg"] + p["boar_kg_per_sow"]
        per_hog_sow = sow_sys / p["hogs_per_sow_year"]
        piglet = p["piglet_kg"] / p["nursery_finish_survival"]
        finish = (p["slaughter_live_kg"] - 30) * p["finish_fcr"]
        tot = per_hog_sow + piglet + finish
        rows.append(dict(case=name, sow_system_kg_per_sow_year=round(sow_sys), sow_kg_per_hog=round(per_hog_sow, 1),
                         piglet_kg_per_hog=round(piglet, 1), finishing_kg_per_hog=round(finish, 1),
                         total_kg_per_hog=round(tot, 1), sow_share=round(per_hog_sow / tot, 3),
                         piglet_share=round(piglet / tot, 3), finishing_share=round(finish / tot, 3),
                         herd_fcr_live=round(tot / p["slaughter_live_kg"], 2)))
    steady = pd.DataFrame(rows)

    # what the July 2026 readings imply for heads: heads_yoy = (1+feed)/(1+per_head)/(1+coverage) - 1
    q = nbsq_q
    dcarc = q.loc["2026Q2", "carcass_wt_kg_est"] - q.loc["2025Q2", "carcass_wt_kg_est"]
    dlive = dcarc * LIVE_PER_CARCASS
    fin_base = (PARAMS["slaughter_live_kg"][1] - 30) * PARAMS["finish_fcr"][1]
    per_head_fin = [dlive * m / fin_base * 100 for m in MARGINAL_FCR]
    grid = []
    cases = {"sow": [-2.0, 0.0, 2.0], "piglet": [-5.0, -2.0, 0.0], "finishing": per_head_fin}
    for stage_name, per_head_list in cases.items():
        phys, full = NAHS_2026_07[stage_name]
        for basis, feed in (("实物", phys), ("折全价", full)):
            for ph in per_head_list:
                for cov in (-1.0, 0.0, 2.0):
                    heads = ((1 + feed / 100) / (1 + ph / 100) / (1 + cov / 100) - 1) * 100
                    grid.append(dict(stage=stage_name, basis=basis, feed_yoy=feed, per_head_chg=round(ph, 2),
                                     coverage_chg=cov, implied_heads_yoy=round(heads, 1)))
    grid = pd.DataFrame(grid)
    weight = pd.DataFrame([dict(carcass_2025Q2=q.loc["2025Q2", "carcass_wt_kg_est"],
                                carcass_2026Q2=q.loc["2026Q2", "carcass_wt_kg_est"], carcass_chg_kg=round(dcarc, 2),
                                live_chg_kg=round(dlive, 2), finishing_kg_base=fin_base,
                                per_kg_effect_pct=" / ".join(f"{m / fin_base * 100:.2f}" for m in MARGINAL_FCR),
                                per_head_finishing_pct=" / ".join(f"{x:.1f}" for x in per_head_fin))])
    return steady, grid, weight


# ---------------------------------------------------------------------------
def monthly_panel(mon, sows_m, nbsq_q):
    m = mon.set_index("month")[["revised_10kt", "revised_basis", "first_10kt", "first_yoy", "revised_yoy",
                                "revision_pct"]].copy()
    m["days"] = pd.PeriodIndex(m.index, freq="M").days_in_month
    m["revised_per_day"] = m.revised_10kt / m.days
    m["revised_yoy_per_day"] = pct(m.revised_per_day, m.revised_per_day.shift(12))
    r3 = m.revised_10kt.rolling(3).sum()
    m["revised_3m_yoy"] = pct(r3, r3.shift(12))
    m = m.join(sows_m[["sow_wan", "sow_yoy"]], how="left")
    qkey = pd.PeriodIndex(m.index, freq="M").asfreq("Q").astype(str)
    m["quarter"] = qkey
    m["slaughter_q_yoy"] = [nbsq_q.slaughter_yoy.get(k, np.nan) for k in qkey]
    return m.reset_index().rename(columns={"index": "month"})


def quarterly_leadlag(mon, nbsq_q):
    m = mon.copy()
    m["q"] = pd.PeriodIndex(m.month, freq="M").asfreq("Q").astype(str)
    g = m.groupby("q").revised_10kt.agg(["sum", "count"])
    feed_q = g["sum"].where(g["count"] == 3)
    df = pd.DataFrame({"feed_q": feed_q})
    df["feed_yoy"] = pct(df.feed_q, df.feed_q.shift(4))
    df = df.join(nbsq_q[["slaughter_yoy", "inventory_yoy", "pork_yoy", "carcass_chg_kg"]], how="left")
    rows = []
    for target in ("slaughter_yoy", "pork_yoy", "inventory_yoy"):
        for k in range(0, 5):
            for label, start in (("2020Q1起", "2020Q1"), ("2022Q1起", "2022Q1")):
                x = df.feed_yoy
                y = df[target].shift(-k)
                d = pd.concat([x, y], axis=1).dropna()
                d = d[d.index >= start]
                if len(d) >= 6:
                    rows.append(dict(target=target, feed_leads_quarters=k, sample=label, n=len(d),
                                     corr=round(d.iloc[:, 0].corr(d.iloc[:, 1]), 3),
                                     mean_gap_pp=round((d.iloc[:, 0] - d.iloc[:, 1]).mean(), 2)))
    return df.reset_index().rename(columns={"index": "quarter"}).round(3), pd.DataFrame(rows)


def sign_turns(panel, nbsq_q):
    """Months in which each YoY series changed sign (3-month feed YoY to damp the Spring Festival)."""
    out = []
    series = {"猪料（修订值，3个月合计同比）": panel.set_index("month").revised_3m_yoy,
              "能繁母猪同比": panel.set_index("month").sow_yoy}
    for name, s in series.items():
        s = s.dropna()
        prev = None
        for k, v in s.items():
            sg = np.sign(v)
            if prev is not None and sg != 0 and sg != prev[1]:
                out.append(dict(series=name, period=k, direction="转正" if sg > 0 else "转负", value=round(v, 1),
                                prior_period=prev[0]))
            if sg != 0:
                prev = (k, sg)
    q = nbsq_q.slaughter_yoy.dropna()
    q = q[q.index >= "2019Q1"]
    prev = None
    for k, v in q.items():
        sg = np.sign(v)
        if prev is not None and sg != prev[1]:
            out.append(dict(series="统计局季度出栏同比", period=k, direction="转正" if sg > 0 else "转负",
                            value=round(v, 1), prior_period=prev[0]))
        prev = (k, sg)
    return pd.DataFrame(out)


def vintage_table(mon, rel):
    v = mon[mon.first_10kt.notna()][["month", "first_10kt", "revised_10kt", "revision_pct", "first_yoy",
                                     "revised_yoy"]].copy()
    v["yoy_revision_pp"] = v.revised_yoy - v.first_yoy
    r = rel[(rel.kind == "月度") & rel.period.str.match(r"^\d{4}-\d{2}(~\d{2})?$")].copy()
    r["month_end"] = pd.PeriodIndex(r.period.str[:7], freq="M").to_timestamp(how="end").normalize()
    r.loc[r.period.str.contains("~"), "month_end"] = pd.PeriodIndex(
        r.period[r.period.str.contains("~")].str[:5] + r.period[r.period.str.contains("~")].str[-2:],
        freq="M").to_timestamp(how="end").normalize()
    r["lag_days"] = (pd.to_datetime(r.release_date) - r.month_end).dt.days
    r = r[r.lag_days.between(0, 75)]
    lag = r.assign(year=r.period.str[:4]).groupby("year").lag_days.agg(["count", "median", "min", "max"])
    return v.round(2), lag.reset_index()


def stage_table(stage, sows_m, nbsq_q):
    rows = []
    st = stage.set_index("period")
    for per, (a, b) in WINDOWS.items():
        if per not in st.index:
            continue
        r = st.loc[per]
        months = pd.period_range(a, b, freq="M").astype(str)
        sy = sows_m.reindex(months).sow_yoy
        qs = sorted(set(pd.PeriodIndex(months, freq="M").asfreq("Q").astype(str)))
        nxt = [str(pd.Period(qs[-1], freq="Q") + i) for i in (1, 2)]
        def qyoy(keys, col):
            num = nbsq_q.reindex(keys)[col]
            den = nbsq_q.reindex([str(pd.Period(k, freq="Q") - 4) for k in keys])[col]
            if num.isna().any() or den.isna().any():
                return np.nan
            return pct(num.sum(), den.sum())
        rows.append(dict(
            period=per, window=f"{a}~{b}", release_date=r.release_date, pig_feed_yoy=r.pig_yoy,
            piglet_yoy=r.piglet_yoy, sow_feed_yoy=r.sow_yoy, finishing_yoy=r.finishing_yoy,
            sow_inv_yoy_end=round(sy.dropna().iloc[-1], 1) if sy.notna().any() else np.nan,
            sow_inv_yoy_avg=round(sy.mean(), 1) if sy.notna().any() else np.nan,
            sow_obs=int(sy.notna().sum()),
            slaughter_yoy_window=round(qyoy(qs, "hog_slaughter_q_wan"), 1),
            pork_yoy_window=round(qyoy(qs, "pork_output_q_wan_t"), 1),
            slaughter_yoy_next2q=round(qyoy(nxt, "hog_slaughter_q_wan"), 1),
            next2q=",".join(nxt),
            carcass_chg_kg=round(nbsq_q.reindex(qs).carcass_chg_kg.mean(), 2),
            quarters=",".join(qs), source_form=r.source_form, url=r.url))
    t = pd.DataFrame(rows)
    t["sow_feed_minus_sow_inv_pp"] = (t.sow_feed_yoy - t.sow_inv_yoy_avg).round(1)
    t["piglet_minus_finishing_pp"] = (t.piglet_yoy - t.finishing_yoy).round(1)
    t["sow_minus_finishing_pp"] = (t.sow_feed_yoy - t.finishing_yoy).round(1)
    nahs = dict(period="2026-07（全国畜牧总站，折全价）", window="2026-07~2026-07", release_date="2026-08-24",
                piglet_yoy=NAHS_2026_07["piglet"][1], sow_feed_yoy=NAHS_2026_07["sow"][1],
                finishing_yoy=NAHS_2026_07["finishing"][1], source_form="分析文章",
                url="https://pig.caaa.cn/html/pig_rd/pig_hydt/2026/0824/2482.html")
    nahs_p = dict(nahs, period="2026-07（全国畜牧总站，实物）", piglet_yoy=NAHS_2026_07["piglet"][0],
                  sow_feed_yoy=NAHS_2026_07["sow"][0], finishing_yoy=NAHS_2026_07["finishing"][0])
    extra = pd.DataFrame([nahs_p, nahs])
    sy = sows_m.sow_yoy.dropna()
    extra["sow_inv_yoy_end"] = round(sy[sy.index <= "2026-07"].iloc[-1], 1)
    extra["piglet_minus_finishing_pp"] = (extra.piglet_yoy - extra.finishing_yoy).round(1)
    extra["sow_minus_finishing_pp"] = (extra.sow_feed_yoy - extra.finishing_yoy).round(1)
    return pd.concat([t, extra], ignore_index=True)


def slaughter_projection(st):
    """Slaughter change in the two quarters after each published window per unit of physical piglet-feed
    change (windows where the two agree in sign), applied to the July 2026 piglet reading on both bases.
    The ratios are physical-basis, so the full-ration row overstates the decline if the past
    physical/full-ration gap was as wide as July 2026's."""
    h = st[st.slaughter_yoy_next2q.notna() & st.piglet_yoy.notna()]
    h = h[np.sign(h.piglet_yoy) == np.sign(h.slaughter_yoy_next2q)]
    ratio = h.slaughter_yoy_next2q / h.piglet_yoy
    rows = [dict(kind="历史窗口", period=p, piglet_yoy=x, slaughter_yoy=y, ratio=round(k, 3))
            for p, x, y, k in zip(h.period, h.piglet_yoy, h.slaughter_yoy_next2q, ratio)]
    for basis, feed in (("实物", NAHS_2026_07["piglet"][0]), ("折全价", NAHS_2026_07["piglet"][1])):
        for stat, k in (("最小", ratio.min()), ("中位", ratio.median()), ("最大", ratio.max())):
            rows.append(dict(kind=f"2026Q4-2027Q1 推算（比例{stat}）", period=f"2026-07 {basis}", piglet_yoy=feed,
                             slaughter_yoy=round(feed * k, 1), ratio=round(k, 3)))
    return pd.DataFrame(rows)


def company_table(comp):
    c = comp.dropna(subset=["value"]).copy()
    c = c[c.company.isin(["东瑞股份", "牧原股份"])]
    w = c.pivot_table(index=["company", "period"], columns="item", values="value", aggfunc="first").reset_index()
    rows = []
    for r in w.itertuples(index=False):
        d = r._asdict()
        name, per = d["company"], d["period"]
        if name == "东瑞股份":
            g = lambda k: d.get(k, np.nan)  # noqa: E731
            prod, ext, inv = g("饲料生产量"), g("饲料对外销售量"), g("饲料库存量")
            self_use = g("自产自用饲料")
            rows.append(dict(company=name, period=per, feed_t=prod, external_t=ext, feed_inventory_t=inv,
                             self_use_t=self_use, hogs_sold_wan=g("生猪销售量"), hog_inventory_wan=g("生猪库存量")))
        elif name == "牧原股份":
            rows.append(dict(company=name, period=per, feed_t=d.get("饲料产量", np.nan) * 1e4,
                             hogs_sold_wan=d.get("生猪出栏量", np.nan),
                             piglets_sold_wan=d.get("仔猪销售量", np.nan),
                             feed_capacity_t=d.get("饲料产能", np.nan) * 1e4))
    t = pd.DataFrame(rows).sort_values(["company", "period"]).reset_index(drop=True)
    dr = t.company == "东瑞股份"
    inv_prev = t.loc[dr, "feed_inventory_t"].shift(1)
    est = t.loc[dr, "feed_t"] - t.loc[dr, "external_t"] - (t.loc[dr, "feed_inventory_t"] - inv_prev)
    t.loc[dr, "self_use_t"] = t.loc[dr, "self_use_t"].fillna(est)
    noted = t.set_index(["company", "period"]).index.isin(
        c[c.item == "自产自用饲料"].set_index(["company", "period"]).index)
    t["self_use_basis"] = np.where(noted, "年报注释", np.where(dr, "生产量-对外销量-库存增加", "饲料产量（基本自用）"))
    t = t[t.feed_t.notna() | t.self_use_t.notna()].reset_index(drop=True)
    dr = t.company == "东瑞股份"
    t["feed_used_t"] = t.self_use_t.where(dr, t.feed_t)
    t["feed_kg_per_hog_sold"] = t.feed_used_t / (t.hogs_sold_wan * 1e4) * 1000
    t["feed_kg_per_finisher_sold"] = t.feed_used_t / ((t.hogs_sold_wan - t.piglets_sold_wan.fillna(0)) * 1e4) * 1000
    t["feed_yoy"] = t.groupby("company").feed_used_t.pct_change() * 100
    t["hogs_yoy"] = t.groupby("company").hogs_sold_wan.pct_change() * 100
    t["hog_inventory_yoy"] = t.groupby("company").hog_inventory_wan.pct_change() * 100
    t["feed_utilisation"] = t.feed_t / t.feed_capacity_t
    return t.round(3)


# ---------------------------------------------------------------------------
def charts(panel, annual, stages, vint, comp_t):
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title

    p = panel.copy()
    p["date"] = pd.PeriodIndex(p.month, freq="M").to_timestamp()

    # 1 monthly feed level + YoY vs sows / slaughter
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7.4), sharex=True, gridspec_kw=dict(height_ratios=[1, 1.1]))
    ax1.plot(p.date, p.revised_10kt, color=C["stock"], lw=1.8, label="修订值（官方图表读数）")
    f = p[p.first_10kt.notna()]
    ax1.scatter(f.date, f.first_10kt, s=16, color=C["spot"], zorder=3, label="首发值（当月月报）")
    ax1.set_ylabel("万吨/月")
    ax1.legend(loc="upper left")
    ax1.set_title("工业猪饲料月产量", loc="left", fontsize=11)
    ax2.axhline(0, color=C["grey"], lw=0.8)
    ax2.plot(p.date, p.revised_3m_yoy, color=C["stock"], lw=1.8, label="猪料同比（修订值，3个月合计）")
    ax2.plot(p.date, p.sow_yoy, "o-", ms=3, color=C["wens"], lw=1.2, label="能繁母猪同比（农业农村部；部分月份为统计局季末）")
    q = p.dropna(subset=["slaughter_q_yoy"]).drop_duplicates("quarter")
    ax2.step(q.date, q.slaughter_q_yoy, where="post", color=C["dark"], lw=1.2, label="出栏同比（统计局季度）")
    ax2.set_ylim(-45, 135)
    ax2.set_ylabel("%")
    ax2.legend(loc="upper right")
    ax2.set_title("同比：猪料长期快于母猪和出栏", loc="left", fontsize=11)
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    title(fig, "猪饲料能看到大方向，但增速长期偏离存栏",
          "2019-01 至 2026-06 月度猪料；2021-03 为插补，2026 年为当年图读数（未经年度修订）")
    source(fig, "中国饲料工业协会月报与半年/前三季度分析图表（像素读数，误差约±1%）；农业农村部能繁母猪；国家统计局季度出栏", y=-0.02)
    save(fig, "i07_feed_vs_herd.png")

    # 2 annual drift and feed per hog
    a = annual[annual.year >= 2019]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.4))
    x = np.arange(len(a))
    ax1.bar(x - 0.27, a.pig_yoy, 0.27, color=C["stock"], label="猪料同比")
    ax1.bar(x, a.slaughter_yoy, 0.27, color=C["dark"], label="出栏同比")
    ax1.bar(x + 0.27, a.pork_yoy, 0.27, color=C["spot"], label="猪肉产量同比")
    ax1.axhline(0, color=C["grey"], lw=0.8)
    ax1.set_xticks(x, a.year.astype(str))
    ax1.set_ylabel("%")
    ax1.legend(loc="upper left")
    ax1.set_title("年度同比", loc="left", fontsize=11)
    for i, g in enumerate(a.gap_vs_slaughter_pp):
        ax1.text(i, max(a.pig_yoy.iloc[i], a.slaughter_yoy.iloc[i], 0) + 2, f"{g:+.1f}" if abs(g) < 1 else f"{g:+.0f}",
                 ha="center", fontsize=8, color=C["wens"])
    ax2.plot(a.year, a.feed_kg_per_hog, "o-", color=C["stock"], lw=1.8)
    for yr, v in zip(a.year, a.feed_kg_per_hog):
        ax2.text(yr, v + 5, f"{v:.0f}", ha="center", fontsize=8)
    lo, mid, hi = whole_herd_need()
    ax2.axhspan(lo, hi, color=C["light"], alpha=0.6, label=f"全群折全价需求 {lo:.0f}–{hi:.0f} kg/头")
    ax2.set_ylim(100, 460)
    ax2.set_ylabel("kg/出栏头")
    ax2.legend(loc="upper left")
    ax2.set_title("每出栏一头猪对应的工业猪料（实物吨）", loc="left", fontsize=11)
    g = a.gap_vs_slaughter_pp
    kg = a.feed_kg_per_hog
    title(fig, f"猪料增速减出栏增速：在 {g.min():+.0f} 到 {g.max():+.0f} 个百分点之间跳动",
          f"红字为猪料同比减出栏同比（百分点）；每头工业料从 {kg.iloc[0]:.0f} kg 升到 {kg.iloc[-1]:.0f} kg，"
          "主要是商品料渗透率变化")
    source(fig, "中国饲料工业协会年度概况；国家统计局年度公报；需求区间为本文参数推算", y=-0.04)
    save(fig, "i07_drift.png")

    # 3 stage episodes
    s = stages[stages.period.isin(list(WINDOWS) + ["2026-07（全国畜牧总站，折全价）"])].copy()
    s["label"] = s.period.str.replace("（全国畜牧总站，折全价）", "\n畜牧总站折全价", regex=False)
    fig, ax = plt.subplots(figsize=(11.5, 4.8))
    x = np.arange(len(s))
    w = 0.16
    ax.bar(x - 2 * w, s.piglet_yoy, w, color=C["small"], label="仔猪料")
    ax.bar(x - w, s.sow_feed_yoy, w, color=C["wens"], label="母猪料")
    ax.bar(x, s.finishing_yoy, w, color=C["stock"], label="育肥料")
    ax.bar(x + w, s.sow_inv_yoy_avg.fillna(s.sow_inv_yoy_end), w, color=C["dark"], label="能繁母猪同比（窗口均值）")
    ax.bar(x + 2 * w, s.slaughter_yoy_window, w, color=C["grey"], label="同期出栏同比")
    ax.axhline(0, color=C["grey"], lw=0.8)
    ax.set_xticks(x, s.label, fontsize=8.5)
    ax.set_ylabel("%")
    ax.set_ylim(-45, 95)
    ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, 1.0))
    gap = s.sow_feed_minus_sow_inv_pp.dropna()
    title(fig, "分阶段猪料：顺序常对，幅度常错",
          f"仔猪料、母猪料每期都弱于育肥料；母猪料同比减能繁母猪同比在 {gap.min():+.0f} 到 {gap.max():+.0f} 个百分点之间")
    source(fig, "中国饲料工业协会年度/半年/前三季度分析与座谈会通报；全国畜牧总站（2026-08）；农业农村部；国家统计局", y=-0.06)
    save(fig, "i07_stages.png")

    # 4 vintage
    v = vint.copy()
    v["date"] = pd.PeriodIndex(v.month, freq="M").to_timestamp()
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(v.date, v.first_yoy, "o-", color=C["spot"], ms=4, label="首发同比（当月月报）")
    ax.plot(v.date, v.revised_yoy, "o-", color=C["stock"], ms=4, label="修订后同比（后来图表）")
    ax.axhline(0, color=C["grey"], lw=0.8)
    ax.set_ylabel("%")
    ax.legend(loc="upper right")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    rv, yr = v.revision_pct, v.yoy_revision_pp.dropna()
    title(fig, f"实时数据系统性偏低：首发值后来被上修 {rv.min():.1f}%–{rv.max():.1f}%",
          f"首发同比 = 当月初值 ÷ 上年终值，所以比修订后同比低 {yr.min():.1f}–{yr.max():.1f} 个百分点")
    source(fig, "中国饲料工业协会月报（首发）与后续分析图表（修订）", y=-0.04)
    save(fig, "i07_vintage.png")

    # 5 company
    c = comp_t[comp_t.feed_kg_per_hog_sold.notna()].copy()
    c["yr"] = c.period.astype(int)
    c["gap"] = c.feed_yoy - c.hogs_yoy
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw=dict(width_ratios=[1.2, 1]))
    for k, (name, col) in enumerate((("东瑞股份", C["gd"]), ("牧原股份", C["muyuan"]))):
        d = c[c.company == name]
        ax1.plot(d.yr, d.feed_kg_per_hog_sold, "o-", color=col, lw=1.8, label=name)
        for yr, val in zip(d.yr, d.feed_kg_per_hog_sold):
            ax1.text(yr, val + 6, f"{val:.0f}", ha="center", fontsize=8, color=col)
        g = d.dropna(subset=["gap"])
        ax2.bar(g.yr + (k - 0.5) * 0.38, g.gap, 0.38, color=col, label=name)
    ax1.axhspan(lo, hi, color=C["light"], alpha=0.6, label="全群折全价需求区间")
    ax1.set_ylim(250, 460)
    ax1.set_ylabel("kg 饲料 / 头出栏")
    ax1.set_title("每出栏一头猪对应的自产饲料", loc="left")
    ax1.legend(loc="upper right", fontsize=8)
    ax2.axhline(0, color=C["grey"], lw=0.8)
    ax2.set_ylabel("百分点")
    ax2.set_title("饲料同比减出栏同比", loc="left")
    ax2.legend(loc="lower left", fontsize=8)
    for ax in (ax1, ax2):
        ax.set_xticks(sorted(c.yr.unique()))
    gp = c.gap.dropna()
    title(fig, f"一体化猪企：单头用料落在生物学区间，但年度增速差在 {gp.min():+.0f} 到 {gp.max():+.0f} 个百分点",
          "东瑞为年报产销表推算的自用料；牧原为 ESG 报告与可转债募集说明书的饲料产量（基本自用），2024 年出栏含 566 万头仔猪")
    source(fig, "东瑞股份年报；牧原股份 ESG 报告、可转债募集说明书；本文推算", y=-0.04)
    save(fig, "i07_company.png")


# ---------------------------------------------------------------------------
def main():
    mon, stage, annual, rel, sows, nbsq, bull, comp = load()
    sows_m = sow_series(sows, nbsq)
    nbsq_q = quarterly_nbs(nbsq)

    a = annual_table(annual, bull, sows_m, mon)
    write(a, "ft_annual.csv")
    panel = monthly_panel(mon, sows_m, nbsq_q)
    write(panel.round(2), "ft_monthly.csv")
    fq, ll = quarterly_leadlag(mon, nbsq_q)
    write(fq, "ft_quarterly.csv")
    write(ll, "ft_leadlag.csv")
    turns = sign_turns(panel, nbsq_q)
    write(turns, "ft_turns.csv")
    vint, lag = vintage_table(mon, rel)
    write(vint, "ft_vintage.csv")
    write(lag, "ft_release_lag.csv")
    st = stage_table(stage, sows_m, nbsq_q)
    write(st, "ft_stages.csv")
    proj = slaughter_projection(st)
    write(proj, "ft_projection.csv")
    steady, grid, weight = model_tables(nbsq_q)
    write(steady, "ft_model_steady.csv")
    write(grid, "ft_model_july2026.csv")
    write(weight, "ft_weight_effect.csv")
    comp_t = company_table(comp)
    write(comp_t, "ft_company.csv")
    charts(panel, a, st, vint, comp_t)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(a.to_string())
    print(ll.to_string())
    print(turns.to_string())
    print(vint.to_string())
    print(lag.to_string())
    print(st.drop(columns=["url"]).to_string())
    print(proj.to_string())
    print(steady.to_string())
    print(weight.to_string())
    print(grid[grid.coverage_chg == 0].to_string())
    print(comp_t.to_string())


if __name__ == "__main__":
    main()
