"""Double tops (2019H1 vs 2020), market cap / profit at cycle peaks, and the 2026-06-25 rebound panel."""
import numpy as np
import pandas as pd

from common import PROC

sd = pd.read_csv(PROC / "stock_daily.csv", dtype={"code": str}, parse_dates=["date"])
fin = pd.read_csv(PROC / "fin_quarterly.csv", dtype={"code": str}, parse_dates=["report_date"])
sc = pd.read_csv(PROC / "screen_snapshot.csv", dtype={"code": str})
inp = pd.read_csv(PROC / "model_company_inputs.csv", dtype={"code": str})
res = pd.read_csv(PROC / "model_results.csv", dtype={"code": str})


def adj(code, f="close"):
    s = sd[sd["code"] == code].set_index("date")
    for c in (f"{f}_tx_hfq", f"{f}_hfq"):
        if c in s and s[c].notna().any():
            return s[c].dropna()
    return pd.Series(dtype=float)


def mcap_series(code):
    """Raw close x share capital of the latest balance sheet on or before each day (亿元)."""
    s = sd[sd["code"] == code][["date", "close_raw", "close_tx_raw"]].copy()
    s["close"] = s["close_raw"].fillna(s["close_tx_raw"])
    s = s.dropna(subset=["close"]).sort_values("date")
    f = fin[(fin["code"] == code)].dropna(subset=["SHARE_CAPITAL"]).sort_values("report_date")[["report_date", "SHARE_CAPITAL"]]
    if s.empty or f.empty:
        return pd.Series(dtype=float)
    m = pd.merge_asof(s, f, left_on="date", right_on="report_date")
    return (m.set_index("date")["close"] * m.set_index("date")["SHARE_CAPITAL"] / 1e8).dropna()


def annual_np(code, y):
    f = fin[(fin["code"] == code) & (fin["report_date"] == f"{y}-12-31")]
    v = f["PARENT_NETPROFIT"].dropna()
    return float(v.iloc[0]) / 1e8 if len(v) else np.nan


# ------------------------------------------------------------------ double tops
DT = {"002714": "牧原", "300498": "温氏", "002157": "正邦", "002124": "天邦", "000876": "新希望", "002567": "唐人神",
      "600975": "新五丰", "603363": "傲农", "002548": "金新农", "002385": "大北农", "002100": "天康", "000735": "罗牛山",
      "000048": "京基智农", "002840": "华统"}
rows = []
for code, nm in DT.items():
    c, h = adj(code, "close"), adj(code, "high")
    c19, c20, c21 = c["2019-01-01":"2019-06-30"], c["2020-01-01":"2020-12-31"], c["2021-01-01":"2021-06-30"]
    h19, h20 = h["2019-01-01":"2019-06-30"], h["2020-01-01":"2020-12-31"]
    if c19.empty or c20.empty:
        continue
    d19, d20 = c19.idxmax(), c20.idxmax()
    rows.append(dict(name=nm, max19H1_date=d19.date(), max20_date=d20.date(),
                     close_ratio_20_vs_19H1=c20.max() / c19.max(), intraday_ratio_20_vs_19H1=h20.max() / h19.max(),
                     max21H1_vs_19H1=c21.max() / c19.max() if len(c21) else np.nan,
                     trough_between=c[d19:d20].min() / c19.max() - 1))
pd.DataFrame(rows).to_csv(PROC / "hist_double_top.csv", index=False)

# ------------------------------------------------------------------ market cap / profit at cycle peaks
PE = {"002714": "牧原", "300498": "温氏", "002157": "正邦", "002124": "天邦", "000876": "新希望", "002567": "唐人神",
      "002100": "天康", "002385": "大北农", "603363": "傲农", "002548": "金新农", "000048": "京基", "600975": "新五丰",
      "605296": "神农", "603477": "巨星", "001201": "东瑞", "002840": "华统"}
CYCLES = [("ASF", "2018-08-01", "2021-12-31", [2019, 2020, 2021]),
          ("2022", "2022-01-01", "2023-06-30", [2022]),
          ("2024", "2024-01-01", "2025-06-30", [2024])]
rows = []
for code, nm in PE.items():
    mc = mcap_series(code)
    for cyc, a, b, yrs in CYCLES:
        w = mc[a:b]
        if w.empty:
            continue
        nps = {y: annual_np(code, y) for y in yrs}
        best = max(nps.values()) if any(pd.notna(v) for v in nps.values()) else np.nan
        r = dict(cycle=cyc, name=nm, peak_date=w.idxmax().date(), peak_mc=round(w.max(), 1), peak_year_np=round(best, 2),
                 pe_on_peak_year_np=round(w.max() / best, 1) if pd.notna(best) and best > 0 else np.nan)
        r.update({f"np{y}": round(v, 2) for y, v in nps.items()})
        rows.append(r)
hp = pd.DataFrame(rows)
hp.to_csv(PROC / "hist_peak_pe.csv", index=False)
print("peak P/E medians:", hp.groupby("cycle")["pe_on_peak_year_np"].median().round(1).to_dict())

# ------------------------------------------------------------------ rebound since 2026-06-25
START, END = "2026-06-25", "2026-10-08"
base = res[(res["path"] == "P1 全年持平") & (res["case"] == "base")][["code", "earnings_yield"]]
cur = sc[~sc["pool"].str.startswith("剔除")][["code", "name", "mcap_yi", "ev_yi", "debt_ratio", "cash_to_st_debt", "cost_latest_kg"]]
cur = cur.merge(inp[["code", "V_base"]], on="code", how="left").merge(base, on="code", how="left")
cur["mcap_per_head"] = cur["mcap_yi"] * 1e8 / (cur["V_base"] * 1e4)
cur["ev_per_head"] = cur["ev_yi"] * 1e8 / (cur["V_base"] * 1e4)


def ret_between(code, a, b):
    c = adj(code)
    ca, cb = c[:a], c[:b]
    return cb.iloc[-1] / ca.iloc[-1] - 1 if len(ca) and len(cb) else np.nan


def dd_from(code, a):
    c = adj(code)[a:END]
    return c.iloc[-1] / c.max() - 1 if len(c) else np.nan


cur["market"] = "A"
cur = pd.concat([cur, pd.DataFrame(dict(code=["02419", "01610"], name=["德康农牧", "中粮家佳康"], market="H"))], ignore_index=True)
cur["ret"] = [ret_between(c, START, END) for c in cur["code"]]
cur["ret_ytd"] = [ret_between(c, "2025-12-31", END) for c in cur["code"]]
cur["dd_from_2024_high"] = [dd_from(c, "2024-01-01") for c in cur["code"]]
cur.to_csv(PROC / "current_rebound_panel.csv", index=False)

out = []
a_only = cur[cur["market"] == "A"]
for x in ["debt_ratio", "cost_latest_kg", "mcap_yi", "earnings_yield", "ev_per_head", "cash_to_st_debt"]:
    d = a_only[["ret", x]].dropna()
    out.append(dict(x=x, n=len(d), spearman_rho=round(d["ret"].rank().corr(d[x].rank()), 2)))
cr = pd.DataFrame(out)
cr.to_csv(PROC / "current_rebound_correlations.csv", index=False)
print(cur[["name", "ret", "ret_ytd", "dd_from_2024_high"]].round(3).to_string())
print(cr.to_string())
