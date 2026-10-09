"""Test the two-phase framework on the ASF cycle (2018-2021).

Phase 1 (expectation/elasticity): did the market pay most for small caps and for big announced growth?
Phase 2 (realization/persistence): did later returns line up with delivered output and profits?

All inputs are files produced earlier in the pipeline; plan figures come from the subagent evidence
tables (each row has a cninfo URL). With ~14 companies, rank correlations are descriptive, not tests.

Outputs (data/processed):
  two_phase_panel.csv        one row per company
  two_phase_correlations.csv Spearman rho for the framework's claims
  plan_realization.csv       first public plan / last revision / actual, per company-year
  ops_at_peaks.csv           monthly operating data known on each stock's peak date
"""
import re

import numpy as np
import pandas as pd

from common import PROC, ROOT

sd = pd.read_csv(PROC / "stock_daily.csv", dtype={"code": str})
sd = sd[sd["date"] <= "2026-10-08"]
fin = pd.read_csv(PROC / "fin_quarterly.csv", dtype={"code": str})
ev = pd.read_csv(PROC / "hist_event_returns.csv", dtype={"code": str})
pk = pd.read_csv(PROC / "hist_peaks.csv", dtype={"code": str})
ms = pd.read_csv(PROC / "monthly_sales.csv", dtype={"code": str})
plans = pd.concat([pd.read_csv(ROOT / "research/history_plans/plans_vs_actuals_A.csv", dtype={"code": str}),
                   pd.read_csv(ROOT / "research/history_plans/plans_vs_actuals_B.csv", dtype={"code": str})])
plans["code"] = plans["code"].str.zfill(6)
plans = plans[~((plans["metric"] == "plan_sales") & ~plans["unit"].fillna("").str.startswith("万头"))]
plans = plans[~plans["unit"].fillna("").str.contains("母猪|产床")]


def expand_multi_year(df):
    """Rows like target_period='2019-2022', scope='2019年350-360万；2020年800-1000万…' -> one row per year."""
    keep, extra = [], []
    pat = r"(20\d{2})年(?:确保|冲击|约|挑战|超过)?\s*([\d\.]+)(?:\s*[-—~]\s*([\d\.]+))?\s*万"
    for _, r in df.iterrows():
        tp = str(r["target_period"])
        if r["metric"] == "plan_sales" and re.fullmatch(r"20\d{2}-20\d{2}", tp):
            for y, lo, hi in re.findall(pat, str(r["scope"])):
                rr = r.copy()
                rr["target_period"], rr["value_low"] = y, float(lo)
                rr["value_high"] = float(hi) if hi else np.nan
                extra.append(rr)
        else:
            keep.append(r)
    return pd.DataFrame(keep + extra)


plans = expand_multi_year(plans)

PIG = ["002714", "300498", "002157", "002124", "000876", "002477", "002567", "600975", "603363",
       "002548", "002385", "002100", "000735", "000048"]
NAMES = {"002714": "牧原", "300498": "温氏", "002157": "正邦", "002124": "天邦", "000876": "新希望",
         "002477": "雏鹰", "002567": "唐人神", "600975": "新五丰", "603363": "傲农", "002548": "金新农",
         "002385": "大北农", "002100": "天康", "000735": "罗牛山", "000048": "京基智农"}
# Later fate, from company announcements (see report sources); used only as an outcome label.
FATE = {"002477": "2019-08-20 决定面值退市，2019-10-15 最后交易日",
        "002157": "2023-07 上市公司重整受理（控股股东2022-10），2023-12 执行完毕、双胞胎入主",
        "603363": "2024-12 重整执行完毕", "002124": "2026 预重整中（投资人9/18解约）"}


def hfq(code):
    s = sd[sd["code"] == code].set_index("date")
    c = s["close_tx_hfq"] if "close_tx_hfq" in s and s["close_tx_hfq"].notna().any() else s["close_hfq"]
    return c.dropna()


def raw_close(code):
    s = sd[sd["code"] == code].set_index("date")["close_raw"].dropna()
    return s


def shares_at(code, date):
    f = fin[(fin["code"] == code) & (fin["report_date"] <= date)].dropna(subset=["SHARE_CAPITAL"])
    return float(f.sort_values("report_date")["SHARE_CAPITAL"].iloc[-1]) if len(f) else np.nan


