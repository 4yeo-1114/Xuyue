# -*- coding: utf-8 -*-
"""国家中小学智慧教育平台「电子教材」抓取到本地资料库。

数据源（公开，无需登录）：
  标签树   tch_material_tag.json
  版本清单 data_version.json -> part_100~103.json（每册教材一条元数据）
  详情     tch_material/details/{id}.json（含 ti_items 文件直链）

落盘结构（资料库根 shared_zyk_dir() 下）：
  电子教材/{学段}/{学科}/{年级}/{册次}/{书名}.pdf

用法：
  python scripts/smartedu_fetch_textbooks.py --plan          # 只看范围与大小，不下
  python scripts/smartedu_fetch_textbooks.py --limit 5       # 试下前 5 本
  python scripts/smartedu_fetch_textbooks.py                 # 全量下载（可断点续）
  python scripts/smartedu_fetch_textbooks.py --covers-only   # 只补抓已下载教材的封面图
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

_here = Path(__file__).resolve().parent
_root = _here.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.grading.user_paths import shared_zyk_dir  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
PREFIX = "https://cdncs.ykt.cbern.com.cn/v0.1/static"
REF = "cs_path:${ref-path}"

VERSION_URL = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json"
DETAILS_TMPL = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{id}.json"

# 抓取范围：主流学科 + 主流版本（与 zyk_catalog.py 人教版为主一致）
CORE_SUBJECTS = {
    "语文", "数学", "英语", "物理", "化学", "生物", "生物学",
    "道德与法治", "历史", "地理",
}
# 学科 -> 允许的版本集合（统编版三科走统编，其余走人教版系）
EDITION_BY_SUBJECT = {
    "语文": {"统编版"},
    "道德与法治": {"统编版"},
    "历史": {"统编版"},
    "数学": {"人教版", "人教A版", "人教B版"},
    "英语": {"人教版", "人教PEP版"},
    "物理": {"人教版"},
    "化学": {"人教版"},
    "生物": {"人教版"},
    "生物学": {"人教版"},
    "地理": {"人教版"},
}

STAGE_OK = {"小学", "初中", "高中"}


def _clean(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
    name = name.strip(" ._")
    return name[:180] or "未命名"


def get(url: str, timeout: int = 60) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r


def load_parts() -> list:
    urls = get(VERSION_URL).json()["urls"].split(",")
    out: list = []
    for url in urls:
        out.extend(get(url).json())
        time.sleep(0.2)
    return out


def parse(e: dict) -> dict:
    tags = {}
    for t in e.get("tag_list") or []:
        tags[t.get("tag_dimension_id")] = t.get("tag_name")
    cp = e.get("custom_properties") or {}
    return {
        "id": e.get("id"),
        "title": e.get("title") or "",
        "stage": tags.get("zxxxd", ""),
        "subject": tags.get("zxxxk", ""),
        "edition": tags.get("zxxbb", ""),
        "grade": tags.get("zxxnj", ""),
        "volume": tags.get("zxxcc", ""),
        "format": cp.get("format"),
        "size": cp.get("size"),
        "policy": (e.get("resource_custom_properties") or {}).get("download_policy"),
    }


def wanted(e: dict) -> bool:
    if e["format"] != "pdf":
        return False
    if e["stage"] not in STAGE_OK:
        return False
    if e["subject"] not in CORE_SUBJECTS:
        return False
    allowed = EDITION_BY_SUBJECT.get(e["subject"])
    if not allowed or e["edition"] not in allowed:
        return False
    # 年级归一：高中年级/高一年级/高二年级/高三年级 都算高中
    return True


def resolve_direct(details: dict):
    cp = details.get("custom_properties") or {}
    fmt = cp.get("format")
    size = cp.get("size")
    for it in details.get("ti_items") or []:
        st = it.get("ti_storage") or ""
        flag = it.get("ti_file_flag")
        if flag in ("source", "href") or (it.get("ti_size") == size and fmt != "mp4"):
            if st.startswith(REF):
                return PREFIX + st[len(REF):]
            return st
    return None


def resolve_cover(details: dict):
    """教材封面图：优先 thumbnails[0]，回退 preview 的封面页（Slide1）。"""
    cp = details.get("custom_properties") or {}
    thumbs = cp.get("thumbnails") or []
    if thumbs and thumbs[0]:
        return thumbs[0]
    preview = cp.get("preview") or {}
    if preview:
        # 封面页键形如 Slide1 / Slide01；找不到就取页码最小的一页
        for k in preview:
            if re.fullmatch(r"[Ss]lide0*1", k):
                return preview[k]

        def _n(k: str) -> int:
            m = re.search(r"(\d+)", k)
            return int(m.group(1)) if m else 10 ** 9

        return preview[min(preview, key=_n)]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true", help="只打印范围与大小")
    ap.add_argument("--limit", type=int, default=0, help="最多下载 N 本")
    ap.add_argument("--subjects", help="逗号分隔，覆盖默认学科范围")
    ap.add_argument("--covers-only", action="store_true", help="只补抓已下载教材的封面图")
    args = ap.parse_args()

    parts = load_parts()
    rows = [parse(e) for e in parts]
    want = [r for r in rows if wanted(r)]

    print(f"教材总数 {len(rows)}，命中范围 {len(want)} 本")
    # 大小统计（元数据里的 size）
    total_bytes = sum(r["size"] or 0 for r in want)
    print(f"预计总大小 {total_bytes / 1024 / 1024:.1f} MB")
    by_subj: dict = {}
    for r in want:
        by_subj.setdefault(r["subject"], []).append(r)
    for s, lst in sorted(by_subj.items(), key=lambda x: -len(x[1])):
        print(f"  {s}: {len(lst)} 本")
    policy: dict = {}
    for r in want:
        policy[r["policy"]] = policy.get(r["policy"], 0) + 1
    print(f"download_policy 分布: {policy}")

    if args.plan:
        return

    # 下载
    root = shared_zyk_dir()
    done = skip = fail = cover_done = 0
    manifest = {"downloaded": [], "failed": [], "covers": []}
    todo = want if not args.limit else want[: args.limit]
    for i, r in enumerate(todo, 1):
        key = f"{r['stage']}/{r['subject']}/{r['grade']}/{r['volume']}/{r['title']}"
        try:
            d = get(DETAILS_TMPL.format(id=r["id"]), timeout=30).json()
            folder = root / "电子教材" / _clean(r["stage"]) / _clean(r["subject"]) / _clean(r["grade"]) / _clean(r["volume"])
            folder.mkdir(parents=True, exist_ok=True)
            fname = _clean(r["title"]) + ".pdf"
            out = folder / fname

            # --- 教材 PDF ---
            if not args.covers_only:
                if out.exists() and out.stat().st_size > 0:
                    skip += 1
                else:
                    url = resolve_direct(d)
                    if not url:
                        fail += 1
                        print(f"[{i}/{len(todo)}] 无直链 {r['title'][:24]}")
                        manifest["failed"].append({"title": r["title"], "id": r["id"], "reason": "no-url"})
                    else:
                        content = None
                        last_err = None
                        for attempt in range(2):
                            try:
                                resp = get(url, timeout=120)
                                content = resp.content
                                break
                            except Exception as ex:  # noqa: BLE001
                                last_err = ex
                                time.sleep(1.0 * (attempt + 1))
                        if content is None:
                            fail += 1
                            print(f"[{i}/{len(todo)}] ✗ {key[:40]} {type(last_err).__name__}: {last_err}")
                            manifest["failed"].append({"title": r["title"], "id": r["id"], "reason": str(last_err)})
                        else:
                            with open(out, "wb") as f:
                                f.write(content)
                            done += 1
                            print(f"[{i}/{len(todo)}] ✓ {r['stage']}/{r['subject']}/{r['grade']}/{r['volume']}/{fname} ({len(content)//1024}KB)")
                            manifest["downloaded"].append({"title": r["title"], "id": r["id"], "size": len(content), "path": str(out)})
                            time.sleep(0.4)

            # --- 封面图（仅当教材 PDF 已存在时抓）---
            if out.exists() and out.stat().st_size > 0:
                stem = Path(fname).stem
                cover_path = folder / (stem + ".jpg")
                if not cover_path.exists() or cover_path.stat().st_size == 0:
                    cover_url = resolve_cover(d)
                    if cover_url:
                        try:
                            cv = get(cover_url, timeout=60).content
                            with open(cover_path, "wb") as cf:
                                cf.write(cv)
                            cover_done += 1
                            manifest["covers"].append({"title": r["title"], "id": r["id"]})
                            if args.covers_only:
                                print(f"[{i}/{len(todo)}] ▣ {r['stage']}/{r['subject']}/{r['grade']}/{r['volume']}/{stem}.jpg ({len(cv)//1024}KB)")
                        except Exception as ex:  # noqa: BLE001
                            if args.covers_only:
                                print(f"[{i}/{len(todo)}] ✗封面 {r['title'][:20]} {type(ex).__name__}: {ex}")
        except Exception as ex:  # noqa: BLE001
            fail += 1
            print(f"[{i}/{len(todo)}] ✗ {r['title'][:24]} {type(ex).__name__}: {ex}")
            manifest["failed"].append({"title": r["title"], "id": r["id"], "reason": str(ex)})

    mf = _here / "smartedu_textbook_manifest.json"
    mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成：下载 {done} / 跳过 {skip} / 失败 {fail} / 封面 {cover_done}")
    print(f"清单：{mf}")


if __name__ == "__main__":
    main()
