"""Report charts (PNG) -> charts/."""
import numpy as np
import pandas as pd
import matplotlib.dates as mdates
from matplotlib.patches import Patch

from common import PROC, ROOT
from plotstyle import C, PALETTE, plt, save, source, title

sd = pd.read_csv(PROC / "stock_daily.csv", dtype={"code": str}, parse_dates=["date"])
sd = sd[sd["date"] <= "2026-10-08"]
sd["px"] = sd["close_tx_hfq"].fillna(sd["close_hfq"])
nx = pd.read_csv(PROC / "nxin_price_wide.csv", parse_dates=["week_label"])
fut = pd.read_csv(PROC / "futures_lh_daily.csv", parse_dates=["trade_date"])
ew = pd.read_csv(PROC / "pig_ew_index.csv", parse_dates=["date"])
tp = pd.read_csv(PROC / "two_phase_panel.csv", dtype={"code": str})

WINDOWS = [("A", "2018-08-02", "2018-12-28"), ("B", "2018-12-28", "2019-04-30"), ("C", "2019-04-30", "2019-11-08"),
           ("D", "2019-11-08", "2020-08-31"), ("E", "2020-08-31", "2021-02-26"), ("F", "2021-02-26", "2021-10-08"),
           ("G", "2021-10-08", "2022-04-29")]


def px(code, a=None, b=None):
    s = sd[sd["code"] == code].set_index("date")["px"]
    return s.loc[a:b] if a or b else s


def shade_windows(ax, alpha=0.06):
    for i, (n, a, b) in enumerate(WINDOWS):
        ax.axvspan(pd.Timestamp(a), pd.Timestamp(b), color=PALETTE[i % 2 * 5], alpha=alpha if i % 2 else alpha * 1.8, lw=0)
        ax.text(pd.Timestamp(a) + (pd.Timestamp(b) - pd.Timestamp(a)) / 2, 0.98, n, transform=ax.get_xaxis_transform(),
                ha="center", va="top", fontsize=9, color="#555")


# 1 ----------------------------------------------------------------- cycle overview
fig, ax = plt.subplots(2, 1, figsize=(12, 7.5), sharex=True, gridspec_kw={"height_ratios": [1.1, 1]})
a, b = "2017-01-01", "2026-10-08"
s = nx.set_index("week_label")["全国"].loc[a:b]
ax[0].plot(s.index, s.values, color=C["spot"], lw=1.6, label="全国生猪均价（新牧网周度，元/公斤）")
ax[0].plot(nx.set_index("week_label")["华南"].loc[a:b], color=C["gd"], lw=0.9, alpha=0.6, label="华南")
ax[0].set_ylabel("元/公斤")
ax[0].legend(loc="upper right")
shade_windows(ax[0])
events = [("2018-08-03", "首例非瘟"), ("2019-09-06", "国办发〔2019〕44号\n稳产保供"), ("2021-09-19", "产能调控\n方案(4100万)"),
          ("2024-02-29", "修订\n(3900万)"), ("2025-07-23", "部长座谈会\n调减母猪"), ("2026-05-03", "2026方案\n(3750万)")]
for d, t in events:
    ax[0].axvline(pd.Timestamp(d), color="#999", lw=0.7, ls="--")
    ax[0].text(pd.Timestamp(d), 39, t, fontsize=7.5, color="#444", ha="left", va="top")
m = px("002714", a, b); w = px("300498", a, b); e = ew.set_index("date")["pig_ew"].loc[a:b]
ax[1].plot(m.index, m / m.iloc[0], color=C["muyuan"], lw=1.4, label="牧原（后复权，2017-01=1）")
ax[1].plot(w.index, w / w.iloc[0], color=C["wens"], lw=1.2, label="温氏")
ax[1].plot(e.index, e / e.iloc[0], color=C["small"], lw=1.2, label="猪企等权指数")
ax[1].set_yscale("log"); ax[1].set_ylabel("相对2017年初（对数）")
ax[1].legend(loc="upper left")
shade_windows(ax[1])
title(fig, "图1  2017—2026：猪价、猪股与关键政策", "阴影A—G为本文事件窗口；股价统一后复权收盘")
source(fig, "新牧网周度均价；腾讯/东方财富后复权日线；政策见policy_timeline/timeline.csv（官方原文）。")
save(fig, "c01_cycle_overview.png")

# 2 ----------------------------------------------------------------- phase-1 scatter
_cr = pd.read_csv(PROC / "two_phase_correlations.csv").set_index(["x", "y"])


def rho_txt(x, y):
    r = _cr.loc[(x, y)]
    return f"ρ={r['spearman_rho']:+.2f}，n={int(r['n'])}".replace("-", "−")


