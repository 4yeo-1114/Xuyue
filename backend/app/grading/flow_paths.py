# -*- coding: utf-8 -*-
"""流水阅卷共享目录布局（grading_data_all/_flow/{batch_id}/）。

流水阅卷是多老师协作，需要「无用户上下文」即可访问的共享根：
`grading_data_all_root()`（user_paths.py）本身不依赖 ContextVar，直接在其下挂 `_flow/`。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.grading.user_paths import grading_data_all_root

FLOW_ROOT_NAME = "_flow"

_IDENTITY_SAFE_RE = re.compile(r"[^0-9A-Za-z一-鿿\-_]")


def flow_root() -> Path:
    """全局共享流水阅卷根目录（不按 user 隔离）。"""
    p = grading_data_all_root() / FLOW_ROOT_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def sanitize_identity(text: str) -> str:
    """学号/姓名清洗：剔除路径非法字符，避免磁盘文件名注入；空值回退占位。"""
    s = str(text or "").strip()
    s = _IDENTITY_SAFE_RE.sub("_", s)
    return s[:64] or "unknown"


def flow_batch_root(batch_id: str) -> Path:
    p = flow_root() / sanitize_identity(batch_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sub(batch_id: str, name: str) -> Path:
    p = flow_batch_root(batch_id) / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def flow_template_dir(batch_id: str) -> Path:
    return _sub(batch_id, "template")


def flow_papers_dir(batch_id: str) -> Path:
    return _sub(batch_id, "papers")


def flow_crops_dir(batch_id: str) -> Path:
    return _sub(batch_id, "crops")


def flow_marks_dir(batch_id: str) -> Path:
    return _sub(batch_id, "marks")


def flow_meta_path(batch_id: str) -> Path:
    return flow_batch_root(batch_id) / "meta.json"
