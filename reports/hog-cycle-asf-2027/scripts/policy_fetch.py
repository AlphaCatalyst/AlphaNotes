"""Fetch policy web pages (cached under data/raw/policy) and return readable text.

Usage:
    python3 policy_fetch.py URL [grep_regex] [context_chars]
"""
from __future__ import annotations

import hashlib
import html
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

from common import RAW, _get

CACHE = RAW / "policy"
CACHE.mkdir(parents=True, exist_ok=True)


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript"}
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "td"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")
        if tag == "a":
            href = dict(attrs).get("href")
            if href and not href.startswith("javascript"):
                self.out.append(f"[[{href}]]")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def _decode(raw: bytes, declared: str | None) -> str:
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:3000], re.I)
    encs = [m.group(1).decode() if m else None, declared, "utf-8", "gb18030"]
    for enc in encs:
        if not enc:
            continue
        enc = "gb18030" if enc.lower() in ("gb2312", "gbk") else enc
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def fetch_html(url: str, refresh: bool = False) -> str:
    h = hashlib.md5(url.encode()).hexdigest()[:16]
    p = CACHE / f"{h}.html"
    if refresh or not p.exists():
        r = _get(url, timeout=40)
        p.write_text(_decode(r.content, r.encoding), encoding="utf-8")
        (CACHE / f"{h}.url").write_text(url)
    return p.read_text(encoding="utf-8")


def html_text(src: str) -> str:
    t = _Text()
    t.feed(src)
    s = html.unescape("".join(t.out)).replace("\u3000", " ").replace("\xa0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def page_text(url: str, refresh: bool = False) -> str:
    return html_text(fetch_html(url, refresh))


if __name__ == "__main__":
    u = sys.argv[1]
    txt = page_text(u)
    if len(sys.argv) > 2:
        ctx = int(sys.argv[3]) if len(sys.argv) > 3 else 300
        for m in re.finditer(sys.argv[2], txt):
            print("...", txt[max(0, m.start() - ctx): m.end() + ctx].replace("\n", " "), "...\n")
    else:
        print(txt)
