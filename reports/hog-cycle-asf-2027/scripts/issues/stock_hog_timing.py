"""Issue #5: when do hog stocks move with hog prices, when do they lead, and do rallies start in the
consumption off-season?

Weekly data (Friday), 2005-01 .. ASOF.
  hog price  one weekly series in nxin-equivalent 元/公斤:
             nxin national weekly transaction price from 2015 (a value labelled Monday L covers the
             week L-7..L-1, so it is dated to that week's Friday L-3), extended past the last weekly
             print with nxin daily national quotes (Mon-Sun means, shifted by their mean gap to the
             weekly series over the previous 26 weeks);
             MOA weekly 集贸 bulletins 2008-2014 (collection date) and MOA monthly reports 2003-2010
             (placed at mid-month), ratio-spliced onto nxin over their overlaps;
             gaps of up to 26 weeks are filled by log-linear interpolation and flagged.
  stocks     backward-adjusted closes. Equal-weight hog-stock index with dated entries (UNIVERSE),
             the two leaders (Muyuan, Wens), the rest ("small/mid"), and relative strength against the
             CSI All Share (000985), i.e. the index divided by the benchmark.
Rules fixed before looking at outcomes:
  - turning points: zigzag on log prices, a leg is confirmed once the series moves log(1+h) away
    from the running extreme (H_HOG for the hog price, K_LAUNCH for stocks);
  - up-leg milestones: trough; sustained start = first week above 20% of the leg's log amplitude
    after the last week within 10% of it; acceleration = start of the steepest 13-week rise; peak;
  - stock leg for a hog leg: lowest week between the previous hog peak and the current hog peak, then
    the highest week between that low and the next hog trough;
  - launch (real time): the week a stock zigzag trough is confirmed (close >= (1+K) x lowest close
    since the last confirmed peak). Outcome over the next 52 weeks: "持续" if the close rises another
    30%, "失败" if it first falls back to within 5% of the trough, otherwise "平淡";
  - seasons by the lunar calendar: 节后淡季 = Spring Festival -> 端午, 夏季淡季 = 端午 -> 21 days
    before 中秋, 旺季 = 21 days before 中秋 -> next Spring Festival.

Inputs (data/processed/): stock_daily.csv, csi_index_daily.csv, nxin_price_wide.csv,
nxin_province_daily.csv, futures_lh_daily.csv (local only); moa_hist_hog_prices.csv,
moa_weekly_prices.csv, moa_sows_monthly.csv, nbs_quarterly.csv, monthly_sales.csv, fin_quarterly.csv.
Outputs: data/processed/issues/ts_*.csv (derived only), charts/i05_*.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
OUT = PROC / "issues"
sys.path.insert(0, str(ROOT / "scripts"))

ASOF = pd.Timestamp("2026-10-13")

# Spring Festival, 端午, 中秋 (lunar calendar)
FEST = {
    2003: ("2003-02-01", "2003-06-04", "2003-09-11"),
    2004: ("2004-01-22", "2004-06-22", "2004-09-28"), 2005: ("2005-02-09", "2005-06-11", "2005-09-18"),
    2006: ("2006-01-29", "2006-05-31", "2006-10-06"), 2007: ("2007-02-18", "2007-06-19", "2007-09-25"),
    2008: ("2008-02-07", "2008-06-08", "2008-09-14"), 2009: ("2009-01-26", "2009-05-28", "2009-10-03"),
    2010: ("2010-02-14", "2010-06-16", "2010-09-22"), 2011: ("2011-02-03", "2011-06-06", "2011-09-12"),
    2012: ("2012-01-23", "2012-06-23", "2012-09-30"), 2013: ("2013-02-10", "2013-06-12", "2013-09-19"),
    2014: ("2014-01-31", "2014-06-02", "2014-09-08"), 2015: ("2015-02-19", "2015-06-20", "2015-09-27"),
    2016: ("2016-02-08", "2016-06-09", "2016-09-15"), 2017: ("2017-01-28", "2017-05-30", "2017-10-04"),
    2018: ("2018-02-16", "2018-06-18", "2018-09-24"), 2019: ("2019-02-05", "2019-06-07", "2019-09-13"),
    2020: ("2020-01-25", "2020-06-25", "2020-10-01"), 2021: ("2021-02-12", "2021-06-14", "2021-09-21"),
    2022: ("2022-02-01", "2022-06-03", "2022-09-10"), 2023: ("2023-01-22", "2023-06-22", "2023-09-29"),
    2024: ("2024-02-10", "2024-06-10", "2024-09-17"), 2025: ("2025-01-29", "2025-05-31", "2025-10-06"),
    2026: ("2026-02-17", "2026-06-19", "2026-09-25"), 2027: ("2027-02-06", "2027-06-09", "2027-09-15"),
}
FEST = {y: tuple(pd.Timestamp(x) for x in v) for y, v in FEST.items()}
PEAK_LEAD = pd.Timedelta(days=21)
SEASONS = ["节后淡季", "夏季淡季", "旺季"]

# hog-stock universe: (code, name, included from, included until)
UNIVERSE = [
    ("600975", "新五丰", "2005-01-01", None),
    ("000735", "罗牛山", "2005-01-01", None),
    ("002157", "正邦科技", "2007-08-17", None),
    ("002477", "雏鹰农牧", "2010-09-15", "2019-10-15"),
    ("002714", "牧原股份", "2014-01-28", None),
    ("300498", "温氏股份", "2015-11-02", None),
    ("002124", "天邦食品", "2016-01-01", None),
    ("603363", "傲农生物", "2017-09-26", None),
    ("000876", "新希望", "2018-01-01", None),
    ("002567", "唐人神", "2018-01-01", None),
    ("002548", "金新农", "2018-01-01", None),
    ("002385", "大北农", "2018-01-01", None),
    ("002100", "天康生物", "2018-01-01", None),
    ("000048", "京基智农", "2019-01-01", None),
    ("002840", "华统股份", "2020-01-01", None),
    ("603477", "巨星农牧", "2021-01-01", None),
    ("001201", "东瑞股份", "2021-04-28", None),
    ("605296", "神农集团", "2021-05-28", None),
]
NAMES = {c: n for c, n, _, _ in UNIVERSE}
LEADERS = ("002714", "300498")

H_HOG = 0.25
K_LAUNCH = {"ew": 0.25, "rs": 0.20}
SERIES_CN = {"ew": "猪企等权指数", "rs": "相对中证全指", "lead": "龙头(牧原+温氏)", "small": "中小猪企"}


def fri(d) -> pd.Timestamp:
    d = pd.Timestamp(d)
    return d + pd.Timedelta(days=(4 - d.dayofweek) % 7)


def wk(a, b) -> float:
    return round((pd.Timestamp(a) - pd.Timestamp(b)).days / 7, 1)


def last_sf(d: pd.Timestamp) -> pd.Timestamp:
    sf = FEST[d.year][0]
    return sf if d >= sf else FEST[d.year - 1][0]


def season(d: pd.Timestamp) -> str:
    sf, dw, mid = FEST[d.year]
    if d < sf:
        return "旺季"
    if d <= dw:
        return "节后淡季"
    if d < mid - PEAK_LEAD:
        return "夏季淡季"
    return "旺季"


def weeks_since_sf(d: pd.Timestamp) -> float:
    return wk(d, last_sf(d))


# ---------------------------------------------------------------------------
# hog price: weekly composite
# ---------------------------------------------------------------------------
def hog_price():
    nx = pd.read_csv(PROC / "nxin_price_wide.csv")
    w_nx = pd.Series(nx["全国"].values, index=pd.to_datetime(nx["week_label"]) - pd.Timedelta(days=3)).dropna()
    dd = pd.read_csv(PROC / "nxin_province_daily.csv")
    dd = dd[dd["province"] == "全国"]
    dd = pd.Series(dd["price"].values, index=pd.to_datetime(dd["date"])).sort_index()
    dd = dd[dd.index <= ASOF]
    dw = dd.groupby(dd.index - pd.to_timedelta(dd.index.dayofweek, unit="D") + pd.Timedelta(days=4)).mean()
    ov = pd.concat([w_nx, dw], axis=1, keys=["w", "d"]).dropna().iloc[-26:]
    adj = float((ov["w"] - ov["d"]).mean())
    ext = dw[dw.index > w_nx.index.max()] + adj

    mh = pd.read_csv(PROC / "moa_hist_hog_prices.csv")
    mw = mh[mh["freq"] == "W"].copy()
    mw["d"] = pd.to_datetime(mw["obs"]).map(fri)
    mw = mw.sort_values(["d", "value_basis"]).drop_duplicates("d")
    mw_s = pd.Series(mw["live_hog"].astype(float).values, index=mw["d"])
    mw_basis = pd.Series(mw["value_basis"].values, index=mw["d"])
    ovw = pd.concat([np.log(w_nx), np.log(mw_s)], axis=1, keys=["n", "m"]).dropna()
    r_w = float(np.exp((ovw["n"] - ovw["m"]).mean()))

    mm = mh[mh["freq"] == "M"].copy()
    mm["p"] = pd.PeriodIndex(mm["obs"], freq="M")
    mm = mm.sort_values(["p", "value_basis"]).drop_duplicates("p").set_index("p")
    wmean = mw_s.groupby(mw_s.index.to_period("M")).agg(["mean", "size"])
    ovm = pd.concat([np.log(mm["live_hog"].astype(float)), np.log(wmean.loc[wmean["size"] >= 3, "mean"])],
                    axis=1, keys=["m", "w"]).dropna()
    r_m = float(np.exp((ovm["w"] - ovm["m"]).mean()))

    pts = {}
    for p, r in mm.iterrows():
        pts[fri(pd.Timestamp(p.year, p.month, 15))] = (float(r["live_hog"]) * r_m * r_w,
                                                        "农业部月报(月中,拼接)")
    for d, v in mw_s.items():
        pts[d] = (v * r_w, "农业部周报(拼接)" + ("" if mw_basis[d] == "本期(原文)" else ",次年同比反推"))
    for d, v in w_nx.items():
        pts[d] = (v, "新牧网周度")
    for d, v in ext.items():
        pts[d] = (v, "新牧网日度(调整)")
    raw = pd.DataFrame([(d, v, s) for d, (v, s) in pts.items()], columns=["d", "hog", "src"]).set_index("d")
    raw = raw.sort_index()
    grid = pd.date_range(fri("2003-12-01"), fri(ASOF), freq="W-FRI")
    lg = np.log(raw["hog"]).reindex(raw.index.union(grid)).interpolate("time", limit=26, limit_area="inside")
    hog = np.exp(lg.reindex(grid))
    src = raw["src"].reindex(grid).fillna("插值")
    meta = dict(r_nxin_over_moa_weekly=round(r_w, 4), n_overlap_weekly=len(ovw),
                r_moa_weekly_over_monthly=round(r_m, 4), n_overlap_monthly=len(ovm),
                nxin_daily_shift=round(adj, 3), last_weekly_nxin=str(w_nx.index.max().date()),
                last_daily_nxin=str(dd.index.max().date()))
    return hog.rename("hog"), src.rename("hog_src"), meta


def moa_weekly_2016():
    """MOA weekly 集贸 live-hog price 2016- (robustness check for turning points)."""
    m = pd.read_csv(PROC / "moa_weekly_prices.csv")
    d = pd.to_datetime(m["collect_date"], errors="coerce")
    iso = pd.to_datetime(m["year"].astype(str) + "-W" + m["week"].astype(int).map("{:02d}".format) + "-5",
                         format="%G-W%V-%u", errors="coerce")
    m["d"] = d.map(lambda x: fri(x) if pd.notna(x) else pd.NaT).fillna(iso)
    return m.dropna(subset=["d"]).drop_duplicates("d").set_index("d")["live_hog"].sort_index()


# ---------------------------------------------------------------------------
# stocks
# ---------------------------------------------------------------------------
def stock_closes() -> pd.DataFrame:
    sd = pd.read_csv(PROC / "stock_daily.csv", dtype={"code": str},
                     usecols=["code", "date", "close_hfq", "close_tx_hfq"])
    sd["code"] = sd["code"].str.zfill(6)
    sd = sd[sd["date"] <= ASOF.strftime("%Y-%m-%d")]
    has_tx = sd.groupby("code")["close_tx_hfq"].transform("count") > 0
    sd["close"] = np.where(has_tx, sd["close_tx_hfq"], sd["close_hfq"])
    px = sd.pivot(index="date", columns="code", values="close")
    px.index = pd.to_datetime(px.index)
    return px.sort_index()


def ew_index(px: pd.DataFrame, members, freq=None):
    """Equal-weight index of period returns; a stock enters after its first period in the window."""
    p = px.resample(freq).last() if freq else px
    rets = {}
    for code, a, b in members:
        if code not in p:
            continue
        s = p[code]
        fv, lv = s.first_valid_index(), s.last_valid_index()
        if fv is None:
            continue
        s = s.loc[fv:lv].ffill()
        r = s.pct_change()
        lo = max(pd.Timestamp(a), fv)
        r = r[(r.index > lo) & (r.index <= (pd.Timestamp(b) if b else p.index.max()))]
        rets[code] = r
    R = pd.DataFrame(rets).reindex(p.index)
    return (1 + R.mean(axis=1).fillna(0)).cumprod(), R.notna().sum(axis=1), R


def csi() -> dict[str, pd.Series]:
    c = pd.read_csv(PROC / "csi_index_daily.csv", dtype={"index": str})
    out = {}
    for code, g in c.groupby("index"):
        s = pd.Series(g["close"].values, index=pd.to_datetime(g["date"])).sort_index()
        out[code.zfill(6)] = s[s.index <= ASOF]
    return out


BETA_WIN = 104


def beta_excess(s: pd.Series, mkt: pd.Series):
    """Cumulative excess return over beta x market, beta from the previous BETA_WIN weeks (1 until 52
    weeks of history exist), so no future data enter a week's excess return."""
    r = np.log(s).diff()
    m = np.log(mkt).diff()
    ok = r.notna() & m.notna()
    rr, mm = r.where(ok), m.where(ok)
    beta = (rr.rolling(BETA_WIN, min_periods=52).cov(mm) / mm.rolling(BETA_WIN, min_periods=52).var()).shift(1)
    beta = beta.where(beta.notna() | ~ok, 1.0).where(ok)
    e = (rr - beta * mm).fillna(0).where(s.notna())
    return np.exp(e.cumsum()).where(s.notna()), beta


