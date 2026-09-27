#!/usr/bin/env python3
"""抓取 B 站视频字幕，输出 SRT、按分钟分段的阅读版和元信息。

用法：
    python3 fetch.py BV1qhen6GEbi [--browser edge]

B 站的字幕轨需要登录态，脚本从本机浏览器读取 cookie。
不直接调 player/v2 接口是因为它对字幕轨的返回不稳定，yt-dlp 的解析更可靠。
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def hhmmss(sec):
    s = int(sec)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_srt(text):
    """解析 SRT -> [(start_sec, content)]"""
    pat = re.compile(
        r"\d+\s*\n"
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
        r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s*\n"
        r"(.*?)(?=\n\s*\n|\Z)",
        re.S,
    )
    out = []
    for m in pat.finditer(text):
        h, mi, s, ms, body = m.groups()
        start = int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000
        content = " ".join(x.strip() for x in body.strip().splitlines())
        if content:
            out.append((start, content))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bvid")
    ap.add_argument("--browser", default="edge",
                    help="从哪个浏览器读 cookie，默认 edge")
    ap.add_argument("--lang", default="ai-zh", help="字幕轨语言代码")
    args = ap.parse_args()

    url = f"https://www.bilibili.com/video/{args.bvid}"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cookies = tmp / "cookies.txt"

        # yt-dlp 每次调用都重新解密浏览器 cookie 很慢，先导出一份复用
        run(["yt-dlp", "--cookies-from-browser", args.browser,
             "--cookies", str(cookies), "--simulate", "--skip-download",
             "--quiet", url])

        run(["yt-dlp", "--cookies", str(cookies),
             "--write-subs", "--sub-langs", args.lang,
             "--skip-download", "--convert-subs", "srt",
             "--write-info-json", "-o", "%(id)s.%(ext)s", url], cwd=tmp)

        srt_path = tmp / f"{args.bvid}.{args.lang}.srt"
        if not srt_path.exists():
            sys.exit(f"没找到字幕轨 {args.lang}，先用 "
                     f"`yt-dlp --cookies-from-browser {args.browser} "
                     f"--list-subs {url}` 看看有哪些可用")

        srt_text = srt_path.read_text(encoding="utf-8")
        info = json.loads((tmp / f"{args.bvid}.info.json").read_text(encoding="utf-8"))

    cues = parse_srt(srt_text)
    fetched = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    meta = {
        "bvid": args.bvid,
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "upload_date": info.get("upload_date"),
        "duration_sec": info.get("duration"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "webpage_url": info.get("webpage_url"),
        "description": info.get("description"),
        "tags": info.get("tags"),
        "chapters": info.get("chapters"),
        "subtitle_track": args.lang,
        "cue_count": len(cues),
        "fetched_at": fetched,
    }
    (HERE / f"{args.bvid}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / f"{args.bvid}.srt").write_text(srt_text, encoding="utf-8")

    up = info.get("upload_date") or ""
    up_fmt = f"{up[:4]}-{up[4:6]}-{up[6:]}" if len(up) == 8 else up
    dur = int(info.get("duration") or 0)

    lines = [
        f"# {info.get('title')}",
        "",
        f"> UP 主：{info.get('uploader')}　｜　发布：{up_fmt}　｜　时长：{dur // 60} 分 {dur % 60} 秒",
        f"> 来源：{info.get('webpage_url')}",
        f"> 字幕：{args.lang}（B 站 AI 自动生成），共 {len(cues)} 条　｜　抓取：{fetched}",
        "",
        "**机器转写稿，未经人工校对。** 专有名词、数字、公司名的识别错误率较高，",
        "引用前务必回原视频对应时间点核对。仅作研究检索用。",
        "",
    ]

    if info.get("chapters"):
        lines += ["## 章节", ""]
        lines += [f"- `[{hhmmss(c.get('start_time', 0))}]` {c.get('title')}"
                  for c in info["chapters"]]
        lines.append("")

    lines += ["## 正文", "", "按每分钟分段，段首时间戳可用于视频定位。", ""]

    bucket, cur = [], -1
    for start, content in cues:
        idx = int(start // 60)
        if idx != cur:
            if bucket:
                lines += [f"`[{hhmmss(cur * 60)}]` " + "".join(bucket), ""]
            bucket, cur = [], idx
        bucket.append(content)
    if bucket:
        lines += [f"`[{hhmmss(cur * 60)}]` " + "".join(bucket), ""]

    (HERE / f"{args.bvid}.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"{info.get('title')}\n字幕 {len(cues)} 条 -> {HERE}")


if __name__ == "__main__":
    main()
