import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id, bind_grading_user_context
from app.grading.user_paths import correct_docs_dir, grading_history_dir
from app.grading.router import (
    _class_folder_prefix,
    _parse_ai_result_to_counts,
    _preview_url_for_file,
    _read_essay_history,
    _read_grading_history,
)
from app.grading import wrong_question_db
from app.models.knowledge_point import KnowledgePoint
from app.models.student import Student
from app.models.targeted_improvement import (
    TargetedImprovementReport,
    TargetedImprovementTask,
    TargetedRecommendation,
)
from app.models.teaching_resource import TeachingResource
from app.schemas.common import ApiResponse
from app.services.redline_filter import filter_text
from app.utils.anonymize import Anonymizer
from app.utils.class_access import can_view_class
from app.utils.qwen_settings import AI_GENERATOR, QWEN_CHAT_EXTRA_BODY, get_llm_base_url, get_llm_config


router = APIRouter(prefix="/targeted-improvement", tags=["targeted_improvement"], dependencies=[Depends(bind_grading_user_context)])


def _assert_class_access(db: Session, user_id: str, class_id: str) -> None:
    """校验调用者对目标班级有访问权限（教师=所带班级，班主任/副班主任=本班，系统管理员/校级管理者/年级组长=全校），否则 403。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级访问权限")

# 导入考试时并行调用千问的 worker 数（可通过环境变量 TARGETED_IMPORT_WORKERS 调整，建议 3~6）
TARGETED_IMPORT_WORKERS = max(1, min(8, int(os.environ.get("TARGETED_IMPORT_WORKERS", "5"))))


SUBJECTS = ["语文", "数学", "英语", "科学", "物理", "化学", "生物", "历史", "地理", "政治"]


class RecommendationUpdate(BaseModel):
    class_id: str
    subject: str
    student_names: list[str]


class ImportExamsRequest(BaseModel):
    class_id: str
    subject: str
    exam_folder_names: list[str]


class TaskSyncRequest(BaseModel):
    """从报告生成/同步任务清单：二选一 report_id，或 class_id+subject(+student_id/student_name)。"""
    report_id: Optional[str] = None
    class_id: Optional[str] = None
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    subject: Optional[str] = None


class TaskUpdateRequest(BaseModel):
    is_done: bool


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _json_loads(text: Optional[str], fallback: Any) -> Any:
    if not text:
        return fallback
    try:
        return json.loads(text)
    except Exception:
        return fallback


def _student_sort_key(student: Student):
    raw = str(student.student_number or "").strip()
    if raw.isdigit():
        return (0, int(raw), student.name)
    return (1, raw, student.name)


def _student_base(student: Student) -> dict:
    return {
        "id": student.id,
        "name": student.name,
        "student_number": student.student_number or "",
    }


def _display_folder_name(name: str) -> str:
    s = str(name or "")
    if s.startswith("cls_") and "__" in s:
        return s.split("__", 1)[1] or s
    return s


def _paper_stem(filename: str) -> str:
    stem = Path(str(filename or "")).stem.strip()
    match = re.match(r"^(?P<name>.+)_\d+$", stem)
    return (match.group("name") if match else stem).strip()


def _safe_excerpt(text: Any, limit: int = 900) -> str:
    s = str(text or "").strip()
    if len(s) <= limit:
        return s
    return s[:limit] + "..."


def _find_paper_by_student(papers: dict, student_name: str) -> tuple[str, dict]:
    if not isinstance(papers, dict):
        return "", {}
    entry = papers.get(student_name)
    if isinstance(entry, dict):
        return student_name, entry
    for name, item in papers.items():
        if not isinstance(item, dict):
            continue
        paper_name = str(item.get("paper_name") or "").strip()
        if paper_name == student_name or _paper_stem(name) == student_name:
            return str(name), item
    return "", {}


def _resolve_student_name(
    filename: str,
    history_item: Optional[dict],
    students_by_name: dict[str, Student],
) -> str:
    if isinstance(history_item, dict):
        group_name = str(history_item.get("group_name") or "").strip()
        if group_name and group_name in students_by_name:
            return group_name
        student_info = history_item.get("student")
        if isinstance(student_info, dict):
            student_name = str(student_info.get("name") or "").strip()
            if student_name and student_name in students_by_name:
                return student_name
    return _paper_stem(filename)


def _ct_paper_student_name(paper_key: str, paper: dict) -> str:
    student_info = paper.get("student")
    if isinstance(student_info, dict):
        student_name = str(student_info.get("name") or "").strip()
        if student_name:
            return student_name
    paper_name = str(paper.get("paper_name") or "").strip()
    if paper_name:
        return paper_name
    return _paper_stem(paper_key)


def _lookup_ct_paper(papers: dict, student_name: str, filename: str = "") -> Optional[dict]:
    if not isinstance(papers, dict):
        return None
    entry = papers.get(student_name)
    if isinstance(entry, dict):
        return entry
    _, entry = _find_paper_by_student(papers, student_name)
    if isinstance(entry, dict):
        return entry
    if filename:
        entry = papers.get(filename)
        if isinstance(entry, dict):
            return entry
    return None


def _read_wrong_jsons(folder_safe: str) -> tuple[dict, dict]:
    record_path = wrong_question_db._record_json_path(folder_safe, create_class_dir=False)
    analysis_path = wrong_question_db._analysis_json_path(folder_safe, create_class_dir=False)
    records = wrong_question_db._read_json(record_path) if record_path else {}
    analysis = wrong_question_db._read_json(analysis_path) if analysis_path else {}
    return records, analysis


def _score_from_item(item: dict) -> Optional[float]:
    if not isinstance(item, dict):
        return None
    for key in ("score_total", "score", "total_score"):
        raw = item.get(key)
        try:
            if raw is not None and str(raw).strip() != "":
                return round(float(raw), 1)
        except Exception:
            pass
    result = str(item.get("result") or "")
    try:
        parsed = json.loads(result)
        scores = parsed.get("scores")
        if isinstance(scores, dict):
            total = 0.0
            seen = False
            for value in scores.values():
                try:
                    total += float(value or 0)
                    seen = True
                except Exception:
                    pass
            if seen:
                return round(total, 1)
    except Exception:
        pass
    m = re.search(r"<essay_score>\s*([\d.]+)\s*</essay_score>", result)
    if not m:
        m = re.search(r"作文得分[：:\s]*([\d.]+)", result)
    if m:
        try:
            return round(float(m.group(1)), 1)
        except Exception:
            return None
    return None


def _wrong_titles_from_grading_result(result: str) -> list[str]:
    titles: list[str] = []
    try:
        _, blocks = _parse_ai_result_to_counts(result or "")
    except Exception:
        return titles
    for block in blocks or []:
        if block.get("status") in ("wrong", "blank"):
            title = str(block.get("title") or "").strip()
            if title:
                titles.append(title)
        for idx, sub in enumerate(block.get("subItems") or [], start=1):
            if isinstance(sub, dict) and sub.get("status") in ("wrong", "blank"):
                base = str(block.get("title") or "").strip()
                sub_title = str(sub.get("title") or f"作答区{idx}").strip()
                titles.append(f"{base}-{sub_title}" if base else sub_title)
    return list(dict.fromkeys(titles))


def _analysis_items_for_paper(analysis_paper: dict) -> list[dict]:
    if not isinstance(analysis_paper, dict):
        return []
    items = analysis_paper.get("wrong_question_analysis")
    return items if isinstance(items, list) else []


def _records_for_paper(record_paper: dict) -> list[dict]:
    if not isinstance(record_paper, dict):
        return []
    items = record_paper.get("questions")
    if not isinstance(items, list):
        items = record_paper.get("wrong_questions")
    return items if isinstance(items, list) else []


def _is_wrong_record(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    try:
        if int(item.get("status_code")) in (2, 3):
            return True
    except Exception:
        pass
    status = str(item.get("status") or "").strip()
    return any(word in status for word in ("错", "错误", "未作答", "blank", "wrong"))


def _is_correct_record(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    try:
        return int(item.get("status_code")) == 1
    except Exception:
        pass
    status = str(item.get("status") or "").strip().lower()
    return status in ("正确", "correct", "right")


def _compact_question_record(item: dict) -> dict:
    render = item.get("render") if isinstance(item.get("render"), dict) else {}
    return {
        "question_key": item.get("question_key"),
        "display_title": item.get("display_title") or item.get("question_key"),
        "status": item.get("status"),
        "status_code": item.get("status_code"),
        "question_type": item.get("question_type"),
        "paper_subject": item.get("paper_subject"),
        "reason": item.get("reason"),
        "comment": render.get("comment") if isinstance(render, dict) else "",
    }


def _exam_mtime(folder_safe: str) -> float:
    candidates = []
    folder = correct_docs_dir() / folder_safe
    if folder.exists():
        candidates.append(folder.stat().st_mtime)
    for suffix in ("", "__manual", "__essay"):
        p = grading_history_dir() / f"{folder_safe}{suffix}.json"
        if p.is_file():
            candidates.append(p.stat().st_mtime)
    return max(candidates) if candidates else 0.0


def _folder_completion_count(folder_safe: str) -> int:
    total = 0
    for engine in ("default", "manual"):
        try:
            data = _read_grading_history(folder_safe, engine)
            completed = data.get("completed")
            if isinstance(completed, dict):
                total += len(completed)
        except Exception:
            pass
    try:
        data = _read_essay_history(folder_safe)
        completed = data.get("completed")
        if isinstance(completed, dict):
            total += len(completed)
    except Exception:
        pass
    records, _ = _read_wrong_jsons(folder_safe)
    papers = records.get("papers")
    if isinstance(papers, dict):
        total = max(total, len(papers))
    return total


def _collect_exam_data(folder_safe: str, students_by_name: dict[str, Student]) -> tuple[dict[str, dict], list[str]]:
    default_history = _read_grading_history(folder_safe, "default").get("completed", {})
    manual_history = _read_grading_history(folder_safe, "manual").get("completed", {})
    essay_history = _read_essay_history(folder_safe).get("completed", {})
    records_json, analysis_json = _read_wrong_jsons(folder_safe)
    record_papers = records_json.get("papers") if isinstance(records_json.get("papers"), dict) else {}
    analysis_papers = analysis_json.get("papers") if isinstance(analysis_json.get("papers"), dict) else {}

    exam_name = _display_folder_name(folder_safe)
    result: dict[str, dict] = {}
    ignored: list[str] = []
    filenames_by_student: dict[str, list[str]] = {}

    def _register_filename(student_name: str, filename: str) -> None:
        token = str(filename or "").strip()
        if not token:
            return
        if student_name not in students_by_name:
            ignored.append(token)
            return
        bucket = filenames_by_student.setdefault(student_name, [])
        if token not in bucket:
            bucket.append(token)

    if isinstance(default_history, dict):
        for filename, item in default_history.items():
            _register_filename(
                _resolve_student_name(str(filename), item if isinstance(item, dict) else None, students_by_name),
                str(filename),
            )
    if isinstance(manual_history, dict):
        for filename, item in manual_history.items():
            _register_filename(
                _resolve_student_name(str(filename), item if isinstance(item, dict) else None, students_by_name),
                str(filename),
            )
    if isinstance(essay_history, dict):
        for filename, item in essay_history.items():
            _register_filename(
                _resolve_student_name(str(filename), item if isinstance(item, dict) else None, students_by_name),
                str(filename),
            )
    for paper_key, paper in record_papers.items():
        if not isinstance(paper, dict):
            continue
        student_name = _ct_paper_student_name(str(paper_key), paper)
        _register_filename(student_name, str(paper_key))
        for src in paper.get("source_filenames") or []:
            _register_filename(student_name, str(src))
    for paper_key, paper in analysis_papers.items():
        if not isinstance(paper, dict):
            continue
        student_name = _ct_paper_student_name(str(paper_key), paper)
        _register_filename(student_name, str(paper_key))
        for src in paper.get("source_filenames") or []:
            _register_filename(student_name, str(src))

    for student_name, grouped_filenames in filenames_by_student.items():
        score_values: list[float] = []
        source_filenames: list[str] = []
        excerpts: list[str] = []
        question_records: list[dict] = []
        wrong_records: list[dict] = []
        correct_records: list[dict] = []
        analysis_items: list[dict] = []
        wrong_titles: list[str] = []
        correct_titles: list[str] = []
        record_keys: list[str] = []
        analysis_keys: list[str] = []
        image_url = ""

        record_paper = _lookup_ct_paper(record_papers, student_name)
        analysis_paper = _lookup_ct_paper(analysis_papers, student_name)
        record_key, _ = _find_paper_by_student(record_papers, student_name)
        analysis_key, _ = _find_paper_by_student(analysis_papers, student_name)
        if record_key:
            record_keys.append(record_key)
        if analysis_key:
            analysis_keys.append(analysis_key)

        if isinstance(record_paper, dict):
            page_records = _records_for_paper(record_paper)
            question_records.extend(page_records)
            page_wrong = [item for item in page_records if _is_wrong_record(item)]
            page_correct = [item for item in page_records if _is_correct_record(item)]
            wrong_records.extend(page_wrong)
            correct_records.extend(page_correct)
            for item in page_wrong:
                title = str(item.get("display_title") or item.get("question_key") or "").strip()
                if title:
                    wrong_titles.append(title)
            for item in page_correct:
                title = str(item.get("display_title") or item.get("question_key") or "").strip()
                if title:
                    correct_titles.append(title)

        if isinstance(analysis_paper, dict):
            analysis_items.extend(_analysis_items_for_paper(analysis_paper))

        for filename in grouped_filenames:
            if filename not in source_filenames:
                source_filenames.append(filename)
            default_item = default_history.get(filename) if isinstance(default_history, dict) else None
            manual_item = manual_history.get(filename) if isinstance(manual_history, dict) else None
            essay_item = essay_history.get(filename) if isinstance(essay_history, dict) else None

            for item in (default_item, manual_item, essay_item):
                score = _score_from_item(item if isinstance(item, dict) else {})
                if score is not None:
                    score_values.append(score)
                    break

            for item in (default_item, manual_item, essay_item):
                if isinstance(item, dict) and item.get("result"):
                    excerpts.append(f"[{Path(filename).stem}] {_safe_excerpt(item.get('result', ''), limit=600)}")
                    break

            if default_item:
                wrong_titles.extend(_wrong_titles_from_grading_result(default_item.get("result", "")))
            if manual_item:
                wrong_titles.extend(_wrong_titles_from_grading_result(manual_item.get("result", "")))

            if not image_url:
                file_path = correct_docs_dir() / folder_safe / filename
                if file_path.is_file():
                    image_url = _preview_url_for_file(folder_safe, filename)

        wrong_titles = list(dict.fromkeys(wrong_titles))
        correct_titles = list(dict.fromkeys(correct_titles))
        source_filenames = list(dict.fromkeys(source_filenames))

        result[student_name] = {
            "exam_name": exam_name,
            "folder_name": folder_safe,
            "filename": student_name,
            "source_filenames": source_filenames,
            "score": round(sum(score_values), 1) if score_values else None,
            "image_url": image_url,
            "grading_result_excerpt": _safe_excerpt("\n".join(excerpts), limit=1200),
            "paper_records": [_compact_question_record(item) for item in question_records[:120]],
            "correct_titles": correct_titles[:60],
            "wrong_titles": wrong_titles,
            "wrong_records": wrong_records[:60],
            "wrong_analysis": analysis_items[:60],
            "record_key": ",".join(dict.fromkeys(record_keys)),
            "analysis_key": ",".join(dict.fromkeys(analysis_keys)),
        }
    return result, ignored


def _student_report_to_dict(report: Optional[TargetedImprovementReport]) -> Optional[dict]:
    if not report:
        return None
    return {
        "id": report.id,
        "class_id": report.class_id,
        "student_id": report.student_id,
        "student_name": report.student_name,
        "student_number": report.student_number,
        "subject": report.subject,
        "diagnosis_text": report.diagnosis_text or "",
        "plan_text": report.plan_text or "",
        "diagnosis": _json_loads(report.diagnosis_json, {}),
        "plan": _json_loads(report.plan_json, {}),
        "source_summary": _json_loads(report.source_summary_json, {}),
        "exam_names": _json_loads(report.exam_names_json, []),
        "imported_folder_names": _json_loads(report.imported_folder_names_json, []),
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
        # E05 · AI 内容统一标识（GB 45438 隐式标识）读回
        "is_ai": bool(report.is_ai),
        "ai_meta": report.ai_meta,
    }


def _extract_subject_points(subject: str) -> str:
    s = subject or ""
    if "语文" in s:
        return "阅读理解、文言古诗、作文结构、语言表达、审题立意、基础字词"
    if "数学" in s:
        return "概念理解、运算准确性、几何推理、函数与方程、建模应用、审题转化"
    if "英语" in s:
        return "词汇语法、阅读理解、完形填空、书面表达、句法结构、语篇逻辑"
    if "科学" in s:
        return "科学探究、现象解释、实验设计、数据分析、科学概念原理"
    if "物理" in s:
        return "概念辨析、受力/电路/能量模型、公式选择、过程分析、实验探究"
    if "化学" in s:
        return "方程式、实验现象、物质推断、离子/氧化还原、计算与规范表达"
    if "生物" in s:
        return "概念网络、图表信息提取、遗传推理、实验设计、生态/调节过程"
    if "历史" in s:
        return "时空线索、史料解读、因果分析、阶段特征、观点论证"
    if "地理" in s:
        return "区域定位、图表判读、成因分析、人地关系、区位综合"
    if "政治" in s or "道德" in s:
        return "概念原理、材料提取、观点论证、时政迁移、规范作答"
    return "基础掌握、应用能力、综合分析、逻辑推理、表达规范"


# S2 学科特征值模型（app/services/subject_profiles.py）注入：
# 把「学科知识本质四分类配方 × 真实世界映像 × 最佳吸收皮」作为策略上下文喂给 AI，
# 让靶向提升建议更贴合学科本质（fact/rule/procedure/symbol 主导决定练习方式侧重）。
_NATURE_LABELS = {
    "fact": "事实记忆",
    "rule": "规律/概念理解",
    "procedure": "操作/程序技能",
    "symbol": "符号/语言形式",
}
# B 端学科命名与 S2 模型命名差异：targeted-improvement 用「政治」，模型配方用「道德与法治」
_SUBJECT_PROFILE_ALIASES = {"政治": "道德与法治"}


def _subject_profile_hint(subject: str) -> str:
    """S2 学科特征值模型 → 学科本质策略段（未知学科返回空串，不改变现有 prompt 行为）。"""
    try:
        from app.services.subject_profiles import get_profile
        profile = get_profile(_SUBJECT_PROFILE_ALIASES.get(subject, subject))
    except Exception:
        return ""
    dominant = max(profile.nature_recipe.items(), key=lambda kv: kv[1])[0]
    label = _NATURE_LABELS.get(dominant, dominant)
    recipe_str = "、".join(f"{k} {v:.3f}" for k, v in profile.nature_recipe.items())
    skins = "、".join(profile.absorption_skins) if profile.absorption_skins else "常规"
    return (
        f"学科知识本质策略：{subject}以「{label}」型知识为主导（四类占比 {recipe_str}），"
        f"真实世界映像方式为「{profile.real_world_image}」，最佳吸收皮为「{skins}」。"
        f"请让练习建议与教学语言贴合这一学科本质：练习方式侧重{label}类内容，"
        f"优先用「{skins}」方式呈现与训练。"
    )


def _prompt_for_subject(subject: str, student_payload: dict, class_payload: dict) -> str:
    focus = _extract_subject_points(subject)
    school_level = class_payload.get("school_level", "")
    grade = class_payload.get("grade", "")
    subject_strategy = _subject_profile_hint(subject)

    level_info = ""
    if school_level and grade:
        level_info = f"该学生当前学段为：{school_level}，年级为：{grade}。请确保所有分析、目标和教学语言符合该学段和年级学生的认知水平和学习要求。"

    return f"""