def build():
    hog, src, meta = hog_price()
    px = stock_closes()
    uni = [(c, a, b) for c, _, a, b in UNIVERSE]
    ew, n_ew, R = ew_index(px, uni, "W-FRI")
    lead, _, _ = ew_index(px, [m for m in uni if m[0] in LEADERS], "W-FRI")
    small, n_small, _ = ew_index(px, [m for m in uni if m[0] not in LEADERS], "W-FRI")
    ci = csi()
    W = pd.DataFrame({"ew": ew, "n_ew": n_ew, "lead": lead, "small": small, "n_small": n_small})
    W = W[(W.index >= "2005-01-07") & (W.index <= fri(ASOF))]
    W["csi_all"] = ci["000985"].resample("W-FRI").last().reindex(W.index)
    W["csi_livestock"] = ci["930707"].resample("W-FRI").last().reindex(W.index)
    W["lead"] = W["lead"].where(W.index > "2014-01-31")
    for c in ("ew", "lead", "small"):
        s = W[c].dropna()
        W[c] = W[c] / s.iloc[0]
    W["rs"] = W["ew"] / (W["csi_all"] / W["csi_all"].iloc[0])
    for c in ("ew", "lead", "small", "csi_livestock"):
        W[f"{c}_xs"], W[f"{c}_beta"] = beta_excess(W[c], W["csi_all"])
    W["hog"] = hog.reindex(W.index)
    W["hog_src"] = src.reindex(W.index)
    # daily equal-weight excess returns for event studies
    ew_d, _, _ = ew_index(px, uni)
    d = pd.DataFrame({"ew": ew_d}).loc["2005-01-04":]
    d["csi_all"] = ci["000985"].reindex(d.index)
    d["ex"] = d["ew"].pct_change() - d["csi_all"].pct_change()
    return W, hog, meta, px, R, d


# ---------------------------------------------------------------------------
# turning points and milestones
# ---------------------------------------------------------------------------
def zigzag(s: pd.Series, h: float) -> pd.DataFrame:
    x = np.log(s.dropna())
    thr = np.log(1 + h)
    out, mode = [], 0
    hi_d = lo_d = x.index[0]
    for d, v in x.items():
        if mode >= 0 and v > x[hi_d]:
            hi_d = d
        if mode <= 0 and v < x[lo_d]:
            lo_d = d
        if mode >= 0 and x[hi_d] - v >= thr:
            out.append((hi_d, "peak", d, False))
            mode, lo_d = -1, d
        elif mode <= 0 and v - x[lo_d] >= thr:
            out.append((lo_d, "trough", d, False))
            mode, hi_d = 1, d
    if mode == 1:
        out.append((hi_d, "peak", pd.NaT, True))
    elif mode == -1:
        out.append((lo_d, "trough", pd.NaT, True))
    df = pd.DataFrame(out, columns=["date", "kind", "confirm", "provisional"])
    df["value"] = s.reindex(df["date"]).values
    return df


def major_turns(s: pd.Series, h=H_HOG, min_amp=0.40, min_weeks=26) -> pd.DataFrame:
    """Zigzag points merged until every leg lasts >= min_weeks and moves >= log(1+min_amp)
    (in the spirit of Bry-Boschan). The unconfirmed last extreme is dropped."""
    z = zigzag(s, h)
    z = z[~z["provisional"]]
    pts = list(zip(z["date"], z["kind"]))
    x = np.log(s.dropna())
    thr = np.log(1 + min_amp)
    while True:
        for i in range(len(pts)):
            a = pts[i - 1][0] if i > 0 else x.index[0]
            b = pts[i + 1][0] if i + 1 < len(pts) else pts[i][0]
            seg = x.loc[a:b]
            pts[i] = (seg.idxmax() if pts[i][1] == "peak" else seg.idxmin(), pts[i][1])
        legs = [(i, wk(pts[i + 1][0], pts[i][0]), abs(x[pts[i + 1][0]] - x[pts[i][0]]))
                for i in range(len(pts) - 1)]
        bad = [g for g in legs if g[1] < min_weeks or g[2] < thr]
        if not bad:
            break
        i = min(bad, key=lambda g: g[2])[0]
        del pts[i: i + 2]
    df = pd.DataFrame(pts, columns=["date", "kind"])
    df["value"] = s.reindex(df["date"]).values
    return df


START_BANDS = (0.2, 0.3)      # main rule: above 30% of the amplitude after the last week within 20%
START_BANDS_ALT = (0.1, 0.2)  # robustness


def _start(x: pd.Series, t0, amp, bands) -> pd.Timestamp:
    lo, hi = x[t0] + bands[0] * amp, x[t0] + bands[1] * amp
    last_lo = x[x <= lo].index.max()
    after = x[(x.index > last_lo) & (x >= hi)]
    return after.index.min() if len(after) else pd.NaT


def milestones(s: pd.Series, t0, t1) -> dict:
    x = np.log(s.loc[t0:t1].dropna())
    if len(x) < 3:
        return {}
    t0, t1 = x.idxmin(), x.loc[x.idxmin():].idxmax()
    x = x.loc[t0:t1]
    amp = x[t1] - x[t0]
    r13 = (x.shift(-13) - x).dropna()
    accel = r13.idxmax() if len(r13) else pd.NaT
    return dict(trough=t0, start=_start(x, t0, amp, START_BANDS), start_alt=_start(x, t0, amp, START_BANDS_ALT),
                accel=accel, peak=t1, rise=float(np.exp(amp) - 1),
                v_trough=float(np.exp(x[t0])), v_peak=float(np.exp(x[t1])))


