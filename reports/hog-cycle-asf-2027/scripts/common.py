"""Shared data-access helpers for the pig-cycle research project.

All raw downloads are cached under data/raw so every number in the report can be
re-derived offline. Functions never fill missing values: a failed fetch returns
None / empty and the caller must record the gap.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

S = requests.Session()
S.headers.update(UA)


def _get(url, params=None, timeout=30, retries=3, **kw):
    last = None
    for i in range(retries):
        try:
            r = S.get(url, params=params, timeout=timeout, **kw)
            if r.status_code == 200:
                return r
            last = RuntimeError(f"HTTP {r.status_code} {url}")
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(1.5 * (i + 1))
    raise last


# ----------------------------------------------------------------------------
# Stocks
# ----------------------------------------------------------------------------

def em_secid(code: str) -> str:
    """East Money secid. SH: 1.xxxxxx, SZ/BJ: 0.xxxxxx, HK: 116.xxxxx"""
    if code.endswith(".HK") or (len(code) == 5 and code.isdigit()):
        return "116." + code.replace(".HK", "").zfill(5)
    return ("1." if code.startswith(("6", "9")) else "0.") + code


def em_kline(code: str, fqt: int = 2, beg: str = "19900101", end: str = "20500101"):
    """Daily K-line from East Money. fqt: 0 raw, 1 forward-adjusted, 2 backward-adjusted.

    Returns list of dicts: date, open, close, high, low, volume, amount, turnover.
    """
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = dict(secid=em_secid(code), fields1="f1,f2,f3,f4,f5,f6",
                  fields2="f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                  klt=101, fqt=fqt, beg=beg, end=end, lmt=100000)
    r = _get(url, params=params)
    d = r.json().get("data") or {}
    out = []
    for line in d.get("klines") or []:
        p = line.split(",")
        out.append(dict(date=p[0], open=float(p[1]), close=float(p[2]), high=float(p[3]),
                        low=float(p[4]), volume=float(p[5]), amount=float(p[6]),
                        amplitude=float(p[7]), pct=float(p[8]), chg=float(p[9]),
                        turnover=float(p[10]) if p[10] not in ("", "-") else None))
    return d.get("name"), out


def tx_kline(code: str, fq: str = "hfq", beg="2006-01-01", end="2026-12-31"):
    """Tencent daily K-line (cross-check source). fq: '', 'qfq', 'hfq'."""
    pre = "sh" if code.startswith(("6", "9")) else "sz"
    sym = pre + code
    out = []
    start = dt.date.fromisoformat(beg)
    stop = dt.date.fromisoformat(end)
    # Tencent caps ~640-2000 rows per call; walk forward in 2-year chunks.
    while start <= stop:
        chunk_end = min(stop, start + dt.timedelta(days=730))
        url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param="
               f"{sym},day,{start},{chunk_end},2000,{fq}")
        try:
            r = _get(url, retries=2)
            d = r.json().get("data", {}).get(sym, {})
        except Exception:  # noqa: BLE001  (Tencent answers 501 for ranges before listing)
            d = {}
        if not isinstance(d, dict):
            d = {}
        key = (fq + "day") if fq else "day"
        rows = d.get(key) or d.get("day") or []
        for p in rows:
            out.append(dict(date=p[0], open=float(p[1]), close=float(p[2]), high=float(p[3]),
                            low=float(p[4]), volume=float(p[5])))
        start = chunk_end + dt.timedelta(days=1)
        time.sleep(0.2)
    # de-dup
    seen, res = set(), []
    for x in out:
        if x["date"] not in seen:
            seen.add(x["date"])
            res.append(x)
    return res


# ----------------------------------------------------------------------------
# East Money F10 financial statements (consolidated, report period values)
# ----------------------------------------------------------------------------

F10 = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/"


def em_code(code: str) -> str:
    return ("SH" if code.startswith(("6", "9")) else "SZ") + code


def em_report_dates(code: str, kind: str = "zcfzb"):
    r = _get(F10 + f"{kind}DateAjaxNew", params=dict(companyType=4, reportDateType=0, code=em_code(code)))
    return [x["REPORT_DATE"][:10] for x in r.json().get("data", [])]


def em_statement(code: str, kind: str = "zcfzb", dates=None, company_type: int = 4):
    """kind: zcfzb (balance sheet), lrb (income), xjllb (cash flow).

    reportType=1 means cumulative report-period values (e.g. H1 = Jan-Jun).
    """
    if dates is None:
        dates = em_report_dates(code, kind)
    out = []
    for i in range(0, len(dates), 5):
        chunk = ",".join(dates[i:i + 5])
        r = _get(F10 + f"{kind}AjaxNew", params=dict(companyType=company_type, reportDateType=0,
                                                     reportType=1, dates=chunk, code=em_code(code)))
        out.extend(r.json().get("data", []) or [])
        time.sleep(0.3)
    return out


# ----------------------------------------------------------------------------
# cninfo announcements
# ----------------------------------------------------------------------------

_ORG = None


def cninfo_org(code: str) -> str:
    global _ORG
    if _ORG is None:
        r = _get("http://www.cninfo.com.cn/new/data/szse_stock.json")
        _ORG = {x["code"]: x["orgId"] for x in r.json()["stockList"]}
    return _ORG[code]


def cninfo_query(code: str, se_date: str = "2018-01-01~2026-12-31", searchkey: str = "",
                 category: str = "", max_pages: int = 60):
    """List announcements for one stock. Returns list of dicts with date/title/url.

    category examples: category_ndbg_szsh (annual), category_bndbg_szsh (semi-annual),
    category_yjdbg_szsh (Q1), category_sjdbg_szsh (Q3), category_dqgg (日常经营)...
    """
    column = "sse" if code.startswith("6") else "szse"
    org = cninfo_org(code)
    res = []
    for page in range(1, max_pages + 1):
        data = dict(stock=f"{code},{org}", tabName="fulltext", pageSize=30, pageNum=page,
                    column=column, category=category, plate="", seDate=se_date,
                    searchkey=searchkey, secid="", sortName="", sortType="", isHLtitle="true")
        for attempt in range(3):
            try:
                r = S.post("http://www.cninfo.com.cn/new/hisAnnouncement/query", data=data, timeout=30)
                d = r.json()
                break
            except Exception:  # noqa: BLE001
                time.sleep(2 * (attempt + 1))
        else:
            break
        anns = d.get("announcements") or []
        for a in anns:
            res.append(dict(code=code, sec_name=a.get("secName"),
                            date=dt.datetime.fromtimestamp(a["announcementTime"] / 1000).strftime("%Y-%m-%d"),
                            title=re.sub(r"<.*?>", "", a.get("announcementTitle") or ""),
                            url="https://static.cninfo.com.cn/" + a["adjunctUrl"],
                            ann_id=a.get("announcementId")))
        if not d.get("hasMore"):
            break
        time.sleep(0.35)
    return res


def fetch_pdf_text(url: str, cache_dir: Path | None = None, max_pages: int | None = None) -> str:
    """Download a PDF (cached by URL hash) and return extracted text (pypdf; fast)."""
    cache_dir = cache_dir or (RAW / "ann")
    cache_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(url.encode()).hexdigest()[:16]
    pdf_path = cache_dir / f"{h}.pdf"
    txt_path = cache_dir / f"{h}.txt"
    if txt_path.exists() and (max_pages is None):
        return txt_path.read_text(encoding="utf-8")
    if not pdf_path.exists():
        r = _get(url, timeout=90)
        pdf_path.write_bytes(r.content)
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(pdf_path))
        pages = reader.pages if max_pages is None else reader.pages[:max_pages]
        text = "\n".join((p.extract_text() or "") for p in pages)
    except Exception as e:  # noqa: BLE001
        text = f"[PDF_PARSE_ERROR] {e}"
    if max_pages is None:
        txt_path.write_text(text, encoding="utf-8")
    (cache_dir / f"{h}.url").write_text(url)
    return text


def save_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
