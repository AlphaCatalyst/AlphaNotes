"""Issue #10: how Issue #5's 8.6 元 post-Spring-Festival benchmark was computed, how to tell an
off-season that is "not weak" from noise, and how to read it together with #5's stock test.

Everything reuses Issue #5 (stock_hog_timing.py): the weekly hog price in nxin-equivalent 元/公斤
(Friday-dated; the latest weeks are means of nxin daily national quotes shifted onto the weekly
index), lunar weeks counted from the Spring Festival (lw), reference years 2011-2025 except 2019-2020,
changes between two lunar positions taken year by year and summarised across years, and the
equal-weight hog-stock index with its excess return over beta x CSI All Share (ew_xs).

  benchmark  #5 as of its last daily quote (2026-10-12): base = week of 10-16 (lunar week 34),
             target = lunar week 8 of 2027; alternative definitions for comparison.
  path       the same calculation from the latest week to SF+20; the 10-16 path against what
             happened; whether autumn surprises carried over to SF+8 in the reference years.
  offseason  each reference year's change from the Spring Festival week to SF+k against the other
             years' quartiles; runs of weeks outside them; NBS slaughter and MOA sows in those years.
  stocks     for each cycle's excess-return low (#5 ts_cycle_milestones.csv), the excess return at
             the next post-festival spot low and what followed; 2026 so far.

Inputs: as stock_hog_timing.py, plus data/processed/issues/ts_cycle_milestones.csv.
Outputs: data/processed/issues/sb_*.csv (derived only), charts/i10_*.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stock_hog_timing as T  # noqa: E402

PROC, OUT = T.PROC, T.OUT
REPRO_ASOF = pd.Timestamp("2026-10-12")  # #5's last daily quote
ASOF = pd.Timestamp("2026-11-07")
TARGET_LW = 8
OFF_WEEKS = range(1, 17)  # SF+1 .. SF+16, the post-festival off-season (端午 is 16-19 weeks after SF)
RUN_MIN = 6


def hog_at(asof):
    T.ASOF = pd.Timestamp(asof)
    hog, src, meta = T.hog_price()
    hog = hog.dropna()
    df, use = T.seasonal_norm(hog, src)
    return hog, meta, df, use


def pivot(use):
    return use.pivot_table(index="year", columns="lw", values="lp")


def week_dates(use):
    return use.assign(date=use.index).groupby(["year", "lw"])["date"].max()


def pair_changes(P, l0, dy, l1, years=None) -> pd.Series:
    """Per reference year y: log change from lunar week l0 of year y-dy to lunar week l1 of year y."""
    out = {}
    for y in P.index if years is None else years:
        if y in P.index and y - dy in P.index and l0 in P.columns and l1 in P.columns:
            v = P.at[y, l1] - P.at[y - dy, l0]
            if pd.notna(v):
                out[y] = v
    return pd.Series(out, dtype=float)


def quart(s: pd.Series) -> dict:
    return {"n": len(s), "q25": s.quantile(0.25), "median": s.median(), "q75": s.quantile(0.75)}


# ---------------------------------------------------------------------------
# 1. the 8.6 benchmark and alternative definitions
# ---------------------------------------------------------------------------
def benchmark():
    hog, meta, df, use = hog_at(REPRO_ASOF)
    P, wd = pivot(use), week_dates(use)
    d0, base = hog.index[-1], float(hog.iloc[-1])
    l0, y0 = int(df.at[d0, "lw"]), int(df.at[d0, "year"])
    ch = pair_changes(P, l0, 1, TARGET_LW)
    pairs = pd.DataFrame({
        "target_year": ch.index,
        "base_week": [wd.get((y - 1, l0)) for y in ch.index],
        "target_week": [wd.get((y, TARGET_LW)) for y in ch.index],
        "chg": np.expm1(ch.values),
    })

    def lows(y, lo, hi):
        return P.loc[y, lo:hi].min() if y in P.index else np.nan

    alt = {}
    alt["A"] = ch
    alt["B"] = pd.Series({y: lows(y, 0, TARGET_LW) - P.at[y - 1, l0] for y in ch.index})
    pre = {y: P.loc[y - 1, l0:].max() for y in ch.index}
    alt["C"] = pd.Series({y: lows(y, 0, 20) - pre[y] for y in ch.index})
    jul = int(df.at[pd.Timestamp("2026-07-10"), "lw"])
    alt["D"] = pair_changes(P, jul, 1, TARGET_LW)
    alt["E"] = pair_changes(P, 0, 0, TARGET_LW)
    alt["F"] = pd.Series({y: lows(y, 0, 20) - P.at[y, 0] for y in P.index})
    spec = {
        "A": ("#5 口径：10-16 所在周（农历第 34 周）→ 2027 年春节后第 8 周周均价", base),
        "B": ("同一基数 → 春节后 0—8 周内最低的一周", base),
        "C": ("节前高点（第 34 周至春节前最高周）→ 节后 0—20 周最低周", np.nan),
        "D": ("7-10 所在周（农历第 20 周）→ 2027 年春节后第 8 周", float(hog.loc["2026-07-10"])),
        "E": ("春节当周 → 春节后第 8 周", np.nan),
        "F": ("春节当周 → 节后 0—20 周最低周", np.nan),
    }
    rows = []
    for k, (label, b) in spec.items():
        q = quart(alt[k])
        rows.append({"def": k, "label": label, "base": b, **{c: np.expm1(q[c]) if c != "n" else q[c]
                                                             for c in ("n", "q25", "median", "q75")},
                     "price_median": b * np.exp(q["median"]) if pd.notna(b) else np.nan,
                     "price_q25": b * np.exp(q["q25"]) if pd.notna(b) else np.nan,
                     "price_q75": b * np.exp(q["q75"]) if pd.notna(b) else np.nan})
    alts = pd.DataFrame(rows)

    sets = {"#5（2011—2025，剔除 2019—2020）": None,
            "全部年份（2005—2025）": "all", "非瘟后（2022—2025）": [2022, 2023, 2024, 2025]}
    rob = []
    for lab, ys in sets.items():
        if ys == "all":
            T.ASOF = REPRO_ASOF
            Pall = df.pivot_table(index="year", columns="lw", values="lp")
            s = pair_changes(Pall, l0, 1, TARGET_LW, years=range(2005, 2026))
        else:
            s = pair_changes(P, l0, 1, TARGET_LW, years=ys)
        q = quart(s)
        rob.append({"set": lab, "n": q["n"], "q25": np.expm1(q["q25"]), "median": np.expm1(q["median"]),
                    "q75": np.expm1(q["q75"]), "price_median": base * np.exp(q["median"])})
    facts = {"base_week": d0, "base_price": base, "base_lw": l0, "base_lunar_year": y0,
             "base_daily_quotes": meta["last_daily_nxin"], "nxin_daily_shift": meta["nxin_daily_shift"],
             "target_week": T.fri(T.FEST[2027][0] + pd.Timedelta(weeks=TARGET_LW)),
             "jul_lw": jul}
    return pairs, alts, pd.DataFrame(rob), facts


# ---------------------------------------------------------------------------
# 2. re-anchored path and whether autumn surprises carry over
# ---------------------------------------------------------------------------
def path_from(asof):
    hog, meta, df, use = hog_at(asof)
    P = pivot(use)
    d0, base = hog.index[-1], float(hog.iloc[-1])
    l0, y0 = int(df.at[d0, "lw"]), int(df.at[d0, "year"])
    rows = []
    for f in pd.date_range(d0, T.FEST[y0 + 1][0] + pd.Timedelta(weeks=21), freq="W-FRI"):
        y = y0 if f < T.FEST[y0 + 1][0] else y0 + 1
        lw = (f - T.FEST[y][0]).days // 7
        q = quart(pair_changes(P, l0, y - y0, lw))
        rows.append({"anchor": d0, "date": f, "lunar_year": y, "lw": lw, "n": q["n"],
                     **{f"p_{c}": base * np.exp(q[c]) for c in ("q25", "median", "q75")}})
    return pd.DataFrame(rows), hog, meta


def carry_over(df, use, lo=30, hi=45, n=3):
    """Reference years: surprise over n weeks ending at lunar week l (l in lo..hi) against the
    surprise from l to lunar week 8 of the next year; both against the other years' medians."""
    P = pivot(use)
    rows = []
    for y in P.index:
        if y + 1 not in P.index:
            continue
        oth = [v for v in P.index if v != y and v + 1 in P.index]
        for l in range(lo, hi + 1):
            if l - n not in P.columns or l not in P.columns:
                continue
            s1 = P.at[y, l] - P.at[y, l - n] - (P.loc[oth, l] - P.loc[oth, l - n]).median()
            s2 = P.at[y + 1, TARGET_LW] - P.at[y, l] - np.nanmedian(
                P.loc[[v + 1 for v in oth], TARGET_LW].values - P.loc[oth, l].values)
            if pd.notna(s1) and pd.notna(s2):
                rows.append({"year": y, "lw": l, "s1": s1, "s2": s2})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. the post-festival off-season, year by year