def final_rally_trough(s: pd.Series, peak, k: float, floor) -> pd.Timestamp:
    """Low of the last rally into `peak`: the lowest week after the last zigzag(k) peak before it."""
    z = zigzag(s.loc[:peak].dropna(), k)
    prev = z[(z["kind"] == "peak") & (z["date"] < peak) & ~z["provisional"]]
    a = max(prev["date"].max(), floor) if len(prev) else floor
    return s.loc[a:peak].idxmin()


def hog_legs(tp: pd.DataFrame) -> list[dict]:
    """Up-legs of the hog price with the neighbouring turning points (the last one may be open)."""
    legs = []
    rows = tp.reset_index(drop=True)
    for i, r in rows.iterrows():
        if r["kind"] != "trough":
            continue
        prev_peak = rows.loc[i - 1, "date"] if i > 0 else None
        peak = rows.loc[i + 1, "date"] if i + 1 < len(rows) else None
        nxt = rows.loc[i + 2, "date"] if i + 2 < len(rows) else None
        legs.append(dict(trough=r["date"], peak=peak, prev_peak=prev_peak, next_trough=nxt))
    return legs


STOCK_COLS = ("ew_xs", "ew", "rs", "lead_xs", "small_xs", "csi_livestock_xs")
ZONE = 0.05


def mid(a, b) -> pd.Timestamp:
    return pd.Timestamp(a) + (pd.Timestamp(b) - pd.Timestamp(a)) / 2


def cycle_table(W: pd.DataFrame, legs: list[dict]) -> pd.DataFrame:
    """Milestones of each hog up-leg and of the matching stock legs; lead = stock date - hog date.
    A stock trough is searched between the midpoints of the adjacent hog phases around the hog trough
    (previous peak -> trough -> peak), a stock peak likewise around the hog peak."""
    hog = W["hog"]
    rows = []
    for g in legs:
        T, P = g["trough"], g["peak"]
        name = f"{T.year}" + (f"—{P.year}" if P is not None else "—")
        if P is not None:
            mh = milestones(hog, T, P)
        else:
            mh = dict(trough=T, start=pd.NaT, accel=pd.NaT, peak=pd.NaT,
                      v_trough=float(hog[T]), v_peak=np.nan, rise=np.nan)
        rows.append(dict(cycle=name, series="hog", **mh))
        tw0 = mid(g["prev_peak"], T) if g["prev_peak"] is not None else T - pd.Timedelta(weeks=52)
        tw1 = mid(T, P) if P is not None else W.index[-1]
        pw1 = mid(P, g["next_trough"]) if g["next_trough"] is not None else W.index[-1]
        for col in STOCK_COLS:
            s = W[col].loc[max(tw0, W.index[0]):tw1].dropna()
            if len(s) < 13 or s.index[0] > tw0 + pd.Timedelta(weeks=8):
                continue
            ts = s.idxmin()
            zone = s[s <= s.min() * (1 + ZONE)].index
            m = dict(trough=ts, start=pd.NaT, accel=pd.NaT, peak=pd.NaT, rise=np.nan)
            if P is not None:
                sp = W[col].loc[tw1:pw1].dropna()
                ps = sp.idxmax()
                m = milestones(W[col], ts, ps)
                m["trough"], m["peak"] = ts, ps
                m["peak_at_window_end"] = bool(ps == sp.index[-1] and g["next_trough"] is not None)
                pz = sp[sp >= sp.max() / (1 + ZONE)].index
                m["peak_zone_first"], m["peak_zone_last"] = pz.min(), pz.max()
            m["zone_first"], m["zone_last"] = zone.min(), zone.max()
            m["n_members"] = int(W["n_ew"].loc[ts]) if col in ("ew", "rs", "ew_xs") else (
                int(W["n_small"].loc[ts]) if col == "small_xs" else np.nan)
            rows.append(dict(cycle=name, series=col, window_trough=f"{tw0.date()}~{tw1.date()}",
                             window_peak=f"{tw1.date()}~{pw1.date()}" if P is not None else "", **m))
    ct = pd.DataFrame(rows)
    hogm = ct[ct["series"] == "hog"].set_index("cycle")
    for k in ("trough", "start", "start_alt", "accel", "peak"):
        ct[f"lead_{k}_w"] = [wk(r[k], hogm.loc[r["cycle"], k]) if pd.notna(r[k]) and pd.notna(hogm.loc[r["cycle"], k])
                             else np.nan for _, r in ct.iterrows()]
    ct["lead_zone_last_w"] = [wk(r["zone_last"], hogm.loc[r["cycle"], "trough"]) if pd.notna(r.get("zone_last"))
                              else np.nan for _, r in ct.iterrows()]
    # where was the hog price when the stock leg started?
    def hog_pos(d, cyc):
        if pd.isna(d):
            return np.nan, np.nan
        h0 = hogm.loc[cyc]
        v = hog.asof(d)
        rise = v / h0["v_trough"] - 1 if d >= h0["trough"] else np.nan
        amp = (np.log(v / h0["v_trough"]) / np.log(h0["v_peak"] / h0["v_trough"])
               if pd.notna(h0["v_peak"]) and d >= h0["trough"] else np.nan)
        return rise, amp
    for k in ("trough", "start"):
        pos = [hog_pos(r[k], r["cycle"]) for _, r in ct.iterrows()]
        ct[f"hog_rise_at_{k}"] = [p[0] for p in pos]
        ct[f"hog_amp_at_{k}"] = [p[1] for p in pos]
    ct["season_trough"] = ct["trough"].map(lambda d: season(d) if pd.notna(d) else None)
    ct["season_start"] = ct["start"].map(lambda d: season(d) if pd.notna(d) else None)
    return ct