d = tp.dropna(subset=["mcap_per_head_2019asof_yuan", "r_B"])
fig, ax = plt.subplots(1, 2, figsize=(12, 4.8))
ax[0].scatter(d["mcap_per_head_2019asof_yuan"], d["r_B"] * 100, s=d["mcap_2018_12_28"] / 4 + 20, color=C["stock"], alpha=0.75)
for _, r in d.iterrows():
    ax[0].annotate(r["name"], (r["mcap_per_head_2019asof_yuan"], r["r_B"] * 100), fontsize=8.5, xytext=(4, 3), textcoords="offset points")
ax[0].set_xscale("log"); ax[0].set_xlabel("2018-12-28市值 / 截至2019-04-30已公告的2019年出栏计划（元/头，对数）")
ax[0].set_ylabel("B窗口涨幅 %（2018-12-28→2019-04-30）")
ax[0].set_title(f"每头“计划出栏”越便宜，第一阶段涨得越多\n（Spearman {rho_txt('mcap_per_head_2019asof_yuan', 'r_B')}）", fontsize=10.5)
d2 = tp.dropna(subset=["mcap_2018_12_28", "r_B"])
ax[1].scatter(d2["mcap_2018_12_28"], d2["r_B"] * 100, color=C["grey"], alpha=0.8)
for _, r in d2.iterrows():
    ax[1].annotate(r["name"], (r["mcap_2018_12_28"], r["r_B"] * 100), fontsize=8.5, xytext=(4, 3), textcoords="offset points")
ax[1].set_xscale("log"); ax[1].set_xlabel("2018-12-28市值（亿元，对数）")
ax[1].set_title(f"单看市值大小解释力弱（{rho_txt('mcap_2018_12_28', 'r_B')}）\n罗牛山、京基当时几乎没有生猪出栏，基本没涨", fontsize=10.5)
title(fig, "图2  第一阶段（预期与弹性）：市场按“每头计划出栏的价格”定价")
source(fig, "two_phase_panel.csv；计划为截至2019-04-30已公告版本（避免后视）；n小，ρ为描述性统计非显著性检验。")
save(fig, "c02_phase1_scatter.png")

# 3 ----------------------------------------------------------------- phase-2 scatter
tp["np1920_over_mcap"] = (tp["np_2019"] + tp["np_2020"]) / tp["mcap_2019_04_30"]
d = tp.dropna(subset=["np1920_over_mcap", "r_phase2_C_D_E"])
fig, ax = plt.subplots(figsize=(10, 5.2))
ax.scatter(d["np1920_over_mcap"], d["r_phase2_C_D_E"] * 100, s=60, color=C["wens"], alpha=0.8)
OFF3 = {"京基智农": (-8, 8, "right"), "天康": (5, -12, "left"), "唐人神": (-6, -12, "right"), "温氏": (5, 4, "left")}
for _, r in d.iterrows():
    dx, dy, ha = OFF3.get(r["name"], (4, 3, "left"))
    ax.annotate(r["name"], (r["np1920_over_mcap"], r["r_phase2_C_D_E"] * 100), fontsize=9, xytext=(dx, dy), textcoords="offset points", ha=ha)
ax.axhline(0, color="#999", lw=0.8)
ax.set_xlabel("2019+2020年归母净利润合计 / 2019-04-30市值")
ax.set_ylabel("第二阶段涨幅 %（2019-04-30→2021-02-26）")
ax.set_xlim(-0.1, 0.3)
title(fig, "图3  第二阶段（兑现与持续）：利润兑现相对市值越高，越能继续获得估值",
      f"Spearman {rho_txt('np19_20_over_mcap_0430', 'r_phase2_C_D_E')}；同期“2020年出栏较2018年增速”{rho_txt('growth_2020_vs_2018', 'r_phase2_C_D_E')}"
      "——市场主要奖励利润兑现，而不是规模增长（雏鹰−0.63在图外）")
source(fig, "two_phase_panel.csv；归母净利润为年报值；雏鹰农牧2019年退市，比值−0.63未画出。")
save(fig, "c03_phase2_scatter.png")

# 4 ----------------------------------------------------------------- double top small multiples
dt = pd.read_csv(PROC / "hist_double_top.csv", dtype={"code": str}) if (PROC / "hist_double_top.csv").exists() else None
names = {"002714": "牧原", "300498": "温氏", "002157": "正邦", "002124": "天邦", "000876": "新希望", "002567": "唐人神",
         "600975": "新五丰", "603363": "傲农", "002548": "金新农", "002385": "大北农", "002100": "天康", "000048": "京基",
         "000735": "罗牛山", "002840": "华统"}
