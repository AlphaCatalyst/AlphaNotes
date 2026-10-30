# 非瘟超级周期复盘 × 2027 情景与上市猪企筛选

> 报告：[analysis.html](analysis.html)（单文件，图表内嵌；[在线阅读](https://alphacatalyst.github.io/AlphaNotes/reports/hog-cycle-asf-2027/analysis.html)）｜ 情景模型：[model.xlsx](model.xlsx)
> 数据截止：股价 2026-10-08 收盘；资产负债表 2026-06-30；公司经营数据至 2026 年 8—9 月简报；能繁母猪至 2026-06；期货为 2026-10-08 结算

报告要回答三个问题：市场最初为什么愿意为某家猪企的弹性买单，后来凭什么继续给它估值，哪一步没有兑现会让整个逻辑失效。

## 核心结论

1. **第一阶段买的是“每头便宜”，不是“市值小”。** 2018-12-28 至 2019-04-30，在已公告 2019 年出栏计划的 10 家猪企中，涨幅与“市值 ÷ 截至当时最新计划出栏”的 Spearman 相关为 −0.95；与市值（−0.28）、计划增速（−0.04）、负债率（−0.01）几乎无关。
2. **第二阶段奖励利润兑现，不奖励头数兑现。** 2019-04-30 至 2021-02-26 的涨幅与“2019—2020 年归母净利润 ÷ 起点市值”的相关为 +0.64（n=14），与出栏增速只有 +0.25。牧原 2020、2021 年出栏分别完成首个计划的 97%、99%，期间涨 200%；温氏 2020 年只完成 33%，跌 40%。
3. **逻辑按顺序失效。** 先是计划没有变成出栏（2020 年温氏、唐人神、大北农只兑现首个计划的约三分之一）；再是出栏靠高价补栏和举债换来（正邦、傲农 2020 年都完成了九成以上的出栏计划，后来都进入重整）；最后是下行期融资断裂。
4. **18 元是给定的情景前提，不是预测。** 按 2026-10-08 结算价折算，2027 年期货均价约 12.5 元；按 10 倍市盈率，当前市值对应的长期全国均价约 13—16 元。一个 18 元年份比 14 元年份多出的养殖利润，约为当前市值的 10%—48%。

各公司的证据、兑现条件和证伪信号见报告第 5—7 节。报告只给条件和跟踪信号，不给买卖结论。

## Issue 答复

| Issue | 答复 | 结论 |
| --- | --- | --- |
| [#1 四川产能去化是否慢于全国，地方补贴起了多大作用](https://github.com/AlphaCatalyst/AlphaNotes/issues/1) | [issues/01-sichuan-destocking.md](issues/01-sichuan-destocking.md) | 本轮调减窗口里四川确实慢：2025Q3 以来四川能繁母猪 −2.6%，全国扣除四川 −6.7%；从 2023Q2 算起两者接近。50 元补贴出台晚、金额小，不是主因。四川多保留的母猪约占全国 0.4%，对 2027 年全国猪价的影响约 1%—4% |
| [#2 东瑞的低市净率是否意味着被低估](https://github.com/AlphaCatalyst/AlphaNotes/issues/2) | [issues/02-dongrui-pb.md](issues/02-dongrui-pb.md) | 低市净率只在同行横比时成立；现价隐含 2027 年全国猪价约 13.9 元，与牧原相当。净资产主要是租地上的猪舍，不是硬底。企业价值与重置成本大致相当，回报来自 2027 年价格和降本两个期权 |
| [#3 四位雪球作者近半年的猪周期观点：周期演绎、预期差、时间节点与相关标的](https://github.com/AlphaCatalyst/AlphaNotes/issues/3) | [issues/03-xueqiu-authors.md](issues/03-xueqiu-authors.md) | 四人都认为去化在加速、2027 年前后转强，牧原是首选或基准，但依据多来自同一批官方数据、第三方数据和政策传闻，不是独立证据。最大分歧是 2027 年价格：豆区约 16 元，期货约 12.2 元，当前估值隐含约 13—16 元，差别主要来自效率和滞后假设。第一个检验点是 10-19 统计局的三季度能繁数据 |
| [#4 广东猪价溢价是长期优势还是阶段现象，东瑞能兑现多少](https://github.com/AlphaCatalyst/AlphaNotes/issues/4) | [issues/04-guangdong-premium.md](issues/04-guangdong-premium.md) | 同源口径下广东常态只比全国高 0.3 元（非瘟前）至 0.6—0.8 元（2023 年以来，调运限制仍在）；"2022、2024 年贵 2 元以上"不成立。非瘟期以外价差与全国价几乎无关，当前也不算偏低。东瑞内销拿不全广东溢价，主要靠供港，且被扩产稀释。全国 18 元时东瑞溢价约 0.64—1.03 元/公斤，Issue #2 的 7.8%（1.40 元）偏高，年赚 10 亿约需全国 17.1—17.5 元；逻辑不依赖溢价扩大，关键是成本 |
| [#5 猪企股价与猪价何时同步、何时领先，行情是否更容易在淡季启动](https://github.com/AlphaCatalyst/AlphaNotes/issues/5) | [issues/05-stock-hog-timing.md](issues/05-stock-hog-timing.md) | 没有固定的提前月数：股价超额收益见底常晚于现货，非瘟后见顶都早于现货 12—27 周。股价底部多在淡季（7 轮中 6 轮），但淡季里的启动大多失败，主升多在旺季，"淡季启动"不是可重复的规律。2026 年没有回到"跟随现货"：6-26 以来超额 +22%，现货弱于季节常态、远月期货跌约 20%，股价主要响应政策和统计数据。检验点是 2027 年春节后现货季节性新低时股价能否守住 6 月低点 |
| [#6 10 月猪价再探是否与春季补栏、集中出栏有关，如何判断见底窗口](https://github.com/AlphaCatalyst/AlphaNotes/issues/6) | [issues/06-autumn-dip.md](issues/06-autumn-dip.md) | 10 月没有跌破 4 月低点，各全国口径仍高 13%—17%；9 月下旬以来约 4% 的跌幅在往年 10 月范围内，由节后积压、夏季二育出栏、散户大猪和冻品出库触发。春季补栏只解释外购育肥这一条的时点，4 月仔猪/生猪比价低于常年，不是额外的抄底潮。10 元左右的价格说明过剩还没扭转，来源是一年前偏高的母猪和每头产出提高；按滞后母猪推算，出栏同比要到 2027 年二季度才明显下降（约 −4% 到 −5%），基准见底窗口是 2027 年 2—4 月。第一个检验是 10 月下旬统计局三季度出栏（推算基准 +1.3%） |
| [#7 能否用母猪料、仔猪料和育肥料数据追踪猪企有效产能，验证行业去化与未来出栏](https://github.com/AlphaCatalyst/AlphaNotes/issues/7) | [issues/07-feed-tracking.md](issues/07-feed-tracking.md) | 饲料能给方向，不能直接换算头数：季度猪料领先统计局出栏约一个季度（相关 0.91），但每年有 −5 到 +20 个百分点的偏差，来自自配料转工业料、一体化扩张、产品形态和体重。分阶段的先后顺序可靠（8 个窗口里仔猪料都弱于育肥料），幅度要折全价才可用：2026 年 7 月折全价母猪料 −5.8%、仔猪料 −9.8%，与能繁母猪 −6.5% 一致，实物口径则仍像扩张。四季度起出栏同比转负的方向较明确，约 −0.4% 到 −5%，中心 −1% 到 −2%；给不出价格见底日期。公司只能用年报做年度校验（东瑞、牧原每出栏一头 303—406 公斤），温氏不可见 |
| [#8 生猪与养殖板块三季度有哪些股票新进了机构？新进资金量有多少，其中多少是主动买入？](https://github.com/AlphaCatalyst/AlphaNotes/issues/8) | [issues/08-q3-institutions.md](issues/08-q3-institutions.md) | 两个板块 14 只股票三季度新进了机构：生猪 8 只、禽类及其他养殖 6 只。新进机构持股市值约 32.4 亿元，能确认是三季度新买入的至少约 8.5 亿元；牧原一家占 21.3 亿元和 5.2 亿元，最大一笔是社保一一四组合（至少买入 1,217 万股，约 5.2 亿元）。差额主要是被动 ETF（9.2 亿元，国泰畜牧 ETF 在牧原按份额推算只净买入约 1 亿元）和无法确认买入时点的社保持仓；QFII 自营账户更像对冲持仓，ST 龙大的银行股东来自司法划转抵债。巨星农牧、京基智农、金新农、罗牛山 4 只股票前十大流通股东里的机构确定是净卖出。北向增持养殖股、减持饲料和肉制品股。新希望等 4 家截至 10-30 中午未披露 |

#1、#2 的股价截至 2026-10-09 收盘，#3 截至 2026-10-08 收盘；#4 的分省价格截至 2026-10-08；#5 的股价、指数和期货截至 2026-10-13 收盘，现货截至 2026-10-12；#6 的新牧网现货截至 2026-10-13（省级 10-14），农业农村部周度价格截至 10-08 采集，期货截至 10-13 结算；#7 的中国饲料工业协会月报截至 2026 年 8 月数据（9-18 发布），分阶段折全价截至 7 月（8-24 发布），公司数据截至 2026 年半年报；#8 的股东名单为 2026 年三季报（取到 10-29 晚，44 家中 40 家已披露）对比半年报，金额按 9-30 收盘价折算。数据和脚本在 `data/processed/issues/`、`scripts/issues/`、`research/sichuan_destocking/`、`research/replacement_cost/`、`research/xueqiu_authors/`、`research/autumn_dip/`、`research/feed_tracking/`。

## 文件

| 路径 | 内容 |
| --- | --- |
| `analysis.html` | 合并报告，结论先行。每条论断标注 事实 / 目标 / 假设 / 推断 / 统计 / 模型，与 A—D 可信度分级的对应见报告 9.5 |
| `model.xlsx` | 2027 情景模型。`Paths!B12` 选价格路径（1—5），`Paths!B13` 选情景（1 熊 / 2 基准 / 3 牛）；Quarterly、Summary、Dongrui、Decomposition、Sensitivity 为公式；QA 表核对 Python 结果 |
| `charts/` | 报告中的 16 张图；`i05_*.png` 为 Issue #5 的 6 张图，`i06_*.png` 为 Issue #6 的 5 张图，`i07_*.png` 为 Issue #7 的 5 张图 |
| `data/processed/` | 分析用的处理后数据：季度财务、月度经营、农业农村部与统计局数据、窗口收益、峰值、两阶段面板、拐点、筛选快照、情景结果等 |
| `research/` | 子研究：政策时间线、历年计划与兑现、东瑞、牧原、各公司当前经营、四川去化与补贴、猪场重置成本与进入壁垒、四位雪球作者的帖子索引与观点还原底稿、10 月猪价再探的第三方现场信号、饲料追踪产能的数据源清单、月度跟踪表与公司饲料口径。每条事实带原文链接和摘录 |
| `issues/` | GitHub Issue 的答复，见上节 |
| `scripts/` | 抓取、分析、模型、图表和报告脚本；`scripts/issues/` 为 Issue 答复的计算 |

## 未公开的数据

以下文件属于第三方原始序列，只存本地、不随仓库公开，运行抓取脚本可重新生成：股价与指数日线（`stock_daily.csv`、`index_daily.csv`、中证全指与中证畜牧养殖 `csi_index_daily.csv`）、大商所生猪期货具体合约日线（`futures_lh_daily.csv`、`fut_main_mapped.csv`）、新牧网现货价格（`nxin_*.csv`）、中国养猪网分省报价（`zhuwang_*.csv`）、月度销售公告全文（`sales_ann_text.csv`）。原始下载缓存 `data/raw/`（约 3 GB）同样只存本地。各子研究的原文缓存和抓取脚本（`research/*/_raw/`、`research/*/_work/`）也只存本地；CSV 里的摘录已逐字核验，可以按链接回查原文。雪球帖子的全文和配图同样只存本地，公开的只有索引、摘要和不超过 40 字的短引文。作为起点的旧报告《非洲猪瘟猪周期复盘》未收录。

## 重跑顺序

只基于仓库内的数据无法完整重跑，需要先执行第 1 步生成上面的本地数据。

1. 抓取与清洗：`fetch_stocks.py` → `build_stock_daily.py`；`fetch_csi_index.py`；`fetch_futures.py`；`industry/run_all.sh`（新牧网、农业农村部（含 2003—2015 年集贸市场价格月报、周报）、统计局、广东、中国养猪网、中国饲料工业协会）→ `process_spot.py`；`fetch_fin.py` → `build_fin.py`；`fetch_sales_ann.py` → `parse_sales.py`；`policy_fetch.py` → `build_policy_timeline.py`、`build_asf_monthly.py`
2. 历史分析：`analyze_history.py`（窗口收益、峰值）→ `analyze_two_phase.py`（两阶段检验、计划兑现）→ `analyze_leadlag.py`、`analyze_futures.py`、`analyze_expansion.py`
3. 当前筛选与模型：`build_screen.py` → `model_2027.py` → `analyze_current.py`（顶点倍数、双顶、2026-06-25 以来的反弹面板）
4. 输出：`make_charts.py`（写入 `charts/`）→ `build_excel.py`（重新调用模型，写入 `model.xlsx`）→ `build_report.py`（写入 `analysis.html`）
5. Issue 答复：`issues/dongrui_pb.py`（另取 2026-10-09 收盘行情快照）、`issues/sichuan.py`、`issues/xueqiu_checks.py`、`issues/gd_premium.py`（在 `dongrui_pb.py` 之后运行）、`issues/stock_hog_timing.py`（同时写入 `charts/i05_*.png`）、`issues/autumn_dip.py`（同时写入 `charts/i06_*.png`；新牧网周度价格读 `industry/nxin_prices.py` 写的 `nxin_region_weekly.csv`，`process_spot.py` 会用旧缓存覆盖这个文件，运行它之后要再运行一次 `industry/nxin_prices.py`）、`issues/feed_tracking.py`（读 `industry/cfia_feed.py` 生成的 `cfia_*.csv`，同时写入 `charts/i07_*.png`）、`issues/q3_institutions.py`（带 `fetch` 参数时先用腾讯自选股 `westock-data` 命令行抓取股东名单、定期报告、行情和 ETF 份额，缓存到 `research/q3_institutions/_raw/`；只使用 2026-10-29 以前发布的报告），结果写入 `data/processed/issues/`；`issues/xueqiu_index.py` 需要本地的雪球抓取库，生成 `research/xueqiu_authors/articles.csv`

依赖：Python 3、pandas、numpy、matplotlib、openpyxl、pypdf；Excel 公式核对用 `formulas`。

## 口径要点

- 股价统一后复权（腾讯为主、东方财富补充）；市值 = 不复权收盘 × 当季股本；牧原含 H 股（港元按 0.8585 折算）。
- 期货 2021-01-08 才上市，2018—2020 年不构造期货；先后判断用具体合约，主力连续只作示意。
- EV = 市值 + 短借 + 一年内到期 + 长借 + 债券 + 租赁负债 − 货币资金（正邦另加重整留债 21.57 亿元）。
- 情景利润只含生猪养殖（与仔猪），饲料、禽类、屠宰等其他业务未建模；养殖价差 ≠ 归母净利润 ≠ 股价涨幅。
- 两阶段检验样本 n=10—14，Spearman 相关只作描述。