def launches(W: pd.DataFrame, col: str, k: float, hog_tp: pd.DataFrame) -> pd.DataFrame:
    s = W[col].dropna()
    z = zigzag(s, k)
    z = z[(z["kind"] == "trough") & ~z["provisional"]]
    troughs_h = hog_tp.loc[hog_tp["kind"] == "trough", "date"]
    rows = []
    for _, r in z.iterrows():
        t, c = r["date"], r["confirm"]
        v_t, v_c = s[t], s[c]
        fwd = s.loc[c:c + pd.Timedelta(weeks=52)]
        hit = fwd[fwd >= v_c * 1.30]
        fail = fwd[fwd <= v_t * 1.05]
        if len(hit) and (not len(fail) or hit.index[0] < fail.index[0]):
            outcome = "持续"
        elif len(fail):
            outcome = "失败"
        else:
            outcome = "平淡" if c + pd.Timedelta(weeks=52) <= s.index[-1] else "未满52周"
        nearest = troughs_h.iloc[(troughs_h - t).abs().argmin()]
        row = dict(series=col, trough=t, confirm=c, trough_value=v_t, rise_to_confirm=v_c / v_t - 1,
                   season_trough=season(t), season_confirm=season(c),
                   wk_since_sf_trough=weeks_since_sf(t), wk_since_sf_confirm=weeks_since_sf(c),
                   outcome=outcome, fwd52_max=float(fwd.max() / v_c - 1), fwd52_min=float(fwd.min() / v_c - 1),
                   nearest_hog_trough=nearest, wk_vs_hog_trough=wk(t, nearest))
        for h in (13, 26, 52):
            e = c + pd.Timedelta(weeks=h)
            row[f"ret{h}"] = float(s.asof(e) / v_c - 1) if e <= s.index[-1] else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def seasonal_norm(hog: pd.Series, src: pd.Series):
    """Weekly hog prices keyed by lunar year and week since Spring Festival; reference years are
    2011-2025 with weekly source data, excluding 2019-2020."""
    x = np.log(hog)
    real = ~src.reindex(hog.index).fillna("插值").isin(["插值"])
    df = pd.DataFrame({"lp": x, "dx": x.diff(), "real": real})
    df["sf"] = [last_sf(d) for d in df.index]
    df["lw"] = ((df.index.to_series() - df["sf"]).dt.days // 7).astype(int)
    df["year"] = df["sf"].dt.year
    use = df[(df["year"] >= 2011) & (df["year"] <= 2025) & ~df["year"].isin([2019, 2020])]
    return df, use


_PIVOT: dict = {}


def seas_exp(df: pd.DataFrame, use: pd.DataFrame, d0, d1, excl=None) -> float:
    """Median across reference years of the log change between the lunar positions of d0 and d1.
    Summing weekly medians would understate the seasonal swing, so the change is taken per year."""
    if id(use) not in _PIVOT:
        _PIVOT[id(use)] = use.pivot_table(index="year", columns="lw", values="lp")
    P = _PIVOT[id(use)]
    y0, l0 = df.at[d0, "year"], df.at[d0, "lw"]
    y1, l1 = df.at[d1, "year"], df.at[d1, "lw"]
    dy = y1 - y0
    if l0 not in P.columns or l1 not in P.columns:
        return np.nan
    v = [P.at[y, l1] - P.at[y - dy, l0] for y in P.index
         if y - dy in P.index and excl not in (y, y - dy)]
    return float(np.nanmedian(v)) if len(v) else np.nan


def surprise(df: pd.DataFrame, use: pd.DataFrame, d: pd.Timestamp, n=8) -> float:
    i = df.index.get_loc(d)
    d0 = df.index[i - n]
    return float(df.at[d, "lp"] - df.at[d0, "lp"] - seas_exp(df, use, d0, d, excl=df.at[d, "year"]))


def launch_context(L: pd.DataFrame, W: pd.DataFrame, sdf, use) -> pd.DataFrame:
    hog = W["hog"]
    out = []
    for _, r in L.iterrows():
        row = {}
        for tag in ("trough", "confirm"):
            d = r[tag]
            v = hog.asof(d)
            low52 = hog.loc[d - pd.Timedelta(weeks=52):d].min()
            row[f"hog_{tag}"] = v
            row[f"hog_vs_52w_low_{tag}"] = v / low52 - 1
            row[f"hog_chg4_{tag}"] = v / hog.asof(d - pd.Timedelta(weeks=4)) - 1
            row[f"hog_chg13_{tag}"] = v / hog.asof(d - pd.Timedelta(weeks=13)) - 1
            row[f"hog_yoy_{tag}"] = v / hog.asof(d - pd.Timedelta(weeks=52)) - 1
            row[f"hog_surprise8_{tag}"] = surprise(sdf, use, d) if d >= pd.Timestamp("2009-01-01") else np.nan
        out.append(row)
    return pd.concat([L.reset_index(drop=True), pd.DataFrame(out)], axis=1)


def base_rates(index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series([season(d) for d in index]).value_counts(normalize=True).reindex(SEASONS)


def seasonal_lows(hog: pd.Series) -> pd.DataFrame:
    """Each year's lowest week between Spring Festival and 中秋, and the highest week after it."""
    rows = []
    for y in range(2005, ASOF.year + 1):
        sf, dw, mid_ = FEST[y]
        s = hog.loc[sf:mid_]
        if len(s) < 10:
            continue
        lo = s.idxmin()
        post = hog.loc[mid_ - PEAK_LEAD: FEST[y + 1][0]]
        rows.append(dict(year=y, sf=sf, low=lo, low_season=season(lo), low_wk_since_sf=wk(lo, sf),
                         low_value=float(s.min()), sf_value=float(hog.asof(sf)),
                         low_vs_sf=float(s.min() / hog.asof(sf) - 1),
                         peak_after=post.idxmax() if len(post) else pd.NaT,
                         peak_after_vs_low=float(post.max() / s.min() - 1) if len(post) else np.nan,
                         src_real=bool(y >= 2009)))
    return pd.DataFrame(rows)


def season_summary(L: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.DataFrame:
    base = base_rates(idx)
    rows = []
    for tag in ("trough", "confirm"):
        cnt = L[f"season_{tag}"].value_counts().reindex(SEASONS).fillna(0)
        for sname in SEASONS:
            sub = L[L[f"season_{tag}"] == sname]
            done = sub[sub["outcome"].isin(["持续", "失败", "平淡"])]
            rows.append(dict(by=tag, season=sname, n=int(cnt[sname]), share=cnt[sname] / max(len(L), 1),
                             base_rate=base[sname], n_persist=int((done["outcome"] == "持续").sum()),
                             n_fail=int((done["outcome"] == "失败").sum()),
                             n_flat=int((done["outcome"] == "平淡").sum()),
                             med_ret26=sub["ret26"].median(), med_ret52=sub["ret52"].median(),
                             med_fwd52_max=sub["fwd52_max"].median()))
    return pd.DataFrame(rows)


def binom_p(k: int, n: int, p: float) -> float:
    """One-sided P(X >= k) for X ~ Binomial(n, p)."""
    from math import comb
    return float(sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)))


ERAS = [("2005-01", "2018-07", "非瘟前 2005—2018.07"), ("2018-08", "2021-12", "非瘟期 2018.08—2021"),
        ("2022-01", "2026-09", "非瘟后 2022—2026.09")]


def monthly(W: pd.DataFrame) -> pd.DataFrame:
    M = pd.DataFrame({"hog": W["hog"].resample("ME").mean()})
    for c in ("ew", "ew_xs", "rs", "lead_xs", "small_xs", "csi_livestock_xs"):
        M[c] = W[c].resample("ME").last()
    return M[M.index <= ASOF]


def xcorr(M: pd.DataFrame, col="ew_xs", horizons=(3, 12), lags=range(-12, 13)) -> pd.DataFrame:
    """corr(stock change over h months ending t, hog change over h months ending t+k); k>0: stock leads."""
    rows = []
    for a, b, name in ERAS:
        for h in horizons:
            s = np.log(M[col]).diff(h)
            g = np.log(M["hog"]).diff(h)
            for k in lags:
                x = pd.concat([s, g.shift(-k)], axis=1, keys=["s", "g"]).loc[a:b].dropna()
                rows.append(dict(era=name, series=col, horizon_m=h, lead_m=k, corr=x["s"].corr(x["g"]), n=len(x),
                                 same_sign=float((np.sign(x["s"]) == np.sign(x["g"])).mean())))
    return pd.DataFrame(rows)


def surprise_corr(W: pd.DataFrame, sdf: pd.DataFrame, use: pd.DataFrame, col="ew_xs") -> pd.DataFrame:
    """Non-overlapping 4-week blocks from 2011: stock excess change vs raw hog change and vs the
    seasonal surprise (raw change minus the median change for the same weeks after Spring Festival in
    other years), same block and with the stock block leading by 1-3 blocks."""
    x = sdf.loc["2011-01-01":]
    ls = np.log(W[col]).reindex(x.index)
    rows = []
    for off in range(4):
        rows_b = []
        for p in range(4 + off, len(x), 4):
            t0, t = x.index[p - 4], x.index[p]
            raw = x.at[t, "lp"] - x.at[t0, "lp"]
            rows_b.append(dict(date=t, raw=raw, sur=raw - seas_exp(sdf, use, t0, t, excl=x.at[t, "year"]),
                               s=ls[t] - ls[t0]))
        B = pd.DataFrame(rows_b).set_index("date")
        for a, b, name in [("2011-01", "2018-07", "非瘟前 2011—2018.07")] + ERAS[1:] + \
                          [("2025-07", "2026-10", "本轮 2025.07—2026.10")]:
            for j in (0, 1, 2, 3):
                z = pd.concat([B["s"], B["raw"].shift(-j), B["sur"].shift(-j)], axis=1, keys=["s", "raw", "sur"])
                z = z.loc[a:b].dropna()
                rows.append(dict(era=name, stock_leads_blocks=j, offset=off, n=len(z), corr_raw=z["s"].corr(z["raw"]),
                                 corr_surprise=z["s"].corr(z["sur"])))
    R_ = pd.DataFrame(rows)
    return R_.groupby(["era", "stock_leads_blocks"], sort=False).agg(
        n=("n", "mean"), corr_raw=("corr_raw", "mean"), corr_raw_min=("corr_raw", "min"),
        corr_raw_max=("corr_raw", "max"), corr_surprise=("corr_surprise", "mean"),
        corr_surprise_min=("corr_surprise", "min"), corr_surprise_max=("corr_surprise", "max")).reset_index()


POLICY_EVENTS = [
    ("2025-06-17", "媒体报道头部猪企被要求暂停能繁扩产", "C"),
    ("2025-07-23", "农业农村部座谈会：合理淘汰能繁、严控新增产能", "A"),
    ("2025-09-08", "农业农村部文章：半年左右调减100万头能繁母猪", "A"),
    ("2025-09-17", "媒体报道生猪产能调控企业座谈会(9-16召开)", "C"),
    ("2026-03-09", "设备更新贷款原则上不支持扩大生猪养殖规模", "A"),
    ("2026-04-28", "政治局会议「稳定生猪等农产品价格」", "A"),
    ("2026-04-30", "四部门部署冻猪肉商业储备收储", "C"),
    ("2026-05-14", "产能调控方案(2026修订)公布，正常保有量3750万头", "A"),
    ("2026-06-22", "部委通稿：大型企业带头压减产能", "A"),
    ("2026-07-15", "统计局：二季度末生猪存栏同比+0.1%；次日解读稿：能繁3780万头，同比-6.5%", "A"),
    ("2026-07-30", "政治局会议「稳定生猪等农畜产品生产和价格」", "A"),
    ("2026-09-07", "十五五畜牧兽医规划公开：动态调整产能目标", "A"),
]


def daily_excess(D: pd.DataFrame, W: pd.DataFrame) -> pd.Series:
    beta = W["ew_beta"].dropna()
    b = beta.reindex(D.index, method="ffill").fillna(1.0)
    return D["ew"].pct_change() - b * D["csi_all"].pct_change()


def car(ex: pd.Series, day, a: int, b: int) -> float:
    idx = ex.index
    i = idx.searchsorted(pd.Timestamp(day))
    if i + b >= len(idx) or i + a < 1:
        return np.nan
    return float(ex.iloc[i + a: i + b + 1].sum())


def ols(y, x):
    z = pd.concat([y, x], axis=1).dropna()
    if len(z) < 5:
        return dict(n=len(z), slope=np.nan, t=np.nan, r2=np.nan)
    X = np.column_stack([np.ones(len(z)), z.iloc[:, 1]])
    beta, res, *_ = np.linalg.lstsq(X, z.iloc[:, 0], rcond=None)
    e = z.iloc[:, 0] - X @ beta
    s2 = (e ** 2).sum() / (len(z) - 2)
    se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
    r2 = 1 - (e ** 2).sum() / ((z.iloc[:, 0] - z.iloc[:, 0].mean()) ** 2).sum()
    return dict(n=len(z), slope=float(beta[1]), t=float(beta[1] / se), r2=float(r2))


def event_studies(D: pd.DataFrame, W: pd.DataFrame):
    ex = daily_excess(D, W)
    rows = []
    ms = pd.read_csv(PROC / "moa_sows_monthly.csv")
    ms = ms[ms["release_date"].notna() & ms["sow_mom_pct"].notna()]
    for _, r in ms.iterrows():
        rows.append(dict(kind="农业农村部月度能繁环比", date=pd.Timestamp(r["release_date"]), period=r["month"],
                         value=float(r["sow_mom_pct"]), label=f"{r['month']} 能繁环比{r['sow_mom_pct']:+.1f}%"))
    nq = pd.read_csv(PROC / "nbs_quarterly.csv")
    nq = nq[nq["release_date"].notna()].sort_values("period")
    nq["d_hog_yoy"] = nq["hog_inventory_yoy_pct"].diff()
    for _, r in nq.iterrows():
        rows.append(dict(kind="统计局季度存栏", date=pd.Timestamp(r["release_date"]), period=r["period"],
                         value=float(r["hog_inventory_yoy_pct"]), value2=float(r["d_hog_yoy"]),
                         sow_yoy=r.get("sow_inventory_yoy_pct"),
                         label=f"{r['period']} 生猪存栏同比{r['hog_inventory_yoy_pct']:+.1f}%"))
    for d, lab, grade in POLICY_EVENTS:
        rows.append(dict(kind="2025—2026政策与数据", date=pd.Timestamp(d), period="", value=np.nan, label=lab,
                         grade=grade))
    E = pd.DataFrame(rows)
    for a, b in ((0, 1), (0, 5), (-5, -1)):
        E[f"car_{a}_{b}"] = [car(ex, d, a, b) for d in E["date"]]
    E["trade_day"] = [ex.index[min(ex.index.searchsorted(d), len(ex) - 1)] for d in E["date"]]
    two_day = ex.rolling(2).sum().dropna()
    reg = []
    for kind, xcol in (("农业农村部月度能繁环比", "value"), ("统计局季度存栏", "value"), ("统计局季度存栏", "value2")):
        sub = E[E["kind"] == kind]
        for a, b, name in (("2015-01-01", "2018-07-31", "非瘟前"), ("2018-08-01", "2021-12-31", "非瘟期"),
                           ("2022-01-01", "2026-12-31", "非瘟后"), ("2015-01-01", "2026-12-31", "全部")):
            s = sub[(sub["date"] >= a) & (sub["date"] <= b)]
            if not len(s):
                continue
            o = ols(s["car_0_1"], s[xcol])
            reg.append(dict(kind=kind, x=xcol, period=name, **o, mean_abs_car01=float(s["car_0_1"].abs().mean()),
                            base_abs_2d=float(two_day.loc[a:b].abs().mean())))
    return E, pd.DataFrame(reg), ex


def debt_at(fin: pd.DataFrame, code: str, d: pd.Timestamp) -> float:
    f = fin[(fin["code"] == code) & (fin["report_date"] <= d)]
    return float(f.sort_values("report_date")["debt_ratio"].iloc[-1]) if len(f) else np.nan


def phase_windows(ct: pd.DataFrame) -> dict:
    """First wave (expectation) and second wave (realisation) per cycle. 2018-19 keeps the main
    report's windows; later cycles: stock excess trough -> hog sustained start -> stock excess peak."""
    hogm = ct[ct["series"] == "hog"].set_index("cycle")
    ewm = ct[ct["series"] == "ew_xs"].set_index("cycle")
    out = {"2018—2019": [("预期段", pd.Timestamp("2018-12-28"), pd.Timestamp("2019-04-30")),
                         ("兑现段", pd.Timestamp("2019-04-30"), pd.Timestamp("2021-02-26"))]}
    for cyc in ("2021—2022", "2024—2024"):
        t0, hs, t2 = ewm.loc[cyc, "trough"], hogm.loc[cyc, "start"], ewm.loc[cyc, "peak"]
        out[cyc] = [("预期段", t0, min(hs, t2))] + ([("兑现段", hs, t2)] if hs < t2 else [])
    out["2026—"] = [("预期段(进行中)", ewm.loc["2026—", "trough"], ASOF)]
    return out


def company_cycles(W, px, legs, ct) -> tuple[pd.DataFrame, pd.DataFrame]:
    fin = pd.read_csv(PROC / "fin_quarterly.csv", dtype={"code": str})
    fin["code"] = fin["code"].str.zfill(6)
    fin["report_date"] = pd.to_datetime(fin["report_date"])
    mi = pd.read_csv(PROC / "model_company_inputs.csv", dtype={"code": str})
    mi["code"] = mi["code"].str.zfill(6)
    cost = mi.set_index("code")["cost_latest"]
    wkpx = px.resample("W-FRI").last()
    phases = phase_windows(ct)
    rows = []
    for g in legs:
        T, P = g["trough"], g["peak"]
        if T.year < 2018:
            continue
        name = f"{T.year}" + (f"—{P.year}" if P is not None else "—")
        tw0 = mid(g["prev_peak"], T)
        tw1 = mid(T, P) if P is not None else W.index[-1]
        pw1 = mid(P, g["next_trough"]) if g["next_trough"] is not None else W.index[-1]
        for code, cname, a, b in UNIVERSE:
            if code not in wkpx or (b and pd.Timestamp(b) < T) or pd.Timestamp(a) > tw1:
                continue
            s = wkpx[code].loc[:pd.Timestamp(b) if b else None]
            fv = s.first_valid_index()
            if fv is None or fv > tw0:
                continue
            s = s.loc[fv:].ffill()
            xs, _ = beta_excess(s, W["csi_all"].reindex(s.index))
            row = dict(cycle=name, code=code, name=cname, group="龙头" if code in LEADERS else "中小",
                       debt_ratio=debt_at(fin, code, T), cost_2026=cost.get(code, np.nan) if P is None else np.nan)
            sw = xs.loc[tw0:tw1].dropna()
            row["trough"] = sw.idxmin()
            row["lead_trough_w"] = wk(row["trough"], T)
            if P is not None:
                sp = xs.loc[tw1:pw1].dropna()
                row["peak"] = sp.idxmax()
                row["lead_peak_w"] = wk(row["peak"], P)
            for lab, t0, t1 in phases[name]:
                row[f"xs_{lab}"] = float(xs.asof(t1) / xs.asof(t0) - 1)
                row[f"abs_{lab}"] = float(s.asof(t1) / s.asof(t0) - 1)
            if P is None:
                row["abs_since_spot_trough"] = float(s.iloc[-1] / s.asof(T) - 1)
            rows.append(row)
    CC = pd.DataFrame(rows)
    summ = []
    for cyc, g in CC.groupby("cycle", sort=False):
        for lab, _, _ in phases[cyc]:
            c = f"xs_{lab}"
            summ.append(dict(cycle=cyc, phase=lab, window=" ~ ".join(f"{d:%Y-%m-%d}" for d in
                                                                   [x for x in phases[cyc] if x[0] == lab][0][1:]),
                             med_leaders=g.loc[g["group"] == "龙头", c].median(),
                             med_small=g.loc[g["group"] == "中小", c].median(),
                             spearman_debt=g[[c, "debt_ratio"]].corr(method="spearman").iloc[0, 1],
                             n=int(g[c].notna().sum())))
        summ.append(dict(cycle=cyc, phase="见顶时点(周,相对猪价高点)", window="",
                         med_leaders=g.loc[g["group"] == "龙头", "lead_peak_w"].median() if "lead_peak_w" in g else np.nan,
                         med_small=g.loc[g["group"] == "中小", "lead_peak_w"].median() if "lead_peak_w" in g else np.nan,
                         spearman_debt=g[["lead_peak_w", "debt_ratio"]].corr(method="spearman").iloc[0, 1]
                         if "lead_peak_w" in g and g["lead_peak_w"].notna().sum() > 3 else np.nan,
                         n=int(g["lead_peak_w"].notna().sum()) if "lead_peak_w" in g else 0))
    return CC, pd.DataFrame(summ)


def realised_turns(W: pd.DataFrame, tp: pd.DataFrame) -> pd.DataFrame:
    ms = pd.read_csv(PROC / "monthly_sales.csv", dtype={"code": str})
    ms["code"] = ms["code"].str.zfill(6)
    ms = ms[(ms["months_covered"] == 1) & ms["price"].notna()]
    ms["m"] = pd.PeriodIndex(ms["month_key"], freq="M")
    nat = W["hog"].resample("ME").mean()
    nat.index = nat.index.to_period("M")
    rows = []
    for _, t in tp[tp["date"] >= "2018-01-01"].iterrows():
        m0 = t["date"].to_period("M")
        win = pd.period_range(m0 - 4, m0 + 4, freq="M")
        f = (lambda s: s.idxmin()) if t["kind"] == "trough" else (lambda s: s.idxmax())
        nm = f(nat.reindex(win).dropna())
        for code in ("002714", "300498", "000876", "002157", "605296", "001201", "600975"):
            s = ms[ms["code"] == code].set_index("m")["price"].reindex(win).dropna()
            if len(s) < 5:
                continue
            cm = f(s)
            rows.append(dict(turn=f"{t['date']:%Y-%m} {'低点' if t['kind'] == 'trough' else '高点'}", code=code,
                             name=NAMES.get(code, code), national_month=str(nm), company_month=str(cm),
                             lag_m=(cm - nm).n))
    return pd.DataFrame(rows)


def facts_2026(W: pd.DataFrame, sdf, use) -> dict:
    f = {}
    h = W["hog"]
    s26 = h.loc["2026-01-01":]
    f["spot_trough"] = (s26.idxmin(), float(s26.min()))
    after = h.loc[s26.idxmin():]
    f["spot_high_after"] = (after.idxmax(), float(after.max()))
    f["spot_last"] = (h.dropna().index[-1], float(h.dropna().iloc[-1]))
    for c in ("ew", "ew_xs", "lead_xs", "small_xs", "lead", "small"):
        s = W[c].loc["2026-01-01":].dropna()
        lo = W["ew_xs"].loc["2026-01-01":].idxmin()
        f[f"{c}_since_ew_trough"] = float(s.iloc[-1] / s.asof(lo) - 1)
    f["ew_trough"] = W["ew"].loc["2026-01-01":].idxmin()
    last = h.dropna().index[-1]
    sf_wk = sdf.index[sdf.index >= FEST[2026][0]][0]
    for lab, d0 in (("sf", sf_wk), ("spot_trough", f["spot_trough"][0]),
                    ("summer_high", f["spot_high_after"][0]), ("ew_trough", f["ew_trough"])):
        act = float(sdf.at[last, "lp"] - sdf.at[d0, "lp"])
        exp_ = seas_exp(sdf, use, d0, last, excl=2026)
        f[f"spot_chg_since_{lab}"] = float(np.expm1(act))
        f[f"seasonal_median_chg_since_{lab}"] = float(np.expm1(exp_))
        f[f"surprise_since_{lab}"] = act - exp_
    try:
        fu = pd.read_csv(PROC / "futures_lh_daily.csv")
        fu["trade_date"] = pd.to_datetime(fu["trade_date"])
        lo = f["ew_trough"]
        for c in ("LH2611", "LH2701", "LH2705", "LH2709"):
            s = fu[fu["contract"] == c].set_index("trade_date")["close"].sort_index()
            if len(s):
                f[f"{c}_since_stock_trough"] = float(s.iloc[-1] / s.asof(lo + pd.Timedelta(days=-1)) - 1)
                f[f"{c}_last"] = float(s.iloc[-1])
        lh0 = fu[fu["contract"] == "LH0"].set_index("trade_date")["close"].sort_index().loc["2026-01-01":]
        f["LH0_trough"] = (lh0.idxmin(), float(lh0.min()))
    except FileNotFoundError:
        pass
    return f


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------
CHART_EVENTS = [
    ("2007-07-30", "国务院扶持生猪生产"), ("2009-04-27", "甲型H1N1(“猪流感”)"),
    ("2018-08-03", "首例非洲猪瘟"), ("2019-09-06", "国办稳产保供意见"),
    ("2021-09-19", "产能调控方案(暂行)"), ("2024-02-29", "产能调控方案(2024修订)"),
    ("2025-07-23", "部座谈会:严控新增产能"), ("2025-09-08", "调减100万头能繁"),
    ("2026-04-28", "政治局:稳定生猪价格"), ("2026-05-14", "正常保有量3750万"),
    ("2026-06-22", "带头压减产能"), ("2026-07-16", "统计局:能繁同比-6.5%"),
    ("2026-07-30", "政治局:稳定生产和价格"),
]
CYCLE_PANEL_2026 = ("调减100万头能繁", "正常保有量3750万", "统计局:能繁同比-6.5%")  # labels shown in the 2026 cycle panel
SEASON_COLORS = {"节后淡季": "#dbe9f4", "夏季淡季": "#e3f1df"}


def shade_seasons(ax, a, b):
    for y in range(a.year - 1, b.year + 1):
        sf, dw, mid_ = FEST[y]
        ax.axvspan(sf, dw, color=SEASON_COLORS["节后淡季"], lw=0, zorder=0)
        ax.axvspan(dw, mid_ - PEAK_LEAD, color=SEASON_COLORS["夏季淡季"], lw=0, zorder=0)
    ax.set_xlim(a, b)


def chart_cycles(W, ct):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
    from plotstyle import C, save, source, title
    panels = [("2006—2008", "2005-07-01", "2009-06-30"), ("2009—2011", "2008-09-01", "2012-12-31"),
              ("2014—2016", "2013-01-01", "2017-06-30"), ("2018—2019", "2017-01-01", "2021-06-30"),
              ("2021—2022", "2020-10-01", "2025-06-30"), ("2026—", "2025-01-01", str(W.index[-1].date()))]
    fig, axes = plt.subplots(3, 2, figsize=(15, 13))
    mk = {"trough": "^", "start": "o", "peak": "v"}
    for ax, (cyc, a, b) in zip(axes.flat, panels):
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        shade_seasons(ax, a, b)
        sub = W.loc[a:b]
        xs = sub["ew_xs"] / sub["ew_xs"].dropna().iloc[0]
        ab = sub["ew"] / sub["ew"].dropna().iloc[0]
        ax.plot(xs.index, xs, color=C["stock"], lw=1.8, label="猪企等权超额(扣除beta×中证全指)")
        ax.plot(ab.index, ab, color=C["grey"], lw=0.9, ls="--", label="猪企等权指数(绝对)")
        ax.set_yscale("log")
        ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 1.5, 2.0, 3.0, 5.0, 7.0)))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_ylabel("股价(起点=1，对数)")
        ax2 = ax.twinx()
        ax2.plot(sub.index, sub["hog"], color=C["spot"], lw=1.6, label="全国生猪均价(元/公斤，右轴)")
        ax2.set_ylabel("元/公斤")
        ax2.grid(False)
        ax2.spines["right"].set_visible(True)
        cycs = [cyc] + (["2024—2024"] if cyc == "2021—2022" else [])
        for cc in cycs:
            h = ct[(ct["cycle"] == cc) & (ct["series"] == "hog")].iloc[0]
            e = ct[(ct["cycle"] == cc) & (ct["series"] == "ew_xs")].iloc[0]
            for k, m in mk.items():
                if pd.notna(h.get(k)) and a <= h[k] <= b:
                    ax2.plot(h[k], W["hog"].asof(h[k]), m, color=C["spot2"], ms=9, mec="white", zorder=5)
                if pd.notna(e.get(k)) and a <= e[k] <= b:
                    ax.plot(e[k], xs.asof(e[k]), m, color=C["stock"], ms=9, mec="white", zorder=5)
        for d, lab in CHART_EVENTS:
            d = pd.Timestamp(d)
            if a <= d <= b and (d.year < 2025 or lab in CYCLE_PANEL_2026):
                ax.axvline(d, color="#777777", lw=0.7, ls=":")
                ax.text(d, 0.98, " " + lab, transform=ax.get_xaxis_transform(), fontsize=7.5, rotation=90,
                        va="top", ha="right", color="#555555")
        n = ct[(ct["cycle"] == cyc) & (ct["series"] == "ew_xs")]["n_members"]
        ax.set_title(f"{cyc} 轮" + (f"（猪企样本 {int(n.iloc[0])} 家）" if len(n) and pd.notna(n.iloc[0]) else ""),
                     loc="left")
    handles = [Line2D([], [], color=C["stock"], lw=1.8, label="猪企等权超额收益（扣除滚动beta×中证全指）"),
               Line2D([], [], color=C["grey"], lw=0.9, ls="--", label="猪企等权指数（绝对）"),
               Line2D([], [], color=C["spot"], lw=1.6, label="全国生猪均价（右轴）"),
               Line2D([], [], marker="^", ls="", color="k", label="底部"),
               Line2D([], [], marker="o", ls="", color="k", label="持续上涨启动"),
               Line2D([], [], marker="v", ls="", color="k", label="见顶"),
               Patch(color=SEASON_COLORS["节后淡季"], label="节后淡季（春节→端午）"),
               Patch(color=SEASON_COLORS["夏季淡季"], label="夏季淡季（端午→中秋前3周）")]
    fig.legend(handles=handles, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.035), fontsize=9)
    title(fig, "历轮猪周期：猪企股价与生猪价格的拐点对照",
          "橙色为猪价、蓝绿色为股价超额收益的底部/启动/见顶；未着色区间为旺季（中秋前3周→次年春节）")
    source(fig, "猪价2015年起为新牧网周度成交均价，此前为农业部集贸市场周报/月报按重叠期比例拼接；"
                "股价为后复权周收盘、等权（按上市与转型时间纳入）；拐点规则见正文“方法”。", y=-0.065)
    fig.tight_layout()
    return save(fig, "i05_cycles.png")


