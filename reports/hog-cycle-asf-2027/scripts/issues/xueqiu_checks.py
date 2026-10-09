"""Issue #3: check the numbers four Xueqiu authors relied on, and line up the stocks they discussed.

Inputs
- data/processed/moa_sows_monthly.csv, nbs_quarterly.csv: official sow inventory and slaughter
- data/processed/nxin_province_daily.csv, futures_lh_daily.csv, fut_main_mapped.csv: third-party quotes, local only (gitignored)
- data/processed/moa_weekly_prices.csv, monthly_sales.csv, fin_quarterly.csv, pig_ew_index_2017_2026.csv
- data/processed/screen_snapshot.csv, model_valuation_lens.csv, model_results.csv: valuation as of 2026-10-08

Outputs (data/processed/issues/)
- xueqiu_efficiency.csv: heads marketed per sow from official data (TTM slaughter / lagged sows) and implied carcass weight
- xueqiu_price_monthly.csv: monthly national spot averages Apr-Oct 2026 (nxin simple mean of provinces; MOA weekly)
- xueqiu_market_checks.csv: spot, futures and company figures quoted by the authors vs local data
- xueqiu_tickers.csv: valuation, balance sheet and 18-yuan scenario columns for the stocks the authors discussed
- xueqiu_supply_price_map.csv: rough 2027Q1-Q3 supply and price ranges from official sows, efficiency and price elasticity
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from common import PROC  # noqa: E402

OUT = PROC / "issues"
OUT.mkdir(parents=True, exist_ok=True)
ASOF = "2026-10-08"

# ------------------------------------------------------------------ efficiency: heads marketed per sow
sows = pd.read_csv(PROC / "moa_sows_monthly.csv")
sows = sows[sows["sow_wan"].notna() & sows["month"].str[5:7].isin(["03", "06", "09", "12"])]
sows = sows.drop_duplicates("month", keep="last")
sows["q"] = pd.PeriodIndex(pd.to_datetime(sows["month"]), freq="Q")
sq = sows.set_index("q")["sow_wan"]

nbs = pd.read_csv(PROC / "nbs_quarterly.csv")
nbs["q"] = pd.PeriodIndex(nbs["period"], freq="Q")
nbs = nbs.set_index("q")

rows = []
for q in nbs.index:
    if q < pd.Period("2022Q1", "Q"):
        continue
    win = [q - i for i in range(4)]
    if not all(w in nbs.index for w in win):
        continue
    ttm = float(nbs.loc[win, "hog_slaughter_q_wan"].sum())
    s12 = sq.get(q - 4, np.nan)
    breed = [q - i for i in range(4, 8)]
    s_breed = float(np.mean([sq[b] for b in breed])) if all(b in sq.index for b in breed) else np.nan
    rows.append(dict(quarter=str(q), ttm_slaughter_wan=ttm, sows_4q_earlier_wan=s12,
                     sows_avg_q7_to_q4_wan=s_breed,
                     heads_per_sow_12m_lag=ttm / s12 if s12 == s12 else np.nan,
                     heads_per_sow_breeding_window=ttm / s_breed if s_breed == s_breed else np.nan,
                     carcass_wt_kg_est=float(nbs.loc[q, "carcass_wt_kg_est"]),
                     carcass_wt_kg_est_4q_earlier=float(nbs.loc[q - 4, "carcass_wt_kg_est"]) if q - 4 in nbs.index else np.nan))
eff = pd.DataFrame(rows)
for c in ["heads_per_sow_12m_lag", "heads_per_sow_breeding_window"]:
    eff[c + "_yoy"] = eff[c] / eff[c].shift(4) - 1
eff["carcass_wt_yoy"] = eff["carcass_wt_kg_est"] / eff["carcass_wt_kg_est_4q_earlier"] - 1
eff.to_csv(OUT / "xueqiu_efficiency.csv", index=False)

# ------------------------------------------------------------------ spot prices
nx = pd.read_csv(PROC / "nxin_province_daily.csv")
nat = nx.groupby("date")["price"].mean()
nat.index = pd.to_datetime(nat.index)
moa = pd.read_csv(PROC / "moa_weekly_prices.csv")
moa = moa[moa["collect_date"].notna()].copy()
moa["collect_date"] = pd.to_datetime(moa["collect_date"])
moa = moa.set_index("collect_date").sort_index()

monthly = []
for m in pd.period_range("2026-04", "2026-10", freq="M"):
    x = nat[(nat.index >= m.start_time) & (nat.index <= min(m.end_time, pd.Timestamp(ASOF)))]
    y = moa.loc[(moa.index >= m.start_time) & (moa.index <= m.end_time), "live_hog"]
    monthly.append(dict(month=str(m), nxin_national_mean=x.mean(), nxin_days=len(x),
                        nxin_min=x.min(), nxin_max=x.max(), moa_weekly_mean=y.mean(), moa_weeks=len(y)))
monthly = pd.DataFrame(monthly)
monthly.to_csv(OUT / "xueqiu_price_monthly.csv", index=False)

checks = []


def add(item, author, claimed, value, unit, date, source, note=""):
    checks.append(dict(item=item, author=author, claimed=claimed, value=value, unit=unit,
                       date=date, source=source, note=note))


def window(a, b):
    x = nat[(nat.index >= a) & (nat.index <= b)]
    return x.idxmin().date().isoformat(), round(x.min(), 2), x.idxmax().date().isoformat(), round(x.max(), 2)


d, v, _, _ = window("2026-03-25", ASOF)
add("2026年现货低点", "一凡帝诺维奇", "4/13—4/14 8.63 元/公斤（猪易网）", v, "元/公斤", d, "新牧网 32 省简单平均")
w = moa.loc["2026-01-01":ASOF, "live_hog"]
add("2026年现货低点（官方周度）", "一凡帝诺维奇", "4 月中旬为全年低点", w.min(), "元/公斤",
    w.idxmin().date().isoformat(), "农业农村部周度集贸市场活猪价", "集贸市场价，高于出场价")
d, v, _, _ = window("2026-06-01", "2026-07-05")
add("6 月低点", "一凡帝诺维奇", "6/26 9.36 元/公斤", v, "元/公斤", d, "新牧网 32 省简单平均")
_, _, d, v = window("2026-07-01", "2026-07-31")
add("7 月高点", "一凡帝诺维奇", "7/7 11.33 元/公斤", v, "元/公斤", d, "新牧网 32 省简单平均")
d, v, _, _ = window("2026-08-01", "2026-08-31")
add("8 月低点", "一凡帝诺维奇", "最低下探至约 10.2 元/公斤", v, "元/公斤", d, "新牧网 32 省简单平均")
add("9 月下旬", "_春风_", "9/24 全国均价 10.58", round(nat["2026-09-24"], 2), "元/公斤", "2026-09-24", "新牧网 32 省简单平均")
add("9 月末", "一凡帝诺维奇", "节前猪价跌破 10 元", round(nat["2026-09-30"], 2), "元/公斤", "2026-09-30", "新牧网 32 省简单平均")
add("节后（截至数据日）", "一凡帝诺维奇、_春风_", "节后触底反弹；第一波 12.5", round(nat[ASOF], 2), "元/公斤", ASOF,
    "新牧网 32 省简单平均", "事后信息")

# ------------------------------------------------------------------ futures
fut = pd.read_csv(PROC / "futures_lh_daily.csv")
fut = fut[fut["contract"] != "LH0"]


def settle(contract, date):
    x = fut[(fut["contract"] == contract) & (fut["trade_date"] == date)]["settle"]
    return float(x.iloc[0]) if len(x) else np.nan


for date, claim in [("2026-08-07", "2705 是 14 块（08-08 发帖，前一交易日）"), ("2026-08-12", "2705 13.1"),
                    ("2026-09-30", ""), (ASOF, "")]:
    add("LH2705 结算价", "豆区" if claim else "", claim, settle("LH2705", date), "元/吨", date, "大商所日线")
h05 = fut[fut["contract"] == "LH2705"].set_index("trade_date")["high"]
add("LH2705 合约最高价", "豆区", "2705 高点 14.5 左右", float(h05.max()), "元/吨", h05.idxmax(), "大商所日线")
for date in ["2026-08-07", ASOF]:
    add("LH2701 结算价", "", "", settle("LH2701", date), "元/吨", date, "大商所日线")
prem = settle("LH2705", "2026-08-07") / 1000 / nat["2026-08-07"] - 1
add("LH2705 相对现货升水", "豆区", "比现货高 40%", round(prem, 3), "比例", "2026-08-07", "大商所日线 / 新牧网")

mm = pd.read_csv(PROC / "fut_main_mapped.csv")
mm = mm.merge(fut[["contract", "trade_date", "high"]], left_on=["mapped_contract", "trade_date"],
              right_on=["contract", "trade_date"], how="left")
mm["year"] = mm["trade_date"].str[:4]
for y, g in mm.groupby("year"):
    add("主力合约年内最高价", "豆区" if y in ("2023", "2025") else "", "连续合约历次上行峰值均≥20000" if y in ("2023", "2025") else "",
        float(g["high"].max()), "元/吨", y, "大商所日线（主力映射）")

# ------------------------------------------------------------------ company figures
sales = pd.read_csv(PROC / "monthly_sales.csv", dtype={"code": str})
sales = sales[sales["months_covered"] == 1]
mu = sales[(sales["code"] == "002714") & (sales["price"] < 10)]
add("牧原月度均价低于 10 元的月份", "我不帅你报警", "上市以来 5 次，3 次在 2026 年（06-06 发帖）",
    "、".join(f"{r.month_key}（{r.price}）" for r in mu.itertuples()), "", "截至2026-08",
    "公司月度销售简报", "本地数据始于 2018 年；6 月 9.69 元为发帖后新增")
h1 = sales[sales["month_key"].str[5:7] <= "06"].copy()
h1["y"] = h1["month_key"].str[:4]
g = h1[h1["y"].isin(["2025", "2026"])].groupby(["code", "y"]).agg(heads=("total_heads", "sum"), n=("month_key", "nunique")).unstack("y")
claimed_h1 = {"002157": 56.07, "002124": 31.41, "300498": -0.69, "000876": -15.89, "605296": 11.98, "002100": 20.95,
              "002840": 21.82, "603477": 17.73, "002548": 37.59, "002567": 4.95, "001201": 15.82, "000048": 5.53}
names = sales.drop_duplicates("code", keep="last").set_index("code")["sec_name"].str.replace(" ", "")
for code, c in claimed_h1.items():
    n25, n26 = g.loc[code, ("n", "2025")], g.loc[code, ("n", "2026")]
    val = g.loc[code, ("heads", "2026")] / g.loc[code, ("heads", "2025")] - 1 if n25 == 6 and n26 == 6 else np.nan
    add(f"1—6 月销量同比：{names[code]}", "我不帅你报警", f"{c:+.2f}%（07-13 图表）",
        round(val * 100, 2) if val == val else np.nan, "%", "2026H1", "公司月度销售简报")

fin = pd.read_csv(PROC / "fin_quarterly.csv", dtype={"code": str})
fq = fin[fin["report_date"].isin(["2026-03-31", "2026-06-30"])].set_index(["code", "report_date"])
for code, rd, field, author, claimed in [
    ("002714", "2026-06-30", "PARENT_NETPROFIT", "一凡帝诺维奇、我不帅你报警", "上半年亏 60.78 亿 / 超 60 亿"),
    ("002714", "2026-06-30", "debt_ratio", "一凡帝诺维奇", "负债率 54.18%"),
    ("605296", "2026-03-31", "PARENT_NETPROFIT", "我不帅你报警", "一季度账面亏 6.48 亿"),
    ("605296", "2026-03-31", "ASSET_IMPAIRMENT_INCOME", "我不帅你报警", "真实亏 1.68 亿＝账面减去减值"),
    ("605296", "2026-03-31", "debt_ratio", "一凡帝诺维奇", "负债率 33.98%"),
    ("605296", "2026-06-30", "debt_ratio", "我不帅你报警", "负债率 40.75%"),
    ("603477", "2026-06-30", "PARENT_NETPROFIT", "我不帅你报警", "上半年亏 8.38 亿"),
    ("603477", "2026-06-30", "debt_ratio", "我不帅你报警", "负债率 69.40%"),
    ("002100", "2026-06-30", "PARENT_NETPROFIT", "我不帅你报警", "上半年亏 4.41 亿"),
    ("002124", "2026-06-30", "PARENT_NETPROFIT", "_春风_", "上半年预计亏 12.77—12.99 亿（测算）"),
    ("002124", "2026-06-30", "debt_ratio", "", ""),
    ("002567", "2026-06-30", "MONETARYFUNDS", "我不帅你报警", "半年报后现金 21 亿"),
    ("001201", "2026-06-30", "FIXED_ASSET", "豆区", "固定资产 39 亿"),
]:
    v = fq.loc[(code, rd), field]
    v = round(v * 100, 2) if field == "debt_ratio" else round(v / 1e8, 2)
    add(f"{fq.loc[(code, rd), 'name']} {field}", author, claimed, v, "%" if field == "debt_ratio" else "亿元", rd, "定期报告")

# ------------------------------------------------------------------ sector index on dated calls (hindsight only)
ew = pd.read_csv(PROC / "pig_ew_index_2017_2026.csv", parse_dates=["date"]).set_index("date")["pig_ew"]
e26 = ew["2026-01-01":ASOF]
add("等权猪股指数 2026 年低点", "", "", round(e26.min(), 2), "指数", e26.idxmin().date().isoformat(), "本项目等权指数")
for date, author, claim in [("2026-06-17", "_春风_", "猪股抄底正当时"), ("2026-06-24", "我不帅你报警", "市场底基本就绪")]:
    lv = ew[:date].iloc[-1]
    add("等权猪股指数：发帖日至数据日涨跌", author, claim, round(ew[ASOF] / lv - 1, 3), "比例", f"{date}→{ASOF}",
        "本项目等权指数", "事后信息")

pd.DataFrame(checks).to_csv(OUT / "xueqiu_market_checks.csv", index=False)

# ------------------------------------------------------------------ rough supply -> price map for 2027Q1-Q3
# sows at 2026Q1-Q3 quarter-ends vs the same quarter-ends of 2025 stand in for 2027Q1-Q3 vs 2026Q1-Q3 marketings;
# price change = -flexibility x supply change (flexibility 2 / 5 / 9 as in Issue #1); demand, imports, frozen stock
# and carcass weight are held constant
s25 = [sq[pd.Period(q, "Q")] for q in ("2025Q1", "2025Q2", "2025Q3")]
s26 = [sq[pd.Period(q, "Q")] for q in ("2026Q1", "2026Q2")]
base_px = float(nat["2026-01-01":"2026-09-30"].mean())
fut27 = [settle(c, ASOF) / 1000 for c in ("LH2701", "LH2703", "LH2705", "LH2707", "LH2709")]
mp = []
for s3 in (3740, 3700, 3650):
    for eff_g in (0.0, 0.02, 0.04):
        sup = np.mean(s26 + [s3]) / np.mean(s25) * (1 + eff_g) - 1
        row = dict(sows_2026q3_wan=s3, efficiency_growth=eff_g, supply_change=sup, base_px_2026q1_q3=base_px,
                   futures_2027_jan_sep_mean=float(np.mean(fut27)))
        for fl in (2, 5, 9):
            row[f"px_flex{fl}"] = base_px * (1 - fl * sup)
        mp.append(row)
pd.DataFrame(mp).to_csv(OUT / "xueqiu_supply_price_map.csv", index=False)

# ------------------------------------------------------------------ tickers discussed by the authors
CODES = ["002714", "300498", "000876", "605296", "001201", "002100", "603477", "002567", "002124",
         "600975", "002385", "000048", "002840", "002157", "603363", "002548"]
scr = pd.read_csv(PROC / "screen_snapshot.csv", dtype={"code": str}).set_index("code")
lens = pd.read_csv(PROC / "model_valuation_lens.csv", dtype={"code": str}).set_index("code")
res = pd.read_csv(PROC / "model_results.csv", dtype={"code": str})
p1 = res[(res["path"] == "P1 全年持平") & (res["case"] == "base")].set_index("code")
tk = scr.loc[CODES, ["name", "close", "close_date", "mcap_yi", "pb", "debt_ratio", "cash_to_st_debt", "np_h1_yi",
                     "ocf_h1_yi", "sows_wan", "run_rate_2026_wan", "cost_latest_kg", "cost_date",
                     "mcap_per_runrate_head_yuan", "flags"]].copy()
tk["implied_national_px_10x"] = lens["implied_national_px_10x"].reindex(CODES)
tk["implied_national_px_15x"] = lens["implied_national_px_15x"].reindex(CODES)
tk["scenario18_parent_earnings_yi"] = p1["parent_earnings_yi"].reindex(CODES)
tk["scenario18_pe"] = p1["scenario_pe"].reindex(CODES)
tk["excess_18_vs_14_pct_mcap"] = lens["excess_18_vs_14_pct_mcap"].reindex(CODES)
tk.reset_index().to_csv(OUT / "xueqiu_tickers.csv", index=False)

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
print(eff.round(3).to_string(index=False))
print(monthly.round(2).to_string(index=False))
print(pd.DataFrame(checks).to_string(index=False))
print(tk.round(2).to_string())
print(pd.DataFrame(mp).round(3).to_string(index=False))