fig, axs = plt.subplots(3, 5, figsize=(15, 8), sharex=True)
for ax, (code, nm) in zip(axs.flat, names.items()):
    s = px(code, "2018-07-01", "2021-12-31")
    s = s / s.iloc[0]
    ax.plot(s.index, s.values, color=C["stock"], lw=1)
    h1 = s.loc["2019-01-01":"2019-06-30"]; h2 = s.loc["2020-01-01":"2020-12-31"]; h3 = s.loc["2021-01-01":"2021-06-30"]
    ax.scatter([h1.idxmax()], [h1.max()], color=C["small"], zorder=3, s=18)
    ax.scatter([h2.idxmax()], [h2.max()], color=C["wens"], zorder=3, s=18)
    ratio = h2.max() / h1.max()
    ax.set_title(f"{nm}  2020高/2019H1高={ratio:.2f}", fontsize=9.5, color=C["wens"] if ratio > 1.1 else "#333")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y"))
    ax.tick_params(labelsize=7.5)
axs.flat[-1].axis("off")
axs.flat[-1].legend(handles=[Patch(color=C["small"], label="2019H1最高收盘"), Patch(color=C["wens"], label="2020年最高收盘")], loc="center")
title(fig, "图4  并非每只猪股都有“两波”：14家中只有6家在2020年创出新高",
      "牧原、新希望、京基、大北农、天康、正邦（比值>1.1）；傲农、新五丰、天邦、唐人神、金新农的收盘高点停在2019年4月")
source(fig, "后复权收盘，2018-07=1；hist_double_top.csv。")
save(fig, "c04_double_top.png")

# 5 ----------------------------------------------------------------- plan vs actual heatmap
pr = pd.read_csv(PROC / "plan_realization.csv", dtype={"code": str})
pr = pr[pr["year"].between(2019, 2022)]
hm = pr.pivot_table(index="name", columns="year", values="actual_vs_first")
order = ["牧原股份", "温氏股份", "正邦科技", "新希望", "天邦食品", "唐人神", "大北农", "天康生物", "傲农生物", "金新农", "新五丰", "华统股份", "京基智农"]
hm = hm.reindex([o for o in order if o in hm.index])
fig, ax = plt.subplots(figsize=(8.5, 6))
im = ax.imshow(hm.values, cmap="RdYlGn", vmin=0.3, vmax=1.2, aspect="auto")
ax.set_xticks(range(hm.shape[1])); ax.set_xticklabels(hm.columns)
ax.set_yticks(range(hm.shape[0])); ax.set_yticklabels(hm.index)
for i in range(hm.shape[0]):
    for j in range(hm.shape[1]):
        v = hm.values[i, j]
        if pd.notna(v):
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9)
ax.grid(False)
fig.colorbar(im, ax=ax, shrink=0.8, label="实际出栏 / 首次公告计划")
title(fig, "图5  计划与兑现：牧原几乎逐年兑现，多数公司首个计划只完成三到八成",
      "2021年温氏0.44、新希望0.33、天邦0.57、正邦0.60——第三波（E窗口）只有牧原上涨")
source(fig, "plan_realization.csv（首次计划=该年度最早公告版本；实际=月度简报12个月合计或年报值）。")
save(fig, "c05_plan_vs_actual.png")

# 6 ----------------------------------------------------------------- capex timing
fq = pd.read_csv(PROC / "fin_quarterly.csv", dtype={"code": str})
HOG = ["002714", "300498", "002157", "002124", "000876", "002567", "600975", "603363", "002548", "002385", "002100",
       "000048", "002840", "001201", "605296", "603477", "002477"]
fq = fq[fq["code"].isin(HOG) & (fq["report_date"] >= "2016-03-31") & (fq["report_date"] <= "2026-06-30")].sort_values(["code", "report_date"]).copy()
fq["y"] = fq["report_date"].str[:4]
fq["capex_q"] = fq.groupby(["code", "y"])["CONSTRUCT_LONG_ASSET"].diff()
first_q = fq["report_date"].str[5:] == "03-31"
fq.loc[first_q, "capex_q"] = fq.loc[first_q, "CONSTRUCT_LONG_ASSET"]
fq["report_date"] = pd.to_datetime(fq["report_date"])
agg = fq.groupby("report_date").apply(lambda g: pd.Series({
    "muyuan": g.loc[g["code"] == "002714", "capex_q"].sum() / 1e8,
    "others": g.loc[g["code"] != "002714", "capex_q"].sum() / 1e8}))
