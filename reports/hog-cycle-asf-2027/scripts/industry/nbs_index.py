"""Locate NBS 最新发布 release pages (www.stats.gov.cn/sj/zxfb/) without hammering the site.

data.stats.gov.cn is blocked (403) from this machine, so NBS numbers come from release pages.
www.stats.gov.cn itself sits behind a WAF that answers with a captcha after a few hundred quick
requests, so this module:
  1. collects release URLs/titles/dates from the government site-search API (api.so-gov.cn, a
     different host) -> anchors;
  2. for releases the search index misses, uses the fact that releases published before 2023-02
     were migrated to /sj/zxfb/202302/t20230203_<id>.html with ids in original publication order:
     the id is interpolated from anchor dates and nearby ids are probed one by one (head only,
     >=1.5 s apart) until a title matches.
Probe results are cached in data/raw/industry/nbs/_probe_cache.csv.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ind_common import RAW, SITE_NBS, WafBlocked, decode, is_waf, session, sogov_search, throttle  # noqa: E402

SUB = "nbs"
PROBE_CACHE = RAW / SUB / "_probe_cache.csv"
ANCHORS = RAW / SUB / "_search_anchors.csv"
MIG = "https://www.stats.gov.cn/sj/zxfb/202302/t20230203_{}.html"
CONTROL = MIG.format(1899020)  # 2015年民间固定资产投资增长10.1%, a small page known to exist


def _mig_id(url: str):
    m = re.search(r"/sj/zxfb/202302/t20230203_(\d+)\.html", url)
    return int(m.group(1)) if m else None


def collect_anchors(force: bool = False) -> pd.DataFrame:
    if ANCHORS.exists() and not force:
        return pd.read_csv(ANCHORS)
    rows = []
    queries = ["流通领域重要生产资料市场价格变动情况", "居民消费价格", "国民经济", "经济运行", "猪牛羊禽肉产量",
               "生猪存栏", "工业生产者出厂价格", "采购经理指数"]
    for y in range(2016, 2027):
        for q in queries:
            for half in [("01-01", "06-30"), ("07-01", "12-31")]:
                docs = sogov_search(SITE_NBS, q, f"{y}-{half[0]}", f"{y}-{half[1]}", key_place=1 if q not in (
                    "猪牛羊禽肉产量", "生猪存栏") else 0, max_pages=8, cache_subdir=f"{SUB}/search")
                for d in docs:
                    u = d["url"]
                    if "www.stats.gov.cn/sj/zxfb/" not in u:
                        continue
                    rows.append(dict(id=_mig_id(u), url=u.replace("http://", "https://"), title=d["title"],
                                     date=d["date"], via="search"))
    df = pd.DataFrame(rows).drop_duplicates("url")
    df.to_csv(ANCHORS, index=False)
    print(f"anchors: {len(df)} (migrated ids: {df.id.notna().sum()})")
    return df


STATIC = RAW / SUB / "_static_list.csv"


def static_list(force: bool = False) -> pd.DataFrame:
    """All items of the static 最新发布 list (reaches back to ~2021-10), fetched >=2 s apart."""
    from urllib.parse import urljoin

    from ind_common import fetch, soup
    if STATIC.exists() and not force:
        return pd.read_csv(STATIC)
    base = "https://www.stats.gov.cn/sj/zxfb/"
    b = fetch(base, f"{SUB}/lists", name="zxfb_index.html", force=True, sleep=2.0)
    m = re.search(r'createPageHTML\((\d+),\s*0,\s*"index"', decode(b))
    n = int(m.group(1)) if m else 1
    rows = []
    for p in range(n):
        u = base if p == 0 else f"{base}index_{p}.html"
        bb = b if p == 0 else fetch(u, f"{SUB}/lists", name=f"zxfb_index_{p}.html", sleep=2.0)
        if not bb:
            continue
        for li in soup(bb).find_all("li"):
            a = li.find("a", href=re.compile(r"t20\d{6}_\d+\.html"))
            if not a:
                continue
            sp = li.find("span")
            dm = re.search(r"(20\d\d-\d\d-\d\d)", sp.get_text() if sp else "")
            url = urljoin(u, a["href"])
            rows.append(dict(id=_mig_id(url), url=url, title=(a.get("title") or a.get_text(strip=True)).strip(),
                             date=dm.group(1) if dm else None, via="static_list"))
    df = pd.DataFrame(rows).drop_duplicates("url")
    df.to_csv(STATIC, index=False)
    print(f"static list: {n} pages, {len(df)} items, {df.date.min()} .. {df.date.max()}")
    return df


def all_known(anchors: pd.DataFrame | None = None) -> pd.DataFrame:
    """Anchors from search + static list + successful id probes, one row per URL."""
    parts = [collect_anchors() if anchors is None else anchors]
    if STATIC.exists():
        parts.append(pd.read_csv(STATIC))
    cache = _load_probe_cache()
    if cache:
        pc = pd.DataFrame(cache.values())
        pc = pc[pc.title.fillna("") != ""].assign(via="id_probe")[["id", "url", "title", "date", "via"]]
        parts.append(pc)
    return pd.concat(parts, ignore_index=True).drop_duplicates("url")


def _load_probe_cache() -> dict:
    if not PROBE_CACHE.exists():
        return {}
    df = pd.read_csv(PROBE_CACHE)
    return {int(r.id): dict(id=int(r.id), url=r.url, title=r.title if isinstance(r.title, str) else "",
                            date=r.date if isinstance(r.date, str) else None, status=r.status)
            for r in df.itertuples()}


_probe = None


def _head(url: str):
    """(status_code, first ~24 KB) of url, honouring the per-host throttle."""
    throttle(url)
    with session().get(url, timeout=40, stream=True) as r:
        buf = b""
        if r.status_code == 200:
            for chunk in r.iter_content(8192):
                buf += chunk
                if len(buf) > 24000:
                    break
        return r.status_code, buf


def probe(i: int) -> dict:
    """Head-only fetch of a migrated release id (cached).

    While throttling, www.stats.gov.cn answers existing pages with a plain 404, so a 404 is only
    accepted after a page known to exist (CONTROL) loads; otherwise wait and retry.
    """
    global _probe
    if _probe is None:
        _probe = _load_probe_cache()
    if i in _probe:
        return _probe[i]
    url = MIG.format(i)
    rec = dict(id=i, url=url, title="", date=None, status="")
    for attempt in range(5):
        code, buf = _head(url)
        if code == 404:
            ccode, _ = _head(CONTROL)
            if ccode == 200:
                rec["status"] = "404"
                break
            time.sleep(60 * (attempt + 1))
            continue
        if is_waf(buf):
            raise WafBlocked(url)
        html = decode(buf)
        t = re.search(r"<title>(.*?)</title>", html, re.S)
        rec["title"] = re.sub(r"\s*-\s*国家统计局\s*$", "", t.group(1).strip()) if t else ""
        m = re.search(r"(20\d\d)/(\d\d)/(\d\d)", html)
        rec["date"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
        rec["status"] = str(code)
        break
    if not rec["status"]:
        return rec
    _probe[i] = rec
    new = not PROBE_CACHE.exists()
    with PROBE_CACHE.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "url", "title", "date", "status"])
        if new:
            w.writeheader()
        w.writerow(rec)
    return rec


def known_points(anchors: pd.DataFrame) -> pd.DataFrame:
    pts = anchors[anchors.id.notna() & anchors.date.notna()][["id", "date"]].copy()
    cache = _load_probe_cache()
    if cache:
        pc = pd.DataFrame(cache.values())
        pc = pc[pc.date.notna()][["id", "date"]]
        pts = pd.concat([pts, pc])
    pts["id"] = pts["id"].astype(int)
    pts["d"] = pd.to_datetime(pts["date"])
    return pts.drop_duplicates("id").sort_values("id")


def estimate_id(pts: pd.DataFrame, date: str) -> int:
    d = pd.Timestamp(date)
    before = pts[pts.d <= d]
    after = pts[pts.d >= d]
    if before.empty:
        return int(after.id.iloc[0])
    if after.empty:
        return int(before.id.iloc[-1])
    b, a = before.iloc[-1], after.iloc[0]
    if a.d == b.d:
        return int(b.id)
    frac = (d - b.d) / (a.d - b.d)
    return int(round(b.id + frac * (a.id - b.id)))


def find_release(anchors: pd.DataFrame, title_re: str, date_lo: str, date_hi: str,
                 max_probes: int = 40, exclude: set | None = None) -> dict | None:
    """Find a migrated release whose title matches title_re and date within [date_lo, date_hi]."""
    exclude = exclude or set()
    pat = re.compile(title_re)
    hit = anchors[anchors.title.fillna("").str.contains(title_re, regex=True)
                  & (anchors.date >= date_lo) & (anchors.date <= date_hi) & ~anchors.url.isin(exclude)]
    if len(hit):
        r = hit.sort_values("date").iloc[0]
        return dict(id=r.id, url=r.url, title=r.title, date=r.date, via="search")
    cache = _load_probe_cache()
    for rec in sorted(cache.values(), key=lambda r: r["id"]):
        if (rec["date"] and date_lo <= rec["date"] <= date_hi and pat.search(rec["title"] or "")
                and rec["url"] not in exclude):
            return dict(rec, via="id_probe")
    pts = known_points(anchors)
    lo_id, hi_id = estimate_id(pts, date_lo), estimate_id(pts, date_hi)
    center = (lo_id + hi_id) // 2
    order = [center]
    for k in range(1, max_probes):
        order += [center + k, center - k]
    n = 0
    for i in order:
        if n >= max_probes:
            break
        rec = probe(i)
        n += rec["id"] not in cache
        if (rec["date"] and date_lo <= rec["date"] <= date_hi and pat.search(rec["title"] or "")
                and rec["url"] not in exclude):
            return dict(rec, via="id_probe")
    return None


if __name__ == "__main__":
    a = collect_anchors(force="--force" in sys.argv)
    print(f"anchors {len(a)}")
    st = static_list(force="--force" in sys.argv)
