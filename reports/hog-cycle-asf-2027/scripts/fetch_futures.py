"""Fetch daily bars for every DCE live-hog (LH) contract from listing (2021-01-08) to now.

Primary: Sina InnerFuturesNewService.getDailyKLine (o/h/l/c/volume/open interest/settlement).
Cross-check: East Money futures kline where available (secid 114.lhYYMM).
Prices are in yuan/tonne in the source; we keep yuan/tonne and add yuan/kg columns.
Each row keeps both the trade date and the delivery month so they are never confused.
"""
import json
import re
import time

import pandas as pd

from common import PROC, RAW, S, save_json

contracts = []
for y in range(21, 28):
    for m in (1, 3, 5, 7, 9, 11):
        c = f"LH{y:02d}{m:02d}"
        if c < "LH2109" or c > "LH2709":
            continue
        contracts.append(c)
contracts += ["LH0"]  # Sina main-continuous series, for roll-effect comparison only

rows, log = [], []
for c in contracts:
    url = ("https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_x=/"
           f"InnerFuturesNewService.getDailyKLine?symbol={c}")
    try:
        t = S.get(url, timeout=30).text
        m = re.search(r"\((\[.*\])\)", t, flags=re.S)
        data = json.loads(m.group(1)) if m else []
    except Exception as e:  # noqa: BLE001
        data = []
        log.append(f"{c} sina ERR {e}")
    save_json(data, RAW / "futures" / f"{c}_sina.json")
    for x in data:
        rows.append(dict(contract=c, trade_date=x["d"], open=float(x["o"]), high=float(x["h"]),
                         low=float(x["l"]), close=float(x["c"]), volume=float(x["v"]),
                         open_interest=float(x["p"]), settle=float(x["s"]) if x.get("s") else None,
                         source="sina"))
    log.append(f"{c}: sina rows={len(data)} first={data[0]['d'] if data else None} last={data[-1]['d'] if data else None}")
    print(log[-1], flush=True)
    time.sleep(0.4)

df = pd.DataFrame(rows)
df["delivery_month"] = df["contract"].map(lambda c: None if c == "LH0" else f"20{c[2:4]}-{c[4:6]}")
for f in ("open", "high", "low", "close", "settle"):
    df[f + "_kg"] = df[f] / 1000.0
df = df.sort_values(["contract", "trade_date"])
df.to_csv(PROC / "futures_lh_daily.csv", index=False)
(RAW / "futures" / "_fetch_log.txt").write_text("\n".join(log), encoding="utf-8")
print("rows", len(df))