spot_q = nx.set_index("week_label")["全国"].resample("QE").mean()
agg["spot"] = spot_q.reindex(agg.index, method="nearest")
fig, ax = plt.subplots(figsize=(12, 5))
x = agg.index
ax.bar(x, agg["muyuan"], width=60, color=C["muyuan"], label="牧原 资本开支（季度，亿元）")
ax.bar(x, agg["others"], width=60, bottom=agg["muyuan"], color=C["small"], alpha=0.85, label="其他上市猪企合计（含已退市雏鹰）")
ax2 = ax.twinx()
ax2.plot(x, agg["spot"], color=C["spot"], lw=1.8, marker="o", ms=2.5, label="全国猪价季度均值（右轴）")
ax2.set_ylabel("元/公斤"); ax.set_ylabel("亿元")
ax.legend(loc="upper left"); ax2.legend(loc="upper right")
ax2.grid(False)
ax.annotate("2017-18低价期：牧原年资本开支50-63亿，\n2018年归母净利仅5.2亿（先建产能）", xy=(pd.Timestamp("2018-06-30"), 25), xytext=(pd.Timestamp("2016-06-30"), 260),
            fontsize=8.5, arrowprops=dict(arrowstyle="->", color="#666"))
title(fig, "图6  资本开支时点：牧原先在低价期建产能，最大一轮投入与行业一样落在高价期",
      "资本开支=购建固定资产、无形资产和其他长期资产支付的现金（单季=年内累计差分）；2023年亏损年牧原仍投入170亿")
source(fig, "东方财富季度财务数据（fin_quarterly.csv）；猪价为新牧网季度均值。")
save(fig, "c06_capex_timing.png")


# 7/8 --------------------------------------------------------------- lead-lag charts with specific contracts
def leadlag(a, b, contracts, fname, ttl, sub):
    fig, ax = plt.subplots(figsize=(12, 5.4))
    s = nx.set_index("week_label")["全国"].loc[a:b]
    ax.plot(s.index, s / s.iloc[0], color=C["spot"], lw=1.8, label="现货全国均价")
    for code, nm, col in [("002714", "牧原", C["muyuan"]), ("300498", "温氏", C["wens"])]:
        p = px(code, a, b)
        ax.plot(p.index, p / p.iloc[0], color=col, lw=1.3, label=nm + "（后复权收盘）")
    e = ew.set_index("date")["pig_ew"].loc[a:b]
    ax.plot(e.index, e / e.iloc[0], color=C["small"], lw=1.1, label="猪企等权指数")
    cols = [C["fut1"], C["fut2"], C["fut3"], C["fut4"], "#555"]
    for c, col in zip(contracts, cols):
        f = fut[(fut["contract"] == c) & fut["trade_date"].between(a, b)].set_index("trade_date")["close"]
        if len(f):
            base = s.iloc[0] * 1000
            ax.plot(f.index, f / base, color=col, lw=1, ls="--", label=f"{c} 收盘（以现货起点为1）")
            ax.scatter([f.idxmax()], [f.max() / base], color=col, s=14)
    ax.set_ylabel("相对窗口起点")
    ax.legend(ncol=2, fontsize=8, loc="upper right")
    title(fig, ttl, sub)
    source(fig, "期货为具体合约收盘价（非主连），点为窗口内最高收盘；股票后复权收盘；现货新牧网周度。")
    save(fig, fname)


leadlag("2020-10-01", "2021-12-31", ["LH2109", "LH2111", "LH2201"], "c07_leadlag_2021.png",
        "图7  2021年见顶：现货1月先见顶，牧原2月19日收盘见顶，期货并未领先",
        "LH2109盘中最高出现在上市首日2021-01-08（30,680），收盘高点02-22；期货此时仅有约1.5个月历史")
leadlag("2024-01-01", "2026-10-08", ["LH2409", "LH2501", "LH2605", "LH2701", "LH2709"], "c08_leadlag_recent.png",
        "图8  2024—2026：股票在2024年5月见顶，早于现货（8月）；2026年6月25日股票见底，2027年合约仍在创新低",
        "现货与LH0低点2026-04-13（8.88元）；LH2701—2707在2026-10-08仍处低位——股价与2027年期货出现背离")

# 9 ----------------------------------------------------------------- futures curve + forecast bias
cs = fut[(fut["trade_date"] == "2026-10-08") & (fut["contract"] != "LH0")].sort_values("delivery_month")
fe = pd.read_csv(PROC / "fut_forecast_error_summary.csv")
fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
ax[0].plot(cs["contract"], cs["settle"] / 1000, marker="o", color=C["fut1"])
for _, r in cs.iterrows():
    ax[0].annotate(f"{r['settle']/1000:.2f}", (r["contract"], r["settle"] / 1000), fontsize=8, xytext=(0, 6), textcoords="offset points", ha="center")
