"""Stock-side history of the ASF super-cycle (2017-2022).

Adjustment: Tencent backward-adjusted (hfq) bars for every A-share (single source, ratio method),
East Money hfq used only to cross-check peak dates. Returns are adjusted price changes, not total
return with reinvested dividends.

Outputs (data/processed):
  hist_halfyear_returns.csv   mechanical half-year windows (no hand-picked start dates)
  hist_event_returns.csv      windows anchored on industry events (documented in EVENTS)
  hist_peaks.csv              cycle peaks by close and by intraday high, drawdowns, cross-check
  pig_ew_index.csv            equal-weight index of the sample (rebalanced daily, hfq)
"""
import numpy as np
import pandas as pd

from common import PROC

sd = pd.read_csv(PROC / "stock_daily.csv", dtype={"code": str})
sd = sd[sd["date"] <= "2026-10-08"]  # drop today's unfinished bar
idx = pd.read_csv(PROC / "index_daily.csv")
csi = idx[idx["index"] == "sh000300"].set_index("date")["close"]
fin = pd.read_csv(PROC / "fin_quarterly.csv", dtype={"code": str})
uni = pd.read_csv(PROC / "universe.csv", dtype=str)

HIST = ["002714", "300498", "002157", "002124", "000876", "002477", "002567", "600975", "603363",
        "002548", "002385", "002100", "000735", "000048", "000702", "002840", "002311", "000895",
        "002726", "603609"]
CHAIN = {"002311", "000895", "002726", "603609", "000702"}


def series(code, col):
    s = sd[sd["code"] == code].set_index("date")
    return s[col].dropna() if col in s else pd.Series(dtype=float)


def px(code):
    """Adjusted close/high/low from Tencent hfq, fallback East Money hfq."""
    out = {}
    for f in ("close", "high", "low"):
        s = series(code, f"{f}_tx_hfq")
        if s.empty:
            s = series(code, f"{f}_hfq")
        out[f] = s
    return pd.DataFrame(out)


def raw_close(code):
    s = series(code, "close_raw")
    return s if not s.empty else series(code, "close_tx_raw")


def shares_at(code, date):
    """Share capital (shares, from balance sheet SHARE_CAPITAL at 1 yuan par) at latest report <= date."""
    f = fin[(fin["code"] == code) & (fin["report_date"] <= date)].sort_values("report_date")
    f = f.dropna(subset=["SHARE_CAPITAL"])
    return float(f["SHARE_CAPITAL"].iloc[-1]) if len(f) else np.nan


def val_on_or_before(s, d):
    s = s[s.index <= d]
    return (s.index[-1], float(s.iloc[-1])) if len(s) else (None, np.nan)


name = dict(zip(uni["code"], uni["name"]))

# ---------------------------------------------------------------- half-year windows
HY = [("2017-12-29", "2018-06-29", "2018H1"), ("2018-06-29", "2018-12-28", "2018H2"),
      ("2018-12-28", "2019-06-28", "2019H1"), ("2019-06-28", "2019-12-31", "2019H2"),
      ("2019-12-31", "2020-06-30", "2020H1"), ("2020-06-30", "2020-12-31", "2020H2"),
      ("2020-12-31", "2021-06-30", "2021H1"), ("2021-06-30", "2021-12-31", "2021H2"),
      ("2021-12-31", "2022-06-30", "2022H1"), ("2022-06-30", "2022-12-30", "2022H2")]

# ---------------------------------------------------------------- event windows
EVENTS = [
    ("2018-08-02", "2018-12-28", "A 疫情冲击", "8月3日首例非瘟确诊前一日收盘→2018年末"),
    ("2018-12-28", "2019-04-30", "B 交易产能缺口", "12月母猪监测降幅公布(1/15)、4/17官方预计下半年猪肉涨幅超70%"),
    ("2019-04-30", "2019-11-08", "C 现货兑现冲顶", "现货自5月起上涨至11月初主峰(农信11/4周度标签)"),
    ("2019-11-08", "2020-08-31", "D 高价利润与复产", "现货高位反复；10月母猪止跌回升于11/22确认；2020年8月现货次高点"),
    ("2020-08-31", "2021-02-26", "E 扩张兑现分化", "母猪恢复至常年九成以上(12/18官方)；2021/1/8期货上市"),
    ("2021-02-26", "2021-10-08", "F 供给恢复下跌", "6月末全国母猪4564万头；10月上旬现货低位"),
    ("2021-10-08", "2022-04-29", "G 二次探底", "2022年春现货再度低迷"),
]


