"""When did each company spend? Capex, productive biological assets (PBA) and construction in
progress (CIP) by quarter, bucketed into price regimes, plus 2021-2022 impairments.

Capex = cash paid to acquire/construct long-term assets (CONSTRUCT_LONG_ASSET), single-quarter.
PBA (生产性生物资产) is a book-value proxy for breeding herd investment, not a head count.
Buckets are defined by spot-price regime (nxin national), not by stock prices:
  P1 2018Q1-2019Q2  pre-surge / early ASF (spot mostly < 16 yuan/kg)
  P2 2019Q3-2020Q2  surge; breeding stock scarce and expensive
  P3 2020Q3-2021Q2  still high prices; capacity race
  P4 2021Q3-2022Q4  supply recovery, low prices
"""
import numpy as np
import pandas as pd

from common import PROC

fin = pd.read_csv(PROC / "fin_quarterly.csv", dtype={"code": str})
uni = pd.read_csv(PROC / "universe.csv", dtype=str)
name = dict(zip(uni.code, uni.name))
spot = pd.read_csv(PROC / "nxin_price_wide.csv", index_col=0, parse_dates=True)["全国"]
spot_q = spot.groupby(spot.index.to_period("Q")).mean()

HIST = ["002714", "300498", "002157", "002124", "000876", "002477", "002567", "600975", "603363",
        "002548", "002385", "002100", "000735", "000048", "002840"]
BUCKET = {"P1 2018Q1-19Q2 低位/疫情初期": ("2018-03-31", "2019-06-30"),
          "P2 2019Q3-20Q2 高价初期": ("2019-09-30", "2020-06-30"),
          "P3 2020Q3-21Q2 高位扩张": ("2020-09-30", "2021-06-30"),
          "P4 2021Q3-22Q4 下行期": ("2021-09-30", "2022-12-31")}

f = fin[fin.code.isin(HIST) & (fin.report_date >= "2017-03-31") & (fin.report_date <= "2022-12-31")].copy()
f["period"] = pd.PeriodIndex(pd.to_datetime(f.report_date), freq="Q")
f["spot_q"] = f["period"].map(spot_q)
q = f[["code", "report_date", "period", "spot_q", "CONSTRUCT_LONG_ASSET_Q", "PRODUCTIVE_BIOLOGY_ASSET", "CIP",
       "FIXED_ASSET", "ASSET_IMPAIRMENT_INCOME_Q", "PARENT_NETPROFIT_Q", "TOTAL_ASSETS", "TOTAL_LIABILITIES",
       "interest_bearing_debt", "MONETARYFUNDS", "NETCASH_OPERATE_Q"]].copy()
q["name"] = q.code.map(name)
q.to_csv(PROC / "expansion_quarterly.csv", index=False)

rows = []
for code, g in q.groupby("code"):
    g = g.set_index("report_date").sort_index()
    tot = g.loc["2018-03-31":"2022-12-31", "CONSTRUCT_LONG_ASSET_Q"].sum(min_count=1)
    r = dict(code=code, name=name.get(code), capex_2018_2022_yi=tot / 1e8)
    for b, (a, z) in BUCKET.items():
        s = g.loc[a:z, "CONSTRUCT_LONG_ASSET_Q"].sum(min_count=1)
        r["capex_" + b[:2]] = s / 1e8
        r["share_" + b[:2]] = s / tot if tot else np.nan
    def at(d, col):
        return g[col].get(d, np.nan) / 1e8
    r["pba_2018Q2"] = at("2018-06-30", "PRODUCTIVE_BIOLOGY_ASSET")
    r["pba_2019Q2"] = at("2019-06-30", "PRODUCTIVE_BIOLOGY_ASSET")
    r["pba_2020Q2"] = at("2020-06-30", "PRODUCTIVE_BIOLOGY_ASSET")
    r["pba_2021Q2"] = at("2021-06-30", "PRODUCTIVE_BIOLOGY_ASSET")
    r["pba_2022Q4"] = at("2022-12-31", "PRODUCTIVE_BIOLOGY_ASSET")
    r["impair_2021_2022_yi"] = g.loc["2021-03-31":"2022-12-31", "ASSET_IMPAIRMENT_INCOME_Q"].sum(min_count=1) / 1e8
    r["np_2019_yi"] = g.loc["2019-03-31":"2019-12-31", "PARENT_NETPROFIT_Q"].sum(min_count=1) / 1e8
    r["np_2020_yi"] = g.loc["2020-03-31":"2020-12-31", "PARENT_NETPROFIT_Q"].sum(min_count=1) / 1e8
    r["np_2021_yi"] = g.loc["2021-03-31":"2021-12-31", "PARENT_NETPROFIT_Q"].sum(min_count=1) / 1e8
    r["np_2022_yi"] = g.loc["2022-03-31":"2022-12-31", "PARENT_NETPROFIT_Q"].sum(min_count=1) / 1e8
    r["debt_ratio_2018Q2"] = g["TOTAL_LIABILITIES"].get("2018-06-30", np.nan) / g["TOTAL_ASSETS"].get("2018-06-30", np.nan)
    r["debt_ratio_2021Q4"] = g["TOTAL_LIABILITIES"].get("2021-12-31", np.nan) / g["TOTAL_ASSETS"].get("2021-12-31", np.nan)
    r["debt_ratio_2022Q4"] = g["TOTAL_LIABILITIES"].get("2022-12-31", np.nan) / g["TOTAL_ASSETS"].get("2022-12-31", np.nan)
    rows.append(r)
s = pd.DataFrame(rows).sort_values("capex_2018_2022_yi", ascending=False)
s.to_csv(PROC / "expansion_buckets.csv", index=False)
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
print(s.round(3).to_string(index=False))
print(spot_q.loc["2018Q1":"2022Q4"].round(2).to_string())
