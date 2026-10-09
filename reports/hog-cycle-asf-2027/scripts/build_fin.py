"""Rebuild the tidy quarterly financial table from cached East Money F10 JSON (no network).

Cumulative report-period flows (income / cash flow) are also converted to single-quarter values.
Units: yuan (as filed). Report dates are period ends; notice_date is the filing date.
"""
import json

import numpy as np
import pandas as pd

from common import PROC, RAW

FIELDS = {
    "zcfzb": ["MONETARYFUNDS", "SHORT_LOAN", "NONCURRENT_LIAB_1YEAR", "LONG_LOAN", "BOND_PAYABLE",
              "LEASE_LIAB", "LONG_PAYABLE", "TOTAL_ASSETS", "TOTAL_LIABILITIES", "MINORITY_EQUITY",
              "TOTAL_PARENT_EQUITY", "PRODUCTIVE_BIOLOGY_ASSET", "INVENTORY", "CIP", "FIXED_ASSET",
              "SHARE_CAPITAL", "USERIGHT_ASSET", "NOTE_ACCOUNTS_PAYABLE", "TOTAL_CURRENT_LIAB",
              "TOTAL_CURRENT_ASSETS", "GOODWILL", "OTHER_NONCURRENT_ASSET", "TRADE_FINASSET",
              "TRADE_FINASSET_NOTFVTPL", "NOTE_PAYABLE", "OTHER_CURRENT_LIAB", "PREFERRED_SHARES",
              "PERPETUAL_BOND", "OTHER_EQUITY_TOOL"],
    "lrb": ["TOTAL_OPERATE_INCOME", "OPERATE_INCOME", "OPERATE_COST", "PARENT_NETPROFIT", "NETPROFIT",
            "MINORITY_INTEREST", "ASSET_IMPAIRMENT_INCOME", "CREDIT_IMPAIRMENT_INCOME", "FINANCE_EXPENSE",
            "FE_INTEREST_EXPENSE", "DEDUCT_PARENT_NETPROFIT", "OPERATE_PROFIT", "INCOME_TAX"],
    "xjllb": ["NETCASH_OPERATE", "CONSTRUCT_LONG_ASSET", "END_CCE", "NETCASH_INVEST", "NETCASH_FINANCE",
              "ASSIGN_DIVIDEND_PORFIT", "DISPOSAL_LONG_ASSET", "ASSET_IMPAIRMENT"],
}
FLOW = FIELDS["lrb"] + [f for f in FIELDS["xjllb"] if f != "END_CCE"]

uni = pd.read_csv(PROC / "universe.csv", dtype=str)
rows = []
for code in uni["code"]:
    rec = {}
    for kind, fl in FIELDS.items():
        p = RAW / "fin" / f"{code}_{kind}.json"
        if not p.exists():
            continue
        for x in json.loads(p.read_text(encoding="utf-8")):
            d = x["REPORT_DATE"][:10]
            r = rec.setdefault(d, {"code": code, "name": x.get("SECURITY_NAME_ABBR"), "report_date": d})
            r[f"notice_{kind}"] = (x.get("NOTICE_DATE") or "")[:10]
            for f in fl:
                if f in x and x[f] is not None:
                    r[f] = x[f]
    rows.extend(rec.values())

df = pd.DataFrame(rows).sort_values(["code", "report_date"]).reset_index(drop=True)
df["year"] = df["report_date"].str[:4].astype(int)
df["q"] = df["report_date"].str[5:7].map({"03": 1, "06": 2, "09": 3, "12": 4})

# single-quarter flows from cumulative values
for f in FLOW:
    if f not in df:
        continue
    df[f + "_Q"] = np.nan
    for (code, yr), g in df.groupby(["code", "year"]):
        g = g.sort_values("q")
        prev = 0.0
        prev_q = 0
        for i, r in g.iterrows():
            v = r[f]
            if pd.isna(v):
                prev_q = r["q"]
                prev = np.nan
                continue
            if r["q"] == 1:
                df.at[i, f + "_Q"] = v
            elif r["q"] == prev_q + 1 and pd.notna(prev):
                df.at[i, f + "_Q"] = v - prev
            prev, prev_q = v, r["q"]

debt_cols = ["SHORT_LOAN", "NONCURRENT_LIAB_1YEAR", "LONG_LOAN", "BOND_PAYABLE", "LEASE_LIAB"]
df["interest_bearing_debt"] = df[debt_cols].fillna(0).sum(axis=1)
df["debt_ratio"] = df["TOTAL_LIABILITIES"] / df["TOTAL_ASSETS"]
df.to_csv(PROC / "fin_quarterly.csv", index=False)
print(df.groupby("code").report_date.agg(["min", "max", "count"]))
print(df[df.code == "002714"][["report_date", "MONETARYFUNDS", "SHORT_LOAN", "PRODUCTIVE_BIOLOGY_ASSET",
                                 "CONSTRUCT_LONG_ASSET", "CONSTRUCT_LONG_ASSET_Q"]].tail(8))
