from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import statistics
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import bind_grading_user_context, get_current_user_id
from app.grading.user_paths import correct_docs_dir, correct_docs_img_dir, grading_paths
from app.utils.class_access import can_view_class
from app.models.class_model import Class
from app.models.class_analysis import ClassAnalysisReport
from app.models.school import School
from app.models.student import Student
from app.models.student_analysis import StudentScoreHistory, StudentWrongQuestion
from app.models.wrong_question_kp_bridge import WrongQuestionKpBridge
from app.routers.targeted_improvement import (
    SUBJECTS,
    _class_folder_prefix,
    _collect_exam_data,
    _display_folder_name,
    _exam_mtime,
    _filter_redline_deep,
    _folder_completion_count,
    _student_sort_key,
)
from app.schemas.common import ApiResponse
from app.services.ai_policy import require_ai_access
from app.services.assessment import access as access_svc
from app.services.grade_scores import ensure_ranking_grade, filter_rankings_for_parent, grade_for_score
from app.utils.anonymize import Anonymizer
from app.utils.qwen_settings import AI_GENERATOR, QWEN_CHAT_EXTRA_BODY, get_qwen_config


router = APIRouter(
    prefix="/class-analysis",
    tags=["class_analysis"],
    dependencies=[Depends(bind_grading_user_context)],
)


