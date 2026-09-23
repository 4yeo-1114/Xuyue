from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
import pandas as pd
import io
import json
import random
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import Dict, List, Literal, Optional, Set, Tuple
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import bind_grading_user_context, get_current_user_id
from app.models.student_analysis import StudentAnalysis, StudentScoreHistory, StudentWrongQuestion
from app.models.student import Student
from app.models.exam import Exam
from app.models.exam_score import ExamScore
from app.models.class_model import Class
from app.models.class_analysis import ClassAnalysisReport
# 引入即注册到 Base.metadata，保证 create_all 自动建 wrong_question_review 表
from app.models.wrong_question_review import WrongQuestionReview
from app.models.wrong_question_kp_bridge import WrongQuestionKpBridge
from app.utils.anonymize import Anonymizer
from app.utils.class_access import can_view_class
from app.services.grade_scores import grade_for_score
from app.services.trend_alert import build_trend_alerts
from app.schemas.student_analysis import (
    StudentAnalysisUpsert,
    StudentAnalysisResponse,
    ImportScoresRequest,
    ScoreHistoryResponse,
    AIDiagnosisRequest,
    WrongQuestionResponse,
    ExamScoreWriteItem,
    ExamScoreItem,
)
from app.schemas.common import ApiResponse
from app.services.ai_policy import assert_no_sensitive_input, require_ai_access
from app.routers.targeted_improvement import _filter_redline_deep
from app.utils.qwen_settings import AI_GENERATOR, get_llm_config
from app.grading.user_paths import grading_history_dir, ai_diagnosis_dir
from app.grading.router import _class_folder_prefix, _read_grading_history, _parse_ai_result_to_counts
from app.grading.wrong_question_db import _analysis_json_path, _read_json, _ct_root, ct_image_api_url_for_rel, resolve_ct_image_path

router = APIRouter(
    prefix="/student-analysis",
    tags=["student_analysis"],
    dependencies=[Depends(bind_grading_user_context)],
)


