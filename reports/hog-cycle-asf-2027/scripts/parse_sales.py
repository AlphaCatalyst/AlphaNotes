"""Parse monthly hog-sales announcements into a tidy monthly table.

Lead-sentence extraction first (current-month figures), then table fallback for months that only
appear in the rolling 12-month tables of later announcements. Every value keeps the announcement
URL it came from. Units: heads in 万头, revenue in 亿元, prices in 元/公斤, weight in 公斤.
Scope caveats (e.g. DBN 控股 vs 参股, Tianbang 控股 only, Muyuan switching to 商品猪-only
reporting) are recorded in `scope_note` instead of being silently mixed.
"""
import re

import numpy as np
import pandas as pd

from common import PROC

t = pd.read_csv(PROC / "sales_ann_text.csv", dtype={"code": str})
t = t[t["text"].notna() & ~t["text"].str.startswith("[")]
if "cumulative_from" not in t:
    t["cumulative_from"] = np.nan


def norm(s):
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(?<=[^\d\.,])\s+|\s+(?=[^\d\.,])", "", s)
    return s.replace("（", "(").replace("）", ")").replace("：", ":").replace("，", ",")


def num(x):
    return float(x.replace(",", ""))


def wan(v, unit):
    return v / 1e4 if unit == "头" else v


def yi(v, unit):
    return v / 1e4 if unit == "万元" else v


CUM = re.compile(r"(?:\d{4}年)?(?:1|一)[-—－至~](?:\d{1,2}|十二|十一|十)月(?:份)?[^。;]*[。;]|累计(?:销售|出栏)[^。;]*[。;]"
                 r"|\d{4}年度,[^。;]*[。;]")
PIG_SECTION = re.compile(r"[一二三四]、\d{4}年\d{1,2}月(?:份)?(?:及\d{4}年度)?(?:商品)?(?:肉猪|猪产品)(?:销售)?情况")
STOPS = re.compile(r"上述|[二三四]、|(?<!\d)月份(?:生猪|商品猪)销(?:售|量)|时间生猪")
JANFEB = re.compile(r"1[-—－~]2月")


def lead(s, jan_feb=False):
    m = PIG_SECTION.search(s)  # Wens: chicken section may come first
    i = m.start() if m else max(s.find("一、"), 0)
    h = re.search(r"情况|数据|简报", s[i:i + 40])
    body = i + (h.end() if h else 5)
    k = STOPS.search(s, body)
    j = k.start() if k else len(s)
    L = s[i:j]
    if jan_feb:  # combined Jan-Feb report: the 1-2月 sentence is the period itself, not a cumulative
        L = JANFEB.sub("JANFEB", L)
    return CUM.sub("", L)


TOTAL = [
    r"控股公司生猪销售数量为([\d,\.]+)(万头|头)",
    r"销售(?:生猪|商品猪|商品肉猪|肉猪|商品肥猪)(?:数量)?(?:为|合计)?([\d,\.]+)(万头|头)",
    r"商品肥猪销售数量为([\d,\.]+)(万头|头)",
    r"生猪销量(?:合计)?([\d,\.]+)(万头|头)",
    r"生猪销售数量(?:当月合计为)?([\d,\.]+)(万头|头)",
    r"共销售生猪([\d,\.]+)(万头|头)",
    r"生猪销售量([\d,\.]+)(万头|头)",
]
COMMODITY = [r"其中商品猪([\d,\.]+)(万头|头)", r"商品猪([\d,\.]+)(万头|头)[,，、]仔猪",
             r"商品肉猪销售量为([\d,\.]+)(万头|头)"]
PIGLET = [r"仔猪(?:销售)?(?:量为)?([\d,\.]+)(万头|头)"]
BREEDER = [r"(?<!淘汰)种猪(?:销售)?(?:量为)?([\d,\.]+)(万头|头)"]
REVENUE = [r"控股公司生猪销售数量为[\d,\.]+万头,销售收入([\d,\.]+)(亿元|万元)",
           r"(?:商品猪|商品肥猪|生猪)?销售收入(?:合计)?(?:为)?([\d,\.]+)(亿元|万元)",
           r"收入(?:合计|为)?([\d,\.]+)(亿元|万元)"]
