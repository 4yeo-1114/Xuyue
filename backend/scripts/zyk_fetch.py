# -*- coding: utf-8 -*-
"""资源库「真实文件抓取 + 链接索引」工具（与 fill_zyk.py 配套）。

用途：
  1. kind="file"：把真实文件（PDF/PPT/DOC 等）下载到共享资源库
     grading_data_all/_shared/zyk_data/{年级}/{学科}/{知识点}/ 下，
     并在旁边落一份 _source.json 记录来源与抓取时间（便于版权溯源）。
  2. kind="link"：视频等只做「链接跳转」——生成 Windows 快捷方式 .url
     与一个可点击的 HTML 索引页，不做文件下载。

清单格式（JSON 数组，放在 zyk_manifest.json）：
  [
    {
      "grade": "三年级", "subject": "数学", "knowledge": "分数",
      "kind": "file",
      "url": "https://.../课件.pdf",
      "filename": "分数的初步认识-课件.pdf",     // 可选，缺省从 url 或 title 推导
      "title": "人教版《分数的初步认识》课件",
      "source": "国家中小学智慧教育平台"          // 来源标签，写入 _source.json
    },
    {
      "grade": "三年级", "subject": "数学", "knowledge": "分数",
      "kind": "link",
      "url": "https://www.bilibili.com/video/BVxxxx/",
      "title": "《分数的初步认识》第一课时"
    }
  ]

运行（项目根目录下）：
    python scripts/zyk_fetch.py --manifest zyk_manifest.json
    python scripts/zyk_fetch.py --manifest zyk_manifest.json --dry-run   # 只打印不下
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.grading.user_paths import shared_zyk_dir

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TIMEOUT = 30
_RETRIES = 3
_MAX_KB = 200 * 1024  # 200MB 上限，避免把超大视频误当成文件下载


def _safe(name: str) -> str:
    """清洗文件名：去掉路径分隔符与 Windows 非法字符。"""
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
    name = name.strip(" ._")
    return name[:180] or "未命名"


def _ext_from_url(url: str, default: str = ".bin") -> str:
    path = unquote(urlparse(url).path or "")
    m = re.search(r"\.([A-Za-z0-9]{1,8})$", path)
    return f".{m.group(1).lower()}" if m else default


def _resolve_filename(entry: dict, url: str) -> str:
    if entry.get("filename"):
        name = _safe(entry["filename"])
        return name if "." in name else name + _ext_from_url(url)
    if entry.get("title"):
        return _safe(entry["title"]) + _ext_from_url(url)
    return _safe(Path(urlparse(url).path).name or "resource") or ("resource" + _ext_from_url(url))


def download_file(entry: dict, dest_dir: Path) -> dict:
    url = entry["url"]
    filename = _resolve_filename(entry, url)
    out = dest_dir / filename

    headers = {"User-Agent": UA}
    last_err: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=_TIMEOUT, stream=True)
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or 0)
            if total and total > _MAX_KB * 1024:
                return {"status": "skip", "reason": "文件超过 200MB", "file": filename}
            if out.exists() and out.stat().st_size == total and total > 0:
                return {"status": "skip", "reason": "已存在且大小一致", "file": filename}
            with open(out, "wb") as f:
                for chunk in resp.iter_content(1024 * 128):
                    f.write(chunk)
            (dest_dir / "_source.json").write_text(
                json.dumps(
                    {
                        "source": entry.get("source", ""),
                        "title": entry.get("title", ""),
                        "url": url,
                        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "file": filename,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return {"status": "ok", "file": filename}
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    return {"status": "fail", "reason": str(last_err), "file": filename}


def write_link(entry: dict, dest_dir: Path) -> dict:
    url = entry["url"]
    title = entry.get("title") or url
    stem = _safe(title)

    # 1) Windows 快捷方式 .url（双击跳转）
    url_file = dest_dir / f"{stem}.url"
    url_file.write_text(
        f"[InternetShortcut]\nURL={url}\n", encoding="utf-8"
    )

    # 2) 追加到该知识点的可点击 HTML 索引
    index = dest_dir / "视频链接索引.html"
    new_item = f'<li><a href="{url}" target="_blank">{title}</a>'
    if entry.get("intro"):
        new_item += f' — <span style="color:#666">{entry["intro"]}</span>'
    new_item += "</li>\n"
    if index.exists():
        html = index.read_text(encoding="utf-8")
        html = html.replace("</ul>", new_item + "</ul>", 1)
    else:
        html = (
            "<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
            f"<title>{_safe(entry.get('knowledge') or '视频')} 视频链接</title></head>"
            "<body style='font-family:Microsoft YaHei;max-width:760px;margin:32px auto'>"
            f"<h2>{entry.get('grade','')} · {entry.get('subject','')} · {entry.get('knowledge','')}</h2>"
            f"<ul>{new_item}</ul></body></html>"
        )
    index.write_text(html, encoding="utf-8")
    return {"status": "ok", "file": url_file.name, "index": index.name}


def process(entries: list[dict], dry_run: bool) -> dict:
    root = shared_zyk_dir()
    report = {"ok": 0, "skip": 0, "fail": 0, "rows": []}
    for i, entry in enumerate(entries, 1):
        if not entry.get("url"):
            report["rows"].append({"i": i, "status": "fail", "reason": "缺少 url"})
            report["fail"] += 1
            continue
        dest = root / _safe(entry.get("grade") or "未分类") / _safe(entry.get("subject") or "未分类") / _safe(entry.get("knowledge") or "未分类")
        if dry_run:
            report["rows"].append({"i": i, "status": "dry", "dest": str(dest.relative_to(root)), "url": entry["url"]})
            continue
        dest.mkdir(parents=True, exist_ok=True)
        r = download_file(entry, dest) if entry.get("kind") == "file" else write_link(entry, dest)
        r["i"] = i
        report["rows"].append(r)
        report[r["status"]] += 1
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="清单 JSON 路径")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else data.get("items", [])
    report = process(entries, args.dry_run)

    print(f"完成：成功 {report['ok']} / 跳过 {report['skip']} / 失败 {report['fail']}")
    print(f"资源库根目录：{shared_zyk_dir()}")
    for r in report["rows"]:
        print(" ", r)


if __name__ == "__main__":
    main()
