"""Issue #8: which hog and livestock stocks gained new institutional holders in Q3 2026, and how much money.

Universe: 申万二级“养殖业” (22, of which 申万三级“生猪养殖” 11); the seven hog-heavy names of the report's
screen that 申万 files under feed or meat (新希望 唐人神 大北农 天康 傲农 金新农 华统); the rest of 聚源概念“猪肉”
(feed, slaughter, processed meat) as an extension.

  fetch   westock-data (腾讯自选股 CLI): latest top-10 holders per stock; the 2026 Q3 and H1 reports
          (PDF -> text, pypdf); 6-30 and 9-30 quotes; units of the ETFs that entered a top-10 list.
          Cached under research/q3_institutions/_raw/ (local only); cached files are not fetched again.
  build   Q3 top-10 float holders (westock when it already shows 2026-09-30, else parsed from the report)
          against the H1 report's top-10 holders and top-10 float holders: a holder is new when its name
          appears in neither H1 list. Every new institution is looked up in the Q3 report text (name and
          share count). Sizes at the 9-30 close: confirmed Q3 addition = Q3 shares - H1 10th-place float
          holding; an exit's confirmed minimum sale = H1 shares - Q3 10th-place float holding.

Reports published after CUTOFF are ignored, so a later fetch reproduces the same answer.
Outputs: data/processed/issues/inst_*.csv (derived only).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "research" / "q3_institutions" / "_raw"
OUT = ROOT / "data" / "processed" / "issues"

Q3, H1 = "2026-09-30", "2026-06-30"
CUTOFF = "2026-10-29 23:59:59"

UNIVERSE = [  # westock symbol, name, group
    ("sz002714", "牧原股份", "生猪"), ("sz300498", "温氏股份", "生猪"), ("sz002124", "天邦食品", "生猪"),
    ("sz000735", "罗牛山", "生猪"), ("sz002157", "正邦科技", "生猪"), ("sz000048", "京基智农", "生猪"),
    ("sh603717", "天域生物", "生猪"), ("sz001201", "东瑞股份", "生猪"), ("sh600975", "新五丰", "生猪"),
    ("sh605296", "神农集团", "生猪"), ("sh603477", "巨星农牧", "生猪"),
    ("sz000876", "新希望", "生猪（样本补充）"), ("sz002567", "唐人神", "生猪（样本补充）"),
    ("sz002385", "大北农", "生猪（样本补充）"), ("sz002100", "天康生物", "生猪（样本补充）"),
    ("sh603363", "傲农生物", "生猪（样本补充）"), ("sz002548", "金新农", "生猪（样本补充）"),
    ("sz002840", "华统股份", "生猪（样本补充）"),
    ("sz300313", "天山生物", "养殖"), ("sz002299", "圣农发展", "养殖"), ("sz002746", "仙坛股份", "养殖"),
    ("sz002321", "华英农业", "养殖"), ("sh600965", "*ST福成", "养殖"), ("sz301116", "益客食品", "养殖"),
    ("sz002458", "益生股份", "养殖"), ("sz300761", "立华股份", "养殖"), ("sz002234", "民和股份", "养殖"),
    ("sz002982", "湘佳股份", "养殖"), ("sz300967", "晓鸣股份", "养殖"),
    ("sz002726", "ST龙大", "产业链"), ("bj920970", "大禹生物", "产业链"), ("sz002661", "克明食品", "产业链"),
    ("sz000702", "正虹科技", "产业链"), ("sh603151", "邦基科技", "产业链"), ("sz301156", "美农生物", "产业链"),
    ("sh600073", "光明肉业", "产业链"), ("sz001366", "播恩集团", "产业链"), ("sz000895", "双汇发展", "产业链"),
    ("sz002515", "金字火腿", "产业链"), ("sh603609", "禾丰股份", "产业链"), ("sz000529", "广弘控股", "产业链"),
    ("sz000860", "顺鑫农业", "产业链"), ("sz002330", "得利斯", "产业链"), ("sz002311", "海大集团", "产业链"),
]
# ETFs met in the top-10 lists, keyed by a fragment of the holder name.
ETFS = {"国泰中证畜牧养殖": "sz159865", "鹏华中证畜牧养殖": "sz159867", "招商中证畜牧养殖": "sh516670",
        "南方中证全指房地产": "sh512200", "博时中证红利低波动100": "sz159307"}

# Checked by hand against the report text: rows glued to a page header or a neighbouring row by the PDF
# text layer, which then fail the name match.
FALSE_NEW = {("sz002714", "牧原食品集团股份有限公司回购专用证券账户 2"),
             ("sz002714", "二期员工持股计划中国工商银行股份有限公司－中证主要消费交易型开放式指数证券投资基金"),
             ("sz002100", "浙商银行股份有限公司-国泰中证畜牧养殖交易型开放式指数证券投资基金")}
FALSE_EXIT = {("sz002714", "中证主要消费"), ("sz002100", "新疆天达生物"), ("sz002515", "郑庆昇")}
# Court-ordered transfer of the controlling holder's shares to offset its debt (ST龙大 notice 2026-149): listed, not counted.
NOT_COUNTED = {("sz002726", "乐山市商业银行股份有限公司成都分行"): "银行(司法划转抵债)"}
# BSE reports number their rows (序号) and the float-table parser does not read them; read from the H1 report.
BSE_H1 = {"bj920970": dict(cutoff=627604, exits=[("全成正宇基金", 627604)])}

CJK = r"\u4e00-\u9fff"
NUM = r"\d{1,3}(?:,\d{3})+|\d+"
TYPE = r"人民币普通股|境外上市外资股|境内上市外资股"
TITLE = re.compile(r"(\d{4}\s*年\s*(半年度|第?[一二三]季度|年度)报告(全文)?(摘要)?)\s*$")
PAGE = re.compile(r"^\s*\d+\s*(/\s*\d+)?\s*$")
H_TOP = re.compile(r"前\s*(10|十)\s*名股东持股情况")
H_FLOAT = re.compile(r"前\s*(10|十)\s*名无限售条件(普通)?股东(持股)?情况")
END = re.compile(r"上述股东关联关系|名无限售条件(普通)?股东之|前\s*(10|十)\s*名股东中回购专"
                 r"|持股\s*5%以上(的)?股东|参与融资融券业务|前\s*(10|十)\s*名无限售条\s*$|前\s*(10|十)\s*名普通股股东参与")
FW = str.maketrans({"（": "(", "）": ")", "－": "-", "—": "-", "–": "-", "，": ",", "·": "", "・": "", "．": ".", "：": ":"})

INST_RULES = [
    ("北向(陆股通)", r"^香港中央结算有限公司$"),
    ("H股名义持有人", r"HKSCCNOMINEES|香港中央结算代理人"),
    ("社保基金", r"全国社保基金|全国社会保障基金|社保基金.{1,6}组合"),
    ("养老金/年金", r"基本养老保险基金|养老金|企业年金|职业年金"),
    ("国家队", r"中央汇金|中国证券金融|汇金资产"),
    ("保险", r"保险|人寿"),
    ("私募", r"私募|股权投资基金"),
    ("公募基金(ETF/指数)", r"交易型开放式指数|ETF|指数.*证券投资基金"),
    ("公募基金(主动)", r"证券投资基金|投资基金$|LOF"),
    ("QFII/外资", r"^[A-Z0-9]+$|摩根|高盛|瑞银|巴克莱|花旗|野村|美林|UBS|MORGAN|GOLDMAN|BARCLAYS|CITI|JPMORGAN"
                  r"|NOMURA|MERRILL|BNP|HSBC|NORGES|KUWAIT|ABUDHABI|自有资金$|客户资金$"),
    ("员工/战配计划", r"员工参与|战略配售"),
    ("资管/信托/理财", r"资产管理计划|信托|理财|资产管理|证券资管|资管计划"),
    ("券商自营", r"证券股份有限公司$|证券有限责任公司$|证券有限公司$|中国国际金融股份有限公司$"),
]
NON_INST = r"回购专用|员工持股|持股计划|奋斗者|合伙企业|实业|控股|集团|投资有限公司$|发展有限公司$"
NOT_FINANCIAL = {"个人", "个人?", "非机构(产业/员工/回购)", "其他法人", "员工/战配计划", "H股名义持有人"}


# ---------------------------------------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------------------------------------

def westock(*args: str, timeout: int = 300) -> str:
    return subprocess.run(["westock-data", *args], capture_output=True, text=True, timeout=timeout).stdout


def find_reports(code: str) -> list[dict]:
    """Latest 2026 Q3 and H1 report notices (full text, not 摘要 or English)."""
    found = {}
    for extra in (["--type", "1", "--limit", "40"], ["--limit", "80"]):
        for ln in westock("notice", "list", code, *extra).splitlines():
            c = [x.strip() for x in ln.strip().strip("|").split("|")]
            if len(c) < 4 or not c[0].startswith("no") or re.search(r"摘要|英文|English", c[2]):
                continue
            for kind, pat in (("Q3", r"2026年(第)?三季度报告"), ("H1", r"2026年半年度报告")):
                if kind not in found and re.search(pat, c[2]):
                    found[kind] = dict(code=code, kind=kind, notice_id=c[0], title=c[2], time=c[3])
        if len(found) == 2:
            break
    return list(found.values())


def pdf_url(notice_id: str) -> str:
    url = json.loads(westock("notice", "detail", notice_id))["data"][0].get("pdf") or ""
    return re.sub(r"(?<!:)/{2,}", "/", url)


def cninfo_url(url: str) -> str:
    """file.finance.qq.com mirrors cninfo under the same date folder and announcement id."""
    m = re.search(r"/pdf/(\d{4})/(\d{2})/(\d{2})/(\d+)\.PDF$", url or "", re.I)
    return f"https://static.cninfo.com.cn/finalpage/{m[1]}-{m[2]}-{m[3]}/{m[4]}.PDF" if m else url


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)


def fetch():
    for sub in ("shareholder", "pdf", "txt"):
        (RAW / sub).mkdir(parents=True, exist_ok=True)
    http = requests.Session()
    http.trust_env = False  # the shell proxy breaks file.finance.qq.com
    index = RAW / "reports.csv"
    reports = pd.read_csv(index, dtype=str).to_dict("records") if index.exists() else []
    for code, name, _ in UNIVERSE:
        md = RAW / "shareholder" / f"{code}.md"
        if not md.exists():
            md.write_text(westock("shareholder", code), encoding="utf-8")
        have = {r["kind"] for r in reports if r["code"] == code}
        if have != {"Q3", "H1"}:
            for rep in find_reports(code):
                if rep["kind"] not in have:
                    rep["pdf_url"] = pdf_url(rep["notice_id"])
                    rep["cninfo_url"] = cninfo_url(rep["pdf_url"])
                    reports.append(rep)
        for rep in (r for r in reports if r["code"] == code):
            txt = RAW / "txt" / f"{code}_{rep['kind']}.txt"
            pdf = RAW / "pdf" / f"{code}_{rep['kind']}.pdf"
            if txt.exists():
                continue
            if not pdf.exists():
                r = http.get(rep["pdf_url"], timeout=120)
                r.raise_for_status()
                if not r.content.startswith(b"%PDF"):
                    print(f"  {code} {rep['kind']}: not a PDF", file=sys.stderr)
                    continue
                pdf.write_bytes(r.content)
            txt.write_text(pdf_text(pdf), encoding="utf-8")
        print(code, name, sorted(r["kind"] for r in reports if r["code"] == code))
    pd.DataFrame(reports).sort_values(["code", "kind"]).to_csv(index, index=False)
    codes = ",".join(c for c, _, _ in UNIVERSE)
    for d in (H1, Q3):
        for path, args in ((RAW / f"quote_{d}.json", ("quote", codes, "--date", d, "--raw")),
                           (RAW / f"etf_{d}.json", ("etf", "detail", ",".join(ETFS.values()), "--date", d, "--raw"))):
            if not path.exists():
                path.write_text(westock(*args), encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------------------------------------

def key(s: str) -> str:
    s = re.sub(r"\s+", "", s or "").translate(FW).upper()
    return re.sub(r"[-()\[\],.:&'\"“”‘’/#*]", "", s)


def clean_lines(text: str):
    """Report lines without the running title and the page number that follows it."""
    out, skip_page = [], False
    for ln in text.splitlines():
        if TITLE.search(ln):
            skip_page = True
            continue
        if PAGE.match(ln) and (skip_page or "/" in ln):
            skip_page = False
            continue
        skip_page = False
        out.append(ln.strip())
    return out


def smart_join(lines):
    """Join lines; glue a number broken across lines only when the pieces form one comma-grouped number."""
    s = ""
    for ln in lines:
        if not ln:
            continue
        if s and re.search(r"[\d,]$", s) and re.match(r"\d", ln):
            tail = re.search(r"[\d,]+$", s).group(0)
            head = re.match(r"[\d,]+", ln).group(0)
            if re.fullmatch(NUM, tail + head) and not re.fullmatch(NUM, tail) or (
                    re.fullmatch(NUM, tail + head) and "," in tail and len(tail.split(",")[-1]) < 3):
                s += ln
                continue
        s += " " + ln
    return re.sub(rf"(?<=[{CJK}])\s+(?=[{CJK}])", "", s)


def sections(text: str):
    """(top-10 holders through float holders, float holders) from a report text."""
    lines = clean_lines(text)
    fl = [i for i, ln in enumerate(lines) if H_FLOAT.search(ln)]
    if not fl:
        return None, None
    i0 = fl[0]
    tops = [i for i, ln in enumerate(lines[:i0]) if H_TOP.search(ln)]
    t0 = tops[-1] if tops else max(0, i0 - 120)
    j = i0 + 1
    while j < len(lines) and not END.search(lines[j]) and j < i0 + 120:
        j += 1
    return smart_join(lines[t0:j]), smart_join(lines[i0 + 1:j])


def parse_float(sec: str):
    sec = re.sub(r"(?<=\d)\s?\.\s?0\s?0(?!\d)", "", sec)
    sec = re.sub(rf"人民币普通\s*({NUM})\s*股", r"人民币普通股 \1", sec)
    rows, prev = [], 0
    hdr = list(re.finditer(r"数量", sec))
    for m in re.finditer(rf"({NUM})\s*({TYPE})\s*({NUM})", sec):
        start = prev
        if not rows and hdr:
            cut = [h.end() for h in hdr if h.end() <= m.start()]
            start = cut[-1] if cut else 0
        rows.append(dict(name=sec[start:m.start()].strip(), shares=int(m.group(1).replace(",", ""))))
        prev = m.end()
    return rows


def parse_md(path: Path):
    """westock `shareholder` markdown: report date and the 十大股东 / 十大流通股东 tables."""
    txt = path.read_text(encoding="utf-8")
    m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", txt)
    out = {}
    for label in ("十大股东", "十大流通股东"):
        part = txt.split(f"**{label}**")[1].split("**")[0] if f"**{label}**" in txt else ""
        rows = []
        for ln in part.splitlines():
            c = [x.strip() for x in ln.strip().strip("|").split("|")]
            if len(c) == 5 and c[0].isdigit():
                rows.append(dict(name=c[1], shares=int(float(c[2]))))
        out[label] = rows
    return (m.group(1) if m else None), out


def classify(name: str) -> str:
    k = key(name)
    for label, pat in INST_RULES:
        if re.search(pat, k):
            return label
    if re.search(NON_INST, k):
        return "非机构(产业/员工/回购)"
    if len(k) <= 4 and re.fullmatch(rf"[{CJK}]+", k):
        return "个人"
    return "其他法人" if "公司" in k else "个人?"


def in_report(text: str, holder: str, shares: int) -> bool:
    """Share count printed in the Q3 report with the holder's name just before it. A wrapped cell can put
    only the start of the name before the number, so either end of the name counts."""
    flat = re.sub(r"\s+", "", text)
    k = key(holder)
    tail = key(re.split(r"[-－]", holder)[-1])[-6:] or k[-6:]
    for m in re.finditer(re.escape(f"{shares:,}"), flat):
        ctx = key(flat[max(0, m.start() - 160):m.start()])
        if k[-6:] in ctx or tail in ctx or k[:12] in ctx:
            return True
    return False


def load_quotes(d: str) -> dict:
    return {x["symbol"]: x["data"] for x in json.loads((RAW / f"quote_{d}.json").read_text())["data"]}


def load_etf_units(d: str) -> dict:
    out = {}

    def walk(o):
        if isinstance(o, dict):
            if {"code", "shares", "name"} <= o.keys():
                out[o["code"]] = dict(name=o["name"], units=float(o["shares"]), index=o.get("trackIndexName"))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(json.loads((RAW / f"etf_{d}.json").read_text()))
    return out


# ---------------------------------------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------------------------------------

def build():
    reports = pd.read_csv(RAW / "reports.csv", dtype=str)
    reports = {(r.code, r.kind): r for r in reports[reports["time"] <= CUTOFF].itertuples()}
    q930, q630 = load_quotes(Q3), load_quotes(H1)
    etf0, etf1 = load_etf_units(H1), load_etf_units(Q3)
    universe, holders, new, exits, flow = [], [], [], [], []
    for code, name, group in UNIVERSE:
        six = code[2:]
        rep_q3, rep_h1 = reports.get((code, "Q3")), reports.get((code, "H1"))
        row = dict(code=six, name=name, group=group, q3_disclosed=rep_q3 is not None,
                   q3_report_time=getattr(rep_q3, "time", None), q3_report_url=getattr(rep_q3, "cninfo_url", None),
                   h1_report_url=getattr(rep_h1, "cninfo_url", None))
        universe.append(row)
        if rep_q3 is None:
            continue
        q3_text = (RAW / "txt" / f"{code}_Q3.txt").read_text(encoding="utf-8")
        date, md = parse_md(RAW / "shareholder" / f"{code}.md")
        if date == Q3:
            q3_float, src = md["十大流通股东"], "westock"
        else:
            q3_float, src = parse_float(sections(q3_text)[1] or ""), "report"
        region, fsec = sections((RAW / "txt" / f"{code}_H1.txt").read_text(encoding="utf-8"))
        h1_float = parse_float(fsec or "")
        rk = key(region or "")
        h1_keys = {key(r["name"]): r for r in h1_float}

        def lookup(nm):
            k = key(nm)
            if k in h1_keys:
                return "float", h1_keys[k]["shares"]
            if k and k in rk:
                return "region", None
            prod = key(re.split(r"[-－]", nm)[-1]) if re.search(r"[-－]", nm) else ""
            if len(prod) >= 6 and prod in rk:
                return "product-only", None
            return None, None

        bse = BSE_H1.get(code)
        h1_cut = bse["cutoff"] if bse else min((r["shares"] for r in h1_float), default=None)
        q3_cut = min(r["shares"] for r in q3_float)
        q, q0 = q930[code], q630.get(code, {})
        px = q["price"]
        n_new = n_stay = new_sh = add_sh = stay_sh = sold_sh = 0
        for rank, r in enumerate(q3_float, 1):
            where, h1_sh = lookup(r["name"])
            kind = classify(r["name"])
            is_new = where is None and (code, r["name"]) not in FALSE_NEW
            holders.append(dict(code=six, name=name, rank=rank, holder=r["name"], holder_type=kind,
                                shares=r["shares"], in_h1=where or "", h1_shares=h1_sh, is_new=is_new))
            if kind not in NOT_FINANCIAL and h1_sh is not None:
                n_stay += 1
                stay_sh += r["shares"] - h1_sh
            special = NOT_COUNTED.get((code, r["name"]))
            if not is_new or (kind in NOT_FINANCIAL and not special):
                continue
            add = max(0, r["shares"] - h1_cut) if h1_cut else 0
            if not special:
                n_new += 1
                new_sh += r["shares"]
                add_sh += add
            etf = next((v for k, v in ETFS.items() if k in r["name"]), None)
            units_chg = etf_add = None
            if etf and etf in etf0 and etf in etf1:
                units_chg = etf1[etf]["units"] / etf0[etf]["units"] - 1
                etf_add = r["shares"] * (1 - etf0[etf]["units"] / etf1[etf]["units"])
            new.append(dict(
                code=six, name=name, group=group, holder=r["name"], holder_type=special or kind,
                shares=r["shares"], pct_of_total=round(r["shares"] / q["total_shares"] * 100, 2), close_0930=px,
                value_0930_yi=round(r["shares"] * px / 1e8, 4), h1_cutoff_shares=h1_cut,
                confirmed_add_shares=add, confirmed_add_yi=round(add * px / 1e8, 4),
                etf_code=etf, etf_units_chg=None if units_chg is None else round(units_chg, 4),
                etf_est_add_shares=None if etf_add is None else round(etf_add),
                etf_est_add_yi=None if etf_add is None else round(etf_add * px / 1e8, 4),
                in_q3_report=in_report(q3_text, r["name"], r["shares"]), counted=special is None))
        q3_keys = {key(r["name"]) for r in q3_float}
        out = ([dict(name=n, shares=s) for n, s in bse["exits"]] if bse else
               [r for r in h1_float if key(r["name"]) not in q3_keys
                and not any(c == code and k in r["name"] for c, k in FALSE_EXIT)])
        n_exit = 0
        for r in out:
            kind = classify(r["name"])
            if kind in NOT_FINANCIAL:
                continue
            n_exit += 1
            sold = max(0, r["shares"] - q3_cut)
            sold_sh += sold
            exits.append(dict(code=six, name=name, group=group, holder=r["name"], holder_type=kind,
                              h1_shares=r["shares"], q3_cutoff_shares=q3_cut, confirmed_sale_shares=sold,
                              confirmed_sale_yi=round(sold * px / 1e8, 4)))
        # New holders bought at most their whole position and exits sold at least the confirmed amount, so the
        # sum bounds the top-10 institutions' net buying from above.
        flow.append(dict(code=six, name=name, group=group, new_institutions=n_new,
                         new_value_yi=round(new_sh * px / 1e8, 4), confirmed_add_yi=round(add_sh * px / 1e8, 4),
                         stayed_institutions=n_stay, stayed_change_yi=round(stay_sh * px / 1e8, 4),
                         exited_institutions=n_exit, confirmed_sale_yi=round(sold_sh * px / 1e8, 4),
                         net_flow_upper_yi=round((new_sh + stay_sh - sold_sh) * px / 1e8, 4)))
        row.update(q3_source=src, q3_rows=len(q3_float),
                   q3_rows_in_report=sum(in_report(q3_text, r["name"], r["shares"]) for r in q3_float),
                   h1_cutoff_shares=h1_cut, q3_cutoff_shares=q3_cut, new_institutions=n_new,
                   exited_institutions=n_exit, close_0930=px, total_shares_0930=q["total_shares"],
                   total_shares_0630=q0.get("total_shares"))
    etf_rows = [dict(etf_code=c, etf_name=etf1[c]["name"], track_index=etf1[c]["index"],
                     units_0630_yi=round(etf0[c]["units"] / 1e8, 3), units_0930_yi=round(etf1[c]["units"] / 1e8, 3),
                     units_chg=round(etf1[c]["units"] / etf0[c]["units"] - 1, 4))
                for c in ETFS.values() if c in etf0 and c in etf1]
    OUT.mkdir(parents=True, exist_ok=True)
    frames = {}
    for fname, rows in (("inst_universe", universe), ("inst_q3_float", holders), ("inst_new", new),
                        ("inst_exits", exits), ("inst_flow", flow), ("inst_etf_units", etf_rows)):
        df = pd.DataFrame(rows)
        for col in df.columns:
            if col.endswith("_shares") or col.endswith("_institutions") or col.startswith("total_shares"):
                df[col] = df[col].astype("Int64")
        df.to_csv(OUT / f"{fname}.csv", index=False)
        frames[fname] = df
    return frames["inst_universe"], frames["inst_new"], frames["inst_exits"]


def report(universe, new, exits):
    counted = new[new["counted"]]
    print(f"disclosed {int(universe['q3_disclosed'].sum())}/{len(universe)}; "
          f"stocks with new institutions {counted['code'].nunique()}; rows {len(new)} "
          f"(not found in Q3 report text: {int((~new['in_q3_report']).sum())})")
    for g, d in counted.groupby("group", sort=False):
        print(f"  {g}: value {d['value_0930_yi'].sum():.2f} 亿, confirmed {d['confirmed_add_yi'].sum():.2f} 亿, "
              f"stocks {d['code'].nunique()}")
    print("  not disclosed:", ", ".join(universe.loc[~universe["q3_disclosed"], "name"]))


if __name__ == "__main__":
    if "fetch" in sys.argv[1:]:
        fetch()
    report(*build())