PRICE = [r"商品肥猪均价为([\d\.]+)元", r"商品猪\(扣除仔猪(?:、种猪)?后\)销售均价([\d\.]+)元",
         r"剔除仔猪、种猪影响后商品猪均价为([\d\.]+)元", r"商品猪销售均价([\d\.]+)元",
         r"商品肥猪(?:当月)?(?:销售)?均价(?:为)?([\d\.]+)元", r"毛猪销售均价([\d\.]+)元",
         r"销售均价([\d\.]+)元/(?:公斤|kg)"]
WEIGHT = [r"商品肥猪出栏均重([\d\.]+)公斤", r"商品猪(?:销售)?均重(?:分别为[\d\.]+公斤/头、[\d\.]+公斤/头、)?([\d\.]+)公斤",
          r"均重([\d\.]+)公斤"]


def first(pats, s):
    for p in pats:
        m = re.search(p, s)
        if m:
            return m
    return None


def xinwufeng(t):
    """600975: quarterly YTD 生产量/销售量 tables (2018-2024) and monthly briefs plus monthly rows
    inside the YTD announcements (2025+)."""
    out = []
    for _, r in t[t["code"] == "600975"].iterrows():
        s = norm(r["text"])
        y = int(r["year"])
        if pd.notna(r.get("cumulative_from")) and y <= 2024:
            m = re.search(r"生猪\(万头\)([\d\.]+) ([\d\.]+)", s)
            if m:
                out.append(dict(code="600975", year=y, ytd_end_month=int(r["month"]), ytd_production=num(m.group(1)),
                                ytd_sales=num(m.group(2)), url=r["url"], ann_date=r["ann_date"], title=r["title"]))
            continue
        for m in re.finditer(r"(?<![\d\.])(\d{1,2})月 ?([\d\.]+) ([\d\.]+) ([\d\.]+) ([\d\.]+) ([\d\.]+)", s):
            mo = int(m.group(1))
            if 1 <= mo <= 12 and num(m.group(2)) <= num(m.group(3)) + 1e-6:
                out.append(dict(code="600975", year=y, month=mo, total_heads=num(m.group(2)),
                                commodity_heads=num(m.group(4)), price=num(m.group(6)), url=r["url"],
                                ann_date=r["ann_date"], title=r["title"], src="ytd_table"))
    return pd.DataFrame(out)


