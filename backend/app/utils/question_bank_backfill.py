# -*- coding: utf-8 -*-
"""C2 校本题库回填器（DL4b）：把一条错题记录 upsert 进 school_question_banks。

输入 record 字段与 app/grading/wrong_question_db.py 的错题记录对齐：
    paper_subject            科目
    question_type            题型
    question_text            题干（NOT NULL，指纹来源）
    estimated_correct_answer 参考答案
    school_id                可选；未给时用 DL2 默认学校占位（见 §文档 15）

三态 upsert（唯一键 uq_sqb_school_fp = UNIQUE(school_id, fingerprint)，DL4a）：
    - 同指纹已存在且 deleted_at 非空 → 恢复该行（清 deleted_at 再更新内容）
    - 同指纹已存在且未删 → 更新内容
    - 不存在 → 新建

查询始终按 (school_id, fingerprint) 命中、不区分 deleted_at，因此软删行同指纹
绝不触发 DuplicateEntry；写侧约定单写者（每校串行）调用，本函数不 commit。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.school_question_bank import SchoolQuestionBank
from app.utils.question_fingerprint import question_fingerprint

# DL2 回填脚本约定的固定默认学校 ID（docs/migrations/2026-08-20-school-backfill.sql）
DEFAULT_SCHOOL_ID = "11111111-1111-4111-8111-111111111111"


def upsert_question_to_bank(
    db: Session,
    record: dict,
    *,
    school_id: Optional[str] = None,
) -> dict:
    """回填一条错题进校本题库，返回动作描述（created / updated / restored）。

    仅 flush 不 commit，事务由调用方收口。
    """
    subject = record.get("paper_subject")
    question_type = record.get("question_type")
    question_text = str(record.get("question_text") or "").strip()
    correct_answer = record.get("estimated_correct_answer")
    if not question_text:
        raise ValueError("question_text 不能为空（题干是 NOT NULL 且为指纹来源）")
    sid = record.get("school_id") or school_id or DEFAULT_SCHOOL_ID
    fp = question_fingerprint(subject, question_type, question_text, correct_answer)

    row = (
        db.query(SchoolQuestionBank)
        .filter(
            SchoolQuestionBank.school_id == sid,
            SchoolQuestionBank.fingerprint == fp,
        )
        .first()
    )

    if row is None:
        row = SchoolQuestionBank(
            school_id=sid,
            subject=subject,
            question_type=question_type,
            question_text=question_text,
            correct_answer=correct_answer,
            fingerprint=fp,
        )
        db.add(row)
        db.flush()
        return {"action": "created", "id": row.id, "school_id": sid, "fingerprint": fp}

    was_soft_deleted = row.deleted_at is not None
    row.subject = subject
    row.question_type = question_type
    row.question_text = question_text
    row.correct_answer = correct_answer
    row.deleted_at = None  # 软删恢复：清 deleted_at（未删时仍置 None 幂等）
    db.flush()
    return {
        "action": "restored" if was_soft_deleted else "updated",
        "id": row.id,
        "school_id": sid,
        "fingerprint": fp,
    }
