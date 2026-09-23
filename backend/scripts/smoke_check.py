# -*- coding: utf-8 -*-
"""发布前冒烟检查：确认批改历史里的图片直链真的能打开。

为什么需要它：留痕图直链用 ?ticket= 短时下载票鉴权，票过期或漏签会返回 401，
前端表现是「看不到试卷」。这类问题只有真正发一次请求才暴露得出来，
跑一遍这个脚本能在交付前发现。

用法：
    # 只做健康检查
    python scripts/smoke_check.py

    # 带登录令牌，检查指定文件夹的历史与图片
    python scripts/smoke_check.py --token <JWT> --folder "班级D_第七单元作文"

    # 不传 --folder 时，自动从本地数据目录发现（脚本与后端同机时可用）
    python scripts/smoke_check.py --token <JWT>

退出码：0 = 全部通过；1 = 有检查项失败。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import requests

# 历史记录里可能出现图片链接的字段
IMAGE_KEYS = ("image_original", "image_annotated", "image_marks_only")


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _skip(msg: str) -> None:
    print(f"  [SKIP] {msg}")


def discover_folders(root: Path) -> list[str]:
    """从本地 grading_data_all/<user>/grading_history/*.json 反推文件夹名。

    历史文件名形如 {folder}__essay.json / {folder}.json，剥掉引擎后缀即为文件夹名。
    """
    names: set[str] = set()
    if not root.is_dir():
        return []
    for hist_dir in root.glob("*/grading_history"):
        for f in hist_dir.glob("*.json"):
            stem = re.sub(r"__(essay|manual)$", "", f.stem)
            if stem.strip():
                names.add(stem)
    return sorted(names)


def check_health(base: str, session: requests.Session) -> bool:
    print(f"\n[1] 后端健康检查 {base}")
    try:
        r = session.get(f"{base}/docs", timeout=10)
    except Exception as e:
        _fail(f"连不上后端: {e}")
        return False
    if r.status_code == 200:
        _ok("GET /docs -> 200")
        return True
    _fail(f"GET /docs -> {r.status_code}")
    return False


def check_auth(base: str, session: requests.Session, token: str) -> bool:
    print("\n[2] 登录态检查")
    session.headers["Authorization"] = f"Bearer {token}"
    try:
        r = session.get(f"{base}/api/v1/auth/me", timeout=10)
    except Exception as e:
        _fail(f"请求异常: {e}")
        return False
    if r.status_code == 200:
        who = r.json().get("email") or r.json().get("display_name") or "?"
        _ok(f"/auth/me -> 200 ({who})")
        return True
    _fail(f"/auth/me -> {r.status_code}（令牌可能已过期，请重新登录后再跑）")
    return False


def check_folder(base: str, session: requests.Session, folder: str, limit: int) -> tuple[int, int]:
    """检查一个文件夹的两类历史接口，并抽查里面的图片链接。返回 (通过数, 失败数)。"""
    print(f"\n[3] 文件夹「{folder}」")
    passed = failed = 0
    endpoints = (
        (f"/api/v1/grading/folders/{folder}/grading-history", {"engine": "aliyun"}),
        (f"/api/v1/grading/folders/{folder}/essay-grading-history", {}),
    )
    for path, params in endpoints:
        label = path.rsplit("/", 1)[-1]
        try:
            r = session.get(f"{base}{path}", params=params, timeout=30)
        except Exception as e:
            _fail(f"{label}: 请求异常 {e}")
            failed += 1
            continue
        if r.status_code != 200:
            _fail(f"{label}: HTTP {r.status_code}")
            failed += 1
            continue

        items = r.json().get("completed") or []
        urls: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in IMAGE_KEYS:
                u = item.get(key)
                if isinstance(u, str) and u:
                    urls.append(u)
        _ok(f"{label}: {len(items)} 条记录, {len(urls)} 个图片链接")

        if not urls:
            continue
        # 去重后抽查
        sample = list(dict.fromkeys(urls))[: max(1, limit)]
        for u in sample:
            url = f"{base}{u}" if u.startswith("/") else u
            try:
                img = session.get(url, timeout=30)
            except Exception as e:
                _fail(f"图片请求异常: {u[:70]}... ({e})")
                failed += 1
                continue
            if img.status_code == 200 and img.content:
                passed += 1
            else:
                _fail(f"图片 HTTP {img.status_code}: {u[:90]}...")
                failed += 1
    return passed, failed


def main() -> int:
    ap = argparse.ArgumentParser(description="发布前冒烟检查")
    ap.add_argument("--base-url", default="http://127.0.0.1:6888")
    ap.add_argument(
        "--token",
        default=os.environ.get("GRADE_BUDDY_TOKEN", ""),
        help="登录令牌；也可用环境变量 GRADE_BUDDY_TOKEN 传入",
    )
    ap.add_argument("--folder", action="append", default=[], help="要检查的文件夹名，可重复")
    ap.add_argument("--limit", type=int, default=5, help="每个接口抽查的图片数（默认 5）")
    ap.add_argument(
        "--data-root",
        default="",
        help="本地 grading_data_all 路径，用于自动发现文件夹（不传则不自动发现）",
    )
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    session = requests.Session()

    if not check_health(base, session):
        return 1

    folders = list(args.folder)
    if not folders and args.data_root:
        folders = discover_folders(Path(args.data_root))
        if folders:
            print(f"\n  自动发现 {len(folders)} 个文件夹: {', '.join(folders[:6])}"
                  f"{' ...' if len(folders) > 6 else ''}")

    if not args.token:
        print("\n[2] 登录态检查")
        _skip("未提供 --token，跳过鉴权与图片检查")
        print("\n未提供令牌，只完成了健康检查。要检查图片直链请加 --token。")
        return 0

    if not check_auth(base, session, args.token):
        return 1

    if not folders:
        _skip("没有指定文件夹（--folder），也没有可自动发现的文件夹")
        return 0

    total_ok = total_fail = 0
    for folder in folders:
        ok, bad = check_folder(base, session, folder, args.limit)
        total_ok += ok
        total_fail += bad

    print("\n" + "=" * 56)
    print(f"图片检查：通过 {total_ok} 个，失败 {total_fail} 个")
    if total_fail:
        print("结论：❌ 有图片打不开，先别交付")
        return 1
    print("结论：✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
