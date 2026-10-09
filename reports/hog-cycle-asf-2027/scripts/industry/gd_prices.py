"""Guangdong official hog prices (广东省农业农村厅 数据发布 > 生猪肉品价格) -> gd_prices.csv

dara.gd.gov.cn/sjfb/szrpjg/ carries three report types (all cached under data/raw/industry/gd/):
  * 屠宰生猪及肉品价格(月报/供应情况), monthly 2020-12 ..: 定点屠宰企业 生猪平均收购价, 白条肉平均出厂价,
    屠宰量, 宰前平均重量 (slaughterhouse purchase price = live hog price paid by slaughterhouses).
  * 屠宰生猪肉品价格专报, bi-weekly 2020-12 .. 2021-12: same prices for a 14-day window, with yoy.
  * 生猪产能监测情况, monthly 2022-01 .. 2025-07: 生猪出栏平均价格 / 仔猪出栏平均价格 (farm-gate, from
    农业农村部养殖场直联直报平台 price points) plus % changes of hog and sow stock.
The 2018 .. 2020-11 period has no report on this column, in the department's information-disclosure
catalogue (gkmlpt API; only 2016 week 52/53 weekly reports exist) or on 产销形势分析 (starts 2020).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ind_common import PROC, decode, fetch, flat_text, soup, write_csv  # noqa: E402

SUB = "gd"
BASE = "https://dara.gd.gov.cn/sjfb/szrpjg/"
NUM = r"(\d+(?:\.\d+)?)"


def signed(word, v):
    if v is None:
        return None
    return -float(v) if word in ("下降", "下跌", "减少") else float(v)


def list_items():
    b = fetch(BASE + "index.html", f"{SUB}/lists", name="szrpjg_index.html", force=True)
    m = re.search(r"totalPage\s*=\s*Math\.ceil\((\d+)/(\d+)\)", decode(b))
    n = -(-int(m.group(1)) // int(m.group(2))) if m else 1
    items = {}
    for p in range(1, n + 1):
        u = BASE + ("index.html" if p == 1 else f"index_{p}.html")
        bb = b if p == 1 else fetch(u, f"{SUB}/lists", name=f"szrpjg_index_{p}.html", force=True)
        for a in soup(bb).find_all("a", href=re.compile(r"/sjfb/szrpjg/content/post_\d+\.html")):
            t = re.sub(r"\s+", "", a.get_text(""))
            t = re.sub(r"\d{2}-\d{2}$", "", t)
            items[urljoin(u, a["href"])] = t
    return items


def parse(url: str, title: str, b: bytes) -> dict | None:
    t = flat_text(soup(b))
    rel = re.search(r"时间：(20\d\d-\d\d-\d\d)", t)
    rec = dict(url=url, title=title, release_date=rel.group(1) if rel else None)
    if "产能监测" in title:
        ym = re.search(r"(20\d\d)年(\d{1,2})月", title)
        rec.update(report_type="生猪产能监测(月)", period_label=f"{ym.group(1)}-{int(ym.group(2)):02d}",
                   period_start=f"{ym.group(1)}-{int(ym.group(2)):02d}-01")
        for key, kw in (("farm_hog_price", "生猪出栏平均价格"), ("farm_piglet_price", "仔猪出栏平均价格")):
            m = re.search(kw + NUM + r"元/公斤[，,]环比(上升|下降|上涨|下跌|持平)" + NUM + r"?%?[，,]同比(上升|下降|上涨|下跌)" + NUM + "%", t)
            if m:
                rec[key] = float(m.group(1))
                rec[key + "_mom_pct"] = signed(m.group(2), m.group(3)) if m.group(3) else 0.0
                rec[key + "_yoy_pct"] = signed(m.group(4), m.group(5))
            else:
                m = re.search(kw + NUM + r"元/公斤", t)
                rec[key] = float(m.group(1)) if m else None
        for key, kw in (("hog_stock", "生猪存栏"), ("sow_stock", "能繁母猪存栏量?")):
            m = re.search(kw + r"环比(上升|下降|持平)" + NUM + r"?%?[，,]同比(上升|下降)" + NUM + "%", t)
            if m:
                rec[key + "_mom_pct"] = signed(m.group(1), m.group(2)) if m.group(2) else 0.0
                rec[key + "_yoy_pct"] = signed(m.group(3), m.group(4))
        return rec
    if "专报" in title:
        pm = re.search(r"（(20\d\d)年(\d{1,2})月(\d{1,2})[－\-—–](?:(20\d\d)年)?(?:(\d{1,2})月)?(\d{1,2})日）", title)
        if pm:
            y1, m1, d1 = int(pm.group(1)), int(pm.group(2)), int(pm.group(3))
            y2 = int(pm.group(4)) if pm.group(4) else y1
            m2 = int(pm.group(5)) if pm.group(5) else m1
            d2 = int(pm.group(6))
            if m2 < m1 and not pm.group(4):
                y2 = y1 + 1
            rec.update(period_start=f"{y1}-{m1:02d}-{d1:02d}", period_end=f"{y2}-{m2:02d}-{d2:02d}")
        rec.update(report_type="屠宰企业价格专报(双周)",
                   period_label=f"{rec.get('period_start')}~{rec.get('period_end')}")
        m = re.search(r"(\d+)个地市(\d+)家生猪定点屠宰企业", t)
        rec["n_enterprises"] = int(m.group(2)) if m else None
        m = re.search(r"生猪平均收购价格为" + NUM + r"元/公斤[，,]环比(上涨|下降|下跌|持平)" + NUM + r"?%?[，,](?:同比|较去年同期)(上涨|下降|下跌)" + NUM + "%", t)
        if m:
            rec["hog_purchase_price"] = float(m.group(1))
            rec["hog_purchase_mom_pct"] = signed(m.group(2), m.group(3)) if m.group(3) else 0.0
            rec["hog_purchase_yoy_pct"] = signed(m.group(4), m.group(5))
        m = re.search(r"白条肉平均出厂价格为" + NUM + r"元/公斤[，,]环比(上涨|下降|下跌|持平)" + NUM + r"?%?[，,](?:同比|较去年同期)(上涨|下降|下跌)" + NUM + "%", t)
        if m:
            rec["carcass_price"] = float(m.group(1))
            rec["carcass_mom_pct"] = signed(m.group(2), m.group(3)) if m.group(3) else 0.0
            rec["carcass_yoy_pct"] = signed(m.group(4), m.group(5))
        return rec
    ym = re.search(r"(20\d\d)年(\d{1,2})月", title) or re.search(r"价格(20\d\d)年(\d{1,2})月报", title)
    if not ym:
        return None
    rec.update(report_type="屠宰生猪及肉品价格(月)", period_label=f"{ym.group(1)}-{int(ym.group(2)):02d}",
               period_start=f"{ym.group(1)}-{int(ym.group(2)):02d}-01")
    m = re.search(r"全省(\d+)家(?:在产)?生猪定点屠宰企业", t)
    rec["n_enterprises"] = int(m.group(1)) if m else None
    m = re.search(r"共屠宰生猪(\d+)头[，,](?:环比|比\d{1,2}月份)(上升|下降|增长|减少)" + NUM + "%", t)
    if m:
        rec["slaughter_heads"] = int(m.group(1))
        rec["slaughter_mom_pct"] = signed(m.group(2), m.group(3))
    m = re.search(r"生猪平均收购价为" + NUM + r"元/公斤[，,]环比(上涨|下降|下跌|上升|持平)" + NUM + r"?%?", t)
    if m:
        rec["hog_purchase_price"] = float(m.group(1))
        rec["hog_purchase_mom_pct"] = signed(m.group(2), m.group(3)) if m.group(3) else 0.0
    m = re.search(r"白条肉平均出厂价为" + NUM + r"元/公斤[，,]环比(上涨|下降|下跌|上升|持平)" + NUM + r"?%?", t)
    if m:
        rec["carcass_price"] = float(m.group(1))
        rec["carcass_mom_pct"] = signed(m.group(2), m.group(3)) if m.group(3) else 0.0
    m = re.search(r"屠宰前平均重量" + NUM + r"公斤", t)
    rec["pre_slaughter_weight_kg"] = float(m.group(1)) if m else None
    return rec


def main():
    items = list_items()
    print("items:", len(items))
    rows = []
    for u, title in items.items():
        b = fetch(u, f"{SUB}/articles", sleep=0.3)
        if not b:
            rows.append(dict(url=u, title=title, note="下载失败"))
            continue
        r = parse(u, title, b)
        if r:
            rows.append(r)
    df = pd.DataFrame(rows)
    cols = ["report_type", "period_label", "period_start", "period_end", "hog_purchase_price",
            "hog_purchase_mom_pct", "hog_purchase_yoy_pct", "carcass_price", "carcass_mom_pct", "carcass_yoy_pct",
            "farm_hog_price", "farm_hog_price_mom_pct", "farm_hog_price_yoy_pct", "farm_piglet_price",
            "farm_piglet_price_mom_pct", "farm_piglet_price_yoy_pct", "hog_stock_mom_pct", "hog_stock_yoy_pct",
            "sow_stock_mom_pct", "sow_stock_yoy_pct", "slaughter_heads", "slaughter_mom_pct",
            "pre_slaughter_weight_kg", "n_enterprises", "release_date", "url", "title"]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols].sort_values(["report_type", "period_start"]).reset_index(drop=True)
    write_csv(df, PROC / "gd_prices.csv")
    print(df.groupby("report_type").period_start.agg(["min", "max", "count"]))
    print(df[["hog_purchase_price", "carcass_price", "farm_hog_price"]].notna().sum())


if __name__ == "__main__":
    main()
