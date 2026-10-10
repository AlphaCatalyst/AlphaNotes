"""中国养猪网 (zhuwang.com.cn) provincial 外三元 hog quotes -> zhuwang_province_daily.csv (local only).

List: www.zhuwang.com.cn/list-63-N.html (生猪价格 column, newest first, 15 items per page).
Since 2015-12 the column carries a daily article "YYYY年MM月DD日全国外三元生猪价格行情涨跌表"
("...行情走势" in late 2015) whose table has one row per province: that day's and the previous
day's average 外三元 price, and the changes on the day and on the week. Earlier provincial quotes
were images or individual county quotes, so the series starts in 2015-12. There is no national row.

Articles are sampled twice a week: the first available day in Mon-Wed and in Thu-Sun.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ind_common import PROC, decode, fetch, write_csv  # noqa: E402

SUB = "zhuwang"
LIST = "https://www.zhuwang.com.cn/list-63-{}.html"
START = dt.date(2015, 12, 1)
FRESH_PAGES = 5
WORKERS = 4
ITEM = re.compile(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>\s*(\d{4})年(\d{1,2})月(\d{1,2})日([^<]{2,60})</a>")
PROV = re.compile(
    r"^(北京|天津|上海|重庆)市?$|^(河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|海南|"
    r"四川|贵州|云南|陕西|甘肃|青海)省?$|^(内蒙古|广西|西藏|宁夏|新疆)"
)
NUM = re.compile(r"^-?\d+(?:\.\d+)?$")


def list_page(n: int) -> list[dict]:
    b = fetch(LIST.format(n), f"{SUB}/lists", name=f"list-63-{n}.html", force=n <= FRESH_PAGES)
    if not b:
        return []
    t = decode(b)
    body = t[t.find("zxleft31"):] if "zxleft31" in t else t
    out = []
    for href, y, m, d, rest in ITEM.findall(body):
        if "外三元" not in rest or not ("涨跌表" in rest or "行情走势" in rest):
            continue
        url = "https:" + href if href.startswith("//") else href
        out.append(dict(date=dt.date(int(y), int(m), int(d)), title=f"{y}年{m}月{d}日{rest.strip()}", url=url, page=n))
    return out


def crawl_lists() -> pd.DataFrame:
    rows, n, batch = [], 1, 40
    while True:
        with ThreadPoolExecutor(WORKERS) as ex:
            got = list(ex.map(list_page, range(n, n + batch)))
        for g in got:
            rows += g
        dates = [r["date"] for g in got for r in g if r["page"] >= n]
        n += batch
        if not dates or min(dates) < START - dt.timedelta(days=10) or n > 3000:
            break
    d = pd.DataFrame(rows).drop_duplicates("url")
    d = d[d.date >= START].sort_values(["date", "url"])
    return d.drop_duplicates("date", keep="last")


def sample(index: pd.DataFrame) -> pd.DataFrame:
    d = index.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["half"] = d["date"].dt.to_period("W-SUN").astype(str) + "_" + (d["date"].dt.weekday >= 3).astype(int).astype(str)
    return d.sort_values("date").groupby("half", as_index=False).first()


def parse(url: str, day: pd.Timestamp) -> list[dict]:
    b = fetch(url, f"{SUB}/articles")
    if not b:
        return []
    t = decode(b)
    tb = re.search(r"<table.*?</table>", t, re.S)
    if not tb:
        return []
    out = []
    for tr in re.findall(r"<tr.*?</tr>", tb.group(0), re.S):
        cells = [re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", c)) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        for i, c in enumerate(cells):
            m = PROV.match(c)
            if m and len(cells) >= i + 3 and NUM.match(cells[i + 1]) and NUM.match(cells[i + 2]):
                name = next(g for g in m.groups() if g)
                rest = cells[i + 1:i + 5] + [""] * 4
                out.append(dict(date=day.date(), province=name, price=float(rest[0]), prev_day=float(rest[1]),
                                chg_day=float(rest[2]) if NUM.match(rest[2]) else None,
                                chg_week=float(rest[3]) if NUM.match(rest[3]) else None, url=url))
                break
    return out


def main():
    index = crawl_lists()
    write_csv(index, PROC.parent / "raw" / "industry" / SUB / "article_index.csv")
    s = sample(index)
    with ThreadPoolExecutor(WORKERS) as ex:
        parts = list(ex.map(parse, s["url"], s["date"]))
    d = pd.DataFrame([r for p in parts for r in p]).sort_values(["date", "province"])
    write_csv(d, PROC / "zhuwang_province_daily.csv")
    print(f"{len(index)} daily articles {index.date.min()} → {index.date.max()}; sampled {len(s)}; "
          f"parsed {d.date.nunique()} days, {len(d)} rows; provinces per day median {d.groupby('date').size().median():.0f}")


if __name__ == "__main__":
    main()