def mcap(code, date):
    c = raw_close(code)
    c = c[c.index <= date]
    return float(c.iloc[-1]) * shares_at(code, date) / 1e8 if len(c) else np.nan


def ret(code, a, b):
    s = hfq(code)
    s0, s1 = s[s.index <= a], s[s.index <= b]
    if s0.empty or s1.empty or s1.index[-1] < a:
        return np.nan
    return float(s1.iloc[-1] / s0.iloc[-1] - 1)


def annual_np(code, year):
    f = fin[(fin["code"] == code) & (fin["report_date"] == f"{year}-12-31")]
    return float(f["PARENT_NETPROFIT"].iloc[0]) / 1e8 if len(f) and pd.notna(f["PARENT_NETPROFIT"].iloc[0]) else np.nan


xq = pd.read_csv(PROC / "xinwufeng_quarterly.csv", dtype={"code": str})
XQ_FY = {(r["code"], int(r["year"])): float(r["ytd_production"]) for _, r in xq[xq["ytd_end_month"] == 12].iterrows()}


def annual_sales(code, year):
    m = ms[(ms["code"] == code) & (ms["month_key"].str[:4] == str(year))]
    cov = m["months_covered"].fillna(1).sum()
    if len(m):
        return float(m["total_heads"].sum()), int(cov)
    if (code, year) in XQ_FY:  # 新五丰 only publishes quarterly YTD production before 2022
        return XQ_FY[(code, year)], 12
    return np.nan, 0


# ------------------------------------------------------------------ plan realization table
pr = []
for (code, tp), g in plans[plans["metric"].isin(["plan_sales", "actual_sales"])].groupby(["code", "target_period"]):
    if not str(tp).isdigit() or not (2018 <= int(tp) <= 2022):
        continue
    p = g[(g["metric"] == "plan_sales") & g["value_low"].notna()].sort_values("disclosed_date")
    p = p[~p["scope"].fillna("").str.contains("能繁")]
    a = g[(g["metric"] == "actual_sales") & g["value_low"].notna()].sort_values("disclosed_date")
    if p.empty and a.empty:
        continue
    mid = lambda r: np.nanmean([r["value_low"], r["value_high"]]) if pd.notna(r["value_high"]) else r["value_low"]
    first = p.iloc[0] if len(p) else None
    last_in_year = p[p["disclosed_date"] <= f"{tp}-12-31"]
    last = last_in_year.iloc[-1] if len(last_in_year) else None
    act_sum, cov = annual_sales(code, int(tp))
    act_doc = a.iloc[0]["value_low"] if len(a) else np.nan
    act = act_sum if cov == 12 else act_doc
    asof = p[p["disclosed_date"] <= "2019-04-30"] if int(tp) == 2019 else p.iloc[0:0]
    pr.append(dict(code=code, name=NAMES.get(code, g["company"].iloc[0]), year=int(tp),
                   plan_asof_2019_04_30=mid(asof.iloc[-1]) if len(asof) else np.nan,
                   plan_asof_date=asof.iloc[-1]["disclosed_date"] if len(asof) else None,
                   first_plan_mid=mid(first) if first is not None else np.nan,
                   first_plan_date=first["disclosed_date"] if first is not None else None,
                   first_plan_scope=first["scope"] if first is not None else None,
                   first_plan_url=first["url"] if first is not None else None,
                   last_plan_mid=mid(last) if last is not None else np.nan,
                   last_plan_date=last["disclosed_date"] if last is not None else None,
                   n_plan_versions=len(p), actual=act,
                   actual_source="月度简报12个月加总" if cov == 12 else "公告/年报披露值"))
pr = pd.DataFrame(pr)
pr["actual_vs_first"] = pr["actual"] / pr["first_plan_mid"]
pr["actual_vs_last"] = pr["actual"] / pr["last_plan_mid"]
pr.to_csv(PROC / "plan_realization.csv", index=False)