def chart_leadlag(ct):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    order = ["2006—2008", "2009—2011", "2014—2016", "2018—2019", "2021—2022", "2024—2024", "2026—"]
    labels = {"2024—2024": "2024", "2026—": "2026(进行中)"}
    ser = [("ew_xs", "等权超额", C["stock"], "o", True), ("lead_xs", "龙头超额(牧原+温氏)", C["wens"], "s", True),
           ("small_xs", "中小猪企超额", C["small"], "^", True), ("ew", "等权绝对", C["grey"], "o", False)]
    ms = [("trough", "底部"), ("start", "持续上涨启动"), ("accel", "加速"), ("peak", "见顶")]
    fig, axes = plt.subplots(1, 4, figsize=(15, 5.6), sharey=True)
    for ax, (k, lab) in zip(axes, ms):
        ax.axvspan(-80, 0, color="#eef4f6", lw=0, zorder=0)
        ax.axvline(0, color="#444444", lw=0.8)
        for j, (col, sl, color, m, filled) in enumerate(ser):
            for i, cyc in enumerate(order):
                r = ct[(ct["cycle"] == cyc) & (ct["series"] == col)]
                if not len(r) or pd.isna(r.iloc[0].get(f"lead_{k}_w")):
                    continue
                v = float(np.clip(r.iloc[0][f"lead_{k}_w"], -78, 78))
                ax.plot(v, i + (j - 1.5) * 0.16, m, color=color, mfc=color if filled else "white", ms=7,
                        label=sl if (i == 0 or cyc == "2018—2019") else None)
        ax.set_title(lab, loc="left")
        ax.set_xlim(-80, 80)
        ax.set_xlabel("周（负值=股价早于猪价）")
        ax.text(-78, len(order) - 0.45, "股价领先", fontsize=8, color="#557a85")
    axes[0].set_yticks(range(len(order)))
    axes[0].set_yticklabels([labels.get(c, c) for c in order])
    axes[0].invert_yaxis()
    h, l = axes[3].get_legend_handles_labels()
    uniq = dict(zip(l, h))
    fig.legend(uniq.values(), uniq.keys(), loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.06))
    title(fig, "每轮的领先与滞后：股价拐点减猪价拐点（周）",
          "超过±78周的值画在边界；2006—2011年猪企样本只有2—3家，绝对指数受大盘牛熊影响大")
    source(fig, "本项目计算；股价超额=扣除滚动104周beta×中证全指的累计收益；底部/高点在相邻猪价阶段中点之间搜索。", y=-0.1)
    fig.tight_layout()
    return save(fig, "i05_leadlag.png")