def _assert_class_access(db: Session, user_id: str, class_id: str) -> None:
    """校验调用者对目标班级有访问权限（教师=所带班级，班主任/副班主任=本班，系统管理员/校级管理者/年级组长=全校），否则 403。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级访问权限")


# ── E04 成绩等级制：exam_scores 读写接口（堵前端 Supabase 直连，走后端鉴权）────────────────
# 契约:
#   读: GET  /student-analysis/exam-scores?exam_id=... → [{ student_id, score, grade }]
#   写: POST /student-analysis/exam-scores             → 请求 [{ exam_id, student_id, score }]
#       → 返回 [{ student_id, score, grade }]（grade 由后端 grade_for_score 计算落库）
# 说明: 每个 exam 先经 _assert_class_access（can_view_class）校验，未授权班级一律 403。

@router.get("/exam-scores", response_model=ApiResponse[List[ExamScoreItem]])
def get_exam_scores(
    exam_id: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """E04 读：按 exam 批量读全班成绩，返回 { student_id, score, grade }。

    grade 为空的历史数据按分数派生（纯函数返回，不落库）。
    """
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")
    _assert_class_access(db, user_id, exam.class_id)

    rows = db.query(ExamScore).filter(ExamScore.exam_id == exam_id).all()
    return ApiResponse(data=[
        ExamScoreItem(
            student_id=row.student_id,
            score=row.score,
            grade=row.grade or grade_for_score(row.score),
        )
        for row in rows
    ])


@router.post("/exam-scores", response_model=ApiResponse[List[ExamScoreItem]])
def upsert_exam_scores(
    body: List[ExamScoreWriteItem],
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """E04 写：按 exam 批量保存/更新全班分数，后端算 grade 落库（excellent|good|pass|needs_work）。

    请求体为 JSON 数组 [{ exam_id, student_id, score }]；返回 [{ student_id, score, grade }]。
    同一请求可覆盖多个 exam，但每个 exam 都会做班级访问鉴权；未授权班级 403。
    """
    if not body:
        raise HTTPException(status_code=400, detail="请求不能为空")

    # 按 exam 去重校验班级访问权限（避免同一 exam 重复鉴权）
    exams = db.query(Exam).filter(Exam.id.in_({item.exam_id for item in body})).all()
    exam_map = {exam.id: exam for exam in exams}
    checked: Set[str] = set()
    for item in body:
        exam = exam_map.get(item.exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail=f"考试不存在: {item.exam_id}")
        if item.exam_id not in checked:
            _assert_class_access(db, user_id, exam.class_id)
            checked.add(item.exam_id)

    # R2 多校归属：exam → class → school_id 回填（school_id 缺失宽松处理，不影响既有逻辑）
    class_ids = {exam.class_id for exam in exams}
    class_rows = db.query(Class.id, Class.school_id).filter(Class.id.in_(class_ids)).all()
    class_school_map = {cid: sid for cid, sid in class_rows}

    result: List[ExamScoreItem] = []
    for item in body:
        exam = exam_map[item.exam_id]
        grade = grade_for_score(item.score)
        row = db.query(ExamScore).filter(
            ExamScore.exam_id == item.exam_id,
            ExamScore.student_id == item.student_id,
        ).first()
        if row:
            row.score = item.score
            row.grade = grade
            if row.school_id is None:
                row.school_id = class_school_map.get(exam.class_id)
        else:
            db.add(ExamScore(
                user_id=user_id,
                exam_id=item.exam_id,
                student_id=item.student_id,
                school_id=class_school_map.get(exam.class_id),
                score=item.score,
                grade=grade,
            ))
        result.append(ExamScoreItem(student_id=item.student_id, score=item.score, grade=grade))

    db.commit()
    return ApiResponse(data=result)


@router.get("/list", response_model=ApiResponse[List[StudentAnalysisResponse]])
def list_student_analysis(
    class_id: str = Query(...),
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    analysis_list = db.query(StudentAnalysis).filter(
        StudentAnalysis.class_id == class_id,
        StudentAnalysis.subject == subject
    ).all()
    
    return ApiResponse(data=analysis_list)

@router.get("", response_model=ApiResponse[StudentAnalysisResponse])
def get_student_analysis(
    class_id: str = Query(...),
    student_name: str = Query(...),
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    analysis = db.query(StudentAnalysis).filter(
        StudentAnalysis.class_id == class_id,
        StudentAnalysis.student_name == student_name,
        StudentAnalysis.subject == subject
    ).first()
    
    if not analysis:
        # Return empty data instead of 404 to let frontend handle defaults
        return ApiResponse(data={
            "id": "",
            "class_id": class_id,
            "student_name": student_name,
            "subject": subject,
            "target_score": None,
            "current_score": None
        })
        
    return ApiResponse(data=analysis)

@router.post("", response_model=ApiResponse[StudentAnalysisResponse])
def upsert_student_analysis(
    body: StudentAnalysisUpsert,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, body.class_id)
    analysis = db.query(StudentAnalysis).filter(
        StudentAnalysis.class_id == body.class_id,
        StudentAnalysis.student_name == body.student_name,
        StudentAnalysis.subject == body.subject
    ).first()
    
    if analysis:
        # Check if the field is present in the request payload, not just whether it is None.
        # This allows explicitly setting the score to None.
        body_dict = body.dict(exclude_unset=True)
        if "target_score" in body_dict:
            analysis.target_score = body.target_score
        if "current_score" in body_dict:
            analysis.current_score = body.current_score
    else:
        analysis = StudentAnalysis(
            class_id=body.class_id,
            student_name=body.student_name,
            subject=body.subject,
            target_score=body.target_score,
            current_score=body.current_score
        )
        db.add(analysis)
        
    db.commit()
    db.refresh(analysis)
    
    return ApiResponse(data=analysis)

@router.get("/score-history", response_model=ApiResponse[List[ScoreHistoryResponse]])
def get_student_score_history(
    class_id: str = Query(...),
    student_name: str = Query(...),
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    history = db.query(StudentScoreHistory).filter(
        StudentScoreHistory.class_id == class_id,
        StudentScoreHistory.student_name == student_name,
        StudentScoreHistory.subject == subject
    ).order_by(StudentScoreHistory.created_at.asc()).all()
    
    return ApiResponse(data=history)


@router.get("/trend-alert", response_model=ApiResponse[dict])
def get_student_trend_alerts(
    student_id: str = Query(...),
    class_id: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """R5 学生级成绩趋势预警（连续下滑/低于目标/排名连降/低于及格线）。

    数据不足（<2 次有效考试）→ alerts 为空列表（诚实不预警）。
    实时派生，不落库；家长端真入口留待后续接入（见 app/services/trend_alert.py 模块注释）。
    """
    _assert_class_access(db, user_id, class_id)
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    if str(student.class_id) != str(class_id):
        raise HTTPException(status_code=403, detail="学生不存在或不在指定班级")
    alerts = build_trend_alerts(db, student_id)
    total_exams = db.query(ExamScore).filter(ExamScore.student_id == student_id).count()
    return ApiResponse(data={
        "alerts": alerts,
        "student_id": student_id,
        "total_exams": total_exams,
    })


@router.delete("/score-history/exam", response_model=ApiResponse[dict])
def delete_exam_history(
    class_id: str = Query(...),
    student_name: str = Query(...),
    subject: str = Query(...),
    exam_name: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    # delete from StudentScoreHistory
    db.query(StudentScoreHistory).filter(
        StudentScoreHistory.class_id == class_id,
        StudentScoreHistory.student_name == student_name,
        StudentScoreHistory.subject == subject,
        StudentScoreHistory.exam_name == exam_name
    ).delete()

    # Also delete from StudentWrongQuestion
    db.query(StudentWrongQuestion).filter(
        StudentWrongQuestion.class_id == class_id,
        StudentWrongQuestion.student_name == student_name,
        StudentWrongQuestion.subject == subject,
        StudentWrongQuestion.exam_name == exam_name
    ).delete()

    # Update current_score in StudentAnalysis to the latest score in StudentScoreHistory
    # or set to null if no history left
    analyses = db.query(StudentAnalysis).filter(
        StudentAnalysis.class_id == class_id,
        StudentAnalysis.student_name == student_name,
        StudentAnalysis.subject == subject
    ).all()

    for analysis in analyses:
        latest_history = db.query(StudentScoreHistory).filter(
            StudentScoreHistory.class_id == class_id,
            StudentScoreHistory.subject == subject,
            StudentScoreHistory.student_name == analysis.student_name
        ).order_by(StudentScoreHistory.created_at.desc()).first()

        if latest_history:
            analysis.current_score = latest_history.score
        else:
            analysis.current_score = None

    db.commit()
    return ApiResponse(data={"ok": True})


def _normalize_score_payload(scores):
    normalized = {}
    for item in scores:
        if isinstance(item, dict):
            student_name = str(item.get("student_name") or "").strip()
            raw_score = item.get("score")
        else:
            student_name = str(getattr(item, "student_name", "") or "").strip()
            raw_score = getattr(item, "score", None)
        if not student_name:
            continue
        try:
            score = int(round(float(raw_score)))
        except Exception:
            score = 0
        normalized[student_name] = score
    return [{"student_name": name, "score": score} for name, score in normalized.items()]


def _refresh_current_scores(db: Session, class_id: str, subject: str, student_names: Set[str]) -> None:
    for student_name in student_names:
        analysis = db.query(StudentAnalysis).filter(
            StudentAnalysis.class_id == class_id,
            StudentAnalysis.student_name == student_name,
            StudentAnalysis.subject == subject
        ).first()
        latest_history = db.query(StudentScoreHistory).filter(
            StudentScoreHistory.class_id == class_id,
            StudentScoreHistory.student_name == student_name,
            StudentScoreHistory.subject == subject
        ).order_by(StudentScoreHistory.created_at.desc()).first()
        if analysis:
            analysis.current_score = latest_history.score if latest_history else None


def _trim_score_history(db: Session, class_id: str, subject: str, student_names: Set[str]) -> None:
    for student_name in student_names:
        student_history = db.query(StudentScoreHistory).filter(
            StudentScoreHistory.class_id == class_id,
            StudentScoreHistory.student_name == student_name,
            StudentScoreHistory.subject == subject
        ).order_by(StudentScoreHistory.created_at.desc()).all()
        if len(student_history) > 9:
            for old_record in student_history[9:]:
                db.delete(old_record)


def _sync_exam_scores(
    db: Session,
    *,
    class_id: str,
    subject: str,
    exam_name: str,
    class_avg: Optional[int],
    scores,
) -> Tuple[List[Dict], Set[str], bool]:
    normalized_scores = _normalize_score_payload(scores)
    score_by_student = {item["student_name"]: item["score"] for item in normalized_scores}
    existing_rows = db.query(StudentScoreHistory).filter(
        StudentScoreHistory.class_id == class_id,
        StudentScoreHistory.subject == subject,
        StudentScoreHistory.exam_name == exam_name
    ).order_by(StudentScoreHistory.created_at.asc()).all()
    existing_by_student: Dict[str, List[StudentScoreHistory]] = {}
    for row in existing_rows:
        existing_by_student.setdefault(row.student_name, []).append(row)

    affected_students = set(score_by_student.keys()) | set(existing_by_student.keys())

    for student_name in set(existing_by_student.keys()) - set(score_by_student.keys()):
        for row in existing_by_student.get(student_name, []):
            db.delete(row)

    for student_name, score in score_by_student.items():
        analysis = db.query(StudentAnalysis).filter(
            StudentAnalysis.class_id == class_id,
            StudentAnalysis.student_name == student_name,
            StudentAnalysis.subject == subject
        ).first()
        if not analysis:
            analysis = StudentAnalysis(
                class_id=class_id,
                student_name=student_name,
                subject=subject,
            )
            db.add(analysis)

        rows = existing_by_student.get(student_name, [])
        if rows:
            keep = rows[0]
            keep.score = score
            keep.class_avg = class_avg
            for duplicate in rows[1:]:
                db.delete(duplicate)
        else:
            history = StudentScoreHistory(
                class_id=class_id,
                student_name=student_name,
                subject=subject,
                exam_name=exam_name,
                score=score,
                class_avg=class_avg
            )
            db.add(history)

    db.flush()
    _trim_score_history(db, class_id, subject, set(score_by_student.keys()))
    db.flush()
    _refresh_current_scores(db, class_id, subject, affected_students)
    return normalized_scores, affected_students, bool(existing_rows)

@router.post("/import-scores", response_model=ApiResponse[dict])
def import_scores(
    body: ImportScoresRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, body.class_id)
    normalized_scores, _, refreshed = _sync_exam_scores(
        db,
        class_id=body.class_id,
        subject=body.subject,
        exam_name=body.exam_name,
        class_avg=body.class_avg,
        scores=body.scores,
    )
    
    # 3. Process wrong questions if record_id is provided
    if body.record_id:
        safe = body.record_id
        # Remove old wrong questions for this exam
        db.query(StudentWrongQuestion).filter(
            StudentWrongQuestion.class_id == body.class_id,
            StudentWrongQuestion.subject == body.subject,
            StudentWrongQuestion.exam_name == body.exam_name
        ).delete()
        
        # Read smart grading history
        history = _read_grading_history(safe, "default")
        completed = history.get("completed", {})
        
        # Read manual grading history
        manual_history = _read_grading_history(safe, "manual")
        manual_completed = manual_history.get("completed", {})
        
        for item in normalized_scores:
            wrong_questions = []
            student_name = item["student_name"]
            
            # Check smart grading
            for filename, info in completed.items():
                if _paper_box_stem(filename) == student_name:
                    counts, blocks = _parse_ai_result_to_counts(info.get("result", ""))
                    for b in blocks:
                        if b.get("status") in ["wrong", "blank"]:
                            wrong_questions.append(b.get("title", ""))
                        for sub in b.get("subItems", []):
                            if sub.get("status") in ["wrong", "blank"]:
                                wrong_questions.append(f"{b.get('title', '')}-{sub.get('title', '')}")
                                
            # Check manual grading
            for filename, info in manual_completed.items():
                if _paper_box_stem(filename) == student_name:
                    try:
                        parsed = json.loads(info.get("result", "{}"))
                        scores = parsed.get("scores", {})
                        for title, score in scores.items():
                            if score == 0:
                                wrong_questions.append(title)
                    except Exception:
                        pass
                        
            # Insert into database
            wrong_questions = list(set(wrong_questions))
            for q_title in wrong_questions:
                wq = StudentWrongQuestion(
                    class_id=body.class_id,
                    student_name=student_name,
                    subject=body.subject,
                    exam_name=body.exam_name,
                    question_title=q_title
                )
                db.add(wq)
                
        db.commit()
    else:
        db.commit()

    return ApiResponse(data={"ok": True, "imported_count": len(normalized_scores), "refreshed": refreshed})


@router.post("/import-scores/excel", response_model=ApiResponse[dict])
def import_scores_excel(
    class_id: str = Form(...),
    subject: str = Form(...),
    exam_name: str = Form(...),
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    try:
        content = file.file.read()
        df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析 Excel 文件失败: {str(e)}")

    if "姓名" not in df.columns or "分数" not in df.columns:
        raise HTTPException(status_code=400, detail="Excel 必须包含“姓名”和“分数”列")

    scores_payload = []
    total_score = 0
    valid_count = 0

    for _, row in df.iterrows():
        student_name = str(row.get("姓名", "")).strip()
        score_val = row.get("分数", "")
        
        if not student_name or student_name == "nan":
            continue
            
        try:
            if pd.isna(score_val) or str(score_val).strip() == "":
                score = 0
            else:
                score = int(float(score_val))
        except ValueError:
            score = 0
            
        scores_payload.append({"student_name": student_name, "score": score})
        total_score += score
        valid_count += 1

    if valid_count == 0:
        raise HTTPException(status_code=400, detail="未能在 Excel 中找到有效的成绩数据")

    # Get valid student names for this class to filter out students not in this class
    from app.models.student import Student
    valid_students = db.query(Student.name).filter(Student.class_id == class_id).all()
    valid_student_names = {s[0] for s in valid_students}

    # Filter payload to only include students in this class
    filtered_payload = [item for item in scores_payload if item["student_name"] in valid_student_names]
    
    if not filtered_payload:
        raise HTTPException(status_code=400, detail="Excel 中的学生都不在当前班级中")

    # Recalculate average based on filtered students
    filtered_total = sum(item["score"] for item in filtered_payload)
    class_avg = round(filtered_total / len(filtered_payload))

    normalized_scores, _, refreshed = _sync_exam_scores(
        db,
        class_id=class_id,
        subject=subject,
        exam_name=exam_name,
        class_avg=class_avg,
        scores=filtered_payload,
    )
    db.commit()

    return ApiResponse(data={"ok": True, "imported_count": len(normalized_scores), "refreshed": refreshed})


def _paper_box_stem(filename: str) -> str:
    stem = Path(str(filename or "")).stem.strip()
    base, sep, suffix = stem.rpartition("_")
    if sep and suffix.isdigit() and base:
        return base
    return stem

def _get_diagnosis_file(class_id: str, student_name: str, subject: str) -> Path:
    safe_name = urllib.parse.quote(f"{class_id}_{student_name}_{subject}", safe="")
    return ai_diagnosis_dir() / f"{safe_name}.json"


# ── R1 · GET /ai-diagnosis 无落盘文件时的数据库聚合推导 ────────────────────────────
# 演示环境无 AI key，POST /ai-diagnosis 不会产生落盘文件，前端能力雷达六维全零。
# 这里从 student_score_history / student_wrong_questions / class_analysis_reports 聚合推导，
# 输出 shape 与真实 AI 产物完全一致：[{ dim, student(0-100), class(0-100), subDims:[{name, mastery}] }]。

# 六维维度名，与 POST /ai-diagnosis 的 dimensions_text 及 demo_seed.SUBJECT_CAPABILITY_DIMS 完全一致
_SUBJECT_DIMENSIONS: Dict[str, List[str]] = {
    "语文": ["作文结构", "阅读理解", "基础知识", "古诗文", "语言表达", "创新思维"],
    "数学": ["计算能力", "逻辑推理", "空间想象", "数据分析", "建模应用", "创新思维"],
    "英语": ["听力理解", "口语表达", "阅读理解", "写作能力", "词汇语法", "翻译能力"],
    "科学": ["基础掌握", "应用能力", "综合分析", "创新思维", "逻辑推理", "知识广度"],
}

# 各学科维度 → 错题标题关键词（命中则该维偏低 + 生成 subDims）
_DIM_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "语文": {
        "作文结构": ["作文", "写作", "结构", "开头", "结尾", "段落"],
        "阅读理解": ["阅读", "理解", "短文", "文章", "主旨", "中心思想"],
        "基础知识": ["拼音", "字词", "词语", "成语", "病句", "标点", "读音", "错别字", "看拼音"],
        "古诗文": ["古诗", "诗词", "文言文", "默写", "名句", "诗句"],
        "语言表达": ["表达", "语言", "口语", "概括", "复述", "排序", "选词填空"],
        "创新思维": ["想象", "创新", "续写", "仿写", "拓展"],
    },
    "数学": {
        "计算能力": ["计算", "口算", "竖式", "递等式", "简便", "运算", "单位换算"],
        "逻辑推理": ["逻辑", "推理", "判断", "规律", "分类", "比较"],
        "空间想象": ["空间", "图形", "几何", "面积", "体积", "周长", "对称", "平移", "旋转"],
        "数据分析": ["数据", "统计", "平均数", "图表", "统计与概率"],
        "建模应用": ["应用", "解决问题", "应用题", "方程", "模型"],
        "创新思维": ["创新", "开放", "策略", "一题多解"],
    },
    "英语": {
        "听力理解": ["听力", "听音", "listen", "sound"],
        "口语表达": ["口语", "朗读", "对话", "speak", "say"],
        "阅读理解": ["阅读", "短文", "理解", "read"],
        "写作能力": ["写作", "书面表达", "作文", "write"],
        "词汇语法": ["词汇", "单词", "语法", "拼写", "单项选择", "时态", "介词", "冠词", "词形"],
        "翻译能力": ["翻译", "英译汉", "汉译英", "句子"],
    },
    "科学": {
        "基础掌握": ["基础", "概念", "知识", "定义", "原理", "填空", "选择"],
        "应用能力": ["应用", "运用", "解决", "实践", "实验"],
        "综合分析": ["分析", "综合", "比较", "归纳", "总结"],
        "创新思维": ["创新", "设计", "创造", "拓展", "开放"],
        "逻辑推理": ["推理", "逻辑", "判断", "规律", "假设"],
        "知识广度": ["常识", "现象", "生活", "科学", "植物", "自然"],
    },
}


def _subject_dimensions(subject: str) -> List[str]:
    """按学科返回六维维度名（语文/数学/英语精确匹配，其余归入科学）。"""
    if "语文" in subject:
        return _SUBJECT_DIMENSIONS["语文"]
    if "数学" in subject:
        return _SUBJECT_DIMENSIONS["数学"]
    if "英语" in subject:
        return _SUBJECT_DIMENSIONS["英语"]
    return _SUBJECT_DIMENSIONS["科学"]


def _subject_key(subject: str) -> str:
    if "语文" in subject:
        return "语文"
    if "数学" in subject:
        return "数学"
    if "英语" in subject:
        return "英语"
    return "科学"


def _clip_score(value: float) -> int:
    """成绩/掌握度收敛到 0-100 的整数。"""
    return int(max(0, min(100, round(value))))


def _derive_ai_diagnosis(db: Session, class_id: str, student_name: str, subject: str) -> List[Dict]:
    """无落盘 AI 诊断文件时，从数据库聚合推导学生六维能力。

    算法：
      1. student 各维 = 该生历次成绩均值 base + 确定性抖动(±3~8) - 错题命中维度扣分(5~10)；
      2. class 各维优先取 class_analysis_reports.capability_dimensions.dims 的 classAvg，
         缺失回退该班该科历次 class_avg 均值，再缺回退 75；
      3. subDims = 错题标题按维度关键词分组，每组最多 2 条，mastery 按该维 student 分数折减；
      4. 确定性：稳定随机实例 random.Random(f"{class_id}_{student_name}_{subject}")，
         同一 (class_id, student_name, subject) 两次调用结果完全一致。
    返回 shape 与 POST /ai-diagnosis 真实产物一致；无任何成绩数据时返回 []（诚实）。
    """
    dims_template = _subject_dimensions(subject)
    dim_keywords = _DIM_KEYWORDS.get(_subject_key(subject), {})

    score_rows = (
        db.query(StudentScoreHistory.score, StudentScoreHistory.class_avg)
        .filter(
            StudentScoreHistory.class_id == class_id,
            StudentScoreHistory.student_name == student_name,
            StudentScoreHistory.subject == subject,
        )
        .all()
    )
    if not score_rows:
        return []

    avg_score = sum(float(r.score) for r in score_rows) / len(score_rows)
    class_avgs = [float(r.class_avg) for r in score_rows if r.class_avg is not None]
    avg_class_avg = (sum(class_avgs) / len(class_avgs)) if class_avgs else None

    wrong_titles = [
        r.question_title or ""
        for r in db.query(StudentWrongQuestion.question_title)
        .filter(
            StudentWrongQuestion.class_id == class_id,
            StudentWrongQuestion.student_name == student_name,
            StudentWrongQuestion.subject == subject,
        )
        .all()
    ]

    # 班级六维 classAvg（B5/B6 seed 注入的 capability_dimensions.dims），按维度名对齐
    class_avg_by_dim: Dict[str, float] = {}
    report = (
        db.query(ClassAnalysisReport.analysis_json)
        .filter(
            ClassAnalysisReport.class_id == class_id,
            ClassAnalysisReport.subject == subject,
        )
        .first()
    )
    if report and report.analysis_json:
        try:
            analysis = report.analysis_json
            if isinstance(analysis, str):
                analysis = json.loads(analysis)
            dims = ((analysis or {}).get("capability_dimensions") or {}).get("dims") or []
            for d in dims:
                if isinstance(d, dict) and d.get("name") and d.get("classAvg") is not None:
                    class_avg_by_dim[d["name"]] = float(d["classAvg"])
        except Exception:
            class_avg_by_dim = {}

    rng = random.Random(f"{class_id}_{student_name}_{subject}")
    fallback_class = avg_class_avg if avg_class_avg is not None else 75.0

    result: List[Dict] = []
    for dim in dims_template:
        # student：base + 确定性抖动(±3~8)，命中错题维度再扣 5~10
        jitter = rng.choice([-1, 1]) * rng.uniform(3, 8)
        student = avg_score + jitter
        matched = [t for t in wrong_titles if any(k in t for k in dim_keywords.get(dim, []))]
        if matched:
            student -= rng.uniform(5, 10)
        student_val = _clip_score(student)

        # class：班级报告 classAvg 优先，缺失回退 avg_class_avg / 75
        class_val = _clip_score(class_avg_by_dim.get(dim, fallback_class))

        # subDims：命中维度关键词的错题标题，取 1-2 条，mastery 按该维成绩折减
        sub_dims: List[Dict] = []
        for title in matched[:2]:
            mastery = max(40, min(88, round(student_val - rng.uniform(5, 20))))
            sub_dims.append({"name": (title or "")[:30], "mastery": int(mastery)})

        result.append({"dim": dim, "student": student_val, "class": class_val, "subDims": sub_dims})

    return result


@router.get("/ai-diagnosis", response_model=ApiResponse[list])
def get_ai_diagnosis(
    class_id: str = Query(...),
    student_name: str = Query(...),
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    f = _get_diagnosis_file(class_id, student_name, subject)
    if f.exists():
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
            # E05 · AI 诊断落盘带 meta(is_ai/generator)：读回时解包，对外响应保持原数组形状
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
            return ApiResponse(data=data)
        except Exception:
            # 落盘文件存在但解析失败：保持原行为，返回空数组
            return ApiResponse(data=[])
    # 无落盘文件：从数据库聚合推导（演示环境无 AI key 也能出数据）
    return ApiResponse(data=_derive_ai_diagnosis(db, class_id, student_name, subject))

@router.post("/ai-diagnosis", response_model=ApiResponse[list])
def run_ai_diagnosis(
    body: AIDiagnosisRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    # E08 · 学校级 AI 管控：AI 诊断开关关闭时一律 403；学生姓名命中身份证/手机号等敏感输入拒答
    require_ai_access(db, user_id, "ai_diagnosis")
    if assert_no_sensitive_input(body.student_name):
        raise HTTPException(status_code=403, detail="输入包含身份证号/手机号等敏感个人信息，请移除后重试")
    _assert_class_access(db, user_id, body.class_id)
    prefix = _class_folder_prefix(body.class_id)
    if not prefix:
        raise HTTPException(status_code=400, detail="班级ID无效")
    
    # 找最近的文件夹
    folders = []
    history_dir = grading_history_dir()
    if history_dir.exists():
        for f in history_dir.iterdir():
            if f.is_file() and f.name.startswith(prefix) and f.name.endswith(".json"):
                if "__manual" not in f.name and "__essay" not in f.name:
                    folders.append(f.stem)
                    
    folders.sort(reverse=True)
    
    wrong_questions = []
    folders_checked = 0
    
    for safe in folders:
        if folders_checked >= 3:
            break
            
        has_student = False
        
        # 1. 查智能批改
        history = _read_grading_history(safe, "default")
        completed = history.get("completed", {})
        for filename, info in completed.items():
            if _paper_box_stem(filename) == body.student_name:
                has_student = True
                counts, blocks = _parse_ai_result_to_counts(info.get("result", ""))
                for b in blocks:
                    if b.get("status") in ["wrong", "blank"]:
                        wrong_questions.append(b.get("title", ""))
                    for sub in b.get("subItems", []):
                        if sub.get("status") in ["wrong", "blank"]:
                            wrong_questions.append(f"{b.get('title', '')}-{sub.get('title', '')}")
                            
        # 2. 查答题卡（自主阅卷）
        manual_history = _read_grading_history(safe, "manual")
        manual_completed = manual_history.get("completed", {})
        for filename, info in manual_completed.items():
            if _paper_box_stem(filename) == body.student_name:
                has_student = True
                try:
                    parsed = json.loads(info.get("result", "{}"))
                    scores = parsed.get("scores", {})
                    for title, score in scores.items():
                        if score == 0:
                            wrong_questions.append(title)
                except Exception:
                    pass
                    
        if has_student:
            folders_checked += 1
            
    if not wrong_questions:
        raise HTTPException(status_code=400, detail="未找到该学生的错题数据，请先进行批改")
        
    wrong_questions = list(set(wrong_questions))
    wrong_questions_text = "\n".join(f"- {q}" for q in wrong_questions)
    
    if "语文" in body.subject:
        dimensions_text = "作文结构, 阅读理解, 基础知识, 古诗文, 语言表达, 创新思维"
    elif "数学" in body.subject:
        dimensions_text = "计算能力, 逻辑推理, 空间想象, 数据分析, 建模应用, 创新思维"
    elif "英语" in body.subject:
        dimensions_text = "听力理解, 口语表达, 阅读理解, 写作能力, 词汇语法, 翻译能力"
    else:
        dimensions_text = "基础掌握, 应用能力, 综合分析, 创新思维, 逻辑推理, 知识广度"

    # PII 匿名化：发千问前把学生姓名匿名，AI 返回里若嵌有匿名名再 restore 回真名。
    anon = Anonymizer()
    anon_student_name = anon.anon(body.student_name)

    prompt = f'''你是一位资深教师，你需要根据学生最近的错题进行深度能力诊断。
学生姓名：{anon_student_name}
学科：{body.subject}

最近错题涉及的知识点/题号：
{wrong_questions_text}

你需要对学生的各项能力进行评估，并返回 JSON 格式数据。
该学科的评估维度包括：
{dimensions_text}

请分析错题，估算学生在各个维度的掌握度（百分制），并与班级平均（假设为75左右）进行对比。
请严格返回以下格式的 JSON 数组（必须是合法的 JSON 数组，不要带 markdown 标记，不要任何其他废话）：
[
  {{
    "dim": "维度1",
    "student": 85,
    "class": 75,
    "subDims": [
       {{ "name": "子维度1", "mastery": 70 }}
    ]
  }}
]
'''
    payload = {
        "model": "qwen-max-latest",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }

    try:
        base_url, api_key, qwen_model = get_llm_config(db)
        if not api_key:
            raise HTTPException(status_code=500, detail="系统设置中未配置文本大模型 API Key，无法生成 AI 诊断")

        if "vl" in qwen_model.lower():
            qwen_model = "qwen-plus"

        url = f"{base_url}/chat/completions"
        payload["model"] = qwen_model
        payload["messages"] = [{"role": "user", "content": prompt}]
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        import requests
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        res_json = response.json()
        
        if response.status_code != 200 or "error" in res_json:
            error_msg = res_json.get("error", {}).get("message", str(res_json))
            raise HTTPException(status_code=500, detail=f"AI生成错误: {error_msg}")
        
        result_str = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        
        if result_str.startswith("```json"):
            result_str = result_str[7:]
        if result_str.startswith("```"):
            result_str = result_str[3:]
        if result_str.endswith("```"):
            result_str = result_str[:-3]
        result_str = result_str.strip()
        
        data = anon.restore_deep(json.loads(result_str))
        # AI 输出红线词过滤：解析后深滤所有文本值（best-effort，异常不阻断诊断主流程；
        # 不能对整个 JSON 字符串 filter_text，删除类命中会破坏 JSON 语法导致解析崩溃）
        try:
            data = _filter_redline_deep(data)
        except Exception:  # noqa: BLE001 - best-effort，红线过滤失败放行原文
            pass

        f = _get_diagnosis_file(body.class_id, body.student_name, body.subject)
        # E05 · AI 内容统一标识（GB 45438 隐式标识）：落盘 JSON 带 meta(is_ai/generator/model)
        with open(f, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "meta": {"is_ai": True, "generator": AI_GENERATOR, "model": qwen_model},
                    "data": data,
                },
                file,
                ensure_ascii=False,
                indent=2,
            )

        return ApiResponse(data=data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI分析失败: {str(e)}")


@router.get("/ct-image")
def get_ct_image(
    path: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Serve CT images dynamically to bypass Nginx static regex matching (.jpg)"""
    if ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path")

    # path 格式：ct/cls_{class_id}/assets/{exam_name}/{student_name}/...（兼容无 ct/ 前缀）
    # 还原 class_id 并在服务图片前做班级归属校验，防止 IDOR 越权读取任意班级图片。
    class_id = None
    for part in path.split("/"):
        if part.startswith("cls_"):
            class_id = part.removeprefix("cls_")
            break
    if not class_id:
        raise HTTPException(status_code=400, detail="Invalid path")
    _assert_class_access(db, user_id, class_id)

    resolved = resolve_ct_image_path(path)
    if resolved and resolved.is_file():
        return FileResponse(str(resolved))
    raise HTTPException(status_code=404, detail="Image not found")