# ------------------------------------------------------------------ company panel
rows = []
for code in PIG:
    s18, _ = annual_sales(code, 2018)
    s19, _ = annual_sales(code, 2019)
    s20, _ = annual_sales(code, 2020)
    s21, _ = annual_sales(code, 2021)
    p = pr[pr["code"] == code].set_index("year")
    g = lambda y, c: float(p.loc[y, c]) if y in p.index and pd.notna(p.loc[y, c]) else np.nan
    base18 = s18 if pd.notna(s18) and s18 > 0 else g(2018, "actual")
    pkr = pk[pk["code"] == code]
    peak_close = pkr["peak_close_date"].iloc[0] if len(pkr) else None
    h = hfq(code)
    after = h[h.index >= peak_close] if peak_close else h
    low_after = after.min() if len(after) else np.nan
    np19, np20, np21 = annual_np(code, 2019), annual_np(code, 2020), annual_np(code, 2021)
    rows.append(dict(
        code=code, name=NAMES[code],
        mcap_2018_12_28=mcap(code, "2018-12-28"), mcap_2019_04_30=mcap(code, "2019-04-30"),
        mcap_2020_08_31=mcap(code, "2020-08-31"),
        r_phase1_A_B=ret(code, "2018-08-02", "2019-04-30"), r_B=ret(code, "2018-12-28", "2019-04-30"),
        r_C=ret(code, "2019-04-30", "2019-11-08"), r_D=ret(code, "2019-11-08", "2020-08-31"),
        r_E=ret(code, "2020-08-31", "2021-02-26"),
        r_phase2_C_D_E=ret(code, "2019-04-30", "2021-02-26"), r_F_G=ret(code, "2021-02-26", "2022-04-29"),
        sales_2018=base18, sales_2019=s19, sales_2020=s20, sales_2021=s21,
        plan2019_first=g(2019, "first_plan_mid"), plan2019_first_date=p.loc[2019, "first_plan_date"] if 2019 in p.index else None,
        plan2019_asof=g(2019, "plan_asof_2019_04_30"), plan2019_asof_date=p.loc[2019, "plan_asof_date"] if 2019 in p.index else None,
        plan2020_first=g(2020, "first_plan_mid"), plan2021_first=g(2021, "first_plan_mid"),
        plan2021_first_date=p.loc[2021, "first_plan_date"] if 2021 in p.index else None,
        np_2019=np19, np_2020=np20, np_2021=np21,
        peak_close_date=peak_close, drawdown_peak_to_low_through_2026=float(low_after / after.iloc[0] - 1) if len(after) else np.nan,
        low_date_through_2026=after.idxmin() if len(after) else None,
        fate=FATE.get(code, "")))
pn = pd.DataFrame(rows)
pn["planned_growth_2019"] = pn["plan2019_first"] / pn["sales_2018"] - 1
pn["planned_growth_2020_vs_2018"] = pn["plan2020_first"] / pn["sales_2018"] - 1
pn["real_2019_vs_plan"] = pn["sales_2019"] / pn["plan2019_first"]
pn["real_2020_vs_plan"] = pn["sales_2020"] / pn["plan2020_first"]
pn["real_2021_vs_plan"] = pn["sales_2021"] / pn["plan2021_first"]
pn["growth_2020_vs_2018"] = pn["sales_2020"] / pn["sales_2018"] - 1
pn["growth_2021_vs_2018"] = pn["sales_2021"] / pn["sales_2018"] - 1
pn["mcap_per_head_2018_yuan"] = pn["mcap_2018_12_28"] * 1e8 / (pn["sales_2018"] * 1e4)
pn["mcap_per_head_2019plan_yuan"] = pn["mcap_2018_12_28"] * 1e8 / (pn["plan2019_first"] * 1e4)
pn["mcap_per_head_2019asof_yuan"] = pn["mcap_2018_12_28"] * 1e8 / (pn["plan2019_asof"] * 1e4)
pn["mcap_per_head_2019actual_yuan"] = pn["mcap_2018_12_28"] * 1e8 / (pn["sales_2019"] * 1e4)
pn["planned_growth_2019_asof"] = pn["plan2019_asof"] / pn["sales_2018"] - 1
dr = fin[fin["report_date"] == "2018-12-31"].set_index("code")["debt_ratio"]
pn["debt_ratio_2018"] = pn["code"].map(dr)
pn["np19_20_over_mcap_0430"] = (pn["np_2019"] + pn["np_2020"]) / pn["mcap_2019_04_30"]
pn["np19_21_over_mcap_0430"] = (pn["np_2019"] + pn["np_2020"] + pn["np_2021"]) / pn["mcap_2019_04_30"]
pn.to_csv(PROC / "two_phase_panel.csv", index=False)

