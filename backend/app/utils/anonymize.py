# -*- coding: utf-8 -*-
"""学生姓名匿名化工具。

PII 防护：所有发往第三方千问模型的学生姓名，在出站前匿名化为「学生01」等稳定标识，
AI 返回后再还原回真名入库/展示。映射为请求级（每次请求新建 Anonymizer），
同一请求内幂等，并加锁保证可被 ThreadPoolExecutor 的多个 worker 线程共享
（如 class_analysis 并发多个 vision batch 时，各线程看到同一个映射）。
"""

from __future__ import annotations

import re
import threading
from typing import Any

# 结构化字段名：这些 key 下的字符串（或字符串列表）即学生姓名 / 姓名集合
_STUDENT_NAME_KEYS: tuple[str, ...] = (
    "student_name",
    "student_names",
    "affected_students",
    "student_box",
    "wrong_students",
)

# 学生对象容器：递归进去后把 "name" 也当作姓名处理（如 papers[].student、deterministic.students）
_STUDENT_CONTAINER_KEYS: tuple[str, ...] = ("student", "students")


class Anonymizer:
    """学生姓名匿名化：真实姓名 ↔ 匿名标识（学生01）双向稳定映射，同请求内幂等。"""

    def __init__(self) -> None:
        self._real_to_anon: dict[str, str] = {}
        self._anon_to_real: dict[str, str] = {}
        self._next_index = 1
        self._lock = threading.RLock()

    # ---------- 基础映射 ----------

    def anon(self, real: str) -> str:
        """真名 → 匿名标识（学生01）。重复调用同真名返回同一匿名；空串原样返回。"""
        real = str(real or "").strip()
        if not real:
            return real
        with self._lock:
            token = self._real_to_anon.get(real)
            if token is None:
                token = f"学生{self._next_index:02d}"
                self._next_index += 1
                self._real_to_anon[real] = token
                self._anon_to_real[token] = real
            return token

    def restore(self, token: str) -> str:
        """匿名标识 → 真名。未知串 / 非匿名串原样返回。"""
        token = str(token or "").strip()
        if not token:
            return token
        with self._lock:
            return self._anon_to_real.get(token, token)

    # ---------- 文本替换 ----------

    def anon_text(self, text: str) -> str:
        """把文本中出现的真实姓名替换为匿名标识（按最长真名优先，避免前缀覆盖）。"""
        if not isinstance(text, str) or not text:
            return text
        with self._lock:
            names = sorted(self._real_to_anon, key=len, reverse=True)
            if not names:
                return text
            mapping = {name: self._real_to_anon[name] for name in names}
        pattern = re.compile("|".join(re.escape(name) for name in names))
        return pattern.sub(lambda m: mapping[m.group(0)], text)

    def restore_text(self, text: str) -> str:
        """把文本中出现的匿名标识（学生01）替换回真实姓名，用于 AI 返回内容还原。"""
        if not isinstance(text, str) or not text:
            return text
        with self._lock:
            tokens = sorted(self._anon_to_real, key=len, reverse=True)
            if not tokens:
                return text
            mapping = {token: self._anon_to_real[token] for token in tokens}
        pattern = re.compile("|".join(re.escape(token) for token in tokens))
        return pattern.sub(lambda m: mapping[m.group(0)], text)

    # ---------- 结构化递归 ----------

    def _anon_value(self, value: Any, keys: tuple[str, ...], *, name_ok: bool) -> Any:
        if isinstance(value, str):
            return self.anon(value)
        if isinstance(value, list):
            return [self._anon_value(x, keys, name_ok=name_ok) for x in value]
        if isinstance(value, dict):
            return self.anon_deep(value, keys=keys, name_ok=name_ok)
        return value

    def anon_deep(
        self,
        data: Any,
        *,
        keys: tuple[str, ...] = _STUDENT_NAME_KEYS,
        name_ok: bool = False,
    ) -> Any:
        """递归匿名化结构中的学生姓名字段，返回新结构（不修改原数据）。

        - keys 命中的 key：字符串 → anon()；字符串列表 → 逐项 anon()。
        - student / students 容器：递归进入后把 "name" 也当作姓名处理。
        """
        effective_keys = keys + ("name",) if name_ok else keys
        if isinstance(data, dict):
            out: dict[str, Any] = {}
            for key, value in data.items():
                if key in _STUDENT_CONTAINER_KEYS:
                    if isinstance(value, list):
                        out[key] = [self._anon_value(x, effective_keys, name_ok=True) for x in value]
                    elif isinstance(value, dict):
                        out[key] = self.anon_deep(value, keys=effective_keys, name_ok=True)
                    elif isinstance(value, str):
                        out[key] = self.anon(value)
                    else:
                        out[key] = value
                elif key in effective_keys:
                    out[key] = self._anon_value(value, effective_keys, name_ok=name_ok)
                elif isinstance(value, (dict, list)):
                    out[key] = self.anon_deep(value, keys=effective_keys, name_ok=name_ok)
                else:
                    out[key] = value
            return out
        if isinstance(data, list):
            return [self._anon_value(x, effective_keys, name_ok=name_ok) for x in data]
        return data

    def anon_text_deep(self, data: Any) -> Any:
        """递归对结构内所有字符串做 anon_text（真名→匿名），返回新结构（不修改原数据）。"""
        if isinstance(data, dict):
            return {key: self.anon_text_deep(value) for key, value in data.items()}
        if isinstance(data, list):
            return [self.anon_text_deep(value) for value in data]
        if isinstance(data, str):
            return self.anon_text(data)
        return data

    def restore_deep(self, data: Any) -> Any:
        """递归把结构内所有字符串里的匿名标识还原为真名，返回新结构（不修改原数据）。"""
        if isinstance(data, dict):
            return {key: self.restore_deep(value) for key, value in data.items()}
        if isinstance(data, list):
            return [self.restore_deep(value) for value in data]
        if isinstance(data, str):
            return self.restore_text(data)
        return data