ax[0].axhline(18, color=C["wens"], ls="--", lw=1); ax[0].text(0, 18.2, "情景前提：2027年均18元", color=C["wens"], fontsize=9)
ax[0].set_ylim(9, 19.5); ax[0].set_ylabel("元/公斤（结算价）")
ax[0].set_title("2026-10-08期货曲线：2027年合约均值约12.5元", fontsize=10.5)
ax[1].bar(fe["months_before"].astype(str), fe["mean"] * 100, color=C["fut2"], alpha=0.8, label="平均偏差（期货/最终交割结算−1）")
ax[1].plot(fe["months_before"].astype(str), fe["mae"] * 100, color=C["dark"], marker="o", label="平均绝对误差")
ax[1].set_xlabel("距最后交易日（月）"); ax[1].set_ylabel("%")
ax[1].legend()
ax[1].set_title("历史上期货对远期现货平均“高估”，并非低估", fontsize=10.5)
title(fig, "图9  18元前提与期货曲线相差约44%：若兑现，是对当前定价的大幅正向意外")
source(fig, "fut_curve_snapshots / fut_forecast_error_summary（2021-2026全部已交割合约，具体合约口径）。")
save(fig, "c09_futures_curve_bias.png")

# 10 ---------------------------------------------------------------- Guangdong premium
g = nx.set_index("week_label")[["全国", "华南"]].dropna()
g["prem"] = g["华南"] - g["全国"]; g["prem_pct"] = g["华南"] / g["全国"] - 1
g = g.loc["2015-01-01":]
fig, ax = plt.subplots(figsize=(12, 4.6))
ax.fill_between(g.index, g["prem"], 0, color=C["gd"], alpha=0.35, label="华南−全国（元/公斤）")
ax2 = ax.twinx()
ax2.plot(g.index, g["prem_pct"] * 100, color=C["dark"], lw=0.8, label="溢价率 %（右轴）")
ax2.grid(False)
ax.axvspan(pd.Timestamp("2019-07-01"), pd.Timestamp("2021-04-30"), color="#f0d9b5", alpha=0.5)
ax.text(pd.Timestamp("2019-08-01"), g["prem"].max() * 0.92, "2019-07至2021-04 均值2.27元\n（调运限制+广东缺口）", fontsize=8.5)
ax.set_ylabel("元/公斤"); ax2.set_ylabel("%")
ax.legend(loc="upper left"); ax2.legend(loc="upper right")
title(fig, "图10  广东（华南）溢价：非瘟期间因“缺口×调运受阻”扩大，2023年后回落到约0.5—1元",
      "2026年上半年广东出栏同比+8.4%（全国+1.7%），广东能繁约为正常保有量109%：结构上不支持溢价再扩大（推断）")
source(fig, "新牧网区域周度（华南区）；广东数据见research/dongrui/gd_premium.md。")
save(fig, "c10_gd_premium.png")

# 11 ---------------------------------------------------------------- Dongrui price split & adv vs gap
ps_ = pd.DataFrame({"period": ["2019", "2020", "2021", "2022", "2025", "2026Q1"],
                    "export": [32.98, 45.96, 29.15, 25.90, 15.96, 13.60], "domestic": [20.58, 36.66, 19.98, 20.50, 14.14, 11.86],
                    "share": [74.5, 81.8, 80.7, 60.0, 28.6, 19.0]})
hist = pd.DataFrame({"year": ["2022", "2023", "2024", "2025", "2026H1"], "adv": [23.68 - 18.16, 17.13 - 14.42, 18.16 - 16.45, 14.66 - 13.48, 11.41 - 10.48],
                     "gap": [18.1 - 15.7, 17.8 - 15.0, 16.67 - 14.0, 14.6 - 12.0, 13.95 - 11.7]})
fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
xx = np.arange(len(ps_))
ax[0].bar(xx - 0.2, ps_["export"] - ps_["domestic"], width=0.4, color=C["gd"], label="出口−内销价差（元/公斤）")
ax0 = ax[0].twinx(); ax0.plot(xx, ps_["share"], color=C["dark"], marker="o", label="出口重量占比 %（右轴）"); ax0.grid(False)
ax[0].set_xticks(xx); ax[0].set_xticklabels(ps_["period"])
ax[0].legend(loc="upper right"); ax0.legend(loc="center right")
ax[0].set_title("供港溢价×占比同时收缩：2019-21年两者都高，2026Q1价差1.74元、占比约19%", fontsize=10)
xx = np.arange(len(hist))
ax[1].bar(xx - 0.2, hist["adv"], width=0.4, color=C["stock"], label="东瑞售价−牧原售价")
ax[1].bar(xx + 0.2, hist["gap"], width=0.4, color=C["wens"], label="东瑞完全成本−牧原完全成本")
for i, r in hist.iterrows():
    ax[1].text(i, max(r["adv"], r["gap"]) + 0.15, f"{r['adv']-r['gap']:+.2f}", ha="center", fontsize=9)
