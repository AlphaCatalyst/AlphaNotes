"""Shared helpers for the industry-supply / spot-price crawlers.

Every downloaded page is cached verbatim under data/raw/industry/<subdir>/ and logged in
<subdir>/_manifest.csv (url, local file, HTTP status, fetch time, sha1) so each number in the
processed tables can be traced back to the exact page it was parsed from. Nothing is ever
imputed here: a failed fetch returns None and callers must record the gap.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "industry"
PROC = ROOT / "data" / "processed"
RESEARCH = ROOT / "research"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

_local = threading.local()
_manifest_lock = threading.Lock()


def session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
        _local.s = s
    return s


def url_to_name(url: str) -> str:
    """Readable, filesystem-safe cache name derived from the URL."""
    p = urlparse(url)
    path = p.path.strip("/") or "index"
    name = (p.netloc + "__" + path.replace("/", "__"))
    if p.query:
        name += "__" + hashlib.md5(p.query.encode()).hexdigest()[:10]
    name = re.sub(r"[^0-9A-Za-z._\-]", "_", name)
    if not re.search(r"\.(s?html?|json|pdf|xlsx?|docx?|txt|js)$", name, re.I):
        name += ".html"
    return name[:200]


def _log(subdir: Path, row: dict):
    mf = subdir / "_manifest.csv"
    with _manifest_lock:
        new = not mf.exists()
        with mf.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["url", "file", "status", "fetched_at", "bytes", "sha1"])
            if new:
                w.writeheader()
            w.writerow(row)


WAF_MARKERS = (b"waf_text_captcha", "访问验证</title>".encode())


class WafBlocked(RuntimeError):
    pass


def is_waf(content: bytes) -> bool:
    head = content[:6000]
    return any(m in head for m in WAF_MARKERS)


HOST_GAP = {"www.stats.gov.cn": 2.5}
_host_last: dict[str, float] = {}
_host_lock = threading.Lock()


def throttle(url: str):
    """Minimum spacing between requests to rate-limited hosts (shared by all callers)."""
    host = urlparse(url).netloc
    gap = HOST_GAP.get(host)
    if not gap:
        return
    with _host_lock:
        wait = gap - (time.time() - _host_last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _host_last[host] = time.time()


def fetch(url: str, subdir: str, name: str | None = None, force: bool = False, timeout: int = 40,
          retries: int = 3, method: str = "GET", data=None, headers=None, sleep: float = 0.25,
          ok_min_bytes: int = 200) -> bytes | None:
    """Download url into RAW/subdir (cached). Returns raw bytes or None on failure.

    Raises WafBlocked when the site answers with its captcha page, so callers can stop instead of
    hammering a site that has rate-limited us. www.stats.gov.cn also answers valid URLs with a plain
    nginx 404 while it is throttling us, so 404s from that host are retried after a long pause.
    """
    d = RAW / subdir
    d.mkdir(parents=True, exist_ok=True)
    fp = d / (name or url_to_name(url))
    if fp.exists() and not force and fp.stat().st_size >= ok_min_bytes and not is_waf(fp.read_bytes()):
        return fp.read_bytes()
    last = None
    soft404 = urlparse(url).netloc in HOST_GAP
    for i in range(retries):
        throttle(url)
        try:
            if method == "GET":
                r = session().get(url, timeout=timeout, headers=headers)
            else:
                r = session().post(url, data=data, timeout=timeout, headers=headers)
            if r.status_code in (200, 302) and is_waf(r.content):
                _log(d, dict(url=url, file="", status="WAF_CAPTCHA",
                             fetched_at=dt.datetime.now().isoformat(timespec="seconds"), bytes=0, sha1=""))
                raise WafBlocked(url)
            if r.status_code == 200 and len(r.content) >= ok_min_bytes:
                fp.write_bytes(r.content)
                _log(d, dict(url=url, file=fp.name, status=r.status_code,
                             fetched_at=dt.datetime.now().isoformat(timespec="seconds"),
                             bytes=len(r.content), sha1=hashlib.sha1(r.content).hexdigest()))
                time.sleep(sleep)
                return r.content
            last = f"HTTP {r.status_code} ({len(r.content)} bytes)"
            if r.status_code == 404 and soft404:
                time.sleep(30 * (i + 1))
                continue
            if r.status_code == 404 and i >= 1:
                break
        except WafBlocked:
            raise
        except Exception as e:  # noqa: BLE001
            last = repr(e)
        time.sleep(1.5 * (i + 1))
    _log(d, dict(url=url, file="", status=str(last)[:80],
                 fetched_at=dt.datetime.now().isoformat(timespec="seconds"), bytes=0, sha1=""))
    return None


def decode(b: bytes) -> str:
    if b is None:
        return ""
    if b[:3] == b"\xef\xbb\xbf":
        b = b[3:]
    for enc in ("utf-8", "gb18030"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def soup(b: bytes | str) -> BeautifulSoup:
    return BeautifulSoup(b if isinstance(b, str) else decode(b), "lxml")


def flat_text(s: BeautifulSoup) -> str:
    """Page text with all whitespace removed (government pages split numbers across tags)."""
    for t in s(["script", "style"]):
        t.decompose()
    return re.sub(r"\s+", "", s.get_text(""))


def table_rows(tb) -> list[list[str]]:
    rows = []
    for tr in tb.find_all("tr"):
        cells = [re.sub(r"\s+", "", c.get_text("")) for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    return rows


def to_float(x):
    if x is None:
        return None
    x = str(x).strip().replace(",", "").replace("，", "")
    m = re.search(r"-?\d+(?:\.\d+)?", x)
    return float(m.group(0)) if m else None


# ---------------------------------------------------------------------------
# so-gov.cn site search (used by www.moa.gov.cn and www.stats.gov.cn)
# ---------------------------------------------------------------------------
SITE_MOA = "bm21000007"
SITE_NBS = "bm36000002"
_REFERER = {SITE_MOA: "https://www.moa.gov.cn", SITE_NBS: "https://www.stats.gov.cn"}
_IE = [str(uuid.uuid4())]


def sogov_search(site: str, qt: str, start: str | None = None, end: str | None = None,
                 key_place: int = 1, max_pages: int = 10, sort: str = "dateDesc",
                 cache_subdir: str = "_search") -> list[dict]:
    """Query the government site search used by MOA/NBS. Successful responses are cached as JSON.

    The API takes a browser-generated user id ("ie", a UUID kept in localStorage) and disables ids
    that send too many queries, so each process uses a random UUID, rotates it when disabled and
    never caches error responses. Returns de-duplicated dicts: url, title, date, summary.
    """
    out, seen = [], set()
    for page in range(1, max_pages + 1):
        params = dict(siteCode=site, qt=qt, page=page, pageSize=20, sort=sort, keyPlace=key_place)
        if start or end:
            params.update(timeOption=2, startDateStr=start or "", endDateStr=end or "")
        key = hashlib.md5(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        d = RAW / cache_subdir
        d.mkdir(parents=True, exist_ok=True)
        fp = d / f"sogov_{site}_{key}.json"
        j = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else None
        if j is not None and j.get("ok") is not True:
            j = None
        if j is None:
            for i in range(4):
                try:
                    r = session().post("https://api.so-gov.cn/query/s", data=dict(params, ie=_IE[0]),
                                       timeout=40,
                                       headers={"Referer": _REFERER[site] + "/", "Origin": _REFERER[site]})
                    j = r.json()
                except Exception:  # noqa: BLE001
                    j = None
                if j is not None and j.get("ok") is True:
                    break
                if j is not None and j.get("code") == -101:
                    _IE[0] = str(uuid.uuid4())
                time.sleep(3 * (i + 1))
                j = None
            if j is None:
                break
            j["_params"] = params
            fp.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
            time.sleep(0.9)
        docs = j.get("resultDocs") or []
        for x in docs:
            dd = x.get("data") or {}
            u = dd.get("url")
            if not u or u in seen:
                continue
            seen.add(u)
            mv = dd.get("myValues") or {}
            out.append(dict(url=u, title=dd.get("titleO") or re.sub(r"<[^>]+>", "", dd.get("title") or ""),
                            date=dd.get("docDate"), summary=mv.get("QUICKDESCRIPTION") or ""))
        if len(docs) < 20:
            break
    return out


def write_csv(df, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"wrote {path} rows={len(df)}")