recs = []
for _, r in t.iterrows():
    s = norm(r["text"])
    jf = bool(JANFEB.search(r["title"]))
    L = lead(s, jan_feb=jf)
    rec = dict(code=r["code"], sec_name=r["sec_name"], year=int(r["year"]), month=2 if jf else int(r["month"]),
               months_covered=2 if jf else 1,
               ann_date=r["ann_date"], title=r["title"], url=r["url"],
               cumulative=(not jf) and pd.notna(r.get("cumulative_from")) and r.get("cumulative_from") not in ("", None),
               src="lead")
    if re.search(r"\d{4}年(?:度)?(?:1-|1—|1－)?12月?(?:份)?及|年度及", r["title"]) and "2018年度及2019年1月" not in r["title"]:
        rec["scope_note"] = "标题含年度汇总"
    m = first(TOTAL, L)
    if m:
        rec["total_heads"] = wan(num(m.group(1)), m.group(2))
    m = first(COMMODITY, L)
    if m:
        rec["commodity_heads"] = wan(num(m.group(1)), m.group(2))
    m = first(PIGLET, L)
    if m:
        rec["piglet_heads"] = wan(num(m.group(1)), m.group(2))
    m = first(BREEDER, L)
    if m:
        rec["breeder_heads"] = wan(num(m.group(1)), m.group(2))
    m = first(REVENUE, L)
    if m:
        rec["revenue_yi"] = yi(num(m.group(1)), m.group(2))
    m = first(PRICE, L)
    if m:
        rec["price"] = num(m.group(1))
    m = first(WEIGHT, L)
    if m:
        rec["weight_kg"] = num(m.group(1))
    # company specifics
    if r["code"] == "001201":
        m = re.search(r"供港(?:活大猪)?([\d\.]+)万头,内销([\d\.]+)万头", L)
        if m:
            rec["export_heads"], rec["domestic_heads"] = num(m.group(1)), num(m.group(2))
        m = re.search(r"供港活大猪均价([\d\.]+)元/公斤、内销商品肉猪均价([\d\.]+)元/公斤", L)
        if m:
            rec["export_price"], rec["domestic_price"] = num(m.group(1)), num(m.group(2))
    if r["code"] == "002385":
        m = re.search(r"参股公司生猪销售数量为([\d,\.]+)万头", L)
        if m:
            rec["jv_heads"] = num(m.group(1))
            rec["scope_note"] = "仅控股公司；参股另列"
    if r["code"] == "002124":
        m = re.search(r"参股公司.{0,20}?销售各类商品猪合计([\d,\.]+)头", s)
        if m:
            rec["jv_heads"] = num(m.group(1)) / 1e4
        rec.setdefault("scope_note", "控股子公司口径；总数含仔猪")
        if "total_heads" in rec and "piglet_heads" in rec:
            rec["commodity_heads"] = rec["total_heads"] - rec["piglet_heads"]
    if r["code"] == "002714" and re.search(r"销售商品猪[\d,\.]+万头", L) and "其中仔猪" not in L:
        rec["commodity_heads"] = rec.get("total_heads")
        rec["scope_note"] = "仅披露商品猪"
    if r["code"] == "002714" and "其中仔猪" in L and "total_heads" in rec and "piglet_heads" in rec:
        rec["commodity_heads_derived"] = rec["total_heads"] - rec["piglet_heads"]
    if r["code"] == "000048" and "商品肥猪" in L and "仔猪" not in L:
        rec["commodity_heads"] = rec.get("total_heads")
        rec["scope_note"] = "仅披露商品肥猪"
    if r["code"] == "002385" and "商品肥猪销售情况" in r["title"]:
        rec["commodity_heads"] = rec.get("total_heads")
        rec["scope_note"] = "仅商品肥猪"
    if r["code"] == "000876" and re.search(r"销售商品猪[\d,\.]+万头", L):
        rec["commodity_heads"] = rec.get("total_heads")
        m = re.search(r"销售仔猪([\d\.]+)万头,销售种猪([\d\.]+)万头", s)
        if m:
            rec["piglet_heads"], rec["breeder_heads"] = num(m.group(1)), num(m.group(2))
        rec["scope_note"] = "主句为商品猪；仔猪种猪另列"
    if r["code"] == "002477":
        m = re.search(r"商品肉猪销售量为([\d\.]+)万头", L)
        if m:
            rec["commodity_heads"] = num(m.group(1))
    recs.append(rec)

df = pd.DataFrame(recs)
# drop cumulative-only (e.g. 1-6月) rows from the monthly table
df = df[~df["cumulative"]]
df = df.sort_values(["code", "year", "month", "ann_date"]).drop_duplicates(["code", "year", "month"], keep="last")


# ---------------------------------------------------------------- table fallback
ROW = re.compile(r"(20\d{2})年(\d{1,2})月(?:份)?\s?([\d,]+\.\d+|\d+)\s([\d,]+\.\d+|\d+)\s([\d,]+\.\d+)\s([\d,]+\.\d+)\s(\d+\.\d+)")
fb = []
for _, r in t.iterrows():
    if r["code"] in ("002124", "002567", "300498", "002840", "002477", "000735"):
        continue  # different column orders
    s = norm(r["text"])
    s = re.sub(r"(?<=月)(?=[\d])", " ", s)
    for m in ROW.finditer(s):
        y, mo = int(m.group(1)), int(m.group(2))
        heads_m, heads_cum, rev_m, rev_cum, price = (num(m.group(i)) for i in range(3, 8))
        if heads_m > heads_cum + 1e-6 or not (3 <= price <= 60):
            continue
        fb.append(dict(code=r["code"], year=y, month=mo, t_total_heads=heads_m, t_revenue_yi=rev_m,
                       t_price=price, t_url=r["url"], t_ann_date=r["ann_date"]))
