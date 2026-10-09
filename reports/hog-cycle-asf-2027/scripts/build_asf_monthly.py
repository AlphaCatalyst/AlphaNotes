"""Build monthly ASF outbreak counts (2018-08 .. 2021-12) from MOA sources.

Sources
- MOA "疫情发布" column (one notice per confirmed outbreak report):
  http://www.moa.gov.cn/gk/yjgl_1/yqfb/  (16 list pages)
- MOA Official Veterinary Bulletin monthly epizootic tables (兽医公报·动物疫情月报), only the
  issues still online at http://www.moa.gov.cn/gk/sygb/ (2019-08, 2019-11, 2020-02..2021-09 partial).

Counting rule for notices (documented in research/policy_timeline/summary.md):
  one outbreak per separately reported county/township site; households lumped into one
  statistic in the same village/area count as one; several trucks seized at one checkpoint
  count as one; explicit "X起" wording always wins.

Outputs (research/policy_timeline/):
  asf_outbreak_notices.csv  every ASF notice with the count assigned and why
  asf_outbreaks_monthly.csv monthly series with official cross-checks
"""
from __future__ import annotations

import csv
import json
import re
import time
from collections import OrderedDict, defaultdict
from pathlib import Path

from common import RAW, ROOT, fetch_pdf_text
from policy_fetch import fetch_html, page_text

OUT = ROOT / "research" / "policy_timeline"
OUT.mkdir(parents=True, exist_ok=True)
LIST_BASE = "http://www.moa.gov.cn/gk/yjgl_1/yqfb/"
SYGB_INDEX = "http://www.moa.gov.cn/gk/sygb/"

# (date published in list, title keyword) -> (count, reason)
OVERRIDES = {
    ("2018-09-02", "宣州区发生"): (2, "古泉镇、五星乡两个养殖场分别列示"),
    ("2018-09-06", "佳木斯市、芜湖市、宣城市"): (3, "标题明确“各发生一起”"),
    ("2018-09-14", "阿巴嘎旗"): (2, "两地各一起"),
    ("2018-09-21", "公主岭市"): (2, "两地各一起"),
    ("2018-09-30", "营口市发生"): (2, "大石桥市、老边区两地（五户合并统计）"),
    ("2018-10-08", "营口市排查出"): (4, "高坎镇、旗口镇、路南镇、边城镇四个镇（六村合并统计）"),
    ("2018-10-15", "锦州市盘锦市"): (3, "正文明确“3起”"),
    ("2018-10-16", "铁岭市盘锦市"): (3, "正文明确“3起”"),
    ("2018-10-22", "昭通市"): (2, "牛场镇养殖场、母享镇合作社分别列示"),
    ("2018-10-23", "益阳市和常德市"): (2, "两县两场"),
    ("2018-10-30", "阳曲县、湖南省沅陵县"): (3, "标题明确“各发生一起”"),
    ("2018-11-08", "涟源市"): (3, "三地各一起"),
    ("2018-11-17", "鄱阳县"): (3, "标题明确“各排查出一起”"),
    ("2018-11-23", "房山区"): (2, "青龙湖镇、琉璃河镇各一个养殖场"),
    ("2018-12-03", "鄠邑区"): (3, "三地（含北安管理局野猪养殖场）"),
    ("2018-12-05", "合江县"): (3, "三地"),
    ("2018-12-10", "神木市"): (2, "两地"),
    ("2018-12-12", "巴州区"): (2, "两地"),
    ("2018-12-16", "盐亭县"): (2, "两地"),
    ("2019-03-31", "利川市"): (2, "两个养殖场分别列示"),
    ("2019-04-07", "林芝市"): (3, "巴宜区、工布江达县、波密县三地"),
    ("2019-04-19", "儋州市和万宁市"): (2, "两市（各两户合并统计）"),
    ("2019-04-21", "秀英区"): (4, "秀英、澄迈、保亭、陵水四县区"),
    ("2019-06-20", "平塘县"): (2, "克度镇、通州镇两处分别列示"),
    ("2019-06-21", "三都县"): (2, "周覃镇、中和镇两处"),
    ("2020-03-13", "泸州市、河南省三门峡市"): (2, "两地"),
    ("2020-04-02", "陇南市"): (2, "正文明确“2起”"),
    ("2020-04-12", "酒泉市和陕西省榆林市"): (2, "标题明确“各发生1起”"),
    ("2021-03-06", "小金县"): (2, "标题明确“分别报告发生一起”"),
}
LUMPED = {
    ("2018-08-23", "乐清市"): "同一养殖小区3户，通报称“一起”",
    ("2018-10-26", "七星关区"): "同村3户合并统计",
    ("2018-11-13", "武穴市"): "两相邻养殖户合并统计",
    ("2018-11-19", "道外区"): "两养殖户合并统计",
    ("2019-01-12", "泗阳县"): "同一公司两场合并统计（若按两场计则2019-01为6起）",
    ("2019-01-18", "七里河区"): "两养殖户合并统计",
    ("2019-02-19", "北海市"): "两养殖小区合并统计",
    ("2019-04-04", "香格里拉市"): "同一村民小组10户合并统计",
    ("2019-04-11", "疏勒县"): "两养殖户合并统计",
    ("2019-06-28", "沙坡头区"): "屠宰厂检出并追溯至一养殖户",
    ("2019-07-27", "西丰县"): "同一检查点截获2车",
    ("2019-10-15", "博白县"): "同一检查点截获2车",
    ("2019-12-24", "叙永县"): "同一检查点截获3车",
}
FIRST_CASE = dict(
    list_date="2018-08-03", pub_date="2018-08-03",
    title="辽宁省沈阳市沈北新区发生一起非洲猪瘟疫情（我国首例）",
    url="http://politics.people.com.cn/n1/2018/0804/c1001-30208671.html",
    count=1, reason="首例；农业农村部“疫情发布”栏目未收录，引人民网转载的农业农村部新闻办公室发布",
)


