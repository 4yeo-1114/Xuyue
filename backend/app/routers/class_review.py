import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.class_review import ClassReviewSession
from app.models.student import Student
from app.schemas.common import ApiResponse
from app.utils.anonymize import Anonymizer
from app.utils.qwen_settings import AI_GENERATOR, QWEN_CHAT_EXTRA_BODY, get_llm_config
from app.routers.targeted_improvement import (
    SUBJECTS,
    _class_folder_prefix,
    _collect_exam_data,
    _ct_paper_student_name,
    _display_folder_name,
    _exam_mtime,
    _folder_completion_count,
    _json_dumps,
    _json_loads,
    _paper_stem,
    _read_wrong_jsons,
    _student_sort_key,
)
from app.dependencies import bind_grading_user_context, get_current_user_id
from app.services.ai_policy import assert_no_sensitive_input, require_ai_access
from app.grading.user_paths import correct_docs_dir
from app.utils.class_access import can_view_class

router = APIRouter(
    prefix="/class-review",
    tags=["class_review"],
    dependencies=[Depends(bind_grading_user_context)],
)


class ImportReviewExamsRequest(BaseModel):
    class_id: str
    subject: str
    exam_folder_names: list[str]


class PostClassFeedbackRequest(BaseModel):
    class_id: str
    subject: str
    taught_points: list[str] = []
    mastered_points: list[str] = []
    unresolved_points: list[str] = []
    overall_effect: str = ""
    teacher_notes: str = ""


