"""分层推送（nav/ai-layered）：真实名单/分层/设置/推送/统计。

数据落点：
- 分层 → students.tier（与 PATCH /students 同一列）；
- 班级设置（分层内容/推送时机/通知策略/模板） → system_config KV（key=layered_push:{class_id}[:subject]）；
- 推送轮次/任务 → student_tasks（task_type="layered_push"，evidence_json 记轮次与发送结果）。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.class_model import Class
from app.models.exam import Exam
from app.models.exam_score import ExamScore
from app.models.student import Student
from app.models.student_analysis import StudentAnalysis
from app.models.student_task import StudentTask
from app.models.system_config import SystemConfig
from app.schemas.common import ApiResponse
from app.schemas.layered_push import (
    PushRequest,
    PushStartResult,
    ReportRequest,
    RosterStudent,
    SettingsPutRequest,
    SyncRosterRequest,
    TaskStatusPatch,
    TestPushRequest,
    TiersAutoRequest,
    TiersAutoResult,
    TiersBatchRequest,
    TiersBatchResult,
    UrgeRequest,
)
from app.services import layered_push_service as svc
from app.utils.class_access import can_manage_students, can_view_class, can_view_student_pii

router = APIRouter(prefix="/layered-push", tags=["layered-push"])

DEFAULT_THRESHOLDS = svc.DEFAULT_THRESHOLDS
_VALID_TIERS = svc.VALID_TIERS
SETTINGS_KEY_PREFIX = "layered_push:"
SETTINGS_CATEGORY = "layered_push"


def _settings_key(class_id: str) -> str:
    return f"{SETTINGS_KEY_PREFIX}{class_id}"


# 分层打分口径已抽到 layered_push_service（批改后自动分层共用），这里保留旧名兼容
_avg_scores = svc.avg_scores
_analysis_scores = svc.analysis_scores
_resolve_score = svc.resolve_score


@router.get("/roster", response_model=ApiResponse[List[RosterStudent]])
def get_roster(
    class_id: str = Query(..., description="班级 ID"),
    subject: Optional[str] = Query(None, description="学科（成绩过滤）"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """真实名单：学生 + 平均分 + 当前分层 + 钉钉同步状态。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    students = (
        db.query(Student)
        .filter(Student.class_id == class_id)
        .order_by(asc(Student.student_number))
        .all()
    )
    avg = _avg_scores(db, class_id, subject)
    fb = _analysis_scores(db, class_id, subject)
    show_pii = can_view_student_pii(db, user_id, class_id)
    rows = [
        RosterStudent(
            id=s.id,
            name=s.name,
            student_number=s.student_number,
            tier=s.tier,
            score=_resolve_score(s, avg, fb),
            dingtalk_synced=bool((getattr(s, "dingtalk_userid", None) or "").strip()),
            parent_name=(getattr(s, "parent_name", None) or None) if show_pii else None,
            parent_phone=(getattr(s, "parent_phone", None) or None) if show_pii else None,
        )
        for s in students
    ]
    return ApiResponse(data=rows)


@router.post("/tiers/auto", response_model=ApiResponse[TiersAutoResult])
def tiers_auto(
    body: TiersAutoRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """按平均分自动分层：score>=a → A，>=b → B，其余 C；无成绩者保持原分层并计数。

    阈值：请求覆盖 > 分层推送设置 > 默认 80/60；用过的阈值写回设置（批改后自动分层沿用同一套）。
    """
    if not can_manage_students(db, user_id, body.class_id):
        raise HTTPException(status_code=403, detail="仅班主任可调整分层")
    try:
        result = svc.apply_auto_tiers(db, body.class_id, body.subject, body.thresholds)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e) or "分层阈值不合法")
    try:
        svc.update_stored_thresholds(db, body.class_id, body.subject, result["thresholds"], user_id)
    except Exception as e:
        print(f"[layered_push] 回写分层阈值失败: {body.class_id}: {e}")
    return ApiResponse(
        data=TiersAutoResult(
            updated=result["updated"], no_score=result["no_score"], tiers=result["tiers"]
        )
    )


