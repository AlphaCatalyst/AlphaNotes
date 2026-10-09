"""Fetch consolidated quarterly statements (balance sheet / income / cash flow) from East Money F10.

Values are cumulative report-period figures as filed (Q1, H1, 9M, FY).
Raw JSON is cached per company; a tidy CSV with the fields used in the report is written to
data/processed/fin_quarterly.csv.
"""
import time

import pandas as pd

from common import PROC, RAW, em_report_dates, em_statement, save_json

uni = pd.read_csv(PROC / "universe.csv", dtype=str)
codes = [c for c, m in zip(uni["code"], uni["market"]) if m.startswith("A")]

FIELDS = {
    "zcfzb": ["MONETARY_FUNDS", "SHORT_LOAN", "NONCURRENT_LIAB_1YEAR", "LONG_LOAN", "BOND_PAYABLE",
              "LEASE_LIAB", "LONG_PAYABLE", "TOTAL_ASSETS", "TOTAL_LIABILITIES", "MINORITY_EQUITY",
              "TOTAL_PARENT_EQUITY", "PRODUCTIVE_BIOLOGY_ASSET", "INVENTORY", "CIP", "FIXED_ASSET",
              "SHARE_CAPITAL", "USERIGHT_ASSET", "NOTE_ACCOUNTS_PAYABLE", "ACCOUNTS_PAYABLE",
              "TOTAL_CURRENT_LIAB", "TOTAL_CURRENT_ASSETS", "TRADE_FINASSET_NOTFVTPL", "GOODWILL"],
    "lrb": ["TOTAL_OPERATE_INCOME", "OPERATE_INCOME", "PARENT_NETPROFIT", "NETPROFIT", "MINORITY_INTEREST",
            "ASSET_IMPAIRMENT_INCOME", "CREDIT_IMPAIRMENT_INCOME", "FINANCE_EXPENSE", "FE_INTEREST_EXPENSE",
            "OPERATE_COST"],
    "xjllb": ["NETCASH_OPERATE", "CONSTRUCT_LONG_ASSET", "END_CCE", "NETCASH_INVEST", "NETCASH_FINANCE",
              "ASSIGN_DIVIDEND_PORFIT"],
}

rows = []
for code in codes:
    rec = {}
    for kind in ("zcfzb", "lrb", "xjllb"):
        try:
            dates = [d for d in em_report_dates(code, kind) if d >= "2015-12-31"]
            data = em_statement(code, kind, dates)
        except Exception as e:  # noqa: BLE001
            print(code, kind, "ERR", e, flush=True)
            data = []
        save_json(data, RAW / "fin" / f"{code}_{kind}.json")
        for x in data:
            d = x["REPORT_DATE"][:10]
            r = rec.setdefault(d, {"code": code, "report_date": d})
            r["notice_date_" + kind] = (x.get("NOTICE_DATE") or "")[:10]
            for f in FIELDS[kind]:
                if f in x:
                    r[f] = x[f]
        time.sleep(0.3)
    rows.extend(rec.values())
    print(code, len(rec), flush=True)

df = pd.DataFrame(rows).sort_values(["code", "report_date"])
df.to_csv(PROC / "fin_quarterly.csv", index=False)
print("rows", len(df))