# ------------------------------------------------------------------ rank correlations
tests = [("r_B", "mcap_2018_12_28", "阶段一：小市值涨得更多？（预期负相关）"),
         ("r_B", "planned_growth_2019", "阶段一：计划增速越高涨得越多？"),
         ("r_phase1_A_B", "mcap_2018_12_28", "阶段一（含疫情冲击段）：市值"),
         ("r_B", "mcap_per_head_2018_yuan", "阶段一：每头（2018实际出栏）市值越低涨得越多？"),
         ("r_B", "mcap_per_head_2019plan_yuan", "阶段一：每头（2019首个计划）市值越低涨得越多？"),
         ("r_B", "mcap_per_head_2019asof_yuan", "阶段一：每头（截至4/30最新计划）市值越低涨得越多？"),
         ("r_B", "mcap_per_head_2019actual_yuan", "对照：每头（2019事后实际）市值"),
         ("r_B", "planned_growth_2019_asof", "阶段一：截至4/30计划增速"),
         ("r_B", "debt_ratio_2018", "阶段一：杠杆越高涨得越多？"),
         ("r_phase2_C_D_E", "real_2020_vs_plan", "阶段二：2020兑现率越高后续越强？"),
         ("r_phase2_C_D_E", "growth_2020_vs_2018", "阶段二：实际出栏增长越高后续越强？"),
         ("r_phase2_C_D_E", "np19_20_over_mcap_0430", "阶段二：利润兑现/起点市值越高后续越强？"),
         ("r_E", "growth_2021_vs_2018", "扩张兑现段：2021出栏增长"),
         ("r_E", "real_2021_vs_plan", "扩张兑现段：2021兑现率"),
         ("r_phase2_C_D_E", "r_B", "阶段一涨幅与阶段二涨幅（均值回归？）")]
out = []
for y, x, label in tests:
    d = pn[[y, x]].dropna()
    rho = d[y].rank().corr(d[x].rank()) if len(d) >= 5 else np.nan
    out.append(dict(test=label, y=y, x=x, n=len(d), spearman_rho=rho))
pd.DataFrame(out).to_csv(PROC / "two_phase_correlations.csv", index=False)

# ------------------------------------------------------------------ operating data known at peak dates
ops = []
for _, r in pk[pk["code"].isin(PIG)].iterrows():
    code, d = r["code"], r["peak_close_date"]
    m = ms[(ms["code"] == code) & (ms["ann_date"] <= d)].sort_values("month_key")
    if m.empty:
        continue
    last3 = m.tail(3)
    prev = ms[(ms["code"] == code) & ms["month_key"].isin(
        [f"{int(k[:4]) - 1}{k[4:]}" for k in last3["month_key"]])]
    yoy = last3["total_heads"].sum() / prev["total_heads"].sum() - 1 if len(prev) == len(last3) and prev["total_heads"].sum() > 0 else np.nan
    ops.append(dict(code=code, name=NAMES[code], peak_close_date=d, last_month_known=m["month_key"].iloc[-1],
                    last3m_heads=last3["total_heads"].sum(), last3m_yoy=yoy,
                    last_price=m["price"].dropna().iloc[-1] if m["price"].notna().any() else np.nan))
pd.DataFrame(ops).to_csv(PROC / "ops_at_peaks.csv", index=False)

pd.set_option("display.width", 250)
print(pn[["name", "mcap_2018_12_28", "mcap_per_head_2018_yuan", "debt_ratio_2018", "r_B", "planned_growth_2019", "r_C", "r_D", "r_E", "r_phase2_C_D_E",
          "real_2019_vs_plan", "real_2020_vs_plan", "real_2021_vs_plan", "growth_2020_vs_2018",
          "np19_20_over_mcap_0430", "peak_close_date", "drawdown_peak_to_low_through_2026"]].round(2).to_string(index=False))
print(pd.DataFrame(out).round(2).to_string(index=False))
print(pd.DataFrame(ops).round(2).to_string(index=False))
