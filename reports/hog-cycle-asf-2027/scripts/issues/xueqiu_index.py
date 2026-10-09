"""Issue #3: public index of the four Xueqiu authors' posts in the review window (no post text).

Input: research/xueqiu_authors/_raw/xq_db.json, collected anonymously in a browser and kept local (gitignored).
Core-article flags come from the per-author notes in research/xueqiu_authors/notes/.

Output: research/xueqiu_authors/articles.csv
  one row per in-window post, plus the author's own posts that were only reachable as the original of a repost;
  topic = title, or the first 24 characters of the author's own text (stock tags, reply prefixes and the quoted
  "//@" comment chain removed);
  other users' screen names are replaced, keeping only the four authors and listed companies' official accounts
"""
from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "research" / "xueqiu_authors"
CST = timezone(timedelta(hours=8))
START = datetime(2026, 4, 9, tzinfo=CST)
END = datetime(2026, 10, 10, tzinfo=CST)
ORDER = ["4069897501", "1632625377", "4932531422", "5091513072"]
AUTHORS = {"我不帅你报警", "一凡帝诺维奇", "_春风_", "豆区"}
OFFICIAL = re.compile(r"\((?:SZ|SH)\d{6}\)$|\(\d{5}\)$")
KIND = {"3": "长文", "1": "长文", "2": "带图帖", "0": "普通帖"}
HOG = re.compile(
    r"猪|母猪|能繁|仔猪|牧原|温氏|新希望|神农|巨星|德康|东瑞|天康|唐人神|天邦|京基|华统|立华|新五丰|正邦|傲农|罗牛山|金新农|大北农|"
    r"养殖|出栏|二育|屠宰|饲料|豆粕|玉米|BK0503|SZ002714|SZ300498"
)


def unescape_all(obj):
    if isinstance(obj, str):
        return html.unescape(obj)
    if isinstance(obj, list):
        return [unescape_all(x) for x in obj]
    if isinstance(obj, dict):
        return {k: unescape_all(v) for k, v in obj.items()}
    return obj


def ts(ms):
    return datetime.fromtimestamp(ms / 1000, CST)


MENTION = re.compile(r"@([^\s:：,，。；;、!！?？)）<>/]+)")
OTHERS: list[str] = []


def public_name(sn):
    if not sn or sn in AUTHORS or OFFICIAL.search(sn):
        return sn or ""
    return "其他用户"


def collect_others(db):
    names = set()
    for rec in db.values():
        for p in rec["posts"].values():
            rts = p.get("rts") or {}
            names.add(rts.get("sn") or "")
            for t in (p.get("text"), p.get("full"), rts.get("text"), rts.get("full")):
                names.update(MENTION.findall(re.sub(r"<[^>]+>", "", t or "")))
    keep = {n for n in names if len(n) >= 2 and public_name(n) == "其他用户"}
    return sorted(keep, key=len, reverse=True)


def scrub(text):
    text = text.split("//@", 1)[0]
    text = MENTION.sub(lambda m: m.group(0) if m.group(1) in AUTHORS else "@用户", text)
    for n in OTHERS:
        text = text.replace(n, "某用户")
    return text


def topic(title, body):
    if title:
        return title.strip()
    t = re.sub(r"\$[^$]{1,30}\$", "", body)
    t = re.sub(r"^\s*(回复)?\s*@[^:：]{1,30}[:：]", "", t)
    t = re.sub(r"\s+", " ", scrub(t)).strip()
    if not t:
        return "（仅转发，无本人文字）"
    return t[:24] + ("…" if len(t) > 24 else "")


def kind(p):
    if p.get("rt"):
        return "转发或评论"
    if "col" in (p.get("src") or []):
        return "专栏"
    return KIND.get(str(p.get("type")), "其他")


def core_ids():
    ids = set()
    for f in (BASE / "notes").glob("*.md"):
        txt = f.read_text()
        if "## 1." not in txt:
            continue
        sec = txt.split("## 1.", 1)[1].split("\n## 2.", 1)[0]
        for line in sec.splitlines():
            if line.startswith("|") and "★" in line:
                ids.update(re.findall(r"\b([34]\d{8})\b", line))
    return ids


def main():
    db = unescape_all(json.loads((BASE / "_raw" / "xq_db.json").read_text()))
    OTHERS[:] = collect_others(db)
    core = core_ids()
    rows = []
    for uid in ORDER:
        rec = db[uid]
        sn = (rec.get("info") or {}).get("sn", uid)
        posts = rec["posts"]
        seen = {str(p["id"]) for p in posts.values()}
        extra = {}
        for p in posts.values():
            t = ts(p["t"])
            if not (START <= t < END):
                continue
            body = p.get("full") or p.get("text") or p.get("desc") or ""
            rts = p.get("rts") or {}
            rt_text = rts.get("full") or rts.get("text") or ""
            rows.append(dict(
                author=sn, uid=uid, post_id=p["id"], date=t.strftime("%Y-%m-%d %H:%M"), kind=kind(p),
                topic=topic(p.get("title"), body), chars=len(body),
                full_text=p.get("full_status") or ("全文" if p.get("full") or (body and not body.endswith(("...", "…"))) else "仅摘要"),
                hog=int(bool(HOG.search((p.get("title") or "") + body + rt_text))),
                core=int(str(p["id"]) in core), reposted_author=public_name(rts.get("sn")),
                url=f"https://xueqiu.com{p.get('target') or '/' + uid + '/' + str(p['id'])}",
                edited=ts(p["ed"]).strftime("%Y-%m-%d %H:%M") if p.get("ed") else "",
            ))
            if rts and str(rts.get("uid")) == uid and str(rts.get("id")) not in seen and rts.get("t"):
                extra[str(rts["id"])] = rts
        for rid, r in extra.items():
            t = ts(r["t"])
            if not (START <= t < END):
                continue
            body = r.get("full") or r.get("text") or ""
            rows.append(dict(
                author=sn, uid=uid, post_id=rid, date=t.strftime("%Y-%m-%d %H:%M"), kind="原帖（经转发获取）",
                topic=topic(r.get("title"), body), chars=len(body), full_text="全文" if body else "仅摘要",
                hog=int(bool(HOG.search((r.get("title") or "") + body))), core=int(rid in core), reposted_author="",
                url=f"https://xueqiu.com/{uid}/{rid}", edited="",
            ))
    rows.sort(key=lambda r: (ORDER.index(r["uid"]), r["date"]))
    out = BASE / "articles.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    by = {}
    for r in rows:
        k = r["author"]
        a = by.setdefault(k, dict(n=0, hog=0, core=0, kinds={}))
        a["n"] += 1
        a["hog"] += r["hog"]
        a["core"] += r["core"]
        a["kinds"][r["kind"]] = a["kinds"].get(r["kind"], 0) + 1
    for k, v in by.items():
        print(k, v)


if __name__ == "__main__":
    main()
