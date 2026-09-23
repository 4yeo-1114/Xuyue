# -*- coding: utf-8 -*-
"""R1 逐题响应日志落库（旁路写入，绝不阻断批改主流程）。

数据底座：供学情预警 / bandit 错题推荐使用。
只做 INSERT（SessionLocal 自建 session + add_all + commit），不做任何 DELETE/UPDATE。
写库范式对齐 app/grading/grading_stats.py 的 _increment（SessionLocal + try/except 静默）。

R2 作业采集：学科/年级/班级/作业类型 优先取显式入参，缺省从文件夹 meta.json
与 cls_<class_id>__ 前缀回填，落到 response_logs 对应列（纯追加，可空）。
"""
from __future__ import annotations

import json
from typing import Any, Optional

from app.database import SessionLocal
from app.models.response_log import ResponseLog

# vlm correctResult / baidu_correct_result 码 -> 统一 status
_CODE_TO_STATUS = {
    1: "correct",
    2: "wrong",
    3: "unanswered",
}
# vlm result 文本 -> 统一 status
_RESULT_TEXT_TO_STATUS = {
    "对": "correct",
    "正确": "correct",
    "错": "wrong",
    "错误": "wrong",
    "半对": "partial",
    "未作答": "unanswered",
}
# manual slot.status -> 统一 status（ungraded 不计入）
_MANUAL_STATUS_MAP = {
    "correct": "correct",
    "wrong": "wrong",
    "partial": "partial",
    "unanswered": "unanswered",
}

META_FILENAME = "meta.json"


def _to_float(value: Any) -> Optional[float]:
    try:
        f = float(value)
        return f if f == f else None  # 过滤 NaN
    except (TypeError, ValueError):
        return None


def _derive_status(block: dict) -> Optional[str]:
    """从批改块提取统一 status。

    优先级：manual slot.status > correctResult / baidu_correct_result 码 > result 文本。
    """
    raw = block.get("status")
    if isinstance(raw, str) and raw:
        s = _MANUAL_STATUS_MAP.get(raw.strip().lower())
        if s:
            return s
    code = block.get("baidu_correct_result", block.get("correctResult"))
    if code is not None:
        try:
            c = int(code)
        except (TypeError, ValueError):
            c = None
        if c in _CODE_TO_STATUS:
            return _CODE_TO_STATUS[c]
    result = block.get("result")
    if isinstance(result, str):
        r = result.strip()
        if r in _RESULT_TEXT_TO_STATUS:
            return _RESULT_TEXT_TO_STATUS[r]
    return None


def _derive_class_id(folder_safe: str) -> str:
    """从 cls_<class_id>__<exam_name> 文件夹名解析 class_id；非班级文件夹返回空串。"""
    safe = str(folder_safe or "").strip()
    if not safe.startswith("cls_") or "__" not in safe:
        return ""
    return safe.split("__", 1)[0][4:].strip()


def _read_folder_meta(folder_safe: str) -> dict:
    """读取作业文件夹 meta.json（subject/grade/homework_type/class_id），失败返回空 dict。"""
    safe = str(folder_safe or "").strip()
    if not safe:
        return {}
    try:
        from app.grading.user_paths import correct_docs_dir

        p = correct_docs_dir() / safe / META_FILENAME
        if not p.is_file():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _row_from_block(
    *,
    user_id: str,
    folder_safe: str,
    paper_name: str,
    engine: str,
    block: dict,
    class_id: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    homework_type: Optional[str] = None,
) -> dict:
    """把单个批改块归一化为 response_logs 行 dict；缺字段一律 None。"""
    status = _derive_status(block)
    qid = block.get("slot_id")
    if qid is None:
        index = block.get("index")
        sub_index = block.get("sub_index")
        qid = f"{index}" if sub_index is None else f"{index}_{sub_index}"
    raw_snapshot: dict = {}
    try:
        # ensure_ascii=False 保留中文；default=str 兜底不可序列化值
        raw_snapshot = json.loads(json.dumps(block, ensure_ascii=False, default=str))
    except Exception:
        raw_snapshot = dict(block)
    return {
        "user_id": user_id,
        "folder_safe": folder_safe,
        "paper_name": paper_name,
        "engine": engine,
        "class_id": class_id or None,
        "subject": subject or None,
        "grade": grade or None,
        "homework_type": homework_type or None,
        "question_id": str(qid).strip() or None,
        "question_content": str(block.get("question_content") or block.get("question") or "").strip() or None,
        "correct_answer": str(block.get("correct_answer") or "").strip() or None,
        "student_answer": str(block.get("student_answer") or "").strip() or None,
        "status": status,
        "is_correct": True if status == "correct" else (False if status else None),
        "score": _to_float(block.get("score")),
        "max_score": _to_float(block.get("max_score")),
        "confidence": _to_float(block.get("confidence")),
        "raw_json": raw_snapshot,
    }


def write_response_logs(
    user_id: str,
    folder_safe: str,
    paper_name: str,
    engine: str,
    blocks: list,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    homework_type: Optional[str] = None,
    class_id: Optional[str] = None,
) -> None:
    """把一页试卷的逐题结果写入 response_logs（纯追加）。

    空 blocks / 缺 user_id / 无有效 block → 静默返回；
    任何异常 try/except 静默（旁路写入绝不阻断批改主流程）。

    R2 作业采集：学科/年级/班级/作业类型优先取显式入参，缺省从文件夹 meta.json
    与 cls_<class_id>__ 前缀回填。
    """
    if not blocks:
        return
    uid = str(user_id or "").strip()
    if not uid:
        return
    safe = str(folder_safe or "").strip()
    meta = _read_folder_meta(safe)
    subject = str(subject or "").strip() or str(meta.get("subject") or "").strip() or None
    grade = str(grade or "").strip() or str(meta.get("grade") or "").strip() or None
    homework_type = str(homework_type or "").strip() or str(meta.get("homework_type") or "").strip() or None
    class_id = str(class_id or "").strip() or str(meta.get("class_id") or "").strip() or _derive_class_id(safe) or None
    rows = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        rows.append(
            ResponseLog(
                **_row_from_block(
                    user_id=uid,
                    folder_safe=safe,
                    paper_name=str(paper_name or "").strip(),
                    engine=str(engine or "").strip(),
                    block=block,
                    class_id=class_id,
                    subject=subject,
                    grade=grade,
                    homework_type=homework_type,
                )
            )
        )
    if not rows:
        return
    db = SessionLocal()
    try:
        db.add_all(rows)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"逐题响应日志写入失败: {folder_safe}/{paper_name}: {e}")
    finally:
        db.close()
