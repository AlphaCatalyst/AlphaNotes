"""Guangdong monthly hog market analyses (广东省农业农村厅 数据发布 > 产销形势分析) -> gd_market_monthly.csv

dara.gd.gov.cn/sjfb/cxxsfx/ carries "生猪产销形势分析" (2020 ..) and, later, "主要农产品产销形势分析"
whose 生猪 section is shorter. From each report this keeps, where stated:
  * inprov_share_pct: share of hogs supplied from within the province at large slaughterhouses
    ("其中省内肉猪供应占比为X%"), the department's own measure of reliance on out-of-province hogs;
  * slaughter_wan: hogs slaughtered at designated plants with >=20k heads/year (万头);
  * farm_price: monitored average farm-gate price of finished hogs (元/公斤);
  * hk_farm_price: farm-gate price of hogs supplied to Hong Kong/Macau, stated in 2021-2022 reports.
Pages are cached under data/raw/industry/gd/cxxsfx/. A report that does not state a figure leaves it blank.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ind_common import PROC, decode, fetch, flat_text, soup, write_csv  # noqa: E402

SUB = "gd/cxxsfx"
BASE = "https://dara.gd.gov.cn/sjfb/cxxsfx/"
NUM = r"(\d+(?:\.\d+)?)"


def list_items() -> dict[str, str]:
    b = fetch(BASE + "index.html", f"{SUB}/lists", name="cxxsfx_index.html", force=True)
    pages = [int(x) for x in re.findall(r"index_(\d+)\.html", decode(b))]
    n = max(pages) if pages else 1
    items = {}
    for p in range(1, n + 1):
        u = BASE + ("index.html" if p == 1 else f"index_{p}.html")
        bb = b if p == 1 else fetch(u, f"{SUB}/lists", name=f"cxxsfx_index_{p}.html", force=True)
        for a in soup(bb).find_all("a", href=re.compile(r"/sjfb/cxxsfx/content/post_\d+\.html")):
            t = re.sub(r"\s+", "", a.get_text(""))
            t = re.sub(r"\d{2}-\d{2}$", "", t)
            if t:
                items[urljoin(u, a["href"])] = t
    return items


def parse(url: str, title: str, b: bytes) -> dict | None:
    ym = re.search(r"(20\d\d)年(\d{1,2})月", title)
    if not ym or not re.search(r"生猪|主要农产品", title):
        return None
    t = flat_text(soup(b))
    rel = re.search(r"时间：(20\d\d-\d\d-\d\d)", t)
    rec = dict(month=f"{ym.group(1)}-{int(ym.group(2)):02d}", title=title, url=url,
               release_date=rel.group(1) if rel else None)
    m = re.search(r"省内肉猪供应占比(?:为|约)?" + NUM + "%", t)
    rec["inprov_share_pct"] = float(m.group(1)) if m else None
    m = re.search(r"肉猪屠宰量约?" + NUM + r"万头", t)
    rec["slaughter_wan"] = float(m.group(1)) if m else None
    m = re.search(r"(?<!港澳地区)(?:商品肉猪|生猪|肉猪)出栏(?:月)?(?:均)?价(?:格)?(?:为|上涨至|下降至|回落至|升至|降至|至)?"
                  + NUM + r"元/公斤", t)
    rec["farm_price"] = float(m.group(1)) if m else None
    m = re.search(r"供港澳地区肉猪出栏均价(?:为)?" + NUM + r"元/公斤", t)
    rec["hk_farm_price"] = float(m.group(1)) if m else None
    m = re.search(r"省内肉猪供应占比(?:为|约)?" + NUM + "%", t)
    rec["excerpt"] = t[max(0, m.start() - 60):m.end() + 10] if m else None
    return rec


def main():
    items = list_items()
    rows = []
    for url, title in items.items():
        if not re.search(r"生猪|主要农产品", title):
            continue
        b = fetch(url, SUB)
        if b:
            r = parse(url, title, b)
            if r:
                rows.append(r)
    df = pd.DataFrame(rows).sort_values(["month", "release_date"]).drop_duplicates("month", keep="first")
    write_csv(df, PROC / "gd_market_monthly.csv")
    print(f"{len(items)} list items, {len(df)} monthly reports; inprov_share stated in "
          f"{df['inprov_share_pct'].notna().sum()} ({df.loc[df['inprov_share_pct'].notna(), 'month'].min()}"
          f" .. {df.loc[df['inprov_share_pct'].notna(), 'month'].max()})")
    print(df[["month", "inprov_share_pct", "slaughter_wan", "farm_price", "hk_farm_price"]].to_string(index=False))


if __name__ == "__main__":
    main()
