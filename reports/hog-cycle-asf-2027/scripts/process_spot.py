"""Tidy nxin weekly hog index / transaction price (national + South China region).

nxin timestamps are UTC milliseconds that correspond to 00:00 Beijing time of the week label,
so we convert with +8h. Column 6 is the weekly transaction price (yuan/kg); column 1 the index.
South China (华南, regionId=5) covers Guangdong/Guangxi/Hainan and is only a proxy for Guangdong.
"""
import datetime as dt

import pandas as pd

from common import PROC, RAW, S, load_json, save_json

REGIONS = {0: "全国", 1: "东北", 2: "华北", 3: "华中", 4: "华东", 5: "华南", 6: "西北", 7: "西南"}
rows = []
for rid, name in REGIONS.items():
    p = RAW / "spot" / f"nxin_region_{rid}.json"
    if not p.exists():
        d = S.get(f"https://hqb.nxin.com/pigindex/getPigIndexChart.shtml?regionId={rid}", timeout=30).json()
        save_json(d, p)
    d = load_json(p)
    for x in d["data"]:
        t = dt.datetime.fromtimestamp(x[0] / 1000, dt.timezone.utc) + dt.timedelta(hours=8)
        rows.append(dict(week_label=t.date().isoformat(), region=name, region_id=rid,
                         index=x[1], price=x[6] if x[6] not in (None, 0, 0.0) else None))
df = pd.DataFrame(rows).sort_values(["region_id", "week_label"])
df.to_csv(PROC / "nxin_region_weekly.csv", index=False)
w = df.pivot_table(index="week_label", columns="region", values="price")
w["华南-全国"] = w["华南"] - w["全国"]
w.to_csv(PROC / "nxin_price_wide.csv")
print(df.groupby("region").week_label.agg(["min", "max", "count"]))
print(w.tail(3))
