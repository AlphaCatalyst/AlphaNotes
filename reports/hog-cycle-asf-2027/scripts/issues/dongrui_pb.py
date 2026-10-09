"""Issue #2: does Dongrui's low P/B buy undervalued, earning assets, or price in losses and dilution?

Snapshot: 2026-10-09 close (Tencent quote taken after the close, cached under data/raw/stocks/),
balance sheets at 2026-06-30. History uses stock_daily.csv (to 2026-10-08) and fin_quarterly.csv.

Outputs (data/processed/issues/):
  dongrui_pb_peers.csv       same-date P/B, P/TB, own-history percentile, ROE windows, leverage
  dongrui_pb_history.csv     Dongrui P/B and BVPS at anchor dates, log decomposition price vs book
  dongrui_equity_bridge.csv  parent equity 2021-06-30 -> 2026-06-30
  dongrui_assets.csv         asset/liability composition at 2026-06-30 with note references
  dongrui_h2_2026.csv        2026H2 loss estimate (month by month, stated assumptions)
  dongrui_scenarios.csv      2027 earnings / ROE / cash flow grid by national price and full cost
  dongrui_value_in_use.csv   equity value of the farm assets at a normalised price (book-value test)
  dongrui_buy_vs_build.csv   EV per head vs book cost per head of built capacity
  dongrui_full_cycle.csv     annual profit, ROE and national price 2015-2026H1
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from common import PROC, RAW, S  # noqa: E402

OUT = PROC / "issues"
OUT.mkdir(exist_ok=True)
SNAP = "2026-10-09"
BS = "2026-06-30"
DR = "001201"

PEERS = ["001201", "002714", "300498", "000876", "002100", "002567", "002385", "000048", "605296",
         "603477", "002840", "600975", "002548", "000735", "002124", "603717", "002157", "603363"]
FLAGS = {
    "002714": "A股×A价＋H股×H价×汇率",
    "000876": "备考：计入2026-08定增（约4.59亿股、募资约26亿元）",
    "002124": "预重整中，净资产很薄",
    "002157": "2023年重整后",
    "603363": "2024—2025年重整后",
    "603717": "高杠杆",
    "000735": "养猪＋地产等多元业务",
    "300498": "含黄羽鸡业务",
}
MUYUAN_A_SHARES, MUYUAN_H_SHARES, HKDCNY = 5_462_773_044, 310_223_100, 0.8585
NEWHOPE_PLACEMENT_SHARES, NEWHOPE_PLACEMENT_CASH = round(2_600_000_000 / 5.66), 26e8

# ------------------------------------------------------------------ snapshot quotes
QUOTE_FILE = RAW / "stocks" / f"tencent_quote_{SNAP.replace('-', '')}.txt"


def sym(code):
    if code.startswith("hk"):
        return code
    return ("sh" if code.startswith("6") else "sz") + code


def load_quotes():
    if not QUOTE_FILE.exists():
        syms = ",".join(sym(c) for c in PEERS + ["hk02714"])
        r = S.get(f"https://qt.gtimg.cn/q={syms}", timeout=30)
        QUOTE_FILE.write_text(r.content.decode("gbk"), encoding="utf-8")
    q = {}
    for line in QUOTE_FILE.read_text(encoding="utf-8").strip().split(";"):
        if "=" not in line:
            continue
        f = line.split("=", 1)[1].strip().strip('"').split("~")
        if len(f) < 47:
            continue
        hk = f[0] == "100"
        code = "hk" + f[2] if hk else f[2]
        stamp = f[30].replace("/", "").replace(" ", "").replace(":", "")
        q[code] = dict(close=float(f[3]), stamp=stamp, mcap_tx_yi=np.nan if hk else float(f[45]),
                       pb_tx=np.nan if hk else float(f[46]))
    for c in PEERS:
        assert q[c]["stamp"].startswith(SNAP.replace("-", "")) and q[c]["stamp"][8:12] >= "1500", (c, q[c]["stamp"])
    return q


quotes = load_quotes()

fin = pd.read_csv(PROC / "fin_quarterly.csv", dtype={"code": str})
fin = fin.sort_values(["code", "report_date"])
sd = pd.read_csv(PROC / "stock_daily.csv", dtype={"code": str},
                 usecols=["code", "date", "close_raw", "close_hfq"])
nz = lambda x: 0.0 if pd.isna(x) else float(x)  # noqa: E731


def common_equity(r):
    return float(r["TOTAL_PARENT_EQUITY"]) - nz(r["OTHER_EQUITY_TOOL"])


def fy_profit(code, year):
    r = fin[(fin["code"] == code) & (fin["report_date"] == f"{year}-12-31")]
    return float(r["PARENT_NETPROFIT"].iloc[0]) if len(r) and pd.notna(r["PARENT_NETPROFIT"].iloc[0]) else np.nan


def h1_profit(code, year):
    r = fin[(fin["code"] == code) & (fin["report_date"] == f"{year}-06-30")]
    return float(r["PARENT_NETPROFIT"].iloc[0]) if len(r) else np.nan


def equity_at(code, d):
    r = fin[(fin["code"] == code) & (fin["report_date"] == d)]
    return common_equity(r.iloc[0]) if len(r) and pd.notna(r["TOTAL_PARENT_EQUITY"].iloc[0]) else np.nan


def roe_window(code, profits, dates, years):
    eq = [equity_at(code, d) for d in dates]
    if any(np.isnan(eq)) or any(np.isnan(profits)):
        return np.nan
    return float(np.sum(profits) / np.mean(eq) / years)


# five years since Dongrui's listing: 2021H2..2026H1; eight calendar years 2018..2025
HALF_ENDS = [f"{y}-{m}" for y in range(2021, 2027) for m in ("06-30", "12-31")][:-1]


def roe_5y(code):
    p = [fy_profit(code, 2021) - h1_profit(code, 2021)] + [fy_profit(code, y) for y in range(2022, 2026)] + [h1_profit(code, 2026)]
    return roe_window(code, p, HALF_ENDS, 5.0), float(np.sum(p))


def roe_8y(code):
    p = [fy_profit(code, y) for y in range(2018, 2026)]
    return roe_window(code, p, [f"{y}-12-31" for y in range(2017, 2026)], 8.0)


def roe_ttm(code):
    f = fin[(fin["code"] == code) & (fin["report_date"].isin(["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]))]
    ni = f["PARENT_NETPROFIT_Q"].sum()
    return float(ni / np.mean([equity_at(code, "2025-06-30"), equity_at(code, BS)])), float(ni)


def pb_history(code, start="2018-01-01"):
    """Daily P/B with the latest quarter-end book (not point-in-time); shares follow split/bonus factors."""
    s = sd[(sd["code"] == code) & (sd["date"] >= start)].dropna(subset=["close_raw", "close_hfq"]).copy()
    s["date"] = pd.to_datetime(s["date"])
    s["factor"] = s["close_hfq"] / s["close_raw"]
    q = fin[(fin["code"] == code)].dropna(subset=["TOTAL_PARENT_EQUITY", "SHARE_CAPITAL"]).copy()
    q["eq"] = q.apply(common_equity, axis=1)
    q["rd"] = pd.to_datetime(q["report_date"])
    first_px = s["date"].min()
    q = q[q["rd"] >= first_px - pd.Timedelta(days=1)] if code in ("001201", "605296") else q
    m = pd.merge_asof(s.sort_values("date"), q[["rd", "eq", "SHARE_CAPITAL"]].sort_values("rd"),
                      left_on="date", right_on="rd", direction="backward").dropna(subset=["eq"])
    fq = s.set_index("date")["factor"]
    m["factor_q"] = m["rd"].map(lambda d: fq[:d].iloc[-1] if len(fq[:d]) else np.nan)
    m = m.dropna(subset=["factor_q"])
    m["shares"] = m["SHARE_CAPITAL"] * m["factor"] / m["factor_q"]
    m["pb"] = m["close_raw"] * m["shares"] / m["eq"]
    return m[["date", "close_raw", "pb"]]


# ------------------------------------------------------------------ 1. same-date P/B vs peers
rows = []
for code in PEERS:
    r = fin[(fin["code"] == code) & (fin["report_date"] == BS)].iloc[0]
    px = quotes[code]["close"]
    shares = float(r["SHARE_CAPITAL"])
    eq = common_equity(r)
    if code == "002714":
        mcap = MUYUAN_A_SHARES * px + MUYUAN_H_SHARES * quotes["hk02714"]["close"] * HKDCNY
    elif code == "000876":
        shares += NEWHOPE_PLACEMENT_SHARES
        eq += NEWHOPE_PLACEMENT_CASH
        mcap = shares * px
    else:
        mcap = shares * px
    gw = nz(r["GOODWILL"])
    ttm, ni_ttm = roe_ttm(code)
    r5, ni5 = roe_5y(code)
    hist = pb_history(code, start="2021-06-30" if code in ("001201", "605296") else "2018-01-01")
    pb_now = mcap / eq if eq > 0 else np.nan
    debt = sum(nz(r[k]) for k in ("SHORT_LOAN", "NONCURRENT_LIAB_1YEAR", "LONG_LOAN", "BOND_PAYABLE", "LEASE_LIAB"))
    st = nz(r["SHORT_LOAN"]) + nz(r["NONCURRENT_LIAB_1YEAR"])
    rows.append(dict(
        code=code, name=r["name"], close=px, mcap_yi=mcap / 1e8, parent_equity_yi=eq / 1e8, goodwill_yi=gw / 1e8,
        pb=pb_now, ptb=mcap / (eq - gw) if eq - gw > 0 else np.nan, pb_tencent=quotes[code]["pb_tx"],
        pb_hist_start=hist["date"].min().date().isoformat(), pb_hist_min=hist["pb"].min(),
        pb_hist_min_date=hist.loc[hist["pb"].idxmin(), "date"].date().isoformat(), pb_hist_median=hist["pb"].median(),
        pb_hist_max=hist["pb"].max(), pb_hist_pct=float((hist["pb"] <= pb_now).mean()) if pd.notna(pb_now) else np.nan,
        roe_ttm=ttm, ni_ttm_yi=ni_ttm / 1e8, roe_5y=r5, ni_5y_yi=ni5 / 1e8, roe_8y=roe_8y(code),
        debt_ratio=float(r["TOTAL_LIABILITIES"] / r["TOTAL_ASSETS"]), cash_to_st_debt=nz(r["MONETARYFUNDS"]) / st if st else np.nan,
        ev_yi=(mcap + debt - nz(r["MONETARYFUNDS"])) / 1e8, flag=FLAGS.get(code, "")))
peers = pd.DataFrame(rows)
peers["pb_rank"] = peers["pb"].rank()
peers["roe_5y_rank"] = peers["roe_5y"].rank(ascending=False)

# what the snapshot price implies: flat national price at which market cap = 10x 2027 parent earnings,
# same inputs and formula as model_2027.py (base volume, base cost, base piglet margin), repriced to SNAP
mi = pd.read_csv(PROC / "model_company_inputs.csv", dtype={"code": str}).set_index("code")
DONGRUI_BASE = dict(d=0.03, s=0.16, e=2.5)
imp = {}
for code, c in mi.iterrows():
    if pd.isna(c["C_base"]) or code not in set(peers["code"]):
        continue
    mc = float(peers.loc[peers["code"] == code, "mcap_yi"].iloc[0])
    kg = c["V_base"] * 1e4 * c["W"] / 1e8
    pig = c["piglets"] * 1e4 * 150.0 / 1e8
    for k in (10, 15):
        px_real = c["C_base"] + (mc / k / c["parent_share"] - pig) / kg
        imp[(code, k)] = ((px_real - DONGRUI_BASE["s"] * DONGRUI_BASE["e"]) / (1 + DONGRUI_BASE["d"]) if code == DR
                          else px_real / (1 + c["regional_premium"]))
peers["implied_national_10x"] = peers["code"].map(lambda c: imp.get((c, 10), np.nan))
peers["implied_national_15x"] = peers["code"].map(lambda c: imp.get((c, 15), np.nan))
peers["cost_2027_base"] = peers["code"].map(mi["C_base"])
sc = pd.read_csv(PROC / "screen_snapshot.csv", dtype={"code": str}).set_index("code")
peers["run_rate_2026_wan"] = peers["code"].map(sc["run_rate_2026_wan"])
peers["run_rate_scope"] = peers["code"].map(sc["ytd2026_scope"])
peers["ev_per_runrate_head"] = peers["ev_yi"] * 1e8 / (peers["run_rate_2026_wan"] * 1e4)
peers.to_csv(OUT / "dongrui_pb_peers.csv", index=False)

# ------------------------------------------------------------------ 2. Dongrui P/B history and decomposition
d = sd[sd["code"] == DR].set_index("date")
ANCHORS = ["2021-06-30", "2021-12-31", "2022-12-30", "2023-09-28", "2023-12-29", "2024-12-31",
           "2025-06-30", "2025-12-31", "2026-06-30", SNAP]
BOOK_FOR = {"2022-12-30": "2022-12-31", "2023-09-28": "2023-09-30", "2023-12-29": "2023-12-31", SNAP: BS}
TREASURY = {"2024-12-31": 2_860_000, "2025-06-30": 2_860_000, "2025-12-31": 2_860_000, "2026-06-30": 2_860_000, BS: 2_860_000}
hrows = []
for a in ANCHORS:
    bd = BOOK_FOR.get(a, a)
    r = fin[(fin["code"] == DR) & (fin["report_date"] == bd)].iloc[0]
    if a == SNAP:
        close, hfq = quotes[DR]["close"], float(d.loc["2026-10-08", "close_hfq"]) * quotes[DR]["close"] / float(d.loc["2026-10-08", "close_raw"])
    else:
        close, hfq = float(d.loc[a, "close_raw"]), float(d.loc[a, "close_hfq"])
    out_sh = float(r["SHARE_CAPITAL"]) - TREASURY.get(bd, 0)
    eq = common_equity(r)
    bvps = eq / out_sh
    hrows.append(dict(date=a, book_date=bd, close=close, shares_out=out_sh, parent_equity_yi=eq / 1e8, bvps=bvps,
                      pb=close / bvps, factor=hfq / close, close_hfq=hfq, bvps_adj=bvps * hfq / close))
hist = pd.DataFrame(hrows)
hist["dln_pb"] = np.log(hist["pb"]).diff()
hist["dln_price_adj"] = np.log(hist["close_hfq"]).diff()
hist["dln_bvps_adj"] = np.log(hist["bvps_adj"]).diff()
hist.to_csv(OUT / "dongrui_pb_history.csv", index=False)

# equity bridge 2021-06-30 -> 2026-06-30
ni_5y = roe_5y(DR)[1]
e0, e1 = equity_at(DR, "2021-06-30"), equity_at(DR, BS)
bridge = pd.DataFrame([
    ("2021-06-30 归母净资产", e0, "fin_quarterly"),
    ("2021H2—2026H1 归母净利润合计", ni_5y, "fin_quarterly（2021全年−2021H1，2022—2025全年，2026H1）"),
    ("2022年现金分红（每10股派2元×177,338,000股）", -0.2 * 177_338_000, "2021年报利润分配预案；2022-05实施"),
    ("2023-12定增募资净额（20.56元/股）", 911_012_049.54, "2023-12发行情况报告书"),
    ("2024—2025回购（库存股，286万股）", -48_410_841.17, "2026半年报资产负债表“减：库存股”"),
], columns=["item", "yuan", "source"])
bridge.loc[len(bridge)] = ("其他（差额：资本公积、少数股东交易等）", e1 - bridge["yuan"].sum(), "倒算")
bridge.loc[len(bridge)] = ("2026-06-30 归母净资产", e1, "fin_quarterly")
bridge["yi"] = bridge["yuan"] / 1e8
bridge.to_csv(OUT / "dongrui_equity_bridge.csv", index=False)

# ------------------------------------------------------------------ 3. asset composition (2026-06-30)
r = fin[(fin["code"] == DR) & (fin["report_date"] == BS)].iloc[0]
A = [  # item, yuan, note
    ("货币资金", r["MONETARYFUNDS"], "资产负债表"),
    ("存货：消耗性生物资产（净额）", 701_689_880.95, "附注七、6：账面余额7.90亿，跌价准备0.88亿（H1计提1.18亿、转销0.66亿）"),
    ("存货：原材料等", 134_631_550.54 + 3_478_100.65, "附注七、6"),
    ("生产性生物资产（种猪）", r["PRODUCTIVE_BIOLOGY_ASSET"], "成熟种猪3年折旧、残值10%"),
    ("固定资产：房屋及建筑物", 3_017_192_814.69, "原值35.50亿，累计折旧5.33亿；20—30年，残值5%；其中26.17亿建在租赁农地上，无法办产权证"),
    ("固定资产：生产设备", 812_704_943.05, "原值13.62亿，累计折旧5.49亿；5—10年"),
    ("固定资产：运输及其他设备", 13_187_661.24 + 65_281_651.86, "5年"),
    ("在建工程（猪场工程）", r["CIP"], "附注七、10"),
    ("使用权资产（主要为租赁土地）", r["USERIGHT_ASSET"], "资产负债表"),
]
assets = pd.DataFrame(A, columns=["item", "yuan", "note"])
assets.loc[len(assets)] = ("其他资产（差额）", float(r["TOTAL_ASSETS"]) - assets["yuan"].sum(), "倒算")
assets.loc[len(assets)] = ("资产合计", float(r["TOTAL_ASSETS"]), "资产负债表")
L = [
    ("短期借款", r["SHORT_LOAN"]), ("一年内到期的非流动负债", r["NONCURRENT_LIAB_1YEAR"]), ("长期借款", r["LONG_LOAN"]),
    ("租赁负债", r["LEASE_LIAB"]), ("应付票据及账款", r["NOTE_ACCOUNTS_PAYABLE"]),
]
for k, v in L:
    assets.loc[len(assets)] = (k, -float(v), "资产负债表（负债，取负号）")
assets.loc[len(assets)] = ("其他负债（差额）", -(float(r["TOTAL_LIABILITIES"]) - sum(float(v) for _, v in L)), "倒算，含粤财基金附回购投资款0.60亿")
assets.loc[len(assets)] = ("少数股东权益", -float(r["MINORITY_EQUITY"]), "资产负债表")
assets.loc[len(assets)] = ("归母净资产", common_equity(r), "资产负债表")
assets["yi"] = assets["yuan"] / 1e8
assets["pct_of_parent_equity"] = assets["yuan"] / common_equity(r)
assets.to_csv(OUT / "dongrui_assets.csv", index=False)

# ------------------------------------------------------------------ national price, Dongrui realised premium
nx = pd.read_csv(PROC / "nxin_price_wide.csv")
nx["m"] = pd.to_datetime(nx["week_label"]).dt.strftime("%Y-%m")
nat_m = nx.groupby("m")["全国"].mean()
south_m = nx.groupby("m")["华南"].mean()
ms = pd.read_csv(ROOT / "research/dongrui/monthly_sales.csv")
ms = ms.set_index("month")


def premium(a, b):
    """Volume-weighted Dongrui commodity-hog price over the national price for the same months, minus 1."""
    m = ms.loc[a:b]
    kg = m["revenue_wan"] / m["avg_price"]
    return float((m["avg_price"] * kg).sum() / (nat_m.reindex(m.index) * kg).sum() - 1)


PREM_2025 = premium("2025-01", "2025-12")
PREM_2026 = premium("2026-01", "2026-08")

# ------------------------------------------------------------------ 4. 2026H2 loss estimate
fut = pd.read_csv(PROC / "futures_lh_daily.csv")
f8 = fut[fut["trade_date"] == "2026-10-08"].set_index("contract")["close"] / 1000
SHARES_OUT = 257_784_001 - 2_860_000
h2 = []
for mth, cost in [("2026-07", 13.8), ("2026-08", 13.7), ("2026-09", 13.6), ("2026-10", 13.4), ("2026-11", 13.2), ("2026-12", 13.0)]:
    if mth in ms.index:
        heads, rev, px, basis = ms.loc[mth, "heads"], ms.loc[mth, "revenue_wan"] * 1e4, ms.loc[mth, "avg_price"], "简报实际"
    else:
        heads = ms.loc[["2026-07", "2026-08"], "heads"].mean()
        nat = {"2026-09": nat_m["2026-09"], "2026-10": f8["LH2611"], "2026-11": f8["LH2611"],
               "2026-12": (f8["LH2611"] + f8["LH2701"]) / 2}[mth]
        px = nat * (1 + PREM_2026)
        kg_per_head = float((ms.loc[["2026-07", "2026-08"], "revenue_wan"] * 1e4 / ms.loc[["2026-07", "2026-08"], "avg_price"]).sum()
                            / ms.loc[["2026-07", "2026-08"], "heads"].sum())
        rev = heads * kg_per_head * px
        basis = "假设：头数取7—8月均值；价格=全国价×(1+2026年1—8月实际溢价)；9月全国价用新牧网月均，10—12月用LH2611/LH2701收盘"
    kg = rev / px
    h2.append(dict(month=mth, heads=heads, kg_yi=kg / 1e8, price=px, cost=cost, margin_kg=px - cost,
                   hog_profit_yi=kg * (px - cost) / 1e8, basis=basis))
h2 = pd.DataFrame(h2)
h2.to_csv(OUT / "dongrui_h2_2026.csv", index=False)
H2_LOSS = float(h2["hog_profit_yi"].sum())  # before extra inventory write-downs and non-hog segments
EQ_2026E = (e1 / 1e8) + H2_LOSS

# ------------------------------------------------------------------ 4b. 2026H1 loss attribution (approximate)
# cycle: realised price vs a normal year; utilisation: fixed D&A + interest spread over actual vs full-capacity kg;
# structural: full cost at full utilisation vs the median latest full cost of listed peers; premium: realised vs national
h1m = ms.loc["2026-01":"2026-06"]
KG_H1 = float((h1m["revenue_wan"] * 1e4 / h1m["avg_price"]).sum())
PX_H1 = float((h1m["revenue_wan"] * 1e4).sum() / KG_H1)
NAT_H1 = float((nat_m.reindex(h1m.index) * h1m["revenue_wan"] / h1m["avg_price"]).sum() / (h1m["revenue_wan"] / h1m["avg_price"]).sum())
COST_H1 = 13.95  # company, 2026H1 full cost
NORMAL_NAT = 13.5
FULL_KG_HALF = 200e4 * W_FULL / 2 if (W_FULL := 115) else np.nan
FIXED_H1 = (195_643_833.18 + 7_264_404.89 + 773_396.20 + 466_528.52 + float(r["FE_INTEREST_EXPENSE"])) / 1e8
PEER_COST = float(sc.loc[[c for c in sc.index if c != DR], "cost_latest_kg"].median())
util_kg = (FIXED_H1 * 1e8 / KG_H1) - (FIXED_H1 * 1e8 / FULL_KG_HALF)
IMPAIR_H1 = 1.17608272800
k = KG_H1 / 1e8
attr = pd.DataFrame([
    ("基准：同行中位成本、常态全国价下的毛利", (NORMAL_NAT - PEER_COST) * k,
     f"常态全国价{NORMAL_NAT}元（假设）减上市同行最新完全成本中位数{PEER_COST:.2f}，乘H1销售重量{k:.3f}亿公斤"),
    ("周期：H1全国价低于常态", -(NORMAL_NAT - NAT_H1) * k, f"H1全国价（按东瑞月度销量加权）{NAT_H1:.2f}"),
    ("周期：存货跌价准备（H1计提）", -IMPAIR_H1, "附注七、6；价格回升时随销售转销"),
    ("未满产：固定成本摊薄不足", -util_kg * k,
     f"H1折旧摊销＋利息{FIXED_H1:.2f}亿；实际重量对比满产{FULL_KG_HALF / 1e8:.2f}亿公斤（200万头×115公斤÷2），合{util_kg:.2f}元/公斤"),
    ("结构性：满产后成本仍高于同行中位数", -(COST_H1 - util_kg - PEER_COST) * k,
     f"H1完全成本{COST_H1}减未满产影响{util_kg:.2f}，再减同行中位数{PEER_COST:.2f}，合{COST_H1 - util_kg - PEER_COST:.2f}元/公斤"),
    ("区域与供港溢价", (PX_H1 - NAT_H1) * k, f"H1商品猪实现均价{PX_H1:.2f}对比全国{NAT_H1:.2f}"),
], columns=["item", "yi", "basis"])
actual = h1_profit(DR, 2026) / 1e8
attr.loc[len(attr)] = ("其他（非生猪业务、仔猪、营业外与估算误差，倒算）", actual - attr["yi"].sum(), "倒算")
attr.loc[len(attr)] = ("2026H1 归母净利润（实际）", actual, "半年报")
attr.to_csv(OUT / "dongrui_h1_attribution.csv", index=False)

# ------------------------------------------------------------------ 5. 2027 grid
DA_YI = (195_643_833.18 + 7_264_404.89 + 773_396.20 + 466_528.52) * 2 / 1e8  # 2026H1 D&A annualised
CAPEX_YI = 1.6  # 2026 plan (company, 2026-04/09 records)
V, W, PIG = 160, 115, 40  # model_2027 base: fattening 万头, kg, piglets 万头
PARENT = 0.99


def piglet_margin(nat):
    return 50.0 * (nat - 15.0)  # 元/头; 18 元 -> 150 (model_2027 base); 12.5 元 -> -125 (assumption)


grid = []
for nat in (11.0, float(np.mean([(f8["LH2701"] + f8["LH2703"]) / 2, f8["LH2705"], (f8["LH2707"] + f8["LH2709"]) / 2,
                                 (f8["LH2707"] + f8["LH2709"]) / 2 * 1.02])), 14.0, 16.0, 18.0):
    for prem_name, p in (("溢价低（2025年实际）", PREM_2025), ("溢价中（2026年1—8月实际）", PREM_2026)):
        for cost in (13.5, 12.9, 12.5):
            px = nat * (1 + p)
            hog = V * 1e4 * W * (px - cost) / 1e8
            pig = PIG * 1e4 * piglet_margin(nat) / 1e8
            ni = (hog + pig) * PARENT
            eq_end = EQ_2026E + ni
            ocf = ni + DA_YI
            grid.append(dict(national=nat, premium_case=prem_name, premium=p, realized=px, cost=cost, hog_profit_yi=hog,
                             piglet_profit_yi=pig, parent_ni_yi=ni, roe=ni / ((EQ_2026E + eq_end) / 2),
                             bvps_end2027=eq_end * 1e8 / SHARES_OUT, ocf_yi=ocf, fcf_yi=ocf - CAPEX_YI,
                             pe_at_snapshot=quotes[DR]["close"] * SHARES_OUT / 1e8 / ni if ni > 0 else np.nan))
grid = pd.DataFrame(grid)
grid.to_csv(OUT / "dongrui_scenarios.csv", index=False)

# ------------------------------------------------------------------ 5b. forward four-year cycles (no peak-year cherry-picking)
STRIP = float(grid["national"].unique()[1])
CYCLES = {"含一个18元高点年": [11.0, STRIP, 14.0, 18.0], "无高点": [11.0, STRIP, 14.0, 16.0], "低迷延长": [11.0, 11.0, STRIP, 14.0]}
cyc = []
for cname, path in CYCLES.items():
    for cost in (13.5, 12.9, 12.5):
        eq, nis = EQ_2026E, []
        for nat in path:
            ni = (V * 1e4 * W * (nat * (1 + PREM_2026) - cost) / 1e8 + PIG * 1e4 * piglet_margin(nat) / 1e8) * PARENT
            nis.append(ni)
            eq += ni
        cyc.append(dict(cycle=cname, path="/".join(f"{x:.1f}" for x in path), avg_national=float(np.mean(path)), cost=cost,
                        avg_ni_yi=float(np.mean(nis)), cum_ni_yi=float(np.sum(nis)), avg_roe=float(np.mean(nis)) / ((EQ_2026E + eq) / 2),
                        bvps_end=eq * 1e8 / SHARES_OUT, min_bvps=min(EQ_2026E + np.cumsum(nis)) * 1e8 / SHARES_OUT))
cyc = pd.DataFrame(cyc)
cyc.to_csv(OUT / "dongrui_cycles.csv", index=False)

# ------------------------------------------------------------------ 6. value-in-use test of book value
# Equity value = PV(operating free cash flow over 20 years at the normalised price) - net debt - other claims.
NET_DEBT = (sum(nz(r[k]) for k in ("SHORT_LOAN", "NONCURRENT_LIAB_1YEAR", "LONG_LOAN", "LEASE_LIAB")) - nz(r["MONETARYFUNDS"])
            - nz(r["TRADE_FINASSET_NOTFVTPL"])) / 1e8
OTHER_CLAIMS = 0.60 + float(r["MINORITY_EQUITY"]) / 1e8  # Yuecai buy-back money + minorities
INTEREST_KG = float(r["FE_INTEREST_EXPENSE"]) * 2 / (V * 1e4 * W)  # full cost includes interest; add back for unlevered FCF
# steady-state reinvestment: equipment, vehicles, other equipment and breeding stock wear out within 20 years;
# 2026H1 depreciation of those classes annualised (buildings excluded: 20-30 year lives)
BIO_DEP_H1 = 195_643_833.18 - 151_592_088.27
REINVEST_YI = 2 * (71_344_508.97 + 2_551_754.59 + 11_240_810.03 + BIO_DEP_H1) / 1e8
vu = []
for nat in (12.5, 13.0, 13.5, 14.0, 14.5, 15.0, 16.0):
    for cost in (13.5, 12.9, 12.5):
        for wacc in (0.08, 0.10):
            px = nat * (1 + PREM_2025)
            ebitda = V * 1e4 * W * (px - cost) / 1e8 + PIG * 1e4 * piglet_margin(nat) / 1e8 + DA_YI + INTEREST_KG * V * 1e4 * W / 1e8
            fcf = ebitda - REINVEST_YI
            annuity = (1 - (1 + wacc) ** -20) / wacc
            ev = fcf * annuity
            vu.append(dict(national=nat, cost=cost, wacc=wacc, ebitda_yi=ebitda, fcf_yi=fcf, ev_yi=ev,
                           equity_value_yi=ev - NET_DEBT - OTHER_CLAIMS, book_equity_yi=e1 / 1e8,
                           equity_value_over_book=(ev - NET_DEBT - OTHER_CLAIMS) / (e1 / 1e8),
                           equity_value_per_share=(ev - NET_DEBT - OTHER_CLAIMS) * 1e8 / SHARES_OUT))
vu = pd.DataFrame(vu)
vu.to_csv(OUT / "dongrui_value_in_use.csv", index=False)

# ------------------------------------------------------------------ 7. buy vs build (book cost per head; replacement benchmarks in research/replacement_cost/)
mcap = quotes[DR]["close"] * SHARES_OUT / 1e8
EV = mcap + NET_DEBT + OTHER_CLAIMS
FA_COST = 5_105_601_694.90 / 1e8
FA_NBV = float(r["FIXED_ASSET"]) / 1e8
bb = pd.DataFrame([
    ("市值（流通股本扣除库存股）", mcap, np.nan),
    ("净有息负债（含租赁，扣现金和交易性金融资产）", NET_DEBT, np.nan),
    ("少数股东权益＋粤财附回购投资款", OTHER_CLAIMS, np.nan),
    ("企业价值 EV", EV, EV * 1e8 / 200e4),
    ("EV ÷ 2026年肉猪目标约150万头", EV, EV * 1e8 / 150e4),
    ("固定资产原值（建成成本）", FA_COST, FA_COST * 1e8 / 200e4),
    ("固定资产净值", FA_NBV, FA_NBV * 1e8 / 200e4),
    ("固定资产原值＋使用权资产＋种猪＋存货（新建一套的账面口径）",
     FA_COST + float(r["USERIGHT_ASSET"]) / 1e8 + float(r["PRODUCTIVE_BIOLOGY_ASSET"]) / 1e8 + float(r["INVENTORY"]) / 1e8,
     (FA_COST + float(r["USERIGHT_ASSET"]) / 1e8 + float(r["PRODUCTIVE_BIOLOGY_ASSET"]) / 1e8 + float(r["INVENTORY"]) / 1e8) * 1e8 / 200e4),
    ("固定资产净值＋使用权资产＋种猪＋存货（折旧后账面口径）",
     FA_NBV + float(r["USERIGHT_ASSET"]) / 1e8 + float(r["PRODUCTIVE_BIOLOGY_ASSET"]) / 1e8 + float(r["INVENTORY"]) / 1e8,
     (FA_NBV + float(r["USERIGHT_ASSET"]) / 1e8 + float(r["PRODUCTIVE_BIOLOGY_ASSET"]) / 1e8 + float(r["INVENTORY"]) / 1e8) * 1e8 / 200e4),
], columns=["item", "yi", "yuan_per_head_of_200wan"])
bb.to_csv(OUT / "dongrui_buy_vs_build.csv", index=False)

# ------------------------------------------------------------------ 8. full-cycle record
nat_y = nx.assign(y=pd.to_datetime(nx["week_label"]).dt.year).groupby("y")["全国"].mean()
fc = []
for y in range(2015, 2026):
    eq0, eq1 = equity_at(DR, f"{y - 1}-12-31"), equity_at(DR, f"{y}-12-31")
    ni = fy_profit(DR, y)
    fc.append(dict(period=str(y), parent_ni_yi=ni / 1e8, parent_equity_end_yi=eq1 / 1e8,
                   roe=ni / np.nanmean([eq0, eq1]) if pd.notna(ni) else np.nan, national_price=nat_y.get(y, np.nan)))
fc.append(dict(period="2026H1", parent_ni_yi=h1_profit(DR, 2026) / 1e8, parent_equity_end_yi=e1 / 1e8,
               roe=h1_profit(DR, 2026) / np.mean([equity_at(DR, "2025-12-31"), e1]), national_price=nat_m.loc["2026-01":"2026-06"].mean()))
pd.DataFrame(fc).to_csv(OUT / "dongrui_full_cycle.csv", index=False)

# ------------------------------------------------------------------ console summary
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
print(peers[["name", "close", "mcap_yi", "pb", "pb_tencent", "ptb", "pb_hist_pct", "pb_hist_min", "pb_hist_min_date", "pb_hist_median",
             "roe_ttm", "roe_5y", "roe_8y", "debt_ratio", "flag"]].sort_values("pb").round(3).to_string(index=False))
print(peers[["name", "pb", "roe_5y", "cost_2027_base", "implied_national_10x", "implied_national_15x", "ev_per_runrate_head",
             "run_rate_scope"]].sort_values("implied_national_10x").round(2).to_string(index=False))
print(hist.round(3).to_string(index=False))
print(bridge[["item", "yi"]].round(3).to_string(index=False))
print(assets[["item", "yi", "pct_of_parent_equity"]].round(3).to_string(index=False))
print(f"premium 2025 {PREM_2025:.3f}  2026Jan-Aug {PREM_2026:.3f}")
print(attr.round(3).to_string(index=False))
print(cyc.round(3).to_string(index=False))
print(h2.round(3).drop(columns=["basis"]).to_string(index=False), "H2 hog profit", round(H2_LOSS, 2), "equity 2026E", round(EQ_2026E, 2))
print("D&A annualised", round(DA_YI, 2), "net debt", round(NET_DEBT, 2), "EV", round(EV, 2), "interest/kg", round(INTEREST_KG, 3),
      "reinvest", round(REINVEST_YI, 2))
print(grid[grid["premium_case"].str.startswith("溢价中")].round(2).to_string(index=False))
print(vu[vu["wacc"] == 0.08].round(2).to_string(index=False))
print(bb.round(2).to_string(index=False))
print(pd.DataFrame(fc).round(3).to_string(index=False))
