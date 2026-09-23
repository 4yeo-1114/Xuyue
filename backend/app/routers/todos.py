from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc, func

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.todo_item import TodoItem
from app.models.system_settings import SystemSettings
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.todos import CreateTodoRequest, TodoItemOut, UpdateTodoRequest


router = APIRouter(prefix="/todos", tags=["todos"])


def _as_utc_naive(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _as_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_utc_z(dt: Optional[datetime]) -> Optional[str]:
    d = _as_utc_aware(dt)
    if not d:
        return None
    s = d.isoformat(timespec="seconds")
    if s.endswith("+00:00"):
        return s[:-6] + "Z"
    return s


def _iso_local(dt: Optional[datetime]) -> Optional[str]:
    d = _as_utc_aware(dt)
    if not d:
        return None
    return d.astimezone().isoformat(timespec="seconds")


def _poke_wakeup(request: Optional[Request]) -> None:
    if request is None:
        return
    try:
        wake = getattr(request.app.state, "todo_wakeup", None)
        if wake is not None:
            wake.set()
    except Exception:
        return


def _to_out(t: TodoItem) -> TodoItemOut:
    return TodoItemOut(
        id=t.id,
        title=t.title,
        content=t.content,
        remind_at=_iso_utc_z(t.remind_at),
        notified_at=_iso_utc_z(t.notified_at),
        is_done=bool(t.is_done),
        created_at=_iso_utc_z(t.created_at) or "",
        updated_at=_iso_utc_z(t.updated_at) or "",
    )

def get_next_pending_remind_at(db: Session, after: Optional[datetime] = None) -> Optional[datetime]:
    after = after or datetime.utcnow()
    return (
        db.query(func.min(TodoItem.remind_at))
        .filter(
            TodoItem.is_done == False,  # noqa: E712
            TodoItem.remind_at != None,  # noqa: E711
            TodoItem.remind_at > after,
            TodoItem.notified_at == None,  # noqa: E711
        )
        .scalar()
    )


def run_due_notification_job(db: Session, now: Optional[datetime] = None, limit: int = 50) -> int:
    now = now or datetime.utcnow()
    due = (
        db.query(TodoItem)
        .filter(
            TodoItem.is_done == False,  # noqa: E712
            TodoItem.remind_at != None,  # noqa: E711
            TodoItem.remind_at <= now,
            TodoItem.notified_at == None,  # noqa: E711
        )
        .order_by(asc(TodoItem.remind_at))
        .limit(int(limit) if limit else 50)
        .all()
    )
    if not due:
        return 0

    try:
        from app.email_utils import send_email
    except Exception:
        return 0

    user_ids = list({t.user_id for t in due if t.user_id})
    users = {}
    user_emails = {}
    if user_ids:
        for u in db.query(User).filter(User.id.in_(user_ids)).all():
            users[u.id] = (getattr(u, "display_name", None) or getattr(u, "email", None) or u.id)
            user_emails[u.id] = (getattr(u, "personal_email", "") or "").strip()

    sent = 0
    for item in due:
        target_email = user_emails.get(item.user_id, "")
        if not target_email:
            continue
        who = users.get(item.user_id, item.user_id)
        subject = f"待办提醒：{item.title}"
        body = (
            f"创建人：{who}\n\n"
            f"待办：{item.title}\n\n"
            f"内容：{item.content or '—'}\n\n"
            f"提醒时间：{_iso_local(item.remind_at) or '—'}\n"
            f"创建时间：{_iso_local(item.created_at) or '—'}\n"
        )
        send_email(target_email, subject, body)
        item.notified_at = now
        sent += 1

    db.commit()
    return sent


@router.get("", response_model=ApiResponse[List[TodoItemOut]])
def list_my_todos(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(TodoItem)
        .filter(TodoItem.user_id == user_id)
        .order_by(desc(TodoItem.created_at))
        .limit(50)
        .all()
    )
    return ApiResponse(data=[_to_out(r) for r in rows])


@router.post("", response_model=ApiResponse[TodoItemOut])
def create_todo(
    request: Request,
    body: CreateTodoRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="请输入待办名称")
    t = TodoItem(
        user_id=user_id,
        title=title,
        content=(body.content or "").strip() or None,
        remind_at=_as_utc_naive(body.remind_at),
        is_done=False,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    _poke_wakeup(request)
    return ApiResponse(data=_to_out(t))


@router.patch("/{todo_id}", response_model=ApiResponse[TodoItemOut])
def update_todo(
    todo_id: str,
    request: Request,
    body: UpdateTodoRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    t = db.query(TodoItem).filter(TodoItem.id == todo_id, TodoItem.user_id == user_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="待办不存在")
    if body.title is not None:
        title = (body.title or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="待办名称不能为空")
        t.title = title
    if body.content is not None:
        t.content = (body.content or "").strip() or None
    if body.remind_at is not None or (hasattr(body, "remind_at") and body.remind_at is None):
        t.remind_at = _as_utc_naive(body.remind_at)
    if body.is_done is not None:
        t.is_done = bool(body.is_done)
    db.commit()
    db.refresh(t)
    _poke_wakeup(request)
    return ApiResponse(data=_to_out(t))


@router.delete("/{todo_id}", response_model=ApiResponse[None])
def delete_todo(
    todo_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    t = db.query(TodoItem).filter(TodoItem.id == todo_id, TodoItem.user_id == user_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="待办不存在")
    db.delete(t)
    db.commit()
    return ApiResponse(data=None)


@router.post("/notify-due", response_model=ApiResponse[dict])
def notify_due(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    due = (
        db.query(TodoItem)
        .filter(
            TodoItem.user_id == user_id,
            TodoItem.is_done == False,  # noqa: E712
            TodoItem.remind_at != None,  # noqa: E711
            TodoItem.remind_at <= now,
            TodoItem.notified_at == None,  # noqa: E711
        )
        .order_by(asc(TodoItem.remind_at))
        .limit(20)
        .all()
    )
    if not due:
        return ApiResponse(data={"sent": 0})

    user = db.query(User).filter(User.id == user_id).first()
    to_email = (getattr(user, "personal_email", "") or "").strip() if user else ""
    if not to_email:
        raise HTTPException(status_code=400, detail="个人设置中未配置个人邮箱")

    try:
        from app.email_utils import send_email
    except Exception:
        raise HTTPException(status_code=500, detail="邮件模块不可用")

    sent = 0
    for item in due:
        subject = f"待办提醒：{item.title}"
        body = (
            f"待办：{item.title}\n\n"
            f"内容：{item.content or '—'}\n\n"
            f"提醒时间：{_iso_local(item.remind_at) or '—'}\n"
            f"创建时间：{_iso_local(item.created_at) or '—'}\n"
        )
        send_email(to_email, subject, body)
        item.notified_at = now
        sent += 1

    db.commit()
    return ApiResponse(data={"sent": sent})


@router.post("/notify-due-system", response_model=ApiResponse[dict])
def notify_due_system(
    request: Request,
    x_cron_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    client_host = (request.client.host or "") if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="仅允许本机调用")
    try:
        from app.config import settings
    except Exception:
        settings = None
    required = str(getattr(settings, "CRON_KEY", "") or "").strip() if settings is not None else ""
    if not required:
        raise HTTPException(status_code=500, detail="CRON_KEY 未配置")
    if (x_cron_key or "").strip() != required:
        raise HTTPException(status_code=403, detail="CRON_KEY 无效")

    sent = run_due_notification_job(db=db, limit=50)
    return ApiResponse(data={"sent": sent})
