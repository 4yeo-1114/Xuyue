# -*- coding: utf-8 -*-
"""打印任务队列：小程序布置作业 → 生成作业纸 → 本机打印代理拉取打印。

设计要点：
1. **纯内存队列，不落库、不留痕** —— 进程重启即清空，不产生任何历史记录。
2. 采用「代理主动轮询」而非云端反向推送，所以本机（学校/办公室那台连着打印机的
   Windows 机器）**不需要公网 IP、不需要内网穿透**，只要能出站访问后端即可。
3. 代理鉴权用独立的 agent token（`.env` 里的 `PRINT_AGENT_TOKEN`），不走用户 JWT，
   避免把用户账号密码放到常驻进程里。
4. 老师侧的接口（创建/查询/预览）走正常用户 JWT。
"""
from __future__ import annotations

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

from app.dependencies import get_current_user_id
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
# 任务在内存中保留的时长（秒）；超时后连同 PDF 一起丢弃，不残留。
_JOB_TTL_SECONDS = 2 * 60 * 60
# 代理领走任务后，超过这个时间没有回执，就判定为代理掉线，任务退回队列重试。
_CLAIM_TIMEOUT_SECONDS = 5 * 60
# 同一任务最多重试次数，超过标记失败。
_MAX_ATTEMPTS = 3
# 队列里最多堆积的任务数（防止内存被塞爆）。
_MAX_QUEUE_SIZE = 200
# 单个任务 PDF 大小上限（字节）。
_MAX_PDF_BYTES = 8 * 1024 * 1024
# 单个上传文件大小上限（字节）。
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# 一次布置作业最多带几份上传材料。
_MAX_UPLOADS_PER_JOB = 20
# 未使用的上传文件在内存里保留多久（秒）。
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
    updated_at: float = field(default_factory=time.time)
    attempts: int = 0
    claimed_at: Optional[float] = None
    claimed_by: Optional[str] = None
    printed_at: Optional[float] = None
    printer: Optional[str] = None
    error: Optional[str] = None

    def to_public(self) -> dict:
        """给小程序看的任务快照（不含 PDF 字节）。"""
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


_JOBS: dict[str, PrintJob] = {}
_LOCK = threading.Lock()

# 老师上传的题目材料（图片 / PDF / Word），暂存在内存里，
# 等创建打印任务时被引用一次，之后随任务一起过期清掉 —— 同样不落库、不留痕。
_UPLOADS: dict[str, dict] = {}


def _iso(ts: Optional[float]) -> Optional[str]:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )


def _sweep() -> None:
    """清理过期任务、回收掉线代理占用的任务。调用方需持有 _LOCK。"""
    now = time.time()

    for job_id, job in list(_JOBS.items()):
        if now - job.created_at > _JOB_TTL_SECONDS:
            _JOBS.pop(job_id, None)
            continue

        # 代理领走后长时间没回执 → 退回队列（或判定失败）
        if job.status == "printing" and job.claimed_at:
            if now - job.claimed_at > _CLAIM_TIMEOUT_SECONDS:
                if job.attempts >= _MAX_ATTEMPTS:
                    job.status = "failed"
                    job.error = "打印代理多次未响应"
                else:
                    job.status = "pending"
                    job.claimed_at = None
                    job.claimed_by = None
                    job.error = "打印代理超时，已退回队列"
                job.updated_at = now

    # 顺手清掉没人用、且放太久的上传材料
    for upload_id, item in list(_UPLOADS.items()):
        if now - item["created_at"] > _UPLOAD_TTL_SECONDS:
            _UPLOADS.pop(upload_id, None)


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


class PrintNowRequest(BaseModel):
    """老师点「打印」时可以临时改份数。"""

    copies: Optional[int] = Field(None, description="临时改打印份数；不传则用生成时定的份数")


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
def agent_health(_: str = Depends(_require_agent)):
    """代理连通性自检。"""
    with _LOCK:
        _sweep()
        pending = sum(1 for j in _JOBS.values() if j.status == "pending")
    return {"ok": True, "pending": pending, "queue_total": len(_JOBS)}