def _assert_class_access(db: Session, user_id: str, class_id: str) -> None:
    """校验调用者对目标班级有访问权限（教师=所带班级，班主任/副班主任=本班，系统管理员/校级管理者/年级组长=全校），否则 403。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=403, detail="forbidden: 无该班级访问权限")


def _register_class_students(anon: Anonymizer, db: Session, class_id: str) -> None:
    """把班级全部学生真名登记进 Anonymizer，使 anon_text 能覆盖任意文本中出现的姓名。"""
    rows = db.query(Student.name).filter(Student.class_id == class_id).all()
    for (name,) in rows:
        anon.anon(name or "")


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


def _call_qwen(prompt: str, db: Session, *, temperature: float = 0.35) -> dict:
    base_url, api_key, model = get_llm_config(db)
    if not api_key:
        raise HTTPException(status_code=500, detail="系统设置中未配置文本大模型 API Key，无法生成课堂讲评内容")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        **QWEN_CHAT_EXTRA_BODY,
    }
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=120,
        )
        res = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"调用千问模型失败: {e}")
    if response.status_code != 200 or res.get("error"):
        msg = (res.get("error") or {}).get("message") if isinstance(res.get("error"), dict) else str(res)
        raise HTTPException(status_code=500, detail=f"千问模型返回错误: {msg}")
    content = (res.get("choices") or [{}])[0].get("message", {}).get("content", "")
    try:
        data = _parse_ai_json(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"千问模型未按要求返回 JSON 格式数据，请重试。模型原始返回:\n{content[:200]}")
    data["_raw_content"] = content
    return data


def _session_to_dict(row: Optional[ClassReviewSession]) -> Optional[dict]:
    if not row:
        return None
    return {
        "id": row.id,
        "class_id": row.class_id,
        "subject": row.subject,
        "title": row.title or "",
        "exam_names": _json_loads(row.exam_names_json, []),
        "imported_folder_names": _json_loads(row.imported_folder_names_json, []),
        "source_summary": _json_loads(row.source_summary_json, {}),
        "pre_class": _json_loads(row.pre_class_json, {}),
        "tracking": _json_loads(row.tracking_json, {}),
        "consolidation": _json_loads(row.consolidation_json, {}),
        "post_feedback": _json_loads(row.post_feedback_json, {}),
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        # E05 · AI 内容统一标识（GB 45438 隐式标识）读回
        "is_ai": bool(row.is_ai),
        "ai_meta": row.ai_meta,
    }


def _status_code(item: dict) -> int:
    try:
        return int(item.get("status_code"))
    except Exception:
        return -1


def _title_of(item: dict) -> str:
    return str(item.get("display_title") or item.get("question_key") or "").strip()


def _compact_records(records: list[dict], limit: int = 260) -> list[dict]:
    out = []
    for item in records[:limit]:
        out.append({
            "exam_name": item.get("exam_name"),
            "student_name": item.get("student_name"),
            "display_title": item.get("display_title"),
            "status": item.get("status"),
            "status_code": item.get("status_code"),
            "question_type": item.get("question_type"),
            "reason": item.get("reason"),
            "comment": item.get("comment"),
        })
    return out


def _records_incomplete(folder_names: list[str]) -> Optional[tuple[int, int]]:
    """检查错题记录是否已生成完整。

    批改完成标记（grading_history 的 completed）会先于错题记录（ct/records）异步落盘。
    自动推送若在记录尚未写全时导入，会出现「有效学生 N 但每题仅 M 人作答、准确率异常」。
    只有 AI 批改（智能/参照答案批改，default 历史）会产错题记录；自主阅卷系
    （manual/manual_reference/manual_paper 共用 __manual.json）和作文批改（__essay.json）
    根本不产记录——这两类不计入分母，否则导入永远卡在「批改记录仍在生成中」。
    返回 (completed, recorded) 表示 recorded < completed（记录未全），None 表示已完整。
    """
    from app.grading.router import _read_grading_history

    completed_total = 0
    recorded_total = 0
    for safe in folder_names:
        names: set[str] = set()
        data = _read_grading_history(safe, "default")
        comp = data.get("completed")
        if isinstance(comp, dict):
            for filename in comp.keys():
                names.add(_paper_stem(str(filename)))
        completed_total += len(names)

        records, _ = _read_wrong_jsons(safe)
        papers = records.get("papers")
        rec_names: set[str] = set()
        if isinstance(papers, dict):
            for paper_key, paper in papers.items():
                if not isinstance(paper, dict):
                    continue
                rec_names.add(_ct_paper_student_name(str(paper_key), paper))
        recorded_total += len(rec_names)

    if recorded_total < completed_total:
        return completed_total, recorded_total
    return None


def _aggregate_payload(class_id: str, subject: str, folder_names: list[str], db: Session) -> tuple[dict, list[str]]:
    students = db.query(Student).filter(Student.class_id == class_id).all()
    students.sort(key=_student_sort_key)
    students_by_name = {s.name: s for s in students}
    
    school_level = ""
    grade = ""
    try:
        from app.models.class_model import Class
        class_info = db.query(Class).filter(Class.id == class_id).first()
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

    all_records: list[dict] = []
    wrong_analysis = []
    scores = []
    exam_names = []
    for student_name, exams in student_exam_map.items():
        for exam in exams:
            if exam.get("exam_name") and exam.get("exam_name") not in exam_names:
                exam_names.append(exam.get("exam_name"))
            if isinstance(exam.get("score"), (int, float)):
                scores.append(exam.get("score"))
            for record in exam.get("paper_records") or []:
                if isinstance(record, dict):
                    all_records.append({"student_name": student_name, "exam_name": exam.get("exam_name"), **record})
            for item in exam.get("wrong_analysis") or []:
                if isinstance(item, dict):
                    wrong_analysis.append({"student_name": student_name, "exam_name": exam.get("exam_name"), **item})

    # 错题原题文字（question_text）：从 VLM 错题分析按大题聚合，供「课堂讲评」点开每题直接展示原题，不再依赖截图。
    # 键归一化与下面 question_accuracy 的 display_title 一致（去掉不稳定的「-作答区Y」后缀）。
    question_text_map: dict[str, str] = {}
    for item in wrong_analysis:
        raw_title = str(item.get("display_title") or item.get("question_key") or "").strip()
        big_title = raw_title.split("-作答区")[0] if "-作答区" in raw_title else raw_title
        analysis = item.get("analysis") if isinstance(item.get("analysis"), dict) else {}
        qt = str(analysis.get("question_text") or "").strip()
        if big_title and qt and big_title not in question_text_map:
            question_text_map[big_title] = qt

    # 两步聚合（按大题，避免"作答区编号不稳定"把同一题拆散）：
    #   1) 先按「大题 × 学生」汇总该生在该大题各作答区的对/错/空数量与错因；
    #   2) 再按大题把每个学生归为「对/错/空」三类之一，得到学生级统计（作答人数=学生数）。
    # display_title 形如"第X题-作答区Y"，"作答区Y"由识别产生、编号不稳，故聚合键取"第X题"。
    student_question_map: dict[str, dict[str, dict]] = {}
    for record in all_records:
        display_title = str(record.get("display_title") or "").strip()
        big_title = display_title.split("-作答区")[0] if "-作答区" in display_title else display_title
        key = big_title or str(record.get("question_key") or "").strip()
        if not key:
            continue
        student_name = record.get("student_name") or ""
        slot = student_question_map.setdefault(key, {}).setdefault(student_name, {
            "correct": 0,
            "wrong": 0,
            "blank": 0,
            "ungraded": 0,
            "reasons": {},
            "question_key": record.get("question_key") or key,
            "display_title": big_title or display_title or key,
        })
        code = _status_code(record)
        if code == 1:
            slot["correct"] += 1
        elif code == 2:
            slot["wrong"] += 1
        elif code == 3:
            slot["blank"] += 1
        else:
            slot["ungraded"] += 1
        reason = str(record.get("reason") or record.get("comment") or "").strip()
        if reason:
            slot["reasons"][reason] = slot["reasons"].get(reason, 0) + 1

    question_stats: dict[str, dict] = {}
    # 「点准确率看名单」：每题按学生归类为对/错/空/未评，存真实姓名（只落库回前端，不发 LLM）。
    question_students: dict[str, dict] = {}
    for key, students in student_question_map.items():
        first = next(iter(students.values()))
        stat = {
            "question_key": first.get("question_key") or key,
            "display_title": first.get("display_title") or key,
            "correct_count": 0,
            "wrong_count": 0,
            "blank_count": 0,
            "ungraded_count": 0,
            "reasons": {},
        }
        by_result = {"correct": [], "wrong": [], "blank": [], "ungraded": []}
        for student_name, slot in students.items():
            # 该生在这道大题上的归类：有错→错；全空→空；有对→对；否则→未评
            if slot["wrong"] > 0:
                stat["wrong_count"] += 1
                by_result["wrong"].append(student_name)
            elif slot["blank"] > 0 and slot["correct"] == 0:
                stat["blank_count"] += 1
                by_result["blank"].append(student_name)
            elif slot["correct"] > 0:
                stat["correct_count"] += 1
                by_result["correct"].append(student_name)
            else:
                stat["ungraded_count"] += 1
                by_result["ungraded"].append(student_name)
            for r, c in slot["reasons"].items():
                stat["reasons"][r] = stat["reasons"].get(r, 0) + c
        question_stats[key] = stat
        for _k in ("correct", "wrong", "blank", "ungraded"):
            by_result[_k].sort()
        question_students[stat.get("question_key") or key] = {
            "display_title": stat["display_title"],
            "correct_students": by_result["correct"],
            "wrong_students": by_result["wrong"],
            "blank_students": by_result["blank"],
            "ungraded_students": by_result["ungraded"],
        }
    # 精简每个统计项的错因集合：reason 文本截 80 字、只保留最高频 5 条。
    # high_risk/strong/question_accuracy 复用同一份 reasons，避免大量长评语撑大聚合统计和 prompt。
    for stat in question_stats.values():
        reasons = stat.get("reasons") or {}
        stat["reasons"] = {
            (r[:80] + "…") if len(r) > 80 else r: c
            for r, c in sorted(reasons.items(), key=lambda kv: -kv[1])[:5]
        }

    high_risk_questions = sorted(
        question_stats.values(),
        key=lambda x: (x.get("wrong_count", 0) + x.get("blank_count", 0), x.get("wrong_count", 0)),
        reverse=True,
    )[:15]
    strong_questions = sorted(
        question_stats.values(),
        key=lambda x: x.get("correct_count", 0),
        reverse=True,
    )[:12]

    # 每道题的准确率统计（完整列表，供「课堂讲评」页展示每题正确率）
    question_accuracy = []
    for stat in question_stats.values():
        correct = int(stat.get("correct_count", 0))
        wrong = int(stat.get("wrong_count", 0))
        blank = int(stat.get("blank_count", 0))
        total = correct + wrong + blank
        accuracy = round(correct / total * 100, 1) if total else 0.0
        reasons = stat.get("reasons") or {}
        # 每题最高频的典型错因（去学生个体，仅保留错因要点与次数），供大模型提取 error_patterns。
        # 错因文本截断到 80 字：个别长评语会成倍撑大聚合统计，课堂讲评只需错因要点即可。
        top_reasons = [
            {"reason": (r[:80] + "…") if len(r) > 80 else r, "count": c}
            for r, c in sorted(reasons.items(), key=lambda kv: -kv[1])[:5]
        ]
        question_accuracy.append({
            "question_key": stat.get("question_key", ""),
            "display_title": stat.get("display_title", ""),
            "question_text": question_text_map.get(stat.get("display_title", ""), ""),
            "correct_count": correct,
            "wrong_count": wrong,
            "blank_count": blank,
            "total": total,
            "accuracy": accuracy,
            "top_reasons": top_reasons,
        })
    # 正确率从低到高排序（最薄弱题目靠前，便于讲评时优先关注）
    question_accuracy.sort(key=lambda x: (x["accuracy"], -x["total"]))

    # 统分题号 + 原题：读统分时保存的 question_structure（第N题 → {major, sub, sub_sub, question_text}），
    # 把「第N题」映射成老师统分时的题号（如「三、2」「二」），并把题干原文（原题）补进题目条目。
    # 不再单独跑一遍视觉识别去猜题号，避免「自作主张」按作答区/顺序号排列，题号与统分保持一致。
    structure_map: dict[str, dict] = {}
    try:
        from app.grading.router import _read_grading_history

        for _safe in folder_names:
            for _engine in ("default", "manual"):
                try:
                    _got = _read_grading_history(_safe, _engine).get("question_structure")
                except Exception:
                    _got = None
                if isinstance(_got, dict) and _got:
                    structure_map = _got
                    break
            if structure_map:
                break
    except Exception:
        structure_map = {}

    def _tongfen_number(major: str, sub: str, sub_sub: str) -> str:
        major = (major or "").strip()
        sub = (sub or "").strip()
        sub_sub = (sub_sub or "").strip()
        if not major:
            return ""
        # 作文/表达题常把大题号重复放进 sub（如 四/四），去掉冗余，只保留大题号
        if sub and sub == major:
            sub = ""
        if sub_sub:
            return f"{major}、{sub}（{sub_sub}）" if sub else f"{major}（{sub_sub}）"
        if sub:
            return f"{major}、{sub}"
        return major

    # 归一化「第N题」的题号：容忍中文/阿拉伯数字与空白差异。统分结构（question_structure）
    # 的键来自批改结果文本的「第N题」，而课堂讲评的 display_title 来自 VLM 记录的
    # 第{display_index}题，两者格式偶有出入（如「第一题」vs「第1题」），直接用字符串匹配
    # 会落空导致 real_number 为空、前端回退到自编题号。这里先转成整数题号再匹配。
    _CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                  "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

    def _cn_to_int(s: str):
        s = (s or "").strip()
        if not s:
            return None
        if s.isdigit():
            return int(s)
        if "十" in s:
            left, right = s.split("十", 1)
            tens = _CN_DIGITS.get(left) if left else 1
            if tens is None:
                return None
            ones = _CN_DIGITS.get(right) if right else 0
            if ones is None:
                return None
            return tens * 10 + ones
        if len(s) == 1 and s in _CN_DIGITS:
            return _CN_DIGITS[s]
        return None

    def _question_no(title: str):
        t = (title or "").strip()
        m = re.match(r"^第(.+?)题$", t)
        if not m:
            return None
        body = re.sub(r"[\s（）()]", "", m.group(1))
        return _cn_to_int(body)

    norm_structure_map: dict[int, dict] = {}
    for _k, _v in structure_map.items():
        _n = _question_no(_k)
        if _n is not None and _n not in norm_structure_map:
            norm_structure_map[_n] = _v

    for _qa in question_accuracy:
        _key = str(_qa.get("display_title") or _qa.get("question_key") or "")
        _info = structure_map.get(_key)
        if not isinstance(_info, dict):
            _n = _question_no(_key)
            if _n is not None:
                _info = norm_structure_map.get(_n)
        if not isinstance(_info, dict):
            continue
        _num = _tongfen_number(
            _info.get("major", ""), _info.get("sub", ""), _info.get("sub_sub", "")
        )
        if _num:
            _qa["real_number"] = _num
        _qt = str(_info.get("question_text") or "").strip()
        if _qt and not _qa.get("question_text"):
            _qa["question_text"] = _qt

    # Process all wrong question images for frontend "错题关联" feature
    from app.grading.wrong_question_db import collect_wrong_question_images

    all_wrong_images = collect_wrong_question_images(folder_names)

    payload = {
        "school_level": school_level,
        "grade": grade,
        "class_id": class_id,
        "subject": subject,
        "exam_names": exam_names,
        "imported_folder_names": folder_names,
        "valid_student_count": len(student_exam_map),
        "class_avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "score_count": len(scores),
        "answer_area_count": len(all_records),
        "correct_count": sum(1 for x in all_records if _status_code(x) == 1),
        "wrong_count": sum(1 for x in all_records if _status_code(x) == 2),
        "blank_count": sum(1 for x in all_records if _status_code(x) == 3),
        "high_risk_questions": high_risk_questions,
        "strong_questions": strong_questions,
        "question_accuracy": question_accuracy,
        "question_students": question_students,
        "wrong_analysis": wrong_analysis[:120],
        "paper_records": _compact_records(all_records),
        "ignored_papers": ignored_papers[:80],
        "all_wrong_images": all_wrong_images,
    }
    return payload, ignored_papers


def _subject_focus(subject: str) -> str:
    s = subject or ""
    if "语文" in s:
        return "阅读理解、文言古诗、作文立意与结构、语言表达、审题与文本证据"
    if "数学" in s:
        return "概念理解、运算准确性、几何推理、函数方程、建模应用、审题转化"
    if "英语" in s:
        return "词汇语法、阅读理解、完形填空、书面表达、句法结构、语篇逻辑"
    if "科学" in s:
        return "科学探究、现象解释、实验设计、数据分析、科学概念原理"
    if "物理" in s:
        return "概念辨析、受力/电路/能量模型、公式选择、过程分析、实验探究"
    if "化学" in s:
        return "方程式、实验现象、物质推断、离子反应、氧化还原、计算与规范表达"
    if "生物" in s:
        return "概念网络、图表信息提取、遗传推理、实验设计、生命活动调节过程"
    if "历史" in s:
        return "时空线索、史料解读、因果分析、阶段特征、观点论证"
    if "地理" in s:
        return "区域定位、图表判读、成因分析、人地关系、区位综合"
    if "政治" in s or "道德" in s:
        return "概念原理、材料提取、观点论证、时政迁移、规范作答"
    return "基础掌握、应用能力、综合分析、逻辑推理、表达规范"


def _subject_prompt(subject: str, payload: dict) -> str:
    focus = _subject_focus(subject)
    school_level = payload.get("school_level", "")
    grade = payload.get("grade", "")
    
    level_info = ""
    if school_level and grade:
        level_info = f"当前学段为：{school_level}，年级为：{grade}。请确保所有分析、目标和教学语言符合该学段和年级学生的认知水平和教学要求。"
        
    return f"""
