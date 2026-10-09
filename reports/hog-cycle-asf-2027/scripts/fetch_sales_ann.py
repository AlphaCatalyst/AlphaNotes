"""Collect monthly hog-sales announcements (销售简报 / 销售情况 / 主要经营数据) from cninfo and cache text.

Step 1 (this script): list + download + extract text -> data/processed/sales_ann_text.csv (merged, de-duplicated)
Step 2 (parse_sales.py): per-company regex parsing into monthly volumes / prices.
Usage: python3 fetch_sales_ann.py [code ...]
"""
import re
import sys
import time

import pandas as pd

from common import PROC, RAW, cninfo_query, fetch_pdf_text

ALL = ["002714", "300498", "002157", "002124", "000876", "002477", "002567", "600975", "603363",
       "002548", "002385", "002100", "000735", "000048", "002840", "603477", "001201", "605296",
       "603717", "000702"]
CODES = sys.argv[1:] or ALL
KEYS = ("销售", "简报", "经营数据")

TITLE_OK = re.compile(r"(销售|出栏).*(简报|情况|公告|快报)|月度.*销售|经营数据")
TITLE_MONTH = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*(?:[-－至]\s*(\d{1,2})\s*)?月")
EXCLUDE = re.compile(r"更正|取消|英文|摘要|问询|回复|担保|募集|关联|激励|减持|质押|计划|饲料|房地产")

out_p = PROC / "sales_ann_text.csv"
old = pd.read_csv(out_p, dtype={"code": str}) if out_p.exists() else pd.DataFrame()
done_urls = set(old["url"]) if len(old) else set()
rows = []
for code in CODES:
    anns = []
    for y in range(2018, 2027):
        for key in KEYS:
            try:
                anns += cninfo_query(code, se_date=f"{y}-01-01~{y}-12-31", searchkey=key)
            except Exception as e:  # noqa: BLE001
                print(code, y, key, "ERR", e, flush=True)
            time.sleep(0.2)
    seen, keep = set(), []
    for a in anns:
        if a["url"] in seen or a["url"] in done_urls:
            continue
        seen.add(a["url"])
        t = a["title"]
        if TITLE_OK.search(t) and TITLE_MONTH.search(t) and not EXCLUDE.search(t):
            keep.append(a)
    print(code, "new candidates", len(keep), flush=True)
    for a in keep:
        try:
            txt = fetch_pdf_text(a["url"], cache_dir=RAW / "ann" / "sales")
        except Exception as e:  # noqa: BLE001
            txt = f"[DOWNLOAD_ERROR] {e}"
        m = TITLE_MONTH.search(a["title"])
        start_m, end_m = int(m.group(2)), int(m.group(3)) if m.group(3) else None
        rows.append(dict(code=code, sec_name=a["sec_name"], ann_date=a["date"], title=a["title"],
                         year=int(m.group(1)), month=end_m or start_m,
                         cumulative_from=start_m if end_m else None, url=a["url"],
                         text=re.sub(r"\s+", " ", txt)[:6000]))
        time.sleep(0.15)
    merged = pd.concat([old, pd.DataFrame(rows)], ignore_index=True).drop_duplicates("url")
    merged.to_csv(out_p, index=False)

merged = pd.concat([old, pd.DataFrame(rows)], ignore_index=True).drop_duplicates("url")
merged.to_csv(out_p, index=False)
print("done; total rows", len(merged))
