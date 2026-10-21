# -*- coding: utf-8 -*-
"""题库批量打标（客户功能清单第 3 条）：单元 / 知识点 / 难度 / 题型 本地标签覆盖层。

存储约定（不建表不加列，JSON 文件落盘，与 layout_templates 同款）：
  grading_data_all/grading_data_{user_id}/question_tags.json

单文件 map：key = 题目稳定键 → 标签记录。key 取法（见 resolve_question_tag_key）：
  - 校本题库 school_question_banks.fingerprint（fp_ + 64hex，稳定指纹）
  - PG 资产题 questions.unique_key（回退 raw_id / id）
  记录里带 source 字段区分来源（school / pg），便于日后扩展。

部分更新语义：PUT batch 只改请求 tags 里出现的字段，未出现的字段原样保留；
空对象打标幂等（再写一遍结果不变）。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies import bind_grading_user_context, get_current_user_id
from app.grading.user_paths import user_grading_root
from app.schemas.common import ApiResponse


router = APIRouter(
    prefix="/question-tags",
    tags=["question-tags"],
    dependencies=[Depends(bind_grading_user_context)],
)

# 题目稳定键：只允许安全字符，杜绝路径穿越 / 控制字符；长度覆盖 fp_(67) 与 unique_key(64)
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-:.]{0,79}$")
_MAX_KEYS_PER_REQUEST = 500
_MAX_UNIT_LEN = 64
_MAX_KP_COUNT = 20
_MAX_KP_LEN = 64
_MAX_DIFFICULTY_LEN = 16
_MAX_QUESTION_TYPE_LEN = 32
_MAX_SOURCE_LEN = 16

# 标签覆盖层允许改写的字段（与前端 QuestionTag 对齐）
_TAG_FIELDS = ("unit", "knowledge_points", "difficulty", "question_type", "source")


class TagPatch(BaseModel):
    """部分更新补丁：字段为 None 表示「本次不改」；显式传空串/空列表表示清空。"""

    unit: Optional[str] = None
    knowledge_points: Optional[list[str]] = None
    difficulty: Optional[str] = None
    question_type: Optional[str] = None
    source: Optional[str] = None


class BatchTagRequest(BaseModel):
    keys: list[str] = Field(..., min_length=1, max_length=_MAX_KEYS_PER_REQUEST)
    tags: TagPatch


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tags_path(user_id: str) -> Path:
    return user_grading_root(user_id) / "question_tags.json"


def _read_store(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "tags": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "tags": {}}
    if not isinstance(data, dict):
        return {"version": 1, "tags": {}}
    tags = data.get("tags")
    if not isinstance(tags, dict):
        tags = {}
    return {"version": int(data.get("version") or 1), "tags": tags}


def _write_store(path: Path, store: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(store, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def resolve_question_tag_key(
    *,
    fingerprint: Optional[str] = None,
    unique_key: Optional[str] = None,
    raw_id: Optional[str] = None,
    question_id: Optional[str] = None,
) -> str:
    """解析题目稳定键：优先校本 fingerprint，其次 PG unique_key，再回退 raw_id / id。"""
    for candidate in (fingerprint, unique_key, raw_id, question_id):
        token = str(candidate or "").strip()
        if token:
            return token
    raise ValueError("题目缺少稳定键（fingerprint / unique_key / raw_id / id 全空）")


def _safe_key(key: str) -> str:
    token = str(key or "").strip()
    if not _KEY_RE.match(token):
        raise HTTPException(status_code=422, detail="非法题目 key")
    return token


def _safe_keys(keys: list[str]) -> list[str]:
    if not keys:
        raise HTTPException(status_code=422, detail="keys 不能为空")
    if len(keys) > _MAX_KEYS_PER_REQUEST:
        raise HTTPException(status_code=422, detail="keys 数量超限")
    seen: set[str] = set()
    out: list[str] = []
    for raw in keys:
        token = _safe_key(raw)
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _clean_str(value: Optional[str], max_len: int) -> Optional[str]:
    if value is None:
        return None
    token = str(value).strip()
    if len(token) > max_len:
        raise HTTPException(status_code=422, detail="标签字段超长")
    # 空串视为「清空该字段」
    return token or None


def _clean_kp_list(values: Optional[list[str]]) -> Optional[list[str]]:
    if values is None:
        return None
    if len(values) > _MAX_KP_COUNT:
        raise HTTPException(status_code=422, detail="知识点数量超限")
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        token = _clean_str(item, _MAX_KP_LEN)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _apply_patch(record: dict[str, Any], patch: TagPatch) -> dict[str, Any]:
    """部分更新：仅 patch 里显式出现（非 None）的字段覆盖进 record。"""
    payload = patch.model_dump(exclude_unset=True)
    for field in _TAG_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if field == "knowledge_points":
            record[field] = _clean_kp_list(value)
        elif field == "unit":
            record[field] = _clean_str(value, _MAX_UNIT_LEN)
        elif field == "difficulty":
            record[field] = _clean_str(value, _MAX_DIFFICULTY_LEN)
        elif field == "question_type":
            record[field] = _clean_str(value, _MAX_QUESTION_TYPE_LEN)
        elif field == "source":
            record[field] = _clean_str(value, _MAX_SOURCE_LEN)
    return record


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "unit": record.get("unit"),
        "knowledge_points": list(record.get("knowledge_points") or []),
        "difficulty": record.get("difficulty"),
        "question_type": record.get("question_type"),
        "source": record.get("source"),
        "updated_at": record.get("updated_at"),
    }


@router.get("", response_model=ApiResponse[dict])
def get_question_tags(
    keys: Optional[str] = Query(
        None,
        description="逗号分隔的题目稳定键；缺省时返回当前用户全量标签 map",
    ),
    user_id: str = Depends(get_current_user_id),
):
    """按 keys 批量取标签（列表徽章）；不传 keys 时返回全量（供筛选侧拉）。"""
    store = _read_store(_tags_path(user_id))
    tags: dict[str, Any] = store["tags"]

    if keys is None:
        return ApiResponse(data={k: _public_record(v) for k, v in tags.items()})

    raw_list = [part for part in (keys.split(",") if keys else [])]
    # 空 keys 串（?keys= 或 ?keys=,,）→ 空 map，不报错
    cleaned = [part.strip() for part in raw_list if part.strip()]
    if not cleaned:
        return ApiResponse(data={})
    wanted = _safe_keys(cleaned)
    return ApiResponse(data={k: _public_record(tags[k]) for k in wanted if k in tags})


@router.put("/batch", response_model=ApiResponse[dict])
def batch_update_question_tags(
    body: BatchTagRequest,
    user_id: str = Depends(get_current_user_id),
):
    """批量写标签：对 keys 里每道题做部分更新（只改传入字段），幂等。"""
    wanted = _safe_keys(body.keys)
    # 先在空记录上试跑一遍补丁校验标签字段，避免写到一半失败
    _apply_patch({}, body.tags)

    path = _tags_path(user_id)
    store = _read_store(path)
    tags: dict[str, Any] = store["tags"]
    now = _now_iso()

    updated: dict[str, Any] = {}
    for key in wanted:
        record = tags.get(key)
        if not isinstance(record, dict):
            record = {
                "source": None,
                "unit": None,
                "knowledge_points": [],
                "difficulty": None,
                "question_type": None,
            }
        _apply_patch(record, body.tags)
        record["updated_at"] = now
        tags[key] = record
        updated[key] = _public_record(record)

    _write_store(path, store)
    return ApiResponse(data={"updated": len(updated), "tags": updated})