fb = pd.DataFrame(fb)
if len(fb):
    fb = fb.sort_values("t_ann_date").drop_duplicates(["code", "year", "month"], keep="last")
    df = df.merge(fb, on=["code", "year", "month"], how="outer")
    annual_first = df["title"].fillna("").str.contains("年度及") & df["t_total_heads"].notna()
    df.loc[annual_first, "total_heads"] = np.nan
    miss = df["total_heads"].isna() & df["t_total_heads"].notna()
    df.loc[miss, "src"] = "table"
    for a, b in [("total_heads", "t_total_heads"), ("revenue_yi", "t_revenue_yi"), ("price", "t_price"),
                 ("url", "t_url"), ("ann_date", "t_ann_date")]:
        df.loc[miss, a] = df.loc[miss, b]
    # consistency flag where both exist
    both = df["total_heads"].notna() & df["t_total_heads"].notna() & (df["src"] == "lead")
    df["table_mismatch"] = both & ((df["total_heads"] - df["t_total_heads"]).abs() > 0.06)
    df = df.drop(columns=[c for c in df.columns if c.startswith("t_")])

xw = xinwufeng(t)
if len(xw):
    ytd = xw[xw["ytd_end_month"].notna()].sort_values(["year", "ytd_end_month", "ann_date"])
    ytd = ytd.drop_duplicates(["year", "ytd_end_month"], keep="last").copy()
    ytd["quarter"] = (ytd["ytd_end_month"] // 3).astype(int)
    for col in ("ytd_production", "ytd_sales"):
        prev = ytd.groupby("year")[col].shift(1).fillna(0)
        ytd[col.replace("ytd_", "q_")] = ytd[col] - prev
    ytd["note"] = "单季=累计差分；上一季缺失时该季为年初至今累计"
    ytd.to_csv(PROC / "xinwufeng_quarterly.csv", index=False)
    mrows = xw[xw["month"].notna()].copy()
    mrows["month"] = mrows["month"].astype(int)
    have = set(zip(df.loc[df["code"] == "600975", "year"], df.loc[df["code"] == "600975", "month"]))
    mrows = mrows[[(y, mo) not in have for y, mo in zip(mrows["year"], mrows["month"])]]
    mrows = mrows.sort_values("ann_date").drop_duplicates(["year", "month"], keep="last")
    mrows["sec_name"] = "新五丰"
    df = pd.concat([df, mrows.drop(columns=[c for c in mrows.columns if c.startswith("ytd_")])], ignore_index=True)

df["months_covered"] = df["months_covered"].fillna(1).astype(int)
df["month_key"] = df["year"].astype(int).astype(str) + "-" + df["month"].astype(int).map("{:02d}".format)
df["sec_name"] = df.groupby("code")["sec_name"].transform(lambda x: x.ffill().bfill())
df = df.sort_values(["code", "month_key"])
cols = ["code", "sec_name", "month_key", "months_covered", "total_heads", "commodity_heads", "commodity_heads_derived", "piglet_heads",
        "breeder_heads", "jv_heads", "revenue_yi", "price", "weight_kg", "export_heads", "domestic_heads",
        "export_price", "domestic_price", "scope_note", "src", "table_mismatch", "ann_date", "title", "url"]
df = df[[c for c in cols if c in df.columns]]
df.to_csv(PROC / "monthly_sales.csv", index=False)
cov = df.groupby("code").agg(first=("month_key", "min"), last=("month_key", "max"), n=("month_key", "size"),
                             total_na=("total_heads", lambda x: int(x.isna().sum())),
                             price_na=("price", lambda x: int(x.isna().sum())))
print(cov)
print(df[df.get("table_mismatch", False) == True][["code", "month_key", "total_heads", "title"]].head(30))