# ---------------------------------------------------------------------------
def runs(flags) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def offseason(df, use):
    P = pivot(use)
    years = list(P.index) + [2026]
    allP = df.pivot_table(index="year", columns="lw", values="lp")
    rows, paths = [], []
    for y in years:
        ref = [v for v in P.index if v != y]
        for k in range(0, 21):
            o = (P.loc[ref, k] - P.loc[ref, 0]).dropna()
            a = allP.at[y, k] - allP.at[y, 0] if k in allP.columns else np.nan
            paths.append({"year": y, "k": k, "chg": a, "q25": o.quantile(0.25), "median": o.median(),
                          "q75": o.quantile(0.75)})
    paths = pd.DataFrame(paths)
    for y, g in paths.groupby("year"):
        g = g.set_index("k").loc[list(OFF_WEEKS)]
        hi, lo = g["chg"] > g["q75"], g["chg"] < g["q25"]
        nxt = allP.at[y, 42] - allP.at[y, 16] if y in allP.index and 42 in allP.columns else np.nan
        rows.append({"year": y, "dev8": g.at[TARGET_LW, "chg"] - g.at[TARGET_LW, "median"],
                     "dev16": g.at[16, "chg"] - g.at[16, "median"],
                     "weeks_above_q75": int(hi.sum()), "run_above_q75": runs(hi),
                     "weeks_below_q25": int(lo.sum()), "run_below_q25": runs(lo),
                     "chg8": g.at[TARGET_LW, "chg"], "chg16": g.at[16, "chg"], "chg16_42": nxt})
    per = pd.DataFrame(rows)
    per["label"] = np.select(
        [per["run_above_q75"] >= RUN_MIN, per["run_below_q25"] >= RUN_MIN],
        ["持续强于常态", "持续弱于常态"], "常态波动")
    return paths, per.merge(supply(), on="year", how="left")