def _db_wrong_question_image_url(value: Optional[str]) -> Optional[str]:
    """DB 错题图 URL 兜底：None/空透出 None；相对路径走 ct 直链转换；已是完整 URL 时原样返回。"""
    if not value:
        return None
    converted = ct_image_api_url_for_rel(value)
    return converted if converted else value


@router.get("/wrong-questions/latest", response_model=ApiResponse[WrongQuestionResponse])
def get_latest_wrong_questions(
    class_id: str = Query(...),
    student_name: str = Query(...),
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    # Query from the new StudentWrongQuestion table
    latest_wq = db.query(StudentWrongQuestion).filter(
        StudentWrongQuestion.class_id == class_id,
        StudentWrongQuestion.student_name == student_name,
        StudentWrongQuestion.subject == subject
    ).order_by(StudentWrongQuestion.created_at.desc()).first()
    
    if not latest_wq:
        return ApiResponse(data={"exam_name": "暂无记录", "questions": [], "created_at": None})
        
    exam_name = latest_wq.exam_name

    # ── BE-2 数据源切换：DB 为主，一次 JOIN wrong_question_kp_bridge ──
    # 真实数据在 student_wrong_questions（含 question_title 文本），演示环境无磁盘图片，
    # 文本错题也要展示，不再因缺图跳过整项。
    db_rows = (
        db.query(
            StudentWrongQuestion.question_title,
            StudentWrongQuestion.knowledge_point_id,
            StudentWrongQuestion.image_url,
            StudentWrongQuestion.answer_url,
            WrongQuestionKpBridge.kp_name,
        )
        .outerjoin(WrongQuestionKpBridge, WrongQuestionKpBridge.wrong_question_id == StudentWrongQuestion.id)
        .filter(
            StudentWrongQuestion.class_id == class_id,
            StudentWrongQuestion.student_name == student_name,
            StudentWrongQuestion.subject == subject,
            StudentWrongQuestion.exam_name == exam_name,
        )
        .all()
    )

    questions = []
    for title, kp_id, image_url, answer_url, kp_name in db_rows:
        questions.append({
            "title": title,
            "image_url": _db_wrong_question_image_url(image_url),
            "answer_url": _db_wrong_question_image_url(answer_url),
            "knowledge_point_id": kp_id,
            "knowledge_point_name": kp_name,
        })

    # 仅当 DB 查无该 (class, student, subject, exam) 组合时，才回退磁盘图片扫描（原逻辑保留）
    if not questions:
        # 知识点锚点：该生该科该场次错题 → knowledge_point_id 映射（P3-B3 列已加；回填前多为 NULL）
        kp_by_title: Dict[str, Optional[str]] = {}
        for wq in db.query(StudentWrongQuestion).filter(
            StudentWrongQuestion.class_id == class_id,
            StudentWrongQuestion.student_name == student_name,
            StudentWrongQuestion.subject == subject,
            StudentWrongQuestion.exam_name == exam_name,
        ).all():
            kp_by_title.setdefault(wq.question_title, wq.knowledge_point_id)

        # 1. Try to directly scan the assets directory
        ct_root = _ct_root()
        student_assets_dir = ct_root / f"cls_{class_id}" / "assets" / exam_name / student_name

        if student_assets_dir.is_dir():
            for q_file in student_assets_dir.glob("*_question.jpg"):
                title_base = q_file.name.replace("_question.jpg", "")

                # Find matching answer file if exists
                a_file = student_assets_dir / f"{title_base}_answer.jpg"
                a_rel = None
                if a_file.is_file():
                    try:
                        a_rel = a_file.relative_to(ct_root.parent).as_posix()
                    except ValueError:
                        a_rel = f"ct/cls_{class_id}/assets/{exam_name}/{student_name}/{a_file.name}"

                try:
                    q_rel = q_file.relative_to(ct_root.parent).as_posix()
                except ValueError:
                    q_rel = f"ct/cls_{class_id}/assets/{exam_name}/{student_name}/{q_file.name}"

                image_url = ct_image_api_url_for_rel(q_rel)
                answer_url = ct_image_api_url_for_rel(a_rel)
                if not image_url and not answer_url:
                    continue

                # Extract a readable title (e.g. "q11_s1" from "刘贞妍_1_q11_s1")
                title_parts = title_base.split("_")
                title = title_base
                if len(title_parts) >= 3:
                    title = f"第{title_parts[-2].replace('q', '')}题-区{title_parts[-1].replace('s', '')}"

                questions.append({
                    "title": title,
                    "image_url": image_url,
                    "answer_url": answer_url,
                    "knowledge_point_id": kp_by_title.get(title),
                })

        # 2. If scanning directory didn't yield results, fallback to analysis.json
        if not questions:
            folder_safe = f"cls_{class_id}__{exam_name}"
            analysis_path = _analysis_json_path(folder_safe, create_class_dir=False)
            if analysis_path and analysis_path.is_file():
                analysis_data = _read_json(analysis_path)
                papers = analysis_data.get("papers", {})
                student_paper = papers.get(student_name)
                if student_paper:
                    wq_list = student_paper.get("wrong_question_analysis", [])
                    for wq in wq_list:
                        title = wq.get("display_title", wq.get("question_key", ""))
                        assets = wq.get("assets", {})
                        q_img = assets.get("question_image", {})
                        a_img = assets.get("answer_image", {})

                        q_rel = q_img.get("relative_to_grading_data") if isinstance(q_img, dict) else None
                        a_rel = a_img.get("relative_to_grading_data") if isinstance(a_img, dict) else None
                        image_url = ct_image_api_url_for_rel(q_rel)
                        answer_url = ct_image_api_url_for_rel(a_rel)
                        if not image_url and not answer_url:
                            continue

                        questions.append({
                            "title": title,
                            "image_url": image_url,
                            "answer_url": answer_url,
                            "knowledge_point_id": kp_by_title.get(title),
                        })

        # 3. If STILL no questions, fallback to DB only
        if not questions:
            # Get all wrong questions for this specific exam
            all_wq = db.query(StudentWrongQuestion).filter(
                StudentWrongQuestion.class_id == class_id,
                StudentWrongQuestion.student_name == student_name,
                StudentWrongQuestion.subject == subject,
                StudentWrongQuestion.exam_name == exam_name
            ).all()

            questions = [{
                "title": wq.question_title,
                "image_url": None,
                "answer_url": None,
                "knowledge_point_id": wq.knowledge_point_id,
            } for wq in all_wq]

    return ApiResponse(data={
        "exam_name": exam_name,
        "questions": questions,
        "created_at": latest_wq.created_at
    })


# ──────────────────────────────────────────────
# 错题遗忘曲线复习（简易 SM-2）+ 举一反三变式题推荐
# ──────────────────────────────────────────────
# 间隔序列：1/2/4/7/15/30/60... 天；review_count 表示当前在序列中的位置。
_REVIEW_INTERVAL_SEQUENCE = [1, 2, 4, 7, 15, 30, 60]


class WrongQuestionReviewResultRequest(BaseModel):
    """复习打卡结果：again=没记住(重置为1天)，good=记住(推进1步)，easy=很轻松(跳2步)。"""
    result: Literal["again", "good", "easy"]


def _review_to_dict(r: WrongQuestionReview) -> Dict:
    def _iso(v):
        return v.isoformat() if v is not None else None
    return {
        "id": r.id,
        "class_id": r.class_id,
        "student_id": r.student_id,
        "student_name": r.student_name,
        "subject": r.subject,
        "question_ref": r.question_ref,
        "question_title": r.question_title,
        "image_url": r.image_url,
        "error_type": r.error_type,
        "review_count": r.review_count,
        "last_reviewed_at": _iso(r.last_reviewed_at),
        "next_review_at": _iso(r.next_review_at),
        "interval_days": r.interval_days,
        "created_at": _iso(r.created_at),
    }


def _advance_review(record: WrongQuestionReview, result: str) -> None:
    """按简易 SM-2 推进间隔。again 重置，good 前进 1 步，easy 前进 2 步。"""
    if result == "again":
        position = 0
    elif result == "easy":
        position = record.review_count + 2
    else:  # good
        position = record.review_count + 1
    interval = _REVIEW_INTERVAL_SEQUENCE[min(position, len(_REVIEW_INTERVAL_SEQUENCE) - 1)]
    now = datetime.now()
    record.review_count = position
    record.interval_days = interval
    record.last_reviewed_at = now
    record.next_review_at = now + timedelta(days=interval)


def _ensure_review_seed(db: Session, class_id: str, subject: Optional[str]) -> None:
    """懒初始化：从 StudentWrongQuestion 为该班级（科目）补齐复习记录，幂等。

    仅当该班级（科目）还没有任何复习记录时执行一次，避免重复建行。
    """
    exists_q = db.query(WrongQuestionReview.id).filter(
        WrongQuestionReview.class_id == class_id
    )
    if subject:
        exists_q = exists_q.filter(WrongQuestionReview.subject == subject)
    if exists_q.first():
        return

    wq_q = db.query(StudentWrongQuestion).filter(
        StudentWrongQuestion.class_id == class_id
    ).order_by(StudentWrongQuestion.created_at.desc())
    if subject:
        wq_q = wq_q.filter(StudentWrongQuestion.subject == subject)
    wrong_questions = wq_q.limit(30).all()
    if not wrong_questions:
        return

    # 一次性把该班学生 姓名 -> id 映射读出来，用于回填 student_id
    name_to_id = {
        s.name: s.id
        for s in db.query(Student).filter(Student.class_id == class_id).all()
    }

    now = datetime.now()
    for wq in wrong_questions:
        db.add(WrongQuestionReview(
            class_id=class_id,
            student_id=name_to_id.get(wq.student_name),
            student_name=wq.student_name,
            subject=wq.subject,
            question_ref=wq.id,
            question_title=wq.question_title,
            image_url=wq.image_url,
            error_type="other",
            review_count=0,
            last_reviewed_at=None,
            next_review_at=now,
            interval_days=1,
        ))
    db.commit()


@router.get("/wrong-questions/due")
def get_wrong_questions_due(
    class_id: str = Query(...),
    subject: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """到期复习列表：next_review_at <= 今天（含逾期）。subject 缺省时返回全班各科目。"""
    _assert_class_access(db, user_id, class_id)
    _ensure_review_seed(db, class_id, subject)
    end_of_today = datetime.now().replace(hour=23, minute=59, second=59)
    q = db.query(WrongQuestionReview).filter(
        WrongQuestionReview.class_id == class_id,
        WrongQuestionReview.next_review_at <= end_of_today,
    )
    if subject:
        q = q.filter(WrongQuestionReview.subject == subject)
    records = q.order_by(WrongQuestionReview.next_review_at.asc()).limit(50).all()
    return ApiResponse(data=[_review_to_dict(r) for r in records])


@router.post("/wrong-questions/{id}/review")
def review_wrong_question(
    id: str,
    body: WrongQuestionReviewResultRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """复习打卡：按 result(again/good/easy) 推进下次复习时间。"""
    record = db.query(WrongQuestionReview).filter(WrongQuestionReview.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="复习记录不存在")
    _assert_class_access(db, user_id, record.class_id)
    _advance_review(record, body.result)
    db.commit()
    db.refresh(record)
    return ApiResponse(data=_review_to_dict(record))


@router.get("/wrong-questions/{id}/variants")
def get_wrong_question_variants(
    id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """变式题推荐：同 subject + 同 error_type 的历史错题，取前 5 条；无则空数组。"""
    record = db.query(WrongQuestionReview).filter(WrongQuestionReview.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="复习记录不存在")
    _assert_class_access(db, user_id, record.class_id)
    variants = db.query(WrongQuestionReview).filter(
        WrongQuestionReview.class_id == record.class_id,
        WrongQuestionReview.subject == record.subject,
        WrongQuestionReview.error_type == record.error_type,
        WrongQuestionReview.id != record.id,
    ).order_by(WrongQuestionReview.created_at.desc()).limit(5).all()
    reason = f"与你错题同「{record.subject}」科目的同类错题，用于举一反三巩固"
    return ApiResponse(data=[{**_review_to_dict(v), "reason": reason} for v in variants])
