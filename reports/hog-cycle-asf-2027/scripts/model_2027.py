"""2027 scenario: national average live-hog price 18 元/kg for the year (given premise).

Hog margin per kg = national price x (1 + regional premium) + channel premium - full cost.
Hog profit = fattening heads x weight x margin; piglet profit = piglet heads x piglet margin.
Parent earnings = (hog profit + piglet profit) x attributable share + other segments (not modelled = 0).
Scenario P/E = current market cap / parent earnings. A farming spread is not parent profit, and neither
is a share-price gain; this file only produces earnings power under stated assumptions.

Labels in the input table: 事实 (disclosed), 目标 (management target), 假设 (research assumption).
Companies without a disclosed full cost get no scenario profit; instead the cost hurdle that would
make the current market cap equal to 8x scenario earnings is reported.
"""
import numpy as np
import pandas as pd

from common import PROC

sc = pd.read_csv(PROC / "screen_snapshot.csv", dtype={"code": str})
ms = pd.read_csv(PROC / "monthly_sales.csv", dtype={"code": str})
fin = pd.read_csv(PROC / "fin_quarterly.csv", dtype={"code": str})
nx = pd.read_csv(PROC / "nxin_price_wide.csv")
fut = pd.read_csv(PROC / "futures_lh_daily.csv")

# ------------------------------------------------------------------ national price paths (avg 18)
snap = fut[fut["trade_date"] == "2026-10-08"].set_index("contract")
s = lambda c: float(snap.loc[c, "settle"]) / 1000
q1, q2, q3 = (s("LH2701") + s("LH2703")) / 2, s("LH2705"), (s("LH2707") + s("LH2709")) / 2
q4 = q3 * 1.02  # LH2711 not listed yet: assumed Q4 = Q3 x 1.02
curve = np.array([q1, q2, q3, q4])
PATHS = {
    "P1 全年持平": np.array([18.0, 18.0, 18.0, 18.0]),
    "P2 后高": np.array([14.5, 17.0, 20.0, 20.5]),
    "P3 前高后落": np.array([19.0, 20.0, 18.0, 15.0]),
    "P4 期货曲线形状放大": curve * 18.0 / curve.mean(),
    "P5 V型冲高": np.array([13.0, 18.0, 23.0, 18.0]),
}
paths = pd.DataFrame({k: v for k, v in PATHS.items()}, index=["Q1", "Q2", "Q3", "Q4"]).T
paths["avg"] = paths.mean(axis=1)
paths.loc["期货曲线原值(2026-10-08结算)"] = list(curve) + [curve.mean()]
paths.to_csv(PROC / "model_price_paths.csv")

# ------------------------------------------------------------------ empirical inputs
nx["m"] = pd.to_datetime(nx["week_label"]).dt.strftime("%Y-%m")
nat = nx.groupby("m")["全国"].mean()


def regional_premium(code, start="2025-10", end="2026-09"):
    m = ms[(ms["code"] == code) & ms["price"].notna() & (ms["month_key"] >= start) & (ms["month_key"] <= end)]
    if m.empty:
        return np.nan, 0
    r = m["price"].values / nat.reindex(m["month_key"]).values - 1
    return float(np.nanmean(r)), int(np.isfinite(r).sum())


def parent_share(code):
    f = fin[(fin["code"] == code) & fin["report_date"].isin(["2023-12-31", "2024-12-31", "2025-12-31"])]
    f = f[(f["NETPROFIT"] > 0) & (f["PARENT_NETPROFIT"] > 0)]
    return float((f["PARENT_NETPROFIT"] / f["NETPROFIT"]).mean()) if len(f) else np.nan