重要升级：学生数据中的 paper_records 来自 records 文件夹，包含该学生每张试卷的全部题目/作答区判定结果，不只是错题；wrong_analysis_summaries 来自 analysis 文件夹，只包含错题分析。
请同时分析“正确题目/稳定掌握部分”和“错误/未作答部分”，不能只写不足。优势表现必须依据 paper_records 中正确题目、得分趋势和批改摘要中的正向表现；薄弱点、根因和提升方案主要依据错题、未作答、错题分析和扣分原因。
请按真实数据比例权衡优点和不足：如果正确题较多，诊断要体现可迁移优势；如果错题集中，诊断要突出短板但仍保留正向反馈。
返回 JSON 的 diagnosis 中必须额外包含：
"strengths": ["优势表现1", "优势表现2"],
"positive_evidence": ["来自具体考试/正确题/批改摘要的正向证据，3-5条"],

你是一位经验丰富的一线{subject}教师和学习诊断专家。请基于真实批改数据，为学生生成“靶向提升”页面需要展示的内容。
{level_info}
{subject_strategy}

要求：
1. 只根据输入中的考试、批改结果、错题记录、错题分析、分数变化和试卷图片路径进行判断，不编造不存在的考试。
2. 学科诊断必须贴合{subject}特点，重点维度包括：{focus}。
3. 输出面向教师，语言简洁但内容充实，可直接用于教学跟进。
4. **完全基于错题生成知识点**：在制定薄弱点（weak_points）、根因（root_causes）和练习重点（practice_focus）时，**必须完全依照学生错题记录中的具体题目提取知识点**，不要生成与本次考试无关或者关联性很差的内容。
5. 必须返回合法 JSON，不要 markdown，不要代码块，不要额外解释。