你是一位资深{subject}教师，正在为老师生成”课堂讲评”课前方案。输入是真实批改数据的聚合统计：question_accuracy（每题正确/错误/空白人数与典型错因 top_reasons）、high_risk_questions（高频错题）、strong_questions（正确率较高题目）、分数概况。请完全据此分析，不要臆造。
{level_info}

请严格遵守以下规则：
1. **完全基于数据**：只根据输入数据判断，绝不编造不存在的考试、学生或题目。所有结论必须有数据支撑。
2. **面向全班讲评**：课堂讲评面向全班，重点是课前用来讲知识点和讲评典型错误，不是个体学生诊断。
3. **重点错题驱动**：对于“课堂重点知识点（key_points）”，**必须完全依照导入考试的错题和题目进行生成**。优先根据高频错题（high_risk_questions）提取知识点，不要生成与本次考试无关或关联性差的内容。
4. **学科特性**：本学科讲评要重点贴合这些维度：{focus}。不同学科的讲评语言和教学活动要有明显区分。

请返回合法 JSON，不要 markdown，不要代码块。字段要求尽量详细充实，字段如下：
{{
  "overview": {{
    "summary": "150字左右概括本班本学科讲评重点",
    "weak_points": ["班级整体薄弱知识点/能力点，一句话概括，如：几何图形理解薄弱，3-5条"],
    "strengths": ["班级整体较好表现，一句话概括，如：计算题正确率高，2-4条"],
    "data_basis": ["核心数据证据，一句话概括，如：选择题平均得分率80%，2-4条"]
  }},
  "review_plan": {{
    "duration": "建议讲评时长，如40分钟",
    "objectives": ["本节讲评的具体可衡量目标，详细描述，3-5条"],
    "key_points": ["需要讲的核心知识点。⚠️必须从输入的错题和考试题目中提取，简洁明了一针见血地指出知识点名称及缺陷，如：分数乘法法则掌握不牢，4-8条"],
    "teaching_flow": [
      {{"step": "环节名称", "minutes": 8, "teacher_action": "教师怎么讲（详细步骤）", "student_action": "学生怎么做（具体动作）"}}
    ],
    "blackboard_design": ["详细的板书要点设计，3-6条"],
    "interaction_questions": ["结合错题设计的课堂追问/互动问题，详细描述，4-8条"]
  }},
  "question_cards": [
    {{
      "title": "具体题号或讲评点名称",
      "knowledge_point": "具体对应的知识点",
      "correct_count": 0,
      "wrong_count": 0,
      "blank_count": 0,
      "error_patterns": ["从 question_accuracy.top_reasons 或 high_risk_questions.reasons 中提取的典型错误详细描述"],
      "teaching_strategy": "针对该题的详细讲评建议和切入点",
      "follow_up_exercise": "具体的变式练习建议"
    }}
  ]
}}