def supply() -> pd.DataFrame:
    n = pd.read_csv(PROC / "nbs_quarterly.csv")
    n["year"] = n["period"].str[:4].astype(int)
    n["q"] = n["period"].str[-1].astype(int)
    q = n.pivot_table(index="year", columns="q", values="hog_slaughter_q_wan")
    w = n.pivot_table(index="year", columns="q", values="carcass_wt_kg_est")
    out = pd.DataFrame({"slaughter_q1_yoy": q[1] / q[1].shift() - 1, "slaughter_q2_yoy": q[2] / q[2].shift() - 1,
                        "carcass_h1_yoy": (w[1] + w[2]) / (w[1] + w[2]).shift() - 1})
    m = pd.read_csv(PROC / "moa_sows_monthly.csv")
    s = m[m["month"].str.endswith("-09")].set_index("month")["sow_yoy_pct"].dropna() / 100
    s.index = s.index.str[:4].astype(int) + 1
    out["sows_prev_sep_yoy"] = s
    return out.reset_index().rename(columns={"index": "year"})


# ---------------------------------------------------------------------------
# 4. stocks at the post-festival spot low after each cycle's stock low
# ---------------------------------------------------------------------------
def stock_test(W, df, use):
    ms = pd.read_csv(OUT / "ts_cycle_milestones.csv", parse_dates=["trough", "start"])
    hog_start = ms[ms["series"] == "hog"].set_index("cycle")["start"]
    xs = W["ew_xs"].dropna()
    rows = []
    for _, r in ms[ms["series"] == "ew_xs"].iterrows():
        t = r["trough"]
        sf = next(T.FEST[y][0] for y in sorted(T.FEST) if T.FEST[y][0] > t + pd.Timedelta(weeks=4))
        win = W.loc[sf:sf + pd.Timedelta(weeks=20), "hog"].dropna()
        if t.year >= 2026 or win.empty:
            continue
        low = win.idxmin()
        seg = xs.loc[t:low + pd.Timedelta(weeks=8)]
        after = xs.loc[low:]
        exp_ = T.seas_exp(df, use, T.fri(t), low, excl=int(df.at[low, "year"]))
        spot_chg = W.at[low, "hog"] / W.at[T.fri(t), "hog"] - 1
        rows.append({
            "cycle": r["cycle"], "xs_trough": t, "spot_low_week": low, "weeks_after_trough": T.wk(low, t),
            "comparable": bool(spot_chg < 0),
            "spot_chg": spot_chg,
            "spot_surprise": np.log(W.at[low, "hog"] / W.at[T.fri(t), "hog"]) - exp_,
            "spot_low_vs_prior_low": W.at[low, "hog"] / W.loc[:t, "hog"].iloc[-104:].min() - 1,
            "xs_at_low_vs_trough": xs.asof(low) / xs.asof(t) - 1,
            "xs_min_vs_trough": seg.min() / xs.asof(t) - 1,
            "held": bool(seg.min() >= xs.asof(t)),
            "xs_26w_after_low": after.iloc[min(26, len(after) - 1)] / after.iloc[0] - 1,
            "xs_52w_after_low": after.iloc[min(52, len(after) - 1)] / after.iloc[0] - 1,
            "hog_sustained_start": hog_start.get(r["cycle"]),
        })
    return pd.DataFrame(rows)


