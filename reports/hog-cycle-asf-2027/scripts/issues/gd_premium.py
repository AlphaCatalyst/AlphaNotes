"""Issue #4: the Guangdong hog premium - its size by cycle, whether it widens with the national price,
what a "normal" level is, and how much of it Dongrui (001201) realises.

Inputs (third-party raw series are local only; only aggregates are written out):
  zhuwang_province_daily.csv  中国养猪网 provincial 外三元 quotes, sampled twice a week, 2015-12 ..  (local)
  nxin_price_wide.csv         新牧网 weekly national / 华南 averages                                   (local)
  nxin_province_daily.csv     新牧网 daily provincial quotes 2025-01 ..                                (local)
  moa_weekly_prices.csv       农业农村部 集贸市场 weekly national live hog price
  nbs_tenday_hog.csv          国家统计局 流通领域 生猪（外三元）ten-day national price, 2018-2022
  gd_prices.csv               广东省农业农村厅 slaughterhouse purchase price (2020-12 ..), farm-gate price (2022-2025)
  research/dongrui/price_split.csv, monthly_sales.csv, fin_quarterly.csv, nbs_annual_bulletin.csv
  issues/dongrui_pb_peers.csv (peer universe), issues/dongrui_scenarios.csv (Issue #2 profit grid)
Outputs (data/processed/issues/):
  gd_spread_periods.csv    GD minus national by period and price-rise phase (same source)
  gd_spread_yearly.csv     by calendar year, with Guangdong's official share of national hog output
  gd_supply.csv            Guangdong hog output and year-end sows (国家统计局广东调查总队) vs national output
  gd_spread_by_level.csv   spread and ratio by national price bucket and regime, with monthly OLS on the national level
  gd_spread_season.csv     spread by calendar month and regime
  gd_spread_sources.csv    the same yearly spread under other source combinations
  gd_source_check.csv      the zhuwang series against other sources (level gap, correlation)
  gd_dongrui_bridge.csv    Dongrui realised price vs national: GD spread, domestic vs GD, export contribution
  gd_peer_price.csv        annual commodity-hog price by listed company, Dongrui's gap to the peer median
  gd_peer_roe.csv          annual ROE by listed company, Dongrui's rank
  gd_scenarios_2027.csv    national 18 元/公斤 in 2027: five spread cases -> Dongrui premium, hog profit, and the
                           national price at which parent net profit reaches 10亿 (Issue #2 grid, premium swapped)
  gd_issue2_recheck.csv    Issue #2's implied national price and 18-yuan net profit with these absolute premiums
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
OUT = PROC / "issues"
DR = ROOT / "research" / "dongrui"
OUT.mkdir(parents=True, exist_ok=True)

ASF = ("2018-08-01", "2021-12-31")          # outbreak, 中南区 transport ban, Guangdong supply collapse
PERIODS = [
    ("非瘟前", "2015-12-01", "2018-07-31"),
    ("非瘟初期（疫区及相邻省禁止调出）", "2018-08-01", "2019-06-30"),
    ("价差高位期（公司问询回复口径）", "2019-07-01", "2021-04-30"),
    ("2021年5—12月", "2021-05-01", "2021-12-31"),
    ("2022年", "2022-01-01", "2022-12-31"),
    ("2022年1—4月（广东暂停省外屠宰生猪前）", "2022-01-01", "2022-04-30"),
    ("2022年5—12月（暂停后）", "2022-05-01", "2022-12-31"),
    ("2023年", "2023-01-01", "2023-12-31"),
    ("2024年", "2024-01-01", "2024-12-31"),
    ("2025年", "2025-01-01", "2025-12-31"),
    ("2026年至今", "2026-01-01", "2026-12-31"),
]
# trough window, peak window of the national price for each rise
PHASES = [
    ("2016年上涨段", ("2015-12-01", "2016-02-29"), ("2016-04-01", "2016-07-31")),
    ("2019年上涨段", ("2019-01-01", "2019-03-31"), ("2019-10-01", "2019-11-30")),
    ("2022年上涨段", ("2022-03-01", "2022-04-30"), ("2022-10-01", "2022-11-30")),
    ("2024年上涨段", ("2024-01-01", "2024-02-29"), ("2024-08-01", "2024-09-30")),
    ("2026年反弹段", ("2026-04-01", "2026-06-30"), ("2026-09-01", "2026-12-31")),
]
GDZD = "https://gdzd.stats.gov.cn/"
GD_SUPPLY = [  # 广东 肉猪出栏 / 年末能繁母猪 (万头); 2015-2017 revised after the 3rd agricultural census
    (2015, 3959.62, 242.52, GDZD + "dcsj/nysc/cmysc/201901/t20190128_154448.html"),
    (2016, 3850.61, 240.22, GDZD + "dcsj/nysc/cmysc/201901/t20190128_154448.html"),
    (2017, 3712.00, 229.43, GDZD + "dcsj/nysc/cmysc/201901/t20190128_154449.html"),
    (2018, 3757.40, 217.98, GDZD + "dcsj/nysc/cmysc/201901/t20190128_154440.html"),
    (2019, 2940.17, 131.01, GDZD + "dcsj/nysc/cmysc/202001/t20200117_175326.html"),
    (2020, 2537.36, None, "http://district.ce.cn/newarea/roll/202103/15/t20210315_36382893.shtml"),
    (2021, 3336.63, 191.18, GDZD + "dcsj/nysc/cmysc/202201/t20220118_179196.html"),
    (2022, 3496.79, 204.37, GDZD + "sjfb/sjfbz/202301/t20230120_180614_mo.html"),
    (2023, 3794.01, 195.79, GDZD + "sjfb/sjjd/202401/t20240118_181738.html"),
    (2024, 3817.71, 204.89, GDZD + "dcsj/nysc/cmysc/202501/t20250120_182365.html"),
    (2025, 4024.96, 203.34, GDZD + "sjfb/sjjd/202601/t20260120_182632.html"),
]
GD_OUTPUT = {y: o for y, o, _, _ in GD_SUPPLY}
WIND_GD = {2018: 13.79, 2019: 23.52, 2020: 36.86, 2021: 21.74, 2022: 19.92, "2023Q1": 15.42}  # 2023-05 问询回复, Wind
# 销售费用-销售佣金 (元): 2018-2019 招股说明书 (万元), 2020+ annual reports; HK agents charge a share of the auction price
COMMISSION = {2018: 23_961_200.0, 2019: 26_799_000.0, 2020: 46_068_914.89,
              2021: 46_393_623.01, 2022: 57_335_962.24, 2023: 43_563_094.28, 2024: 24_752_312.81,
              2025: 1_298_427.31, "2024H1": 22_226_206.66, "2025H1": 748_882.46, "2026H1": 662_586.46}
# 问询回复 7-1-12: 商品猪 / 自产内销 / 自产供港 / 外购供港, 万千克
KG = {2018: (2666.55, 713.31, 1115.14, 838.10), 2019: (2495.77, 635.74, 1388.47, 471.56),
      2020: (2441.35, 445.23, 1649.24, 346.89), 2021: (2847.10, 548.10, 1958.16, 340.83),
      2022: (4409.62, 1764.87, 2488.85, 155.90), "2023Q1": (1455.79, 649.55, 788.75, 17.50)}
PEERS_INQ = {  # 2023-05 问询回复 7-1-11: 商品猪单位售价 元/公斤
    "牧原股份": {2018: 11.62, 2019: 18.74, 2020: 30.19, 2021: 16.87, 2022: 18.30, "2023Q1": 14.75},
    "正邦科技": {2018: 12.91, 2019: 18.20, 2020: 32.70, 2021: 16.60, 2022: 15.00, "2023Q1": 14.20},
    "温氏股份": {2018: 12.82, 2019: 18.65, 2020: 33.56, 2021: 17.39, 2022: 19.05, "2023Q1": 14.85},
    "新希望": {2018: 12.72, 2019: 20.48, 2020: 32.08, 2021: 18.51, 2022: 17.71, "2023Q1": 14.75},
    "天邦食品": {2018: 12.12, 2019: 18.58, 2020: 31.59, 2021: 17.29, 2022: 18.10, "2023Q1": 14.73},
    "东瑞股份": {2018: 15.36, 2019: 28.45, 2020: 43.88, 2021: 27.77, 2022: 23.68, "2023Q1": 16.77},
}
INQ_URL = "https://static.cninfo.com.cn/finalpage/2023-05-22/1216871308.PDF"
EXPORT_KG = 120


# ------------------------------------------------------------------ same-source GD and national series
def load_zhuwang() -> pd.DataFrame:
    z = pd.read_csv(PROC / "zhuwang_province_daily.csv", parse_dates=["date"])
    z = z[(z.price > 3) & (z.price < 80)]
    w = z.pivot_table(index="date", columns="province", values="price", aggfunc="mean")
    w = w[w.notna().sum(axis=1) >= 20]
    # a one-off jump that reverses at the next quote while the neighbours agree is a typo, not a market move
    prev, nxt = w.shift(1), w.shift(-1)
    d1, d2 = w - prev, nxt - w
    spike = (d1.abs() > 1.2) & (d2.abs() > 1.2) & (d1 * d2 < 0) & ((prev - nxt).abs() < 0.5 * np.minimum(d1.abs(), d2.abs()))
    w = w.mask(spike)
    d = pd.DataFrame({"gd": w["广东"], "nat": w.mean(axis=1), "nat_ex_gd": w.drop(columns="广东").mean(axis=1),
                      "henan": w["河南"], "guangxi": w["广西"], "hunan": w["湖南"], "jiangxi": w["江西"],
                      "n_prov": w.notna().sum(axis=1)})
    d = d.dropna(subset=["gd", "nat"])
    d["spread"] = d["gd"] - d["nat"]
    d["ratio"] = d["gd"] / d["nat"] - 1
    return d


def longest_run_days(mask: pd.Series) -> int:
    best, start, prev = 0, None, None
    for t, v in mask.items():
        if v:
            start = t if start is None else start
            best = max(best, (t - start).days + 3)
        else:
            start = None
        prev = t
    return best


def stats(x: pd.DataFrame, label: str) -> dict:
    sp = x["spread"]
    return dict(period=label, start=x.index.min().date(), end=x.index.max().date(), n_obs=len(x),
                national_mean=x["nat"].mean(), gd_mean=x["gd"].mean(), spread_mean=sp.mean(), spread_median=sp.median(),
                ratio_mean=x["ratio"].mean(), spread_max=sp.max(), spread_max_date=sp.idxmax().date(),
                spread_min=sp.min(), spread_min_date=sp.idxmin().date(), share_gd_above=(sp > 0).mean(),
                share_gt1=(sp > 1).mean(), share_gt2=(sp > 2).mean(), longest_gt2_days=longest_run_days(sp > 2))


def regime(t: pd.Timestamp) -> str:
    if t < pd.Timestamp(ASF[0]):
        return "非瘟前"
    if t <= pd.Timestamp(ASF[1]):
        return "非瘟冲击期"
    return "2022年后"


zw = load_zhuwang()
zw["regime"] = [regime(t) for t in zw.index]
last = zw.index.max()

per = [stats(zw.loc[a:b], name) for name, a, b in PERIODS if not zw.loc[a:b].empty]
smooth = zw["nat"].rolling(4, center=True, min_periods=2).mean()
for name, lo, hi in PHASES:
    lo_s, hi_s = smooth.loc[lo[0]:lo[1]], smooth.loc[hi[0]:hi[1]]
    if lo_s.empty or hi_s.empty:
        continue
    t0, t1 = lo_s.idxmin(), hi_s.idxmax()
    x = zw.loc[t0:t1]
    r = stats(x, name)
    r["corr_spread_national"] = x["spread"].corr(x["nat"])
    r["spread_first4"], r["spread_last4"] = x["spread"].iloc[:4].mean(), x["spread"].iloc[-4:].mean()
    per.append(r)
cur = zw.iloc[-8:]
per.append(stats(cur, "最近8个采样点（约4周）"))
periods = pd.DataFrame(per)
periods.to_csv(OUT / "gd_spread_periods.csv", index=False, float_format="%.4f")

# ------------------------------------------------------------------ yearly, with output share
nbs = pd.read_csv(PROC / "nbs_annual_bulletin.csv").set_index("year")["b_slaughter"]
yr = []
for y, x in zw.groupby(zw.index.year):
    r = stats(x, str(y))
    r["year"] = y
    r["gd_output_wan"] = GD_OUTPUT.get(y)
    r["national_output_wan"] = nbs.get(y)
    r["gd_output_share"] = GD_OUTPUT[y] / nbs[y] if y in GD_OUTPUT and y in nbs.index else np.nan
    for p in ("henan", "guangxi", "hunan", "jiangxi"):
        r[f"gd_minus_{p}"] = (x["gd"] - x[p]).mean()
    yr.append(r)
yearly = pd.DataFrame(yr)
yearly.to_csv(OUT / "gd_spread_yearly.csv", index=False, float_format="%.4f")
supply = pd.DataFrame(GD_SUPPLY, columns=["year", "gd_output_wan", "gd_sows_end_wan", "gd_url"])
supply["national_output_wan"] = supply["year"].map(nbs)
supply["gd_output_share"] = supply["gd_output_wan"] / supply["national_output_wan"]
supply.to_csv(OUT / "gd_supply.csv", index=False, float_format="%.4f")

# ------------------------------------------------------------------ does the spread widen with the national price?
bins = [0, 12, 14, 16, 18, 20, 22, 26, 80]
labels = ["<12", "12-14", "14-16", "16-18", "18-20", "20-22", "22-26", ">26"]
zw["bucket"] = pd.cut(zw["nat"], bins, labels=labels, right=False)
lv = (zw.groupby(["regime", "bucket"], observed=True)
        .agg(n_obs=("spread", "size"), national_mean=("nat", "mean"), spread_mean=("spread", "mean"),
             spread_median=("spread", "median"), ratio_mean=("ratio", "mean"), share_gt2=("spread", lambda s: (s > 2).mean()))
        .reset_index())
non_asf = zw[zw["regime"] != "非瘟冲击期"]
lv2 = (non_asf.groupby("bucket", observed=True)
       .agg(n_obs=("spread", "size"), national_mean=("nat", "mean"), spread_mean=("spread", "mean"),
            spread_median=("spread", "median"), ratio_mean=("ratio", "mean"), share_gt2=("spread", lambda s: (s > 2).mean()))
       .reset_index().assign(regime="非瘟前+2022年后"))
level = pd.concat([lv, lv2], ignore_index=True)

reg_rows = []
mon = zw.resample("MS").mean(numeric_only=True)
mon["regime"] = [regime(t) for t in mon.index]
for name, sub in [("非瘟前", mon[mon.regime == "非瘟前"]), ("2022年后", mon[mon.regime == "2022年后"]),
                  ("非瘟前+2022年后", mon[mon.regime != "非瘟冲击期"]), ("非瘟冲击期", mon[mon.regime == "非瘟冲击期"])]:
    sub = sub.dropna(subset=["spread", "nat"])
    for ycol in ("spread", "ratio"):
        b, a = np.polyfit(sub["nat"], sub[ycol], 1)
        pred = a + b * sub["nat"]
        r2 = 1 - ((sub[ycol] - pred) ** 2).sum() / ((sub[ycol] - sub[ycol].mean()) ** 2).sum()
        reg_rows.append(dict(regime=name, bucket=f"OLS {ycol}~national (monthly)", n_obs=len(sub), slope=b, intercept=a, r2=r2,
                             corr=sub[ycol].corr(sub["nat"])))
        # same slope after removing regime x calendar-month means from both sides
        key = [sub["regime"], sub.index.month]
        yd = sub[ycol] - sub.groupby(key)[ycol].transform("mean")
        xd = sub["nat"] - sub.groupby(key)["nat"].transform("mean")
        bd = (xd * yd).sum() / (xd ** 2).sum()
        r2d = 1 - ((yd - bd * xd) ** 2).sum() / (yd ** 2).sum()
        reg_rows.append(dict(regime=name, bucket=f"OLS {ycol}~national, regime x month means removed", n_obs=len(sub), slope=bd,
                             intercept=0.0, r2=r2d, corr=xd.corr(yd)))
level = pd.concat([level, pd.DataFrame(reg_rows)], ignore_index=True)
level.to_csv(OUT / "gd_spread_by_level.csv", index=False, float_format="%.4f")

season = (zw.assign(month=zw.index.month).groupby(["regime", "month"])
            .agg(n_obs=("spread", "size"), spread_mean=("spread", "mean"), ratio_mean=("ratio", "mean"), national_mean=("nat", "mean"))
            .reset_index())
season.to_csv(OUT / "gd_spread_season.csv", index=False, float_format="%.4f")

# ------------------------------------------------------------------ other sources
nx = pd.read_csv(PROC / "nxin_price_wide.csv", parse_dates=["week_label"]).set_index("week_label")
nx_m = nx.resample("MS").mean()
moa = pd.read_csv(PROC / "moa_weekly_prices.csv")
moa = moa[moa["live_hog"].notna()].copy()
moa["date"] = [pd.Timestamp.fromisocalendar(int(y), int(min(w, 52)), 3) for y, w in zip(moa.year, moa.week)]
moa_m = moa.set_index("date")["live_hog"].resample("MS").mean()
nbs_t = pd.read_csv(PROC / "nbs_tenday_hog.csv")
nbs_t = nbs_t[nbs_t["price_yuan_kg"].notna()].copy()
nbs_t["month"] = pd.to_datetime(nbs_t["period"].str.extract(r"(\d{4}-\d{2})")[0] + "-01")
nbs_m = nbs_t.groupby("month")["price_yuan_kg"].mean()
gdp = pd.read_csv(PROC / "gd_prices.csv", parse_dates=["period_start", "period_end"])
gd_slaughter = (gdp[gdp.report_type.str.contains("屠宰")].dropna(subset=["hog_purchase_price"])
                .assign(m=lambda x: x.period_start.dt.to_period("M").dt.to_timestamp())
                .groupby("m")["hog_purchase_price"].mean())
gd_farm = (gdp.dropna(subset=["farm_hog_price"]).assign(m=lambda x: x.period_start.dt.to_period("M").dt.to_timestamp())
           .groupby("m")["farm_hog_price"].mean())
nxp = pd.read_csv(PROC / "nxin_province_daily.csv", parse_dates=["date"])
nx_gd = nxp[nxp.province.str.startswith("广东")].set_index("date")["price"].resample("MS").mean()

M = pd.DataFrame({"zw_gd": mon["gd"], "zw_nat": mon["nat"], "nx_nat": nx_m.get("全国"), "nx_south": nx_m.get("华南"),
                  "moa_nat": moa_m, "nbs_nat": nbs_m, "gd_slaughter": gd_slaughter, "gd_farm": gd_farm, "nx_gd": nx_gd})
combos = [
    ("中国养猪网广东−中国养猪网全国（同源，本文主口径）", "zw_gd", "zw_nat"),
    ("中国养猪网广东−新牧网全国", "zw_gd", "nx_nat"),
    ("新牧网广东−新牧网全国（2025年起）", "nx_gd", "nx_nat"),
    ("新牧网华南−新牧网全国（区域代理）", "nx_south", "nx_nat"),
    ("广东官方养殖场出栏价−新牧网全国", "gd_farm", "nx_nat"),
    ("广东官方养殖场出栏价−农业农村部集贸价", "gd_farm", "moa_nat"),
    ("广东屠宰企业收购价−新牧网全国", "gd_slaughter", "nx_nat"),
    ("广东屠宰企业收购价−农业农村部集贸价", "gd_slaughter", "moa_nat"),
    ("广东屠宰企业收购价−统计局旬价", "gd_slaughter", "nbs_nat"),
]
src_rows = []
for y in range(2016, last.year + 1):
    for name, a, b in combos:
        s = (M[a] - M[b]).loc[str(y)].dropna()
        if len(s) >= 3:
            src_rows.append(dict(year=y, combo=name, months=len(s), spread_mean=s.mean(), spread_max_month=s.max(),
                                 months_gt2=int((s > 2).sum())))
for name, (a, b) in {"2022年上涨段": ("2022-04-01", "2022-10-31"), "2024年上涨段": ("2024-02-01", "2024-08-31")}.items():
    for cname, ca, cb in combos:
        s = (M[ca] - M[cb]).loc[a:b].dropna()
        if len(s) >= 3:
            src_rows.append(dict(year=name, combo=cname, months=len(s), spread_mean=s.mean(), spread_max_month=s.max(),
                                 months_gt2=int((s > 2).sum())))
sources = pd.DataFrame(src_rows)
sources.to_csv(OUT / "gd_spread_sources.csv", index=False, float_format="%.4f")

chk = []
for name, a, b in [("中国养猪网全国 vs 新牧网全国", "zw_nat", "nx_nat"), ("中国养猪网全国 vs 农业农村部集贸价", "zw_nat", "moa_nat"),
                   ("中国养猪网全国 vs 统计局旬价", "zw_nat", "nbs_nat"), ("中国养猪网广东 vs 新牧网广东", "zw_gd", "nx_gd"),
                   ("中国养猪网广东 vs 广东官方养殖场出栏价", "zw_gd", "gd_farm"),
                   ("中国养猪网广东 vs 广东屠宰企业收购价", "zw_gd", "gd_slaughter")]:
    s = M[[a, b]].dropna()
    chk.append(dict(check=name, months=len(s), first=s.index.min().strftime("%Y-%m") if len(s) else None,
                    last=s.index.max().strftime("%Y-%m") if len(s) else None, mean_gap=(s[a] - s[b]).mean(),
                    mean_abs_gap=(s[a] - s[b]).abs().mean(), corr=s[a].corr(s[b])))
gd_year = zw["gd"].groupby(zw.index.year).mean()
for y, v in WIND_GD.items():
    if isinstance(y, int) and y in gd_year.index:
        chk.append(dict(check=f"中国养猪网广东 vs Wind广东年均价 {y}", months=12, first=str(y), last=str(y),
                        mean_gap=gd_year[y] - v, mean_abs_gap=abs(gd_year[y] - v), corr=np.nan))
q2 = zw.loc["2026-04-01":"2026-06-30", "gd"].resample("MS").mean()
for m, v in zip(q2.index, (9.76, 10.12, 10.25)):  # 国家统计局广东调查总队 大县出栏均价
    chk.append(dict(check=f"中国养猪网广东 vs 广东调查总队大县出栏均价 {m:%Y-%m}", months=1, first=f"{m:%Y-%m}", last=f"{m:%Y-%m}",
                    mean_gap=q2[m] - v, mean_abs_gap=abs(q2[m] - v), corr=np.nan))
check = pd.DataFrame(chk)
check.to_csv(OUT / "gd_source_check.csv", index=False, float_format="%.4f")

# ------------------------------------------------------------------ Dongrui bridge
ps = pd.read_csv(DR / "price_split.csv").set_index("period")
# Dongrui's monthly sales weight (revenue / commodity-hog price), to compare its volume-weighted annual price
# with equally weighted GD and national prices on a like-for-like basis
mz = zw[["nat", "gd"]].resample("MS").mean()
drw = pd.read_csv(PROC / "monthly_sales.csv", dtype={"code": str})
drw = drw[(drw["code"].str.zfill(6) == "001201") & (drw["months_covered"] == 1)].copy()
drw.index = pd.to_datetime(drw["month_key"] + "-01")
drw["kg_w"] = drw["revenue_yi"] / drw["price"]


def window(key):
    return {"2023Q1": ("2023-01-01", "2023-03-31"), "2026Q1": ("2026-01-01", "2026-03-31"),
            "2026H1": ("2026-01-01", "2026-06-30")}.get(key, (f"{key}-01-01", f"{key}-12-31"))


bridge = []
for key, pkey in [(2018, "2018"), (2019, "2019"), (2020, "2020"), (2021, "2021"), (2022, "2022"), ("2023Q1", "2023-Q1"),
                  (2023, "2023"), (2024, "2024"), (2025, "2025"), ("2026Q1", "2026-Q1"), ("2026H1", "2026-H1")]:
    a, b = window(key)
    x = zw.loc[a:b]
    row = dict(period=str(key), national_zw=x["nat"].mean(), gd_zw=x["gd"].mean(),
               national_nx=nx["全国"].loc[a:b].mean(), gd_wind=WIND_GD.get(key))
    wm = drw.loc[a:b, "kg_w"].dropna()
    if len(wm) and len(wm) == len(pd.date_range(a, b, freq="MS")):
        mm = mz.loc[wm.index]
        row["national_zw_w"] = float((mm["nat"] * wm).sum() / wm.sum())
        row["gd_zw_w"] = float((mm["gd"] * wm).sum() / wm.sum())
    p = ps.loc[pkey] if pkey in ps.index else None
    row["dr_export"] = p["export_price"] if p is not None else np.nan
    row["dr_domestic"] = p["domestic_price"] if p is not None else np.nan
    row["dr_blended"] = p["blended_price"] if p is not None else np.nan
    if key in KG:
        tot, dom, exp_own, exp_bought = KG[key]
        row["export_share_w"] = (exp_own + exp_bought) / tot
        row["export_kg_wan"] = exp_own + exp_bought
        row["commodity_kg_wan"] = tot
    elif pkey == "2025":
        row["export_share_w"] = (row["dr_blended"] - row["dr_domestic"]) / (row["dr_export"] - row["dr_domestic"])
    elif pkey == "2026-Q1":
        row["export_share_w"] = (row["dr_blended"] - row["dr_domestic"]) / (row["dr_export"] - row["dr_domestic"])
    row["gd_minus_nat"] = row["gd_zw"] - row["national_zw"]
    row["dom_minus_gd_zw"] = row["dr_domestic"] - row["gd_zw"]
    row["dom_minus_gd_zw_w"] = row["dr_domestic"] - row.get("gd_zw_w", np.nan)
    row["blended_minus_nat_zw_w"] = row["dr_blended"] - row.get("national_zw_w", np.nan)
    row["dom_minus_gd_wind"] = row["dr_domestic"] - row["gd_wind"] if row["gd_wind"] else np.nan
    row["dom_minus_nat_zw"] = row["dr_domestic"] - row["national_zw"]
    row["dom_minus_nat_nx"] = row["dr_domestic"] - row["national_nx"]
    row["exp_minus_dom"] = row["dr_export"] - row["dr_domestic"]
    # blended − domestic, so that blended − national = GD spread + (domestic − GD) + export_contrib exactly;
    # share × (export − domestic) differs where bought-in export hogs settle at another price (2019-2021)
    row["export_contrib"] = row["dr_blended"] - row["dr_domestic"]
    row["blended_minus_nat_zw"] = row["dr_blended"] - row["national_zw"]
    row["blended_minus_nat_nx"] = row["dr_blended"] - row["national_nx"]
    if key in COMMISSION and key in KG:
        row["commission_per_export_kg"] = COMMISSION[key] / (row["export_kg_wan"] * 1e4)
    elif key in COMMISSION and pd.notna(p["export_heads"] if p is not None else np.nan):
        # monthly briefs stop giving commodity heads and weights in 2023; assume 120 kg per export hog
        row["commission_per_export_kg"] = COMMISSION[key] / (p["export_heads"] * EXPORT_KG)
        row["commission_basis"] = f"出口{p['export_heads'] / 1e4:.2f}万头×{EXPORT_KG}公斤（假设）"
    if key == 2023:  # no split disclosed; 2024-03-01 交流记录: "供港价格高出内销价格4元/公斤左右"
        row["exp_minus_dom"] = 4.0
    row["exp_minus_dom_net"] = row["exp_minus_dom"] - row.get("commission_per_export_kg", 0.0)
    bridge.append(row)
bridge = pd.DataFrame(bridge)
bridge.to_csv(OUT / "gd_dongrui_bridge.csv", index=False, float_format="%.4f")

ms = pd.read_csv(PROC / "monthly_sales.csv", dtype={"code": str})
ms = ms[(ms["months_covered"] == 1) & ms["price"].notna()].copy()
ms["year"] = ms["month_key"].str[:4].astype(int)
ms["heads"] = ms["commodity_heads"].fillna(ms["commodity_heads_derived"]).fillna(ms["total_heads"])
ms["w"] = ms["heads"].fillna(1.0)

# ------------------------------------------------------------------ peers: realised price and ROE
rows = []
for name, d in PEERS_INQ.items():
    for y, v in d.items():
        rows.append(dict(year=str(y), name=name, price=v, months=None, source="2023-05问询回复（年报、简报汇总）"))
ann = (ms.groupby(["year", "code", "sec_name"])
         .apply(lambda g: pd.Series({"price": np.average(g["price"], weights=g["w"]), "months": g["month_key"].nunique()}),
                include_groups=False)
         .reset_index())
ann = ann[(ann["months"] >= 9) | ((ann["year"] == last.year) & (ann["months"] >= 6))]
ann["name"] = ann["code"].map(ms.drop_duplicates("code", keep="last").set_index("code")["sec_name"]).str.replace(" ", "")
for r in ann.itertuples():
    if r.year >= 2023:
        rows.append(dict(year=str(r.year), name=r.name, price=r.price, months=r.months, source="月度销售简报（头数加权）"))
peer = pd.DataFrame(rows)
summ = []
for y, g in peer.groupby("year"):
    dr = g[g["name"].str.contains("东瑞")]
    others = g[~g["name"].str.contains("东瑞")]
    if dr.empty or others.empty:
        continue
    v = dr["price"].iloc[0]
    jj = others[others["name"].str.contains("京基")]
    summ.append(dict(year=y, name="（汇总）", price=v, peer_median=others["price"].median(), peer_n=len(others),
                     dongrui_gap=v - others["price"].median(), dongrui_rank=int((g["price"] > v).sum() + 1), n=len(g),
                     jingji_gap=v - jj["price"].iloc[0] if not jj.empty else np.nan, source=dr["source"].iloc[0]))
peer = pd.concat([peer, pd.DataFrame(summ)], ignore_index=True)
peer.to_csv(OUT / "gd_peer_price.csv", index=False, float_format="%.4f")

fq = pd.read_csv(PROC / "fin_quarterly.csv", dtype={"code": str}, parse_dates=["report_date"])
pb_peers = pd.read_csv(OUT / "dongrui_pb_peers.csv", dtype={"code": str})["code"].str.zfill(6)
fq = fq[fq["code"].isin(pb_peers)]  # the 18 hog producers compared in Issue #2
roe = []
for code, g in fq.groupby("code"):
    g = g.set_index("report_date").sort_index()
    for y in range(2019, last.year + 1):
        end = pd.Timestamp(f"{y}-12-31") if y < last.year else pd.Timestamp(f"{y}-06-30")
        beg = pd.Timestamp(f"{y - 1}-12-31")
        if end in g.index and beg in g.index:
            e0, e1 = g.loc[beg, "TOTAL_PARENT_EQUITY"], g.loc[end, "TOTAL_PARENT_EQUITY"]
            ni = g.loc[end, "PARENT_NETPROFIT"]
            roe.append(dict(year=f"{y}" if y < last.year else f"{y}H1", code=code, name=g["name"].iloc[-1],
                            parent_ni_yi=ni / 1e8, roe=ni / np.mean([e0, e1]) if e0 > 0 and e1 > 0 else np.nan,
                            ocf_yi=g.loc[end, "NETCASH_OPERATE"] / 1e8))
roe = pd.DataFrame(roe)
ranks = []
for y, g in roe.groupby("year"):
    g = g.dropna(subset=["roe"])
    if (g.code == "001201").any():
        v = g.loc[g.code == "001201", "roe"].iloc[0]
        ranks.append(dict(year=y, code="（汇总）", name="东瑞股份", roe=v, roe_peer_median=g.loc[g.code != "001201", "roe"].median(),
                          rank=int((g["roe"] > v).sum() + 1), n=len(g), share_profitable=(g["parent_ni_yi"] > 0).mean()))
roe = pd.concat([roe, pd.DataFrame(ranks)], ignore_index=True)
roe.to_csv(OUT / "gd_peer_roe.csv", index=False, float_format="%.4f")

# ------------------------------------------------------------------ 2027 scenarios at national 18
NAT27, KG27 = 18.0, 160 * 115 / 1e4           # 肉猪160万头 x 115公斤 = 1.84亿公斤 (main-report base volume)
COST = {"完全成本12.9（基准）": 12.9, "完全成本13.5": 13.5, "完全成本12.5（公司目标）": 12.5}
ph = periods.set_index("period")
ols22 = next(r for r in reg_rows if r["regime"] == "2022年后" and r["bucket"] == "OLS spread~national (monthly)")
cases = {
    "回落至非瘟前（2015-12—2018-07均值）": ph.loc["非瘟前", "spread_mean"],
    "维持当前（2026年至今均值）": ph.loc["2026年至今", "spread_mean"],
    "按2022年后月度关系外推至18元": ols22["intercept"] + ols22["slope"] * NAT27,
    "恢复历史可比（2022、2024年上涨段均值的平均）": (ph.loc["2022年上涨段", "spread_mean"] + ph.loc["2024年上涨段", "spread_mean"]) / 2,
    "进一步扩大（2022年上涨段均值）": ph.loc["2022年上涨段", "spread_mean"],
}
# Dongrui: blended − national = (1−s)(GD spread + basis) + s(GD spread + basis + e) = GD spread + basis + s·e,
# basis = Dongrui domestic − Guangdong average (same source), s = export share by weight, e = export premium over domestic
# basis against the volume-weighted GD price: in 2025 volume rose while prices fell, which a flat-price year does not have
recent = bridge[bridge.period.isin(["2025", "2026Q1"])]
basis = float(recent["dom_minus_gd_zw_w"].mean())
EXPORT = {"出口占比15%、出口溢价1.8元（基准）": (0.15, 1.8), "出口占比12%、出口溢价1.1元": (0.12, 1.1),
          "出口占比20%、出口溢价2.5元": (0.20, 2.5)}
REF_ISSUE2 = 0.0777 * NAT27
sc = []
for cname, spread in cases.items():
    for ename, (s, e) in EXPORT.items():
        prem = spread + basis + s * e
        for kname, cost in COST.items():
            sc.append(dict(national=NAT27, spread_case=cname, gd_spread=spread, domestic_basis=basis, export_case=ename,
                           export_share=s, export_premium=e, dongrui_premium=prem, dongrui_premium_ratio=prem / NAT27,
                           cost_case=kname, cost=cost, hog_profit_yi=(NAT27 + prem - cost) * KG27,
                           premium_profit_yi=prem * KG27, premium_share_of_profit=prem / (NAT27 + prem - cost),
                           vs_issue2_yi=(prem - REF_ISSUE2) * KG27))
for ref, prem in [("Issue #2口径：售价溢价7.8%（2026年1—8月实际比例）×18", REF_ISSUE2),
                  ("主模型基准：内销+3%、出口占比16%×出口溢价2.5元", 0.03 * NAT27 + 0.16 * 2.5),
                  ("无溢价", 0.0)]:
    for kname, cost in COST.items():
        sc.append(dict(national=NAT27, spread_case=ref, dongrui_premium=prem, dongrui_premium_ratio=prem / NAT27, cost_case=kname,
                       cost=cost, hog_profit_yi=(NAT27 + prem - cost) * KG27, premium_profit_yi=prem * KG27,
                       premium_share_of_profit=prem / (NAT27 + prem - cost), vs_issue2_yi=(prem - REF_ISSUE2) * KG27))
scen = pd.DataFrame(sc)
# national price at which 2027 parent net profit reaches 10亿: Issue #2 grid (premium 7.8% of the national price),
# with only the premium term swapped for the absolute premium of each case
ds = pd.read_csv(OUT / "dongrui_scenarios.csv")
ds = ds[ds["premium_case"].str.startswith("溢价中")]


def solve(target, ni, nat):
    ni, nat = np.asarray(ni, float), np.asarray(nat, float)
    if target > ni[-1]:  # beyond the grid: extend the last segment
        return float(nat[-2] + (target - ni[-2]) * (nat[-1] - nat[-2]) / (ni[-1] - ni[-2]))
    return float(np.interp(target, ni, nat))


def national_for_ni(target, prem_abs, cost, swap=True):
    g = ds[np.isclose(ds["cost"], cost)].sort_values("national")
    ni = g["parent_ni_yi"] - ((g["national"] * g["premium"] - prem_abs) * KG27 if swap else 0.0)
    return solve(target, ni, g["national"]) if len(g) and ni.is_monotonic_increasing else np.nan


scen["national_for_ni_10yi"] = [national_for_ni(10.0, p, c, not s.startswith("Issue #2"))
                                for p, c, s in zip(scen["dongrui_premium"], scen["cost"], scen["spread_case"])]
scen.to_csv(OUT / "gd_scenarios_2027.csv", index=False, float_format="%.4f")

# Issue #2 recheck with the absolute premiums: snapshot-implied national price at 10x 2027 earnings
# (realised price held fixed, Issue #2 used the main-model base premium) and the 18-yuan parent net profit
pbp = pd.read_csv(OUT / "dongrui_pb_peers.csv", dtype={"code": str})
imp10 = float(pbp.loc[pbp["code"].str.zfill(6) == "001201", "implied_national_10x"].iloc[0])
px_real = imp10 * 1.03 + 0.16 * 2.5
base_sc = scen[scen["export_case"].fillna("").str.contains("基准") & np.isclose(scen["cost"], 12.9)]
rc = [dict(item="现价隐含2027年全国均价（10倍市盈率）", premium_case="Issue #2（主模型基准：内销+3%、出口16%×2.5元）",
           dongrui_premium=px_real - imp10, value=imp10)]
for _, r in base_sc.iterrows():
    if r["spread_case"].startswith("按2022年后"):  # spread depends on the level: solve n = px_real - (a + b n + basis + s e)
        n = (px_real - ols22["intercept"] - basis - r["export_share"] * r["export_premium"]) / (1 + ols22["slope"])
        rc.append(dict(item="现价隐含2027年全国均价（10倍市盈率）", premium_case=r["spread_case"], dongrui_premium=px_real - n, value=n))
    else:
        rc.append(dict(item="现价隐含2027年全国均价（10倍市盈率）", premium_case=r["spread_case"], dongrui_premium=r["dongrui_premium"],
                       value=px_real - r["dongrui_premium"]))
for _, g in ds[np.isclose(ds["national"], NAT27)].iterrows():
    item = f"2027年全国18元归母净利润（亿元，成本{g['cost']:.1f}）"
    rc.append(dict(item=item, premium_case="Issue #2（售价溢价7.8%）", dongrui_premium=NAT27 * g["premium"], value=g["parent_ni_yi"]))
    for _, r in base_sc.iterrows():
        rc.append(dict(item=item, premium_case=r["spread_case"], dongrui_premium=r["dongrui_premium"],
                       value=g["parent_ni_yi"] - (NAT27 * g["premium"] - r["dongrui_premium"]) * KG27))
recheck = pd.DataFrame(rc)
recheck.to_csv(OUT / "gd_issue2_recheck.csv", index=False, float_format="%.4f")

# ------------------------------------------------------------------ print
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
print(f"zhuwang: {len(zw)} obs {zw.index.min().date()} .. {last.date()}, provinces/obs median {zw.n_prov.median():.0f}")
print(periods.round(2).to_string(index=False))
print(yearly[["year", "n_obs", "national_mean", "gd_mean", "spread_mean", "ratio_mean", "spread_max", "spread_max_date", "share_gt2",
              "longest_gt2_days", "gd_output_share", "gd_minus_henan", "gd_minus_guangxi", "gd_minus_hunan",
              "gd_minus_jiangxi"]].round(3).to_string(index=False))
print(level.round(3).to_string(index=False))
print(season.pivot_table(index="month", columns="regime", values="spread_mean").round(2).to_string())
print(sources.round(2).to_string(index=False))
print(check.round(3).to_string(index=False))
print(bridge.round(2).T.to_string())
print(peer[peer.name == "（汇总）"].round(2).to_string(index=False))
print(roe[roe.code == "（汇总）"].round(3).to_string(index=False))
print(f"domestic basis (Dongrui domestic - volume-weighted zhuwang GD, 2025 & 2026Q1) {basis:.2f}")
print(scen[(scen.cost == 12.9) & (scen.export_case.isna() | scen.export_case.str.contains("基准", na=False))]
      [["spread_case", "gd_spread", "dongrui_premium", "dongrui_premium_ratio", "hog_profit_yi", "premium_profit_yi",
        "premium_share_of_profit", "vs_issue2_yi", "national_for_ni_10yi"]].round(3).to_string(index=False))
print(scen[scen.export_case.isna() | scen.export_case.str.contains("基准", na=False)]
      .pivot_table(index="spread_case", columns="cost", values="national_for_ni_10yi").round(2).to_string())
print(scen[scen.cost == 12.9].pivot_table(index="spread_case", columns="export_case", values="dongrui_premium").round(2).to_string())
