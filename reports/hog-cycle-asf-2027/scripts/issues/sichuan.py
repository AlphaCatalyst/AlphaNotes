"""Issue #1: is Sichuan destocking slower than the nation, and does it matter for national supply and the 2027 price?

Inputs
- research/sichuan_destocking/sichuan_supply.csv: Sichuan and national quarter-end series with sources and grades
- data/processed/nbs_quarterly.csv: national hog inventory and pork output (NBS)
- data/processed/nxin_region_weekly.csv, nxin_province_daily.csv: third-party quotes, local only (gitignored)

Outputs (data/processed/issues/)
- sichuan_windows.csv: sow declines by window, Sichuan vs national vs national ex-Sichuan, and the "extra" sows Sichuan kept
- sichuan_supply_effect.csv: near-term hog-inventory effect and 2027 national price sensitivity
- price_flexibility_annual.csv: annual pork output change vs national price change (rough flexibility check)
- sichuan_price_spread.csv: Sichuan minus national monthly price (same source), Southwest minus national yearly
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
SC = ROOT / "research" / "sichuan_destocking"

sup = pd.read_csv(SC / "sichuan_supply.csv")


def series(region: str, metric: str) -> pd.Series:
    d = sup[(sup.region == region) & (sup.metric == metric)]
    return d.set_index("period")["value"].astype(float)


sc_sow, nat_sow, sc_hog = series("四川", "能繁母猪存栏"), series("全国", "能繁母猪存栏"), series("四川", "生猪存栏")
nbs = pd.read_csv(PROC / "nbs_quarterly.csv").set_index("period")
nat_hog = nbs["hog_inventory_wan"].astype(float)

# ------------------------------------------------------------------ 1. windows
WINDOWS = [
    ("2025Q2", "2026Q2", "同比"),
    ("2025Q3", "2026Q2", "全国部署调减之后"),
    ("2025Q4", "2026Q2", "2026年方案基数（2025年末）之后"),
    ("2025Q3", "2026Q1", "50元补贴出台前"),
    ("2026Q1", "2026Q2", "50元补贴出台后一个季度"),
    ("2023Q2", "2024Q4", "四川第一轮去化"),
    ("2024Q4", "2026Q2", "四川第一轮去化之后"),
    ("2023Q2", "2026Q2", "完整周期（自四川2023Q2高点）"),
]
rows = []
for a, b, label in WINDOWS:
    ex = (nat_sow[b] - sc_sow[b]) / (nat_sow[a] - sc_sow[a]) - 1
    extra = sc_sow[b] - sc_sow[a] * (1 + ex)
    rows.append(dict(window=f"{a}→{b}", label=label, sichuan=sc_sow[b] / sc_sow[a] - 1, national=nat_sow[b] / nat_sow[a] - 1,
                     national_ex_sichuan=ex, sichuan_extra_vs_rest_wan=extra, extra_share_of_national=extra / nat_sow[b],
                     sichuan_share_end=sc_sow[b] / nat_sow[b]))
win = pd.DataFrame(rows)
win.to_csv(OUT / "sichuan_windows.csv", index=False)

# ------------------------------------------------------------------ 2. rough price flexibility from annual data
nx = pd.read_csv(PROC / "nxin_region_weekly.csv", parse_dates=["date"])
nat_price = nx[nx.region == "全国"].assign(year=lambda d: d.date.dt.year).groupby("year").price.mean()
q4 = nbs[nbs.index.str.endswith("Q4")]
pork = pd.Series(q4["pork_output_cum_wan_t"].astype(float).values, index=q4.index.str[:4].astype(int))
flex = []
for y in range(pork.index.min() + 1, pork.index.max() + 1):
    if y in pork.index and y - 1 in pork.index and y in nat_price.index and y - 1 in nat_price.index:
        dq, dp = np.log(pork[y] / pork[y - 1]), np.log(nat_price[y] / nat_price[y - 1])
        flex.append(dict(year=y, pork_output_wan_t=pork[y], pork_chg=np.exp(dq) - 1, national_price=nat_price[y],
                         price_chg=np.exp(dp) - 1, flexibility=-dp / dq if abs(dq) >= 0.01 else np.nan))
flex = pd.DataFrame(flex)
flex.to_csv(OUT / "price_flexibility_annual.csv", index=False)
f_ok = flex.flexibility.dropna()
F_LO, F_MID, F_HI = 2.0, 5.0, 9.0

# ------------------------------------------------------------------ 3. supply effect and 2027 price sensitivity
hog_ex = (nat_hog["2026Q2"] - sc_hog["2026Q2"]) / (nat_hog["2025Q2"] - sc_hog["2025Q2"]) - 1
hog_extra = sc_hog["2026Q2"] - sc_hog["2025Q2"] * (1 + hog_ex)
dest_per_month = (nat_sow["2025Q3"] - nat_sow["2026Q2"]) / 9

pc = pd.read_csv(SC / "province_compare.csv")
gd = pc[(pc.region == "广东") & (pc.metric == "能繁母猪存栏") & (pc.period == "2026Q2")].iloc[0]
gd_end, gd_start = float(gd.value), float(gd.value) / (1 + float(gd.yoy_pct) / 100)
ex2 = (nat_sow["2026Q2"] - sc_sow["2026Q2"] - gd_end) / (nat_sow["2025Q2"] - sc_sow["2025Q2"] - gd_start) - 1
both_extra = (sc_sow["2026Q2"] - sc_sow["2025Q2"] * (1 + ex2)) + (gd_end - gd_start * (1 + ex2))

eff = []
for key, share, note in [
    ("能繁母猪：四川自2025Q3起与全国其余地区同步", win.loc[win.window == "2025Q3→2026Q2", "extra_share_of_national"].item(), "影响约 10 个月后的出栏，即 2027 年"),
    ("能繁母猪：四川同比与全国其余地区同步", win.loc[win.window == "2025Q2→2026Q2", "extra_share_of_national"].item(), "同上"),
    ("能繁母猪：四川和广东同比与全国其余地区同步", both_extra / nat_sow["2026Q2"], f"广东 2026Q2 {gd_end} 万头、同比 {gd.yoy_pct}%（A）；两省合计多保留 {both_extra:.1f} 万头"),
    ("生猪存栏：四川同比与全国其余地区同步", hog_extra / nat_hog["2026Q2"], "影响 2026 年下半年至 2027 年初的出栏；四川二季度存栏环比 +7.7% 异常，待三季度数据核实"),
]:
    for price in (12.5, 14.0, 18.0):
        eff.append(dict(channel=key, extra_share_of_national=share, price_level=price, flex_lo=F_LO, flex_mid=F_MID, flex_hi=F_HI,
                        price_impact_pct_lo=share * F_LO, price_impact_pct_mid=share * F_MID, price_impact_pct_hi=share * F_HI,
                        price_impact_yuan_lo=price * share * F_LO, price_impact_yuan_mid=price * share * F_MID,
                        price_impact_yuan_hi=price * share * F_HI, note=note))
eff = pd.DataFrame(eff)
eff.to_csv(OUT / "sichuan_supply_effect.csv", index=False)

# ------------------------------------------------------------------ 4. local price spread (same source, derived only)
pv = pd.read_csv(PROC / "nxin_province_daily.csv", parse_dates=["date"])
pv["month"] = pv.date.dt.to_period("M").astype(str)
m = pv[pv.province.isin(["四川省", "全国"])].pivot_table(index="month", columns="province", values="price", aggfunc="mean")
spread_m = pd.DataFrame(dict(period=m.index, freq="月", series="四川省−全国（新牧网省级报价）",
                             spread_yuan=(m["四川省"] - m["全国"]).values, spread_pct=(m["四川省"] / m["全国"] - 1).values))
yr = nx.assign(year=nx.date.dt.year).pivot_table(index="year", columns="region", values="price", aggfunc="mean")
spread_y = pd.DataFrame(dict(period=yr.index.astype(str), freq="年", series="西南大区−全国（新牧网指数成交均价）",
                             spread_yuan=(yr["西南"] - yr["全国"]).values, spread_pct=(yr["西南"] / yr["全国"] - 1).values))
spread = pd.concat([spread_m, spread_y], ignore_index=True)
spread.to_csv(OUT / "sichuan_price_spread.csv", index=False)

pd.set_option("display.width", 220)
print(win.round(4).to_string(index=False))
print(f"\nhog inventory 2026Q2 yoy: Sichuan {sc_hog['2026Q2'] / sc_hog['2025Q2'] - 1:.4f}, national {nat_hog['2026Q2'] / nat_hog['2025Q2'] - 1:.4f}, "
      f"ex-Sichuan {hog_ex:.4f}; Sichuan extra {hog_extra:.1f} wan = {hog_extra / nat_hog['2026Q2']:.4f} of national")
print(f"national sow destocking since 2025Q3: {dest_per_month:.1f} wan/month")
print(flex.round(3).to_string(index=False))
print(f"flexibility median {f_ok.median():.2f}, IQR {f_ok.quantile(.25):.2f}-{f_ok.quantile(.75):.2f}, n={len(f_ok)}")
print(eff.round(4).to_string(index=False))
sm = spread_m.assign(y=spread_m.period.str[:4], mo=spread_m.period.str[5:7].astype(int))
for y in ("2025", "2026"):
    d = sm[sm.y == y]
    print(y, "avg spread", round(d.spread_yuan.mean(), 3), "Apr-Jul pct", round(d[d.mo.between(4, 7)].spread_pct.mean(), 4))
print(spread_y.round(3).to_string(index=False))
