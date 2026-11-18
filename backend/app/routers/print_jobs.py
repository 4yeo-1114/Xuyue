# -*- coding: utf-8 -*-
"""打印任务队列：小程序布置作业 → 生成作业纸 → 本机打印代理拉取打印。

设计要点：
1. **落库留痕（2026-10-23 起）** —— 任务/上传材料存 print_jobs / print_uploads 表，
   小程序与网页共享同一批作业记录（网页可看可改可删）。此前是纯内存队列，
   进程重启即清空，网页端无法留痕。
2. 采用「代理主动轮询」而非云端反向推送，所以本机（学校/办公室那台连着打印机的
   Windows 机器）**不需要公网 IP、不需要内网穿透**，只要能出站访问后端即可。
3. 代理鉴权用独立的 agent token（`.env` 里的 `PRINT_AGENT_TOKEN`），不走用户 JWT，
   避免把用户账号密码放到常驻进程里。
4. 老师侧的接口（创建/查询/预览/修改）走正常用户 JWT。
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.print_job import PrintJobRow, PrintUploadRow
from app.utils.worksheet_pdf import (
    available_page_sizes,
    build_worksheet_pdf,
    detect_kind,
    grade_label,
    page_spec_label,
    resolve_page_spec,
    subject_label,
)

router = APIRouter(prefix="/print-jobs", tags=["print-jobs"])

# ─── 配置 ────────────────────────────────────────────────────────────────
# 代理领走任务后，超过这个时间没有回执，就判定为代理掉线，任务退回队列重试。
_CLAIM_TIMEOUT_SECONDS = 5 * 60
# 同一任务最多重试次数，超过标记失败。
_MAX_ATTEMPTS = 3
# 活跃任务（draft/pending/printing）最多堆积数（防止队列被塞爆）。
_MAX_QUEUE_SIZE = 200
# 单个任务 PDF 大小上限（字节）。
_MAX_PDF_BYTES = 8 * 1024 * 1024
# 单个上传文件大小上限（字节）。
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# 一次布置作业最多带几份上传材料。
_MAX_UPLOADS_PER_JOB = 20
# 未被任何作业引用的上传文件保留多久（秒）；被作业引用的随作业长期保留（改题重建 PDF 要用）。
_UPLOAD_TTL_SECONDS = 1 * 60 * 60


def _agent_token() -> str:
    """读取打印代理令牌（来自 .env 的 PRINT_AGENT_TOKEN，见 app/config.py）。

    未配置时返回空串，代理接口一律拒绝（返回 503），不影响其他模块。
    """
    try:
        from app.config import settings

        return str(getattr(settings, "PRINT_AGENT_TOKEN", "") or "").strip()
    except Exception:
        return str(os.environ.get("PRINT_AGENT_TOKEN", "") or "").strip()


# ─── 数据结构 ────────────────────────────────────────────────────────────
@dataclass
class PrintJob:
    id: str
    # draft    —— 作业纸已生成，等老师看过再决定打不打
    # pending  —— 老师点了打印，进了队列，等本机代理取走
    # printing —— 代理已取走，正在送打印机
    # done / failed —— 打印完成 / 失败
    status: str
    title: str
    subject: str
    grade: str
    class_name: str
    teacher: str
    question_count: int
    copies: int
    created_by: str
    created_at: float
    pdf: bytes
    # text = 老师手写题目；upload = 上传了图片/文档；ai = AI 生成
    source: str = "text"
    # 纸张规格代码，见 worksheet_pdf._PAGE_SPECS
    page_size: str = "a4"
    # 排版方式：auto / single / double
    layout: str = "auto"
    # 出卷全量参数（questions / question_items / note / answer_lines / upload_ids …）
    payload: dict = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)
    attempts: int = 0
    claimed_at: Optional[float] = None
    claimed_by: Optional[str] = None
    printed_at: Optional[float] = None
    printer: Optional[str] = None
    error: Optional[str] = None

    def to_public(self) -> dict:
        """给小程序看的任务快照（不含 PDF 字节与出卷参数）。"""
        return {
            "job_id": self.id,
            "status": self.status,
            "title": self.title,
            "subject": self.subject,
            "subject_label": subject_label(self.subject),
            "grade": self.grade,
            "grade_label": grade_label(self.grade),
            "class_name": self.class_name,
            "teacher": self.teacher,
            "question_count": self.question_count,
            "source": self.source,
            "page_size": self.page_size,
            "page_size_label": page_spec_label(self.page_size),
            "copies": self.copies,
            "attempts": self.attempts,
            "printer": self.printer,
            "error": self.error,
            "created_at": _iso(self.created_at),
            "printed_at": _iso(self.printed_at),
        }

    def to_full(self) -> dict:
        """网页端编辑弹窗用：任务快照 + 出卷参数 + 上传材料清单（不含文件字节）。"""
        data = self.to_public()
        p = self.payload if isinstance(self.payload, dict) else {}
        data.update(
            {
                "layout": self.layout,
                "note": p.get("note") or "",
                "answer_lines": p.get("answer_lines", 2),
                "upload_answer_lines": p.get("upload_answer_lines", 0),
                "answer_lines_override": p.get("answer_lines_override"),
                "questions": p.get("questions") or [],
                "question_items": p.get("question_items") or [],
                "upload_ids": p.get("upload_ids") or [],
                "uploads": p.get("uploads_meta") or [],
            }
        )
        return data


_LOCK = threading.Lock()


def _iso(ts: Optional[float]) -> Optional[str]:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )


# ─── 存取层（行 ↔ dataclass）─────────────────────────────────────────────
def _row_to_job(row: PrintJobRow) -> PrintJob:
    try:
        p = json.loads(row.payload or "{}")
        if not isinstance(p, dict):
            p = {}
    except Exception:
        p = {}
    return PrintJob(
        id=row.id,
        status=row.status or "draft",
        title=row.title or "",
        subject=row.subject or "",
        grade=row.grade or "",
        class_name=row.class_name or "",
        teacher=row.teacher or "",
        question_count=int(row.question_count or 0),
        copies=int(row.copies or 1),
        created_by=row.created_by or "",
        created_at=float(row.created_at or 0),
        pdf=bytes(row.pdf or b""),
        source=row.source or "text",
        page_size=row.page_size or "a4",
        layout=row.layout or "auto",
        payload=p,
        updated_at=float(row.updated_at or 0),
        attempts=int(row.attempts or 0),
        claimed_at=row.claimed_at,
        claimed_by=row.claimed_by,
        printed_at=row.printed_at,
        printer=row.printer,
        error=row.error,
    )


def _apply_job_to_row(job: PrintJob, row: PrintJobRow) -> None:
    row.created_by = job.created_by
    row.status = job.status
    row.title = job.title
    row.subject = job.subject
    row.grade = job.grade
    row.class_name = job.class_name
    row.teacher = job.teacher
    row.question_count = job.question_count
    row.copies = job.copies
    row.source = job.source
    row.page_size = job.page_size
    row.layout = job.layout
    row.payload = json.dumps(job.payload or {}, ensure_ascii=False)
    row.pdf = job.pdf
    row.created_at = job.created_at
    row.updated_at = job.updated_at
    row.attempts = job.attempts
    row.claimed_at = job.claimed_at
    row.claimed_by = job.claimed_by
    row.printed_at = job.printed_at
    row.printer = job.printer
    row.error = job.error


def _load_job(db: Session, job_id: str) -> Optional[PrintJob]:
    row = db.get(PrintJobRow, job_id)
    return _row_to_job(row) if row is not None else None


def _save_job(db: Session, job: PrintJob) -> None:
    row = db.get(PrintJobRow, job.id)
    if row is None:
        row = PrintJobRow(id=job.id)
        db.add(row)
    _apply_job_to_row(job, row)
    db.commit()


def _sweep(db: Session) -> None:
    """清理无主上传材料、回收掉线代理占用的任务。"""
    now = time.time()

    stale = (
        db.query(PrintJobRow)
        .filter(PrintJobRow.status == "printing", PrintJobRow.claimed_at.isnot(None))
        .all()
    )
    for row in stale:
        claimed_at = float(row.claimed_at or 0)
        if now - claimed_at > _CLAIM_TIMEOUT_SECONDS:
            if int(row.attempts or 0) >= _MAX_ATTEMPTS:
                row.status = "failed"
                row.error = "打印代理多次未响应"
            else:
                row.status = "pending"
                row.claimed_at = None
                row.claimed_by = None
                row.error = "打印代理超时，已退回队列"
            row.updated_at = now

    # 顺手清掉没人引用、且放太久的上传材料（被作业引用的随作业长期保留）
    db.query(PrintUploadRow).filter(
        PrintUploadRow.job_id.is_(None),
        PrintUploadRow.created_at < now - _UPLOAD_TTL_SECONDS,
    ).delete(synchronize_session=False)
    db.commit()


def _upload_item_to_dict(item: PrintUploadRow) -> dict:
    return {
        "kind": item.kind,
        "name": item.name,
        "data": bytes(item.data or b""),
        "width": item.width,
        "height": item.height,
    }


def _build_pdf(job_payload: dict, uploads: list[dict]) -> bytes:
    """按出卷参数重建作业纸 PDF（创建与修改共用）。"""
    try:
        pdf = build_worksheet_pdf(
            title=str(job_payload.get("title") or ""),
            subject=str(job_payload.get("subject") or ""),
            grade=str(job_payload.get("grade") or ""),
            class_name=str(job_payload.get("class_name") or ""),
            teacher=str(job_payload.get("teacher") or ""),
            questions=job_payload.get("questions") or [],
            question_count=int(job_payload.get("question_count") or 0),
            answer_lines=int(job_payload.get("answer_lines") or 2),
            note=str(job_payload.get("note") or ""),
            uploads=uploads or None,
            upload_answer_lines=int(job_payload.get("upload_answer_lines") or 0),
            question_items=job_payload.get("question_items") or None,
            answer_lines_override=job_payload.get("answer_lines_override"),
            page_size=str(job_payload.get("page_size") or "a4"),
            layout=str(job_payload.get("layout") or "auto"),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"作业纸生成失败：{exc}")
    if len(pdf) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=500, detail="作业纸文件过大，请减少题目数量")
    return pdf


# ─── 请求 / 响应模型 ─────────────────────────────────────────────────────
class CreatePrintJobRequest(BaseModel):
    title: str = Field("", description="作业标题，留空按「年级+学科」自动生成")
    subject: str = Field("", description="学科代码，如 math / chinese")
    grade: str = Field("", description="年级代码，如 junior1 / grade3")
    class_name: str = Field("", description="班级，可留空由老师手写")
    teacher: str = Field("", description="布置老师")
    questions: list[str] = Field(default_factory=list, description="题目文本，一行一题")
    question_count: int = Field(0, description="题量；questions 为空时按此生成空白题")
    answer_lines: int = Field(2, description="每题答题横线数")
    note: str = Field("", description="卷首提示语")
    copies: int = Field(1, description="打印份数")
    upload_ids: list[str] = Field(
        default_factory=list,
        description="已上传题目材料的 ID 列表（先调 /print-jobs/upload 拿到）。有值时按上传内容出卷",
    )
    upload_answer_lines: int = Field(
        0, description="上传内容之后是否追加答题横线，0 表示不加"
    )
    question_items: list[dict] = Field(
        default_factory=list,
        description="结构化题目（AI 生成或老师手编）—— 有值时按题型排版出卷，"
        "形如 [{'type':'choice','content':'...','score':5,'options':[...]}]",
    )
    answer_lines_override: Optional[int] = Field(
        None, description="覆盖每题的默认答题行数；不传则按题型自动（作文多、选择题无）"
    )
    page_size: str = Field(
        "a4", description="纸张规格：a4 / a3 / b5 / 16k / 8k / letter，默认 a4"
    )
    layout: str = Field(
        "auto",
        description="排版方式：auto（按纸张，大纸默认双栏）/ single（强制单栏）/ double（强制双栏）",
    )


class UpdatePrintJobRequest(BaseModel):
    """网页/小程序修改作业记录。只传要改的字段；改了出卷内容会重建 PDF。"""

    title: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    class_name: Optional[str] = None
    teacher: Optional[str] = None
    copies: Optional[int] = None
    questions: Optional[list[str]] = None
    question_count: Optional[int] = None
    answer_lines: Optional[int] = None
    note: Optional[str] = None
    upload_answer_lines: Optional[int] = None
    question_items: Optional[list[dict]] = None
    answer_lines_override: Optional[int] = None
    page_size: Optional[str] = None
    layout: Optional[str] = None


class PrintNowRequest(BaseModel):
    """老师点「打印」时可以临时改份数。"""

    copies: Optional[int] = Field(None, description="临时改打印份数；不传则用生成时定的份数")
    reprint: bool = Field(False, description="已打印过的作业重打一份（网页端「再打」用）")


class AgentAckRequest(BaseModel):
    success: bool
    printer: Optional[str] = None
    error: Optional[str] = None


# ─── 代理鉴权 ────────────────────────────────────────────────────────────
def _require_agent(
    x_print_agent_token: Optional[str] = Header(None, alias="X-Print-Agent-Token"),
) -> str:
    expected = _agent_token()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="后端未配置打印代理令牌（.env 缺少 PRINT_AGENT_TOKEN），打印功能未启用",
        )
    provided = (x_print_agent_token or "").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="打印代理令牌无效")
    return provided


# ══════════════════════════════════════════════════════════════════════════
#  代理侧接口（本机 print_agent.py 调用）
#  注意：必须写在 /{job_id} 之前，避免 "agent" 被当作 job_id 匹配。
# ══════════════════════════════════════════════════════════════════════════
@router.get("/agent/health")
def agent_health(db: Session = Depends(get_db), _: str = Depends(_require_agent)):
    """代理连通性自检。"""
    with _LOCK:
        _sweep(db)
        pending = (
            db.query(PrintJobRow).filter(PrintJobRow.status == "pending").count()
        )
        queue_total = (
            db.query(PrintJobRow)
            .filter(PrintJobRow.status.in_(("draft", "pending", "printing")))
            .count()
        )
    return {"ok": True, "pending": pending, "queue_total": queue_total}


@router.get("/agent/next")
def agent_next(
    agent: str = Query("default", description="代理名，用于日志标识"),
    db: Session = Depends(get_db),
    _: str = Depends(_require_agent),
):
    """代理拉取下一个待打印任务。

    - 有任务：返回 `application/pdf`，任务号在响应头 `X-Print-Job-Id`，
      份数在 `X-Print-Copies`。
    - 无任务：返回 204 No Content（代理据此继续等待）。
    """
    with _LOCK:
        _sweep(db)
        row = (
            db.query(PrintJobRow)
            .filter(PrintJobRow.status == "pending")
            .order_by(PrintJobRow.created_at.asc())
            .first()
        )
        if row is None:
            return Response(status_code=204)

        row.status = "printing"
        row.claimed_at = time.time()
        row.claimed_by = agent
        row.attempts = int(row.attempts or 0) + 1
        row.updated_at = time.time()
        db.commit()
        job_id, pdf, copies, title = row.id, bytes(row.pdf or b""), row.copies, row.title

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "X-Print-Job-Id": job_id,
            "X-Print-Copies": str(copies),
            "X-Print-Title": title.encode("utf-8").decode("latin-1", "ignore"),
            "Content-Disposition": f'attachment; filename="{job_id}.pdf"',
        },
    )


@router.post("/agent/{job_id}/ack")
def agent_ack(
    job_id: str,
    payload: AgentAckRequest,
    agent: str = Query("default"),
    db: Session = Depends(get_db),
    _: str = Depends(_require_agent),
):
    """代理回报打印结果。"""
    with _LOCK:
        row = db.get(PrintJobRow, job_id)
        if row is None:
            raise HTTPException(status_code=404, detail="打印任务不存在或已过期")

        row.updated_at = time.time()
        row.printer = payload.printer or row.printer
        row.claimed_by = agent or row.claimed_by
        if payload.success:
            row.status = "done"
            row.printed_at = time.time()
            row.error = None
        else:
            row.error = payload.error or "打印机报错"
            # 还有重试机会就退回队列，让代理稍后再试
            if int(row.attempts or 0) < _MAX_ATTEMPTS:
                row.status = "pending"
                row.claimed_at = None
                row.claimed_by = None
            else:
                row.status = "failed"
        db.commit()
        return _row_to_job(row).to_public()


# ══════════════════════════════════════════════════════════════════════════
#  老师 / 小程序侧接口
# ══════════════════════════════════════════════════════════════════════════
@router.post("/upload")
async def upload_material(
    file: UploadFile = File(..., description="题目材料：图片 / PDF / Word(.docx) / 文本"),
    filename: Optional[str] = Form(
        None, description="原始文件名。小程序上传时临时文件名可能丢后缀，用它兜底判断格式"
    ),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """上传一份题目材料，返回 upload_id；创建打印任务时用 upload_ids 引用它。

    支持的格式：
        - 图片：jpg / png / bmp / webp / gif / tiff（手机拍的照片会自动摆正、压缩）
        - PDF：原样插入作业纸，保持原版式
        - Word：.docx 提取文字后重排（.doc 老格式请先另存为 .docx 或 PDF）
        - 文本：txt / md / csv

    材料先暂存（一小时没被作业引用自动清掉）；被作业引用后随作业长期保留，
    改题重建 PDF 时还要用。
    """
    # 小程序上传的临时文件名常常没有扩展名，优先用前端传过来的原始文件名
    raw_name = (filename or "").strip() or file.filename or "material"
    kind = detect_kind(raw_name, file.content_type or "")

    if kind == "doc_legacy":
        raise HTTPException(
            status_code=400,
            detail="不支持老版 .doc 格式，请在 Word 里另存为 .docx 或 PDF 后再上传",
        )
    if kind == "unknown":
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{raw_name}")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大，单个文件上限 {_MAX_UPLOAD_BYTES // 1024 // 1024} MB",
        )

    extra: dict = {}

    # 图片在这里就摆正并压缩，顺便把「不是图片」这种情况挡在门口
    if kind == "image":
        try:
            from app.utils.worksheet_pdf import _normalize_image

            data, iw, ih = _normalize_image(data)
            extra = {"width": iw, "height": ih}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"图片读取失败：{exc}")

    elif kind == "docx":
        try:
            from app.utils.worksheet_pdf import _docx_text

            if not _docx_text(data).strip():
                raise HTTPException(status_code=400, detail="Word 文件里没有可打印的文字")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Word 文件解析失败：{exc}")

    elif kind == "pdf":
        try:
            import fitz

            doc = fitz.open("pdf", data)
            pages = doc.page_count
            doc.close()
            if pages <= 0:
                raise ValueError("没有页面")
            extra = {"pages": pages}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"PDF 读取失败：{exc}")

    with _LOCK:
        _sweep(db)
        mine = (
            db.query(PrintUploadRow)
            .filter(PrintUploadRow.created_by == user_id, PrintUploadRow.job_id.is_(None))
            .count()
        )
        if mine >= _MAX_UPLOADS_PER_JOB:
            raise HTTPException(
                status_code=429,
                detail=f"已上传 {mine} 份材料（单次布置上限 {_MAX_UPLOADS_PER_JOB} 份），"
                "请先完成本次布置",
            )

        upload_id = "up_" + uuid.uuid4().hex[:12]
        item = PrintUploadRow(
            id=upload_id,
            created_by=user_id,
            kind=kind,
            name=raw_name,
            size=len(data),
            width=extra.get("width"),
            height=extra.get("height"),
            pages=extra.get("pages"),
            data=data,
            job_id=None,
            created_at=time.time(),
        )
        db.add(item)
        db.commit()

    return {
        "upload_id": upload_id,
        "kind": kind,
        "name": raw_name,
        "size": len(data),
        **extra,
    }


@router.get("/page-sizes")
def list_page_sizes():
    """可选的纸张规格列表（小程序/网页下拉用）。

    注意：必须注册在 `/{job_id}` 之前，否则 "page-sizes" 会被当成任务号。
    """
    return {"page_sizes": available_page_sizes(), "default": "a4"}


@router.post("")
def create_print_job(
    payload: CreatePrintJobRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """生成作业纸（草稿）。

    只生成、不打印 —— 老师要先在小程序里预览，确认没问题再点「打印」，
    那时才调 /print-jobs/{job_id}/print 真正入队。不想打就直接返回或删掉。
    """
    with _LOCK:
        _sweep(db)
        active = (
            db.query(PrintJobRow)
            .filter(PrintJobRow.status.in_(("draft", "pending", "printing")))
            .count()
        )
        if active >= _MAX_QUEUE_SIZE:
            raise HTTPException(
                status_code=429,
                detail="打印队列已满，请确认打印代理是否在运行",
            )

    # 取出本次要用的上传材料。不解除暂存 —— 结果页的「再打一份」和网页改题
    # 重建 PDF 都还要用；未被引用的由 _sweep 一小时后清掉。
    uploads: list[dict] = []
    uploads_meta: list[dict] = []
    used_upload_ids: list[str] = []
    if payload.upload_ids:
        with _LOCK:
            _sweep(db)
            for upload_id in payload.upload_ids[:_MAX_UPLOADS_PER_JOB]:
                item = db.get(PrintUploadRow, upload_id)
                if item is None or item.created_by != user_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"上传的题目材料已过期或无效（{upload_id}），请重新上传",
                    )
                uploads.append(_upload_item_to_dict(item))
                used_upload_ids.append(upload_id)
                uploads_meta.append(
                    {
                        "upload_id": upload_id,
                        "kind": item.kind,
                        "name": item.name,
                        "size": int(item.size or 0),
                        "width": item.width,
                        "height": item.height,
                        "pages": item.pages,
                    }
                )

    now = time.time()
    fallback_title = f"{grade_label(payload.grade)}{subject_label(payload.subject)}作业".strip()
    job_payload = {
        "questions": payload.questions or [],
        "question_count": payload.question_count,
        "answer_lines": payload.answer_lines,
        "note": payload.note or "",
        "upload_answer_lines": payload.upload_answer_lines,
        "question_items": payload.question_items or [],
        "answer_lines_override": payload.answer_lines_override,
        "layout": payload.layout or "auto",
        "upload_ids": used_upload_ids,
        "uploads_meta": uploads_meta,
    }
    # 生成时标题/学科等也在 payload 里留一份，网页改题重建 PDF 时用
    job_payload["title"] = payload.title.strip()
    job_payload["subject"] = payload.subject
    job_payload["grade"] = payload.grade
    job_payload["class_name"] = payload.class_name
    job_payload["teacher"] = payload.teacher

    pdf = _build_pdf(job_payload, uploads)

    job = PrintJob(
        id="pj_" + uuid.uuid4().hex[:12],
        status="draft",
        title=payload.title.strip() or fallback_title or "作业",
        subject=payload.subject,
        grade=payload.grade,
        class_name=payload.class_name,
        teacher=payload.teacher,
        question_count=(
            len(uploads)
            if uploads
            else (
                len(payload.question_items)
                or len([q for q in payload.questions if str(q).strip()])
                or payload.question_count
            )
        ),
        copies=max(1, min(int(payload.copies or 1), 50)),
        source=(
            "upload"
            if uploads
            else ("ai" if payload.question_items else "text")
        ),
        page_size=resolve_page_spec(payload.page_size).key,
        layout=payload.layout or "auto",
        payload=job_payload,
        created_by=user_id,
        created_at=now,
        pdf=pdf,
    )

    with _LOCK:
        _save_job(db, job)
        # 上传材料打上归属，随作业长期保留
        if used_upload_ids:
            db.query(PrintUploadRow).filter(
                PrintUploadRow.id.in_(used_upload_ids)
            ).update({"job_id": job.id}, synchronize_session=False)
            db.commit()
        return job.to_public()


@router.get("")
def list_print_jobs(
    limit: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """列出当前用户的打印任务（最新的在前）。"""
    with _LOCK:
        _sweep(db)
        rows = (
            db.query(PrintJobRow)
            .filter(PrintJobRow.created_by == user_id)
            .order_by(PrintJobRow.created_at.desc())
            .limit(limit)
            .all()
        )
        return {"jobs": [_row_to_job(j).to_public() for j in rows]}


@router.get("/{job_id}")
def get_print_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """查询单个打印任务状态，供小程序轮询。"""
    with _LOCK:
        _sweep(db)
        job = _load_job(db, job_id)
        if job is None or job.created_by != user_id:
            raise HTTPException(status_code=404, detail="打印任务不存在或已过期")
        return job.to_public()


@router.get("/{job_id}/full")
def get_print_job_full(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """作业完整详情（含出卷参数），网页端编辑弹窗用。"""
    with _LOCK:
        job = _load_job(db, job_id)
        if job is None or job.created_by != user_id:
            raise HTTPException(status_code=404, detail="打印任务不存在或已过期")
        return job.to_full()


@router.patch("/{job_id}")
def update_print_job(
    job_id: str,
    payload: UpdatePrintJobRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """修改作业记录（网页/小程序通用）。改了出卷内容会重建 PDF。

    正在打印中（printing）的作业不允许改，其余状态（含 done/failed）都可改。
    """
    with _LOCK:
        _sweep(db)
        job = _load_job(db, job_id)
        if job is None or job.created_by != user_id:
            raise HTTPException(status_code=404, detail="打印任务不存在或已过期")
        if job.status == "printing":
            raise HTTPException(status_code=409, detail="这份作业正在打印中，稍后再改")

        meta_changed = False
        content_changed = False

        for key in ("title", "subject", "grade", "class_name", "teacher"):
            val = getattr(payload, key)
            if val is not None:
                if (getattr(job, key) or "") != val:
                    setattr(job, key, val)
                    meta_changed = True

        if payload.copies is not None:
            copies = max(1, min(int(payload.copies), 50))
            if job.copies != copies:
                job.copies = copies
                meta_changed = True

        content_map = {
            "questions": payload.questions,
            "question_items": payload.question_items,
            "note": payload.note,
            "answer_lines": payload.answer_lines,
            "upload_answer_lines": payload.upload_answer_lines,
            "answer_lines_override": payload.answer_lines_override,
            "question_count": payload.question_count,
        }
        for key, val in content_map.items():
            if val is not None and job.payload.get(key) != val:
                job.payload[key] = val
                content_changed = True

        if payload.page_size is not None:
            page_size = resolve_page_spec(payload.page_size).key
            if job.page_size != page_size:
                job.page_size = page_size
                job.payload["page_size"] = page_size
                content_changed = True

        if payload.layout is not None:
            layout = payload.layout if payload.layout in ("auto", "single", "double") else "auto"
            if job.layout != layout:
                job.layout = layout
                job.payload["layout"] = layout
                content_changed = True

        # 标题/学科/班级/老师也进 payload（重建 PDF 卷头要用）
        if meta_changed or content_changed:
            job.payload["title"] = job.title
            job.payload["subject"] = job.subject
            job.payload["grade"] = job.grade
            job.payload["class_name"] = job.class_name
            job.payload["teacher"] = job.teacher
            job.payload["page_size"] = job.page_size
            job.payload["layout"] = job.layout

        if content_changed:
            upload_ids = job.payload.get("upload_ids") or []
            uploads = []
            if upload_ids:
                rows = (
                    db.query(PrintUploadRow)
                    .filter(
                        PrintUploadRow.id.in_(upload_ids),
                        PrintUploadRow.job_id == job.id,
                    )
                    .all()
                )
                by_id = {r.id: r for r in rows}
                for up_id in upload_ids:
                    item = by_id.get(up_id)
                    if item is not None:
                        uploads.append(_upload_item_to_dict(item))
            job.pdf = _build_pdf(job.payload, uploads)
            # 题量跟着内容重算
            if not uploads:
                job.question_count = (
                    len(job.payload.get("question_items") or [])
                    or len(
                        [q for q in (job.payload.get("questions") or []) if str(q).strip()]
                    )
                    or int(job.payload.get("question_count") or 0)
                )

        job.updated_at = time.time()
        _save_job(db, job)
        return job.to_full()


@router.get("/{job_id}/pdf")
def get_print_job_pdf(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """下载作业纸 PDF（小程序里预览用）。"""
    with _LOCK:
        _sweep(db)
        job = _load_job(db, job_id)
        if job is None or job.created_by != user_id:
            raise HTTPException(status_code=404, detail="打印任务不存在或已过期")
        pdf = job.pdf

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{job_id}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{job_id}/print")
def enqueue_print_job(
    job_id: str,
    payload: Optional[PrintNowRequest] = None,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """把作业送出打印。老师在预览页点了「打印」才调这个。

    草稿（draft）和之前失败的（failed）都能重新入队；已经在打印的会拒绝；
    已打印过的（done）默认拒绝，带 reprint=true 可重打。
    """
    with _LOCK:
        _sweep(db)
        job = _load_job(db, job_id)
        if job is None or job.created_by != user_id:
            raise HTTPException(status_code=404, detail="作业不存在或已过期")

        if job.status == "pending":
            return job.to_public()  # 重复点按，幂等返回
        if job.status == "printing":
            raise HTTPException(status_code=409, detail="这份作业正在打印中")
        if job.status == "done" and not (payload is not None and payload.reprint):
            raise HTTPException(status_code=409, detail="这份作业已经打印过了")

        if payload is not None and payload.copies:
            job.copies = max(1, min(int(payload.copies), 50))

        job.status = "pending"
        job.attempts = 0
        job.error = None
        job.claimed_at = None
        job.claimed_by = None
        job.updated_at = time.time()
        _save_job(db, job)
        return job.to_public()


@router.delete("/{job_id}")
def cancel_print_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """删除一份作业记录。打印中（printing）的不能删，其余状态（含 done/failed）都可删。"""
    with _LOCK:
        job = _load_job(db, job_id)
        if job is None or job.created_by != user_id:
            raise HTTPException(status_code=404, detail="作业不存在或已过期")
        if job.status == "printing":
            raise HTTPException(status_code=409, detail="这份作业正在打印中，无法删除")
        row = db.get(PrintJobRow, job_id)
        db.query(PrintUploadRow).filter(PrintUploadRow.job_id == job_id).delete(
            synchronize_session=False
        )
        if row is not None:
            db.delete(row)
        db.commit()
    return {"ok": True, "job_id": job_id}
