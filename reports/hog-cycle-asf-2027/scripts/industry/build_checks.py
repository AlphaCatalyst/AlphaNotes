"""Coverage summary and cross-source consistency checks for the industry datasets.

Writes data/processed/industry_checks/*.csv and prints the headline numbers used in
research/industry_data_notes.md. Nothing here feeds back into the datasets.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ind_common import PROC  # noqa: E402

OUT = PROC / "industry_checks"
OUT.mkdir(parents=True, exist_ok=True)


def nbs_revisions():
    q = pd.read_csv(PROC / "nbs_quarterly.csv")
    q["year"] = q.period.str[:4].astype(int)
    q["qn"] = q.period.str[-1].astype(int)
    rows = []
    for col, yoy in [("hog_inventory_wan", "hog_inventory_yoy_pct"), ("hog_slaughter_cum_wan", "hog_slaughter_cum_yoy_pct"),
                     ("pork_output_cum_wan_t", "pork_output_cum_yoy_pct"), ("sow_inventory_wan", "sow_inventory_yoy_pct")]:
        for _, r in q.iterrows():
            if pd.isna(r[col]) or pd.isna(r[yoy]):
                continue
            prev = q[(q.year == r.year - 1) & (q.qn == r.qn)]
            implied = r[col] / (1 + r[yoy] / 100)
            pub = prev[col].iloc[0] if len(prev) else np.nan
            rows.append(dict(period=r.period, series=col, value=r[col], yoy_pct=r[yoy], implied_prev=round(implied, 1),
                             published_prev=pub, gap_pct=round((implied / pub - 1) * 100, 2) if pub == pub else None))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "nbs_implied_prev_vs_published.csv", index=False)
    big = df[df.gap_pct.abs() > 1.0]
    print("NBS: implied prior-year (from yoy) vs prior-year as published, |gap|>1%:")
    print(big.to_string(index=False))
    return df


def sow_compare():
    q = pd.read_csv(PROC / "nbs_quarterly.csv")
    s = pd.read_csv(PROC / "moa_sows_monthly.csv")
    q["month"] = q.period.str[:4] + "-" + (q.period.str[-1].astype(int) * 3).astype(str).str.zfill(2)
    m = s[s.scope.str.startswith("全国绝对量") & s.sow_wan.notna()].drop_duplicates("month", keep="first")
    j = q[["month", "sow_inventory_wan"]].merge(m[["month", "sow_wan", "scope"]], on="month", how="inner")
    j["diff"] = j.sow_wan - j.sow_inventory_wan
    j.to_csv(OUT / "sow_nbs_vs_moa_quarter_end.csv", index=False)
    print("\nQuarter-end sows NBS vs MOA:")
    print(j.dropna(subset=["sow_inventory_wan"]).to_string(index=False))


def price_compare():
    w = pd.read_csv(PROC / "moa_weekly_prices.csv")
    w = w[w.value_basis == "本周(原文)"].copy()
    w["d"] = pd.to_datetime(w.collect_date)
    wm = w.set_index("d").live_hog.resample("MS").mean().rename("moa_live_hog")
    n = pd.read_csv(PROC / "nxin_region_weekly.csv")
    n["d"] = pd.to_datetime(n.date)
    nm = n[n.region == "全国"].set_index("d").price.resample("MS").mean().rename("nxin_national")
    hn = n[n.region == "华南"].set_index("d").price.resample("MS").mean().rename("nxin_south")
    t = pd.read_csv(PROC / "nbs_tenday_hog.csv")
    t["d"] = pd.to_datetime(t.period.str[:7] + "-01")
    tm = t.groupby("d").price_yuan_kg.mean().rename("nbs_tenday")
    g = pd.read_csv(PROC / "gd_prices.csv")
    gm = g[g.report_type == "屠宰生猪及肉品价格(月)"].copy()
    gm["d"] = pd.to_datetime(gm.period_start)
    gm = gm.set_index("d").hog_purchase_price.rename("gd_slaughter_purchase")
    gf = g[g.report_type == "生猪产能监测(月)"].copy()
    gf["d"] = pd.to_datetime(gf.period_start)
    gf = gf.set_index("d").farm_hog_price.rename("gd_farm_hog")
    p = pd.read_csv(PROC / "nxin_province_daily.csv")
    p["d"] = pd.to_datetime(p.date)
    pg = p[p.province == "广东省"].set_index("d").price.resample("MS").mean().rename("nxin_gd_quote")
    allm = pd.concat([wm, nm, hn, tm, gm, gf, pg], axis=1)
    allm.to_csv(OUT / "monthly_price_crosscheck.csv")
    print("\nMonthly price cross-check (corr on overlapping months / mean diff):")
    pairs = [("moa_live_hog", "nbs_tenday"), ("moa_live_hog", "nxin_national"), ("nxin_south", "gd_slaughter_purchase"),
             ("gd_farm_hog", "gd_slaughter_purchase"), ("nxin_gd_quote", "gd_slaughter_purchase")]
    rows = []
    for a, b in pairs:
        x = allm[[a, b]].dropna()
        if len(x) < 3:
            continue
        rows.append(dict(a=a, b=b, n_months=len(x), corr=round(x[a].corr(x[b]), 3),
                         mean_b_minus_a=round((x[b] - x[a]).mean(), 2), first=x.index.min().date(), last=x.index.max().date()))
    r = pd.DataFrame(rows)
    r.to_csv(OUT / "price_pairs.csv", index=False)
    print(r.to_string(index=False))


def coverage():
    rows = []

    def add(name, df, col, extra=""):
        rows.append(dict(file=name, rows=len(df), first=df[col].dropna().min(), last=df[col].dropna().max(), note=extra))
    q = pd.read_csv(PROC / "nbs_quarterly.csv")
    add("nbs_quarterly.csv", q, "period",
        f"hog_inv {q.hog_inventory_wan.notna().sum()}, sow {q.sow_inventory_wan.notna().sum()}, "
        f"slaughter {q.hog_slaughter_cum_wan.notna().sum()}, pork {q.pork_output_cum_wan_t.notna().sum()} non-null")
    s = pd.read_csv(PROC / "moa_sows_monthly.csv")
    for sc, g in s.groupby("scope"):
        add(f"moa_sows_monthly.csv[{sc}]", g, "month")
    w = pd.read_csv(PROC / "moa_weekly_prices.csv")
    for vb, g in w.groupby("value_basis"):
        add(f"moa_weekly_prices.csv[{vb}]", g.assign(yw=g.year.astype(str) + "W" + g.week.astype(str).str.zfill(2)), "yw")
    n = pd.read_csv(PROC / "nxin_region_weekly.csv")
    for rg, g in n.groupby("region"):
        add(f"nxin_region_weekly.csv[{rg}]", g, "date")
    p = pd.read_csv(PROC / "nxin_province_daily.csv")
    add("nxin_province_daily.csv", p, "date", f"{p.province.nunique()} areas")
    g = pd.read_csv(PROC / "gd_prices.csv")
    for rt, gg in g.groupby("report_type"):
        add(f"gd_prices.csv[{rt}]", gg, "period_start")
    t = pd.read_csv(PROC / "nbs_tenday_hog.csv")
    add("nbs_tenday_hog.csv", t[t.price_yuan_kg.notna()], "period", f"{t.price_yuan_kg.isna().sum()} periods missing")
    c = pd.DataFrame(rows)
    c.to_csv(OUT / "coverage.csv", index=False)
    print("\nCoverage:")
    print(c.to_string(index=False))


if __name__ == "__main__":
    coverage()
    nbs_revisions()
    sow_compare()
    price_compare()
