"""Current screen of listed hog producers (snapshot: 2026-10-08 close, balance sheets at 2026-06-30).

Market cap = raw close x share capital at 2026-06-30, with two corrections that happened later or
sit outside the A-share line: Muyuan's H shares (priced in HKD) and New Hope's 2026-08 placement.
Interest-bearing debt = short loans + current portion of non-current liabilities + long loans +
bonds + lease liabilities (+ Zhengbang's restructuring debt booked in long-term payables).
Manual inputs (sows, costs, targets, convertible bonds) are in research/screen_inputs_manual.csv with URLs.
"""
import numpy as np
import pandas as pd

from common import PROC, ROOT

SNAP = "2026-10-08"
sd = pd.read_csv(PROC / "stock_daily.csv", dtype={"code": str})
fin = pd.read_csv(PROC / "fin_quarterly.csv", dtype={"code": str})
man = pd.read_csv(ROOT / "research/screen_inputs_manual.csv", dtype={"code": str})
nx = pd.read_csv(PROC / "nxin_price_wide.csv")

# H-share leg and FX (East Money quote API, previous close = 2026-10-08 close)
MUYUAN_H_SHARES, MUYUAN_H_CLOSE_HKD, HKDCNY = 310_223_100, 36.16, 0.8585
MUYUAN_A_SHARES = 5_462_773_044
NEWHOPE_PLACEMENT_SHARES = round(2_600_000_000 / 5.66)  # 26亿元 @5.66元 (approximate share count)
ZHENGBANG_RESTRUCT_DEBT = 21.57e8

# 2026 year-to-date output (company briefs, verified by subagents; 万头) and latest commodity price (元/kg)
YTD = {  # code: (heads, months, scope, latest price, price month)
    "002714": (5230.7, 8, "商品猪", 10.30, "2026-08"),
    "300498": (2651.17, 9, "肉猪（毛猪+鲜品）", 10.75, "2026-09"),
    "000876": (953.81, 8, "商品猪", 10.46, "2026-08"),
    "002100": (265.55, 8, "生猪合计（6月起含羌都）", 9.61, "2026-08"),
    "001201": (113.09, 8, "生猪合计（含猪苗）", 12.16, "2026-08"),
    "000048": (155.80, 9, "商品肥猪", 11.06, "2026-09"),
    "605296": (236.13, 8, "商品猪（含内供屠宰）", 10.62, "2026-08"),
    "603477": (320.19, 9, "商品肥猪", 11.05, "2026-09"),
    "002567": (253.55, 8, "商品猪", np.nan, None),
    "002385": (263.91, 8, "商品肥猪", 10.95, "2026-08"),
    "002840": (188.35, 8, "生猪合计（含种猪仔猪）", 10.74, "2026-08"),
    "600975": (207.48, 8, "商品猪", 10.35, "2026-08"),
    "603363": (170.45, 9, "生猪合计", np.nan, None),
    "002124": (324.81, 8, "商品肥猪（推算=总数-仔猪）", 10.14, "2026-08"),
    "002548": (53.44, 8, "商品猪（推算）", 11.64, "2026-08"),
    "002157": (726.76, 8, "生猪合计", 11.14, "2026-08"),
    "603717": (27.93, 8, "商品猪（推算）", np.nan, None),
    "000735": (59.78, 8, "生猪合计", np.nan, None),
}

nx["date"] = pd.to_datetime(nx["week_label"])
nat_month = nx.groupby(nx["date"].dt.strftime("%Y-%m"))["全国"].mean()
south_month = nx.groupby(nx["date"].dt.strftime("%Y-%m"))["华南"].mean()


def close_on(code, d=SNAP):
    s = sd[(sd["code"] == code) & (sd["date"] <= d)].sort_values("date")
    return float(s["close_raw"].iloc[-1]), s["date"].iloc[-1]


def bs(code, d="2026-06-30"):
    f = fin[(fin["code"] == code) & (fin["report_date"] == d)]
    return f.iloc[0] if len(f) else None