def crawl_list():
    items = []
    for i in range(16):
        u = LIST_BASE if i == 0 else LIST_BASE + f"index_{i}.htm"
        src = fetch_html(u)
        for m in re.finditer(r'href="(\./\d{6}/t\d{8}_\d+\.htm)"[^>]*>(.*?)</a>.*?(\d{4}-\d{2}-\d{2})', src, re.S):
            href, title, d = m.groups()
            title = re.sub(r"<.*?>|\s", "", title)
            if "猪瘟" in title:
                items.append(dict(url=LIST_BASE + href[2:], title=title, list_date=d))
    items.sort(key=lambda x: x["list_date"])
    return items


def pub_date_of(item):
    t = page_text(item["url"])
    m = re.search(r"农业农村部新闻办公室(\d{1,2})月(\d{1,2})日发布", t)
    if not m:
        return item["list_date"], "正文无发布日期，用列表日期"
    y = int(item["list_date"][:4])
    mo, d = int(m.group(1)), int(m.group(2))
    if mo == 12 and item["list_date"][5:7] == "01":
        y -= 1
    return f"{y:04d}-{mo:02d}-{d:02d}", ""


def assign(item):
    for (d, kw), (n, why) in OVERRIDES.items():
        if item["list_date"] == d and kw in item["title"]:
            return n, why
    for (d, kw), why in LUMPED.items():
        if item["list_date"] == d and kw in item["title"]:
            return 1, why
    return 1, ""


def bulletin_counts():
    """Monthly ASF new-outbreak totals from the bulletins still online."""
    src = fetch_html(SYGB_INDEX)
    res = {}
    months = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                                           "August", "September", "October", "November", "December"], 1)}
    for m in re.finditer(r'href="\./(\d{6}/P\d+\.pdf)"[^>]*>.*?(\d{4})年\s*第(\d+)期', src, re.S):
        rel, y, _ = m.groups()
        if y not in ("2019", "2020", "2021"):
            continue
        u = SYGB_INDEX + rel
        t = fetch_pdf_text(u, cache_dir=RAW / "policy")
        mm = re.search(r"Monthly Epizootic Bulletin for\s+([A-Za-z]+)\s*(\d{4})", t)
        if not mm:
            continue
        key = f"{mm.group(2)}-{months[mm.group(1)]:02d}"
        i = t.find("African Swine Fever")
        j = t.find("本月新发生次数", i)
        total, rows = 0, []
        for line in t[i:j].split("\n"):
            if re.search(r"\b(P|Wp)\b", line) and not re.search(r"\b(O|A|Asia)\b", line):
                r = re.search(r"\s(\d+)\s+(\d+)\s+(P|Wp)\b", line)
                if r:
                    total += int(r.group(1))
                    rows.append(re.sub(r"\s+", " ", line.strip()))
        res[key] = dict(value=total, url=u, rows="; ".join(rows))
    return res