真实输入：
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def _tracking_prompt(subject: str, session: dict, feedback: dict) -> str:
    return f"""
你是一位{subject}教研组长。请根据课前课堂讲评方案、真实批改数据和教师填写的课后课堂效果，评估本堂讲评课的质量、优点和不足。
注意：不要输出针对某个学生的个体方案，本模块只评估讲课质量和数据闭环。
返回合法 JSON：
{{
  "summary": "本堂讲评效果总体评价，100字以内",
  "quality_score": 0,
  "strengths": ["讲课优点，3-5条"],
  "problems": ["讲课不足，3-5条"],
  "evidence": ["依据教师反馈和课前数据的证据，3-6条"],
  "improvement_suggestions": ["下次讲评改进建议，3-5条"],
  "next_observation": ["后续需要观察的数据，2-4条"]
}}
课堂讲评方案：
{json.dumps(session, ensure_ascii=False)}
课后反馈：
{json.dumps(feedback, ensure_ascii=False)}
""".strip()


def _consolidation_prompt(subject: str, session: dict, feedback: dict) -> str:
    return f"""
你是一位{subject}备课专家。请根据课前课堂讲评方案和教师填写的课后课堂效果，生成二次讲解/课后分层巩固方案。
注意：这里不是学生个体靶向提升，不要写具体学生姓名；重点是二次讲课参考、知识点再讲策略和巩固练习。
返回合法 JSON：
{{
  "summary": "二次讲解与巩固总体思路，100字以内",
  "reteaching_points": ["需要二次讲解的知识点，3-6条"],
  "lesson_adjustments": ["二次讲课调整策略，3-6条"],
  "tiered_practice": [
    {{"level": "基础巩固", "tasks": ["练习任务1", "练习任务2"]}},
    {{"level": "能力提升", "tasks": ["练习任务1", "练习任务2"]}},
    {{"level": "拓展迁移", "tasks": ["练习任务1", "练习任务2"]}}
  ],
  "teacher_actions": ["教师后续动作，3-5条"],
  "checkpoints": ["验收方式，2-4条"]
}}
课堂讲评方案：
{json.dumps(session, ensure_ascii=False)}
课后反馈：
{json.dumps(feedback, ensure_ascii=False)}
""".strip()