def window_ret(p, a, b):
    da, va = val_on_or_before(p, a)
    db, vb = val_on_or_before(p, b)
    if da is None or db is None:
        return np.nan
    # require the stock to have traded within 30 days before window start, and at least once inside the window
    if (pd.Timestamp(a) - pd.Timestamp(da)).days > 30 or db <= a:
        return np.nan
    return vb / va - 1


rows_hy, rows_ev, rows_pk = [], [], []
for code in HIST:
    p = px(code)
    if p.empty:
        continue
    c = p["close"]
    for a, b, lab in HY:
        r = window_ret(c, a, b)
        m = window_ret(csi, a, b)
        rows_hy.append(dict(code=code, name=name.get(code), window=lab, start=a, end=b, ret=r,
                            csi300=m, excess=r - m if pd.notna(r) else np.nan))
    for a, b, lab, why in EVENTS:
        r = window_ret(c, a, b)
        m = window_ret(csi, a, b)
        rc = raw_close(code)
        da, pa = val_on_or_before(rc, a)
        mcap = pa * shares_at(code, a) / 1e8 if da else np.nan
        rows_ev.append(dict(code=code, name=name.get(code), window=lab, start=a, end=b, basis=why,
                            ret=r, csi300=m, excess=r - m if pd.notna(r) else np.nan,
                            mcap_start_yi=mcap))
    # cycle peak inside 2018-08-01 .. 2021-12-31 (main window) by close and by intraday high
    w = p[(p.index >= "2018-08-01") & (p.index <= "2021-12-31")]
    if w.empty:
        continue
    d_close = w["close"].idxmax()
    d_high = w["high"].idxmax()
    pre = p[(p.index >= "2018-01-01") & (p.index <= d_close)]["close"]
    trough_before = pre.idxmin()
    post = p[(p.index > d_close) & (p.index <= "2022-04-30")]["close"]
    dd = post.min() / w["close"].max() - 1 if len(post) else np.nan
    # East Money hfq cross-check
    em = series(code, "close_hfq")
    em_w = em[(em.index >= "2018-08-01") & (em.index <= "2021-12-31")]
    em_peak = em_w.idxmax() if len(em_w) else None
    rc = raw_close(code)
    _, peak_raw = val_on_or_before(rc, d_close)
    rows_pk.append(dict(
        code=code, name=name.get(code), chain=code in CHAIN,
        peak_close_date=d_close, peak_high_date=d_high, same_day=d_close == d_high,
        trough_before_date=trough_before,
        rise_trough_to_peak=w["close"].max() / pre.min() - 1,
        drawdown_to_2022_04=dd, post_low_date=post.idxmin() if len(post) else None,
        peak_mcap_yi=peak_raw * shares_at(code, d_close) / 1e8,
        em_peak_close_date=em_peak, em_agrees=em_peak == d_close if em_peak else None,
    ))

hy = pd.DataFrame(rows_hy)
ev = pd.DataFrame(rows_ev)
pk = pd.DataFrame(rows_pk).sort_values("peak_close_date")
hy.to_csv(PROC / "hist_halfyear_returns.csv", index=False)
ev.to_csv(PROC / "hist_event_returns.csv", index=False)
pk.to_csv(PROC / "hist_peaks.csv", index=False)

# ---------------------------------------------------------------- equal-weight index
core = [c for c in HIST if c not in CHAIN]
rets = {}
for code in core:
    c = px(code)["close"]
    rets[code] = c.pct_change()
R = pd.DataFrame(rets).sort_index()
R = R[R.index >= "2017-01-01"]
ew = (1 + R.mean(axis=1, skipna=True).fillna(0)).cumprod()
ew.name = "pig_ew"
ew.to_frame().to_csv(PROC / "pig_ew_index.csv")

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)
print(pk.to_string(index=False))
print(ev.pivot_table(index="name", columns="window", values="ret").round(3).to_string())