def month_range(a, b):
    y, m = map(int, a.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= b:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


ANCHORS = [
    ("2018-09-01", 5, "农业农村部发言人（9月2日）：8月初以来相继发生5起，不含9月2日当天发布的宣州疫情",
     "https://www.cneb.gov.cn/2018/09/02/ARTI1535871685741149.shtml"),
    ("2018-10-09", 29, "农业农村部畜牧兽医局负责人：截至10月9日全国共发生29起",
     "http://www.moa.gov.cn/ztzl/fzzwfk/gzdt/201810/t20181009_6160378.htm"),
    ("2018-11-22", 74, "农业农村部发布会：截至11月22日家猪73起、野猪1起",
     "https://www.gov.cn/zhengce/2018-11/23/content_5342905.htm"),
    ("2018-12-14", 89, "农业农村部（央视新闻客户端/中新网转）：截至12月14日家猪87起、野猪2起",
     "https://www.chinanews.com/gn/2018/12-15/8702996.shtml"),
    ("2019-07-03", 143, "国新办吹风会：截至2019年7月3日共143起（2019年以来44起）",
     "https://www.gov.cn/xinwen/2019-07/04/content_5406088.htm"),
    ("2019-12-31", 162, "农业农村部发布会（2020-01-08）：累计162起，2019年全年63起",
     "https://www.cneb.gov.cn/2020/01/08/ARTI1578457084723323.shtml"),
]


def main():
    items = crawl_list()
    rows = []
    for it in items:
        pd, why_date = pub_date_of(it)
        n, why = assign(it)
        rows.append(dict(list_date=it["list_date"], pub_date=pd, title=it["title"], url=it["url"],
                         count=n, reason="；".join(x for x in (why, why_date) if x)))
        time.sleep(0.05)
    rows.insert(0, dict(list_date=FIRST_CASE["list_date"], pub_date=FIRST_CASE["pub_date"],
                        title=FIRST_CASE["title"], url=FIRST_CASE["url"], count=1, reason=FIRST_CASE["reason"]))
    rows.sort(key=lambda r: (r["pub_date"], r["list_date"]))

    with open(OUT / "asf_outbreak_notices.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["pub_date", "list_date", "title", "outbreaks_counted", "counting_note", "url"])
        w.writeheader()
        for r in rows:
            w.writerow(dict(pub_date=r["pub_date"], list_date=r["list_date"], title=r["title"],
                            outbreaks_counted=r["count"], counting_note=r["reason"], url=r["url"]))

    by_month = defaultdict(lambda: dict(n=0, notices=0, urls=[]))
    for r in rows:
        k = r["pub_date"][:7]
        by_month[k]["n"] += r["count"]
        by_month[k]["notices"] += 1
        by_month[k]["urls"].append(r["url"])

    bul = bulletin_counts()
    cum = 0
    cum_at = OrderedDict()
    for r in rows:
        cum += r["count"]
        cum_at[r["pub_date"]] = cum

    def cum_by(date):
        v = 0
        for d, c in cum_at.items():
            if d <= date:
                v = c
        return v

    print("Anchor check (notice-derived cumulative vs official):")
    for d, off, desc, _ in ANCHORS:
        print(f"  {d}: derived {cum_by(d)} vs official {off}  ({desc})")

    yearly = defaultdict(int)
    for k, v in by_month.items():
        yearly[k[:4]] += v["n"]
    print("Yearly derived:", dict(yearly))

    notes = {
        "2018-08": "官方锚点：农业农村部发言人9月2日称8月初以来共5起（含沈阳首例，不含9月2日发布的宣州疫情），吻合",
        "2018-09": "截至10月9日官方累计29起；本口径8—9月24起+10月8日营口4起+10月9日鞍山1起=29起，吻合",
        "2018-11": "官方：截至11月22日73+1=74起；本口径截至11月22日确诊为72起，若计入11月23日上午9时确诊的房山2起则为74起",
        "2018-12": "官方：截至12月14日87+2=89起（本口径吻合）；2018年全年=162-63=99起（本口径8—12月合计99起，吻合）",
        "2019-01": "泗阳县“一公司两场”按1起计；若按2起计则本月为6起",
        "2019-04": "官方称2019年“除4月份之外，其他11个月的疫情发生数都保持在个位数”，本口径4月13起，吻合",
        "2019-06": "官方：2019年1月1日—7月3日共44起；本口径1—6月合计44起，吻合",
        "2019-12": "官方2019全年63起；本口径合计62起，差1起，可能为某月有1起未单独发布通报（参见2020-11、2021-09兽医公报有记录而无通报的先例），或某次多车/多场合并通报的计数口径不同",
        "2020-11": "兽医公报记录重庆1起，“疫情发布”栏目无对应通报",
        "2021-09": "兽医公报记录湖南1起，“疫情发布”栏目无对应通报（2021年4月29日后该栏目不再逐起发布）",
    }
    with open(OUT / "asf_outbreaks_monthly.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "outbreaks", "outbreaks_from_moa_notices", "notices_n", "bulletin_value",
                    "confidence", "source_url", "note", "notice_urls"])
        for k in month_range("2018-08", "2021-12"):
            v = by_month.get(k, dict(n=0, notices=0, urls=[]))
            b = bul.get(k)
            if b is not None:
                val, conf, src = b["value"], "高（兽医公报月报）", b["url"]
            elif k <= "2021-04":
                val = v["n"]
                conf = "中（逐起通报统计，已与官方累计数核对）" if k <= "2019-12" else "中（逐起通报统计，无月报可核）"
                src = LIST_BASE
            else:
                val, conf, src = "", "无公开数据（通报栏目2021-04-29后停更，月报缺期）", ""
            note = notes.get(k, "")
            if b is not None and b["value"] != v["n"]:
                note = (note + "；" if note else "") + f"通报统计为{v['n']}起，取月报值"
            if b is not None and b["rows"]:
                note = (note + "；" if note else "") + f"月报分省行：{b['rows']}"
            w.writerow([k, val, v["n"] if k <= "2021-04" or v["n"] else "", v["notices"], "" if b is None else b["value"],
                        conf, src, note, " | ".join(v["urls"])])
    print("months written; bulletin months:", sorted(bul))


if __name__ == "__main__":
    main()