def _upsert_session(db: Session, class_id: str, subject: str, folders: list[str], payload: dict, ai_data: dict, user_id: str) -> ClassReviewSession:
    pre_class = {k: v for k, v in ai_data.items() if k != "_raw_content"}
    if "all_wrong_images" in payload:
        pre_class["all_wrong_images"] = payload["all_wrong_images"]
    _, _, ai_model = get_llm_config(db)
    row = db.query(ClassReviewSession).filter(
        ClassReviewSession.class_id == class_id,
        ClassReviewSession.subject == subject,
        ClassReviewSession.user_id == user_id,
    ).first()
    if not row:
        row = ClassReviewSession(class_id=class_id, subject=subject, user_id=user_id)
        db.add(row)
    row.title = f"{subject}课堂讲评"
    row.exam_names_json = _json_dumps(payload.get("exam_names", []))
    row.imported_folder_names_json = _json_dumps(folders)
    row.source_summary_json = _json_dumps({
        "valid_student_count": payload.get("valid_student_count", 0),
        "class_avg_score": payload.get("class_avg_score"),
        "answer_area_count": payload.get("answer_area_count", 0),
        "correct_count": payload.get("correct_count", 0),
        "wrong_count": payload.get("wrong_count", 0),
        "blank_count": payload.get("blank_count", 0),
        "high_risk_questions": payload.get("high_risk_questions", [])[:10],
        "strong_questions": payload.get("strong_questions", [])[:8],
        "question_accuracy": payload.get("question_accuracy", []),
        "question_students": payload.get("question_students", {}),
    })
    row.pre_class_json = _json_dumps(pre_class)
    row.ai_raw_json = _json_dumps({"pre_class": pre_class})
    # E05 · AI 内容统一标识（GB 45438 隐式标识）：课堂讲评由 AI 生成，落库显式写 is_ai=1 + ai_meta
    row.is_ai = 1
    row.ai_meta = {"generator": AI_GENERATOR, "model": ai_model}
    row.generated_at = datetime.now(timezone.utc)
    return row


@router.get("/subjects", response_model=ApiResponse[list])
def list_subjects(user_id: str = Depends(get_current_user_id)):
    return ApiResponse(data=SUBJECTS)