def stocks_2026(W, df, use):
    lo = W["ew_xs"].loc["2026-01-01":].idxmin()
    last = W["ew_xs"].dropna().index[-1]
    x = W.loc[lo:last]
    f = {"xs_trough_week": lo, "xs_trough": float(W.at[lo, "ew_xs"]), "last_week": last,
         "xs_last": float(W.at[last, "ew_xs"]), "xs_vs_trough": float(W.at[last, "ew_xs"] / W.at[lo, "ew_xs"] - 1),
         "ew_vs_trough": float(W.at[last, "ew"] / W.at[lo, "ew"] - 1),
         "rs_vs_trough": float(W.at[last, "rs"] / W.at[lo, "rs"] - 1),
         "csi_vs_trough": float(W.at[last, "csi_all"] / W.at[lo, "csi_all"] - 1),
         "hog_vs_trough": float(W.at[last, "hog"] / W.at[lo, "hog"] - 1),
         "hog_last": float(W.at[last, "hog"]), "xs_max_since": float(x["ew_xs"].max()),
         "xs_max_week": x["ew_xs"].idxmax(),
         "hog_2026_low_week": W["hog"].loc["2026-01-01":].idxmin(),
         "hog_2026_low": float(W["hog"].loc["2026-01-01":].min())}
    for lab, d0 in (("10-16", pd.Timestamp("2026-10-16")), ("07-10", pd.Timestamp("2026-07-10"))):
        act = float(df.at[last, "lp"] - df.at[d0, "lp"])
        f[f"hog_chg_since_{lab}"] = float(np.expm1(act))
        f[f"seasonal_median_since_{lab}"] = float(np.expm1(T.seas_exp(df, use, d0, last, excl=2026)))
    for lab, d0 in (("10-16", "2026-10-16"), ("trough", lo)):
        f[f"xs_chg_since_{lab}"] = float(W.at[last, "ew_xs"] / W.at[pd.Timestamp(d0), "ew_xs"] - 1)
    return f


