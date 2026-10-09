# AlphaNotes

可核实的市场研究笔记。每份报告以"能被推翻"为第一标准：所有数字标注来源与截止日期，公告数据、研报测算、本报告推演三者分开标注，结论落在可观测的跟踪阈值上而不是目标价。

## 报告索引

| 主题 | 标的 | 报告 | 交互工具 | 数据截至 |
| --- | --- | --- | --- | --- |
| 猪周期估值推演的辩证复核 | 牧原 002714 · 东瑞 001201 · 神农 605296 | [analysis.md](reports/hog-cycle/analysis.md) · [视频交叉比对](reports/hog-cycle/video-crosscheck.md) | [估值沙盘](reports/hog-cycle/sandbox.html)（含东瑞模式与广东溢价滑杆） | 2026-10-03 |
| 非瘟超级周期复盘 × 2027 情景与上市猪企筛选 | 牧原 002714 · 温氏 300498 · 东瑞 001201 等 17 家 A 股，德康、中粮家佳康单列 | [analysis.html](reports/hog-cycle-asf-2027/analysis.html) · [目录说明](reports/hog-cycle-asf-2027/README.md) · Issue 答复：[四川去化与补贴](reports/hog-cycle-asf-2027/issues/01-sichuan-destocking.md)、[东瑞低市净率](reports/hog-cycle-asf-2027/issues/02-dongrui-pb.md)、[四位雪球作者观点梳理](reports/hog-cycle-asf-2027/issues/03-xueqiu-authors.md) | [2027 情景模型](reports/hog-cycle-asf-2027/model.xlsx)（Excel，可切换价格路径与情景） | 2026-10-08 |

每个主题目录下至少有三个文件：`source.md` 是原始推演记录，`analysis.md` 是核实与复核后的报告，`sandbox.html` 是可调参数的交互工具。保留 `source.md` 是为了让结论的演化过程可追溯——包括被推翻的部分。

数据驱动的主题结构不同，例如 `hog-cycle-asf-2027`：`analysis.html` 是图表内嵌的单文件报告，`model.xlsx` 是带公式的情景模型，另附 `data/`、`research/`、`scripts/` 供复算，目录下的 `README.md` 写明重跑顺序。第三方原始行情序列只存本地，由脚本重新生成。

研究过程中引入的外部材料（视频、研报等）单独写成比对文档，如 `video-crosscheck.md`，逐条标注哪些与已核实数据一致、哪些提供新角度、哪些站不住。视频转写原文只存本地（`transcripts/`），不随仓库公开。

## 写作约定

**数据可信度四级分类。** 每份报告的附录都按这个标准给数据分级：

| 级别 | 含义 | 使用方式 |
| --- | --- | --- |
| A | 公司公告、交易所、政府统计原文 | 可直接引用 |
| B | 管理层口头表述（业绩会、调研、互动平台） | 注明非审计数据与模糊区间 |
| C | 媒体转述、券商测算、本报告推演 | 打折使用，标明推演前提 |
| D | 明确未找到 | 写明"未找到"，不编造 |

**口径必须锁定。** 同一指标常有多套并行口径——生猪价格至少有农业农村部集贸、统计局旬报、22 省市、卓创外三元、Mysteel 五套，同日差异可达 0.3–1.0 元/kg。跨年度、跨机构比较前先统一口径，否则趋势结论可能纯粹是口径切换造成的。

**不下买卖结论。** 报告只回答两个问题：某个观点要成立需要什么条件，以及这些条件是否正在发生。给出可证伪的跟踪指标与触发阈值。

**对被批评的观点记分。** 批判性复核要同时标出对方说对的地方。反例、翻案和自我更正写进正文，不藏在脚注里。猪周期那篇里有三处作者自我更正和一份"对方八条疑点的记分卡"，就是这条约定的产物。

## 交互工具

`sandbox.html` 一类的文件是**零依赖单文件页面**——纯 vanilla JS 加手写 SVG，不引用任何 CDN，不需要构建步骤。因此它同时支持三种用法：直接双击本地打开、通过 GitHub Pages 发布、或者当成单个附件发给别人。

发布地址：

```
https://alphacatalyst.github.io/AlphaNotes/reports/hog-cycle/sandbox.html
```

## 本地预览

Markdown 直接在 GitHub 上读即可。想在本地完整预览 Pages 站点（含主题样式）：

```bash
bundle exec jekyll serve   # 需先安装 github-pages gem
```

只想看交互工具的话，双击 `sandbox.html` 就行，不需要起服务。

## 免责声明

全部内容为研究记录与方法论演示，不构成投资建议。报告中的情景假设、概率赋值和敏感性测算均为特定时点下的推演，不代表对未来的预测。
