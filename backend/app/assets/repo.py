"""P0 资产引擎只读查询（家长端 PG 资产库）。

- 全部参数化查询（ORM 表达式），禁止字符串拼接。
- 全部强制 LIMIT 兜底，杜绝全表拉取。
- 返回 dict 列表，便于路由层直接 JSON 序列化。
- 统一 `import app.assets.models as am` 别名访问，防与主平台同名模型遮蔽。
"""
from sqlalchemy import func

import app.assets.models as am
from app.assets.database import assets_session

# 单次查询最大行数硬上限（强制 LIMIT 兜底）
_MAX_LIMIT = 500


def _coerce_limit(limit, default=20) -> int:
    """把 limit 收敛到 [1, _MAX_LIMIT]，防御负数/0/超限。"""
    try:
        v = int(limit)
    except (TypeError, ValueError):
        v = default
    return max(1, min(v, _MAX_LIMIT))


def _quality_ok(column):
    """抽题质量过滤：quality_flag IN ('ok','filled') OR quality_flag IS NULL。"""
    return (column.in_(["ok", "filled"])) | column.is_(None)


def _escape_like(s: str) -> str:
    """转义 LIKE 通配符，防用户输入 %/_ 被当通配符。"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _question_to_dict(q) -> dict:
    """列白名单契约：仅挑白名单列返回（防未来漂移泄敏）。

    新增列若属于 ASSET_SENSITIVE_COLUMNS（user_id / mastery / is_weak / phone /
    email 等家长端 PII / 学习状态列）必须先剥离或改走其他白名单，禁止直接加进
    本 dict。_asset_query_rows 亦在返回前做统一剥列兜底（双保险）。
    """
    return {
        "id": q.id,
        "subject": q.subject,
        "grade": q.grade,
        "question_type": q.question_type,
        "question": q.question,
        "options": q.options,
        "answer": q.answer,
        "analysis": q.analysis,
        "knowledge_point": q.knowledge_point,
        "difficulty": q.difficulty,
        "source": q.source,
        "raw_id": q.raw_id,
        "unique_key": q.unique_key,
        "curriculum": q.curriculum,
        "difficulty_source": q.difficulty_source,
        "esl_level": q.esl_level,
        "quality_flag": q.quality_flag,
        "ai_verdict": q.ai_verdict,
        "ai_confidence": q.ai_confidence,
        "ai_judge_source": q.ai_judge_source,
    }


def get_kp_tree(subject: str):
    """按学科返回知识点树节点（JOIN subject_units 过滤学科）。

    返回 id/code/name/level/knowledge_nature/unit_id，按 level 排序。
    """
    limit = _coerce_limit(1000, default=1000)
    with assets_session() as db:
        rows = (
            db.query(am.KnowledgePoint)
            .join(am.SubjectUnit, am.SubjectUnit.id == am.KnowledgePoint.unit_id)
            .filter(am.SubjectUnit.subject == subject)
            .order_by(am.KnowledgePoint.level, am.KnowledgePoint.code)
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "level": r.level,
                "knowledge_nature": r.knowledge_nature,
                "unit_id": r.unit_id,
            }
            for r in rows
        ]


def get_questions(subject: str, limit: int = 20):
    """按学科取题，过滤 quality_flag IN ('ok','filled') OR IS NULL。"""
    limit = _coerce_limit(limit)
    with assets_session() as db:
        rows = (
            db.query(am.Question)
            .filter(am.Question.subject == subject)
            .filter(_quality_ok(am.Question.quality_flag))
            .limit(limit)
            .all()
        )
        return [_question_to_dict(r) for r in rows]


def get_questions_by_kp(kp_id: str, count: int = 20):
    """经 question_kp 桥接表，按知识点取题。"""
    count = _coerce_limit(count)
    with assets_session() as db:
        rows = (
            db.query(am.Question)
            .join(am.QuestionKp, am.QuestionKp.question_id == am.Question.id)
            .filter(am.QuestionKp.kp_id == kp_id)
            .filter(_quality_ok(am.Question.quality_flag))
            .limit(count)
            .all()
        )
        return [_question_to_dict(r) for r in rows]


def get_random_questions(subject: str, grade: str, count: int = 20):
    """按中文学段（小学/初中/高中/大学）随机抽题。

    过滤：quality_flag IN ('ok','filled') OR IS NULL，且 ai_verdict != 'reject'
    （ai_verdict IS NULL 放行）。
    """
    count = _coerce_limit(count)
    with assets_session() as db:
        rows = (
            db.query(am.Question)
            .filter(am.Question.subject == subject, am.Question.grade == grade)
            .filter(_quality_ok(am.Question.quality_flag))
            .filter((am.Question.ai_verdict != "reject") | am.Question.ai_verdict.is_(None))
            .order_by(func.random())
            .limit(count)
            .all()
        )
        return [_question_to_dict(r) for r in rows]


def search_questions(
    subject: str | None = None,
    grade: str | None = None,
    question_type: str | None = None,
    difficulty: int | None = None,
    knowledge_point: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """多条件组合检索 + 分页，返回 (items, total)。

    - 全部参数化 ORM 表达式（ilike 关键词走绑定参数，escape 转义通配符），禁字符串拼接。
    - quality_flag ok/filled/NULL 放行；offset/limit 强制兜底。
    - total 供前端分页条数。
    """
    page_size = _coerce_limit(page_size, default=20)
    page = max(1, int(page or 1))
    offset = (page - 1) * page_size

    with assets_session() as db:
        q = db.query(am.Question).filter(_quality_ok(am.Question.quality_flag))
        if subject:
            q = q.filter(am.Question.subject == subject)
        if grade:
            q = q.filter(am.Question.grade == grade)
        if question_type:
            q = q.filter(am.Question.question_type == question_type)
        if difficulty is not None:
            q = q.filter(am.Question.difficulty == difficulty)
        if knowledge_point:
            q = q.filter(
                am.Question.knowledge_point.ilike(
                    f"%{_escape_like(knowledge_point)}%", escape="\\"
                )
            )
        if keyword:
            q = q.filter(
                am.Question.question.ilike(f"%{_escape_like(keyword)}%", escape="\\")
            )

        total = q.count()
        rows = (
            q.order_by(am.Question.updated_at.desc().nulls_last(), am.Question.id)
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return [_question_to_dict(r) for r in rows], total


def get_filters():
    """返回前端筛选下拉可用的枚举值（去重后的学科/学段/题型/难度）。"""
    with assets_session() as db:
        subjects = [
            r[0]
            for r in db.query(am.Question.subject)
            .distinct()
            .order_by(am.Question.subject)
            .all()
            if r[0]
        ]
        grades = [
            r[0]
            for r in db.query(am.Question.grade)
            .distinct()
            .order_by(am.Question.grade)
            .all()
            if r[0]
        ]
        question_types = [
            r[0]
            for r in db.query(am.Question.question_type)
            .distinct()
            .order_by(am.Question.question_type)
            .all()
            if r[0]
        ]
        difficulties = [
            r[0]
            for r in db.query(am.Question.difficulty)
            .distinct()
            .order_by(am.Question.difficulty)
            .all()
            if r[0] is not None
        ]
    return {
        "subjects": subjects,
        "grades": grades,
        "question_types": question_types,
        "difficulties": difficulties,
    }