rows = []
for _, m in man.iterrows():
    code = m["code"]
    b = bs(code)
    px, pxd = close_on(code)
    shares = float(b["SHARE_CAPITAL"])
    note = []
    if code == "002714":
        mc = (MUYUAN_A_SHARES * px + MUYUAN_H_SHARES * MUYUAN_H_CLOSE_HKD * HKDCNY) / 1e8
        note.append("A股×A价+H股×H价×汇率")
    else:
        if code == "000876":
            shares += NEWHOPE_PLACEMENT_SHARES
            note.append("含2026-08定增新股（约4.59亿股）")
        mc = shares * px / 1e8
    g = lambda k: float(b[k]) if pd.notna(b[k]) else 0.0
    debt = sum(g(k) for k in ("SHORT_LOAN", "NONCURRENT_LIAB_1YEAR", "LONG_LOAN", "BOND_PAYABLE", "LEASE_LIAB"))
    if code == "002157":
        debt += ZHENGBANG_RESTRUCT_DEBT
        note.append("有息负债含重整留债21.57亿（长期应付款）")
    cash = g("MONETARYFUNDS")
    h1 = fin[(fin["code"] == code) & (fin["report_date"] == "2026-06-30")]
    ocf, capex = g("NETCASH_OPERATE"), g("CONSTRUCT_LONG_ASSET")
    st_debt = g("SHORT_LOAN") + g("NONCURRENT_LIAB_1YEAR")
    y = YTD.get(code)
    ytd_heads, ytd_months, ytd_scope, last_px, px_month = y if y else (np.nan, np.nan, None, np.nan, None)
    run_rate = ytd_heads / ytd_months * 12 if y else np.nan
    nat = nat_month.get(px_month, np.nan) if px_month else np.nan
    rows.append(dict(
        code=code, name=m["name"], pool=m["pool"], close=px, close_date=pxd, mcap_yi=mc,
        cash_yi=cash / 1e8, ib_debt_yi=debt / 1e8, net_debt_yi=(debt - cash) / 1e8, ev_yi=mc + (debt - cash) / 1e8,
        minority_equity_yi=g("MINORITY_EQUITY") / 1e8, parent_equity_yi=g("TOTAL_PARENT_EQUITY") / 1e8,
        debt_ratio=g("TOTAL_LIABILITIES") / g("TOTAL_ASSETS"), cash_to_st_debt=cash / st_debt if st_debt else np.nan,
        st_debt_yi=st_debt / 1e8, lease_liab_yi=g("LEASE_LIAB") / 1e8,
        ocf_h1_yi=ocf / 1e8, capex_h1_yi=capex / 1e8, np_h1_yi=g("PARENT_NETPROFIT") / 1e8,
        pb=mc / (g("TOTAL_PARENT_EQUITY") / 1e8) if g("TOTAL_PARENT_EQUITY") > 0 else np.nan,
        sows_wan=m["sows_wan"], sows_date=m["sows_date"], sows_def=m["sows_def"],
        ytd2026_heads_wan=ytd_heads, ytd2026_months=ytd_months, ytd2026_scope=ytd_scope, run_rate_2026_wan=run_rate,
        out2025_fat_wan=m["out2025_fat_wan"], target2026_total_wan=m["target2026_total_wan"],
        last_price=last_px, price_month=px_month, national_avg_same_month=nat,
        price_premium_pct=last_px / nat - 1 if pd.notna(last_px) and pd.notna(nat) else np.nan,
        cost_latest_kg=m["cost_latest_kg"], cost_date=m["cost_date"], cost_def=m["cost_def"],
        cost_target2026_kg=m["cost_target2026_kg"], cost_target2027_kg=m["cost_target2027_kg"],
        cb_outstanding_yi=m["cb_outstanding_yi"], cb_conv_price=m["cb_conv_price"],
        parent_share_hog=m["parent_share_hog"], flags=m["flags"], calc_note="；".join(note)))

sc = pd.DataFrame(rows)
sc["mcap_per_sow_wan"] = sc["mcap_yi"] / sc["sows_wan"]       # 亿元 / 万头 = 万元/头
sc["ev_per_sow_wan"] = sc["ev_yi"] / sc["sows_wan"]
sc["ev_per_runrate_head_yuan"] = sc["ev_yi"] * 1e8 / (sc["run_rate_2026_wan"] * 1e4)
sc["mcap_per_runrate_head_yuan"] = sc["mcap_yi"] * 1e8 / (sc["run_rate_2026_wan"] * 1e4)
# +1 元/kg on the 2026 run-rate at 120 kg, attributable share applied; pre-tax (hog farming is income-tax exempt)
sc["dprofit_per_yuan_yi"] = sc["run_rate_2026_wan"] * 1e4 * 120 * 1 * sc["parent_share_hog"] / 1e8
sc["dprofit_per_yuan_pct_mcap"] = sc["dprofit_per_yuan_yi"] / sc["mcap_yi"]
sc["cb_dilution_pct_if_converted"] = (sc["cb_outstanding_yi"] * 1e8 / sc["cb_conv_price"]) / (sc["mcap_yi"] * 1e8 / sc["close"])
sc.to_csv(PROC / "screen_snapshot.csv", index=False)

pd.set_option("display.width", 260)
cols = ["name", "mcap_yi", "ev_yi", "debt_ratio", "cash_to_st_debt", "ocf_h1_yi", "np_h1_yi", "sows_wan",
        "mcap_per_sow_wan", "run_rate_2026_wan", "ev_per_runrate_head_yuan", "price_premium_pct", "cost_latest_kg",
        "dprofit_per_yuan_pct_mcap", "cb_dilution_pct_if_converted"]
print(sc[cols].round(2).to_string(index=False))
print("national monthly avg (nxin):", nat_month.loc["2026-06":].round(2).to_dict())