@router.get("/agent/next")
def agent_next(
    agent: str = Query("default", description="代理名，用于日志标识"),
    _: str = Depends(_require_agent),
):
    """代理拉取下一个待打印任务。

    - 有任务：返回 `application/pdf`，任务号在响应头 `X-Print-Job-Id`，
      份数在 `X-Print-Copies`。
    - 无任务：返回 204 No Content（代理据此继续等待）。
    """
    with _LOCK:
        _sweep()
        job = next((j for j in _JOBS.values() if j.status == "pending"), None)
        if job is None:
            return Response(status_code=204)

        job.status = "printing"
        job.claimed_at = time.time()
        job.claimed_by = agent
        job.attempts += 1
        job.updated_at = time.time()
        job_id, pdf, copies, title = job.id, job.pdf, job.copies, job.title

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
    _: str = Depends(_require_agent),
):
    """代理回报打印结果。"""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="打印任务不存在或已过期")

        job.updated_at = time.time()
        job.printer = payload.printer or job.printer
        job.claimed_by = agent or job.claimed_by
        if payload.success:
            job.status = "done"
            job.printed_at = time.time()
            job.error = None
        else:
            job.error = payload.error or "打印机报错"
            # 还有重试机会就退回队列，让代理稍后再试
            if job.attempts < _MAX_ATTEMPTS:
                job.status = "pending"
                job.claimed_at = None
                job.claimed_by = None
            else:
                job.status = "failed"

        return job.to_public()


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
):
    """上传一份题目材料，返回 upload_id；创建打印任务时用 upload_ids 引用它。

    支持的格式：
        - 图片：jpg / png / bmp / webp / gif / tiff（手机拍的照片会自动摆正、压缩）
        - PDF：原样插入作业纸，保持原版式
        - Word：.docx 提取文字后重排（.doc 老格式请先另存为 .docx 或 PDF）
        - 文本：txt / md / csv

    材料存在内存里，一小时没人用就自动清掉，不写数据库。
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
        _sweep()
        mine = sum(1 for u in _UPLOADS.values() if u["created_by"] == user_id)
        if mine >= _MAX_UPLOADS_PER_JOB:
            raise HTTPException(
                status_code=429,
                detail=f"已上传 {mine} 份材料（单次布置上限 {_MAX_UPLOADS_PER_JOB} 份），"
                "请先完成本次布置",
            )

        upload_id = "up_" + uuid.uuid4().hex[:12]
        item = {
            "id": upload_id,
            "kind": kind,
            "name": raw_name,
            "size": len(data),
            "data": data,
            "created_by": user_id,
            "created_at": time.time(),
        }
        item.update(extra)
        _UPLOADS[upload_id] = item

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
):
    """生成作业纸（草稿）。

    只生成、不打印 —— 老师要先在小程序里预览，确认没问题再点「打印」，
    那时才调 /print-jobs/{job_id}/print 真正入队。不想打就直接返回或删掉。
    """
    with _LOCK:
        _sweep()
        if len(_JOBS) >= _MAX_QUEUE_SIZE:
            raise HTTPException(
                status_code=429,
                detail="打印队列已满，请确认打印代理是否在运行",
            )

    # 取出本次要用的上传材料。不在这里删除 —— 结果页的「再打一份」还要用，
    # 一小时后由 _sweep 统一清理。
    uploads: list[dict] = []
    if payload.upload_ids:
        with _LOCK:
            _sweep()
            for upload_id in payload.upload_ids[:_MAX_UPLOADS_PER_JOB]:
                item = _UPLOADS.get(upload_id)
                if item is None or item["created_by"] != user_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"上传的题目材料已过期或无效（{upload_id}），请重新上传",
                    )
                uploads.append(
                    {
                        "kind": item["kind"],
                        "name": item["name"],
                        "data": item["data"],
                        "width": item.get("width"),
                        "height": item.get("height"),
                    }
                )

    try:
        pdf = build_worksheet_pdf(
            title=payload.title,
            subject=payload.subject,
            grade=payload.grade,
            class_name=payload.class_name,
            teacher=payload.teacher,
            questions=payload.questions,
            question_count=payload.question_count,
            answer_lines=payload.answer_lines,
            note=payload.note,
            uploads=uploads or None,
            upload_answer_lines=payload.upload_answer_lines,
            question_items=payload.question_items or None,
            answer_lines_override=payload.answer_lines_override,
            page_size=payload.page_size,
            layout=payload.layout,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"作业纸生成失败：{exc}")

    if len(pdf) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=500, detail="作业纸文件过大，请减少题目数量")

    now = time.time()
    fallback_title = f"{grade_label(payload.grade)}{subject_label(payload.subject)}作业".strip()
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
        created_by=user_id,
        created_at=now,
        pdf=pdf,
    )

    with _LOCK:
        _JOBS[job.id] = job
        return job.to_public()


@router.get("")
def list_print_jobs(
    limit: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
):
    """列出当前用户的打印任务（最新的在前）。"""
    with _LOCK:
        _sweep()
        jobs = [j for j in _JOBS.values() if j.created_by == user_id]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return {"jobs": [j.to_public() for j in jobs[:limit]]}


@router.get("/{job_id}")
def get_print_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """查询单个打印任务状态，供小程序轮询。"""
    with _LOCK:
        _sweep()
        job = _JOBS.get(job_id)
        if job is None or job.created_by != user_id:
            raise HTTPException(status_code=404, detail="打印任务不存在或已过期")
        return job.to_public()


@router.get("/{job_id}/pdf")
def get_print_job_pdf(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """下载作业纸 PDF（小程序里预览用）。"""
    with _LOCK:
        _sweep()
        job = _JOBS.get(job_id)
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
):
    """把作业送出打印。老师在预览页点了「打印」才调这个。

    草稿（draft）和之前失败的（failed）都能重新入队；已经在打印或已完成的会拒绝。
    """
    with _LOCK:
        _sweep()
        job = _JOBS.get(job_id)
        if job is None or job.created_by != user_id:
            raise HTTPException(status_code=404, detail="作业不存在或已过期")

        if job.status == "pending":
            return job.to_public()  # 重复点按，幂等返回
        if job.status == "printing":
            raise HTTPException(status_code=409, detail="这份作业正在打印中")
        if job.status == "done":
            raise HTTPException(status_code=409, detail="这份作业已经打印过了")

        if payload is not None and payload.copies:
            job.copies = max(1, min(int(payload.copies), 50))

        job.status = "pending"
        job.attempts = 0
        job.error = None
        job.claimed_at = None
        job.claimed_by = None
        job.updated_at = time.time()
        return job.to_public()


@router.delete("/{job_id}")
def cancel_print_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """删除一份作业（草稿，或还没被打印机取走的排队中作业）。"""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or job.created_by != user_id:
            raise HTTPException(status_code=404, detail="作业不存在或已过期")
        if job.status in ("printing", "done"):
            raise HTTPException(status_code=409, detail="这份作业已经在打印了，无法删除")
        _JOBS.pop(job_id, None)
    return {"ok": True, "job_id": job_id}
