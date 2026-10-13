"""Daily closes of CSI indices from www.csindex.com.cn (full history from 2005) -> csi_index_daily.csv

  000985 中证全指: market benchmark for excess returns (East Money / Tencent only reach back to 2011)
  930707 中证畜牧养殖: an external sector index, used as a cross-check of our own hog-stock index
Local only (third-party series, see .gitignore).
"""
import json
import sys

import pandas as pd

from common import PROC, RAW, S

END = sys.argv[1] if len(sys.argv) > 1 else "20261013"
CODES = {"000985": "中证全指", "930707": "中证畜牧养殖"}
rows = []
for code, name in CODES.items():
    url = ("https://www.csindex.com.cn/csindex-home/perf/index-perf"
           f"?indexCode={code}&startDate=20050101&endDate={END}")
    j = S.get(url, timeout=60, headers={"Referer": "https://www.csindex.com.cn/"}).json()
    (RAW / "csindex").mkdir(parents=True, exist_ok=True)
    (RAW / "csindex" / f"{code}_{END}.json").write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
    for x in j.get("data") or []:
        rows.append(dict(index=code, name=name, date=pd.Timestamp(x["tradeDate"]).date(), open=x["open"],
                         high=x["high"], low=x["low"], close=x["close"], cons=x.get("consNumber")))
    print(code, name, len(j.get("data") or []))
df = pd.DataFrame(rows)
df = df[pd.to_datetime(df["date"]).dt.dayofweek < 5]
df.sort_values(["index", "date"]).to_csv(PROC / "csi_index_daily.csv", index=False)
print(df.groupby("name")["date"].agg(["min", "max", "count"]))
