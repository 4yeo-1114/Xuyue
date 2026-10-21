# -*- coding: utf-8 -*-
"""批改完成后自动导入学情 + 自动分层（客户清单 #1「批改完自动分层」）。

链路：批改落盘 → grading.router._schedule_auto_sync_class → auto_sync_folder_after_grading：
  1) 解析 folder_safe `cls_{class_id}__{exam_name}`（非班级文件夹直接跳过）；
  2) 从 grading_history（default+manual 合并，人工覆盖同名；作文 essay 历史整卷语义）
     按卷盒提取每生整卷总分（与前端 computeBoxScoreGrade/box_totals 同口径：
     智能/参照/自主多页求和，作文多页取最大）；
  3) 复用 student_analysis.import_scores_core（成绩历史 + 当前分 + 错题）；
  4) 复用 layered_push_service.apply_auto_tiers（阈值取分层推送设置，缺省 80/60）。

本模块只做编排：重依赖（grading.router / student_analysis / SessionLocal）全部
函数内懒加载，避免与 grading.router 循环 import。所有路径解析依赖 grading 用户
上下文，调用方必须用 run_with_grading_user 包住。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# 与 grading.router._paper_box_display_name / ImportScoresDialog.paperBoxName 同口径
_PAPER_BOX_RE = re.compile(r"^(?P<name>.+)_\d+$")


def parse_class_folder(folder_safe: str) -> Optional[Tuple[str, str]]:
    """cls_{class_token}__{exam_name} → (class_id, exam_name)；非班级文件夹返回 None。

    与 response_log_db._derive_class_id / 前端 displayFolderName 同口径：取第一个 `__` 切分。
    """
    safe = str(folder_safe or "")
    if not safe.startswith("cls_"):
        return None
    prefix, sep, exam_name = safe.partition("__")
    if not sep or not exam_name:
        return None
    class_id = prefix[4:]
    if not class_id or not exam_name:
        return None
    return class_id, exam_name


def paper_box_display_name(filename: str) -> str:
    """张三_1.jpg → 张三（卷盒名=去掉页码后缀的试卷名）。"""
    stem = Path(str(filename or "")).stem
    match = _PAPER_BOX_RE.match(stem)
    return (match.group("name") if match else stem) or ""


def merge_completed(default_completed: Any, manual_completed: Any) -> Dict[str, Any]:
    """default+manual 两份历史的 completed 按文件名合并：同名文件人工结果覆盖智能结果。"""
    merged: Dict[str, Any] = dict(default_completed or {})
    merged.update(manual_completed or {})
    return merged


def extract_scores_from_completed(completed: Any, essay_completed: Any = None) -> Dict[str, float]:
    """{文件名: item} → {卷盒名: 整卷总分}；无分/坏值跳过。

    合并口径（与前端 computeBoxScoreGrade / box_totals 一致）：
      - 智能/参照/自主阅卷：每页独立计分 → 同卷多页 score_total 累加
      - 作文批改：score_total 是整卷总分，多页重复写同一总分 → 取最大值，不累加
    同一卷盒同时出现在两边（两种通道都批过）时作文整卷总分视为权威。
    """
    totals: Dict[str, float] = {}

    def _num(info: Any) -> Optional[float]:
        if not isinstance(info, dict):
            return None
        raw = info.get("score_total")
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    # 先按逐页累加收普通通道
    for filename, info in (completed or {}).items():
        num = _num(info)
        if num is None:
            continue
        box = paper_box_display_name(filename)
        if not box:
            continue
        totals[box] = totals.get(box, 0.0) + num

    # 作文通道：整卷总分取最大；命中即覆盖该卷盒（权威）
    essay_boxes: Dict[str, float] = {}
    for filename, info in (essay_completed or {}).items():
        num = _num(info)
        if num is None:
            continue
        box = paper_box_display_name(filename)
        if not box:
            continue
        essay_boxes[box] = max(essay_boxes.get(box, num), num)
    totals.update(essay_boxes)
    return totals


def class_average(score_map: Dict[str, float]) -> Optional[int]:
    """班级平均分：与 ImportScoresDialog 一致，Math.round(sum/len)（.5 向上）。"""
    if not score_map:
        return None
    return int(sum(score_map.values()) / len(score_map) + 0.5)


def read_folder_meta(folder_safe: str) -> Dict[str, Any]:
    """文件夹 meta.json（subject/grade/homework_type/class_id）；读不到返回 {}。"""
    from app.grading.response_log_db import _read_folder_meta

    return _read_folder_meta(folder_safe) or {}


def load_folder_completed(folder_safe: str) -> Dict[str, Any]:
    """读 default+manual 批改历史 completed 并按文件名合并（人工覆盖同名）。"""
    from app.grading.router import _read_grading_history

    default_completed = (_read_grading_history(folder_safe, "default") or {}).get("completed") or {}
    manual_completed = (_read_grading_history(folder_safe, "manual") or {}).get("completed") or {}
    return merge_completed(default_completed, manual_completed)


def load_folder_essay_completed(folder_safe: str) -> Dict[str, Any]:
    """读作文批改历史 completed（独立文件，整卷总分语义，与智能通道分开合并）。"""
    from app.grading.router import _read_essay_history

    return (_read_essay_history(folder_safe) or {}).get("completed") or {}


def auto_sync_folder_after_grading(user_id: str, folder_safe: str) -> Dict[str, Any]:
    """批改落盘后自动导入学情 + 按成绩自动分层。返回执行摘要；不合规场景以 skipped 标记。

    必须在 grading 用户上下文中调用（读批改历史依赖 user_paths）。
    """
    # 轻成绩表（对齐批改君 exam_scores）：任何文件夹都重建每生成绩汇总行
    #（不限班级文件夹），失败只记摘要不阻断后面的学情/分层链路
    score_summary: Any
    try:
        from app.grading.score_summary_db import sync_folder_score_summaries

        score_summary = sync_folder_score_summaries(user_id, folder_safe)
    except Exception as e:
        score_summary = {"error": str(e)}

    parsed = parse_class_folder(folder_safe)
    if not parsed:
        return {"skipped": "not_class_folder", "folder": folder_safe, "score_summary": score_summary}
    class_id, exam_name = parsed

    completed = load_folder_completed(folder_safe)
    essay_completed = load_folder_essay_completed(folder_safe)
    score_map = extract_scores_from_completed(completed, essay_completed)
    if not score_map:
        # 尚无带分结果（如还在切题/未统分）；空列表绝不能进 _sync_exam_scores
        # （会把该场已有成绩当缺失清掉），与导入按钮「无成绩」直接报错同理。
        return {"skipped": "no_scores", "folder": folder_safe, "class_id": class_id}

    scores = [{"student_name": name, "score": value} for name, value in score_map.items()]
    class_avg = class_average(score_map)

    meta = read_folder_meta(folder_safe)
    subject = str((meta or {}).get("subject") or "").strip() or exam_name

    from app.database import SessionLocal
    from app.models.class_model import Class
    from app.utils.class_access import can_view_class

    db = SessionLocal()
    try:
        cls_row = db.query(Class).filter(Class.id == class_id).first()
        if not cls_row:
            return {"skipped": "class_not_found", "folder": folder_safe, "class_id": class_id}
        if not can_view_class(db, user_id, class_id):
            return {"skipped": "no_permission", "folder": folder_safe, "class_id": class_id}

        from app.routers.student_analysis import import_scores_core

        imported = import_scores_core(
            db,
            class_id=class_id,
            subject=subject,
            exam_name=exam_name,
            class_avg=class_avg,
            scores=scores,
            record_id=folder_safe,
        )

        from app.services import layered_push_service as svc

        tier_result = svc.apply_auto_tiers(db, class_id, subject)

        # 客户清单#2：学情同步成功后自动配套练习（静默兜底，绝不影响本主链路返回）
        try:
            from app.services.auto_variant import auto_generate_variants_after_grading

            auto_generate_variants_after_grading(user_id, folder_safe)
        except Exception:
            pass

        return {
            "folder": folder_safe,
            "class_id": class_id,
            "subject": subject,
            "exam_name": exam_name,
            "students": len(scores),
            "class_avg": class_avg,
            "imported_count": imported.get("imported_count"),
            "tier_updated": tier_result.get("updated"),
            "tier_no_score": tier_result.get("no_score"),
            "thresholds": tier_result.get("thresholds"),
            "score_summary": score_summary,
        }
    finally:
        db.close()