ax[1].set_xticks(xx); ax[1].set_xticklabels(hist["year"]); ax[1].legend()
ax[1].set_title("“价格优势>成本差距”只在2022年成立；2023年起由正转负", fontsize=10)
title(fig, "图11  东瑞：价格优势是否大于成本差距？")
source(fig, "东瑞招股书/问询回复/投资者关系记录；牧原月度简报与业绩说明会（2022 15.7、2023 15.0、2024约14、2025约12元/kg）；2025东瑞成本、2026H1牧原成本为推算约值。")
save(fig, "c11_dongrui.png")

# 12 ---------------------------------------------------------------- Muyuan sows & PBA flows
sw = pd.read_csv(ROOT / "research/muyuan/sows_quarterly.csv")
sw["period_end"] = pd.to_datetime(sw["period_end"])
sw = sw[sw["quality"].astype(str).str.startswith("精确") & sw["period_end"].dt.is_quarter_end].copy()
sw["sows_wan"] = pd.to_numeric(sw["sows_wan"], errors="coerce")
sw = sw.dropna(subset=["sows_wan"])
ba = pd.read_csv(ROOT / "research/muyuan/bio_assets.csv")
ba = ba[(ba["measure"] == "原值") & ba["item"].str.contains("合计") & ba["report"].str.match(r"^\d{4}(半年报|年报)$")].copy()
ba["year"] = ba["report"].str[:4].astype(int)
ba["kind"] = np.where(ba["report"].str.contains("半年报"), "H1", "FY")
half = []
for y, g in ba.groupby("year"):
    h1 = g[g["kind"] == "H1"]; fy = g[g["kind"] == "FY"]
    if len(h1):
        half.append((pd.Timestamp(y, 6, 30), h1["additions_transfer"].iloc[0], h1["disposals"].iloc[0]))
    if len(h1) and len(fy):
        half.append((pd.Timestamp(y, 12, 31), fy["additions_transfer"].iloc[0] - h1["additions_transfer"].iloc[0],
                     fy["disposals"].iloc[0] - h1["disposals"].iloc[0]))
hf = pd.DataFrame(half, columns=["end", "add", "disp"]).dropna()
hf = hf[hf["end"] >= "2019-01-01"].sort_values("end")
fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
ax[0].plot(sw["period_end"], sw["sows_wan"], marker="o", ms=3, color=C["muyuan"], label="能繁母猪（万头，季末）")
ax0 = ax[0].twinx()
s = nx.set_index("week_label")["全国"].loc["2019-01-01":]
ax0.plot(s.index, s.values, color=C["spot"], lw=0.8, alpha=0.7, label="全国猪价（右轴）"); ax0.grid(False)
ax[0].legend(loc="upper left"); ax0.legend(loc="upper right")
ax[0].set_title("能繁母猪：2022Q2、2025H2—2026在调减；2023—2024低价期反而增至351万", fontsize=10)
xx = np.arange(len(hf))
ax[1].bar(xx - 0.2, hf["add"], width=0.4, color=C["fut3"], label="自行培育增加（原值，亿元）")
ax[1].bar(xx + 0.2, hf["disp"], width=0.4, color=C["grey"], label="处置减少（淘汰）")
ax[1].set_xticks(xx); ax[1].set_xticklabels([f"{d.year}{'H1' if d.month == 6 else 'H2'}" for d in hf["end"]], rotation=60, fontsize=8)
for i, r in hf.reset_index().iterrows():
    ax[1].text(i, max(r["add"], r["disp"]) + 1, f"{r['add']/r['disp']:.2f}", ha="center", fontsize=7.5)
ax[1].legend(fontsize=8)
ax[1].set_title("生产性生物资产：2026H1增加/处置=1.53，为2019年以来最高之一", fontsize=10)
title(fig, "图12  牧原：账面生物资产增加≠净扩产——同期能繁母猪数在下降",
      "增加额含后备母猪培育成本；能繁从323.2（2025末）降至311.3（2026-06），计划9月底<300万头。两种解读见正文")
source(fig, "牧原定期报告附注（生产性生物资产原值变动）、月度销售简报（能繁母猪）；research/muyuan/。")
save(fig, "c12_muyuan_sows_pba.png")

