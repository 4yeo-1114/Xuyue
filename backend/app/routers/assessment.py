"""测评域（B 域）API —— B0 契约 §7

基础路径：/api/v1/assessment（本文件 router）+ /api/v1/parent-students（parent_router）
鉴权：JWT Bearer Token（get_current_user_id 仅解析 user_id；角色判定走服务层 access.py）

注意：叙阅当前无 parent 角色，家长身份以 parent_students 绑定表为准（见 access.is_parent_user）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.schemas.common import ApiResponse

from app.models.assessment_definition import AssessmentDefinition
from app.models.assessment_session import AssessmentSession
from app.models.assessment_result import AssessmentResult
from app.models.assessment_answer import AssessmentAnswer
from app.models.class_model import Class
from app.models.parent_student import ParentStudent
from app.models.student import Student
from app.models.user import User

from app.schemas.assessment.definitions import (
    CreateDefinitionRequest,
    UpdateDefinitionRequest,
    DefinitionRecord,
    DefinitionListData,
    ALLOWED_DOMAINS,
    ALLOWED_GRADE_RANGES,
    ALLOWED_STATUSES,
)
from app.schemas.assessment.sessions import (
    CreateSessionRequest,
    SubmitAnswersRequest,
    SessionRecord,
    SessionListData,
    ALLOWED_TEST_MODES,
)
from app.schemas.assessment.results import ResultRecord, ResultListData, SubmitAnswerResult
from app.schemas.assessment.parents import (
    CreateParentStudentRequest,
    ParentStudentRecord,
    ParentStudentListData,
    ALLOWED_RELATIONS,
)

from app.services.assessment import access as access_svc
from app.services.assessment import scoring as scoring_svc
from app.services.assessment import consent as consent_svc
from app.services.assessment import seed as seed_svc
from app.services.audit.access_log import log_access, resolve_user_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assessment", tags=["assessment"])


def _log_consent_access(
    db: Session,
    user_id: str,
    student_id: str,
    result_id: str,
    old_status: str,
    new_status: str,
) -> None:
    """E03/E14：consent grant/withdraw/restore 留痕（写失败不阻断）。"""
    role = resolve_user_role(db, user_id)
    log_access(
        db,
        user_id=user_id,
        user_role=role,
        action="consent_change",
        target_type="student",
        target_id=student_id,
        detail={"result_id": result_id, "old_status": old_status, "new_status": new_status},
    )
parent_router = APIRouter(prefix="/parent-students", tags=["parent-students"])

# 惰性种子触发：不能改 app/main.py / app/database.py 挂 init_db 钩子，
# 在首个测评接口访问时幂等写入种子题组（B0 附录 A）。
_seed_attempted = False


def _ensure_seed(db: Session) -> None:
    """惰性幂等写入种子题组；失败不阻塞接口（记录日志）。"""
    global _seed_attempted
    if _seed_attempted:
        return
    _seed_attempted = True
    try:
        seed_svc.seed_assessment_definition(db)
    except Exception:  # pragma: no cover - 表未建/种子已存在等均静默
        logger.warning("[assessment] 种子题组写入失败（跳过，非阻塞）", exc_info=True)


# ── 工具函数 ──────────────────────────────────────────────

def _dt(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_definition(db: Session, definition_id: str) -> AssessmentDefinition:
    d = db.query(AssessmentDefinition).filter(AssessmentDefinition.id == definition_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="definition_not_found")
    return d


def _get_student(db: Session, student_id: str) -> Student:
    s = db.query(Student).filter(Student.id == student_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="student_not_found")
    return s


def _get_session(db: Session, session_id: str) -> AssessmentSession:
    s = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="session_not_found")
    return s


def _student_name(db: Session, student_id: str) -> Optional[str]:
    s = db.query(Student).filter(Student.id == student_id).first()
    return s.name if s else None


def _definition_name(db: Session, definition_id: Optional[str]) -> Optional[str]:
    if not definition_id:
        return None
    d = db.query(AssessmentDefinition).filter(AssessmentDefinition.id == definition_id).first()
    return d.name if d else None


def _def_record(db: Session, d: AssessmentDefinition, include_questions: bool = True) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "domain": d.domain,
        "grade_range": d.grade_range,
        "version": d.version,
        "status": d.status,
        "consent_required": bool(d.consent_required),
        "description": d.description,
        "question_count": len(d.questions or []),
        "questions": d.questions if include_questions else None,
        "created_at": _dt(d.created_at) or "",
    }


def _session_record(db: Session, s: AssessmentSession, include_questions: bool = False) -> dict:
    rec = {
        "id": s.id,
        "student_id": s.student_id,
        "student_name": _student_name(db, s.student_id),
        "definition_id": s.definition_id,
        "definition_name": _definition_name(db, s.definition_id),
        "test_mode": s.test_mode,
        "batch_id": s.batch_id,
        "status": s.status,
        "proctored_by": s.proctored_by,
        "created_by": s.created_by,
        "taken_at": _dt(s.taken_at),
        "submitted_at": _dt(s.submitted_at),
        "created_at": _dt(s.created_at) or "",
        "updated_at": _dt(s.updated_at) or "",
    }
    if include_questions:
        d = db.query(AssessmentDefinition).filter(AssessmentDefinition.id == s.definition_id).first()
        rec["questions"] = d.questions if d else []
    return rec


def _result_record(db: Session, r: AssessmentResult, include_raw: bool = False) -> dict:
    rec = {
        "id": r.id,
        "student_id": r.student_id,
        "definition_id": r.definition_id,
        "definition_name": _definition_name(db, r.definition_id),
        "domain": r.domain,
        "purpose": r.purpose,
        "tag_schema": r.tag_schema or {},
        "guardian_consent": r.guardian_consent or {},
        "session_id": r.session_id,
        "created_by": r.created_by,
        "created_at": _dt(r.created_at) or "",
    }
    if include_raw:
        rec["raw_score"] = r.raw_score
    else:
        rec["raw_score"] = None
    return rec


def _parent_record(db: Session, p: ParentStudent) -> dict:
    u = db.query(User).filter(User.id == p.parent_id).first()
    parent_name = u.display_name if u else None
    return {
        "id": p.id,
        "parent_id": p.parent_id,
        "parent_name": parent_name,
        "student_id": p.student_id,
        "student_name": _student_name(db, p.student_id),
        "relation": p.relation,
        "status": p.status,
        "created_by": p.created_by,
        "created_at": _dt(p.created_at) or "",
    }


def _assert_definition_can_manage(db: Session, user_id: str) -> None:
    if not access_svc.can_manage_definitions(db, user_id):
        raise HTTPException(status_code=403, detail="forbidden")


# ── 7.1 题组定义 API ──────────────────────────────────────

@router.get("/definitions", response_model=ApiResponse[DefinitionListData])
def list_definitions(
    domain: Optional[str] = Query(None, description="按 domain 过滤"),
    status: Optional[str] = Query(None, description="按状态过滤，默认 active"),
    brief: bool = Query(False, description="true 时仅返回 question_count 不含 questions"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _ensure_seed(db)
    q = db.query(AssessmentDefinition)
    if domain:
        q = q.filter(AssessmentDefinition.domain == domain)
    if status:
        q = q.filter(AssessmentDefinition.status == status)
    else:
        # 默认仅列 active 状态（教师选题施测、学生读题面）
        q = q.filter(AssessmentDefinition.status == "active")
    rows = q.order_by(AssessmentDefinition.created_at.desc()).all()
    return ApiResponse(
        data=DefinitionListData(
            rows=[DefinitionRecord(**_def_record(db, d, include_questions=not brief)) for d in rows],
            total=len(rows),
        ),
        message="success",
    )


@router.post("/definitions", response_model=ApiResponse[dict])
def create_definition(
    body: CreateDefinitionRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_definition_can_manage(db, user_id)
    _ensure_seed(db)
    if body.domain not in ALLOWED_DOMAINS:
        raise HTTPException(status_code=400, detail="invalid_domain")
    if body.grade_range not in ALLOWED_GRADE_RANGES:
        raise HTTPException(status_code=400, detail="invalid_grade_range")
    if body.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="invalid_status")
    if not body.questions or len(body.questions) == 0:
        raise HTTPException(status_code=400, detail="validation_error")
    # 题面字段完整性（B0 §9.2 C2.3）
    for q in body.questions:
        if not q.id or not q.dim or not q.text or not q.options:
            raise HTTPException(status_code=400, detail="validation_error")
        if len(q.options) < 2:
            raise HTTPException(status_code=400, detail="validation_error")
        for o in q.options:
            if not o.key or not o.text or not o.dim:
                raise HTTPException(status_code=400, detail="validation_error")

    d = AssessmentDefinition(
        name=body.name.strip(),
        domain=body.domain,
        grade_range=body.grade_range,
        version=body.version,
        status=body.status,
        consent_required=body.consent_required,
        description=body.description,
        questions=[q.model_dump() for q in body.questions],
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return ApiResponse(data=_def_record(db, d, include_questions=False), message="题组定义已创建")


@router.get("/definitions/{definition_id}", response_model=ApiResponse[DefinitionRecord])
def get_definition(
    definition_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    d = _get_definition(db, definition_id)
    return ApiResponse(data=DefinitionRecord(**_def_record(db, d, include_questions=True)), message="success")


@router.put("/definitions/{definition_id}", response_model=ApiResponse[DefinitionRecord])
def update_definition(
    definition_id: str,
    body: UpdateDefinitionRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_definition_can_manage(db, user_id)
    d = _get_definition(db, definition_id)
    if body.name is not None:
        d.name = body.name.strip()
    if body.domain is not None:
        if body.domain not in ALLOWED_DOMAINS:
            raise HTTPException(status_code=400, detail="invalid_domain")
        d.domain = body.domain
    if body.grade_range is not None:
        if body.grade_range not in ALLOWED_GRADE_RANGES:
            raise HTTPException(status_code=400, detail="invalid_grade_range")
        d.grade_range = body.grade_range
    if body.version is not None:
        d.version = body.version
    if body.status is not None:
        if body.status not in ALLOWED_STATUSES:
            raise HTTPException(status_code=400, detail="invalid_status")
        d.status = body.status
    if body.consent_required is not None:
        d.consent_required = body.consent_required
    if body.description is not None:
        d.description = body.description
    if body.questions is not None:
        if len(body.questions) == 0:
            raise HTTPException(status_code=400, detail="validation_error")
        d.questions = [q.model_dump() for q in body.questions]
    db.commit()
    db.refresh(d)
    return ApiResponse(data=DefinitionRecord(**_def_record(db, d, include_questions=True)), message="题组定义已更新")


@router.delete("/definitions/{definition_id}", response_model=ApiResponse[dict])
def delete_definition(
    definition_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _assert_definition_can_manage(db, user_id)
    d = _get_definition(db, definition_id)
    db.delete(d)
    db.commit()
    return ApiResponse(data={"id": definition_id}, message="题组定义已删除")


# ── 7.2 施测会话 API ──────────────────────────────────────

@router.post("/sessions", response_model=ApiResponse[SessionListData])
def create_sessions(
    body: CreateSessionRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if body.test_mode not in ALLOWED_TEST_MODES:
        raise HTTPException(status_code=400, detail="validation_error")

    d = _get_definition(db, body.definition_id)
    if d.status != "active":
        raise HTTPException(status_code=400, detail="definition_not_active")

    student_ids: list[str] = []
    if body.test_mode == "class_batch":
        if not body.student_ids or len(body.student_ids) == 0:
            raise HTTPException(status_code=400, detail="validation_error")
        if access_svc.is_student_user(db, user_id) and not access_svc.is_admin(db, user_id):
            raise HTTPException(status_code=403, detail="forbidden")
        student_ids = body.student_ids
        # teacher 限本班：逐个校验班级访问
        for sid in student_ids:
            st = _get_student(db, sid)
            if not access_svc.can_manage_class_batch(db, user_id, st.class_id):
                raise HTTPException(status_code=403, detail="not_own_class")
    else:  # self
        if not body.student_id:
            raise HTTPException(status_code=400, detail="validation_error")
        st = _get_student(db, body.student_id)
        me = access_svc.get_student_for_user(db, user_id)
        if not access_svc.is_admin(db, user_id):
            if not me or me.id != body.student_id:
                raise HTTPException(status_code=403, detail="forbidden")
        student_ids = [body.student_id]

    created: list[AssessmentSession] = []
    for sid in student_ids:
        s = AssessmentSession(
            student_id=sid,
            definition_id=body.definition_id,
            test_mode=body.test_mode,
            batch_id=body.batch_id,
            status="pending",
            proctored_by=None if body.test_mode == "self" else user_id,
            created_by=user_id,
        )
        db.add(s)
        created.append(s)
    db.commit()
    for s in created:
        db.refresh(s)

    return ApiResponse(
        data=SessionListData(
            rows=[SessionRecord(**_session_record(db, s)) for s in created],
            total=len(created),
        ),
        message=f"已创建 {len(created)} 个施测会话",
    )


@router.get("/sessions", response_model=ApiResponse[SessionListData])
def list_sessions(
    student_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(AssessmentSession)
    if student_id:
        q = q.filter(AssessmentSession.student_id == student_id)
    if status:
        q = q.filter(AssessmentSession.status == status)
    # 权限收紧：student 只看到自己；teacher 看到自己创建/本班
    if not access_svc.is_admin(db, user_id):
        me = access_svc.get_student_for_user(db, user_id)
        if me:
            q = q.filter(AssessmentSession.student_id == me.id)
        else:
            from app.utils.class_access import can_view_class
            rows = q.order_by(AssessmentSession.created_at.desc()).all()
            filtered = [s for s in rows if s.created_by == user_id or can_view_class(db, user_id, _student_class(db, s.student_id))]
            return ApiResponse(
                data=SessionListData(
                    rows=[SessionRecord(**_session_record(db, s)) for s in filtered],
                    total=len(filtered),
                ),
                message="success",
            )
    rows = q.order_by(AssessmentSession.created_at.desc()).all()
    return ApiResponse(
        data=SessionListData(
            rows=[SessionRecord(**_session_record(db, s)) for s in rows],
            total=len(rows),
        ),
        message="success",
    )


def _student_class(db: Session, student_id: str) -> Optional[str]:
    s = db.query(Student).filter(Student.id == student_id).first()
    return s.class_id if s else None


@router.get("/sessions/{session_id}", response_model=ApiResponse[SessionRecord])
def get_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    s = _get_session(db, session_id)
    if not _session_view_allowed(db, user_id, s):
        raise HTTPException(status_code=403, detail="forbidden")
    return ApiResponse(
        data=SessionRecord(**_session_record(db, s, include_questions=True)),
        message="success",
    )


def _session_view_allowed(db: Session, user_id: str, s: AssessmentSession) -> bool:
    """会话查看权限：本人（student）/ 创建者 / 管理角色 / 本班教师。"""
    if access_svc.is_admin(db, user_id):
        return True
    if s.created_by == user_id:
        return True
    me = access_svc.get_student_for_user(db, user_id)
    if me and me.id == s.student_id:
        return True
    from app.utils.class_access import can_view_class
    return can_view_class(db, user_id, _student_class(db, s.student_id))


@router.post("/sessions/{session_id}/start", response_model=ApiResponse[dict])
def start_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """pending → in_progress（学生开始作答，记录 taken_at）。"""
    s = _get_session(db, session_id)
    # 归属校验：仅会话当事人/创建者/本班教师/管理角色可 start（防任意用户凭 id 越权开启）
    if not _session_view_allowed(db, user_id, s):
        raise HTTPException(status_code=403, detail="forbidden")
    if s.status == "canceled":
        raise HTTPException(status_code=400, detail="invalid_status")
    if s.status == "submitted" or s.status == "graded":
        raise HTTPException(status_code=400, detail="invalid_status")
    if s.status == "in_progress":
        return ApiResponse(data={"id": s.id, "status": s.status}, message="会话已在作答中")
    s.status = "in_progress"
    s.taken_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)
    return ApiResponse(data={"id": s.id, "status": s.status}, message="会话已开始作答")


@router.post("/sessions/{session_id}/cancel", response_model=ApiResponse[dict])
def cancel_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """仅 pending/in_progress 可取消。"""
    s = _get_session(db, session_id)
    if s.status in ("submitted", "graded"):
        raise HTTPException(status_code=400, detail="invalid_status")
    # 权限：会话创建者 / super_admin / org_admin（B0 §7.2）
    if not (access_svc.is_super_admin(db, user_id) or access_svc.is_org_admin(db, user_id) or s.created_by == user_id):
        raise HTTPException(status_code=403, detail="forbidden")
    s.status = "canceled"
    db.commit()
    db.refresh(s)
    return ApiResponse(data={"id": s.id, "status": s.status, "updated_at": _dt(s.updated_at)}, message="会话已取消")


# ── 7.3 作答与计分 API ────────────────────────────────────

@router.post("/sessions/{session_id}/answers", response_model=ApiResponse[SubmitAnswerResult])
def submit_answers(
    session_id: str,
    body: SubmitAnswersRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    s = _get_session(db, session_id)
    # 归属校验：仅会话当事人/创建者/本班教师/管理角色可作答（防替他人作答生成结果）
    if not _session_view_allowed(db, user_id, s):
        raise HTTPException(status_code=403, detail="forbidden")
    if s.status in ("submitted", "graded"):
        raise HTTPException(status_code=400, detail="already_submitted")
    if s.status == "canceled":
        raise HTTPException(status_code=400, detail="invalid_status")

    d = _get_definition(db, s.definition_id)
    questions: list[dict] = d.questions or []

    answers = {a.question_id: a.option_key for a in body.answers}
    if not answers:
        raise HTTPException(status_code=400, detail="validation_error")
    matched = scoring_svc.validate_answers(questions, answers)
    if matched == 0:
        raise HTTPException(status_code=400, detail="no_match")

    # 计分（等权累加 + 归一化 + 白名单闸门 + 冲突裁决）
    try:
        score = scoring_svc.score_answers(questions, answers)
    except Exception as exc:  # pragma: no cover
        logger.exception("[assessment] scoring_error: %s", exc)
        raise HTTPException(status_code=500, detail="scoring_error")

    tag_schema = scoring_svc.build_tag_schema(score)
    raw_score = scoring_svc.build_raw_score(questions, answers, score)
    consent = scoring_svc.default_guardian_consent()
    if not d.consent_required:
        # 题组无需监护人同意：仍写 not_required（B0 §6.2 首测默认），不默认 granted
        consent = consent_svc.default_consent()

    result = AssessmentResult(
        student_id=s.student_id,
        definition_id=d.id,
        session_id=s.id,
        domain=d.domain,
        purpose="anchor",
        tag_schema=tag_schema,
        raw_score=raw_score,
        guardian_consent=consent,
        created_by=user_id,
    )
    db.add(result)
    # 先 flush 拿到 result.id（Python 侧 default 在 INSERT 时生效），供明细表引用
    db.flush()

    # 逐题明细（assessment_answers 表，可选启用；B0 §2.4 推荐写 raw_score，这里二者都留）
    for q in questions:
        qid = q.get("id")
        opt_key = answers.get(qid)
        if not opt_key:
            continue
        selected = next((o for o in q.get("options", []) if o.get("key") == opt_key), None)
        if not selected:
            continue
        db.add(AssessmentAnswer(
            result_id=result.id,
            question_id=qid,
            option_key=opt_key,
            dim=q.get("dim", ""),
            option_dim=selected.get("dim"),
        ))

    s.status = "submitted"
    s.submitted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(result)

    return ApiResponse(
        data=SubmitAnswerResult(
            result_id=result.id,
            session_id=s.id,
            labels=score.get("labels", []),
            dimension_percents=score.get("dimension_percents", {}),
            total_answered=score.get("total_answered", 0),
            consent_status=consent.get("status", "not_required"),
        ),
        message="答案已提交，锚点结果已写入",
    )


# ── 7.4 锚点结果 API ──────────────────────────────────────

@router.get("/students/{student_id}/results", response_model=ApiResponse[ResultListData])
def list_results(
    student_id: str,
    domain: Optional[str] = Query(None),
    include_withdrawn: bool = Query(False),
    include_raw: bool = Query(False),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    st = _get_student(db, student_id)

    q = db.query(AssessmentResult).filter(AssessmentResult.student_id == student_id)
    if domain:
        q = q.filter(AssessmentResult.domain == domain)
    rows_all = q.order_by(AssessmentResult.created_at.desc()).all()

    # 权限与可见性闸门
    rows = []
    for r in rows_all:
        consent_status = (r.guardian_consent or {}).get("status", "not_required")
        if consent_status == "withdrawn" and not include_withdrawn:
            continue
        if not _result_view_allowed(db, user_id, st, r, consent_status):
            continue
        rows.append(r)

    return ApiResponse(
        data=ResultListData(
            rows=[ResultRecord(**_result_record(db, r, include_raw=include_raw)) for r in rows],
            total=len(rows),
        ),
        message="success",
    )


def _result_view_allowed(db: Session, user_id: str, student: Student, result: AssessmentResult, consent_status: str) -> bool:
    """结果查看权限（B0 §6.3 + 附录 B）：
      - 管理角色（super/org/school_admin）放行
      - 学生本人
      - 该生班级教师/mentor
      - parent：已绑定（active）且 consent=granted 才可见
    """
    if access_svc.is_admin(db, user_id):
        return True
    me = access_svc.get_student_for_user(db, user_id)
    if me and me.id == student.id:
        return True
    from app.utils.class_access import can_view_class
    if access_svc.is_teacher(db, user_id) and can_view_class(db, user_id, student.class_id):
        return True
    # parent：绑定 + granted
    if consent_status == "granted":
        bound = (
            db.query(ParentStudent.id)
            .filter(
                ParentStudent.parent_id == user_id,
                ParentStudent.student_id == student.id,
                ParentStudent.status == "active",
            )
            .first()
        )
        if bound:
            return True
    return False


# ── 7.4.2 班级批量同意状态 API ────────────────────────────

class ConsentOverviewRecord(BaseModel):
    """班级批量同意总览中的单条记录（对应该生最新一条 result）。"""
    student_id: str
    student_name: str
    student_number: Optional[str] = None
    has_result: bool
    result_id: Optional[str] = None
    definition_name: Optional[str] = None
    domain: Optional[str] = None
    version: int
    consent_status: str
    created_at: Optional[str] = None


class ConsentsListData(BaseModel):
    rows: List[ConsentOverviewRecord]
    total: int


@router.get("/classes/{class_id}/consents", response_model=ApiResponse[ConsentsListData])
def list_class_consents(
    class_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """班级批量同意状态：返回该班全体学生的监护人同意总览。

    consent_status 取该生最新一条 result(created_at desc) 的 guardian_consent.status；
    该生无任何 result 时 has_result=false、consent_status="not_required"。
    权限口径同 listStudentsByClass：管理角色放行；教师须 can_view_class；其余 403。
    """
    c = db.query(Class).filter(Class.id == class_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="class_not_found")
    from app.utils.class_access import can_view_class

    if not (
        access_svc.is_admin(db, user_id)
        or (access_svc.is_teacher(db, user_id) and can_view_class(db, user_id, class_id))
    ):
        raise HTTPException(status_code=403, detail="forbidden")

    students = (
        db.query(Student)
        .filter(Student.class_id == class_id)
        .order_by(Student.student_number)
        .all()
    )
    # 单次查询该班全部结果，按 created_at desc 逐条落表，每个学生首条即最新
    latest_by_student: dict[str, AssessmentResult] = {}
    if students:
        results = (
            db.query(AssessmentResult)
            .filter(AssessmentResult.student_id.in_([s.id for s in students]))
            .order_by(AssessmentResult.created_at.desc())
            .all()
        )
        for r in results:
            if r.student_id not in latest_by_student:
                latest_by_student[r.student_id] = r

    rows: list[ConsentOverviewRecord] = []
    for s in students:
        r = latest_by_student.get(s.id)
        if r is None:
            rows.append(
                ConsentOverviewRecord(
                    student_id=s.id,
                    student_name=s.name,
                    student_number=s.student_number or None,
                    has_result=False,
                    result_id=None,
                    definition_name=None,
                    domain=None,
                    version=0,
                    consent_status="not_required",
                    created_at=None,
                )
            )
            continue
        consent = r.guardian_consent or {}
        rows.append(
            ConsentOverviewRecord(
                student_id=s.id,
                student_name=s.name,
                student_number=s.student_number or None,
                has_result=True,
                result_id=r.id,
                definition_name=_definition_name(db, r.definition_id),
                domain=r.domain,
                version=int(consent.get("version", 0) or 0),
                consent_status=consent.get("status", "not_required"),
                created_at=_dt(r.created_at),
            )
        )

    return ApiResponse(
        data=ConsentsListData(rows=rows, total=len(rows)),
        message="success",
    )


# ── 7.5 监护人同意 API ────────────────────────────────────

@router.post("/students/{student_id}/results/{result_id}/grant", response_model=ApiResponse[dict])
def grant_consent(
    student_id: str,
    result_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """首次授予监护人同意（not_required → granted）。B0 §6.1 状态机前置步骤。"""
    st = _get_student(db, student_id)
    r = db.query(AssessmentResult).filter(AssessmentResult.id == result_id, AssessmentResult.student_id == student_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="result_not_found")
    if not access_svc.can_consent_operate(db, user_id, st):
        raise HTTPException(status_code=403, detail="forbidden")

    consent = r.guardian_consent or consent_svc.default_consent()
    old_status = consent.get("status", "not_required")
    try:
        new_consent, msg = consent_svc.grant(consent)
    except ValueError as exc:
        if str(exc) == "withdrawn_use_restore":
            raise HTTPException(status_code=400, detail="not_withdrawn")
        raise HTTPException(status_code=400, detail="invalid_consent")

    r.guardian_consent = new_consent
    db.commit()
    db.refresh(r)
    _log_consent_access(db, user_id, student_id, r.id, old_status, new_consent.get("status", old_status))
    return ApiResponse(
        data={"id": r.id, "guardian_consent": r.guardian_consent, "updated_at": _dt(r.updated_at)},
        message=msg,
    )


@router.post("/students/{student_id}/results/{result_id}/withdraw", response_model=ApiResponse[dict])
def withdraw_consent(
    student_id: str,
    result_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    st = _get_student(db, student_id)
    r = db.query(AssessmentResult).filter(AssessmentResult.id == result_id, AssessmentResult.student_id == student_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="result_not_found")
    if not access_svc.can_consent_operate(db, user_id, st):
        raise HTTPException(status_code=403, detail="forbidden")

    consent = r.guardian_consent or consent_svc.default_consent()
    old_status = consent.get("status", "not_required")
    try:
        new_consent, msg = consent_svc.withdraw(consent)
    except ValueError as exc:
        code = str(exc)
        if code == "already_withdrawn":
            raise HTTPException(status_code=400, detail="already_withdrawn")
        raise HTTPException(status_code=400, detail="not_required")

    r.guardian_consent = new_consent
    db.commit()
    db.refresh(r)
    _log_consent_access(db, user_id, student_id, r.id, old_status, new_consent.get("status", old_status))
    return ApiResponse(
        data={"id": r.id, "guardian_consent": r.guardian_consent, "updated_at": _dt(r.updated_at)},
        message=msg,
    )


@router.post("/students/{student_id}/results/{result_id}/restore", response_model=ApiResponse[dict])
def restore_consent(
    student_id: str,
    result_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    st = _get_student(db, student_id)
    r = db.query(AssessmentResult).filter(AssessmentResult.id == result_id, AssessmentResult.student_id == student_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="result_not_found")
    if not access_svc.can_consent_operate(db, user_id, st):
        raise HTTPException(status_code=403, detail="forbidden")

    consent = r.guardian_consent or consent_svc.default_consent()
    old_status = consent.get("status", "not_required")
    try:
        new_consent, msg = consent_svc.restore(consent)
    except ValueError as exc:
        if str(exc) == "not_withdrawn":
            raise HTTPException(status_code=400, detail="not_withdrawn")
        raise HTTPException(status_code=400, detail="invalid_consent")

    r.guardian_consent = new_consent
    db.commit()
    db.refresh(r)
    _log_consent_access(db, user_id, student_id, r.id, old_status, new_consent.get("status", old_status))
    return ApiResponse(
        data={"id": r.id, "guardian_consent": r.guardian_consent, "updated_at": _dt(r.updated_at)},
        message=msg,
    )


# ── 7.6 家长-学生绑定 API（/api/v1/parent-students）────────

@parent_router.post("", response_model=ApiResponse[ParentStudentRecord])
def create_parent_student(
    body: CreateParentStudentRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    # 权限：teacher / school_admin / org_admin / super_admin
    if not (access_svc.is_admin(db, user_id) or access_svc.is_teacher(db, user_id)):
        raise HTTPException(status_code=403, detail="forbidden")
    if body.relation not in ALLOWED_RELATIONS:
        raise HTTPException(status_code=400, detail="validation_error")
    parent = db.query(User).filter(User.id == body.parent_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="parent_not_found")
    _get_student(db, body.student_id)

    exists = (
        db.query(ParentStudent)
        .filter(ParentStudent.parent_id == body.parent_id, ParentStudent.student_id == body.student_id)
        .first()
    )
    if exists:
        # 幂等：重复绑定返回既有记录
        return ApiResponse(data=ParentStudentRecord(**_parent_record(db, exists)), message="家长绑定成功")

    p = ParentStudent(
        parent_id=body.parent_id,
        student_id=body.student_id,
        relation=body.relation,
        status="active",
        created_by=user_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return ApiResponse(data=ParentStudentRecord(**_parent_record(db, p)), message="家长绑定成功")


@parent_router.get("", response_model=ApiResponse[ParentStudentListData])
def list_parent_students(
    parent_id: Optional[str] = Query(None),
    student_id: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    q = db.query(ParentStudent)
    if parent_id:
        q = q.filter(ParentStudent.parent_id == parent_id)
    if student_id:
        q = q.filter(ParentStudent.student_id == student_id)

    # 权限：parent 本人只看自己绑定；teacher 本班；admin 全量
    if not access_svc.is_admin(db, user_id):
        if access_svc.is_parent_user(db, user_id):
            q = q.filter(ParentStudent.parent_id == user_id)
        else:
            from app.utils.class_access import can_view_class
            rows_all = q.order_by(ParentStudent.created_at.desc()).all()
            filtered = []
            for p in rows_all:
                cid = _student_class(db, p.student_id)
                if cid and can_view_class(db, user_id, cid):
                    filtered.append(p)
            return ApiResponse(
                data=ParentStudentListData(
                    rows=[ParentStudentRecord(**_parent_record(db, p)) for p in filtered],
                    total=len(filtered),
                ),
                message="success",
            )
    rows = q.order_by(ParentStudent.created_at.desc()).all()
    return ApiResponse(
        data=ParentStudentListData(
            rows=[ParentStudentRecord(**_parent_record(db, p)) for p in rows],
            total=len(rows),
        ),
        message="success",
    )