返回 JSON 格式：
{{
  "diagnosis": {{
    "summary": "150字左右总体诊断，包含主要优缺点",
    "level": "当前层级或表现判断",
    "evidence": ["详细描述来自哪次考试/哪类错题的证据，3-6条"],
    "weak_points": ["薄弱点1", "薄弱点2，必须结合具体错题详细描述"],
    "root_causes": ["根因1", "根因2，结合错题分析详细推断"],
    "teacher_notes": ["教师课堂/面批关注点，详细建议，3-5条"]
  }},
  "plan": {{
    "goal": "2-4周可达成的具体、可衡量目标",
    "duration": "建议周期",
    "phases": [
      {{
        "title": "阶段名称",
        "period": "时间安排",
        "teacher_actions": ["教师要做什么（详细动作），2-4条"],
        "student_tasks": ["学生每日/每周任务（详细），2-4条"],
        "practice_focus": ["练习重点。⚠️必须从错题中提取，明确指明具体题型或知识点，2-4条"],
        "checkpoints": ["验收方式（可衡量），1-3条"]
      }}
    ],
    "daily_routine": ["日常执行建议，详细可操作，3-5条"],
    "follow_up": ["后续追踪建议，详细说明，2-4条"]
  }}
}}

班级概况：
{json.dumps(class_payload, ensure_ascii=False)}

