# -*- coding: utf-8 -*-
"""按 user_id 隔离的 grading_data_all/grading_data_{user_id} 目录布局与访问。"""
from __future__ import annotations

import re
import sys
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

_grading_user_id: ContextVar[Optional[str]] = ContextVar("grading_user_id", default=None)

GRADING_DATA_ALL_DIR = "grading_data_all"
_legacy_dirs_migrated = False


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def grading_data_all_root() -> Path:
    """所有用户 grading_data_{user_id} 的统一父目录，便于部署时与代码目录分离保留。"""
    return project_root() / GRADING_DATA_ALL_DIR


def migrate_legacy_grading_dirs_if_needed() -> None:
    """将项目根下旧的 grading_data_{user_id} / grading_data 迁入 grading_data_all/（目标不存在时）。"""
    global _legacy_dirs_migrated
    if _legacy_dirs_migrated:
        return
    _legacy_dirs_migrated = True

    all_root = grading_data_all_root()
    try:
        all_root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    root = project_root()
    prefix = "grading_data_"
    try:
        for item in root.iterdir():
            if not item.is_dir() or not item.name.startswith(prefix):
                continue
            dest = all_root / item.name
            if dest.exists():
                continue
            try:
                item.rename(dest)
            except OSError:
                pass
    except OSError:
        pass

    legacy = root / "grading_data"
    if legacy.is_dir():
        legacy_dest = all_root / "grading_data_legacy"
        if not legacy_dest.exists():
            try:
                legacy.rename(legacy_dest)
            except OSError:
                pass


def sanitize_user_id(user_id: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9\-_]", "_", str(user_id or "").strip())
    return token[:64] or "unknown"


def user_grading_dir_name(user_id: str) -> str:
    return f"grading_data_{sanitize_user_id(user_id)}"


def user_grading_root(user_id: str) -> Path:
    return grading_data_all_root() / user_grading_dir_name(user_id)


@dataclass(frozen=True)
class UserGradingPaths:
    root: Path
    temp: Path
    test: Path
    modify: Path
    correct_docs: Path
    correct_docs_img: Path
    scan: Path
    grading_history: Path
    home_img: Path
    ai_diagnosis: Path
    history_legacy: Path
    ct: Path
    zyk_data: Path

    @classmethod
    def for_root(cls, root: Path) -> UserGradingPaths:
        return cls(
            root=root,
            temp=root / "temp",
            test=root / "test",
            modify=root / "modify",
            correct_docs=root / "correct_documents" / "test_paper",
            correct_docs_img=root / "correct_documents" / "test_paper_img",
            scan=root / "scan",
            grading_history=root / "grading_history",
            home_img=root / "home_img",
            ai_diagnosis=root / "ai_diagnosis",
            history_legacy=root / "history",
            ct=root / "ct",
            zyk_data=root / "zyk_data",
        )


def _subdir_names(root: Path) -> list[Path]:
    p = UserGradingPaths.for_root(root)
    return [
        p.temp,
        p.test,
        p.modify,
        p.correct_docs,
        p.correct_docs_img,
        p.scan,
        p.grading_history,
        p.home_img,
        p.ai_diagnosis,
        p.history_legacy,
        p.ct,
        p.zyk_data,
    ]


def ensure_user_grading_layout(user_id: str) -> UserGradingPaths:
    migrate_legacy_grading_dirs_if_needed()
    try:
        grading_data_all_root().mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    root = user_grading_root(user_id)
    paths = UserGradingPaths.for_root(root)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    for d in _subdir_names(root):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    return paths


def get_user_grading_paths(user_id: str) -> UserGradingPaths:
    return ensure_user_grading_layout(user_id)


def set_grading_user_id(user_id: str) -> Token:
    return _grading_user_id.set(sanitize_user_id(user_id) if user_id else user_id)


def reset_grading_user_id(token: Token) -> None:
    try:
        _grading_user_id.reset(token)
    except ValueError:
        # FastAPI 线程池 / 异步切换时 token 可能来自不同 Context，忽略即可
        pass


def get_grading_user_id() -> str:
    uid = _grading_user_id.get()
    if not uid:
        raise RuntimeError("grading user context 未设置")
    return uid


def grading_paths() -> UserGradingPaths:
    return get_user_grading_paths(get_grading_user_id())


T = TypeVar("T")


def run_with_grading_user(user_id: str, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """在线程池等子线程中恢复 grading 用户上下文后执行 fn。"""
    token = set_grading_user_id(user_id)
    try:
        return fn(*args, **kwargs)
    finally:
        reset_grading_user_id(token)


def test_dir() -> Path:
    return grading_paths().test


def modify_dir() -> Path:
    return grading_paths().modify


def correct_docs_dir() -> Path:
    return grading_paths().correct_docs


def correct_docs_img_dir() -> Path:
    return grading_paths().correct_docs_img


def scan_dir() -> Path:
    return grading_paths().scan


def grading_history_dir() -> Path:
    return grading_paths().grading_history


def home_img_dir() -> Path:
    return grading_paths().home_img


def ai_diagnosis_dir() -> Path:
    return grading_paths().ai_diagnosis


def ct_root_for_user(user_id: str) -> Path:
    return get_user_grading_paths(user_id).ct


def ct_root() -> Path:
    return grading_paths().ct


def zyk_dir_for_user(user_id: str) -> Path:
    return get_user_grading_paths(user_id).zyk_data


def zyk_dir() -> Path:
    return grading_paths().zyk_data


def shared_zyk_dir() -> Path:
    """全局共享资源库目录（所有用户共用一套），与各用户的 grading_data_* 平级。"""
    p = grading_data_all_root() / "_shared" / "zyk_data"
    p.mkdir(parents=True, exist_ok=True)
    return p
