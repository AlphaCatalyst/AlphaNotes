"""Futures-side analysis: contract-level extremes, listing-day effects, liquidity by tenor,
main-continuous roll gaps, forecast error versus final prices, and term-structure snapshots.

All prices yuan/tonne in source; *_kg columns are yuan/kg. Trade date and delivery month are kept
separate everywhere: a contract named LH2109 trades from 2021-01-08 and delivers in 2021-09.
"""
import numpy as np
import pandas as pd

from common import PROC

f = pd.read_csv(PROC / "futures_lh_daily.csv")
f = f[f["trade_date"] <= "2026-10-08"]
f["trade_date"] = pd.to_datetime(f["trade_date"])
lh = f[f["contract"] != "LH0"].copy()
main = f[f["contract"] == "LH0"].set_index("trade_date").sort_index()

# ---------------------------------------------------------------- per-contract stats
rows = []
for c, g in lh.groupby("contract"):
    g = g.sort_values("trade_date")
    first = g.iloc[0]
    after = g.iloc[1:]
    last = g.iloc[-1]
    deliv = pd.Timestamp(f"20{c[2:4]}-{c[4:6]}-01")
    rows.append(dict(
        contract=c, delivery_month=deliv.strftime("%Y-%m"), list_date=first.trade_date.date(),
        last_date=last.trade_date.date(), n_days=len(g),
        first_open=first.open, first_high=first.high, first_close=first.close, first_settle=first.settle,
        max_close=g.close.max(), max_close_date=g.loc[g.close.idxmax(), "trade_date"].date(),
        max_settle=g.settle.max(), max_settle_date=g.loc[g.settle.idxmax(), "trade_date"].date(),
        max_high=g.high.max(), max_high_date=g.loc[g.high.idxmax(), "trade_date"].date(),
        max_close_ex1=after.close.max() if len(after) else np.nan,
        max_close_ex1_date=after.loc[after.close.idxmax(), "trade_date"].date() if len(after) else None,
        max_high_ex1=after.high.max() if len(after) else np.nan,
        max_high_ex1_date=after.loc[after.high.idxmax(), "trade_date"].date() if len(after) else None,
        min_close=g.close.min(), min_close_date=g.loc[g.close.idxmin(), "trade_date"].date(),
        last_close=last.close, last_settle=last.settle,
        first_day_vol=first.volume, first_day_oi=first.open_interest,
        peak_oi=g.open_interest.max(), peak_oi_date=g.loc[g.open_interest.idxmax(), "trade_date"].date(),
    ))
cs = pd.DataFrame(rows).sort_values("contract")
cs.to_csv(PROC / "fut_contract_stats.csv", index=False)

# ---------------------------------------------------------------- liquidity by months to delivery
lh["deliv"] = pd.to_datetime(lh["delivery_month"] + "-01")
lh["m2d"] = ((lh["deliv"].dt.year - lh["trade_date"].dt.year) * 12
             + (lh["deliv"].dt.month - lh["trade_date"].dt.month))
liq = lh[lh["contract"] >= "LH2203"].groupby("m2d").agg(
    median_volume=("volume", "median"), median_oi=("open_interest", "median"), n=("volume", "size"))
liq.to_csv(PROC / "fut_liquidity_by_tenor.csv")

# ---------------------------------------------------------------- main-continuous roll detection
# map each LH0 bar to the contract with identical close & volume on that date
key = lh.set_index(["trade_date", "close", "volume"])["contract"]
m = main.reset_index()[["trade_date", "open", "close", "settle", "volume", "open_interest"]]
match = []
for _, r in m.iterrows():
    cand = lh[(lh.trade_date == r.trade_date) & (np.isclose(lh.close, r.close)) & (np.isclose(lh.volume, r.volume))]
    if len(cand) != 1:
        cand = lh[(lh.trade_date == r.trade_date) & (np.isclose(lh.close, r.close))]
    match.append(cand.contract.iloc[0] if len(cand) == 1 else None)
m["mapped_contract"] = match
m["prev_contract"] = m["mapped_contract"].shift(1)
m["is_roll"] = (m["mapped_contract"] != m["prev_contract"]) & m["prev_contract"].notna() & m["mapped_contract"].notna()
# roll gap = new contract's previous close - old contract's previous close (price jump caused by switching)
gaps = []
px = lh.set_index(["contract", "trade_date"])["close"]
dates = list(m["trade_date"])
for i, r in m[m["is_roll"]].iterrows():
    prev_day = dates[i - 1]
    try:
        old = px[(r.prev_contract, prev_day)]
        new = px[(r.mapped_contract, prev_day)]
        gaps.append(dict(roll_date=r.trade_date.date(), from_c=r.prev_contract, to_c=r.mapped_contract,
                         old_prev_close=old, new_prev_close=new, gap=new - old))
    except KeyError:
        gaps.append(dict(roll_date=r.trade_date.date(), from_c=r.prev_contract, to_c=r.mapped_contract))
rg = pd.DataFrame(gaps)
rg.to_csv(PROC / "fut_main_roll_gaps.csv", index=False)
m.to_csv(PROC / "fut_main_mapped.csv", index=False)

# ---------------------------------------------------------------- forecast error vs final
fe = []
for c, g in lh.groupby("contract"):
    g = g.sort_values("trade_date").set_index("trade_date")
    if g.index[-1] < pd.Timestamp(f"20{c[2:4]}-{c[4:6]}-01"):
        continue  # not yet in delivery month -> no final
    s_ok = g["settle"].where(g["settle"] > 0)
    final = s_ok.dropna().iloc[-1] if s_ok.notna().any() else g["close"].iloc[-1]
    for k in (1, 3, 6, 9, 12):
        t = g.index[-1] - pd.DateOffset(months=k)
        h = g[g.index <= t]
        if len(h) == 0:
            continue
        p_then = h["settle"].iloc[-1] if h["settle"].iloc[-1] > 0 else h["close"].iloc[-1]
        fe.append(dict(contract=c, months_before=k, date=h.index[-1].date(), price=p_then,
                       final_settle=final, err_pct=p_then / final - 1))
fe = pd.DataFrame(fe)
fe.to_csv(PROC / "fut_forecast_error.csv", index=False)
summ = fe.groupby("months_before")["err_pct"].agg(
    n="size", mean="mean", mae=lambda x: x.abs().mean(), max="max", min="min")
summ.to_csv(PROC / "fut_forecast_error_summary.csv")


# ---------------------------------------------------------------- term-structure snapshots
def curve(d):
    d = pd.Timestamp(d)
    g = lh[lh.trade_date == d][["contract", "delivery_month", "close", "settle", "high", "volume", "open_interest"]]
    return g.sort_values("contract").assign(trade_date=d.date())


snaps = pd.concat([curve(d) for d in ["2021-02-19", "2021-02-22", "2022-07-04", "2022-10-17", "2024-05-20",
                                      "2024-08-19", "2026-09-30", "2026-10-08"]])
snaps.to_csv(PROC / "fut_curve_snapshots.csv", index=False)

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
print(cs[["contract", "list_date", "first_close", "max_close", "max_close_date", "max_close_ex1", "max_close_ex1_date",
          "max_settle_date", "max_high", "max_high_date", "min_close", "min_close_date", "last_settle"]].to_string(index=False))
print(liq.head(14))
print(rg.head(40).to_string(index=False))
print(summ)
print(snaps[snaps.trade_date.astype(str) == "2026-10-08"].to_string(index=False))
