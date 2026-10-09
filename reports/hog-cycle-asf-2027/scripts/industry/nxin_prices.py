"""农信网 (hqb.nxin.com) hog index and provincial quotes.

1. 生猪市场(交易)价格指数, weekly (published Mondays):
   /pigindex/getPigIndexChart.shtml?regionId=R -> [[ts_ms, index, MA4, MA6, MA12, chg, 成交均价, 成交均重], ...]
   regionId only exists for 0=全国 and the seven regions 1..7 (list in /pigindex/getPigIndex.shtml);
   province codes (440000, 44, nxin areaIds ...) return {"data": []}. Guangdong is inside 5=华南.
   ts_ms is 00:00 Beijing time of the Monday week label (UTC+8).
2. 查猪价 provincial quotes, daily, 生猪(外三元) goodsId=1:
   /hqb/chq.shtml?...queryPriceVo.areaId=A&queryPriceVo.whatTime=365 returns "MM-DD" dates with
   data1 = current calendar year and data2 = previous year (labels year / year-1 in chartsList.js),
   so only the last two calendar years are reachable. areaIds come from /hqb/queryPigPrice.shtml
   (广东省=15591, 河南省=25475, 四川省=4771, 湖南省=31233, 广西=17313, 全国=100000).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ind_common import PROC, decode, fetch, soup, write_csv  # noqa: E402

SUB = "nxin"
REGIONS = {0: "全国", 1: "东北", 2: "华北", 3: "华中", 4: "华东", 5: "华南", 6: "西北", 7: "西南"}
BASE = "https://hqb.nxin.com"


def unwrap(v):
    """Highlighted (max/min) chart points come as "{'y': 17.0, 'marker': {...}}" strings or dicts."""
    if isinstance(v, dict):
        return v.get("y")
    if isinstance(v, str) and v.lstrip().startswith("{"):
        m = re.search(r"['\"]y['\"]\s*:\s*(-?\d+(?:\.\d+)?)", v)
        return float(m.group(1)) if m else None
    return v


def index_weekly() -> pd.DataFrame:
    # evidence of the regionId list
    fetch(f"{BASE}/pigindex/getPigIndex.shtml?regionId=0", SUB, name="getPigIndex_region0.html", force=True)
    fetch(f"{BASE}/pigindex/getRegionPigIndex.shtml", SUB, name="getRegionPigIndex.html", force=True)
    rows = []
    for rid, name in REGIONS.items():
        url = f"{BASE}/pigindex/getPigIndexChart.shtml?regionId={rid}"
        b = fetch(url, SUB, name=f"getPigIndexChart_regionId_{rid}.json", force=True)
        for x in json.loads(decode(b))["data"]:
            t = dt.datetime.fromtimestamp(x[0] / 1000, dt.timezone.utc) + dt.timedelta(hours=8)
            d = t.date().isoformat()
            rows.append(dict(date=d, region=name, region_id=rid, index=x[1],
                             price=x[6] if x[6] not in (None, 0, 0.0) else None,
                             avg_weight_kg=x[7] if x[7] not in (None, 0, 0.0) else None,
                             index_chg=x[5], week_label=d, source_url=url))
    # province codes tried for the index API (all empty -> documented)
    probes = []
    for rid in (440000, 44, 15591, 410000, 25475):
        url = f"{BASE}/pigindex/getPigIndexChart.shtml?regionId={rid}"
        b = fetch(url, SUB, name=f"getPigIndexChart_regionId_{rid}.json", force=True, ok_min_bytes=5)
        probes.append(dict(regionId=rid, n_points=len(json.loads(decode(b)).get("data", [])) if b else None))
    print("province-code probes on index API:", probes)
    df = pd.DataFrame(rows).sort_values(["region_id", "date"])
    write_csv(df, PROC / "nxin_region_weekly.csv")
    return df


def province_daily() -> pd.DataFrame:
    b = fetch(f"{BASE}/hqb/queryPigPrice.shtml", SUB, name="queryPigPrice.html", force=True)
    areas = {"全国": 100000}
    for a in soup(b).find_all("a", href=re.compile(r"/hqb/areapriceinfo-(\d+)\.shtml")):
        nm = a.get_text(strip=True)
        if nm and nm not in areas:
            areas[nm] = int(re.search(r"areapriceinfo-(\d+)", a["href"]).group(1))
    today = dt.date.today()
    rows, checks = [], []
    for nm, aid in areas.items():
        url = (f"{BASE}/hqb/chq.shtml?type=0&date=0&queryPriceVo.goodsId=1&queryPriceVo.areaId={aid}"
               f"&queryPriceVo.whatTime=365")
        bb = fetch(url, SUB, name=f"chq_goods1_area{aid}_365.json", force=True)
        if not bb:
            continue
        j = json.loads(decode(bb))["pig"][0]
        for series, year in (("data1", today.year), ("data2", today.year - 1)):
            for md, v in zip(j["date"], j[series]):
                v = unwrap(v)
                try:
                    d = dt.date(year, int(md[:2]), int(md[3:5]))
                    v = float(v) if v not in (None, "") else None
                except (ValueError, TypeError):
                    continue
                rows.append(dict(date=d.isoformat(), province=nm, area_id=aid, price=v,
                                 goods="生猪(外三元)", source_url=url))
        # year-mapping check against the 30-day endpoint (which also uses MM-DD labels)
        u30 = url.replace("whatTime=365", "whatTime=30")
        b30 = fetch(u30, SUB, name=f"chq_goods1_area{aid}_30.json", force=True)
        if b30:
            j30 = json.loads(decode(b30))["pig"][0]
            last_md, last_v = j30["date"][-1], unwrap(j30["data"][-1])
            idx = len(j["data1"]) - 1
            checks.append(dict(area=nm, last30_date=last_md, last30_price=last_v,
                               data1_last_date=j["date"][idx], data1_last_price=j["data1"][idx]))
    df = pd.DataFrame(rows).sort_values(["area_id", "date"])
    df = df[pd.to_datetime(df.date) <= pd.Timestamp(today)]
    write_csv(df, PROC / "nxin_province_daily.csv")
    ck = pd.DataFrame(checks)
    ck.to_csv(Path(PROC.parent / "raw" / "industry" / SUB / "_year_mapping_check.csv"), index=False)
    print(ck.head(8).to_string())
    return df


if __name__ == "__main__":
    w = index_weekly()
    print(w.groupby("region").date.agg(["min", "max", "count"]))
    p = province_daily()
    print(p.groupby("province").date.agg(["min", "max", "count"]).head(40))
