"""NBS 流通领域重要生产资料市场价格: 生猪(外三元) ten-day prices -> nbs_tenday_hog.csv

Each 旬 NBS publishes "<year>年<m>月<上/中/下>旬流通领域重要生产资料市场价格变动情况" (titled
"流通领域重要生产资料市场价格变动情况（<year>年<m>月1-10日）" before 2019). Its table row
"生猪（外三元） | 千克 | 本期价格 | 比上期涨跌 | 涨跌幅%" gives the national average (24 provinces, wholesale
/ circulation channel). 玉米 and 豆粕 (元/吨) from the same table are kept as extra columns.
Release URLs come from the site-search anchors, the static list and, for gaps, id probing
(see nbs_index.py); downloads are spaced >=2 s apart because of the site's WAF.
"""
from __future__ import annotations

import calendar
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ind_common import PROC, RAW, SITE_NBS, fetch, sogov_search, soup, table_rows, to_float, write_csv  # noqa: E402
from nbs_index import all_known, collect_anchors, find_release  # noqa: E402

SUB = "nbs_tenday"
XUN = {"上": (1, 10), "中": (11, 20), "下": (21, None)}
Y0, Y1 = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (2018, 2022)


def title_re(y, m, x):
    d1, d2 = XUN[x]
    d2 = d2 or calendar.monthrange(y, m)[1]
    return (rf"({y}年{m}月{x}旬流通领域重要生产资料市场价格变动情况|"
            rf"流通领域重要生产资料市场价格变动情况（{y}年{m}月{d1}日?[-－—~]{XUN[x][1] or r'\d+'}日）)")


def windows(y, m, x):
    import datetime as dt
    d2 = XUN[x][1] or calendar.monthrange(y, m)[1]
    end = dt.date(y, m, d2)
    return (end + dt.timedelta(days=1)).isoformat(), (end + dt.timedelta(days=16)).isoformat()


def parse(b: bytes) -> dict:
    s = soup(b)
    rec = {}
    for tb in s.find_all("table"):
        for r in table_rows(tb):
            if not r:
                continue
            name = r[0]
            nums = [c for c in r[1:] if re.fullmatch(r"-?\d+(\.\d+)?", c)]
            if name.startswith("生猪") and "hog" not in rec and len(nums) >= 1:
                rec["hog"] = float(nums[0])
                rec["hog_unit"] = r[1] if len(r) > 1 else ""
                rec["hog_chg"] = float(nums[1]) if len(nums) > 1 else None
                rec["hog_chg_pct"] = float(nums[2]) if len(nums) > 2 else None
                rec["hog_name"] = name
            elif name.startswith("玉米") and "corn" not in rec and nums:
                rec["corn"] = float(nums[0])
            elif name.startswith("豆粕") and "soymeal" not in rec and nums:
                rec["soymeal"] = float(nums[0])
    return rec


def main():
    anchors = collect_anchors()
    known = all_known(anchors)
    rows = []
    for y in range(Y0, Y1 + 1):
        for m in range(1, 13):
            for x in ("上", "中", "下"):
                period = f"{y}-{m:02d}{x}旬"
                tre = title_re(y, m, x)
                lo, hi = windows(y, m, x)
                cand = known[known.title.fillna("").str.contains(tre, regex=True)]
                hit = None
                if len(cand):
                    r = cand.sort_values("date").iloc[0]
                    hit = dict(url=r.url, title=r.title, date=r.date, via=r.via)
                if hit is None:
                    for d in sogov_search(SITE_NBS, f"{y}年{m}月{x}旬流通领域重要生产资料市场价格变动情况", lo, hi,
                                          key_place=1, max_pages=1, cache_subdir=f"{SUB}/search"):
                        if "www.stats.gov.cn/sj/zxfb/" in d["url"] and re.search(tre, d["title"]):
                            hit = dict(url=d["url"].replace("http://", "https://"), title=d["title"],
                                       date=d["date"], via="search")
                            break
                if hit is None and hi < "2023-02-03":
                    hit = find_release(anchors, tre, lo, hi, max_probes=24)
                if hit is None:
                    rows.append(dict(period=period, note="未找到发布稿"))
                    print(period, "NOT FOUND")
                    continue
                b = fetch(hit["url"], f"{SUB}/releases", sleep=2.0)
                rec = dict(period=period, release_date=hit["date"], url=hit["url"], title=hit["title"],
                           found_via=hit["via"])
                if b:
                    rec.update(parse(b))
                else:
                    rec["note"] = "下载失败"
                print(period, rec.get("release_date"), rec.get("hog"), rec.get("found_via"))
                rows.append(rec)
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "period": df.period, "price_yuan_kg": df.get("hog"), "release_date": df.get("release_date"),
        "url": df.get("url"), "chg_yuan_kg": df.get("hog_chg"), "chg_pct": df.get("hog_chg_pct"),
        "item": df.get("hog_name"), "unit": df.get("hog_unit"), "corn_yuan_t": df.get("corn"),
        "soymeal_yuan_t": df.get("soymeal"), "title": df.get("title"), "found_via": df.get("found_via"),
        "note": df.get("note")})
    name = "nbs_tenday_hog.csv" if (Y0, Y1) == (2018, 2022) else f"nbs_tenday_hog_{Y0}_{Y1}.csv"
    write_csv(out, PROC / name)
    print(out.price_yuan_kg.notna().sum(), "of", len(out))


if __name__ == "__main__":
    main()