学生数据：
{json.dumps(student_payload, ensure_ascii=False)}
""".strip()


def _parse_ai_json(text: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise
        data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("AI 返回不是 JSON 对象")
    return data


def _call_qwen_with_config(api_key: str, model: str, prompt: str) -> dict:
    if not api_key:
        raise ValueError("系统设置中未配置千问 API Key，无法生成靶向提升 AI 内容")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.35,
        **QWEN_CHAT_EXTRA_BODY,
    }
    try:
        import requests
        response = requests.post(
            f"{get_llm_base_url()}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=90,
        )
        res = response.json()
    except Exception as e:
        raise RuntimeError(f"调用千问模型失败: {e}") from e
    if response.status_code != 200 or res.get("error"):
        msg = (res.get("error") or {}).get("message") if isinstance(res.get("error"), dict) else str(res)
        raise RuntimeError(f"千问模型返回错误: {msg}")
    content = (res.get("choices") or [{}])[0].get("message", {}).get("content", "")
    try:
        data = _parse_ai_json(content)
    except Exception as e:
        raise RuntimeError(f"千问模型未按要求返回 JSON 格式数据，请重试。模型原始返回:\n{content[:200]}") from e
    data["_raw_content"] = content
    return data


def _call_qwen(prompt: str, db: Session) -> dict:
    _, api_key, model = get_llm_config(db)
    try:
        return _call_qwen_with_config(api_key, model, prompt)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _filter_redline_deep(data: Any) -> Any:
    """递归红线过滤：深滤嵌套 dict/list 中所有字符串值，返回新结构。

    结构保持：dict/list 递归进入，仅对 str 值应用 filter_text，
    其余类型（int/bool/None/float）原样返回，不原地修改输入。
    供靶向提升/能力诊断/班级学情等结构化 AI 输出出口复用。
    """
    if isinstance(data, str):
        return filter_text(data)
    if isinstance(data, dict):
        return {k: _filter_redline_deep(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_filter_redline_deep(item) for item in data]
    return data


def _generate_student_ai(api_key: str, model: str, student_name: str, prompt: str) -> tuple[str, Optional[dict], Optional[str]]:
    try:
        data = _call_qwen_with_config(api_key, model, prompt)
    except Exception as e:
        return student_name, None, str(e)
    # AI 输出红线词过滤：返回前深滤结构化文本（best-effort，过滤器异常不阻断单学生结果）
    try:
        data = _filter_redline_deep(data)
    except Exception:  # noqa: BLE001 - best-effort，红线过滤失败放行原文
        pass
    return student_name, data, None


def _compact_student_payload(student: Student, subject: str, exams: list[dict]) -> dict:
    scores = [x.get("score") for x in exams if isinstance(x.get("score"), (int, float))]
    wrong_titles = []
    correct_titles = []
    paper_records = []
    analysis_summaries = []
    image_urls = []
    for exam in exams:
        wrong_titles.extend(exam.get("wrong_titles") or [])
        correct_titles.extend(exam.get("correct_titles") or [])
        for item in exam.get("paper_records") or []:
            if isinstance(item, dict):
                paper_records.append({"exam_name": exam.get("exam_name"), **item})
        image_url = exam.get("image_url")
        if image_url:
            image_urls.append({"exam_name": exam.get("exam_name"), "image_url": image_url})
        for item in exam.get("wrong_analysis") or []:
            analysis = item.get("analysis") if isinstance(item, dict) else {}
            if isinstance(analysis, dict):
                text = analysis.get("summary") or analysis.get("diagnosis") or analysis.get("advice") or analysis.get("message")
                if text:
                    analysis_summaries.append(str(text))
            elif analysis:
                analysis_summaries.append(str(analysis))
    return {
        "student": _student_base(student),
        "subject": subject,
        "exam_count": len(exams),
        "scores": scores,
        "latest_score": scores[-1] if scores else None,
        "score_trend": round(scores[-1] - scores[0], 1) if len(scores) >= 2 else 0,
        "answer_area_count": len(paper_records),
        "correct_question_count": len([x for x in paper_records if _is_correct_record(x)]),
        "wrong_question_count": len(wrong_titles),
        "top_correct_titles": list(dict.fromkeys(correct_titles))[:25],
        "top_wrong_titles": list(dict.fromkeys(wrong_titles))[:25],
        "wrong_analysis_summaries": list(dict.fromkeys(analysis_summaries))[:20],
        "paper_images": image_urls[:10],
        "paper_records": paper_records[:120],
        "exams": [
            {
                "exam_name": e.get("exam_name"),
                "score": e.get("score"),
                "correct_titles": (e.get("correct_titles") or [])[:20],
                "wrong_titles": (e.get("wrong_titles") or [])[:20],
                "paper_records": (e.get("paper_records") or [])[:40],
                "grading_result_excerpt": e.get("grading_result_excerpt"),
            }
            for e in exams
        ],
    }


def _source_summary_from_payload(payload: dict) -> dict:
    return {
        "exam_count": payload.get("exam_count", 0),
        "latest_score": payload.get("latest_score"),
        "score_trend": payload.get("score_trend", 0),
        "answer_area_count": payload.get("answer_area_count", 0),
        "correct_question_count": payload.get("correct_question_count", 0),
        "wrong_question_count": payload.get("wrong_question_count", 0),
        "top_correct_titles": payload.get("top_correct_titles", []),
        "top_wrong_titles": payload.get("top_wrong_titles", []),
        "paper_images": payload.get("paper_images", []),
    }


def _upsert_report(
    db: Session,
    *,
    student: Student,
    subject: str,
    folders: list[str],
    payload: dict,
    ai_data: dict,
    model: Optional[str] = None,
) -> TargetedImprovementReport:
    diagnosis = ai_data.get("diagnosis") if isinstance(ai_data.get("diagnosis"), dict) else {}
    plan = ai_data.get("plan") if isinstance(ai_data.get("plan"), dict) else {}
    diagnosis_text = str(diagnosis.get("summary") or "").strip()
    plan_text = str(plan.get("goal") or "").strip()
    exam_names = [x.get("exam_name") for x in payload.get("exams", []) if x.get("exam_name")]
    report = db.query(TargetedImprovementReport).filter(
        TargetedImprovementReport.class_id == student.class_id,
        TargetedImprovementReport.student_name == student.name,
        TargetedImprovementReport.subject == subject,
    ).first()
    if not report:
        report = TargetedImprovementReport(
            class_id=student.class_id,
            student_id=student.id,
            student_name=student.name,
            subject=subject,
        )
        db.add(report)
    report.student_id = student.id
    report.student_number = student.student_number or ""
    report.diagnosis_text = diagnosis_text
    report.plan_text = plan_text
    report.diagnosis_json = _json_dumps(diagnosis)
    report.plan_json = _json_dumps(plan)
    report.source_summary_json = _json_dumps(_source_summary_from_payload(payload))
    report.exam_names_json = _json_dumps(exam_names)
    report.imported_folder_names_json = _json_dumps(folders)
    report.ai_raw_json = _json_dumps({k: v for k, v in ai_data.items() if k != "_raw_content"})
    # E05 · AI 内容统一标识（GB 45438 隐式标识）：靶向报告由 AI 生成，落库显式写 is_ai=1 + ai_meta
    report.is_ai = 1
    report.ai_meta = {"generator": AI_GENERATOR, "model": model}
    report.generated_at = datetime.now(timezone.utc)
    return report


@router.get("/subjects", response_model=ApiResponse[list])
def list_subjects(user_id: str = Depends(get_current_user_id)):
    return ApiResponse(data=SUBJECTS)


@router.get("/students", response_model=ApiResponse[dict])
def list_targeted_students(
    class_id: str = Query(...),
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    students = db.query(Student).filter(Student.class_id == class_id).all()
    students.sort(key=_student_sort_key)
    reports = db.query(TargetedImprovementReport).filter(
        TargetedImprovementReport.class_id == class_id,
        TargetedImprovementReport.subject == subject,
    ).all()
    reports_by_name = {r.student_name: r for r in reports}
    rec = db.query(TargetedRecommendation).filter(
        TargetedRecommendation.class_id == class_id,
        TargetedRecommendation.subject == subject,
    ).first()
    valid_names = {s.name for s in students}
    if rec:
        recommended_names = [n for n in _json_loads(rec.student_names_json, []) if n in valid_names][:5]
    else:
        recommended_names = [s.name for s in students[:5]]

    items = []
    for student in students:
        report = reports_by_name.get(student.name)
        source = _json_loads(report.source_summary_json, {}) if report else {}
        top_wrong = source.get("top_wrong_titles") if isinstance(source, dict) else []
        score = source.get("latest_score") if isinstance(source, dict) else None
        items.append({
            **_student_base(student),
            "current_score": score,
            "score_trend": source.get("score_trend", 0) if isinstance(source, dict) else 0,
            "wrong_question_count": source.get("wrong_question_count", 0) if isinstance(source, dict) else 0,
            "weak_points": top_wrong[:3] if isinstance(top_wrong, list) else [],
            "has_report": bool(report),
            "updated_at": report.updated_at.isoformat() if report and report.updated_at else None,
        })
    return ApiResponse(data={"students": items, "recommended_names": recommended_names})


@router.post("/recommendations", response_model=ApiResponse[dict])
def save_recommendations(
    body: RecommendationUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, body.class_id)
    valid_names = {
        s.name
        for s in db.query(Student).filter(Student.class_id == body.class_id).all()
    }
    names = []
    for name in body.student_names:
        n = str(name or "").strip()
        if n and n in valid_names and n not in names:
            names.append(n)
        if len(names) >= 5:
            break
    rec = db.query(TargetedRecommendation).filter(
        TargetedRecommendation.class_id == body.class_id,
        TargetedRecommendation.subject == body.subject,
    ).first()
    if not rec:
        rec = TargetedRecommendation(class_id=body.class_id, subject=body.subject, student_names_json="[]")
        db.add(rec)
    rec.student_names_json = _json_dumps(names)
    db.commit()
    return ApiResponse(data={"ok": True, "recommended_names": names})


@router.get("/report", response_model=ApiResponse[dict])
def get_report(
    class_id: str = Query(...),
    subject: str = Query(...),
    student_name: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    report = db.query(TargetedImprovementReport).filter(
        TargetedImprovementReport.class_id == class_id,
        TargetedImprovementReport.subject == subject,
        TargetedImprovementReport.student_name == student_name,
    ).first()
    return ApiResponse(data={"report": _student_report_to_dict(report)})


@router.get("/importable-exams", response_model=ApiResponse[list])
def list_importable_exams(
    class_id: str = Query(...),
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    prefix = _class_folder_prefix(class_id)
    if not prefix:
        return ApiResponse(data=[])
    folders = []
    try:
        candidates = [d.name for d in correct_docs_dir().iterdir() if d.is_dir() and d.name.startswith(prefix)]
    except Exception:
        candidates = []
    # 只返回当前科目的考试文件夹，避免「语文页面误选数学考试」导致科目错乱
    for safe in candidates:
        if subject and not safe.endswith(f"__{subject}"):
            continue
        count = _folder_completion_count(safe)
        if count <= 0:
            continue
        folders.append({
            "id": safe,
            "name": _display_folder_name(safe),
            "completed_count": count,
            "updated_at": _exam_mtime(safe),
        })
    folders.sort(key=lambda x: x.get("updated_at") or 0, reverse=True)
    return ApiResponse(data=folders)


@router.post("/import-exams", response_model=ApiResponse[dict])
def import_exams(
    body: ImportExamsRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, body.class_id)
    prefix = _class_folder_prefix(body.class_id)
    if not prefix:
        raise HTTPException(status_code=400, detail="班级ID无效")
    folder_names = [str(x or "").strip() for x in body.exam_folder_names if str(x or "").strip()]
    folder_names = list(dict.fromkeys(folder_names))
    if not folder_names:
        raise HTTPException(status_code=400, detail="请选择要导入的考试")
    invalid = [x for x in folder_names if not x.startswith(prefix) or not x.endswith(f"__{body.subject}")]
    if invalid:
        raise HTTPException(status_code=400, detail="存在不属于当前班级或科目的考试")

    students = db.query(Student).filter(Student.class_id == body.class_id).all()
    students.sort(key=_student_sort_key)
    students_by_name = {s.name: s for s in students}

    school_level = ""
    grade = ""
    try:
        from app.models.class_model import Class
        class_info = db.query(Class).filter(Class.id == body.class_id).first()
        school_level = class_info.school_level if class_info else ""
        grade = class_info.grade if class_info else ""
    except Exception:
        pass

    if not students_by_name:
        raise HTTPException(status_code=400, detail="当前班级暂无学生")

    student_exam_map: dict[str, list[dict]] = {}
    ignored_papers: list[dict] = []
    for safe in folder_names:
        collected, ignored = _collect_exam_data(safe, students_by_name)
        for name, payload in collected.items():
            student_exam_map.setdefault(name, []).append(payload)
        for filename in ignored:
            ignored_papers.append({"folder_name": safe, "filename": filename})

    if not student_exam_map:
        raise HTTPException(status_code=400, detail="选中的考试中没有找到以本班学生姓名命名的试卷")

    score_values = [
        x.get("score")
        for exams in student_exam_map.values()
        for x in exams
        if isinstance(x.get("score"), (int, float))
    ]
    class_payload = {
        "class_id": body.class_id,
        "subject": body.subject,
        "imported_exam_count": len(folder_names),
        "valid_student_count": len(student_exam_map),
        "class_avg_score": round(sum(score_values) / len(score_values), 1) if score_values else None,
        "school_level": school_level,
        "grade": grade,
    }

    generated = []
    failed = []
    # PII 匿名化：请求级映射，先登记全班真名，拼 prompt 前把学生数据里的姓名/文本匿名，
    # AI 返回后 restore 回真名再入库（入库 payload 保持真名，班级/学生页展示不受影响）。
    anon = Anonymizer()
    for student in students_by_name.values():
        anon.anon(student.name)
    work_items: list[tuple[Student, dict, str]] = []
    for student_name, exams in student_exam_map.items():
        student = students_by_name.get(student_name)
        if not student:
            continue
        payload = _compact_student_payload(student, body.subject, exams)
        prompt = _prompt_for_subject(body.subject, anon.anon_text_deep(payload), class_payload)
        work_items.append((student, payload, prompt))

    _, api_key, model = get_llm_config(db)
    if not api_key:
        raise HTTPException(status_code=500, detail="系统设置中未配置文本大模型 API Key，无法生成靶向提升 AI 内容")

    ai_results: dict[str, tuple[Optional[dict], Optional[str]]] = {}
    if work_items:
        with ThreadPoolExecutor(max_workers=TARGETED_IMPORT_WORKERS) as executor:
            futures = {
                executor.submit(_generate_student_ai, api_key, model, student.name, prompt): student.name
                for student, _, prompt in work_items
            }
            for future in as_completed(futures):
                name, ai_data, err = future.result()
                ai_results[name] = (ai_data, err)

    for student, payload, _ in work_items:
        ai_data, err = ai_results.get(student.name, (None, "未返回结果"))
        if err or not ai_data:
            failed.append({"student_name": student.name, "message": err or "AI 生成失败"})
            continue
        ai_data = anon.restore_deep(ai_data)
        try:
            report = _upsert_report(
                db,
                student=student,
                subject=body.subject,
                folders=folder_names,
                payload=payload,
                ai_data=ai_data,
                model=model,
            )
            generated.append({"student_name": student.name, "report_id": report.id})
        except Exception as e:
            failed.append({"student_name": student.name, "message": str(e)})

    if generated:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"保存靶向提升报告失败: {e}") from e
    elif failed:
        db.rollback()
        detail = failed[0]["message"] if failed else "AI生成失败"
        raise HTTPException(status_code=500, detail=detail)
    return ApiResponse(data={
        "ok": True,
        "generated_count": len(generated),
        "failed_count": len(failed),
        "ignored_count": len(ignored_papers),
        "generated": generated,
        "failed": failed,
        "ignored_papers": ignored_papers[:50],
    })


# ── 🟡 学情驱动内容推荐闭环（评价 → 内容 → 再评价）────────────────────────────
# 内容推荐：TargetedImprovementReport.source_summary_json 弱项知识点 → KnowledgePoint(related/is_weak)
# → TeachingResource(detected_subject/difficulty/tags) 匹配，按 subject 过滤，每组最多 3 条；无匹配返回空数组。
# 再评价：复用 run_ai_diagnosis 对同一学生再跑二次诊断，返回 before(原 diagnosis_json)/after(新诊断) 对比。


class ReEvaluateRequest(BaseModel):
    class_id: str
    student_id: str
    subject: str


def _weak_point_keywords(source_summary: dict) -> list[str]:
    """从 source_summary_json 提取弱项知识点关键词（优先错题标题列表）。"""
    keywords: list[str] = []
    for key in ("top_wrong_titles", "weak_points", "weak_knowledge_points"):
        value = source_summary.get(key)
        if isinstance(value, list):
            for item in value:
                text = str(item or "").strip()
                if text and text not in keywords:
                    keywords.append(text)
    return keywords


def _term_matches(kw: str, term: str) -> bool:
    """双向子串匹配：知识点名/相关名与关键词互相包含即可命中。"""
    kw_l = str(kw or "").strip().lower()
    t_l = str(term or "").strip().lower()
    if not kw_l or not t_l:
        return False
    return t_l in kw_l or kw_l in t_l


def _kp_search_terms(kp: KnowledgePoint) -> list[str]:
    terms = [str(kp.name or ""), str(kp.code or "")]
    if isinstance(kp.related, list):
        terms.extend(str(x or "") for x in kp.related)
    return [t for t in terms if str(t or "").strip()]


def _match_knowledge_points(db: Session, keywords: list[str], limit: int = 8) -> list[KnowledgePoint]:
    """弱项关键词 → KnowledgePoint（name/code/related 匹配，优先 is_weak 与低掌握度）。"""
    if not keywords:
        return []
    candidates = db.query(KnowledgePoint).order_by(KnowledgePoint.mastery.asc()).limit(300).all()
    matched: list[KnowledgePoint] = []
    seen: set[str] = set()
    for kw in keywords:
        for kp in candidates:
            if kp.id in seen:
                continue
            if any(_term_matches(kw, term) for term in _kp_search_terms(kp)):
                matched.append(kp)
                seen.add(kp.id)
                if len(matched) >= limit:
                    return matched
    # 关键词无命中时兜底：取 is_weak=True 的薄弱知识点
    if not matched:
        matched = [kp for kp in candidates if kp.is_weak][:limit]
    return matched


def _resource_dict(resource: TeachingResource) -> dict:
    return {
        "id": resource.id,
        "title": resource.title,
        "description": resource.description or "",
        "type": resource.type,
        "file_url": resource.file_url,
        "file_name": resource.file_name,
        "difficulty": resource.difficulty,
        "knowledge_point_count": resource.knowledge_point_count,
        "question_count": resource.question_count,
        "detected_subject": resource.detected_subject,
        "detected_unit": resource.detected_unit,
        "tags": resource.tags if isinstance(resource.tags, list) else [],
    }


def _resource_matches_kp(resource: TeachingResource, kp: KnowledgePoint) -> bool:
    """教学资源与知识点匹配：title/detected_unit/description/tags 任一包含知识点名称或相关知识点。"""
    terms = _kp_search_terms(kp)
    if not terms:
        return False
    hay = " ".join(
        [
            str(resource.title or ""),
            str(resource.detected_unit or ""),
            str(resource.description or ""),
            " ".join(str(x or "") for x in (resource.tags or [])),
        ]
    ).lower()
    return any(_term_matches(hay, term) for term in terms)


def _find_student_report(db: Session, class_id: str, student_id: str, student_name: str, subject: str):
    return db.query(TargetedImprovementReport).filter(
        TargetedImprovementReport.class_id == class_id,
        TargetedImprovementReport.subject == subject,
        or_(
            TargetedImprovementReport.student_id == student_id,
            TargetedImprovementReport.student_name == student_name,
        ),
    ).first()


@router.get("/recommendations/content", response_model=ApiResponse[list])
def get_recommendation_content(
    class_id: str = Query(...),
    subject: str = Query(...),
    student_id: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """弱项知识点 → 知识点 → 教学资源映射；按 subject 过滤，每组最多 3 条；无匹配返回空数组。"""
    _assert_class_access(db, user_id, class_id)
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.class_id == class_id,
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    report = _find_student_report(db, class_id, student_id, student.name, subject)
    if not report:
        return ApiResponse(data=[])
    keywords = _weak_point_keywords(_json_loads(report.source_summary_json, {}))
    if not keywords:
        return ApiResponse(data=[])
    knowledge_points = _match_knowledge_points(db, keywords)
    if not knowledge_points:
        return ApiResponse(data=[])
    resources = (
        db.query(TeachingResource)
        .filter(TeachingResource.detected_subject == subject)
        .order_by(TeachingResource.created_at.desc())
        .limit(200)
        .all()
    )
    groups: list[dict] = []
    for kp in knowledge_points:
        group_resources: list[dict] = []
        for resource in resources:
            if len(group_resources) >= 3:
                break
            if _resource_matches_kp(resource, kp):
                group_resources.append(_resource_dict(resource))
        if group_resources:
            groups.append({
                "knowledge_point_id": kp.id,
                "knowledge_point_name": kp.name,
                "code": kp.code,
                "is_weak": bool(kp.is_weak),
                "mastery": kp.mastery,
                "related": kp.related if isinstance(kp.related, list) else [],
                "resources": group_resources,
            })
    return ApiResponse(data=groups)


@router.post("/re-evaluate", response_model=ApiResponse[dict])
def re_evaluate_diagnosis(
    body: ReEvaluateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """复用 run_ai_diagnosis 对同一学生再跑二次诊断，返回 before(原 diagnosis_json)/after(新诊断) 对比。"""
    _assert_class_access(db, user_id, body.class_id)
    student = db.query(Student).filter(
        Student.id == body.student_id,
        Student.class_id == body.class_id,
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="学生不存在")
    report = _find_student_report(db, body.class_id, body.student_id, student.name, body.subject)
    before = _json_loads(report.diagnosis_json, {}) if report else {}
    # 复用 /ai-diagnosis 的 run_ai_diagnosis（内部含 PII 匿名化与错题采集），对同一学生再跑一次
    from app.routers.student_analysis import run_ai_diagnosis
    from app.schemas.student_analysis import AIDiagnosisRequest
    result = run_ai_diagnosis(
        AIDiagnosisRequest(
            class_id=body.class_id,
            student_name=student.name,
            subject=body.subject,
        ),
        user_id=user_id,
        db=db,
    )
    return ApiResponse(data={
        "class_id": body.class_id,
        "student_id": body.student_id,
        "student_name": student.name,
        "subject": body.subject,
        "before": before,
        "after": result.data,
    })


# ── 个性化学习任务清单（客户功能 #15 闭环：勾完成 / 进度跟踪）────────────────
# 从报告 plan_json 抽 dailyTasks / student_tasks → TargetedImprovementTask 持久化；
# sync 幂等（同一 report 重复 sync 不重复建行），PATCH 勾/取消，列表带 total/done 计数。


def _normalize_task_text(value: Any) -> str:
    s = str(value or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _task_rows_from_text_list(items: Any, stage_label: Optional[str], start_order: int) -> list[dict]:
    rows: list[dict] = []
    order = start_order
    for item in items if isinstance(items, list) else []:
        text = _normalize_task_text(item)
        if not text:
            continue
        rows.append({"task_text": text, "stage_label": stage_label or "", "sort_order": order})
        order += 1
    return rows


def _extract_tasks_from_plan(plan: Any) -> list[dict]:
    """plan_json → 任务行候选（task_text / stage_label / sort_order）。

    兼容真实 AI 输出（phases[].student_tasks）与前端 demo 结构（stages[].dailyTasks），
    以及 plan.daily_routine 日常执行建议；同文去重，保持出现顺序。
    """
    if not isinstance(plan, dict):
        return []
    collected: list[dict] = []
    seen: set[str] = set()

    def _push(rows: list[dict]) -> None:
        for row in rows:
            key = row["task_text"]
            if key in seen:
                continue
            seen.add(key)
            row["sort_order"] = len(collected)
            collected.append(row)

    # AI 方案分阶段：phases[].student_tasks（prompt 契约）+ 兼容 dailyTasks/daily_tasks
    for idx, phase in enumerate(plan.get("phases") or []):
        if not isinstance(phase, dict):
            continue
        stage_label = _normalize_task_text(phase.get("title") or phase.get("name") or f"阶段{idx + 1}")
        tasks_src = (
            phase.get("student_tasks")
            or phase.get("studentTasks")
            or phase.get("dailyTasks")
            or phase.get("daily_tasks")
            or []
        )
        _push(_task_rows_from_text_list(tasks_src, stage_label, len(collected)))

    # 前端 demo / 旧结构：stages[].dailyTasks
    for idx, stage in enumerate(plan.get("stages") or []):
        if not isinstance(stage, dict):
            continue
        stage_label = _normalize_task_text(stage.get("name") or stage.get("title") or f"阶段{idx + 1}")
        tasks_src = stage.get("dailyTasks") or stage.get("daily_tasks") or stage.get("student_tasks") or []
        _push(_task_rows_from_text_list(tasks_src, stage_label, len(collected)))

    # 日常执行建议一并入清单（阶段标签「日常」）
    daily_routine = plan.get("daily_routine") or plan.get("dailyRoutine") or []
    _push(_task_rows_from_text_list(daily_routine, "日常", len(collected)))
    return collected


def _task_to_dict(task: TargetedImprovementTask) -> dict:
    return {
        "id": task.id,
        "class_id": task.class_id,
        "student_id": task.student_id,
        "student_name": task.student_name,
        "subject": task.subject,
        "report_id": task.report_id,
        "task_text": task.task_text or "",
        "stage_label": task.stage_label or "",
        "sort_order": task.sort_order or 0,
        "is_done": bool(task.is_done),
        "done_at": task.done_at.isoformat() if task.done_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _resolve_sync_report(db: Session, body: TaskSyncRequest) -> TargetedImprovementReport:
    if body.report_id:
        report = db.query(TargetedImprovementReport).filter(
            TargetedImprovementReport.id == body.report_id
        ).first()
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")
        return report
    if not body.class_id or not body.subject:
        raise HTTPException(status_code=400, detail="请提供 report_id 或 class_id+subject")
    query = db.query(TargetedImprovementReport).filter(
        TargetedImprovementReport.class_id == body.class_id,
        TargetedImprovementReport.subject == body.subject,
    )
    if body.student_id:
        query = query.filter(TargetedImprovementReport.student_id == body.student_id)
    if body.student_name:
        query = query.filter(TargetedImprovementReport.student_name == body.student_name)
    report = query.order_by(TargetedImprovementReport.generated_at.desc()).first()
    if not report:
        raise HTTPException(status_code=404, detail="未找到可导入的靶向报告")
    return report


@router.post("/tasks/sync", response_model=ApiResponse[dict])
def sync_improvement_tasks(
    body: TaskSyncRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """从报告 plan_json 同步任务清单（幂等：同一 report+task_text 不重复建行）。"""
    report = _resolve_sync_report(db, body)
    _assert_class_access(db, user_id, report.class_id)
    plan = _json_loads(report.plan_json, {})
    candidates = _extract_tasks_from_plan(plan)

    existing = db.query(TargetedImprovementTask).filter(
        TargetedImprovementTask.class_id == report.class_id,
        TargetedImprovementTask.student_name == report.student_name,
        TargetedImprovementTask.subject == report.subject,
    ).all()
    # 幂等键：优先按 report_id+task_text；历史行 report_id 为空时退化为同学生同科 task_text
    existing_keys = set()
    for row in existing:
        existing_keys.add((row.report_id or "", _normalize_task_text(row.task_text)))
        if not row.report_id:
            existing_keys.add(("", _normalize_task_text(row.task_text)))

    created = 0
    skipped = 0
    for item in candidates:
        key = (report.id or "", item["task_text"])
        fallback_key = ("", item["task_text"])
        if key in existing_keys or fallback_key in existing_keys:
            skipped += 1
            continue
        task = TargetedImprovementTask(
            class_id=report.class_id,
            student_id=report.student_id,
            student_name=report.student_name,
            subject=report.subject,
            report_id=report.id,
            task_text=item["task_text"],
            stage_label=item.get("stage_label") or "",
            sort_order=item.get("sort_order") or 0,
            is_done=False,
        )
        db.add(task)
        existing_keys.add(key)
        created += 1

    if created:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"保存任务清单失败: {e}") from e

    rows = (
        db.query(TargetedImprovementTask)
        .filter(
            TargetedImprovementTask.class_id == report.class_id,
            TargetedImprovementTask.student_name == report.student_name,
            TargetedImprovementTask.subject == report.subject,
        )
        .order_by(TargetedImprovementTask.sort_order.asc(), TargetedImprovementTask.created_at.asc())
        .all()
    )
    done_count = sum(1 for r in rows if r.is_done)
    return ApiResponse(data={
        "ok": True,
        "report_id": report.id,
        "created_count": created,
        "skipped_count": skipped,
        "total": len(rows),
        "done": done_count,
        "tasks": [_task_to_dict(r) for r in rows],
    })


@router.get("/tasks", response_model=ApiResponse[dict])
def list_improvement_tasks(
    class_id: str = Query(...),
    subject: str = Query(...),
    student_id: Optional[str] = None,
    student_name: Optional[str] = None,
    include_done: bool = True,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """列任务：按班级/科目/学生筛选，响应带 total/done 进度计数（全量计数，不受 include_done 影响）。"""
    _assert_class_access(db, user_id, class_id)
    base = db.query(TargetedImprovementTask).filter(
        TargetedImprovementTask.class_id == class_id,
        TargetedImprovementTask.subject == subject,
    )
    if student_id:
        base = base.filter(TargetedImprovementTask.student_id == student_id)
    if student_name:
        base = base.filter(TargetedImprovementTask.student_name == student_name)

    all_rows = base.order_by(
        TargetedImprovementTask.sort_order.asc(),
        TargetedImprovementTask.created_at.asc(),
    ).all()
    total = len(all_rows)
    done_count = sum(1 for r in all_rows if r.is_done)
    if include_done is False:
        rows = [r for r in all_rows if not r.is_done]
    else:
        rows = all_rows
    return ApiResponse(data={
        "tasks": [_task_to_dict(r) for r in rows],
        "total": total,
        "done": done_count,
    })


@router.patch("/tasks/{task_id}", response_model=ApiResponse[dict])
def update_improvement_task(
    task_id: str,
    body: TaskUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """勾/取消任务完成状态；勾选时写 done_at，取消时清空。"""
    task = db.query(TargetedImprovementTask).filter(
        TargetedImprovementTask.id == task_id
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    _assert_class_access(db, user_id, task.class_id)
    task.is_done = bool(body.is_done)
    task.done_at = datetime.now(timezone.utc) if task.is_done else None
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新任务状态失败: {e}") from e
    return ApiResponse(data=_task_to_dict(task))