def chart_seasons(W, sdf, use, L, lows, idx):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.2), gridspec_kw=dict(width_ratios=[1.25, 1.25, 0.8]))
    ax = axes[0]
    x = sdf.loc["2011-01-01":].copy()
    x = x[(x["year"] >= 2011) & ~x["year"].isin([2019, 2020]) & (x["year"] < 2026)]
    x["lp"] = np.log(W["hog"].reindex(x.index))
    x["dev"] = x["lp"] - x.groupby("year")["lp"].transform("first")
    prof = x[x["lw"] <= 50].groupby("lw")["dev"].quantile([0.25, 0.5, 0.75]).unstack()
    ax.axvspan(0, 17, color=SEASON_COLORS["节后淡季"], lw=0)
    ax.axvspan(17, 30, color=SEASON_COLORS["夏季淡季"], lw=0)
    ax.fill_between(prof.index, np.exp(prof[0.25]) - 1, np.exp(prof[0.75]) - 1, color=C["spot"], alpha=0.25,
                    lw=0, label="四分位区间")
    ax.plot(prof.index, np.exp(prof[0.5]) - 1, color=C["spot2"], lw=2, label="中位数")
    ax.axhline(0, color="#444444", lw=0.7)
    lw_lows = lows[lows["year"] >= 2009]["low_wk_since_sf"]
    ax.plot(lw_lows, np.full(len(lw_lows), -0.27), "|", color=C["dark"], ms=12, label="各年春节→中秋最低周")
    ax.set_xlabel("春节后第几周")
    ax.set_ylabel("相对春节当周的猪价")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.0%}"))
    ax.set_title("猪价的农历季节性（2011—2025，剔除2019—2020）", loc="left")
    ax.legend(loc="upper left")
    ax = axes[1]
    ax.axvspan(0, 17, color=SEASON_COLORS["节后淡季"], lw=0)
    ax.axvspan(17, 30, color=SEASON_COLORS["夏季淡季"], lw=0)
    colors = {"持续": C["fut3"], "失败": C["fut4"], "平淡": C["grey"], "未满52周": C["fut1"]}
    for _, r in L.iterrows():
        y = r["trough"].year + r["trough"].dayofyear / 366
        x0, x1 = r["wk_since_sf_trough"], r["wk_since_sf_confirm"]
        if x1 < x0:
            x1 += 52
        ax.plot([x0, x1], [y, y], color=colors[r["outcome"]], lw=1.2)
        ax.plot(x0, y, "o", color=colors[r["outcome"]], ms=7)
        ax.plot(x1, y, "x", color=colors[r["outcome"]], ms=7, mew=1.6)
    for k, c in colors.items():
        ax.plot([], [], "o", color=c, label=k)
    ax.plot([], [], "o", color="k", mfc="white", label="股价超额底部")
    ax.plot([], [], "x", color="k", label="启动确认(底部上涨20%)")
    ax.set_xlim(-2, 72)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v)}"))
    ax.set_xlabel("春节后第几周（超过52周为跨到次年）")
    ax.set_title("历次股价启动：底部与确认时点", loc="left")
    ax.legend(loc="upper right", fontsize=7.5, ncol=2)
    ax = axes[2]
    base = base_rates(idx)
    tro = L["season_trough"].value_counts(normalize=True).reindex(SEASONS).fillna(0)
    con = L["season_confirm"].value_counts(normalize=True).reindex(SEASONS).fillna(0)
    xx = np.arange(3)
    ax.bar(xx - 0.27, base, 0.27, color="#cfcfcf", label="全年周数占比")
    ax.bar(xx, tro, 0.27, color=C["stock"], label="股价底部")
    ax.bar(xx + 0.27, con, 0.27, color=C["fut1"], alpha=0.7, label="启动确认")
    ax.set_xticks(xx)
    ax.set_xticklabels(SEASONS)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_title(f"落在各季节的占比（n={len(L)}）", loc="left")
    ax.legend(loc="upper left", fontsize=8)
    title(fig, "“淡季启动”：猪价有季节性，股价启动的季节聚集不稳健",
          "股价按猪企等权超额收益的20%阈值识别；节后淡季=春节→端午，夏季淡季=端午→中秋前3周")
    source(fig, "本项目计算；季节性中位数只用2011年后有周度原始数据的年份。", y=-0.04)
    fig.tight_layout()
    return save(fig, "i05_seasons.png")