def futures_now():
    fu = pd.read_csv(PROC / "futures_lh_daily.csv", parse_dates=["trade_date"])
    fu = fu[fu["trade_date"] <= ASOF]
    p = fu.pivot_table(index="trade_date", columns="contract", values="close")
    last = p.index.max()
    out = {"futures_date": last}
    for c in ("LH2611", "LH2701", "LH2703", "LH2705", "LH2709"):
        if c in p:
            out[f"{c}_last"] = float(p.at[last, c])
            out[f"{c}_1013"] = float(p[c].asof(pd.Timestamp("2026-10-13")))
    return out


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------
def chart_benchmark(pairs, alts, path_now, path_old, hog_now, facts, fut):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), gridspec_kw={"width_ratios": [1, 1.6]})
    ax = axes[0]
    p = pairs.sort_values("chg")
    ax.barh([f"{y - 1}→{y}" for y in p["target_year"]], p["chg"] * 100,
            color=[C["spot"] if v < 0 else C["fut3"] for v in p["chg"]])
    a = alts.set_index("def").loc["A"]
    for v, ls in ((a["median"], "-"), (a["q25"], ":"), (a["q75"], ":")):
        ax.axvline(v * 100, color=C["dark"], ls=ls, lw=1)
    ax.set_xlabel("上一年农历第 34 周 → 当年春节后第 8 周，%")
    ax.set_title(f"11 组参照年份：中位数 {a['median']:+.1%}，四分位 {a['q25']:+.0%} 至 {a['q75']:+.0%}")

    ax = axes[1]
    h = hog_now.loc["2026-03-01":]
    ax.plot(h.index, h.values, color=C["dark"], lw=1.6, label="现货（新牧网口径周均价）")
    for df_, col, lab in ((path_old, C["grey"], "#5：从 10-16 出发"), (path_now, C["stock"], "从最新一周出发")):
        ax.plot(df_["date"], df_["p_median"], color=col, lw=1.4, label=f"{lab}的季节中位数")
        ax.fill_between(df_["date"], df_["p_q25"], df_["p_q75"], color=col, alpha=0.15)
    ax.axhline(8.6, color=C["fut4"], ls="--", lw=1)
    ax.text(h.index[0], 8.62, "8.6 元", color=C["fut4"], fontsize=8, va="bottom")
    tw, top = facts["target_week"], ax.get_ylim()[1]
    for d, lab in ((T.FEST[2027][0], "春节 "), (tw, " 节后第 8 周")):
        ax.axvline(d, color=C["grey"], lw=0.8, ls=":")
        ax.text(d, top, lab, fontsize=8, color=C["grey"], va="top", ha="right" if lab == "春节 " else "left")
    for c, d in (("LH2701", "2027-01-15"), ("LH2703", "2027-03-15"), ("LH2705", "2027-05-15")):
        if f"{c}_last" in fut:
            ax.plot(pd.Timestamp(d), fut[f"{c}_last"] / 1000, "D", color=C["fut1"], ms=5)
            ax.annotate(c, (pd.Timestamp(d), fut[f"{c}_last"] / 1000), fontsize=7.5, color=C["fut1"],
                        xytext=(4, 4), textcoords="offset points")
    ax.set_ylabel("元/公斤")
    ax.set_title("季节路径（阴影为四分位）与期货收盘价（元/吨 ÷ 1000，交割标准不同）")
    ax.legend(loc="upper right")
    title(fig, "8.6 元怎么来的：10-16 周价 × 历年同农历窗口跌幅中位数",
          "现货 11 月初已跌到 8.6—8.8 元，比季节路径提前约 5 个月到达；从最新价重算，节后第 8 周中位数更低")
    source(fig, "新牧网全国生猪均价（周度；最新几周为日度均值并按此前 26 周平均差调整），2011—2025 年剔除 2019—2020 年"
                "为参照；逐年计算同一农历窗口的对数变化后取中位数。期货为大商所收盘价。本文计算。")
    return save(fig, "i10_benchmark.png")


