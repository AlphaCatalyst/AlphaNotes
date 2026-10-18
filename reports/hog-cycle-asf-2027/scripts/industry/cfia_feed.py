"""中国饲料工业协会 / 农业农村部畜牧兽医局 feed-production releases -> cfia_pig_feed_*.csv

The CFIA "行业分析" list (https://www.chinafeed.org.cn/hyfx/hyfx_erji/, 2020-05 onward) carries the
monthly "X月份全国饲料生产形势" sample-enterprise estimates, the H1 / Q1-Q3 analyses and the annual
"全国饲料工业发展概况". The 2019 annual summary comes from the MOA site.

What is public, and how it is captured here:
- Monthly pig feed (万吨, MoM, YoY) appears in the monthly text only up to the 2022-08 release; from
  2022-09 the monthly releases give total feed and 配合/浓缩/预混 only. The 2021-01..07 releases are
  images, transcribed by hand below (IMAGE_TRANSCRIPTIONS, with the image URLs).
- The H1 / Q1-Q3 analyses embed a chart of monthly pig feed (2019-01 onward in the 2023 Q1-Q3 chart,
  2022-01..2026-06 in the 2026 H1 chart). Those values are read off the charts by pixel colour
  (digitize_chart); they are the revised series and carry a reading error of roughly ±0.5-1%.
- Stage YoY (仔猪/母猪/育肥猪) appear only in annual / H1 / Q1-Q3 texts.

Outputs (data/processed/):
- cfia_feed_releases.csv   every release with parsed headline numbers
- cfia_pig_feed_monthly.csv first-release monthly values next to the revised chart readings
- cfia_pig_feed_chart_readings.csv every chart reading (chart, year, month, value)
- cfia_pig_feed_stage.csv  stage YoY by period
- cfia_pig_feed_annual.csv annual totals
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ind_common import PROC, RAW, decode, fetch, flat_text, soup, write_csv  # noqa: E402

SUB = "cfia_feed"
LIST = "https://www.chinafeed.org.cn/hyfx/hyfx_erji/"
EXTRA = [  # releases not on the CFIA list (title, url)
    ("2019年全国饲料工业发展概况", "https://www.moa.gov.cn/xw/bmdt/202003/t20200305_6338606.htm"),
]

# Image-only releases (and image tables inside text releases), transcribed by hand.
# doc_date = date printed on the release itself; the website date can be later.
IMAGE_TRANSCRIPTIONS = [
    dict(period="2021-01", pig=1252, doc_date="2021-03-17",
         url="https://www.chinafeed.org.cn/xwdt_10092/hyxw/202103/t20210318_373294.htm",
         note="1—2月合并发布：1月1252、2月779万吨"),
    dict(period="2021-02", pig=779, doc_date="2021-03-17", cum_pig=2032, cum_yoy=79.9,
         url="https://www.chinafeed.org.cn/xwdt_10092/hyxw/202103/t20210318_373294.htm"),
    dict(period="2022-01", pig=1202, total=2409,
         url="https://www.chinafeed.org.cn/hyfx/hyfx_erji/202203/t20220315_399347.htm",
         note="表2：1月1202、2月924万吨"),
    dict(period="2022-02", pig=924, total=1976, cum_pig=2126, cum_yoy=2.9,
         url="https://www.chinafeed.org.cn/hyfx/hyfx_erji/202203/t20220315_399347.htm"),
    dict(period="2021-03", pig=995, mom=27.7, yoy=68.3, doc_date="2021-04-20", cum_pig=3027, cum_yoy=75.9,
         url="https://www.chinafeed.org.cn/xwdt_10092/hyxw/202104/t20210421_376551.htm"),
    dict(period="2021-04", pig=1090, mom=9.5, yoy=69.8, doc_date="2021-05-12", cum_pig=4117, cum_yoy=74.2,
         url="https://www.chinafeed.org.cn/xwdt_10092/hyxw/202105/t20210513_378247.htm"),
    dict(period="2021-05", pig=1103, mom=1.2, yoy=79.7, doc_date="2021-06-17", cum_pig=5219, cum_yoy=75.4,
         url="https://www.chinafeed.org.cn/hyfx/hyfx_erji/202106/t20210621_381033.htm"),
    dict(period="2021-06", pig=1026, mom=-6.9, yoy=53.5, doc_date="2021-07-08", cum_pig=6246, cum_yoy=71.4,
         url="https://www.chinafeed.org.cn/hyfx/hyfx_erji/202107/t20210720_383193.htm"),
    dict(period="2021-07", pig=1045, mom=1.9, yoy=41.6, doc_date="2021-08-17", cum_pig=7291, cum_yoy=66.4,
         url="https://www.chinafeed.org.cn/hyfx/hyfx_erji/202108/t20210817_385126.htm"),
]
# 2026 H1 analysis is an image; its pig paragraph reads (transcribed):
H1_2026 = dict(period="2026H1", pig=8353, yoy=7.9, piglet=1.1, sow=4.2, finishing=11.8,
               url="https://www.chinafeed.org.cn/hyfx/hyfx_erji/202607/t20260720_473456.htm",
               release_date="2026-07-20", source_form="图片转录")
# Stage figures published outside the 行业分析 list (association news).
STAGE_OTHER = [
    dict(period="2021-01~05", pig=5219, yoy=75.4, piglet=67.6, sow=68.2, finishing=81.8,
         release_date="2021-06-21", source_form="协会座谈会通报",
         url="https://www.chinafeed.org.cn/xwdt_10092/xhxw/202106/t20210621_381070.htm",
         note="同文：5月母猪饲料环比-0.4%，连续20个月除季节性下降外的首次下降"),
]

CHARTS = {  # monthly pig-feed charts inside the periodic analyses
    "2023Q1-Q3": dict(page="https://www.chinafeed.org.cn/hyfx/202311/t20231114_434324.htm",
                      img="W020231115352222799895.png", crop=None, top=1400, step=200, n=6, ref="orange",
                      series={2019: "orange", 2020: "green", 2021: "gold", 2022: "blue", 2023: "red"},
                      release_date="2023-11-14"),
    "2024H1": dict(page="https://www.chinafeed.org.cn/hyfx/202407/t20240729_445115.htm",
                   img="W020240729581803438390.png", crop=None, top=1600, step=200, n=7, ref="green",
                   series={2020: "green", 2021: "gold", 2022: "blue", 2023: "orange", 2024: "red"},
                   release_date="2024-07-29"),
    "2024Q1-Q3": dict(page="https://www.chinafeed.org.cn/hyfx/202410/t20241023_448438.htm",
                      img="W020241023547221705902.png", crop=None, top=1600, step=400, n=4, ref="green",
                      series={2020: "green", 2021: "gold", 2022: "blue", 2023: "orange", 2024: "red"},
                      release_date="2024-10-23"),
    "2026H1": dict(page="https://www.chinafeed.org.cn/hyfx/hyfx_erji/202607/t20260720_473456.htm",
                   img="W020260720359814271142.jpg", crop=(0, 1375, 700, 1720), top=1800, step=300, n=5,
                   ref="gold", series={2022: "blue", 2023: "orange", 2024: "green", 2025: "gold", 2026: "red"},
                   release_date="2026-07-20"),
}
COLORS = {False: dict(blue=(91, 155, 213), orange=(237, 125, 49), green=(0, 176, 80), gold=(255, 192, 0),
                      red=(255, 0, 0)),
          True: dict(blue=(105, 150, 180), orange=(205, 130, 80), green=(35, 150, 85), gold=(225, 200, 70),
                     red=(190, 30, 30))}  # True = JPEG, colours shifted by compression

NUM = r"(\d+(?:\.\d+)?)"
SIGN = {"增长": 1, "增加": 1, "上升": 1, "提高": 1, "下降": -1, "减少": -1}


def signed(word, x):
    return SIGN[word] * float(x)


# ---------------------------------------------------------------------------
# release list and text
# ---------------------------------------------------------------------------
def list_releases() -> pd.DataFrame:
    rows = []
    for i in range(5):
        url = LIST + ("index.htm" if i == 0 else f"index_{i}.htm")
        b = fetch(url, f"{SUB}/list")
        if not b:
            continue
        for m in re.finditer(r'<a href="([^"]+)"[^>]*title="([^"]+)"', decode(b)):
            href, title = m.group(1), m.group(2)
            if "饲料" in title and "weixin" not in href:
                rows.append(dict(title=title, url=urljoin(url, href)))
    rows += [dict(title=t, url=u) for t, u in EXTRA]
    return pd.DataFrame(rows).drop_duplicates("url")


def page(url):
    b = fetch(url, f"{SUB}/pages", sleep=0.5)
    if not b:
        return "", None
    t = flat_text(soup(b))
    d = re.search(r"日期[：:](\d{4}-\d{2}-\d{2})", t)
    i, j = t.find("打印本页"), t.find("相关附件")
    if i >= 0:
        t = t[i:j if j > i else None]
    return t, d.group(1) if d else None


def kind_period(title):
    if m := re.search(r"(\d{4})年(\d{1,2})月份全国饲料生产形势", title):
        return "月度", f"{m.group(1)}-{int(m.group(2)):02d}"
    if m := re.search(r"(\d{4})年1—2月份全国饲料生产形势", title):
        return "月度", f"{m.group(1)}-01~02"
    if m := re.search(r"(\d{4})年全国饲料工业发展概况", title):
        return "年度", m.group(1)
    if m := re.search(r"(\d{4})年上半年", title):
        return "半年", f"{m.group(1)}H1"
    if m := re.search(r"(\d{4})年前三季度", title):
        return "前三季度", f"{m.group(1)}Q1-Q3"
    if m := re.search(r"(\d{4})年一季度", title):
        return "一季度", f"{m.group(1)}Q1"
    if m := re.search(r"从(\d{4})年饲料产量变化趋势", title):
        return "年度分析", m.group(1)
    return "其他", ""


def parse_monthly(t):
    r = {}
    m = re.search(r"(?:全国工业饲料总产量|全国工业饲料产量|饲料总产量)" + NUM +
                  r"万吨，(环比|同比)(增长|下降)" + NUM + r"%，(环比|同比)(增长|下降)" + NUM + "%", t)
    if m:
        r["total_10kt"] = float(m.group(1))
        for k in (2, 5):
            r["total_" + ("mom" if m.group(k) == "环比" else "yoy")] = signed(m.group(k + 1), m.group(k + 2))
    seg = t[t.find("从品种看"):] if "从品种看" in t else t
    m = re.search(r"猪饲料产量" + NUM + r"万吨[，,](环比|同比)(增长|下降)" + NUM +
                  r"%(?:[，,](环比|同比)(增长|下降)" + NUM + "%)?", seg)
    if m:
        r["pig_10kt"] = float(m.group(1))
        for k in (2, 5):
            if m.group(k):
                r["pig_" + ("mom" if m.group(k) == "环比" else "yoy")] = signed(m.group(k + 1), m.group(k + 2))
    m = re.search(r"猪饲料同比降幅进一步收窄，自(\d{4})年(\d{1,2})月份的同比下降" + NUM + r"%收窄到" + NUM + "%", t)
    if m:
        r["pig_yoy"] = -float(m.group(4))
        r["note"] = f"{m.group(1)}-{int(m.group(2)):02d}同比-{m.group(3)}%（同文）"
    cum = r"(?:1[～~—-]\d{1,2}月|一季度|上半年|前三季度)[^。]{0,60}。?[^。]{0,40}?"
    m = (re.search(cum + r"猪饲料产量" + NUM + r"万吨，同比(增长|下降)" + NUM + "%", t)
         or re.search(cum + r"猪、蛋禽、肉禽饲料产量分别为" + NUM + r"万吨[^。]*?同比分别(增长|下降)" + NUM + "%", t))
    if m:
        r["cum_pig_10kt"], r["cum_pig_yoy"] = float(m.group(1)), signed(m.group(2), m.group(3))
    for stage, key in (("母猪", "sow"), ("仔猪", "piglet"), ("育肥猪", "finishing")):
        m = re.search(stage + r"饲料(?:产量)?同比(?:大幅)?(增长|下降)" + NUM + "%", t)
        if m:
            r[key + "_yoy"] = signed(m.group(1), m.group(2))
    return r


STAGE_NAMES = {"仔猪": "piglet", "母猪": "sow", "育肥猪": "finishing"}


def parse_stage(t):
    """Pig total and the 仔猪/母猪/育肥猪 YoY sentence (any order) from an annual / H1 / Q1-Q3 text."""
    r = {}
    m = re.search(r"猪饲料(?:总)?产量(?:达|为)?" + NUM + r"万吨[，、](?:同比)?(增长|下降)" + NUM + "%", t) or \
        re.search(r"猪饲料" + NUM + r"万吨，同比(增长|下降)" + NUM + "%", t) or \
        re.search(r"猪饲料产量[^。]{0,12}产量达" + NUM + r"万吨，同比(增长|下降)" + NUM + "%", t)
    if m:
        r["pig_10kt"], r["pig_yoy"] = float(m.group(1)), signed(m.group(2), m.group(3))
    for nm, key in STAGE_NAMES.items():
        m = re.search(nm + r"饲料[^；。]{0,80}?一季度累计(增长|下降)" + NUM + "%", t)
        if m:
            r[key + "_yoy"] = signed(m.group(1), m.group(2))
    m = re.search(r"((?:仔猪|母猪|育肥猪)(?:饲料)?、(?:仔猪|母猪|育肥猪)(?:饲料)?、(?:仔猪|母猪|育肥猪))饲料(?:产量)?"
                  r"(?:同比)?分别(增长|下降)" + NUM + "%、" + NUM + "%、" + NUM + "%", t)
    if m:
        names = re.findall(r"仔猪|母猪|育肥猪", m.group(1))
        for nm, v in zip(names, (m.group(3), m.group(4), m.group(5))):
            r[STAGE_NAMES[nm] + "_yoy"] = signed(m.group(2), v)
        r["stage_sentence"] = m.group(0)[:60]
    return r


# ---------------------------------------------------------------------------
# chart digitising
# ---------------------------------------------------------------------------
def _mask(a, rgb, tol):
    return np.sqrt(((a - np.array(rgb)) ** 2).sum(-1)) < tol


def _peaks(counts, n, sep):
    c = np.convolve(counts, np.ones(5) / 5, mode="same").astype(float)
    out = []
    for _ in range(n):
        i = int(np.argmax(c))
        if c[i] <= 0:
            break
        out.append(i)
        c[max(0, i - sep):i + sep + 1] = -1
    return sorted(out)


def _label_rows(a, xmax, n):
    """Vertical centres of the y-axis tick labels (the n lowest text clusters left of the plot)."""
    dark = a[:, :xmax].max(-1) < 175
    for x in np.where(dark.mean(0) > 0.5)[0]:
        dark[:, max(0, x - 3): x + 4] = False
    for y in np.where(dark.mean(1) > 0.6)[0]:
        dark[max(0, y - 3): y + 4, :] = False
    groups = []
    for r in np.where(dark.sum(1) > 0)[0]:
        if groups and r - groups[-1][-1] <= 3:
            groups[-1].append(r)
        else:
            groups.append([r])
    groups = [g for g in groups if 5 <= len(g) <= 25]
    return [float((g[0] + g[-1]) / 2) for g in groups][-n:]


def digitize_chart(name, c):
    b = fetch(urljoin(c["page"], c["img"]), f"{SUB}/img", name=f"{name}_{c['img']}", ok_min_bytes=1000)
    fp = RAW / SUB / "img" / f"{name}_{c['img']}"
    if not b:
        return []
    im = Image.open(fp).convert("RGB")
    if c["crop"]:
        im = im.crop(c["crop"])
    a = np.asarray(im).astype(int)
    h, w = a.shape[:2]
    jpg = c["img"].endswith(".jpg")
    cols, tol = COLORS[jpg], (45 if jpg else 60)
    ref = _mask(a, cols[c["ref"]], tol)
    ref[int(h * 0.8):] = False
    xs = _peaks(ref.sum(0), 12, int(w / 30))
    bx, ax = np.polyfit(np.arange(len(xs)), xs, 1)
    labs = _label_rows(a, int(ax - 0.55 * bx), c["n"])
    if len(labs) != c["n"]:
        raise RuntimeError(f"{name}: found {len(labs)} y labels, expected {c['n']}")
    by, ay = np.polyfit(np.arange(len(labs)), labs, 1)
    lo, hi = int(ay - by * 0.6), int(ay + by * (c["n"] - 0.7))
    out = []
    for yr, cname in c["series"].items():
        m = _mask(a, cols[cname], tol)
        m[:lo], m[hi:] = False, False
        for k in range(12):
            xi = int(round(ax + bx * k))
            ys = np.where(m[:, max(0, xi - 1): xi + 2].any(1))[0]
            if len(ys) < 3:
                continue
            runs, cur = [], [ys[0]]
            for y in ys[1:]:
                if y - cur[-1] <= 2:
                    cur.append(y)
                else:
                    runs.append(cur)
                    cur = [y]
            runs.append(cur)
            run = max(runs, key=len)
            yc = (run[0] + run[-1]) / 2
            out.append(dict(chart=name, chart_release=c["release_date"], year=yr, month=k + 1,
                            value_10kt=round(c["top"] - (yc - ay) / by * c["step"], 1),
                            px_per_10kt=round(by / c["step"], 4), marker_px=len(run),
                            source=urljoin(c["page"], c["img"])))
    return out


# ---------------------------------------------------------------------------
def main():
    rel = list_releases()
    recs = []
    for r in rel.itertuples():
        kind, period = kind_period(r.title)
        t, date = page(r.url)
        rec = dict(kind=kind, period=period, title=r.title, release_date=date, url=r.url,
                   source_form="正文" if len(t) > 60 else "图片")
        if kind == "月度":
            rec.update(parse_monthly(t))
        elif kind != "其他":
            rec.update(parse_stage(t))
        recs.append(rec)
    df = pd.DataFrame(recs)
    base = df.drop_duplicates("url").set_index("url")
    rows = [base.loc[x["url"]].to_dict() | dict(
        url=x["url"], period=x["period"], total_10kt=x.get("total"), total_mom=None, total_yoy=None,
        pig_10kt=x["pig"], pig_mom=x.get("mom"), pig_yoy=x.get("yoy"),
        cum_pig_10kt=x.get("cum_pig"), cum_pig_yoy=x.get("cum_yoy"), doc_date=x.get("doc_date"),
        source_form="图片转录", note=x.get("note")) for x in IMAGE_TRANSCRIPTIONS]
    df = pd.concat([df[~df.url.isin({x["url"] for x in IMAGE_TRANSCRIPTIONS})], pd.DataFrame(rows)],
                   ignore_index=True)
    i = df.index[df.url == H1_2026["url"]]
    for k in ("pig", "piglet", "sow", "finishing"):
        col = "pig_10kt" if k == "pig" else f"{k}_yoy"
        df.loc[i, col] = H1_2026[k]
    df.loc[i, "pig_yoy"] = H1_2026["yoy"]
    df.loc[i, "source_form"] = "图片转录"
    df = df.drop_duplicates(["period", "kind", "pig_10kt", "pig_yoy"]).sort_values(["period", "kind"])
    cols = ["kind", "period", "release_date", "doc_date", "total_10kt", "total_mom", "total_yoy", "pig_10kt",
            "pig_mom", "pig_yoy", "cum_pig_10kt", "cum_pig_yoy", "piglet_yoy", "sow_yoy", "finishing_yoy",
            "stage_sentence", "source_form", "note", "title", "url"]
    df = df.reindex(columns=cols)
    write_csv(df, PROC / "cfia_feed_releases.csv")

    # chart readings -> revised monthly series
    readings = pd.DataFrame([x for n, c in CHARTS.items() for x in digitize_chart(n, c)])
    write_csv(readings, PROC / "cfia_pig_feed_chart_readings.csv")
    readings["month_key"] = readings.year.astype(str) + "-" + readings.month.map("{:02d}".format)
    # A chart released in a later calendar year than the data shows the final (revised) value; a same-year
    # chart shows a preliminary one. Markers squeezed to < 5 px are partly hidden behind another series and
    # read unreliably, so they are dropped whenever a fully visible reading of the same month exists.
    readings["vintage"] = np.where(readings.chart_release.str[:4].astype(int) > readings.year, "final", "prelim")
    full = readings.groupby("month_key").marker_px.transform("max") >= 8
    ok = readings[~((readings.marker_px < 5) & full)]
    fin = ok[ok.vintage == "final"].groupby("month_key").value_10kt
    pre = ok[ok.vintage == "prelim"].groupby("month_key").value_10kt
    rev = pd.DataFrame({"revised_10kt": fin.median(), "n_final_charts": fin.size(),
                        "final_spread_10kt": (fin.max() - fin.min()).round(1), "prelim_chart_10kt": pre.median()})
    rev["revised_basis"] = np.where(rev.revised_10kt.notna(), "终值图读数", None)
    late = rev.revised_10kt.isna() & rev.prelim_chart_10kt.notna()
    rev.loc[late, "revised_10kt"] = rev.loc[late, "prelim_chart_10kt"]
    rev.loc[late, "revised_basis"] = "当年图读数（未经年度修订）"
    first = df[(df.kind == "月度") & df.pig_10kt.notna() & ~df.period.str.contains("~")]
    first = first.set_index("period")[["pig_10kt", "pig_mom", "pig_yoy", "release_date", "doc_date", "url"]]
    first.columns = ["first_10kt", "first_mom", "first_yoy", "first_release_date", "first_doc_date", "first_url"]
    months = pd.period_range("2019-01", rev.index.max(), freq="M").astype(str)
    mon = pd.DataFrame(index=pd.Index(months, name="month")).join(rev).join(first)
    yoy_first = df[(df.kind == "月度") & df.pig_yoy.notna() & df.pig_10kt.isna()].set_index("period").pig_yoy
    mon.loc[mon.index.isin(yoy_first.index), "first_yoy"] = yoy_first
    hidden = mon.revised_10kt.isna() & mon.first_10kt.notna()  # marker hidden in every chart (2021-03)
    for m in mon.index[hidden]:
        nb = (mon.revised_10kt / mon.first_10kt).rolling(3, center=True, min_periods=2).mean()[m]
        mon.loc[m, ["revised_10kt", "revised_basis"]] = [round(mon.first_10kt[m] * nb, 1), "首发值×相邻月修订比（插补）"]
    mon["revised_yoy"] = (mon.revised_10kt / mon.revised_10kt.shift(12) - 1) * 100
    mon["revision_pct"] = (mon.revised_10kt / mon.first_10kt - 1) * 100
    write_csv(mon.reset_index().round(2), PROC / "cfia_pig_feed_monthly.csv")

    # stage table
    st = df[df.kind.isin(["年度", "半年", "前三季度", "一季度", "年度分析"]) &
            (df.piglet_yoy.notna() | df.sow_yoy.notna())].copy()
    st = pd.concat([st, pd.DataFrame([dict(kind="累计", period=x["period"], release_date=x["release_date"],
                                           pig_10kt=x["pig"], pig_yoy=x["yoy"], piglet_yoy=x["piglet"],
                                           sow_yoy=x["sow"], finishing_yoy=x["finishing"],
                                           source_form=x["source_form"], note=x["note"], url=x["url"])
                                      for x in STAGE_OTHER])], ignore_index=True)
    st = st[["period", "kind", "release_date", "pig_10kt", "pig_yoy", "piglet_yoy", "sow_yoy", "finishing_yoy",
             "source_form", "note", "url"]].sort_values("period")
    write_csv(st, PROC / "cfia_pig_feed_stage.csv")

    an = df[df.kind == "年度"].sort_values("release_date")[["period", "release_date", "pig_10kt", "pig_yoy", "url"]]
    an = an.rename(columns={"period": "year"}).drop_duplicates("year")
    write_csv(an.sort_values("year"), PROC / "cfia_pig_feed_annual.csv")
    print(df[["kind", "period", "release_date", "pig_10kt", "pig_mom", "pig_yoy", "cum_pig_10kt", "cum_pig_yoy",
              "piglet_yoy", "sow_yoy", "finishing_yoy", "source_form"]].to_string())


if __name__ == "__main__":
    main()
