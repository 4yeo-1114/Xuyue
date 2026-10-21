# -*- coding: utf-8 -*-
"""定期清旧留痕图——1016 不花钱项②。

批改产物图越积越多（marks_only_*/annotated_* 留痕图按学生×页数线性增长），
但它们只是展示/打印用的衍生图：批改记录（grading_history）和原卷（original_*、
test/ 上传件）才是数据本体。本模块按 mtime 清理超过保留期的留痕图，
原卷与记录永远不碰；已画进留痕的批注内容在 grading_history 里可随时重绘。

保留天数默认 90，环境变量 MARKS_IMAGE_RETENTION_DAYS 可调（0=关闭清理）。
每天在后台线程里扫一遍（进程内调度，不依赖 cron/计划任务）。
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

# 只清这两类衍生图；original_（原卷归档）、上传件、JSON 记录都不在名单里
_MARKS_PREFIXES = ("marks_only_", "annotated_")
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
# 留痕图落盘位置（每用户的 modify/ 与 home_img/ 子目录）
_TARGET_SUBDIRS = ("modify", "home_img")

_loop_started = False
_loop_lock = threading.Lock()


def retention_days() -> int:
    """保留天数；非法/负值按 0（关闭）处理。"""
    try:
        return max(0, int(os.environ.get("MARKS_IMAGE_RETENTION_DAYS", "90") or "90"))
    except ValueError:
        return 0


def cleanup_old_marks_images(older_than_days: int | None = None) -> dict:
    """删除过期留痕图，返回 {"removed", "freed_bytes", "errors", "days"}（磁盘字节数）。

    扫描 grading_data_all/grading_data_*/{modify,home_img}/ 下
    marks_only_*/annotated_* 图片文件，mtime 早于保留期的删除。
    单个文件失败只计 errors 不中断。
    """
    days = retention_days() if older_than_days is None else max(0, int(older_than_days))
    result = {"removed": 0, "freed_bytes": 0, "errors": 0, "days": days}
    if days <= 0:
        return result
    try:
        from app.grading.user_paths import grading_data_all_root

        all_root = grading_data_all_root()
    except Exception:
        result["errors"] += 1
        return result
    if not all_root.is_dir():
        return result
    cutoff = time.time() - days * 86400
    try:
        user_dirs = [d for d in all_root.iterdir() if d.is_dir()]
    except OSError:
        result["errors"] += 1
        return result
    for user_dir in user_dirs:
        for sub in _TARGET_SUBDIRS:
            target = user_dir / sub
            if not target.is_dir():
                continue
            try:
                entries = list(target.iterdir())
            except OSError:
                result["errors"] += 1
                continue
            for path in entries:
                if not path.is_file():
                    continue
                name = path.name
                if not name.startswith(_MARKS_PREFIXES):
                    continue
                if path.suffix.lower() not in _IMAGE_SUFFIXES:
                    continue
                try:
                    st = path.stat()
                    if st.st_mtime >= cutoff:
                        continue
                    path.unlink()
                    result["removed"] += 1
                    result["freed_bytes"] += st.st_size
                except OSError:
                    result["errors"] += 1
    return result


def start_cleanup_loop(interval_seconds: int = 24 * 3600) -> None:
    """启动每日清理线程（幂等；daemon 随进程退出）。启动后先等 10 分钟避开高峰。"""
    global _loop_started
    with _loop_lock:
        if _loop_started:
            return
        _loop_started = True

    def _loop():
        time.sleep(600)
        while True:
            try:
                r = cleanup_old_marks_images()
                if r["removed"]:
                    print(
                        f"[marks-cleanup] 清理过期留痕图 {r['removed']} 张，"
                        f"释放 {r['freed_bytes'] / 1048576:.1f}MB（保留 {r['days']} 天）"
                    )
            except Exception as e:  # noqa: BLE001 — 清理是旁路，绝不影响主服务
                print(f"[marks-cleanup] 清理异常: {e}")
            time.sleep(max(60, int(interval_seconds)))

    threading.Thread(target=_loop, daemon=True, name="marks-cleanup").start()