def chart_offseason(paths, per):
    import matplotlib.pyplot as plt
    from plotstyle import C, PALETTE, save, source, title

    fig, ax = plt.subplots(figsize=(12, 5.4))
    band = paths[paths["year"] == 2026].set_index("k")
    ax.fill_between(band.index, np.expm1(band["q25"]) * 100, np.expm1(band["q75"]) * 100,
                    color=C["light"], alpha=0.7, label="2011—2025 年四分位（剔除 2019—2020）")
    ax.plot(band.index, np.expm1(band["median"]) * 100, color=C["dark"], lw=1.6, label="中位数")
    lab = per.set_index("year")["label"]
    pal = [c for c in PALETTE if c != C["fut4"]]
    i = 0
    for y, g in paths.groupby("year"):
        g = g.set_index("k")
        if y == 2026:
            ax.plot(g.index, np.expm1(g["chg"]) * 100, color=C["fut4"], lw=2.2, label="2026 年")
        elif lab.get(y) != "常态波动":
            ax.plot(g.index, np.expm1(g["chg"]) * 100, color=pal[i % len(pal)], lw=1.3,
                    label=f"{y}（{lab.get(y)}）")
            i += 1
        else:
            ax.plot(g.index, np.expm1(g["chg"]) * 100, color=C["grey"], lw=0.6, alpha=0.5)
    ax.axvspan(OFF_WEEKS[0], OFF_WEEKS[-1], color=C["spot"], alpha=0.05)
    ax.axhline(0, color=C["grey"], lw=0.6)
    ax.set_xticks(range(0, 21, 2))
    ax.set_xlim(0, 20)
    ax.set_xlabel("春节后第 k 周（阴影为第 1—16 周）")
    ax.set_ylabel("相对春节当周，%")
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5))
    title(fig, "节后淡季：逐年相对春节当周的涨跌（灰线为常态波动年份）",
          f"“持续强于/弱于常态”= 第 1—16 周内连续 {RUN_MIN} 周以上高于上四分位 / 低于下四分位（其余年份算四分位）")
    source(fig, "新牧网与农业部周价拼接的周度序列（同 Issue #5）；四分位每年用其余参照年份计算。本文计算。")
    return save(fig, "i10_offseason.png")


def chart_stocks(W, st):
    import matplotlib.pyplot as plt
    from plotstyle import C, PALETTE, save, source, title

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), gridspec_kw={"width_ratios": [1.2, 1]})
    ax = axes[0]
    xs = W["ew_xs"].dropna()
    pal = [c for c in PALETTE if c != C["fut4"]]
    for i, r in st[st["comparable"]].reset_index(drop=True).iterrows():
        t = r["xs_trough"]
        s = xs.loc[t - pd.Timedelta(weeks=8):t + pd.Timedelta(weeks=80)]
        x = [(d - t).days / 7 for d in s.index]
        ax.plot(x, (s / xs.asof(t) - 1) * 100, color=pal[i], lw=1.3, label=f"{t:%Y-%m}（{r['cycle']}）")
        lw_ = (r["spot_low_week"] - t).days / 7
        ax.plot(lw_, (xs.asof(r["spot_low_week"]) / xs.asof(t) - 1) * 100, "o", color=pal[i], ms=6)
    t = W["ew_xs"].loc["2026-01-01":].idxmin()
    s = xs.loc[t - pd.Timedelta(weeks=8):]
    ax.plot([(d - t).days / 7 for d in s.index], (s / xs.asof(t) - 1) * 100, color=C["fut4"], lw=2.4,
            label="2026-06")
    ax.axhline(0, color=C["dark"], lw=0.8)
    ax.set_xlabel("距超额收益低点的周数（圆点 = 其后第一个节后现货低点）")
    ax.set_ylabel("超额收益相对低点，%")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title("各轮超额收益低点之后：节后现货低点时守没守住")

    ax = axes[1]
    x = W.loc["2026-06-01":]
    b = x.loc["2026-06-26"]
    for c, col, lab in (("ew_xs", C["stock"], "猪企等权超额收益"), ("ew", C["muyuan"], "猪企等权（绝对）"),
                        ("hog", C["spot"], "现货"), ("csi_all", C["grey"], "中证全指")):
        ax.plot(x.index, (x[c] / b[c] - 1) * 100, color=col, lw=1.8 if c == "ew_xs" else 1.2, label=lab,
                ls="--" if c == "ew" else "-")
    ax.axhline(0, color=C["dark"], lw=0.8)
    ax.set_ylabel("相对 2026-06-26，%")
    ax.legend(loc="lower left")
    ax.set_title("本轮：现货创年内新低，超额收益仍高于 6-26 低点")
    title(fig, f"猪股超额收益与现货季节性低点：历史 {int(st['comparable'].sum())} 轮与本轮",
          "超额收益 = 猪企等权指数扣除 beta × 中证全指（beta 用此前 104 周）；同 Issue #5")
    source(fig, "腾讯证券后复权收盘价、中证指数、新牧网与农业部周价；周收盘。本文计算。")
    return save(fig, "i10_stocks.png")