def _assert_class_access(db: Session, user_id: str, class_id: str) -> None:
    """校验调用者对目标班级有访问权限（教师=所带班级，班主任/副班主任=本班，系统管理员/校级管理者/年级组长=全校），否则 403。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级访问权限")


CLASS_ANALYSIS_IMAGE_BATCH_SIZE = max(1, min(10, int(os.environ.get("CLASS_ANALYSIS_IMAGE_BATCH_SIZE", "6"))))
CLASS_ANALYSIS_IMAGE_WORKERS = max(1, min(5, int(os.environ.get("CLASS_ANALYSIS_IMAGE_WORKERS", "3"))))
CLASS_ANALYSIS_MAX_IMAGES = max(20, min(300, int(os.environ.get("CLASS_ANALYSIS_MAX_IMAGES", "160"))))
_report_lock = threading.RLock()


class GenerateClassAnalysisRequest(BaseModel):
    class_id: str
    subject: str
    exam_folder_names: list[str]


def _safe_stem(value: Any, fallback: str = "item") -> str:
    token = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", str(value or "").strip())
    token = token.strip(" .")
    return (token[:120] or fallback)


def _report_path(class_id: str, subject: str) -> Path:
    root = grading_paths().ct / f"cls_{_safe_stem(class_id, 'unknown')}" / "class_analysis"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{_safe_stem(subject, 'subject')}.json"


def _read_file_report(class_id: str, subject: str) -> Optional[dict]:
    path = _report_path(class_id, subject)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_file_report(class_id: str, subject: str, data: dict) -> None:
    path = _report_path(class_id, subject)
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    with _report_lock:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def _json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _json_value(text: Optional[str], fallback: Any) -> Any:
    if not text:
        return fallback
    try:
        value = json.loads(text)
        return value
    except Exception:
        return fallback


def _db_report_to_dict(row: Optional[ClassAnalysisReport]) -> Optional[dict]:
    if not row:
        return None
    report = {
        "id": row.report_uuid or row.id,
        "class_id": row.class_id,
        "class_name": row.class_name,
        "subject": row.subject,
        "exam_names": _json_value(row.exam_names_json, []),
        "imported_folder_names": _json_value(row.imported_folder_names_json, []),
        "source_summary": _json_value(row.source_summary_json, {}),
        "analysis": _json_value(row.analysis_json, {}),
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        # E05 · AI 内容统一标识（GB 45438 隐式标识）读回
        "is_ai": bool(row.is_ai),
        "ai_meta": row.ai_meta,
    }
    # E04 兼容历史报告：grade 字段缺失时按 score 派生，保证旧报告 rankings 也带等级。
    _ensure_report_grades(report)
    return report


def _ensure_report_grades(report: dict) -> None:
    """就地给 report.source_summary.exam_summaries[].rankings[] 补 grade（旧数据派生，不落库）。"""
    for summary in (report.get("source_summary") or {}).get("exam_summaries") or []:
        if isinstance(summary, dict):
            ensure_ranking_grade(summary.get("rankings") or [])


def _upsert_db_report(
    db: Session,
    *,
    class_id: str,
    class_name: str,
    subject: str,
    report: dict,
    model: Optional[str] = None,
) -> ClassAnalysisReport:
    row = db.query(ClassAnalysisReport).filter(
        ClassAnalysisReport.class_id == class_id,
        ClassAnalysisReport.subject == subject,
    ).first()
    if not row:
        row = ClassAnalysisReport(class_id=class_id, class_name=class_name, subject=subject)
        db.add(row)
    row.report_uuid = str(report.get("id") or uuid.uuid4().hex)
    row.class_name = class_name
    row.exam_names_json = _json_text(report.get("exam_names") or [])
    row.imported_folder_names_json = _json_text(report.get("imported_folder_names") or [])
    row.source_summary_json = _json_text(report.get("source_summary") or {})
    row.analysis_json = _json_text(report.get("analysis") or {})
    # E05 · AI 内容统一标识（GB 45438 隐式标识）：本表由 AI 生成，落库显式写 is_ai=1 + ai_meta
    row.is_ai = 1
    row.ai_meta = {"generator": AI_GENERATOR, "model": model}
    row.generated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def _status_code(item: dict) -> int:
    try:
        return int(item.get("status_code"))
    except Exception:
        status = str(item.get("status") or "").strip().lower()
        if status in ("正确", "对", "correct", "right"):
            return 1
        if status in ("未作答", "blank", "unanswered"):
            return 3
        if status:
            return 2
        return -1


def _round_number(value: Any, digits: int = 1) -> Optional[float]:
    try:
        return round(float(value), digits)
    except Exception:
        return None


def _compact_record(item: Any) -> dict:
    if not isinstance(item, dict):
        return {}
    return {
        "question_key": item.get("question_key"),
        "display_title": item.get("display_title"),
        "status_code": item.get("status_code"),
        "status": item.get("status"),
        "question_type": item.get("question_type"),
        "question": item.get("question"),
        "student_answer": item.get("student_answer"),
        "reason": str(item.get("reason") or item.get("comment") or "")[:700],
    }


def _compact_wrong_analysis(item: Any) -> dict:
    if not isinstance(item, dict):
        return {}
    analysis = item.get("analysis")
    if isinstance(analysis, dict):
        analysis_value: Any = {
            "question_text": analysis.get("question_text"),
            "student_answer": analysis.get("student_answer"),
            "knowledge_points": analysis.get("knowledge_points") or [],
            "error_type": analysis.get("error_type"),
            "error_reason": analysis.get("error_reason"),
            "explanation": analysis.get("explanation"),
            "suggestion": analysis.get("suggestion"),
            "confidence": analysis.get("confidence"),
        }
    else:
        analysis_value = str(analysis or "")[:1000]
    return {
        "question_key": item.get("question_key"),
        "display_title": item.get("display_title"),
        "status_code": item.get("status_code"),
        "status": item.get("status"),
        "reason": str(item.get("reason") or item.get("baidu_reason") or "")[:700],
        "analysis": analysis_value,
    }


def _student_exam_counts(exam: dict) -> dict:
    records = [x for x in (exam.get("paper_records") or []) if isinstance(x, dict)]
    correct = sum(1 for x in records if _status_code(x) == 1)
    wrong = sum(1 for x in records if _status_code(x) == 2)
    blank = sum(1 for x in records if _status_code(x) == 3)
    return {
        "answer_area_count": len(records),
        "correct_count": correct,
        "wrong_count": wrong,
        "blank_count": blank,
    }


def _rank_scores(score_map: dict[str, float], students_by_name: dict[str, Student]) -> list[dict]:
    ordered = sorted(score_map.items(), key=lambda item: (-item[1], _student_sort_key(students_by_name[item[0]])))
    rows: list[dict] = []
    previous_score: Optional[float] = None
    previous_rank = 0
    for index, (student_name, score) in enumerate(ordered, start=1):
        rank = previous_rank if previous_score == score else index
        previous_score = score
        previous_rank = rank
        student = students_by_name[student_name]
        rows.append({
            "student_id": student.id,
            "student_name": student.name,
            "student_number": student.student_number or "",
            "score": _round_number(score),
            # E04 成绩等级制：等级呈现（rank 保留给教师/管理员视图，家长视图会裁剪）
            "grade": grade_for_score(score),
            "rank": rank,
        })
    return rows


def _score_history_map(
    db: Session,
    class_id: str,
    subject: str,
    exam_names: list[str],
    students_by_name: dict[str, Student],
) -> dict[str, dict[str, float]]:
    if not exam_names:
        return {}
    rows = (
        db.query(StudentScoreHistory)
        .filter(
            StudentScoreHistory.class_id == class_id,
            StudentScoreHistory.subject == subject,
            StudentScoreHistory.exam_name.in_(exam_names),
        )
        .order_by(StudentScoreHistory.created_at.asc())
        .all()
    )
    result: dict[str, dict[str, float]] = {}
    for row in rows:
        if row.student_name not in students_by_name:
            continue
        result.setdefault(row.exam_name, {})[row.student_name] = float(row.score)
    return result


def _percentile(values: list[int], proportion: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * proportion) - 1))
    return int(ordered[index])


def _build_warning_candidates(student_rows: dict[str, list[dict]]) -> list[dict]:
    candidates: dict[str, dict] = {}
    for exam_name, rows in student_rows.items():
        wrong_values = [int(row.get("wrong_count") or 0) + int(row.get("blank_count") or 0) for row in rows]
        if not wrong_values:
            continue
        mean = statistics.fmean(wrong_values)
        deviation = statistics.pstdev(wrong_values) if len(wrong_values) > 1 else 0
        threshold = max(2, _percentile(wrong_values, 0.75), math.ceil(mean + deviation * 0.5))
        for row in rows:
            wrong_count = int(row.get("wrong_count") or 0) + int(row.get("blank_count") or 0)
            if wrong_count < threshold or wrong_count <= mean:
                continue
            name = str(row.get("student_name") or "")
            item = candidates.setdefault(name, {
                "student_id": row.get("student_id"),
                "student_name": name,
                "student_number": row.get("student_number") or "",
                "warning_exams": [],
                "total_wrong_count": 0,
            })
            item["warning_exams"].append({
                "exam_name": exam_name,
                "wrong_count": wrong_count,
                "class_average_wrong_count": round(mean, 1),
                "warning_threshold": threshold,
                "score": row.get("score"),
                "rank": row.get("rank"),
                "top_wrong_titles": (row.get("wrong_titles") or [])[:6],
            })
            item["total_wrong_count"] += wrong_count
    output = list(candidates.values())
    for item in output:
        exam_hits = len(item.get("warning_exams") or [])
        item["risk_level"] = "high" if exam_hits >= 2 else "medium"
    output.sort(key=lambda item: (-len(item.get("warning_exams") or []), -int(item.get("total_wrong_count") or 0), item.get("student_number") or item.get("student_name")))
    return output[:20]


def _resolve_full_image_paths(folder_name: str, filename: str) -> list[Path]:
    name = Path(str(filename or "")).name
    if not name:
        return []
    ext = Path(name).suffix.lower()
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    if ext in image_extensions:
        source = correct_docs_dir() / folder_name / name
        if source.is_file():
            return [source]
        preview = correct_docs_img_dir() / folder_name / name
        return [preview] if preview.is_file() else []
    if ext == ".pdf":
        pdf_path = correct_docs_dir() / folder_name / name
        if not pdf_path.is_file():
            return []
        preview_dir = correct_docs_img_dir() / folder_name
        preview_dir.mkdir(parents=True, exist_ok=True)
        pattern = f"{Path(name).stem}__class_analysis_page_*.jpg"
        cached = sorted(preview_dir.glob(pattern), key=lambda path: path.name)
        try:
            source_mtime = pdf_path.stat().st_mtime
            if cached and all(path.stat().st_mtime >= source_mtime for path in cached):
                return cached
        except OSError:
            pass
        try:
            from app.grading.doc_convert import pdf_to_images

            images = pdf_to_images(str(pdf_path), dpi=150)
            output: list[Path] = []
            for page_index, image in enumerate(images, start=1):
                page_path = preview_dir / f"{Path(name).stem}__class_analysis_page_{page_index:04d}.jpg"
                image.convert("RGB").save(page_path, quality=88)
                output.append(page_path)
            for stale_path in cached:
                if stale_path not in output:
                    try:
                        stale_path.unlink()
                    except OSError:
                        pass
            return output
        except Exception:
            return []
    return []


def _image_to_data_url(path: Path) -> str:
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError(f"缺少 Pillow，无法读取完整试卷图片: {exc}") from exc
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((1800, 1800))
        stream = io.BytesIO()
        image.save(stream, format="JPEG", quality=82, optimize=True)
    encoded = base64.b64encode(stream.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _parse_ai_json(text: str) -> dict:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
    if fenced:
        raw = fenced.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError(f"千问未返回JSON对象: {raw[:240]}")
    try:
        data = json.loads(raw[start : end + 1])
    except Exception as exc:
        raise RuntimeError(f"千问返回JSON解析失败: {exc}; 原文: {raw[:300]}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("千问返回结果不是JSON对象")
    return data


def _qwen_completion(api_key: str, model: str, content: Any, *, timeout: int = 180) -> dict:
    if not api_key:
        raise RuntimeError("系统设置中未配置千问 API Key，无法生成班级分析")
    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError(f"缺少 openai 依赖，无法调用千问: {exc}") from exc
    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=timeout,
        )
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            temperature=0.1,
            stream=False,
            extra_body=QWEN_CHAT_EXTRA_BODY,
        )
        text = (completion.choices[0].message.content or "").strip()
        return _parse_ai_json(text)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"调用千问模型失败: {exc}") from exc


def _vision_batch_prompt(batch_id: str, papers: list[dict]) -> str:
    payload = {
        "batch_id": batch_id,
        "papers": [
            {
                "paper_ref": paper["paper_ref"],
                "exam_name": paper["exam_name"],
                "student": paper["student"],
                "score_and_rank": paper["score_and_rank"],
                "image_refs": paper["image_refs"],
                "exam_record_json": paper["exam_record_json"],
                "wrong_question_json": paper["wrong_question_json"],
            }
            for paper in papers
        ],
    }
    return f"""你是一名负责班级学情分析的资深教师。消息中包含若干学生完整试卷图片，每组图片前都有paper_ref和image_ref标签。下面JSON中的paper_ref、image_refs与图片标签一一对应，严禁把不同学生或不同考试的图片和JSON混用。

