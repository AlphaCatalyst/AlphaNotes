#!/usr/bin/env bash
# Rebuild all industry-supply / spot-price datasets from cached raw pages (downloads only what is
# missing). The two NBS scripts run sequentially because www.stats.gov.cn rate-limits with a captcha.
set -euo pipefail
cd "$(dirname "$0")"
python3 -u nbs_index.py
python3 -u nbs_quarterly.py
python3 -u nbs_tenday.py            # 2018-2022; `python3 nbs_tenday.py 2016 2017` etc. for other years
python3 -u moa_weekly_prices.py
python3 -u moa_sows_monthly.py
python3 -u nxin_prices.py
python3 -u gd_prices.py
python3 -u gd_supply_share.py       # 广东省农业农村厅 产销形势分析 (Issue #4)
python3 -u zhuwang_prices.py        # 中国养猪网 provincial quotes, local only (Issue #4)
python3 -u build_checks.py