# ---------------------------------------------------------------------------
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pairs, alts, rob, facts = benchmark()
    path_old, _, _ = path_from(REPRO_ASOF)

    T.ASOF = ASOF
    W, hog, meta, *_ = T.build()
    df, use = T.seasonal_norm(hog, W["hog_src"])
    path_now, hog_now, meta_now = path_from(ASOF)
    co = carry_over(df, use)
    paths, per = offseason(df, use)
    T.ASOF = ASOF
    st = stock_test(W, df, use)
    f26 = stocks_2026(W, df, use)
    fut = futures_now()

    pairs.to_csv(OUT / "sb_pairs.csv", index=False, float_format="%.4f")
    alts.to_csv(OUT / "sb_definitions.csv", index=False, float_format="%.4f")
    rob.to_csv(OUT / "sb_reference_sets.csv", index=False, float_format="%.4f")
    pd.concat([path_old, path_now]).to_csv(OUT / "sb_path.csv", index=False, float_format="%.3f")
    per.to_csv(OUT / "sb_offseason_years.csv", index=False, float_format="%.4f")
    band = paths[paths["year"] == 2026][["k", "q25", "median", "q75", "chg"]].rename(columns={"chg": "chg_2026"})
    np.expm1(band.set_index("k")).reset_index().to_csv(OUT / "sb_offseason_band.csv", index=False,
                                                       float_format="%.4f")
    st.to_csv(OUT / "sb_stock_test.csv", index=False, float_format="%.4f")

    realized = hog_now.loc[facts["base_week"]:].rename("realized")
    cmp_ = path_old.set_index("date")[["p_q25", "p_median", "p_q75"]].join(realized, how="inner")

    slope = np.polyfit(co["s1"], co["s2"], 1)[0] if len(co) > 10 else np.nan
    big = co[co["s1"] <= -0.08]
    facts_out = {**facts, **{f"now_{k}": v for k, v in meta_now.items()}, **f26, **fut,
                 "carry_slope": slope, "carry_corr": co[["s1", "s2"]].corr().iloc[0, 1], "carry_n": len(co),
                 "carry_big_neg_n": len(big), "carry_big_neg_years": ",".join(map(str, sorted(big["year"].unique()))),
                 "carry_big_neg_s2_median": big["s2"].median() if len(big) else np.nan}
    for d, r in cmp_.iterrows():
        facts_out[f"realized_{d:%m%d}"] = r["realized"]
        facts_out[f"path_median_{d:%m%d}"] = r["p_median"]
    pn = path_now.set_index("date")
    tw = facts["target_week"]
    for c in ("p_q25", "p_median", "p_q75"):
        facts_out[f"now_target_{c}"] = pn.at[tw, c] if tw in pn.index else np.nan
    pd.Series(facts_out).to_csv(OUT / "sb_facts.csv", header=["value"], index_label="key")
    co.to_csv(OUT / "sb_carry_over.csv", index=False, float_format="%.4f")

    chart_benchmark(pairs, alts, path_now, path_old, hog_now, facts, fut)
    chart_offseason(paths, per)
    chart_stocks(W, st)

    with pd.option_context("display.width", 200, "display.max_columns", 30):
        print(pairs.round(3).to_string(index=False))
        print(alts.drop(columns="label").round(4).to_string(index=False))
        print(rob.round(4).to_string(index=False))
        print(cmp_.round(3).to_string())
        print(per.round(3).to_string(index=False))
        print(st.round(3).to_string(index=False))
        for k, v in facts_out.items():
            print(k, v)


if __name__ == "__main__":
    main()