def chart_xcorr(xc):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    cols = {ERAS[0][2]: C["grey"], ERAS[1][2]: C["fut4"], ERAS[2][2]: C["stock"]}
    for ax, h in zip(axes, (3, 12)):
        for era, color in cols.items():
            s = xc[(xc["series"] == "ew_xs") & (xc["era"] == era) & (xc["horizon_m"] == h)]
            ax.plot(s["lead_m"], s["corr"], color=color, lw=2, label=f"{era}（n≈{int(s['n'].median())}个月）")
            b = s.loc[s["corr"].idxmax()]
            ax.plot(b["lead_m"], b["corr"], "o", color=color, ms=7)
            ax.annotate(f"{int(b['lead_m']):+d}月 {b['corr']:.2f}", (b["lead_m"], b["corr"]), fontsize=8,
                        xytext=(4, 6), textcoords="offset points", color=color)
        ax.axvline(0, color="#444444", lw=0.7)
        ax.axhline(0, color="#444444", lw=0.5)
        ax.set_xlabel("股价领先月数（正值=股价变动在前）")
        ax.set_title(f"{h}个月变动的互相关", loc="left")
    axes[0].set_ylabel("相关系数")
    axes[0].legend(loc="lower left", fontsize=8)
    title(fig, "分时期看：股价超额收益与猪价变动谁在前",
          "股价为猪企等权超额收益（扣除beta×中证全指）；月度重叠窗口，相关系数会被放大，非瘟期样本基本只有一轮")
    source(fig, "本项目计算。", y=-0.03)
    fig.tight_layout()
    return save(fig, "i05_xcorr.png")


def chart_2026(W, sdf, use, E):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    a = pd.Timestamp("2025-06-01")
    lo = W["ew_xs"].loc["2026-01-01":].idxmin()
    fig, axes = plt.subplots(2, 1, figsize=(13, 8.6), sharex=True)
    ax = axes[0]
    for c, lab, color, ls in (("ew", "猪企等权指数", C["stock"], "-"), ("ew_xs", "猪企等权超额", C["fut3"], "-"),
                              ("csi_all", "中证全指", C["grey"], "--")):
        s = W[c].loc[a:].ffill()
        ax.plot(s.index, s / s.asof(lo) * 100, color=color, ls=ls, lw=1.8, label=lab)
    ax.axhline(100, color="#444444", lw=0.6)
    ax.set_ylabel(f"{lo:%Y-%m-%d}=100")
    ax.legend(loc="upper left")
    ax.set_title("股价：6月底见底后逆大盘上行", loc="left")
    ax = axes[1]
    h = W["hog"].loc[a:]
    ax.plot(h.index, h, color=C["spot"], lw=2, label="全国生猪均价（周）")
    t0 = W["hog"].loc["2026-01-01":].idxmin()
    days = sdf.loc[t0:].index
    path = pd.Series([W["hog"][t0] * np.exp(seas_exp(sdf, use, t0, d, excl=2026)) for d in days], index=days)
    ax.plot(path.index, path, color=C["spot2"], lw=1.4, ls=":", label="若从4月低点起走常年季节路径（中位数）")
    t1 = W["hog"].loc[t0:].idxmax()
    days = sdf.loc[t1:].index
    path = pd.Series([W["hog"][t1] * np.exp(seas_exp(sdf, use, t1, d, excl=2026)) for d in days], index=days)
    ax.plot(path.index, path, color=C["spot2"], lw=1.4, ls="--", label="若从7月高点起走常年季节路径（中位数）")
    try:
        fu = pd.read_csv(PROC / "futures_lh_daily.csv")
        fu["trade_date"] = pd.to_datetime(fu["trade_date"])
        for cc, color in (("LH2611", C["fut1"]), ("LH2701", C["fut2"]), ("LH2705", C["fut4"])):
            s = fu[fu["contract"] == cc].set_index("trade_date")["close"].sort_index().loc[a:] / 1000
            ax.plot(s.index, s, color=color, lw=1.1, label=f"{cc} 收盘")
    except FileNotFoundError:
        pass
    ax.set_ylabel("元/公斤")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.set_title("现货与期货：7月后回落，弱于季节常态", loc="left")
    for axx in axes:
        shade_seasons(axx, a, W.index[-1])
        for d, lab in CHART_EVENTS:
            d = pd.Timestamp(d)
            if d >= a:
                axx.axvline(d, color="#777777", lw=0.7, ls=":")
        axx.axvline(lo, color=C["stock"], lw=1, ls="--")
    ev = [(pd.Timestamp(d), lab) for d, lab in CHART_EVENTS if pd.Timestamp(d) >= a]
    for i, (d, lab) in enumerate(ev):
        axes[0].text(d, 0.02 if i % 2 == 0 else 0.6, " " + lab, transform=axes[0].get_xaxis_transform(),
                     fontsize=7.5, rotation=90, va="bottom", ha="right", color="#555555")
    title(fig, "本轮（2025—2026）：股价底部晚于现货，之后与现货、期货背离",
          "蓝绿虚线为股价超额收益底部；季节常态路径用2011—2025年（剔除2019—2020）春节后同周的中位数变化")
    source(fig, "新牧网（2026-10-12 为日度报价周均）、大商所 LH 合约、中证指数公司；本项目计算。", y=-0.02)
    fig.tight_layout()
    return save(fig, "i05_2026.png")


