"""Turning-point comparison between stocks, spot and *specific* futures contracts (2021-2026).

For each cycle window we locate the extreme (peak or trough) of:
  - stocks: Muyuan, Wens (close and intraday) and an equal-weight pig-stock index (close)
  - spot: nxin national weekly transaction price (week label = Monday)
  - every LH contract with >= 20 trading days inside the window (close / settle / intraday)
  - LH0 main-continuous (close) - shown only to illustrate roll distortions
Lags are reported in calendar days and in trading days (A-share calendar) relative to the stock.
No fixed lead is assumed; windows are wide and documented.
"""
import numpy as np
import pandas as pd

from common import PROC

sd = pd.read_csv(PROC / "stock_daily.csv", dtype={"code": str})
sd = sd[sd["date"] <= "2026-10-08"]
fut = pd.read_csv(PROC / "futures_lh_daily.csv")
fut = fut[fut["trade_date"] <= "2026-10-08"]
spot = pd.read_csv(PROC / "nxin_price_wide.csv", index_col=0)["全国"].dropna()
spot.index = pd.to_datetime(spot.index)

CORE = ["002714", "300498", "002157", "002124", "000876", "002567", "600975", "603363", "002548",
        "002385", "002100", "000048", "002840", "603477", "001201", "605296", "000735", "603717"]


def adj(code, f="close"):
    s = sd[sd.code == code].set_index("date")
    col = f"{f}_tx_hfq" if s[f"{f}_tx_hfq"].notna().sum() > 0 else f"{f}_hfq"
    out = s[col].dropna()
    out.index = pd.to_datetime(out.index)
    return out


ew_rets = pd.DataFrame({c: adj(c).pct_change() for c in CORE}).sort_index()
ew = (1 + ew_rets.mean(axis=1, skipna=True).fillna(0)).cumprod()
cal = ew.index  # A-share trading calendar

WINDOWS = [
    ("2021 高点", "peak", "2021-01-04", "2021-06-30"),
    ("2021-22 低点", "trough", "2021-06-01", "2022-04-29"),
    ("2022 高点", "peak", "2022-05-04", "2022-12-30"),
    ("2023-24 低点", "trough", "2023-01-03", "2024-03-29"),
    ("2024 高点", "peak", "2024-03-01", "2024-12-31"),
    ("2025-26 低点", "trough", "2025-06-03", "2026-10-08"),
]


def ext(s, a, b, kind):
    w = s[(s.index >= a) & (s.index <= b)].dropna()
    if w.empty:
        return None, np.nan
    d = w.idxmax() if kind == "peak" else w.idxmin()
    return d, float(w.loc[d])


def tdays(d0, d1):
    if d0 is None or d1 is None:
        return np.nan
    i0 = cal.searchsorted(d0)
    i1 = cal.searchsorted(d1)
    return int(i1 - i0)


rows = []
for lab, kind, a, b in WINDOWS:
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    ref_d, ref_v = ext(adj("002714"), a, b, kind)
    series = [("股票", "牧原 收盘", adj("002714")), ("股票", "牧原 盘中", adj("002714", "high" if kind == "peak" else "low")),
              ("股票", "温氏 收盘", adj("300498")), ("股票", "猪企等权指数 收盘", ew),
              ("现货", "农信全国周度成交价", spot)]
    for cat, nm, s in series:
        d, v = ext(s, a, b, kind)
        rows.append(dict(window=lab, kind=kind, category=cat, series=nm, date=d, value=v,
                         cal_days_vs_muyuan_close=(d - ref_d).days if d is not None else np.nan,
                         tdays_vs_muyuan_close=tdays(ref_d, d)))
    fw = fut[(pd.to_datetime(fut.trade_date) >= a) & (pd.to_datetime(fut.trade_date) <= b)]
    for c, g in fw.groupby("contract"):
        if c != "LH0" and len(g) < 20:
            continue
        g = g.set_index(pd.to_datetime(g.trade_date)).sort_index()
        first_day = pd.to_datetime(fut[fut.contract == c].trade_date.min())
        for basis, col in [("收盘", "close"), ("结算", "settle"),
                           ("盘中", "high" if kind == "peak" else "low")]:
            if c == "LH0" and basis != "收盘":
                continue
            s = g[col].where(g[col] > 0)
            d, v = ext(s, a, b, kind)
            rows.append(dict(window=lab, kind=kind, category="期货" if c != "LH0" else "主连(仅示意)",
                             series=f"{c} {basis}", contract=c, basis=basis,
                             delivery=None if c == "LH0" else f"20{c[2:4]}-{c[4:6]}",
                             listed_in_window=first_day >= a, is_first_day=d == first_day if d is not None else None,
                             date=d, value=v,
                             cal_days_vs_muyuan_close=(d - ref_d).days if d is not None else np.nan,
                             tdays_vs_muyuan_close=tdays(ref_d, d),
                             n_days_in_window=len(g)))

out = pd.DataFrame(rows)
out["date"] = pd.to_datetime(out["date"]).dt.date
out.to_csv(PROC / "leadlag_turning_points.csv", index=False)
ew.rename("pig_ew").to_csv(PROC / "pig_ew_index_2017_2026.csv")
pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 400)
for lab, g in out.groupby("window", sort=False):
    print("\n==", lab)
    gg = g[(g.category != "期货") | (g.basis == "收盘")]
    print(gg[["category", "series", "date", "value", "cal_days_vs_muyuan_close", "tdays_vs_muyuan_close"]].to_string(index=False))