@router.get("/sessions", response_model=ApiResponse[list])
def list_sessions(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """课堂讲评历史：列出当前老师的全部讲评会话（每班每科一条），供「讲评历史」列表使用。"""
    rows = (
        db.query(ClassReviewSession)
        .filter(ClassReviewSession.user_id == user_id)
        .order_by(ClassReviewSession.updated_at.desc())
        .all()
    )
    # 批量查班级名/年级，避免逐条查询
    class_id_set = {r.class_id for r in rows}
    class_name_map: dict[str, str] = {}
    grade_map: dict[str, str] = {}
    if class_id_set:
        try:
            from app.models.class_model import Class

            cls_rows = (
                db.query(Class.id, Class.name, Class.grade)
                .filter(Class.id.in_(class_id_set))
                .all()
            )
            for cid, cname, cgrade in cls_rows:
                class_name_map[cid] = cname
                grade_map[cid] = cgrade or ""
        except Exception:
            pass

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "class_id": r.class_id,
            "class_name": class_name_map.get(r.class_id, ""),
            "grade": grade_map.get(r.class_id, ""),
            "subject": r.subject,
            "title": r.title or "",
            "exam_names": _json_loads(r.exam_names_json, []),
            "imported_folder_names": _json_loads(r.imported_folder_names_json, []),
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })
    return ApiResponse(data=items)


