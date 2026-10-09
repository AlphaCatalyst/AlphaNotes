"""Fill missing stock downloads (slow, with retries) and rebuild stock_daily.csv from the cache.

For every code we want: em_raw, em_hfq, and (A-shares) tx_hfq + tx_raw.
"""
import json
import sys
import time

import pandas as pd

from common import PROC, RAW, em_kline, load_json, save_json, tx_kline

uni = pd.read_csv(PROC / "universe.csv", dtype=str)
D = RAW / "stocks"
refetch = "--no-fetch" not in sys.argv


def have(code, tag):
    p = D / f"{code}_{tag}.json"
    return p.exists() and len(load_json(p)) > 0


if refetch:
    for _, u in uni.iterrows():
        code, hk = u["code"], u["market"] == "HK"
        jobs = [("em_raw", lambda c=code: em_kline(c, 0, "20050101", "20261231")[1]),
                ("em_hfq", lambda c=code: em_kline(c, 2, "20050101", "20261231")[1])]
        if not hk and "--em-only" not in sys.argv:
            jobs += [("tx_hfq", lambda c=code: tx_kline(c, "hfq", "2005-01-01", "2026-12-31")),
                     ("tx_raw", lambda c=code: tx_kline(c, "", "2005-01-01", "2026-12-31"))]
        for tag, fn in jobs:
            if have(code, tag):
                continue
            if tag == "tx_raw" and have(code, "em_raw"):
                continue
            for attempt in range(4):
                try:
                    k = fn()
                    if k:
                        save_json(k, D / f"{code}_{tag}.json")
                        print(code, tag, len(k), flush=True)
                        break
                except Exception as e:  # noqa: BLE001
                    print(code, tag, "ERR", e, flush=True)
                time.sleep(3 * (attempt + 1))
            time.sleep(1.0)

rows = []
for _, u in uni.iterrows():
    code = u["code"]
    by = {}
    for tag in ("em_raw", "em_hfq", "tx_hfq", "tx_raw"):
        p = D / f"{code}_{tag}.json"
        if not p.exists():
            continue
        for x in load_json(p):
            d = by.setdefault(x["date"], {"code": code, "name": u["name"], "date": x["date"]})
            suffix = {"em_raw": "raw", "em_hfq": "hfq", "tx_hfq": "tx_hfq", "tx_raw": "tx_raw"}[tag]
            for f in ("open", "high", "low", "close"):
                d[f"{f}_{suffix}"] = x[f]
            if tag == "em_raw":
                d["volume"], d["amount"], d["turnover"] = x.get("volume"), x.get("amount"), x.get("turnover")
            elif tag == "tx_raw" and "volume" not in d:
                d["volume"] = x.get("volume")
    rows.extend(by.values())
    print(code, u["name"], len(by), {t: (D / f"{code}_{t}.json").exists() for t in ("em_raw", "em_hfq", "tx_hfq", "tx_raw")})
df = pd.DataFrame(rows).sort_values(["code", "date"])
df.to_csv(PROC / "stock_daily.csv", index=False)
print("rows", len(df))
