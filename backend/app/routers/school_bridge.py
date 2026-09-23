# -*- coding: utf-8 -*-
"""家长端只读接口桥：暴露学校学生成绩数据（只读，无 PII 扩展）。

- GET /api/v1/school-bridge/students/{student_id}/scores → 在校成绩趋势
- GET /api/v1/school-bridge/students/{student_id}/class-compare → 学生 vs 班级对比

数据源：主平台当前业务库 MySQL（SQLAlchemy ORM models，app/models/），只读。
身份匹配：按学校 student_id（students.id）直查；家长端↔学校学生走 PG identity_link
（app/routers/identity_link.py 已暴露只读查询），本接口不复用跨库 join。
安全：student_id 不存在 → 404；仅返回成绩/班级聚合，绝不返回手机/住址等 PII。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.class_model import Class
from app.models.exam import Exam
from app.models.exam_score import ExamScore
from app.models.student import Student

router = APIRouter(prefix="/school-bridge", tags=["school_bridge"])


@router.get("/students/{student_id}/scores")
def student_scores(student_id: str, db: Session = Depends(get_db)):
    """在校成绩趋势：exam_scores × exams，按 exam_date 倒序。"""
    if db.query(Student.id).filter(Student.id == student_id).first() is None:
        raise HTTPException(status_code=404, detail="student not found")
    rows = (
        db.query(ExamScore, Exam)
        .join(Exam, Exam.id == ExamScore.exam_id)
        .filter(ExamScore.student_id == student_id)
        .order_by(Exam.exam_date.desc(), ExamScore.created_at.desc())
        .all()
    )
    return {
        "student_id": student_id,
        "items": [
            {
                "exam_id": es.exam_id,
                "exam_name": e.title,
                "subject": e.subject,
                "score": es.score,
                "exam_date": e.exam_date.isoformat() if e.exam_date else None,
                "created_at": es.created_at.isoformat() if es.created_at else None,
            }
            for es, e in rows
        ],
        "count": len(rows),
    }


@router.get("/students/{student_id}/class-compare")
def student_class_compare(student_id: str, db: Session = Depends(get_db)):
    """学生 vs 班级：取该生最近一次考试（exam_scores 库补列 class_avg/class_rank + classes）。"""
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="student not found")
    latest = (
        db.query(ExamScore, Exam)
        .join(Exam, Exam.id == ExamScore.exam_id)
        .filter(ExamScore.student_id == student_id)
        .order_by(Exam.exam_date.desc(), ExamScore.created_at.desc())
        .first()
    )
    if not latest:
        raise HTTPException(status_code=404, detail="no exam scores for student")
    es, e = latest
    cls = db.query(Class).filter(Class.id == es.class_id).first() if es.class_id else None
    return {
        "student_id": student_id,
        "subject": e.subject,
        "exam_id": es.exam_id,
        "exam_name": e.title,
        "exam_date": e.exam_date.isoformat() if e.exam_date else None,
        "student": {"score": es.score, "rank": es.class_rank},
        "class": {
            "avg_score": float(es.class_avg) if es.class_avg is not None else None,
            "student_count": cls.student_count if cls else None,
        },
    }