@router.get("/report", response_model=ApiResponse[dict])
def get_report(
    class_id: str = Query(...),
    subject: str = Query(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_class_access(db, user_id, class_id)
    row = db.query(ClassReviewSession).filter(
        ClassReviewSession.class_id == class_id,
        ClassReviewSession.subject == subject,
        ClassReviewSession.user_id == user_id,
    ).first()
    report = _session_to_dict(row)
    if report:
        folders = report.get("imported_folder_names") or []
        if folders:
            from app.grading.wrong_question_db import collect_wrong_question_images

            fresh_images = collect_wrong_question_images(folders)
            pre_class = report.setdefault("pre_class", {})
            pre_class["all_wrong_images"] = fresh_images
            if row:
                stored_pre_class = _json_loads(row.pre_class_json, {})
                if stored_pre_class.get("all_wrong_images") != fresh_images:
                    stored_pre_class["all_wrong_images"] = fresh_images
                    row.pre_class_json = _json_dumps(stored_pre_class)
                    db.commit()
    return ApiResponse(data={"report": report})


class GeneratePptRequest(BaseModel):
    class_id: str
    subject: str
    # 可选：只针对某一道题生成单题 PPT（前端「原题」旁的生成按钮传入 question_key）
    question_key: Optional[str] = None


def _ct_image_bytes(url: Optional[str]) -> Optional[bytes]:
    """把错题图 URL（/api/v1/ct/...?ticket= 或旧 ct-image?path=）解析为本地图片字节，供 PPT 嵌入。"""
    if not url:
        return None
    from app.grading.wrong_question_db import resolve_ct_image_path

    rel = None
    s = str(url).split("?", 1)[0]
    if s.startswith("/api/v1/ct/"):
        rel = s[len("/api/v1/ct/"):]
    elif "/ct-image" in s:
        from urllib.parse import urlparse, parse_qs

        qs = parse_qs(urlparse(url).query)
        rel = (qs.get("path") or [None])[0]
    if not rel:
        return None
    try:
        p = resolve_ct_image_path(rel)
    except Exception:
        return None
    if p and p.is_file():
        try:
            return p.read_bytes()
        except Exception:
            return None
    return None


def _variant_prompt(subject: str, questions: list) -> str:
    return f"""你是资深{subject}教师。下面是课堂讲评中需要讲解的题目列表，每道题含题号与题干原文。

请针对每道题输出：
1. knowledge_points：该题考查的核心知识点清单（2~4 条）。每条要具体、可教学，写成「知识点名称：要点说明」的形式（例如「一元二次方程根的判别式：Δ=b²−4ac>0 时方程有两个不相等的实数根」），不要只写名词。
2. variant_stem：一道「同类变式题」题干（同知识点、同题型，难度略高于原题，适合课堂巩固练习）。
3. variant_answer：该变式题的参考答案/思路（≤60 字）。

【硬性要求】
- 严格按输入题目的 label 原样回填，不要改名、不要增减题目数量。
- 只输出一个 JSON 对象：{{"questions":[{{"label":"…","knowledge_points":["…","…"],"variant_stem":"…","variant_answer":"…"}}]}}
- 不要输出 ```json 代码块、不要任何说明文字。

题目列表：
{json.dumps(questions, ensure_ascii=False)}"""


def _leading_qno(title: str) -> Optional[int]:
    """从「第N题…」里提取题号（阿拉伯数字），用于单题 PPT 对齐错答扫描。"""
    m = re.match(r"^第(\d+)题", (title or "").strip())
    return int(m.group(1)) if m else None


def _normalize_knowledge_points(it: dict) -> list:
    """兼容 knowledge_points(list) 与旧 knowledge_point(str) 两种返回。"""
    kps = it.get("knowledge_points")
    if isinstance(kps, list):
        return [str(x).strip() for x in kps if str(x).strip()][:4]
    kp = it.get("knowledge_point")
    if isinstance(kp, str) and kp.strip():
        return [kp.strip()]
    return []


@router.post("/generate-pptx")
def generate_class_review_pptx(
    body: GeneratePptRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """把已生成的课堂讲评方案转换为 .pptx（原题 + 知识点 + 学生错答扫描 + 同类变式题）。

    传入 question_key 时只生成单题 PPT；否则生成整份讲评（正确率最低的前 8 题）。
    """
    require_ai_access(db, user_id, "ai_review")
    _assert_class_access(db, user_id, body.class_id)

    row = db.query(ClassReviewSession).filter(
        ClassReviewSession.class_id == body.class_id,
        ClassReviewSession.subject == body.subject,
        ClassReviewSession.user_id == user_id,
    ).first()
    if not row:
        raise HTTPException(status_code=400, detail="请先导入考试生成课堂讲评方案")

    report = _session_to_dict(row) or {}
    subject = body.subject
    summary = report.get("source_summary") or {}
    pre_class = report.get("pre_class") or {}
    folders = report.get("imported_folder_names") or []

    question_accuracy = summary.get("question_accuracy") or []

    def _label(q: dict) -> str:
        return (q.get("real_number") or q.get("display_title") or q.get("question_key") or "").strip()

    # 单题 vs 整份：单题按 question_key 定位（回退 display_title 精确匹配）
    target_key = (body.question_key or "").strip()
    if target_key:
        selected = None
        for q in question_accuracy:
            if str(q.get("question_key") or "") == target_key:
                selected = q
                break
        if selected is None:
            for q in question_accuracy:
                if str(q.get("display_title") or "") == target_key:
                    selected = q
                    break
        if selected is None:
            raise HTTPException(status_code=400, detail="未找到该题目，请刷新后重试")
        top_questions = [selected]
    else:
        top_questions = (question_accuracy or [])[:8]

    # 学生错答扫描：重扫磁盘取最新裁剪图（避免旧 ?ticket= 过期导致取不到本地文件）
    from app.grading.wrong_question_db import collect_wrong_question_images

    all_wrong_images = pre_class.get("all_wrong_images") or []
    if folders:
        try:
            all_wrong_images = collect_wrong_question_images(folders)
        except Exception:
            pass

    wrong_images = []
    for item in all_wrong_images or []:
        ib = _ct_image_bytes(item.get("image_url"))
        ab = _ct_image_bytes(item.get("answer_url"))
        if not ib and not ab:
            continue
        wrong_images.append({
            "student_name": item.get("student_name") or "",
            "title": item.get("title") or "",
            "image_bytes": ib,
            "answer_bytes": ab,
        })

    # 单题模式：只保留这道题的错答扫描（按「第N题」题号对齐）
    if target_key and selected is not None:
        qno = _leading_qno(str(selected.get("display_title") or ""))
        wrong_images = (
            [wi for wi in wrong_images if _leading_qno(str(wi.get("title") or "")) == qno]
            if qno is not None else []
        )
    wrong_images = wrong_images[:16]

    base_blocks = []
    for idx, q in enumerate(top_questions):
        base_blocks.append({
            "label": _label(q) or f"第{idx + 1}题",
            "accuracy": q.get("accuracy") or 0,
            "question_text": q.get("question_text") or "",
        })

    # AI：一次批量生成每题「知识点（详细）+ 同类变式题」；失败则降级（知识点/变式留空，仍可出 PPT）
    ai_map: dict = {}
    if base_blocks:
        prompt_input = [
            {
                "label": b["label"],
                "accuracy": b["accuracy"],
                "question_text": (b["question_text"] or "")[:400],
            }
            for b in base_blocks
        ]
        if not assert_no_sensitive_input(json.dumps(prompt_input, ensure_ascii=False)[:4000]):
            try:
                ai_raw = _call_qwen(_variant_prompt(subject, prompt_input), db, temperature=0.5)
                for it in (ai_raw.get("questions") or []):
                    if not isinstance(it, dict):
                        continue
                    lbl = str(it.get("label") or "").strip()
                    if not lbl:
                        continue
                    ai_map[lbl] = {
                        "knowledge_points": _normalize_knowledge_points(it),
                        "variant_stem": str(it.get("variant_stem") or "").strip(),
                        "variant_answer": str(it.get("variant_answer") or "").strip(),
                    }
            except Exception:
                ai_map = {}

    question_blocks = []
    for b in base_blocks:
        ai = ai_map.get(b["label"]) or {}
        question_blocks.append({
            **b,
            "knowledge_points": ai.get("knowledge_points") or [],
            "variant_stem": ai.get("variant_stem") or "",
            "variant_answer": ai.get("variant_answer") or "",
        })

    variant_blocks = [
        {"label": b["label"], "variant_stem": b["variant_stem"], "variant_answer": b["variant_answer"]}
        for b in question_blocks
        if (b.get("variant_stem") or b.get("variant_answer"))
    ]

    date_str = datetime.now().strftime("%Y-%m-%d")
    if target_key:
        acc = (top_questions[0].get("accuracy") or 0) if top_questions else 0
        qlabel = _label(top_questions[0]) if top_questions else "题目"
        overview_items = [
            f"本题正确率：{round(acc, 1)}%",
            f"学生错答扫描：{len(wrong_images)} 张",
            f"同类变式练习：{len(variant_blocks)} 道",
        ]
        title = f"{qlabel} · 原题与知识点"
        subtitle = f"{subject} · {qlabel} · 课堂讲评"
        base_name = f"{qlabel}_讲评PPT"
    else:
        avg_acc = 0.0
        if question_accuracy:
            avg_acc = sum((q.get("accuracy") or 0) for q in question_accuracy) / len(question_accuracy)
        overview_items = [
            f"讲评题目：{len(top_questions)} 道（全卷共 {len(question_accuracy)} 道，按正确率从低到高）",
            f"全卷平均正确率：{round(avg_acc, 1)}%",
            f"学生错答扫描：{len(wrong_images)} 张",
            f"同类变式练习：{len(variant_blocks)} 道",
        ]
        title = (report.get("title") or f"{subject}课堂讲评").strip()
        subtitle = f"{subject} · 课堂讲评 · {date_str}"
        base_name = f"{subject}_课堂讲评PPT"

    from app.services.class_review_pptx import build_class_review_pptx

    try:
        pptx_bytes = build_class_review_pptx(
            title, subject, subtitle, overview_items, question_blocks, wrong_images, variant_blocks
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    filename = quote(f"{base_name}_{date_str}.pptx")
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


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
        candidates = [d.name for d in correct_docs_dir().iterdir() if d.is_dir() and d.name.startswith(prefix)]
    except Exception:
        candidates = []
    folders = []
    for safe in candidates:
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
    body: ImportReviewExamsRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    # E08 · 学校级 AI 管控：课堂讲评/班级分析（ai_review）开关关闭时一律 403
    require_ai_access(db, user_id, "ai_review")
    _assert_class_access(db, user_id, body.class_id)
    prefix = _class_folder_prefix(body.class_id)
    if not prefix:
        raise HTTPException(status_code=400, detail="班级ID无效")
    folder_names = [str(x or "").strip() for x in body.exam_folder_names if str(x or "").strip()]
    folder_names = list(dict.fromkeys(folder_names))
    if not folder_names:
        raise HTTPException(status_code=400, detail="请选择要导入的考试")
    invalid = [x for x in folder_names if not x.startswith(prefix)]
    if invalid:
        raise HTTPException(status_code=400, detail="存在不属于当前班级的考试")

    # 错题记录完整性检查：批改完成但错题记录尚未生成完整时，先返回 pending 让前端稍后重试，
    # 避免「自动推送」在批改刚完成的瞬间导入半截数据（表现为每题作答人数偏少、准确率异常）。
    incomplete = _records_incomplete(folder_names)
    if incomplete is not None:
        completed_count, record_count = incomplete
        return ApiResponse(data={
            "ok": False,
            "pending": True,
            "completed_count": completed_count,
            "record_count": record_count,
        })

    payload, ignored = _aggregate_payload(body.class_id, body.subject, folder_names, db)

    # PII 匿名化：聚合 records 里的 student_name 等字段在拼 prompt 前匿名，AI 返回后还原再入库。
    anon = Anonymizer()
    _register_class_students(anon, db, body.class_id)
    # 精简发给大模型的输入，避免大试卷拼出的 prompt 超过网关单次请求配额
    # （表现为"当前用户的余额不足"）：
    #   1) 去掉全量逐生答题明细 paper_records 与逐条错因 wrong_analysis；
    #   2) question_accuracy 只保留正确率最低的 top N 题（讲评重点，已按正确率升序排好）。
    prompt_payload = {
        k: v for k, v in payload.items()
        if k not in {"all_wrong_images", "paper_records", "wrong_analysis", "question_students"}
    }
    _qa_limit = 50
    _qa = prompt_payload.get("question_accuracy") or []
    if len(_qa) > _qa_limit:
        prompt_payload["question_accuracy"] = _qa[:_qa_limit]
    ai_data = _call_qwen(_subject_prompt(body.subject, anon.anon_text_deep(prompt_payload)), db)
    ai_data = anon.restore_deep(ai_data)

    row = _upsert_session(db, body.class_id, body.subject, folder_names, payload, ai_data, user_id)
    db.commit()
    db.refresh(row)
    return ApiResponse(data={
        "ok": True,
        "report": _session_to_dict(row),
        "ignored_count": len(ignored),
        "ignored_papers": ignored[:50],
    })


@router.post("/post-class", response_model=ApiResponse[dict])
def generate_post_class(
    body: PostClassFeedbackRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    # E08 · 学校级 AI 管控：课堂讲评（ai_review）开关关闭时一律 403；教师自由文本命中敏感输入拒答
    require_ai_access(db, user_id, "ai_review")
    free_texts = [
        *body.taught_points,
        *body.mastered_points,
        *body.unresolved_points,
        body.overall_effect,
        body.teacher_notes,
    ]
    if any(assert_no_sensitive_input(t) for t in free_texts):
        raise HTTPException(status_code=403, detail="输入包含身份证号/手机号等敏感个人信息，请移除后重试")
    _assert_class_access(db, user_id, body.class_id)
    row = db.query(ClassReviewSession).filter(
        ClassReviewSession.class_id == body.class_id,
        ClassReviewSession.subject == body.subject,
        ClassReviewSession.user_id == user_id,
    ).first()
    if not row:
        raise HTTPException(status_code=400, detail="请先导入考试生成课堂讲评方案")
    feedback = {
        "taught_points": body.taught_points,
        "mastered_points": body.mastered_points,
        "unresolved_points": body.unresolved_points,
        "overall_effect": body.overall_effect,
        "teacher_notes": body.teacher_notes,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    session_data = _session_to_dict(row) or {}
    # PII 匿名化：课前方案/教师反馈中可能嵌入学生姓名，发千问前匿名，返回后还原。
    anon = Anonymizer()
    _register_class_students(anon, db, body.class_id)
    session_anon = anon.anon_text_deep(session_data)
    feedback_anon = anon.anon_text_deep(feedback)
    tracking = anon.restore_deep(_call_qwen(_tracking_prompt(body.subject, session_anon, feedback_anon), db))
    consolidation = anon.restore_deep(_call_qwen(_consolidation_prompt(body.subject, session_anon, feedback_anon), db))
    row.post_feedback_json = _json_dumps(feedback)
    row.tracking_json = _json_dumps({k: v for k, v in tracking.items() if k != "_raw_content"})
    row.consolidation_json = _json_dumps({k: v for k, v in consolidation.items() if k != "_raw_content"})
    row.ai_raw_json = _json_dumps({
        "pre_class": _json_loads(row.pre_class_json, {}),
        "tracking": _json_loads(row.tracking_json, {}),
        "consolidation": _json_loads(row.consolidation_json, {}),
    })
    db.commit()
    db.refresh(row)
    return ApiResponse(data={"ok": True, "report": _session_to_dict(row)})