# 13 ---------------------------------------------------------------- screen quadrant
res = pd.read_csv(PROC / "model_results.csv", dtype={"code": str})
inp = pd.read_csv(PROC / "model_company_inputs.csv", dtype={"code": str})
scn = pd.read_csv(PROC / "screen_snapshot.csv", dtype={"code": str})
b = res[(res["path"] == "P1 全年持平") & (res["case"] == "base")].merge(scn[["code", "ev_yi", "debt_ratio", "cash_to_st_debt"]], on="code")
b["ev_per_head"] = b["ev_yi"] * 1e8 / (b["fattening_wan"] * 1e4)
fig, ax = plt.subplots(figsize=(11, 6.5))
risk = {"002124": "存续风险", "002548": "高杠杆", "600975": "高杠杆(租赁)", "603363": "重整后"}
for _, r in b.iterrows():
    y = r["earnings_yield"] * 100 if pd.notna(r["earnings_yield"]) else None
    col = C["wens"] if r["code"] in risk else C["stock"]
    if y is None:
        k = {"002840": 0, "600975": 1, "002157": 2}.get(r["code"], 0)
        ax.scatter(r["ev_per_head"], 2, marker="x", color=C["grey"], s=50)
        ax.annotate(r["name"] + "（成本未披露）", (r["ev_per_head"], 2), fontsize=8, xytext=(4, 3 + 11 * k), textcoords="offset points", color=C["grey"])
        continue
    ax.scatter(r["ev_per_head"], y, s=max(r["mcap_yi"] / 6, 25), color=col, alpha=0.7)
    ax.annotate(r["name"] + (f"（{risk[r['code']]}）" if r["code"] in risk else ""), (r["ev_per_head"], y), fontsize=8.5, xytext=(5, 3), textcoords="offset points")
ax.set_xlabel("EV / 2027年基准育肥出栏（元/头）  ←越便宜")
ax.set_ylabel("18元情景归母利润 / 当前市值 %  ↑弹性越大")
ax.axvline(b["ev_per_head"].median(), color="#aaa", ls=":"); ax.axhline(b["earnings_yield"].median() * 100, color="#aaa", ls=":")
title(fig, "图13  筛选象限：弹性（情景利润/市值）× 债务调整后的每头估值",
      "气泡=市值；红色=存续或杠杆约束。弹性高的左上角公司，要先过“活到2027年”这一关")
source(fig, "screen_snapshot.csv、model_results.csv（P1全年18元、基准量与成本）；EV=市值+有息负债−货币资金（2026-06-30）。")
save(fig, "c13_screen_quadrant.png")

# 14 ---------------------------------------------------------------- scenario P/E and implied price
val = pd.read_csv(PROC / "model_valuation_lens.csv", dtype={"code": str})
p1 = res[res["path"] == "P1 全年持平"].pivot_table(index="name", columns="case", values="scenario_pe")
p1 = p1.dropna().sort_values("base")
fig, ax = plt.subplots(1, 2, figsize=(13, 5))
yy = np.arange(len(p1))
ax[0].hlines(yy, p1["bull"], p1["bear"], color="#bbb", lw=3)
ax[0].scatter(p1["base"], yy, color=C["stock"], zorder=3, label="基准")
ax[0].scatter(p1["bear"], yy, color=C["wens"], s=12, label="熊（量/成本差）")
ax[0].scatter(p1["bull"], yy, color=C["fut3"], s=12, label="牛")
ax[0].set_yticks(yy); ax[0].set_yticklabels(p1.index); ax[0].set_xlabel("当前市值 / 2027年18元情景归母利润（倍）")
ax[0].legend(); ax[0].set_title("18元情景市盈率普遍2—7倍（历史周期顶点约15—17倍）", fontsize=10)
v = val.set_index("name").sort_values("implied_national_px_10x")
yy = np.arange(len(v))
ax[1].barh(yy, v["implied_national_px_10x"], color=C["spot"], alpha=0.85, label="当前市值=10倍利润所需的长期全国均价")
ax[1].scatter(v["implied_national_px_15x"], yy, color=C["dark"], s=14, label="15倍")
ax[1].axvline(12.5, color=C["fut1"], ls="--", lw=1); ax[1].text(12.55, len(v) - 0.6, "2027期货均值12.5", color=C["fut1"], fontsize=8.5)
ax[1].axvline(18, color=C["wens"], ls="--", lw=1); ax[1].text(17.2, len(v) - 0.6, "情景18", color=C["wens"], fontsize=8.5)
ax[1].set_yticks(yy); ax[1].set_yticklabels(v.index); ax[1].set_xlim(10, 19)
ax[1].legend(loc="lower right", fontsize=8); ax[1].set_title("当前股价隐含的“正常化猪价”约13—16元", fontsize=10)
title(fig, "图14  18元情景的估值含义：市场在为“长期13—16元”定价，而不是为一年18元定价")
source(fig, "model_results.csv、model_valuation_lens.csv；其他业务未建模，饲料/禽类占比高的公司隐含价格偏高。")
save(fig, "c14_scenario_pe.png")