def season(code):
    m = ms[(ms["code"] == code) & (ms["month_key"].str[:4] == "2025")]
    if m["months_covered"].sum() < 12:
        return np.array([0.25] * 4)
    q = m.assign(q=((m["month_key"].str[5:7].astype(int) - 1) // 3)).groupby("q")["total_heads"].sum()
    return (q / q.sum()).reindex(range(4)).fillna(0.25).values


def interest_per_kg(code, heads_wan):
    f = fin[(fin["code"] == code) & (fin["report_date"] == "2026-06-30")]
    if f.empty or pd.isna(f["FE_INTEREST_EXPENSE"].iloc[0]) or not heads_wan:
        return np.nan
    return float(f["FE_INTEREST_EXPENSE"].iloc[0]) * 2 / (heads_wan * 1e4 * 120)


# ------------------------------------------------------------------ company assumptions
# V: 2027 fattening heads (万头) bear/base/bull; P: piglets (万头); C: 2027 avg full cost bear/base/bull (元/kg)
# basis strings say what each number rests on.
A = [
    # code, V(bear,base,bull), W, piglets, C(bear,base,bull), basis
    ("002714", (7000, 7500, 8000), 120, 1000, (11.8, 11.3, 11.0),
     "量：2026商品猪指引7500-8100、能繁9月计划<300万头（目标/事实）→2027取7500（假设）；重：政策降体重取120kg（假设）；仔猪：2025年1-9月1157万头，2025-08后不再披露，取1000万（假设）；成本：2026-07为11.5（事实），全年目标≤11.5（目标）"),
    ("300498", (3300, 3500, 3700), 120, 0, (12.2, 11.7, 11.4),
     "量：2026年1-9月肉猪年化3535万（事实）；成本：8月<12.0、2026目标11.8（事实/目标）；黄羽鸡等未建模"),
    ("000876", (1350, 1450, 1550), 120, 140, (12.8, 12.3, 11.9),
     "量：2026目标1600万全口径、商品猪年化1431万（目标/事实）；成本：运营场线12.0不含闲置（<1元）→全口径取12.3（假设）；饲料未建模"),
    ("002100", (330, 365, 390), 120, 100, (12.3, 11.8, 11.5),
     "量：2026目标475万（天康315+羌都160）含仔猪，按2021年肥猪占比约77%折算（假设）；成本：6月11.8、目标<12（事实/目标）；归属比例按羌都49%少数股东折算"),
    ("001201", (140, 160, 175), 115, 40, (13.5, 12.9, 12.5),
     "量：2026目标200万（150肉猪+50猪苗等），能繁9.2万持平（事实）；成本：7月13.8，2027目标<12.5（事实/目标），基准取中间偏目标12.9（假设）；售价另按内销/出口拆分"),
    ("000048", (190, 210, 225), 120, 0, (13.3, 12.6, 12.0),
     "量：2026年1-9月商品肥猪年化208万（事实）；成本：3月13.3、目标12.0（事实/目标），基准12.6（假设）"),
    ("605296", (340, 370, 400), 120, 0, (12.1, 11.7, 11.4),
     "量：2026目标350万（目标）；成本：7月12.0、目标11.5（事实/目标）"),
    ("603477", (390, 430, 470), 120, 0, (12.5, 12.0, 11.6),
     "量：2026年1-9月商品肥猪年化427万（事实）；成本：7月<12.4、目标12.0（事实/目标）"),
    ("002567", (320, 360, 400), 120, 150, (12.8, 12.2, 11.8),
     "量：2026目标500万含仔猪约150万（目标/推算）；成本：Q1营业总成本12.66、Q2环比-0.8（事实），基准12.2（假设）"),
    ("002385", (360, 400, 430), 120, 0, (12.4, 11.9, 11.6),
     "量：2026年1-8月商品肥猪年化396万（事实）；成本：8月略低于12（事实）；饲料未建模"),
    ("603363", (120, 150, 170), 120, 100, (13.3, 12.6, 12.2),
     "量：2026目标出栏240万，肥猪占比未披露，按60%（假设）；成本：实际未披露，目标12.25（目标），基准12.6（假设，低可信）"),
    ("002124", (380, 450, 500), 120, 250, (13.2, 12.5, 12.2),
     "量：2026年1-8月肥猪年化487万（推算）、目标630万含仔猪；成本：H1 12.65、目标12.26（事实/目标）；预重整中，股东权益可能被稀释"),
    ("002548", (70, 85, 95), 120, 70, (13.2, 12.6, 12.3),
     "量：2026年1-8月商品猪年化80万（推算）、仔猪约70万；成本：4月12.77、目标12.5（事实/目标）"),
    ("002840", (200, 230, 260), 120, 0, (np.nan, np.nan, np.nan),
     "成本未披露：不计算情景利润，只给成本门槛"),
    ("600975", (290, 320, 350), 120, 250, (np.nan, np.nan, np.nan),
     "成本未披露（只有同比降幅）：不计算情景利润，只给成本门槛"),
    ("002157", (420, 500, 600), 120, 400, (np.nan, np.nan, np.nan),
     "成本与商品猪拆分未披露：不计算情景利润，只给成本门槛"),
]
PIGLET_MARGIN = {"bear": 80.0, "base": 150.0, "bull": 250.0}  # 元/头，18元年份的仔猪毛利（假设）
# Starting (2026H2) all-in cost where the disclosed figure is on a different basis than the 2027 assumption
COST0_OVERRIDE = {
    "000876": (12.5, "运营场线12.0（不含闲置）+闲置影响取0.5（公司称<1元，取中值，假设）"),
    "002567": (12.26, "Q1营业总成本12.66与Q2（环比-0.8）推算值的均值（推算）"),
    "603363": (13.0, "H1养殖毛利率-18.92%、均价约10.5元反推营业成本约12.5，加期间费用约0.5（推算+假设）"),
}
CASES = ["bear", "base", "bull"]

# Dongrui channel model: blended = national x (1+d) + s x e
# d: domestic price premium over the national average (2025 +2.0%, 2026Q1 +2.6%; 2019-20 Guangdong ran ~7% over national)
# s: export share by weight (2026 HK quota 21.5万头 + ~4万 non-quota exports vs ~160万 fattening hogs in 2027 ≈ 16%)
# e: export minus domestic price (2026H1 1.10, 2025 1.82, 2023 ~4, 2022 5.40, 2019-21 9-12)
DONGRUI = {"bear": dict(d=0.01, s=0.12, e=1.1), "base": dict(d=0.03, s=0.16, e=2.5), "bull": dict(d=0.08, s=0.22, e=4.0)}

inp = []
for code, V, W, PIG, C, basis in A:
    row = sc[sc["code"] == code].iloc[0]
    r, n_r = regional_premium(code)
    ps_emp = parent_share(code)
    use_emp = code != "002100" and pd.notna(ps_emp) and 0.75 <= ps_emp <= 1.0
    ps = ps_emp if use_emp else float(row["parent_share_hog"])
    if code in COST0_OVERRIDE:
        row = row.copy()
        row["cost_latest_kg"] = COST0_OVERRIDE[code][0]
    inp.append(dict(code=code, name=row["name"], mcap_yi=row["mcap_yi"], V_bear=V[0], V_base=V[1], V_bull=V[2], W=W,
                    piglets=PIG, C_bear=C[0], C_base=C[1], C_bull=C[2], cost_latest=row["cost_latest_kg"],
                    regional_premium=0.0 if code == "001201" else (r if pd.notna(r) else 0.0), regional_premium_months=n_r,
                    parent_share=ps, parent_share_source="2023-2025盈利年份归母/净利润均值" if use_emp else "手工（实测值缺失或失真，见筛选输入表）",
                    cost_latest_basis=COST0_OVERRIDE[code][1] if code in COST0_OVERRIDE else row["cost_def"],
                    season=season(code), interest_per_kg=interest_per_kg(code, row["run_rate_2026_wan"]),
                    run_rate_2026=row["run_rate_2026_wan"], last_price=row["last_price"], basis=basis))
inp = pd.DataFrame(inp)


def realized(code, nat_q, case, r):
    if code == "001201":
        p = DONGRUI[case]
        return nat_q * (1 + p["d"]) + p["s"] * p["e"]
    return nat_q * (1 + r)


res = []
for _, c in inp.iterrows():
    for pname, nat_q in PATHS.items():
        for case in CASES:
            V, Cy = c[f"V_{case}"], c[f"C_{case}"]
            vol_q = V * c["season"]
            px_q = realized(c["code"], nat_q, case, c["regional_premium"])
            px_avg = float((px_q * vol_q).sum() / vol_q.sum())
            if np.isnan(Cy):
                hog = np.nan
                m_kg = np.nan
            else:
                # cost glides linearly from the latest disclosed level (2026H2) to the 2027 assumption by Q4,
                # anchored so the annual volume-weighted mean equals the 2027 assumption
                c0 = c["cost_latest"] if pd.notna(c["cost_latest"]) else Cy
                glide = np.array([0.375, 0.125, -0.125, -0.375]) * (c0 - Cy) + Cy
                m_q = px_q - glide
                hog = float((vol_q * 1e4 * c["W"] * m_q).sum() / 1e8)
                m_kg = float((vol_q * m_q).sum() / vol_q.sum())
            pig = c["piglets"] * 1e4 * PIGLET_MARGIN[case] / 1e8
            parent = (hog + pig) * c["parent_share"] if pd.notna(hog) else np.nan
            # cost hurdle: full cost at which 8 x parent earnings = market cap (flat 18 path, base volume)
            denom = V * 1e4 * c["W"]
            hurdle = (px_avg - (c["mcap_yi"] / 8 / c["parent_share"] - pig) * 1e8 / denom) if denom else np.nan
            res.append(dict(code=c["code"], name=c["name"], path=pname, case=case, nat_avg=float(nat_q.mean()),
                            realized_px=px_avg, cost_2027=Cy, margin_kg=m_kg, margin_head=m_kg * c["W"] if pd.notna(m_kg) else np.nan,
                            fattening_wan=V, hog_profit_yi=hog, piglet_profit_yi=pig, parent_share=c["parent_share"],
                            parent_earnings_yi=parent, mcap_yi=c["mcap_yi"],
                            scenario_pe=c["mcap_yi"] / parent if parent and parent > 0 else np.nan,
                            earnings_yield=parent / c["mcap_yi"] if pd.notna(parent) else np.nan,
                            cost_hurdle_8x=hurdle))
res = pd.DataFrame(res)
res.to_csv(PROC / "model_results.csv", index=False)

# ------------------------------------------------------------------ what the current market cap prices in
# implied flat national price at which current mcap = k x parent earnings (base volumes and costs, base piglet margin);
# one-off value of an 18-yuan year = excess hog profit over a 14-yuan "normal" year, as % of market cap
val = []
for _, c in inp.iterrows():
    if np.isnan(c["C_base"]):
        continue
    W, V, ps, pig = c["W"], c["V_base"], c["parent_share"], c["piglets"] * 1e4 * PIGLET_MARGIN["base"] / 1e8
    kg = V * 1e4 * W / 1e8  # 亿 kg-equivalent: profit (亿元) per 1 元/kg of margin
    row = dict(code=c["code"], name=c["name"], mcap_yi=c["mcap_yi"], profit_per_yuan_kg_yi=kg * ps,
               profit_per_yuan_pct_mcap=kg * ps / c["mcap_yi"])
    for k in (10, 15):
        need_margin = (c["mcap_yi"] / k / ps - pig) / kg
        px_real = c["C_base"] + need_margin
        if c["code"] == "001201":
            p = DONGRUI["base"]
            nat_imp = (px_real - p["s"] * p["e"]) / (1 + p["d"])
        else:
            nat_imp = px_real / (1 + c["regional_premium"])
        row[f"implied_national_px_{k}x"] = nat_imp
    row["excess_18_vs_14_yi"] = kg * ps * (18 - 14) * (1 + (DONGRUI["base"]["d"] if c["code"] == "001201" else c["regional_premium"]))
    row["excess_18_vs_14_pct_mcap"] = row["excess_18_vs_14_yi"] / c["mcap_yi"]
    val.append(row)
val = pd.DataFrame(val)
val.to_csv(PROC / "model_valuation_lens.csv", index=False)

# ------------------------------------------------------------------ decomposition vs 2026 run-rate (flat path, base)
dec = []
NAT_NOW = float(nat.loc["2026-07":"2026-09"].mean())
for _, c in inp.iterrows():
    if np.isnan(c["C_base"]):
        continue
    V0 = c["run_rate_2026"] if c["code"] not in ("002100", "001201", "603363", "002157") else c["V_base"] * 0.95
    if c["code"] == "002100":
        V0 = 315 * 0.77 + 158 * 0.77 * 7 / 12  # Qiangdu consolidated from June 2026
    if c["code"] == "001201":
        V0 = 130.0  # 2026E fattening: ~150 target vs 1-8月 run-rate; research assumption
    if c["code"] == "603363":
        V0 = 0.6 * c["run_rate_2026"]
    r = c["regional_premium"]
    P0n, P1n = NAT_NOW, 18.0
    if c["code"] == "001201":
        p = DONGRUI["base"]
        p0, p1 = P0n * (1 + p["d"]) + p["s"] * p["e"], P1n * (1 + p["d"]) + p["s"] * p["e"]
        reg0, reg1 = P0n * p["d"], P1n * p["d"]
        ch0 = ch1 = p["s"] * p["e"]
    else:
        p0, p1 = P0n * (1 + r), P1n * (1 + r)
        reg0, reg1, ch0, ch1 = P0n * r, P1n * r, 0.0, 0.0
    C0 = c["cost_latest"]
    C1 = c["C_base"]
    W = c["W"]
    m0, m1 = p0 - C0, p1 - C1
    V1 = c["V_base"]
    Vb, mb = (V0 + V1) / 2, (m0 + m1) / 2
    k = 1e4 * W / 1e8
    dec.append(dict(code=c["code"], name=c["name"], V_2026=V0, V_2027=V1, price_2026=p0, price_2027=p1,
                    cost_2026=C0, cost_2027=C1, margin_2026=m0, margin_2027=m1,
                    hog_profit_2026_yi=V0 * m0 * k, hog_profit_2027_yi=V1 * m1 * k,
                    contrib_volume_yi=(V1 - V0) * mb * k,
                    contrib_national_price_yi=Vb * (P1n - P0n) * k,
                    contrib_regional_premium_yi=Vb * (reg1 - reg0) * k,
                    contrib_channel_premium_yi=Vb * (ch1 - ch0) * k,
                    contrib_cost_yi=Vb * (C0 - C1) * k,
                    interest_per_kg=c["interest_per_kg"]))
dec = pd.DataFrame(dec)
dec["check_total"] = dec[[c for c in dec.columns if c.startswith("contrib_")]].sum(axis=1) - (dec["hog_profit_2027_yi"] - dec["hog_profit_2026_yi"])
dec.to_csv(PROC / "model_decomposition.csv", index=False)

# ------------------------------------------------------------------ survival test: 2027 at the futures strip, bear volumes/costs
surv = []
for _, c in inp.iterrows():
    row = sc[sc["code"] == c["code"]].iloc[0]
    if np.isnan(c["C_bear"]):
        cash_burn = np.nan
    else:
        px = realized(c["code"], curve.mean(), "bear", c["regional_premium"])
        cash_burn = c["V_bear"] * 1e4 * c["W"] * (px - c["C_bear"]) / 1e8
    surv.append(dict(code=c["code"], name=c["name"], strip_avg=curve.mean(), hog_profit_at_strip_bear_yi=cash_burn,
                     cash_yi=row["cash_yi"], st_debt_yi=row["st_debt_yi"], cash_to_st_debt=row["cash_to_st_debt"],
                     debt_ratio=row["debt_ratio"], parent_equity_yi=row["parent_equity_yi"],
                     loss_over_equity=-cash_burn / row["parent_equity_yi"] if pd.notna(cash_burn) and cash_burn < 0 else 0.0,
                     ocf_h1_yi=row["ocf_h1_yi"], flags=row["flags"]))
pd.DataFrame(surv).to_csv(PROC / "model_survival.csv", index=False)

out_inp = inp.drop(columns=["season"]).assign(season_q=[",".join(f"{x:.3f}" for x in s_) for s_ in inp["season"]])
out_inp.to_csv(PROC / "model_company_inputs.csv", index=False)

pd.set_option("display.width", 260)
print(paths.round(2))
b = res[(res["case"] == "base")].pivot_table(index="name", columns="path", values="parent_earnings_yi").round(1)
print(b)
pe = res[(res["case"] == "base") & (res["path"] == "P1 全年持平")][["name", "realized_px", "cost_2027", "margin_kg", "margin_head", "hog_profit_yi", "piglet_profit_yi", "parent_earnings_yi", "mcap_yi", "scenario_pe", "cost_hurdle_8x"]]
print(pe.round(2).to_string(index=False))
print(dec.round(2).to_string(index=False))
print(pd.DataFrame(surv).round(2).to_string(index=False))
print(inp[["name", "regional_premium", "regional_premium_months", "parent_share", "interest_per_kg"]].round(3).to_string(index=False))
