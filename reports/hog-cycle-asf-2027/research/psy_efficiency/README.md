# PSY 与效率：说法清单

本目录是 [Issue #11 答复](../../issues/11-psy-efficiency.md)的材料层。议题问的是：猪周期底部的高 PSY 能否持续，"PSY 提升约 10%""长期年均约 1%"分别是什么口径，效率提升能抵消多少母猪去化。材料截止 2026-10。

## 材料范围

- **官方与研究人员：** 农业农村部（经媒体转述）、中国农科院北京畜牧兽医研究所研究人员、全国政协委员的公开表述。
- **行业平台与咨询机构：** 微猪科技《2025猪业数据年报》（中国养猪网转载）、涌益咨询访谈纪要、卓创资讯、Agritoken。
- **券商、期货公司与媒体：** 南华期货周报、开源证券行业周报、格隆汇、同花顺专题、新浪自媒体文章。

只收录带具体数字或具体机制的说法；同一来源的重复转载只留一条。

## 文件

| 文件 | 内容 |
| --- | --- |
| `claims.csv` | 24 条：`P` 开头为 PSY/MSY 数字（17 条），`M` 为机制描述（5 条），`F` 为出栏预测（2 条）。每条记录日期、来源、说话人、范围（全国、监测样本、集团）、指标、起止年份和数值、口径说明、链接、40 字以内的逐字摘录和可信度等级 |

`basis` 列写明数字是单年变化、多年累计还是水平，以及换算时的取值（例如"24 头以上"取 24）。累计变化的年化在 `scripts/issues/psy_efficiency.py` 中计算，结果在 `data/processed/issues/psy_claims.csv`。

## 等级

- **B：** 农业农村部的说法经媒体转述（P03、P04）。
- **C：** 其余各条。行业平台和咨询机构的样本范围、权重未公开，媒体和自媒体常不写起点年份或范围。

## 重跑

在专题目录 `reports/hog-cycle-asf-2027/` 下，先运行 `scripts/issues/autumn_dip.py`、`scripts/issues/feed_tracking.py`、`scripts/issues/xueqiu_checks.py`，再运行：

```bash
python3 scripts/issues/psy_efficiency.py   # 生成 data/processed/issues/psy_*.csv 和 charts/i11_*.png
```