@router.post("/tiers/batch", response_model=ApiResponse[TiersBatchResult])
def tiers_batch(
    body: TiersBatchRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """拖拽/批量调整分层（仅本班学生、合法分层值）。"""
    if not can_manage_students(db, user_id, body.class_id):
        raise HTTPException(status_code=403, detail="仅班主任可调整分层")
    if not body.moves:
        return ApiResponse(data=TiersBatchResult(updated=0))
    ids = {m.student_id for m in body.moves}
    rows = (
        db.query(Student)
        .filter(Student.class_id == body.class_id, Student.id.in_(ids))
        .all()
    )
    found = {r.id: r for r in rows}
    updated = 0
    for m in body.moves:
        s = found.get(m.student_id)
        if not s:
            continue
        tier = m.tier.upper()
        if tier not in _VALID_TIERS:
            raise HTTPException(status_code=400, detail="分层取值须为 A/B/C")
        if s.tier != tier:
            s.tier = tier
            updated += 1
    db.commit()
    return ApiResponse(data=TiersBatchResult(updated=updated))


@router.get("/settings", response_model=ApiResponse[Optional[dict]])
def get_settings(
    class_id: str = Query(..., description="班级 ID"),
    subject: Optional[str] = Query(None, description="学科（按学科分别存）"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """读取本班分层推送设置；未存过返回 null（前端套默认模板）。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    value = svc.load_settings(db, class_id, subject)
    return ApiResponse(data=(value or None))


@router.put("/settings", response_model=ApiResponse[dict])
def put_settings(
    body: SettingsPutRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """全量保存本班分层推送设置（容忍任意 JSON，读侧合并默认值）。"""
    if not can_manage_students(db, user_id, body.class_id):
        raise HTTPException(status_code=403, detail="仅班主任可保存推送设置")
    if not isinstance(body.settings, dict):
        raise HTTPException(status_code=400, detail="settings 须为对象")
    key = svc.settings_key(body.class_id, body.subject)
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row is None:
        row = SystemConfig(
            key=key,
            value=body.settings,
            label="分层推送设置",
            category=SETTINGS_CATEGORY,
            updated_by=user_id,
        )
        db.add(row)
    else:
        row.value = body.settings
        row.updated_by = user_id
    db.commit()
    return ApiResponse(data={"saved": True})


# ── 推送 / 预览 / 统计 ──────────────────────────────────


@router.get("/message-preview", response_model=ApiResponse[dict])
def message_preview(
    class_id: str = Query(...),
    subject: str = Query(""),
    tier: str = Query("A"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """预览某一层真实会发出的钉钉消息（与推送同一拼装函数）。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    cls = db.query(Class).filter(Class.id == class_id).first()
    cfg = svc.load_settings(db, class_id, subject)
    content = svc._tier_content(cfg, tier)
    count = sum(
        1
        for s in db.query(Student).filter(Student.class_id == class_id).all()
        if (s.tier or "B").upper() == tier.upper()
    )
    title, body = svc.compose_push(
        cls.name if cls else "班级",
        subject or "—",
        tier.upper(),
        content,
        count,
        str(cfg.get("form_type") or "h5"),
    )
    return ApiResponse(data={"title": title, "body_markdown": body})


@router.post("/test-push", response_model=ApiResponse[dict])
def test_push(
    body: TestPushRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """测试推送：给当前老师本人发配置摘要，验证钉钉通道。"""
    if not can_manage_students(db, user_id, body.class_id):
        raise HTTPException(status_code=403, detail="仅班主任可发起推送")
    result = svc.send_test_push(body.class_id, body.subject or "", user_id)
    if not result.get("ok") and "未接入" in str(result.get("message")):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return ApiResponse(data=result)


@router.post("/push", response_model=ApiResponse[PushStartResult])
def push(
    body: PushRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """确认推送：立即返回轮次，后台线程逐学生发送并回写结果。"""
    if not can_manage_students(db, user_id, body.class_id):
        raise HTTPException(status_code=403, detail="仅班主任可发起推送")
    if not svc.dingtalk_ready():
        raise HTTPException(status_code=400, detail="钉钉未接入（缺 CORP_ID/APP_KEY/APP_SECRET/AGENT_ID）")
    roster = db.query(Student).filter(Student.class_id == body.class_id).all()
    if not roster and not body.notice_only:
        raise HTTPException(status_code=400, detail="该班暂无学生，无法推送")
    try:
        info = svc.start_push_round(
            body.class_id,
            body.subject or "",
            user_id,
            notice_only=body.notice_only,
            notice_text=(body.notice_text or "").strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ApiResponse(
        data=PushStartResult(
            round_id=info["round_id"],
            total=info["total"],
            created_tasks=info["created_tasks"],
            notice_only=bool(info.get("notice_only")),
        )
    )


@router.post("/urge", response_model=ApiResponse[dict])
def urge(
    body: UrgeRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """催交：对最近一轮未完成的学生（+家长）发提醒。"""
    if not can_manage_students(db, user_id, body.class_id):
        raise HTTPException(status_code=403, detail="仅班主任可催交")
    if not svc.dingtalk_ready():
        raise HTTPException(status_code=400, detail="钉钉未接入")
    counts = svc.run_urge(body.class_id, body.subject or "", tier=body.tier, user_id=user_id)
    return ApiResponse(data=counts)


@router.get("/stats", response_model=ApiResponse[dict])
def stats(
    class_id: str = Query(...),
    subject: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """最近一轮的分层推送统计（发送/完成/未完成名单）。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    return ApiResponse(data=svc.collect_stats(db, class_id, subject))


@router.get("/rounds", response_model=ApiResponse[List[dict]])
def rounds(
    class_id: str = Query(...),
    subject: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """历史推送轮次（新→旧）。"""
    if not can_view_class(db, user_id, class_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    return ApiResponse(data=svc.collect_rounds(db, class_id, subject))


@router.patch("/tasks/{task_id}/status", response_model=ApiResponse[dict])
def patch_task_status(
    task_id: str,
    body: TaskStatusPatch,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """教师标记任务完成/未完成（当前无学生端提交入口，完成状态以教师为准）。"""
    task = db.query(StudentTask).filter(StudentTask.id == task_id).first()
    if task is None or task.task_type != svc.TASK_TYPE:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not can_manage_students(db, user_id, task.class_id):
        raise HTTPException(status_code=403, detail="仅班主任可更新完成状态")
    if body.status == "completed":
        task.status = "completed"
        task.completed_at = datetime.now()
    else:
        task.status = "pending"
        task.completed_at = None
    db.commit()
    return ApiResponse(data={"id": task.id, "status": task.status})


@router.post("/report", response_model=ApiResponse[dict])
def report(
    body: ReportRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """生成真实统计报告并发钉钉（本人/班主任）。"""
    if not can_view_class(db, user_id, body.class_id):
        raise HTTPException(status_code=404, detail="班级不存在")
    result = svc.send_report(body.class_id, body.subject or "", body.kind, body.recipient, user_id)
    if not result.get("ok") and "未接入" in str(result.get("message")):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return ApiResponse(data=result)


@router.post("/sync-roster", response_model=ApiResponse[dict])
def sync_roster(
    body: SyncRosterRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """按班级绑定的钉钉部门整班刷新名单（更新已有学生的钉钉绑定/姓名/手机号，补建缺失学生）。"""
    if not can_manage_students(db, user_id, body.class_id):
        raise HTTPException(status_code=403, detail="仅班主任可同步名单")
    cls = db.query(Class).filter(Class.id == body.class_id).first()
    if cls is None:
        raise HTTPException(status_code=404, detail="班级不存在")
    if not cls.dingtalk_dept_id:
        raise HTTPException(
            status_code=400,
            detail="该班未绑定钉钉部门，请在 设置·数据同步 中选择部门",
        )
    try:
        dept_id = int(cls.dingtalk_dept_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="班级绑定的钉钉部门 ID 不合法")
    if dept_id == 1:
        raise HTTPException(status_code=400, detail="班级不能绑定根部门")

    from app.routers.dingtalk_sync import _get_user_detail, _list_dept_users

    try:
        members = _list_dept_users(dept_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"拉取钉钉部门成员失败：{e}")

    created = updated = 0
    for m in members:
        uid = (m.get("userid") or "").strip()
        if not uid:
            continue
        try:
            detail = _get_user_detail(uid)
        except HTTPException:
            detail = m
        name = (detail.get("name") or m.get("name") or "").strip()
        mobile = (detail.get("mobile") or "").strip()

        stu = (
            db.query(Student)
            .filter(Student.class_id == cls.id, Student.dingtalk_userid == uid)
            .first()
        )
        if stu is None and name:
            stu = (
                db.query(Student)
                .filter(
                    Student.class_id == cls.id,
                    Student.name == name,
                    Student.dingtalk_userid.is_(None),
                )
                .first()
            )
        if stu is None:
            db.add(
                Student(
                    class_id=cls.id,
                    user_id=cls.user_id,
                    school_id=cls.school_id,
                    name=name or f"钉钉成员{uid}",
                    student_number=mobile or "",
                    phone=mobile or None,
                    dingtalk_userid=uid,
                    tier="B",
                    status="正常",
                )
            )
            created += 1
        else:
            if name:
                stu.name = name
            if mobile:
                stu.student_number = mobile
                stu.phone = mobile
            stu.dingtalk_userid = uid
            updated += 1
    db.commit()
    cls.student_count = db.query(Student).filter(Student.class_id == cls.id).count()
    db.commit()
    return ApiResponse(
        data={"created": created, "updated": updated, "total": cls.student_count}
    )
