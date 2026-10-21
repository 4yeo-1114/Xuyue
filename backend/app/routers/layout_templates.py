# -*- coding: utf-8 -*-
"""试卷布局模板（客户功能清单第 10 条）：命名框选布局跨考试复用，免重复框选。

存储约定（不建表不加列，JSON 文件落盘）：
  grading_data_all/grading_data_{user_id}/layout_templates/{template_id}.json

与考试目录里的 .reference_vlm_layout.json 的关系：
  布局仍以 confirm_reference_layout 为唯一持久化/确认入口；模板只是
  「命名布局快照」，套用时前端把模板页套到当前考试的 prepare/editing 会话上，
  再走 confirm_reference_layout 确认，不绕过既有约束。
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import bind_grading_user_context, get_current_user_id
from app.grading.user_paths import user_grading_root
from app.schemas.common import ApiResponse


router = APIRouter(
    prefix="/layout-templates",
    tags=["layout-templates"],
    dependencies=[Depends(bind_grading_user_context)],
)

# 模板 id 只允许安全字符，杜绝路径穿越
_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_MAX_NAME_LEN = 80


class SaveLayoutTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=_MAX_NAME_LEN)
    layout: dict[str, Any]
    source_folder: Optional[str] = None
    class_id: Optional[str] = None
    subject: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _templates_dir(user_id: str) -> Path:
    root = user_grading_root(user_id) / "layout_templates"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return root


def _safe_template_id(template_id: str) -> str:
    token = str(template_id or "").strip()
    if not _ID_RE.match(token):
        raise HTTPException(status_code=404, detail="模板不存在")
    return token


def _template_path(user_id: str, template_id: str) -> Path:
    return _templates_dir(user_id) / f"{_safe_template_id(template_id)}.json"


def _read_template(path: Path) -> Optional[dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_template(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def _meta_only(record: dict[str, Any]) -> dict[str, Any]:
    """列表/保存响应不带整份 layout，省流量；详情接口才返回完整布局。"""
    layout = record.get("layout") if isinstance(record.get("layout"), dict) else {}
    pages = layout.get("pages") if isinstance(layout.get("pages"), list) else []
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "subject": record.get("subject") or "",
        "class_id": record.get("class_id") or "",
        "source_folder": record.get("source_folder") or "",
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "page_count": len(pages),
    }


def _list_all(user_id: str) -> list[dict[str, Any]]:
    root = _templates_dir(user_id)
    rows: list[dict[str, Any]] = []
    try:
        files = sorted(root.glob("*.json"))
    except OSError:
        return []
    for path in files:
        record = _read_template(path)
        if not record:
            continue
        rows.append(_meta_only(record))
    rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return rows


@router.get("", response_model=ApiResponse[list[dict]])
def list_layout_templates(
    class_id: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
):
    """列出当前用户的布局模板；class_id / subject 可选过滤（空串视为不过滤）。"""
    rows = _list_all(user_id)
    class_filter = (class_id or "").strip()
    subject_filter = (subject or "").strip()
    if class_filter:
        rows = [row for row in rows if str(row.get("class_id") or "") == class_filter]
    if subject_filter:
        rows = [row for row in rows if str(row.get("subject") or "") == subject_filter]
    return ApiResponse(data=rows)


@router.post("", response_model=ApiResponse[dict])
def save_layout_template(
    body: SaveLayoutTemplateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """保存命名布局模板（新建；同名不覆盖，各自独立 id）。"""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="模板名称不能为空")
    layout = body.layout if isinstance(body.layout, dict) else {}
    if not isinstance(layout.get("pages"), list) or not layout.get("pages"):
        raise HTTPException(status_code=422, detail="layout.pages 不能为空")

    template_id = f"lt_{uuid.uuid4().hex[:16]}"
    now = _now_iso()
    record = {
        "id": template_id,
        "name": name,
        "subject": (body.subject or "").strip(),
        "class_id": (body.class_id or "").strip(),
        "source_folder": (body.source_folder or "").strip(),
        "created_at": now,
        "updated_at": now,
        "layout": layout,
    }
    path = _templates_dir(user_id) / f"{template_id}.json"
    _write_template(path, record)
    return ApiResponse(data=_meta_only(record))


@router.get("/{template_id}", response_model=ApiResponse[dict])
def get_layout_template(
    template_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """取模板详情（含完整 layout JSON）。"""
    path = _template_path(user_id, template_id)
    record = _read_template(path)
    if not record:
        raise HTTPException(status_code=404, detail="模板不存在")
    return ApiResponse(data=record)


@router.delete("/{template_id}", response_model=ApiResponse[dict])
def delete_layout_template(
    template_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """删除模板；不存在或 id 非法一律 404（不暴露路径信息）。"""
    path = _template_path(user_id, template_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="模板不存在")
    try:
        path.unlink(missing_ok=True)
    except OSError:
        raise HTTPException(status_code=500, detail="模板删除失败")
    return ApiResponse(data={"id": _safe_template_id(template_id), "deleted": True})
