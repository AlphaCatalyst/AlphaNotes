"""NBS quarterly hog supply data (2016Q1-2026Q2) -> nbs_quarterly.csv (+ nbs_annual_bulletin.csv)

Sources: the quarterly 国民经济运行情况 press releases (Q1 / 上半年 / 前三季度 / 全年) on
www.stats.gov.cn/sj/zxfb/ and the annual 统计公报 (www.stats.gov.cn/sj/tjgb/ndtjgb/). Values are
parsed from the release's appendix table (附表: 猪牛羊禽肉, 其中猪肉, 生猪存栏, 生猪出栏) and, where
the table lacks a series (能繁母猪 is only in the text), from the release text.

Derived columns (marked as such in the notes): single-quarter slaughter / pork output are
differences of year-to-date cumulative values taken from releases of the same year; carcass weight
estimate = single-quarter pork output / single-quarter slaughter (kg/head).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ind_common import PROC, RAW, fetch, flat_text, soup, table_rows, write_csv  # noqa: E402
from nbs_index import all_known, collect_anchors, find_release  # noqa: E402

SUB = "nbs"
EXCL = ("居民消费|工业生产者|固定资产|房地产|消费品|国内生产总值|GDP|统计公报|普查|指数|能源|采购经理|流通领域|"
        "食品|利润|投资|人口|粮食|系列|成就|十八大|党的|新中国|改革开放|周年|答记者问|收入|服务业|工业增加值|核算")
QTITLE = rf"^(?!.*({EXCL})).*(国民经济|经济运行|经济发展|经济增长|经济)"
WINDOWS = {1: ("-04-08", "-04-30", 0), 2: ("-07-08", "-07-31", 0), 3: ("-10-08", "-10-31", 0),
           4: ("-01-10", "-01-31", 1)}


def targets():
    out = []
    for y in range(2016, 2027):
        for q in (1, 2, 3, 4):
            if (y, q) > (2026, 2):
                break
            lo, hi, plus = WINDOWS[q]
            out.append((f"{y}Q{q}", y, q, f"{y + plus}{lo}", f"{y + plus}{hi}"))
    return out


ROWS = {
    "meat": [r"^猪牛羊禽肉"],
    "pork": [r"^(其中：)?猪肉（万吨）", r"^其中：猪肉"],
    "hog_inv": [r"^生猪存栏"],
    "slaughter": [r"^生猪出栏"],
    "sow_inv": [r"^(其中：)?能繁(殖)?母猪存栏"],
}


def parse_release(b: bytes) -> dict:
    s = soup(b)
    rec, notes = {}, []
    for tb in s.find_all("table"):
        for r in table_rows(tb):
            lab = r[0]
            for key, pats in ROWS.items():
                if key in rec or not any(re.search(p, lab) for p in pats):
                    continue
                nums = [c for c in r[1:] if re.fullmatch(r"-?\d+(\.\d+)?", c)]
                if len(nums) >= 2:
                    rec[key], rec[key + "_yoy"] = float(nums[-2]), float(nums[-1])
                    rec[key + "_src"] = "附表"
                elif len(nums) == 1:
                    rec[key] = float(nums[0])
                    rec[key + "_src"] = "附表"
    t = flat_text(s)
    txt = {
        "pork": r"猪肉产量(\d+)万吨",
        "hog_inv": r"生猪存栏(\d+)万头",
        "slaughter": r"生猪出栏(\d+)万头",
        "sow_inv": r"能繁(?:殖)?母猪存栏(\d+)万头",
        "meat": r"猪牛羊禽肉产量(\d+)万吨",
    }
    for key, pat in txt.items():
        m = re.search(pat, t)
        if not m:
            continue
        v = float(m.group(1))
        if key not in rec:
            rec[key], rec[key + "_src"] = v, "正文"
        elif abs(rec[key] - v) > 0.5:
            notes.append(f"{key}:附表{rec[key]}≠正文{v}")
    if "sow_inv_yoy" not in rec:
        m = (re.search(r"能繁(?:殖)?母猪存栏\d+万头[，,]?(?:同比|比上年末)?(增长|下降|减少)(\d+\.?\d*)%", t)
             or re.search(r"能繁(?:殖)?母猪存栏(?:同比|比上年末|比上年同期)(增长|下降|减少)(\d+\.?\d*)%", t))
        if m:
            rec["sow_inv_yoy"] = float(m.group(2)) * (-1 if m.group(1) in ("下降", "减少") else 1)
        m = re.search(r"生猪存栏、能繁(?:殖)?母猪存栏(?:比上年末|同比)?分别(增长|下降)(\d+\.?\d*)%、(\d+\.?\d*)%", t)
        if m:
            sign = -1 if m.group(1) == "下降" else 1
            rec["sow_inv_yoy"] = sign * float(m.group(3))
            rec.setdefault("hog_inv_yoy", sign * float(m.group(2)))
    for key in ("hog_inv", "slaughter", "pork"):
        if key in rec and key + "_yoy" not in rec:
            m = re.search({"hog_inv": r"生猪存栏\d+万头[，,]?(?:同比|比上年末)?(增长|下降|减少)(\d+\.?\d*)%",
                           "slaughter": r"生猪出栏\d+万头[，,]?(?:同比|比上年)?(增长|下降|减少)(\d+\.?\d*)%",
                           "pork": r"猪肉产量\d+万吨[，,]?(?:同比|比上年)?(增长|下降|减少)(\d+\.?\d*)%"}[key], t)
            if m:
                rec[key + "_yoy"] = float(m.group(2)) * (-1 if m.group(1) in ("下降", "减少") else 1)
    rec["has_pig_text"] = ("生猪" in t)
    rec["parse_note"] = "; ".join(notes)
    return rec


def bulletins(anchors: pd.DataFrame, known: pd.DataFrame) -> pd.DataFrame:
    """Annual 统计公报: year-end hog inventory, annual slaughter and pork output (cross-check)."""
    rows = []
    links = {}
    for _, r in known[known.title.fillna("").str.contains("国民经济和社会发展统计公报")].iterrows():
        m = re.search(r"(20\d\d)年国民经济和社会发展统计公报", r.title)
        if m and (r.date or "") >= f"{int(m.group(1)) + 1}-02-01":
            links.setdefault(int(m.group(1)), r.url)
    for y in range(2015, 2026):
        u = links.get(y)
        if not u and f"{y + 1}-03-05" < "2023-02-03":
            hit = find_release(anchors, rf"{y}年国民经济和社会发展统计公报", f"{y + 1}-02-20", f"{y + 1}-03-05",
                               max_probes=24)
            u = hit["url"] if hit else None
        if not u:
            rows.append(dict(year=y, bulletin_url=None, note="未找到公报"))
            continue
        bb = fetch(u, f"{SUB}/bulletins", sleep=2.0)
        if not bb:
            rows.append(dict(year=y, bulletin_url=u, note="下载失败"))
            continue
        t = flat_text(soup(bb))
        rec = dict(year=y, bulletin_url=u)
        for key, pat in {"b_pork": r"猪肉产量(\d+)万吨", "b_hog_inv": r"生猪存栏(\d+)万头",
                         "b_slaughter": r"生猪出栏(\d+)万头", "b_sow_inv": r"能繁(?:殖)?母猪存栏(\d+)万头"}.items():
            m = re.search(pat, t)
            rec[key] = float(m.group(1)) if m else None
        rows.append(rec)
    df = pd.DataFrame(rows)
    write_csv(df, PROC / "nbs_annual_bulletin.csv")
    return df


def main():
    anchors = collect_anchors()
    known = all_known(anchors)
    recs = []
    for period, y, q, lo, hi in targets():
        cand = known[known.title.fillna("").str.contains(QTITLE, regex=True)
                     & (known.date >= lo) & (known.date <= hi)].sort_values("date")
        tried, rec = set(), None
        for attempt in range(4):
            left = cand[~cand.url.isin(tried)]
            if len(left):
                r = left.iloc[0]
                hit = dict(url=r.url, title=r.title, date=r.date, via=r.via)
            elif hi < "2023-02-03":
                hit = find_release(anchors, QTITLE, lo, hi, max_probes=30, exclude=tried)
            else:
                hit = None
            if not hit:
                break
            tried.add(hit["url"])
            b = fetch(hit["url"], f"{SUB}/releases", sleep=2.0)
            rec = dict(period=period, year=y, q=q, source_url=hit["url"], release_title=hit["title"],
                       release_date=hit["date"], found_via=hit.get("via"))
            if not b:
                rec["note"] = "下载失败"
                continue
            rec.update(parse_release(b))
            if any(rec.get(k) is not None for k in ("hog_inv", "slaughter", "pork")):
                break
            rec["note"] = "候选稿无生猪数据"
        if rec is None:
            recs.append(dict(period=period, year=y, q=q, note="未找到发布稿"))
            print(period, "NOT FOUND")
            continue
        print(period, rec.get("release_date"), str(rec.get("release_title"))[:24],
              {k: rec.get(k) for k in ("hog_inv", "sow_inv", "slaughter", "pork")}, rec.get("note") or "")
        recs.append(rec)
    df = pd.DataFrame(recs)
    df.to_csv(RAW / SUB / "_quarterly_parsed.csv", index=False)

    # single-quarter values from same-year cumulative values
    df = df.sort_values(["year", "q"]).reset_index(drop=True)
    for col, out in (("slaughter", "hog_slaughter_q_wan"), ("pork", "pork_output_q_wan_t")):
        vals = []
        for _, r in df.iterrows():
            if pd.isna(r.get(col)):
                vals.append(None)
                continue
            if r.q == 1:
                vals.append(r[col])
                continue
            prev = df[(df.year == r.year) & (df.q == r.q - 1)]
            vals.append(r[col] - prev[col].iloc[0] if len(prev) and pd.notna(prev[col].iloc[0]) else None)
        df[out] = vals
    df["carcass_wt_kg_est"] = (df["pork_output_q_wan_t"] / df["hog_slaughter_q_wan"] * 1000).round(2)

    bl = bulletins(anchors, known)
    df = df.merge(bl.rename(columns={"year": "year"}), on="year", how="left")
    for c in ("b_pork", "b_hog_inv", "b_slaughter", "b_sow_inv", "bulletin_url"):
        df.loc[df.q != 4, c] = None
    out = pd.DataFrame({
        "period": df.period,
        "hog_inventory_wan": df.get("hog_inv"),
        "sow_inventory_wan": df.get("sow_inv"),
        "hog_slaughter_cum_wan": df.get("slaughter"),
        "pork_output_cum_wan_t": df.get("pork"),
        "hog_slaughter_q_wan": df.hog_slaughter_q_wan,
        "pork_output_q_wan_t": df.pork_output_q_wan_t,
        "carcass_wt_kg_est": df.carcass_wt_kg_est,
        "source_url": df.get("source_url"),
        "release_date": df.get("release_date"),
        "hog_inventory_yoy_pct": df.get("hog_inv_yoy"),
        "sow_inventory_yoy_pct": df.get("sow_inv_yoy"),
        "hog_slaughter_cum_yoy_pct": df.get("slaughter_yoy"),
        "pork_output_cum_yoy_pct": df.get("pork_yoy"),
        "meat_output_cum_wan_t": df.get("meat"),
        "release_title": df.get("release_title"),
        "bulletin_hog_inventory_wan": df.get("b_hog_inv"),
        "bulletin_hog_slaughter_wan": df.get("b_slaughter"),
        "bulletin_pork_output_wan_t": df.get("b_pork"),
        "bulletin_sow_inventory_wan": df.get("b_sow_inv"),
        "bulletin_url": df.get("bulletin_url"),
        "parse_note": df.get("parse_note"),
        "note": df.get("note"),
    })
    write_csv(out, PROC / "nbs_quarterly.csv")


if __name__ == "__main__":
    main()