请结合完整试卷图片、考试答题记录JSON、错题分析JSON、成绩和排名，提取本批次中可供班级汇总使用的证据。图片只用于理解题目、作答和错因，不要重新批改已经有明确status_code的题目。

只返回以下JSON，不要Markdown，不要额外字段：
{{
  "batch_id": "{batch_id}",
  "knowledge_evidence": [
    {{"exam_name":"","knowledge_point":"","student_names":[],"question_refs":[],"severity":"high/medium/low","evidence":""}}
  ],
  "student_evidence": [
    {{"student_name":"","exam_name":"","paper_ref":"","observations":[],"evidence_question_refs":[]}}
  ],
  "class_patterns": [
    {{"exam_name":"","pattern":"","student_names":[],"evidence":""}}
  ],
  "data_notes": []
}}

约束：
1. 只能使用输入图片和JSON中的证据，不得虚构题目、学生、分数、知识点表现或人数。
2. student_names必须来自输入JSON，question_refs优先使用question_key。
3. 图片看不清或JSON缺失时写入data_notes，不要猜测。
4. 每个数组最多12项，文字简洁。

对应数据：
{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"""


def _run_vision_batch(api_key: str, model: str, batch_id: str, papers: list[dict]) -> tuple[str, dict]:
    content: list[dict] = []
    for paper in papers:
        for image_ref, image_path in zip(paper["image_refs"], paper["image_paths"]):
            content.append({
                "type": "text",
                "text": f"图片标签：paper_ref={paper['paper_ref']}，image_ref={image_ref}，考试={paper['exam_name']}，学生={paper['student']['name']}",
            })
            content.append({"type": "image_url", "image_url": {"url": _image_to_data_url(image_path)}})
    content.append({"type": "text", "text": _vision_batch_prompt(batch_id, papers)})
    result = _qwen_completion(api_key, model, content, timeout=240)
    returned_id = str(result.get("batch_id") or "")
    if returned_id and returned_id != batch_id:
        raise RuntimeError(f"千问返回批次号不一致: expected={batch_id}, got={returned_id}")
    return batch_id, result


def _build_final_prompt(subject: str, deterministic: dict, vision_results: list[dict]) -> str:
    schema = {
        "overall_level": {
            "level": "优秀/良好/中等/需提升/数据不足",
            "summary": "",
            "trend": "",
            "score_interpretation": "",
            "strengths": [],
            "data_notes": [],
        },
        "knowledge_heatmap": [
            {
                "knowledge_point": "",
                "values": [{"exam_name": "", "risk_score": 0, "evidence_count": 0}],
                "summary": "",
            }
        ],
        "weak_points": [
            {
                "knowledge_point": "",
                "severity": "high/medium/low",
                "affected_student_count": 0,
                "affected_students": [],
                "evidence_exam_names": [],
                "evidence": "",
                "teaching_suggestion": "",
            }
        ],
        "student_warnings": [
            {
                "student_name": "",
                "risk_level": "high/medium",
                "reason": "",
                "suggestion": "",
            }
        ],
        "teaching_actions": [],
    }
    return f"""你是一名资深{subject}教师，请根据后端已计算的班级统计、成绩排名、逐题错情和完整试卷视觉证据，生成班级多次考试学情分析。

后端统计值是唯一数字事实来源。你只能解释这些数字，不能重新计算、修改或猜测平均分、排名、人数、错题数。考试顺序必须严格使用exam_order。

知识点热力图表示“薄弱风险”，risk_score越高表示越薄弱：0-29低、30-59中、60-79高、80-100严重。只能依据vision_results中的知识点证据生成；证据不足时使用null，不得用0冒充无风险。每个知识点必须为exam_order中的每场考试返回一个values项且顺序一致。

预警学生只能来自warning_candidates。不得增加学生，不得删除候选学生；只补充基于证据的reason和suggestion。不要把相关性写成因果关系。

严格只返回以下JSON结构，不要Markdown，不要额外字段：
{json.dumps(schema, ensure_ascii=False)}

确定性数据：
{json.dumps(deterministic, ensure_ascii=False, separators=(',', ':'))}

完整试卷分批视觉分析证据：
{json.dumps(vision_results, ensure_ascii=False, separators=(',', ':'))}"""


def _as_text_list(value: Any, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        token = str(item or "").strip()
        if token and token not in output:
            output.append(token[:300])
        if len(output) >= limit:
            break
    return output


def _bounded_int(value: Any, minimum: int, maximum: int, default: Optional[int] = 0) -> Optional[int]:
    if value is None:
        return None
    try:
        return max(minimum, min(maximum, int(round(float(value)))))
    except Exception:
        return default


def _normalize_final_analysis(raw: dict, deterministic: dict) -> dict:
    exam_order = [str(x) for x in deterministic.get("exam_order") or []]
    allowed_exams = set(exam_order)
    candidates = deterministic.get("warning_candidates") or []
    allowed_students = {str(x.get("student_name") or "") for x in candidates if isinstance(x, dict)}
    class_students = {
        str(x.get("name") or "")
        for x in deterministic.get("students") or []
        if isinstance(x, dict) and str(x.get("name") or "")
    }

    overall_raw = raw.get("overall_level") if isinstance(raw.get("overall_level"), dict) else {}
    averages = [x.get("average_score") for x in deterministic.get("exam_summaries") or [] if isinstance(x.get("average_score"), (int, float))]
    fallback_summary = "已完成所选考试的班级学情分析。"
    if averages:
        fallback_summary = f"所选考试班级平均分从{averages[0]}变化到{averages[-1]}。"
    overall = {
        "level": str(overall_raw.get("level") or ("数据不足" if not averages else "中等"))[:20],
        "summary": str(overall_raw.get("summary") or fallback_summary)[:1200],
        "trend": str(overall_raw.get("trend") or "")[:600],
        "score_interpretation": str(overall_raw.get("score_interpretation") or "")[:600],
        "strengths": _as_text_list(overall_raw.get("strengths"), 8),
        "data_notes": _as_text_list(overall_raw.get("data_notes"), 8),
    }

    heatmap: list[dict] = []
    for item in raw.get("knowledge_heatmap") or []:
        if not isinstance(item, dict):
            continue
        knowledge_point = str(item.get("knowledge_point") or "").strip()
        if not knowledge_point or any(x.get("knowledge_point") == knowledge_point for x in heatmap):
            continue
        source_values = item.get("values") if isinstance(item.get("values"), list) else []
        by_exam = {
            str(value.get("exam_name") or ""): value
            for value in source_values
            if isinstance(value, dict) and str(value.get("exam_name") or "") in allowed_exams
        }
        values = []
        for exam_name in exam_order:
            value = by_exam.get(exam_name, {})
            values.append({
                "exam_name": exam_name,
                "risk_score": _bounded_int(value.get("risk_score"), 0, 100, None),
                "evidence_count": _bounded_int(value.get("evidence_count"), 0, 9999, 0),
            })
        heatmap.append({
            "knowledge_point": knowledge_point[:100],
            "values": values,
            "summary": str(item.get("summary") or "")[:500],
        })
        if len(heatmap) >= 10:
            break

    weak_points: list[dict] = []
    for item in raw.get("weak_points") or []:
        if not isinstance(item, dict):
            continue
        knowledge_point = str(item.get("knowledge_point") or "").strip()
        if not knowledge_point:
            continue
        students = [x for x in _as_text_list(item.get("affected_students"), 30) if x in class_students]
        exams = [x for x in _as_text_list(item.get("evidence_exam_names"), 12) if x in allowed_exams]
        severity = str(item.get("severity") or "medium").lower()
        if severity not in ("high", "medium", "low"):
            severity = "medium"
        weak_points.append({
            "knowledge_point": knowledge_point[:100],
            "severity": severity,
            "affected_student_count": len(students) if students else _bounded_int(
                item.get("affected_student_count"), 0, len(class_students), 0
            ),
            "affected_students": students,
            "evidence_exam_names": exams,
            "evidence": str(item.get("evidence") or "")[:700],
            "teaching_suggestion": str(item.get("teaching_suggestion") or "")[:700],
        })
        if len(weak_points) >= 8:
            break

    ai_warnings = {
        str(item.get("student_name") or ""): item
        for item in raw.get("student_warnings") or []
        if isinstance(item, dict) and str(item.get("student_name") or "") in allowed_students
    }
    warnings: list[dict] = []
    for candidate in candidates:
        name = str(candidate.get("student_name") or "")
        ai_item = ai_warnings.get(name, {})
        exam_bits = [
            f"{x.get('exam_name')}错题{x.get('wrong_count')}道（班均{x.get('class_average_wrong_count')}道）"
            for x in candidate.get("warning_exams") or []
        ]
        warnings.append({
            **candidate,
            "risk_level": candidate.get("risk_level") or "medium",
            "reason": str(ai_item.get("reason") or "；".join(exam_bits))[:800],
            "suggestion": str(ai_item.get("suggestion") or "优先复盘高频错题，并在下一次练习中跟踪同类题表现。")[:600],
        })

    return {
        "overall_level": overall,
        "knowledge_heatmap": heatmap,
        "weak_points": weak_points,
        "student_warnings": warnings,
        "teaching_actions": _as_text_list(raw.get("teaching_actions"), 10),
    }


def _build_analysis_payload(
    class_id: str,
    subject: str,
    folder_names: list[str],
    db: Session,
) -> tuple[dict, list[list[dict]], list[dict]]:
    students = db.query(Student).filter(Student.class_id == class_id).all()
    students.sort(key=_student_sort_key)
    students_by_name = {student.name: student for student in students}
    if not students_by_name:
        raise HTTPException(status_code=400, detail="当前班级暂无学生")

    class_info = db.query(Class).filter(Class.id == class_id).first()
    exam_names = [_display_folder_name(folder) for folder in folder_names]
    history_scores = _score_history_map(db, class_id, subject, exam_names, students_by_name)
    ignored_papers: list[dict] = []
    exam_summaries: list[dict] = []
    student_rows_by_exam: dict[str, list[dict]] = {}
    vision_papers: list[dict] = []
    image_count = 0
    missing_image_papers = 0
    total_record_papers = 0

    for exam_index, folder_name in enumerate(folder_names, start=1):
        exam_name = _display_folder_name(folder_name)
        collected, ignored = _collect_exam_data(folder_name, students_by_name)
        ignored_papers.extend({"folder_name": folder_name, "filename": name} for name in ignored)

        score_map = dict(history_scores.get(exam_name) or {})
        for student_name, exam in collected.items():
            score = exam.get("score")
            if student_name not in score_map and isinstance(score, (int, float)):
                score_map[student_name] = float(score)
        rankings = _rank_scores(score_map, students_by_name)
        ranking_by_student = {row["student_name"]: row for row in rankings}
        student_rows: list[dict] = []

        for student_name, exam in collected.items():
            total_record_papers += 1
            student = students_by_name[student_name]
            counts = _student_exam_counts(exam)
            ranking = ranking_by_student.get(student_name) or {}
            wrong_records = [x for x in (exam.get("paper_records") or []) if isinstance(x, dict) and _status_code(x) in (2, 3)]
            row = {
                "student_id": student.id,
                "student_name": student.name,
                "student_number": student.student_number or "",
                "score": ranking.get("score"),
                "rank": ranking.get("rank"),
                **counts,
                "wrong_titles": [str(x.get("display_title") or x.get("question_key") or "") for x in wrong_records if x.get("display_title") or x.get("question_key")][:12],
            }
            student_rows.append(row)

            image_paths: list[Path] = []
            image_refs: list[str] = []
            page_index = 0
            for filename in exam.get("source_filenames") or []:
                for image_path in _resolve_full_image_paths(folder_name, str(filename)):
                    if image_path in image_paths:
                        continue
                    page_index += 1
                    image_paths.append(image_path)
                    image_refs.append(f"exam_{exam_index}_student_{_safe_stem(student.id)}_page_{page_index}")
            if not image_paths:
                missing_image_papers += 1
                continue
            image_count += len(image_paths)
            vision_papers.append({
                "paper_ref": f"exam_{exam_index}_student_{_safe_stem(student.id)}",
                "exam_name": exam_name,
                "student": {
                    "id": student.id,
                    "name": student.name,
                    "student_number": student.student_number or "",
                },
                "score_and_rank": {
                    "score": ranking.get("score"),
                    "rank": ranking.get("rank"),
                    **counts,
                },
                "image_paths": image_paths,
                "image_refs": image_refs,
                "exam_record_json": [_compact_record(x) for x in (exam.get("paper_records") or [])[:160] if isinstance(x, dict)],
                "wrong_question_json": [_compact_wrong_analysis(x) for x in (exam.get("wrong_analysis") or [])[:80] if isinstance(x, dict)],
            })

        student_rows.sort(key=lambda row: (row.get("rank") is None, row.get("rank") or 999999, row.get("student_number") or row.get("student_name")))
        student_rows_by_exam[exam_name] = student_rows
        scores = [float(row["score"]) for row in rankings if isinstance(row.get("score"), (int, float))]
        answer_area_count = sum(int(row.get("answer_area_count") or 0) for row in student_rows)
        wrong_count = sum(int(row.get("wrong_count") or 0) for row in student_rows)
        blank_count = sum(int(row.get("blank_count") or 0) for row in student_rows)
        exam_summaries.append({
            "exam_name": exam_name,
            "folder_name": folder_name,
            "order": exam_index,
            "participant_count": len(rankings),
            "record_paper_count": len(collected),
            "average_score": round(statistics.fmean(scores), 1) if scores else None,
            "median_score": round(statistics.median(scores), 1) if scores else None,
            "highest_score": round(max(scores), 1) if scores else None,
            "lowest_score": round(min(scores), 1) if scores else None,
            "answer_area_count": answer_area_count,
            "wrong_count": wrong_count,
            "blank_count": blank_count,
            "wrong_rate": round((wrong_count + blank_count) / answer_area_count * 100, 1) if answer_area_count else None,
            "rankings": rankings,
        })

    if not exam_summaries or not any(item.get("record_paper_count") for item in exam_summaries):
        raise HTTPException(status_code=400, detail="选中的考试中没有找到与本班学生对应的批改JSON")
    if image_count <= 0:
        raise HTTPException(status_code=400, detail="选中的考试没有找到可与学生JSON对应的完整试卷图片")
    if image_count > CLASS_ANALYSIS_MAX_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"本次共需分析{image_count}张完整试卷图片，超过单次上限{CLASS_ANALYSIS_MAX_IMAGES}张，请减少考试数量后重试",
        )

    warning_candidates = _build_warning_candidates(student_rows_by_exam)
    averages = [item.get("average_score") for item in exam_summaries if isinstance(item.get("average_score"), (int, float))]
    deterministic = {
        "class": {
            "class_id": class_id,
            "class_name": class_info.name if class_info else "",
            "school_level": class_info.school_level if class_info else "",
            "grade": class_info.grade if class_info else "",
            "student_count": len(students),
        },
        "subject": subject,
        "students": [
            {"id": student.id, "name": student.name, "student_number": student.student_number or ""}
            for student in students
        ],
        "exam_order": exam_names,
        "exam_summaries": exam_summaries,
        "overall_metrics": {
            "exam_count": len(exam_names),
            "latest_average_score": averages[-1] if averages else None,
            "average_score_change": round(averages[-1] - averages[0], 1) if len(averages) >= 2 else None,
            "record_paper_count": total_record_papers,
            "image_count": image_count,
            "image_paper_coverage_rate": round((total_record_papers - missing_image_papers) / total_record_papers * 100, 1) if total_record_papers else 0,
        },
        "warning_candidates": warning_candidates,
    }

    batches: list[list[dict]] = []
    current: list[dict] = []
    current_images = 0
    for paper in vision_papers:
        paper_image_count = len(paper.get("image_paths") or [])
        if current and current_images + paper_image_count > CLASS_ANALYSIS_IMAGE_BATCH_SIZE:
            batches.append(current)
            current = []
            current_images = 0
        current.append(paper)
        current_images += paper_image_count
    if current:
        batches.append(current)
    return deterministic, batches, ignored_papers


@router.get("/subjects", response_model=ApiResponse[list])
def list_subjects(user_id: str = Depends(get_current_user_id)):
    return ApiResponse(data=SUBJECTS)


def _report_view_allowed(db: Session, user_id: str, class_id: str) -> bool:
    """班级报告可见性（E04）：教师/管理员走原有 can_view_class（完整视图）。

    家长当前在 class_access 体系无入口，这里作为契约预埋：仅当家长绑定本班学生
    （parent_students.status=active）时才放行，视图由调用方用 filter_rankings_for_parent 裁剪。
    """
    if can_view_class(db, user_id, class_id):
        return True
    if access_svc.is_parent_user(db, user_id):
        bound_ids = access_svc.get_parent_bound_student_ids(db, user_id)
        if not bound_ids:
            return False
        return (
            db.query(Student.id)
            .filter(Student.class_id == class_id, Student.id.in_(bound_ids))
            .first()
            is not None
        )
    return False


@router.get("/report", response_model=ApiResponse[dict])
def get_report(
    class_id: str = Query(...),
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if not _report_view_allowed(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级访问权限")

    # 家长视图裁剪（教师/管理员 is_parent_view=False，保持现状完整视图）
    is_parent_view = (
        not can_view_class(db, user_id, class_id)
        and access_svc.is_parent_user(db, user_id)
    )
    parent_bound_ids: set[str] = set(
        access_svc.get_parent_bound_student_ids(db, user_id)
    ) if is_parent_view else set()

    class_info = db.query(Class).filter(Class.id == class_id).first()
    row = db.query(ClassAnalysisReport).filter(
        ClassAnalysisReport.class_id == class_id,
        ClassAnalysisReport.subject == subject,
    ).first()
    if row:
        current_name = class_info.name if class_info else row.class_name
        if current_name and row.class_name != current_name:
            row.class_name = current_name
            db.commit()
            db.refresh(row)
        report = _db_report_to_dict(row)
    else:
        # Compatibility migration: import an existing local report into MySQL once.
        file_report = _read_file_report(class_id, subject)
        if file_report and class_info:
            row = _upsert_db_report(
                db,
                class_id=class_id,
                class_name=class_info.name,
                subject=subject,
                report=file_report,
            )
            db.commit()
            db.refresh(row)
            report = _db_report_to_dict(row)
        else:
            return ApiResponse(data={"report": None})

    if is_parent_view and report:
        for summary in (report.get("source_summary") or {}).get("exam_summaries") or []:
            if isinstance(summary, dict):
                summary["rankings"] = filter_rankings_for_parent(
                    summary.get("rankings") or [], parent_bound_ids
                )
    return ApiResponse(data={"report": report})


@router.get("/importable-exams", response_model=ApiResponse[list])
def list_importable_exams(
    class_id: str = Query(...),
    subject: str = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    prefix = _class_folder_prefix(class_id)
    if not prefix:
        return ApiResponse(data=[])
    try:
        candidates = [item.name for item in correct_docs_dir().iterdir() if item.is_dir() and item.name.startswith(prefix)]
    except Exception:
        candidates = []
    exams = []
    for folder_name in candidates:
        count = _folder_completion_count(folder_name)
        if count <= 0:
            continue
        exams.append({
            "id": folder_name,
            "name": _display_folder_name(folder_name),
            "completed_count": count,
            "updated_at": _exam_mtime(folder_name),
        })
    exams.sort(key=lambda item: item.get("updated_at") or 0)
    return ApiResponse(data=exams)


@router.post("/analyze", response_model=ApiResponse[dict])
def generate_analysis(
    body: GenerateClassAnalysisRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    # E08 · 学校级 AI 管控：班级学情分析（ai_review）开关关闭时一律 403
    require_ai_access(db, user_id, "ai_review")
    _assert_class_access(db, user_id, body.class_id)
    prefix = _class_folder_prefix(body.class_id)
    if not prefix:
        raise HTTPException(status_code=400, detail="班级ID无效")
    folder_names = [str(item or "").strip() for item in body.exam_folder_names if str(item or "").strip()]
    folder_names = list(dict.fromkeys(folder_names))
    if not folder_names:
        raise HTTPException(status_code=400, detail="请选择至少一场考试")
    invalid = [name for name in folder_names if not name.startswith(prefix)]
    if invalid:
        raise HTTPException(status_code=400, detail="存在不属于当前班级的考试")

    deterministic, batches, ignored_papers = _build_analysis_payload(
        body.class_id,
        body.subject,
        folder_names,
        db,
    )
    api_key, model = get_qwen_config(db)
    if not api_key:
        raise HTTPException(status_code=500, detail="系统设置中未配置千问 API Key，无法生成班级分析")

    # PII 匿名化：请求级稳定映射，先登记全班真名再匿名化 deterministic，
    # 各并发 vision batch 与最终汇总 prompt 共享同一个 Anonymizer，保证同学生跨 batch 用同一匿名。
    anon = Anonymizer()
    for student in deterministic.get("students") or []:
        if isinstance(student, dict) and student.get("name"):
            anon.anon(str(student["name"]))
    deterministic_anon = anon.anon_deep(deterministic)

    vision_results_by_id: dict[str, dict] = {}
    errors: list[str] = []
    worker_count = min(CLASS_ANALYSIS_IMAGE_WORKERS, len(batches))
    with ThreadPoolExecutor(max_workers=max(1, worker_count), thread_name_prefix="class-analysis-vision") as executor:
        futures = {
            executor.submit(_run_vision_batch, api_key, model, f"batch_{index}", anon.anon_deep(papers)): f"batch_{index}"
            for index, papers in enumerate(batches, start=1)
        }
        for future in as_completed(futures):
            batch_id = futures[future]
            try:
                got_id, result = future.result()
                vision_results_by_id[got_id] = result
            except Exception as exc:
                errors.append(f"{batch_id}: {exc}")
    if errors:
        raise HTTPException(status_code=500, detail="完整试卷图片分析失败：" + "；".join(errors[:3]))

    # vision_results 内 student_names/student_name 均为匿名标识，直接喂给最终汇总 prompt，
    # AI 返回的 student_warnings/affected_students 等再统一 restore 回真名后入库。
    vision_results = [vision_results_by_id[f"batch_{index}"] for index in range(1, len(batches) + 1)]
    try:
        raw_analysis = _qwen_completion(
            api_key,
            model,
            _build_final_prompt(body.subject, deterministic_anon, vision_results),
            timeout=240,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"千问班级汇总分析失败: {exc}") from exc
    raw_analysis = anon.restore_deep(raw_analysis)
    analysis = _normalize_final_analysis(raw_analysis, deterministic)
    # AI 输出红线词过滤：深滤所有文本值（best-effort，异常不阻断分析主流程）
    try:
        analysis = _filter_redline_deep(analysis)
    except Exception:  # noqa: BLE001 - best-effort，红线过滤失败放行原文
        pass

    now = datetime.now(timezone.utc).isoformat()
    report = {
        "id": uuid.uuid4().hex,
        "class_id": body.class_id,
        "subject": body.subject,
        "exam_names": deterministic["exam_order"],
        "imported_folder_names": folder_names,
        "source_summary": {
            "class": deterministic["class"],
            "overall_metrics": deterministic["overall_metrics"],
            "exam_summaries": deterministic["exam_summaries"],
            "ignored_paper_count": len(ignored_papers),
            "vision_batch_count": len(batches),
            "model": model,
        },
        "analysis": analysis,
        "generated_at": now,
        "updated_at": now,
    }
    class_name = str((deterministic.get("class") or {}).get("class_name") or "").strip()
    if not class_name:
        raise HTTPException(status_code=400, detail="未找到当前班级名称，无法保存班级分析")
    row = _upsert_db_report(
        db,
        class_id=body.class_id,
        class_name=class_name,
        subject=body.subject,
        report=report,
        model=model,
    )
    db.commit()
    db.refresh(row)
    stored_report = _db_report_to_dict(row) or report
    try:
        _write_file_report(body.class_id, body.subject, stored_report)
    except Exception:
        # MySQL is authoritative; local JSON is only a recovery backup.
        pass
    return ApiResponse(data={
        "ok": True,
        "report": stored_report,
        "ignored_count": len(ignored_papers),
        "ignored_papers": ignored_papers[:50],
    })


# ═══════════════════════════════ 年级分析 / 跨班对标（聚合端点） ═══════════════════════════════

_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}
_RISK_BY_SEVERITY = {"high": 80.0, "medium": 50.0, "low": 30.0}


def _round_1(value: Any) -> float:
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return 0.0


def _score_num(value: Any) -> Any:
    """成绩数值序列化：整数保持 int，小数保留 1 位。"""
    if value is None:
        return 0
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0
    return int(f) if f.is_integer() else round(f, 1)


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _exam_summaries(source_summary: dict) -> list[dict]:
    """按考试 order 升序返回 exam_summaries（无 order 字段时保持原始顺序）。"""
    summaries = [x for x in (source_summary or {}).get("exam_summaries") or [] if isinstance(x, dict)]
    return sorted(
        summaries,
        key=lambda x: x.get("order") if isinstance(x.get("order"), (int, float)) else 999999,
    )


def _rankings_pass_rate(final: Optional[dict], threshold: int) -> float:
    """期末 rankings 中 score>=threshold 的比例（%）。rankings 为空返回 0。"""
    if not final:
        return 0.0
    rankings = [r for r in (final.get("rankings") or []) if isinstance(r, dict)]
    if not rankings:
        return 0.0
    passed = sum(1 for r in rankings if (_to_float(r.get("score")) or 0.0) >= threshold)
    return round(passed / len(rankings) * 100, 1)


def _class_metrics(source_summary: dict) -> dict:
    """从 source_summary 提炼班级聚合指标（期末均分/最高分/及格率/优秀率/趋势/各次均分）。"""
    summaries = _exam_summaries(source_summary)
    final = summaries[-1] if summaries else None
    first = summaries[0] if summaries else None
    scores_by_exam: dict[str, Optional[float]] = {}
    for s in summaries:
        scores_by_exam[str(s.get("exam_name") or "")] = _to_float(s.get("average_score"))
    first_avg = _to_float(first.get("average_score")) if first else None
    final_avg = _to_float(final.get("average_score")) if final else None
    trend_delta = 0.0
    if first_avg is not None and final_avg is not None:
        trend_delta = round(final_avg - first_avg, 1)
    return {
        "average_score": final_avg,
        "highest_score": _to_float(final.get("highest_score")) if final else None,
        "pass_rate": _rankings_pass_rate(final, 60),
        "excellent_rate": _rankings_pass_rate(final, 85),
        "trend_delta": trend_delta,
        "scores_by_exam": scores_by_exam,
        "final_exam_name": str((final or {}).get("exam_name") or ""),
        "final": final,
    }


def _load_grade_reports(db: Session, class_ids: list[str], subject: str) -> dict[str, dict]:
    """批量按班加载同科报告；解析异常/无报告跳过，返回 {class_id: {source_summary, analysis}}。"""
    ids = [x for x in (class_ids or []) if x]
    if not ids:
        return {}
    rows = db.query(ClassAnalysisReport).filter(
        ClassAnalysisReport.class_id.in_(ids),
        ClassAnalysisReport.subject == subject,
    ).all()
    out: dict[str, dict] = {}
    for row in rows:
        try:
            source = json.loads(row.source_summary_json or "{}")
            analysis = json.loads(row.analysis_json or "{}")
        except Exception:
            continue
        if not isinstance(source, dict) or not isinstance(analysis, dict):
            continue
        out[row.class_id] = {"source_summary": source, "analysis": analysis}
    return out


def _aggregate_weak_points(class_weak: list[tuple[dict, str]]) -> list[dict]:
    """跨班按知识点聚合薄弱点：avgRisk 降序取前 5。class_weak: [(analysis, final_exam_name), ...]。

    风险取 heatmap 期末 risk（无则取 weak_points severity 折算），affectedClasses 为出现班级数，
    severity 取出现班级里最高级；无 weak_points 时按 avgRisk 阈值折算。
    """
    by_point: dict[str, dict] = {}
    for analysis, final_exam_name in class_weak:
        heatmap = {
            str(i.get("knowledge_point") or ""): i
            for i in (analysis.get("knowledge_heatmap") or [])
            if isinstance(i, dict) and str(i.get("knowledge_point") or "")
        }
        weak = {
            str(i.get("knowledge_point") or ""): i
            for i in (analysis.get("weak_points") or [])
            if isinstance(i, dict) and str(i.get("knowledge_point") or "")
        }
        for kp in set(heatmap) | set(weak):
            entry = by_point.setdefault(kp, {"risks": [], "severities": []})
            risk: Optional[float] = None
            heat = heatmap.get(kp)
            if heat:
                values = [v for v in (heat.get("values") or []) if isinstance(v, dict)]
                if values:
                    matched = next(
                        (v for v in values if str(v.get("exam_name") or "") == final_exam_name),
                        None,
                    )
                    risk = _to_float((matched or values[-1]).get("risk_score"))
            wp = weak.get(kp)
            if risk is None and wp:
                severity = str(wp.get("severity") or "medium").lower()
                risk = _RISK_BY_SEVERITY.get(severity, 50.0)
            if risk is None:
                continue  # 该班该点无风险数据，跳过
            entry["risks"].append(risk)
            if wp:
                entry["severities"].append(str(wp.get("severity") or "medium").lower())

    output: list[dict] = []
    for kp, entry in by_point.items():
        if not entry["risks"]:
            continue
        avg_risk = round(sum(entry["risks"]) / len(entry["risks"]), 1)
        severity = "low"
        for s in entry["severities"]:
            if _SEVERITY_RANK.get(s, 0) > _SEVERITY_RANK.get(severity, 0):
                severity = s
        if not entry["severities"]:
            severity = "high" if avg_risk >= 60 else "medium" if avg_risk >= 30 else "low"
        output.append({
            "knowledge_point": kp,
            "avgRisk": avg_risk,
            "affectedClasses": len(entry["risks"]),
            "severity": severity,
        })
    output.sort(key=lambda x: (-x["avgRisk"], x["knowledge_point"]))
    return output[:5]


def _ordered_exam_names(source_list: list[dict]) -> list[str]:
    """按各班 exam_summaries 顺序收集考试名并集（保留首次出现顺序）。"""
    names: list[str] = []
    seen: set[str] = set()
    for source in source_list:
        for s in _exam_summaries(source):
            name = str(s.get("exam_name") or "")
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _empty_grade_summary(grade: str, subject: str) -> dict:
    return {
        "grade": grade,
        "subject": subject,
        "totalStudents": 0,
        "subjectAverage": 0.0,
        "passRate": 0.0,
        "attentionCount": 0,
        "classRows": [],
        "trendSeries": {"examNames": [], "perClass": []},
        "weakPointsTop5": [],
    }


@router.get("/grade-summary", response_model=ApiResponse[dict])
def get_grade_summary(
    grade: str = Query(...),
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """年级分析聚合：同一年级多班的核心指标、多班趋势、跨班薄弱点。"""
    grade = (grade or "").strip()
    class_rows = db.query(Class).filter(Class.grade == grade).all()
    if not class_rows:
        return ApiResponse(data=_empty_grade_summary(grade, subject))
    # 权限：同年级任一班级可访问即放行（管理员/年级组长天然通过）
    if not any(can_view_class(db, user_id, c.id) for c in class_rows):
        raise HTTPException(status_code=403, detail="forbidden: 无该年级访问权限")

    reports = _load_grade_reports(db, [c.id for c in class_rows], subject)
    if not reports:
        return ApiResponse(data=_empty_grade_summary(grade, subject))

    class_metrics: list[tuple[Class, dict]] = []
    total_students = 0
    pass_count = 0
    ranking_total = 0
    attention: set[tuple[str, str]] = set()
    weak_source: list[tuple[dict, str]] = []

    for c in class_rows:
        report = reports.get(c.id)
        if not report:
            continue
        metrics = _class_metrics(report["source_summary"])
        if metrics["average_score"] is None:
            continue  # 期末无均分，跳过该班
        rankings = [r for r in (metrics["final"] or {}).get("rankings") or [] if isinstance(r, dict)]
        pass_count += sum(1 for r in rankings if (_to_float(r.get("score")) or 0.0) >= 60)
        ranking_total += len(rankings)
        total_students += int(getattr(c, "student_count") or 0)
        class_metrics.append((c, metrics))

        for w in report["analysis"].get("student_warnings") or []:
            if not isinstance(w, dict):
                continue
            if w.get("student_id"):
                attention.add(("id", str(w["student_id"])))
            else:
                name = str(w.get("student_name") or "")
                if name:
                    attention.add(("name", name))
        weak_source.append((report["analysis"], metrics["final_exam_name"]))

    # 统一按期末均分降序排列（classRows 与 trendSeries.perClass 顺序一致）
    class_metrics.sort(key=lambda x: (-x[1]["average_score"], x[0].name))

    subject_average = (
        round(statistics.fmean([m["average_score"] for _, m in class_metrics]), 1)
        if class_metrics
        else 0.0
    )
    pass_rate = round(pass_count / ranking_total * 100, 1) if ranking_total else 0.0

    class_rows_out: list[dict] = []
    for c, m in class_metrics:
        class_rows_out.append({
            "classId": c.id,
            "className": c.name,
            "averageScore": _round_1(m["average_score"]),
            "passRate": m["pass_rate"],
            "excellentRate": m["excellent_rate"],
            "highestScore": _score_num(m["highest_score"]),
            "trendDelta": m["trend_delta"],
        })

    ordered_names = _ordered_exam_names([
        reports[c.id]["source_summary"] for c, _ in class_metrics
    ])
    per_class: list[dict] = []
    for c, m in class_metrics:
        scores = []
        for name in ordered_names:
            value = m["scores_by_exam"].get(name)
            scores.append(_score_num(value) if value is not None else None)
        per_class.append({"className": c.name, "scores": scores})

    return ApiResponse(data={
        "grade": grade,
        "subject": subject,
        "totalStudents": total_students,
        "subjectAverage": subject_average,
        "passRate": pass_rate,
        "attentionCount": len(attention),
        "classRows": class_rows_out,
        "trendSeries": {"examNames": ordered_names, "perClass": per_class},
        "weakPointsTop5": _aggregate_weak_points(weak_source),
    })


@router.get("/grade-comparison", response_model=ApiResponse[dict])
def get_grade_comparison(
    class_id: str = Query(...),
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """跨班对标：本班在同年级中的位置、年级均值、含本班的班级排名列表与标杆班。"""
    _assert_class_access(db, user_id, class_id)
    class_info = db.query(Class).filter(Class.id == class_id).first()
    if not class_info:
        raise HTTPException(status_code=404, detail="班级不存在")
    class_rows = db.query(Class).filter(Class.grade == class_info.grade).all()
    reports = _load_grade_reports(db, [c.id for c in class_rows], subject)

    peers: list[tuple[Class, dict]] = []
    pass_count = 0
    ranking_total = 0
    for c in class_rows:
        report = reports.get(c.id)
        if not report:
            continue
        metrics = _class_metrics(report["source_summary"])
        if metrics["average_score"] is None:
            continue
        rankings = [r for r in (metrics["final"] or {}).get("rankings") or [] if isinstance(r, dict)]
        pass_count += sum(1 for r in rankings if (_to_float(r.get("score")) or 0.0) >= 60)
        ranking_total += len(rankings)
        peers.append((c, metrics))
    peers.sort(key=lambda x: (-x[1]["average_score"], x[0].name))

    rank = 0
    current_metrics: Optional[dict] = None
    for idx, (c, m) in enumerate(peers, start=1):
        if c.id == class_id:
            rank = idx
            current_metrics = m
            break

    peer_classes: list[dict] = []
    for c, m in peers:
        peer_classes.append({
            "classId": c.id,
            "className": c.name,
            "averageScore": _round_1(m["average_score"]),
            "passRate": m["pass_rate"],
            "highestScore": _score_num(m["highest_score"]),
            "trendDelta": m["trend_delta"],
            "isCurrent": c.id == class_id,
        })

    grade_avg = {
        "averageScore": (
            round(statistics.fmean([m["average_score"] for _, m in peers]), 1) if peers else 0.0
        ),
        "passRate": round(pass_count / ranking_total * 100, 1) if ranking_total else 0.0,
    }

    benchmark_class: Optional[dict] = None
    if peers:
        top = peers[0]
        benchmark_class = {
            "className": top[0].name,
            "averageScore": _round_1(top[1]["average_score"]),
        }

    current_class = {
        "classId": class_id,
        "className": class_info.name,
        "averageScore": _round_1(current_metrics["average_score"]) if current_metrics else 0.0,
        "passRate": current_metrics["pass_rate"] if current_metrics else 0.0,
        "rank": rank,
        "trendDelta": current_metrics["trend_delta"] if current_metrics else 0.0,
        "highestScore": _score_num(current_metrics["highest_score"]) if current_metrics else 0,
    }

    return ApiResponse(data={
        "currentClass": current_class,
        "gradeAvg": grade_avg,
        "peerClasses": peer_classes,
        "benchmarkClass": benchmark_class,
    })


@router.get("/mastery-distribution", response_model=ApiResponse[list])
def get_mastery_distribution(
    school_id: str = Query(..., description="学校 ID（必填，防越权）"),
    class_id: Optional[str] = Query(None, description="班级维度：仅统计该班"),
    student_id: Optional[str] = Query(None, description="学生维度：仅统计该生"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """班级/学生知识点掌握度聚合（错题分布派生口径）。

    口径：数据源为错题唯一权威表 student_wrong_questions（17,052 行），仅含错题样本、
    无正答/满分样本；知识点归属经 wrong_question_kp_bridge（R6a 跨库匹配落表）以 kp_name
    关联，kp_id 可能为 NULL（未收录），无 bridge 的错题归入「未标注知识点」桶。
    mastery = 1 - wrong_count/total（该知识点错题占比越低→掌握度越高），相对口径、
    真实但粗，由错题分布派生（非测评满分率）；total=当前范围内错题总数。
    school_id 必填，且 class/student 归属该校校验，防越权；仅返回聚合统计，不暴露 PII。
    """
    if class_id and student_id:
        raise HTTPException(status_code=400, detail="class_id 与 student_id 只能二选一")
    if not db.query(School.id).filter(School.id == school_id).first():
        raise HTTPException(status_code=404, detail="学校不存在")
    school_class_ids = {cid for (cid,) in db.query(Class.id).filter(Class.school_id == school_id).all()}
    scope_ids: set[str] = school_class_ids
    student_name: Optional[str] = None
    if class_id:
        if class_id not in school_class_ids:
            raise HTTPException(status_code=404, detail="班级不存在或不属于该校")
        _assert_class_access(db, user_id, class_id)
        scope_ids = {class_id}
    elif student_id:
        stu = db.query(Student).filter(Student.id == student_id).first()
        if not stu or stu.school_id != school_id:
            raise HTTPException(status_code=404, detail="学生不存在或不属于该校")
        _assert_class_access(db, user_id, stu.class_id)
        scope_ids = {stu.class_id}
        student_name = stu.name
    elif not scope_ids:
        return ApiResponse(data=[])
    elif not any(can_view_class(db, user_id, cid) for cid in scope_ids):
        raise HTTPException(status_code=403, detail="forbidden: 无该校班级访问权限")

    q = (
        db.query(StudentWrongQuestion.id, WrongQuestionKpBridge.kp_id, WrongQuestionKpBridge.kp_name)
        .outerjoin(WrongQuestionKpBridge, WrongQuestionKpBridge.wrong_question_id == StudentWrongQuestion.id)
        .filter(StudentWrongQuestion.class_id.in_(scope_ids))
    )
    if student_name is not None:
        q = q.filter(StudentWrongQuestion.student_name == student_name)
    rows = q.all()
    if not rows:
        return ApiResponse(data=[])
    total = len(rows)
    agg: dict[str, dict] = {}
    for _, kp_id, kp_name in rows:
        key = kp_name or "未标注知识点"
        bucket = agg.get(key)
        if bucket is None:
            agg[key] = {"knowledge_point_id": kp_id, "name": key, "wrong_count": 0}
        agg[key]["wrong_count"] += 1
    items = [
        {
            "knowledge_point_id": b["knowledge_point_id"],
            "name": b["name"],
            "mastery": round(1 - b["wrong_count"] / total, 4),
            "wrong_count": b["wrong_count"],
            "total": total,
        }
        for b in sorted(agg.values(), key=lambda x: -x["wrong_count"])
    ]
    return ApiResponse(data=items)