# 15 ---------------------------------------------------------------- decomposition
dec = pd.read_csv(PROC / "model_decomposition.csv", dtype={"code": str})
dec = dec[dec["code"] != "002714"].copy() if False else dec.copy()
dec["total"] = dec["hog_profit_2027_yi"] - dec["hog_profit_2026_yi"]
dec = dec.sort_values("total")
comp = [("contrib_national_price_yi", "全国价格", C["spot"]), ("contrib_regional_premium_yi", "区域/渠道溢价", C["gd"]),
        ("contrib_cost_yi", "成本下降", C["fut3"]), ("contrib_volume_yi", "出栏量", C["fut1"])]
fig, axs = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1, 2.2]})
for ax, sub in zip(axs, [dec[dec["code"].isin(["002714", "300498", "000876"])], dec[~dec["code"].isin(["002714", "300498", "000876"])]]):
    yy = np.arange(len(sub))
    left_pos = np.zeros(len(sub)); left_neg = np.zeros(len(sub))
    for colname, lab, col in comp:
        vals = sub[colname].values
        if colname == "contrib_regional_premium_yi":
            vals = vals + sub["contrib_channel_premium_yi"].values
        pos = np.where(vals > 0, vals, 0); neg = np.where(vals < 0, vals, 0)
        ax.barh(yy, pos, left=left_pos, color=col, label=lab); left_pos += pos
        ax.barh(yy, neg, left=left_neg, color=col); left_neg += neg
    ax.set_yticks(yy); ax.set_yticklabels(sub["name"]); ax.axvline(0, color="#666", lw=0.8)
    ax.set_xlabel("养殖利润变化（亿元，2026年当前状态→2027年18元基准）")
axs[1].legend(loc="lower right")
title(fig, "图15  18元情景利润增量拆分：全国价格贡献中位数约99%（东瑞83%、京基89%最低），成本和溢价是区分公司的“第二变量”",
      "中点拆分Δ(V·m)=ΔV·m̄+V̄·Δm；东瑞的溢价含内销溢价与供港渠道溢价；融资影响体现在成本（利息/公斤见Excel）与稀释")
source(fig, "model_decomposition.csv；2026状态=最近年化出栏、2026年7-9月全国均价、最新披露成本。")
save(fig, "c15_decomposition.png")

# 16 ---------------------------------------------------------------- historical peak P/E
hp = pd.read_csv(PROC / "hist_peak_pe.csv")
fig, ax = plt.subplots(figsize=(11, 4.6))
cyc = ["ASF", "2022", "2024"]
for i, c in enumerate(cyc):
    d = hp[(hp["cycle"] == c) & hp["pe_on_peak_year_np"].notna()]
    jitter = np.linspace(-0.25, 0.25, len(d))
    ax.scatter(np.full(len(d), i) + jitter, d["pe_on_peak_year_np"].clip(upper=120), color=C["grey"], s=20, alpha=0.7)
    for nm, col, dy in [("牧原", C["muyuan"], -13), ("温氏", C["wens"], 9)]:
        r = d[d["name"] == nm]
        if len(r):
            ax.scatter([i], r["pe_on_peak_year_np"], color=col, s=80, zorder=3)
            ax.annotate(f"{nm} {r['pe_on_peak_year_np'].iloc[0]:.1f}x", (i, r["pe_on_peak_year_np"].iloc[0]), xytext=(-12, dy), textcoords="offset points",
                        fontsize=9, color=col, ha="right", fontweight="bold")
    ax.text(i, 125, f"中位数 {d['pe_on_peak_year_np'].median():.1f}x", ha="center", fontsize=9)
ax.set_xticks(range(3)); ax.set_xticklabels(["非瘟周期（2018-21）", "2022小周期", "2024小周期"])
ax.set_ylabel("市值峰值 / 峰值年度归母净利润（倍，截断于120）"); ax.set_ylim(0, 135)
title(fig, "图16  周期顶点市场愿付的倍数：牧原、温氏在非瘟和2024年顶点约15—17倍（2022年26—32倍）",
      "倍数=市值峰值÷周期内最高年度归母净利润；非瘟周期中位数18.7倍；小周期里小盘股利润太薄，倍数失真（交易的是“期权”而非已兑现利润）")
source(fig, "hist_peak_pe.csv（市值=不复权收盘×总股本；窗口内市值最高日）。")
save(fig, "c16_hist_peak_pe.png")
print("charts done")
