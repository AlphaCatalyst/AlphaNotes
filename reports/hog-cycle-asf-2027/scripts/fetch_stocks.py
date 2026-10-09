"""Fetch daily bars for the research universe.

Primary: East Money raw (fqt=0) and backward-adjusted (fqt=2) bars.
Cross-check: Tencent backward-adjusted bars (A-shares only).
Output: data/processed/stock_daily.csv (long format, one row per code-date).
"""
import csv
import time

import pandas as pd

from common import PROC, RAW, em_kline, save_json, tx_kline

uni = pd.read_csv(PROC / "universe.csv", dtype=str)
rows = []
log = []
for _, u in uni.iterrows():
    code = u["code"]
    is_hk = u["market"] == "HK"
    got = {}
    for fqt, tag in [(0, "raw"), (2, "hfq")]:
        try:
            name, k = em_kline(code, fqt=fqt, beg="20050101", end="20261231")
        except Exception as e:  # noqa: BLE001
            name, k = None, []
            log.append(f"{code} em {tag} ERR {e}")
        if k:
            save_json(k, RAW / "stocks" / f"{code}_em_{tag}.json")
        got[tag] = k
        time.sleep(0.3)
    if not is_hk:
        try:
            tk = tx_kline(code, "hfq", beg="2005-01-01", end="2026-12-31")
            save_json(tk, RAW / "stocks" / f"{code}_tx_hfq.json")
        except Exception as e:  # noqa: BLE001
            tk = []
            log.append(f"{code} tx hfq ERR {e}")
        got["tx_hfq"] = tk
        if not got["raw"]:
            try:
                traw = tx_kline(code, "", beg="2005-01-01", end="2026-12-31")
                save_json(traw, RAW / "stocks" / f"{code}_tx_raw.json")
                got["tx_raw"] = traw
            except Exception as e:  # noqa: BLE001
                log.append(f"{code} tx raw ERR {e}")
    by = {}
    for tag, k in got.items():
        for x in k:
            d = by.setdefault(x["date"], {"code": code, "name": u["name"], "date": x["date"]})
            for f in ("open", "high", "low", "close"):
                d[f"{f}_{tag}"] = x[f]
            if tag in ("raw", "tx_raw"):
                d["volume"] = x.get("volume")
                d["amount"] = x.get("amount")
                d["turnover"] = x.get("turnover")
    rows.extend(by.values())
    log.append(f"{code} {u['name']}: " + ", ".join(f"{t}={len(k)}" for t, k in got.items()))
    print(log[-1], flush=True)

df = pd.DataFrame(rows).sort_values(["code", "date"])
df.to_csv(PROC / "stock_daily.csv", index=False, quoting=csv.QUOTE_MINIMAL)
(RAW / "stocks" / "_fetch_log.txt").write_text("\n".join(log), encoding="utf-8")
print("rows", len(df))