def chart_companies(CC):
    import matplotlib.pyplot as plt
    from plotstyle import C, save, source, title
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.8), gridspec_kw=dict(width_ratios=[1.1, 1]))
    ax = axes[0]
    cycs = ["2018—2019", "2021—2022", "2024—2024"]
    names = [n for _, n, _, _ in UNIVERSE if n in set(CC["name"])]
    ypos = {n: i for i, n in enumerate(names)}
    colors = {"2018—2019": C["fut4"], "2021—2022": C["stock"], "2024—2024": C["small"]}
    ax.axvspan(-60, 0, color="#eef4f6", lw=0, zorder=0)
    ax.axvline(0, color="#444444", lw=0.8)
    for j, cyc in enumerate(cycs):
        g = CC[(CC["cycle"] == cyc) & CC["lead_peak_w"].notna()]
        ax.plot(g["lead_peak_w"].clip(-60, 60), [ypos[n] + (j - 1) * 0.2 for n in g["name"]], "o",
                color=colors[cyc], ms=6, label=f"{cyc[:4]}轮")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels([("★" if n in ("牧原股份", "温氏股份") else "") + n for n in names])
    ax.invert_yaxis()
    ax.set_xlim(-60, 60)
    ax.set_xlabel("股价超额收益高点 − 猪价高点（周）")
    ax.set_title("各公司见顶时点", loc="left")
    ax.legend(loc="lower right")
    ax = axes[1]
    g = CC[CC["cycle"] == "2026—"].copy()
    sc = ax.scatter(g["debt_ratio"], g["abs_预期段(进行中)"], c=g["cost_2026"], cmap="viridis_r", s=60,
                    edgecolor="white", zorder=3)
    nudge = {"唐人神": (4, -10), "傲农生物": (-30, 5), "罗牛山": (4, 4), "正邦科技": (4, -10), "牧原股份": (-24, -4)}
    for _, r in g.iterrows():
        ax.annotate(r["name"].replace("股份", "").replace("集团", ""), (r["debt_ratio"], r["abs_预期段(进行中)"]),
                    fontsize=8, xytext=nudge.get(r["name"], (4, 3)), textcoords="offset points")
    ax.axhline(0, color="#444444", lw=0.6)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.0%}"))
    ax.set_xlabel("资产负债率（2026-03末）")
    ax.set_ylabel("2026-06-26 以来涨幅")
    cb = fig.colorbar(sc, ax=ax, fraction=0.04)
    cb.set_label("2026年完全成本（元/公斤，灰点为无数据）")
    ax.scatter(g.loc[g["cost_2026"].isna(), "debt_ratio"], g.loc[g["cost_2026"].isna(), "abs_预期段(进行中)"],
               color="#bbbbbb", s=60, zorder=4)
    rho = g[["abs_预期段(进行中)", "debt_ratio", "cost_2026"]].corr(method="spearman").iloc[0]
    ax.set_title(f"本轮反弹与负债、成本只弱相关（秩相关 {rho['debt_ratio']:.2f} / {rho['cost_2026']:.2f}）",
                 loc="left")
    title(fig, "公司差异：谁先见顶，谁先反弹", "★为龙头；左图超出±60周的值画在边界")
    source(fig, "后复权股价、定期报告资产负债表、主报告成本假设表（model_company_inputs）；本项目计算。", y=-0.03)
    fig.tight_layout()
    return save(fig, "i05_companies.png")


def write(df: pd.DataFrame, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / name, index=False, encoding="utf-8")


if __name__ == "__main__":
    W, hog, meta, px, R, D = build()
    tp = major_turns(hog.loc["2004-01-01":])
    tp["season"] = tp["date"].map(season)
    legs = hog_legs(tp)
    ct = cycle_table(W, legs)
    sdf, use = seasonal_norm(W["hog"], W["hog_src"])
    idx = W.index[W.index >= "2005-07-01"]
    launch_sets, robust = {}, []
    for col, k in (("ew_xs", 0.20), ("ew_xs", 0.15), ("ew_xs", 0.30), ("ew", 0.25), ("rs", 0.20)):
        L = launch_context(launches(W, col, k, tp), W, sdf, use)
        L["k"] = k
        launch_sets[(col, k)] = L
        for tag in ("trough", "confirm"):
            n = len(L)
            k_off = int(L[f"season_{tag}"].isin(["节后淡季", "夏季淡季"]).sum())
            k_sum = int((L[f"season_{tag}"] == "夏季淡季").sum())
            b = base_rates(idx)
            done = L[L["outcome"] != "未满52周"]
            robust.append(dict(series=col, k=k, by=tag, n=n, off_season=k_off, share_off=k_off / n,
                               base_off=float(b[["节后淡季", "夏季淡季"]].sum()),
                               p_off=binom_p(k_off, n, float(b[["节后淡季", "夏季淡季"]].sum())),
                               summer=k_sum, base_summer=float(b["夏季淡季"]),
                               p_summer=binom_p(k_sum, n, float(b["夏季淡季"])),
                               persist_off=int(((done[f"season_{tag}"] != "旺季") & (done["outcome"] == "持续")).sum()),
                               n_off_done=int((done[f"season_{tag}"] != "旺季").sum()),
                               persist_peak=int(((done[f"season_{tag}"] == "旺季") & (done["outcome"] == "持续")).sum()),
                               n_peak_done=int((done[f"season_{tag}"] == "旺季").sum())))
    b = base_rates(idx)
    for col in ("ew_xs", "hog"):
        for tag in ("trough", "start"):
            s = ct.loc[ct["series"] == col, f"season_{tag}"].dropna()
            n, k_off, k_sum, k_peak = len(s), int((s != "旺季").sum()), int((s == "夏季淡季").sum()), int((s == "旺季").sum())
            robust.append(dict(series=f"周期拐点:{col}", k=np.nan, by=tag, n=n, off_season=k_off, share_off=k_off / n,
                               base_off=float(b[["节后淡季", "夏季淡季"]].sum()),
                               p_off=binom_p(k_off, n, float(b[["节后淡季", "夏季淡季"]].sum())),
                               summer=k_sum, base_summer=float(b["夏季淡季"]), p_summer=binom_p(k_sum, n, float(b["夏季淡季"])),
                               peak_season=k_peak, p_peak_season=binom_p(k_peak, n, float(b["旺季"]))))
    L = launch_sets[("ew_xs", 0.20)]
    lows = seasonal_lows(W["hog"])
    M = monthly(W)
    xc = pd.concat([xcorr(M, "ew_xs"), xcorr(M, "ew")], ignore_index=True)
    sc = surprise_corr(W, sdf, use)
    E, REG, ex = event_studies(D, W)
    CC, CS = company_cycles(W, px, legs, ct)
    RT = realised_turns(W, tp)
    F = facts_2026(W, sdf, use)

    write(tp, "ts_hog_turns.csv")
    keep = ["cycle", "series", "trough", "zone_first", "zone_last", "start", "start_alt", "accel", "peak",
            "peak_zone_first", "peak_zone_last", "rise", "lead_trough_w", "lead_zone_last_w", "lead_start_w",
            "lead_start_alt_w", "lead_accel_w", "lead_peak_w", "hog_rise_at_trough", "hog_rise_at_start",
            "hog_amp_at_start", "season_trough", "season_start", "n_members", "window_trough", "window_peak"]
    write(ct[[c for c in keep if c in ct]], "ts_cycle_milestones.csv")
    write(pd.concat(launch_sets.values(), ignore_index=True), "ts_launches.csv")
    write(pd.DataFrame(robust), "ts_launch_season_tests.csv")
    write(season_summary(L, idx), "ts_launch_season_summary.csv")
    write(lows, "ts_seasonal_lows.csv")
    x = sdf.loc["2011-01-01":]
    x = x[(x["year"] >= 2011) & ~x["year"].isin([2019, 2020]) & (x["year"] < 2026)].copy()
    x["dev"] = np.log(W["hog"].reindex(x.index)) - np.log(W["hog"].reindex(x.index)).groupby(x["year"]).transform("first")
    write(x[x["lw"] <= 50].groupby("lw")["dev"].quantile([0.25, 0.5, 0.75]).unstack().reset_index()
          .rename(columns={0.25: "q25_log", 0.5: "median_log", 0.75: "q75_log"}), "ts_seasonal_profile.csv")
    write(xc, "ts_xcorr.csv")
    write(sc, "ts_surprise_corr.csv")
    write(E.drop(columns=[c for c in ("trade_day",) if c in E]), "ts_events.csv")
    write(REG, "ts_event_regressions.csv")
    write(CC, "ts_company_cycles.csv")
    write(CS, "ts_company_phase_summary.csv")
    write(RT, "ts_realised_price_turns.csv")
    Mo = M.drop(columns=["hog"])  # spot after 2015 is 新牧网 data, kept local
    Mo.index = Mo.index.strftime("%Y-%m").rename("month")
    write(Mo.reset_index().round(4), "ts_monthly.csv")
    def fmt(v):
        if isinstance(v, tuple):
            return " ".join(fmt(x) for x in v)
        if isinstance(v, pd.Timestamp):
            return f"{v:%Y-%m-%d}"
        if isinstance(v, float):
            return f"{v:.4f}"
        return str(v)
    write(pd.DataFrame([dict(key=k, value=fmt(v)) for k, v in {**F, **meta}.items()]), "ts_facts.csv")

    for f in (chart_cycles(W, ct), chart_leadlag(ct), chart_seasons(W, sdf, use, L, lows, idx), chart_xcorr(xc),
              chart_2026(W, sdf, use, E), chart_companies(CC)):
        print("chart", f.name)
    print("outputs ->", OUT)
    if "-v" in sys.argv:
        pd.set_option("display.width", 250)
        cols = ["trough", "confirm", "season_trough", "season_confirm", "outcome", "ret52", "wk_vs_hog_trough",
                "hog_vs_52w_low_confirm", "hog_chg13_confirm", "hog_yoy_confirm", "hog_surprise8_confirm"]
        print(L[cols].round(3).to_string())
        print(pd.DataFrame(robust).round(3).to_string())
        print(sc.round(3).to_string())
        best = xc.reset_index(drop=True)
        print(best.loc[best.groupby(["series", "era", "horizon_m"])["corr"].idxmax()].round(2).to_string())
        print(REG.round(4).to_string())
        print({k: v for k, v in F.items() if "since" in k or "surprise" in k})
