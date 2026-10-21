# -*- coding: utf-8 -*-
"""分层推送（nav/ai-layered）核心服务：消息拼装、推送轮次、发送、统计、定时任务。

约定：
- 设置存 system_config KV（key=layered_push:{class_id}[:subject]，category=layered_push）；
- 每轮推送为每名学生建一条 student_tasks（task_type="layered_push"），
  evidence_json 记 round_id/tier/subject/push 发送结果/提醒标记；
- 钉钉发送统一走 send_work_notice_ex（asyncsend_v2，返回 task_id 留痕），
  任何失败只记 evidence 与日志，绝不外抛打断主流程；
- 日志只打 errcode/数量，不打 token/密钥/手机号。
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.class_model import Class
from app.models.exam import Exam
from app.models.exam_score import ExamScore
from app.models.student import Student
from app.models.student_analysis import StudentAnalysis
from app.models.student_task import StudentTask
from app.models.system_config import SystemConfig
from app.services.dingtalk_notify import (
    _get_userid_by_mobile,
    _resolve_dingtalk_userid,
    send_work_notice_ex,
)

TASK_TYPE = "layered_push"
SETTINGS_PREFIX = "layered_push:"
SETTINGS_CATEGORY = "layered_push"
_WEEKDAY_ZH = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
_TIER_ZH = {"A": "A层", "B": "B层", "C": "C层"}
_MAX_UNFINISHED_NAMES = 10
# 催办/提醒单次发送上限，防钉钉限流
_SEND_CAP = 50


def dingtalk_ready() -> bool:
    """四项钉钉配置缺一不可（与 notify_grading_done 同一门槛）。"""
    return bool(
        settings.DINGTALK_CORP_ID
        and settings.DINGTALK_APP_KEY
        and settings.DINGTALK_APP_SECRET
        and settings.DINGTALK_AGENT_ID
    )


# ── 设置读写 ──────────────────────────────────────────────

def settings_key(class_id: str, subject: Optional[str] = None) -> str:
    key = f"{SETTINGS_PREFIX}{class_id}"
    if subject:
        key = f"{key}:{subject.strip()}"
    return key


def load_settings(db: Session, class_id: str, subject: Optional[str] = None) -> Dict[str, Any]:
    """读取存储的设置（可能为 None/旧结构），返回 dict；未存过返回 {}。"""
    row = db.query(SystemConfig).filter(SystemConfig.key == settings_key(class_id, subject)).first()
    if row is None and subject:
        # 兼容旧 key（不带学科）
        row = db.query(SystemConfig).filter(SystemConfig.key == settings_key(class_id)).first()
    value = row.value if row else None
    return dict(value) if isinstance(value, dict) else {}


def save_settings(
    db: Session, class_id: str, subject: Optional[str], value: Dict[str, Any], user_id: str
) -> None:
    key = settings_key(class_id, subject)
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row is None:
        db.add(
            SystemConfig(
                key=key,
                value=value,
                label="分层推送设置",
                category=SETTINGS_CATEGORY,
                updated_by=user_id,
            )
        )
    else:
        row.value = value
        row.updated_by = user_id
    db.commit()


# ── 按成绩自动分层（tiers_auto 端点与「批改后自动分层」共用） ──────────────

DEFAULT_THRESHOLDS = {"a": 80.0, "b": 60.0}
VALID_TIERS = ("A", "B", "C")


def avg_scores(db: Session, class_id: str, subject: Optional[str] = None) -> Dict[str, float]:
    """学生平均分：exam_scores 聚合（可按学科过滤），{student_id: avg}。"""
    q = (
        db.query(ExamScore.student_id, func.avg(ExamScore.score))
        .join(Student, Student.id == ExamScore.student_id)
        .join(Exam, Exam.id == ExamScore.exam_id)
        .filter(Student.class_id == class_id, ExamScore.score.isnot(None))
    )
    if subject:
        q = q.filter(Exam.subject == subject)
    return {sid: float(avg) for sid, avg in q.group_by(ExamScore.student_id).all()}


def analysis_scores(db: Session, class_id: str, subject: Optional[str] = None) -> Dict[str, float]:
    """兜底：student_analysis.current_score（按学生姓名），{student_name: score}。"""
    q = db.query(StudentAnalysis.student_name, StudentAnalysis.current_score).filter(
        StudentAnalysis.class_id == class_id,
        StudentAnalysis.current_score.isnot(None),
    )
    if subject:
        q = q.filter(StudentAnalysis.subject == subject)
    return {name: float(v) for name, v in q.all()}


def resolve_score(student: Student, avg: Dict[str, float], fb: Dict[str, float]) -> Optional[float]:
    score = avg.get(student.id)
    if score is None:
        score = fb.get(student.name)
    return round(score, 1) if score is not None else None


def merge_thresholds(stored: Any, overrides: Any = None) -> Dict[str, float]:
    """阈值合并：默认 80/60 ← 设置里存的（坏值忽略）← 显式覆盖（坏值报错）。"""
    merged: Dict[str, float] = dict(DEFAULT_THRESHOLDS)
    if isinstance(stored, dict):
        for k, v in stored.items():
            key = str(k).strip().lower()
            if key not in ("a", "b"):
                continue
            try:
                merged[key] = float(v)
            except (TypeError, ValueError):
                continue
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("分层阈值不合法")
    for k, v in (overrides or {}).items():
        key = str(k).strip().lower()
        if key not in ("a", "b"):
            continue
        try:
            merged[key] = float(v)
        except (TypeError, ValueError):
            raise ValueError("分层阈值不合法")
    return merged


def resolve_thresholds(
    db: Session, class_id: str, subject: Optional[str] = None, overrides: Any = None
) -> Dict[str, float]:
    """阈值优先级：显式覆盖 > 分层推送设置 thresholds > 默认 80/60。"""
    stored = load_settings(db, class_id, subject).get("thresholds")
    return merge_thresholds(stored, overrides)


def apply_auto_tiers(
    db: Session,
    class_id: str,
    subject: Optional[str] = None,
    thresholds: Any = None,
) -> Dict[str, Any]:
    """按成绩自动分层：score>=a → A，>=b → B，其余 C；无成绩者保持原分层并计数。

    thresholds=None 时用分层推送设置里的阈值（缺省 80/60）；传 dict 则作为显式覆盖。
    commit 本函数内完成。返回 {updated, no_score, tiers, thresholds}。
    """
    lines = resolve_thresholds(db, class_id, subject, thresholds)
    a_line, b_line = lines["a"], lines["b"]
    if not b_line < a_line:
        raise ValueError("分层阈值不合法：A 线必须高于 B 线")

    students = db.query(Student).filter(Student.class_id == class_id).all()
    avg = avg_scores(db, class_id, subject)
    fb = analysis_scores(db, class_id, subject)

    updated = 0
    no_score = 0
    buckets: Dict[str, List[str]] = {"A": [], "B": [], "C": []}
    for s in students:
        score = resolve_score(s, avg, fb)
        if score is None:
            no_score += 1
            tier = (s.tier or "B").upper()
            if tier not in VALID_TIERS:
                tier = "B"
        else:
            tier = "A" if score >= a_line else ("B" if score >= b_line else "C")
            if s.tier != tier:
                s.tier = tier
                updated += 1
        buckets.setdefault(tier, []).append(s.id)
    db.commit()
    return {
        "updated": updated,
        "no_score": no_score,
        "tiers": buckets,
        "thresholds": {"a": a_line, "b": b_line},
    }


def update_stored_thresholds(
    db: Session, class_id: str, subject: Optional[str], thresholds: Dict[str, float], user_id: str
) -> None:
    """把实际使用的分层阈值写回设置（写进 load_settings 命中的那行，避免拆散/遮蔽整份设置）。"""
    key = settings_key(class_id, subject)
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row is None and subject:
        key = settings_key(class_id)
        row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row is None:
        row = SystemConfig(
            key=settings_key(class_id, subject),
            value={"thresholds": dict(thresholds)},
            label="分层推送设置",
            category=SETTINGS_CATEGORY,
            updated_by=user_id,
        )
        db.add(row)
    else:
        value = dict(row.value) if isinstance(row.value, dict) else {}
        value["thresholds"] = dict(thresholds)
        row.value = value
        row.updated_by = user_id
    db.commit()


def _tier_content(settings_value: Dict[str, Any], tier: str) -> Dict[str, Any]:
    tiers = settings_value.get("tiers")
    if not isinstance(tiers, dict):
        return {}
    content = tiers.get(tier)
    return dict(content) if isinstance(content, dict) else {}


def _requirements_of(content: Dict[str, Any]) -> Dict[str, bool]:
    return {
        "parent_sign": bool(content.get("require_parent_sign")),
        "photo": bool(content.get("require_photo")),
        "voice": bool(content.get("require_voice")),
    }


def _deadline_text(content: Dict[str, Any]) -> str:
    try:
        weekday = int(content.get("deadline_weekday") or 5)
    except (TypeError, ValueError):
        weekday = 5
    weekday = min(max(weekday, 1), 7)
    time_str = str(content.get("deadline_time") or "22:00")
    return f"{_WEEKDAY_ZH[weekday]} {time_str}"


def _next_deadline_date(content: Dict[str, Any], now: Optional[datetime] = None) -> Optional[Any]:
    """按截止星期+时间算下一个截止日期（已过点则顺延下周），返回 date。"""
    now = now or datetime.now()
    try:
        weekday = int(content.get("deadline_weekday") or 5)
    except (TypeError, ValueError):
        weekday = 5
    weekday = min(max(weekday, 1), 7)
    time_str = str(content.get("deadline_time") or "22:00")
    try:
        hh, mm = time_str.split(":")[:2]
        due_time = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    except (ValueError, TypeError):
        due_time = now.replace(hour=22, minute=0, second=0, microsecond=0)
    days = (weekday - now.isoweekday()) % 7
    due = due_time + timedelta(days=days)
    if due <= now:
        due += timedelta(days=7)
    return due.date()


# ── 消息拼装 ──────────────────────────────────────────────

def compose_push(
    class_name: str,
    subject: str,
    tier: str,
    content: Dict[str, Any],
    student_count: int,
    form_type: str = "h5",
) -> Tuple[str, str]:
    """某一层的推送消息（纯 markdown，不带链接：学生侧无提交页，避免误导）。"""
    assignments = content.get("assignments") if isinstance(content.get("assignments"), list) else []
    materials = content.get("materials") if isinstance(content.get("materials"), list) else []
    reqs = _requirements_of(content)
    title = f"{class_name} · {subject} 分层作业推送（{_TIER_ZH.get(tier, tier)}）"
    lines = [f"**{student_count}** 位同学 ｜ 共 **{len(assignments)}** 项任务"]
    if assignments:
        lines.append("")
        lines.append("**作业内容**")
        for i, a in enumerate(assignments, 1):
            a = a if isinstance(a, dict) else {}
            a_title = str(a.get("title") or "").strip() or f"任务{i}"
            a_desc = str(a.get("desc") or "").strip()
            lines.append(f"{i}. **{a_title}**{'：' + a_desc if a_desc else ''}")
    if materials:
        names = "、".join(str(m.get("name") or "") for m in materials if isinstance(m, dict))
        if names:
            lines.append(f"📎 材料：{names}")
    lines.append("")
    lines.append(f"⏰ 截止：**{_deadline_text(content)}** ｜ 预计 {content.get('estimated_minutes') or 40} 分钟")
    req_names = [
        name
        for key, name in (
            ("parent_sign", "家长签字"),
            ("photo", "拍照提交"),
            ("voice", "语音反馈"),
        )
        if reqs.get(key)
    ]
    if req_names:
        lines.append("📝 要求：" + "、".join(req_names))
    if form_type == "dingtalk":
        lines.append("（请在钉钉内按上述要求完成并告知老师）")
    else:
        lines.append("（完成后告知老师或家长代为提交）")
    return title, "\n".join(lines)


def compose_notice(class_name: str, subject: str, text: str) -> Tuple[str, str]:
    """头部「发送钉钉通知」的班级通知。"""
    title = f"{class_name} · {subject} 班级通知"
    return title, text or "请及时查看班级通知。"


def compose_reminder(student_name: str, task_title: str, due_text: str) -> Tuple[str, str]:
    title = "分层作业明日截止提醒"
    body = (
        f"{student_name} 同学，你的分层作业 **{task_title}** 将于 **{due_text}** 截止，"
        "请尽快完成。"
    )
    return title, body


def compose_late(student_name: str, task_title: str, due_text: str) -> Tuple[str, str]:
    title = "分层作业逾期提醒"
    body = (
        f"{student_name} 同学，你的分层作业 **{task_title}** 已于 **{due_text}** 截止，"
        "尚未标记完成，请尽快补交。"
    )
    return title, body


def compose_urge(student_name: str, task_title: str, due_text: str) -> Tuple[str, str]:
    title = "分层作业催交提醒"
    body = (
        f"{student_name} 同学，分层作业 **{task_title}**（截止 {due_text}）尚未完成，"
        "请抓紧提交。"
    )
    return title, body


# ── 收件人解析 ────────────────────────────────────────────

def resolve_student_userid(db: Session, student: Student) -> Optional[str]:
    """学生 → 钉钉 userid：students.dingtalk_userid 优先，否则按 User.phone 反查并回填。"""
    bound = (getattr(student, "dingtalk_userid", None) or "").strip()
    if bound:
        return bound
    userid = _resolve_dingtalk_userid(student.user_id)
    if userid:
        try:
            fresh = db.query(Student).filter(Student.id == student.id).first()
            if fresh is not None:
                fresh.dingtalk_userid = userid
                db.commit()
        except Exception:
            db.rollback()
    return userid


def resolve_parent_userid(db: Session, student: Student) -> Optional[str]:
    """家长手机号 → 钉钉 userid（家长需在同一企业通讯录内，否则 None）。"""
    phone = (getattr(student, "parent_phone", None) or "").strip()
    if not phone:
        return None
    try:
        return _get_userid_by_mobile(phone)
    except Exception:
        return None


# ── 推送轮次 ──────────────────────────────────────────────

def _class_or_none(db: Session, class_id: str) -> Optional[Class]:
    return db.query(Class).filter(Class.id == class_id).first()


def _roster(db: Session, class_id: str) -> List[Student]:
    return db.query(Student).filter(Student.class_id == class_id).all()


def create_round(
    db: Session,
    class_id: str,
    subject: str,
    user_id: str,
    notice_only: bool = False,
) -> Dict[str, Any]:
    """建一轮推送：为每名在册学生建 student_tasks 行（notice_only 不建行）。

    返回 {round_id, total, created_tasks, class_name, notice_only}。
    调用方须先过 dingtalk_ready() 门槛。
    """
    cls = _class_or_none(db, class_id)
    if cls is None:
        raise ValueError("班级不存在")
    roster = _roster(db, class_id)
    cfg = load_settings(db, class_id, subject)
    round_id = uuid.uuid4().hex
    now_text = datetime.now().isoformat(timespec="seconds")

    if notice_only:
        return {
            "round_id": round_id,
            "total": len(roster),
            "created_tasks": 0,
            "class_name": cls.name or "",
            "notice_only": True,
        }

    for s in roster:
        tier = (s.tier or "B").upper()
        content = _tier_content(cfg, tier)
        assignments = content.get("assignments") if isinstance(content.get("assignments"), list) else []
        first_title = ""
        if assignments and isinstance(assignments[0], dict):
            first_title = str(assignments[0].get("title") or "").strip()
        if first_title:
            title = f"【{_TIER_ZH.get(tier, tier)}】{first_title}" + (
                f" 等{len(assignments)}项" if len(assignments) > 1 else ""
            )
        else:
            title = f"【{_TIER_ZH.get(tier, tier)}】分层作业"
        desc_lines = []
        for i, a in enumerate(assignments, 1):
            if not isinstance(a, dict):
                continue
            a_title = str(a.get("title") or "").strip() or f"任务{i}"
            a_desc = str(a.get("desc") or "").strip()
            desc_lines.append(f"{a_title}：{a_desc}" if a_desc else a_title)
        reqs = _requirements_of(content)
        desc_lines.append(f"截止：{_deadline_text(content)}")
        if reqs["parent_sign"]:
            desc_lines.append("要求：家长签字")
        if reqs["photo"]:
            desc_lines.append("要求：拍照提交")
        if reqs["voice"]:
            desc_lines.append("要求：语音反馈")

        due_date = _next_deadline_date(content)
        task = StudentTask(
            student_id=s.id,
            class_id=class_id,
            user_id=s.user_id,
            title=title,
            description="\n".join(desc_lines),
            task_type=TASK_TYPE,
            due_date=due_date,
            status="pending",
            evidence_json={
                "round_id": round_id,
                "tier": tier,
                "subject": subject,
                "class_name": cls.name or "",
                "requirements": reqs,
                "assignments": [
                    {"title": str(a.get("title") or ""), "desc": str(a.get("desc") or "")}
                    for a in assignments
                    if isinstance(a, dict)
                ],
                "deadline": _deadline_text(content),
                "created_at": now_text,
                "push": {},
                "reminded_24h": False,
                "urged_late": False,
                "urged_at": None,
            },
        )
        db.add(task)
    db.commit()
    return {
        "round_id": round_id,
        "total": len(roster),
        "created_tasks": len(roster),
        "class_name": cls.name or "",
        "notice_only": False,
    }


def _tasks_of_round(db: Session, class_id: str, round_id: str) -> List[StudentTask]:
    tasks = (
        db.query(StudentTask)
        .filter(StudentTask.class_id == class_id, StudentTask.task_type == TASK_TYPE)
        .all()
    )
    out = []
    for t in tasks:
        ev = t.evidence_json if isinstance(t.evidence_json, dict) else {}
        if ev.get("round_id") == round_id:
            out.append(t)
    return out


def _send_one(userid: str, title: str, body: str) -> Dict[str, Any]:
    res = send_work_notice_ex(userid, title, body, "")
    return {
        "status": "sent" if res.get("ok") else "failed",
        "sent_at": datetime.now().isoformat(timespec="seconds"),
        "task_id": res.get("task_id"),
        "errcode": res.get("errcode"),
        "error": "" if res.get("ok") else (res.get("errmsg") or ""),
    }


def run_push_round(
    class_id: str,
    round_id: str,
    subject: str,
    notice_only: bool = False,
    notice_text: str = "",
    parent_enabled: bool = True,
    student_enabled: bool = True,
) -> Dict[str, int]:
    """线程体：逐学生发送并把结果写回 evidence_json（每条独立 commit，崩溃可续）。"""
    counts = {"sent": 0, "failed": 0, "skipped": 0, "parent_sent": 0, "parent_failed": 0, "parent_skipped": 0}
    db = SessionLocal()
    try:
        cls = _class_or_none(db, class_id)
        roster = _roster(db, class_id)
        if cls is None:
            return counts
        cfg = load_settings(db, class_id, subject)
        class_name = cls.name or ""

        if notice_only:
            title, body = compose_notice(class_name, subject, notice_text)
            sent = failed = skipped = 0
            for s in roster[:_SEND_CAP]:
                userid = resolve_student_userid(db, s)
                if not userid:
                    skipped += 1
                    continue
                r = _send_one(userid, title, body)
                if r["status"] == "sent":
                    sent += 1
                elif r["status"] == "failed":
                    failed += 1
                else:
                    skipped += 1
            return {"sent": sent, "failed": failed, "skipped": skipped}

        tasks = _tasks_of_round(db, class_id, round_id)
        # 每层消息只拼一次
        compose_cache: Dict[str, Tuple[str, str]] = {}
        for t in tasks:
            ev = dict(t.evidence_json) if isinstance(t.evidence_json, dict) else {}
            tier = ev.get("tier") or "B"
            if tier not in compose_cache:
                content = _tier_content(cfg, tier)
                student_count = sum(
                    1
                    for x in tasks
                    if (x.evidence_json or {}).get("tier") == tier
                )
                compose_cache[tier] = compose_push(
                    class_name, subject, tier, content, student_count,
                    str(cfg.get("form_type") or "h5"),
                )
            title, body = compose_cache[tier]
            push = dict(ev.get("push") or {})

            s = db.query(Student).filter(Student.id == t.student_id).first()
            if student_enabled:
                userid = resolve_student_userid(db, s) if s else None
                if userid:
                    push["student"] = _send_one(userid, title, body)
                    counts[push["student"]["status"]] = counts.get(push["student"]["status"], 0) + 1
                else:
                    push["student"] = {
                        "status": "skipped",
                        "error": "未绑定钉钉",
                        "sent_at": datetime.now().isoformat(timespec="seconds"),
                    }
                    counts["skipped"] += 1
            if parent_enabled:
                p_userid = resolve_parent_userid(db, s) if s else None
                if p_userid:
                    push["parent"] = _send_one(p_userid, title, body)
                    key = "parent_" + push["parent"]["status"]
                    counts[key] = counts.get(key, 0) + 1
                else:
                    push["parent"] = {
                        "status": "skipped",
                        "error": "家长未绑定钉钉",
                        "sent_at": datetime.now().isoformat(timespec="seconds"),
                    }
                    counts["parent_skipped"] += 1

            ev["push"] = push
            t.evidence_json = ev
            try:
                db.commit()
            except Exception:
                db.rollback()
        print(
            f"[layered_push] round={round_id[:8]} 完成 "
            f"sent={counts['sent']} failed={counts['failed']} skipped={counts['skipped']}"
        )
        return counts
    except Exception as e:
        print(f"[layered_push] run_push_round 异常 round={round_id[:8]}: {e}")
        return counts
    finally:
        db.close()


def start_push_round(
    class_id: str,
    subject: str,
    user_id: str,
    notice_only: bool = False,
    notice_text: str = "",
    parent_enabled: Optional[bool] = None,
    student_enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """建轮次 + 起后台线程发送；返回立即可给前端的 {round_id, total, created_tasks}。"""
    db = SessionLocal()
    try:
        info = create_round(db, class_id, subject, user_id, notice_only=notice_only)
        cfg = load_settings(db, class_id, subject)
    finally:
        db.close()
    notify_cfg = cfg.get("notify") if isinstance(cfg.get("notify"), dict) else {}
    if parent_enabled is None:
        parent_enabled = bool(notify_cfg.get("parent", True))
    if student_enabled is None:
        student_enabled = bool(notify_cfg.get("student", True))
    threading.Thread(
        target=run_push_round,
        kwargs={
            "class_id": class_id,
            "round_id": info["round_id"],
            "subject": subject,
            "notice_only": notice_only,
            "notice_text": notice_text,
            "parent_enabled": parent_enabled,
            "student_enabled": student_enabled,
        },
        daemon=True,
    ).start()
    return info


# ── 催交 / 提醒 ──────────────────────────────────────────

def run_urge(
    class_id: str, subject: str, tier: Optional[str] = None, user_id: str = ""
) -> Dict[str, int]:
    """对最近一轮未完成任务的学生（+家长）发催交提醒；同步执行，返回 {sent, failed}。"""
    db = SessionLocal()
    counts = {"sent": 0, "failed": 0}
    try:
        latest = latest_round_id(db, class_id, subject)
        if not latest:
            return counts
        tasks = _tasks_of_round(db, class_id, latest)
        roster_map = {s.id: s for s in _roster(db, class_id)}
        sent = failed = 0
        for t in tasks:
            if t.status == "completed":
                continue
            ev = t.evidence_json if isinstance(t.evidence_json, dict) else {}
            if tier and ev.get("tier") != tier:
                continue
            if sent + failed >= _SEND_CAP:
                break
            s = roster_map.get(t.student_id)
            due_text = ev.get("deadline") or (t.due_date.isoformat() if t.due_date else "截止时间")
            title, body = compose_urge(s.name if s else "同学", t.title, due_text)
            targets: List[str] = []
            if s:
                userid = resolve_student_userid(db, s)
                if userid:
                    targets.append(userid)
                p_userid = resolve_parent_userid(db, s)
                if p_userid:
                    targets.append(p_userid)
            for userid in targets:
                r = _send_one(userid, title, body)
                if r["status"] == "sent":
                    sent += 1
                else:
                    failed += 1
            ev["urged_at"] = datetime.now().isoformat(timespec="seconds")
            t.evidence_json = ev
            try:
                db.commit()
            except Exception:
                db.rollback()
        return {"sent": sent, "failed": failed}
    finally:
        db.close()


# ── 统计 / 轮次 ──────────────────────────────────────────

def _round_tasks(db: Session, class_id: str, subject: Optional[str]) -> List[StudentTask]:
    tasks = (
        db.query(StudentTask)
        .filter(StudentTask.class_id == class_id, StudentTask.task_type == TASK_TYPE)
        .all()
    )
    out = []
    for t in tasks:
        ev = t.evidence_json if isinstance(t.evidence_json, dict) else {}
        if subject and ev.get("subject") not in (None, subject):
            continue
        out.append(t)
    return out


def latest_round_id(db: Session, class_id: str, subject: Optional[str]) -> Optional[str]:
    tasks = _round_tasks(db, class_id, subject)
    best_round = None
    best_at: Optional[datetime] = None
    for t in tasks:
        ev = t.evidence_json if isinstance(t.evidence_json, dict) else {}
        rid = ev.get("round_id")
        if not rid:
            continue
        at = t.created_at
        if best_at is None or (at and at > best_at):
            best_at = at
            best_round = rid
    return best_round


def collect_stats(db: Session, class_id: str, subject: Optional[str]) -> Dict[str, Any]:
    """最近一轮的分层统计（服务端算好，前端直接渲染）。"""
    round_id = latest_round_id(db, class_id, subject)
    if not round_id:
        return {"round_id": None, "round_index": 0, "rounds": 0, "tiers": {}}
    all_tasks = _round_tasks(db, class_id, subject)
    round_tasks = [
        t
        for t in all_tasks
        if isinstance(t.evidence_json, dict) and t.evidence_json.get("round_id") == round_id
    ]
    # 轮次序号 = 出现过的 round_id 按首次创建时间排序的位次
    order: Dict[str, datetime] = {}
    for t in all_tasks:
        ev = t.evidence_json if isinstance(t.evidence_json, dict) else {}
        rid = ev.get("round_id")
        if rid and t.created_at:
            if rid not in order or t.created_at < order[rid]:
                order[rid] = t.created_at
    round_index = sorted(order, key=lambda r: order[r]).index(round_id) + 1 if round_id in order else 1

    tiers: Dict[str, Any] = {}
    for t in round_tasks:
        ev = t.evidence_json if isinstance(t.evidence_json, dict) else {}
        tier = ev.get("tier") or "B"
        push = ev.get("push") if isinstance(ev.get("push"), dict) else {}
        stu = push.get("student") if isinstance(push.get("student"), dict) else {}
        parent = push.get("parent") if isinstance(push.get("parent"), dict) else {}
        bucket = tiers.setdefault(
            tier,
            {
                "total": 0,
                "sent_ok": 0,
                "sent_failed": 0,
                "sent_skipped": 0,
                "sent_pending": 0,
                "parent_sent_ok": 0,
                "completed": 0,
                "unfinished": [],
                "read_count": None,
            },
        )
        bucket["total"] += 1
        status = stu.get("status")
        if status == "sent":
            bucket["sent_ok"] += 1
        elif status == "failed":
            bucket["sent_failed"] += 1
        elif status == "skipped":
            bucket["sent_skipped"] += 1
        else:
            bucket["sent_pending"] += 1
        if parent.get("status") == "sent":
            bucket["parent_sent_ok"] += 1
        if t.status == "completed":
            bucket["completed"] += 1
        elif len(bucket["unfinished"]) < _MAX_UNFINISHED_NAMES:
            s = db.query(Student).filter(Student.id == t.student_id).first()
            # 带 task_id：前端「标记完成」要按任务 PATCH status
            bucket["unfinished"].append({"task_id": t.id, "name": s.name if s else "?"})

    # 供展示的层序（固定 A/B/C，只带有任务的）
    ordered = {k: tiers[k] for k in ("A", "B", "C") if k in tiers}
    return {
        "round_id": round_id,
        "round_index": round_index,
        "rounds": len(order),
        "tiers": ordered,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def collect_rounds(db: Session, class_id: str, subject: Optional[str]) -> List[Dict[str, Any]]:
    """历史轮次列表（新→旧）。"""
    all_tasks = _round_tasks(db, class_id, subject)
    grouped: Dict[str, Dict[str, Any]] = {}
    for t in all_tasks:
        ev = t.evidence_json if isinstance(t.evidence_json, dict) else {}
        rid = ev.get("round_id")
        if not rid:
            continue
        g = grouped.setdefault(
            rid,
            {
                "round_id": rid,
                "total": 0,
                "sent_ok": 0,
                "sent_failed": 0,
                "completed": 0,
                "pushed_at": None,
            },
        )
        g["total"] += 1
        push = ev.get("push") if isinstance(ev.get("push"), dict) else {}
        status = (push.get("student") or {}).get("status")
        if status == "sent":
            g["sent_ok"] += 1
        elif status == "failed":
            g["sent_failed"] += 1
        if t.status == "completed":
            g["completed"] += 1
        created = ev.get("created_at")
        if created and (g["pushed_at"] is None or created > g["pushed_at"]):
            g["pushed_at"] = created
    return sorted(grouped.values(), key=lambda g: g.get("pushed_at") or "", reverse=True)


# ── 周报 / 报告 ──────────────────────────────────────────

def compose_report(
    db: Session, class_id: str, subject: str, kind: str, round_index: int
) -> Tuple[str, str]:
    stats = collect_stats(db, class_id, subject)
    cls = _class_or_none(db, class_id)
    class_name = cls.name or "班级" if cls else "班级"
    kind_zh = "本周" if kind == "weekly" else f"第{round_index}轮"
    title = f"{class_name} · {subject} 分层推送{kind_zh}报告"
    lines: List[str] = []
    tiers = stats.get("tiers") or {}
    if not tiers:
        lines.append("暂无推送记录。")
    for tier in ("A", "B", "C"):
        b = tiers.get(tier)
        if not b:
            continue
        rate = int(round(b["completed"] / b["total"] * 100)) if b["total"] else 0
        skipped = b.get("sent_skipped", 0)
        line = (
            f"**{_TIER_ZH.get(tier, tier)}**：推送成功 {b['sent_ok']}/{b['total']}"
            f"（失败 {b['sent_failed']}·未绑定 {skipped}）｜ 完成 {b['completed']}/{b['total']}（{rate}%）"
        )
        lines.append(line)
        if b["unfinished"]:
            names = "、".join(
                u.get("name", "?") if isinstance(u, dict) else str(u)
                for u in b["unfinished"]
            )
            suffix = "…" if b["total"] - b["completed"] > len(b["unfinished"]) else ""
            lines.append(f"　未完成：{names}{suffix}")
    # 完成率最低的层给一句建议
    with_rate = [
        (tier, b["completed"] / b["total"])
        for tier, b in tiers.items()
        if b.get("total")
    ]
    if with_rate:
        worst = min(with_rate, key=lambda x: x[1])
        if worst[1] < 0.8:
            lines.append("")
            lines.append(f"💡 建议：{_TIER_ZH.get(worst[0], worst[0])}完成率 {int(worst[1]*100)}%，可优先催办。")
    return title, "\n".join(lines) if lines else "暂无数据。"


def send_report(
    class_id: str, subject: str, kind: str, recipient: str, user_id: str
) -> Dict[str, Any]:
    """生成报告并发给本人（self）或班主任（head=班级创建者，未绑钉钉则回退本人）。"""
    if not dingtalk_ready():
        return {"ok": False, "message": "钉钉未接入"}
    db = SessionLocal()
    try:
        stats = collect_stats(db, class_id, subject)
        title, body = compose_report(db, class_id, subject, kind, stats.get("round_index") or 1)
        target_user = user_id
        fell_back = False
        if recipient == "head":
            cls = _class_or_none(db, class_id)
            if cls and cls.user_id and cls.user_id != user_id:
                target_user = cls.user_id
        userid = _resolve_dingtalk_userid(target_user)
        if not userid and target_user != user_id:
            # 班主任未绑钉钉 → 回退发给本人
            fell_back = True
            target_user = user_id
            userid = _resolve_dingtalk_userid(user_id)
        if not userid:
            return {"ok": False, "message": "该账号未绑定钉钉，无法推送"}
        res = send_work_notice_ex(userid, title, body, "")
        ok = bool(res.get("ok"))
        msg = "已发送" if ok else f"发送失败（errcode={res.get('errcode')}）"
        if fell_back:
            msg += "（班主任未绑定钉钉，已改发给你）"
        return {"ok": ok, "message": msg}
    finally:
        db.close()


def send_test_push(class_id: str, subject: str, user_id: str) -> Dict[str, Any]:
    """测试推送：给当前老师本人发一条配置摘要，验证通道。"""
    if not dingtalk_ready():
        return {"ok": False, "message": "钉钉未接入（缺 CORP_ID/APP_KEY/APP_SECRET/AGENT_ID）"}
    db = SessionLocal()
    try:
        cls = _class_or_none(db, class_id)
        class_name = cls.name or "班级" if cls else "班级"
        cfg = load_settings(db, class_id, subject)
        roster = _roster(db, class_id)
        tiers_cfg = cfg.get("tiers") if isinstance(cfg.get("tiers"), dict) else {}
        tier_counts: Dict[str, int] = {}
        for s in roster:
            t = (s.tier or "B").upper()
            tier_counts[t] = tier_counts.get(t, 0) + 1
        userid = _resolve_dingtalk_userid(user_id)
        if not userid:
            return {"ok": False, "message": "当前账号未绑定钉钉（无手机号且无 dingtalk_userid）"}
        title = f"{class_name} · {subject} 分层推送·测试通知"
        lines = ["这是一条**测试通知**，证明分层推送通道可用。", ""]
        lines.append(f"班级在册 **{len(roster)}** 人："
                     + " ｜ ".join(f"{_TIER_ZH.get(k, k)} {v}人" for k, v in sorted(tier_counts.items())))
        timing = cfg.get("timing") if isinstance(cfg.get("timing"), dict) else {}
        mode = timing.get("mode") or "now"
        lines.append(f"推送时机：{'立即推送' if mode == 'now' else '定时推送'}")
        if len(tiers_cfg) == 0:
            lines.append("（尚未保存分层内容设置，将使用默认模板）")
        res = send_work_notice_ex(userid, title, "\n".join(lines), "")
        if res.get("ok"):
            return {"ok": True, "message": "测试通知已发送到你的钉钉"}
        return {"ok": False, "message": f"发送失败（errcode={res.get('errcode')}）"}
    finally:
        db.close()


# ── 定时任务（lifespan 循环调用）────────────────────────

_job_lock = threading.Lock()


def run_due_layered_pushes(now: Optional[datetime] = None) -> None:
    """定时推送 + T-24h 提醒 + 逾期催办（整段丢进后台线程执行，防阻塞事件循环）。"""
    if not _job_lock.acquire(blocking=False):
        return
    try:
        threading.Thread(target=_due_job_worker, args=(now,), daemon=True).start()
    finally:
        _job_lock.release()


def _due_job_worker(now: Optional[datetime] = None) -> None:
    now = now or datetime.now()
    db = SessionLocal()
    try:
        if not dingtalk_ready():
            return
        rows = (
            db.query(SystemConfig)
            .filter(SystemConfig.category == SETTINGS_CATEGORY)
            .all()
        )
        fired: List[Tuple[str, str, str, bool, Dict[str, Any]]] = []
        for row in rows:
            value = row.value if isinstance(row.value, dict) else {}
            timing = value.get("timing") if isinstance(value.get("timing"), dict) else {}
            if timing.get("mode") != "scheduled" or timing.get("fired_at"):
                continue
            scheduled_at = str(timing.get("scheduled_at") or "")
            if not scheduled_at:
                continue
            try:
                when = datetime.fromisoformat(scheduled_at)
            except ValueError:
                continue
            if when > now:
                continue
            # key = layered_push:{class_id}[:subject]
            rest = row.key[len(SETTINGS_PREFIX):]
            parts = rest.split(":", 1)
            class_id = parts[0]
            subject = parts[1] if len(parts) > 1 else ""
            fired.append((class_id, subject, row.key, True, value))

        for class_id, subject, key, _, value in fired:
            notify_cfg = value.get("notify") if isinstance(value.get("notify"), dict) else {}
            try:
                start_push_round(
                    class_id,
                    subject,
                    user_id="",
                    notice_only=False,
                    parent_enabled=bool(notify_cfg.get("parent", True)),
                    student_enabled=bool(notify_cfg.get("student", True)),
                )
            except Exception as e:
                print(f"[layered_push] 定时推送失败 class={class_id}: {e}")
                continue
            # 标记已触发
            row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
            if row and isinstance(row.value, dict):
                value2 = dict(row.value)
                timing2 = dict(value2.get("timing") or {})
                timing2["fired_at"] = now.isoformat(timespec="seconds")
                value2["timing"] = timing2
                row.value = value2
                try:
                    db.commit()
                except Exception:
                    db.rollback()

        _run_reminder_and_late(db, now)
    except Exception as e:
        print(f"[layered_push] 定时任务异常: {e}")
    finally:
        db.close()


def _run_reminder_and_late(db: Session, now: datetime) -> None:
    """T-24h 提醒与逾期催办：按任务的 evidence 提醒标记去重，每个任务各只发一次。"""
    tasks = (
        db.query(StudentTask)
        .filter(StudentTask.task_type == TASK_TYPE, StudentTask.status == "pending")
        .all()
    )
    for t in tasks:
        ev = dict(t.evidence_json) if isinstance(t.evidence_json, dict) else {}
        subject = ev.get("subject") or ""
        class_id = t.class_id
        cfg = load_settings(db, class_id, subject)
        notify_cfg = cfg.get("notify") if isinstance(cfg.get("notify"), dict) else {}
        if not t.due_date:
            continue
        # due_date 是 date（无时分），按“当天结束”近似判定窗口
        due_dt = datetime.combine(t.due_date, datetime.max.time())
        hours_left = (due_dt - now).total_seconds() / 3600
        s = db.query(Student).filter(Student.id == t.student_id).first()
        if s is None:
            continue
        due_text = ev.get("deadline") or t.due_date.isoformat()

        if (
            notify_cfg.get("reminder24h", True)
            and not ev.get("reminded_24h")
            and 0 <= hours_left <= 24
        ):
            title, body = compose_reminder(s.name, t.title, due_text)
            _send_task_targets(db, s, title, body, cfg)
            ev["reminded_24h"] = True
            t.evidence_json = ev
            try:
                db.commit()
            except Exception:
                db.rollback()
            continue

        if notify_cfg.get("late", True) and not ev.get("urged_late") and hours_left < 0:
            title, body = compose_late(s.name, t.title, due_text)
            _send_task_targets(db, s, title, body, cfg)
            ev["urged_late"] = True
            ev["urged_at"] = now.isoformat(timespec="seconds")
            t.evidence_json = ev
            try:
                db.commit()
            except Exception:
                db.rollback()


def _send_task_targets(db: Session, s: Student, title: str, body: str, cfg: Dict[str, Any]) -> None:
    notify_cfg = cfg.get("notify") if isinstance(cfg.get("notify"), dict) else {}
    if notify_cfg.get("student", True):
        userid = resolve_student_userid(db, s)
        if userid:
            _send_one(userid, title, body)
    if notify_cfg.get("parent", True):
        p_userid = resolve_parent_userid(db, s)
        if p_userid:
            _send_one(p_userid, title, body)
