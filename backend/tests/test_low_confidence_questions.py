# -*- coding: utf-8 -*-
"""低置信题批量清单接口测试（只读 · R1 response_logs 摸底）。"""
from datetime import datetime, timezone
from types import SimpleNamespace

from app.grading.router import _bucket_conf, api_low_confidence_questions
from app.models.response_log import ResponseLog


# ---- 纯函数：confidence 分桶 ----
def test_bucket_conf_boundaries():
    assert _bucket_conf(0.0) == "<0.3"
    assert _bucket_conf(0.29) == "<0.3"
    assert _bucket_conf(0.3) == "0.3-0.6"
    assert _bucket_conf(0.5) == "0.3-0.6"
    assert _bucket_conf(0.5999) == "0.3-0.6"
    assert _bucket_conf(0.6) == "0.6-0.8"
    assert _bucket_conf(0.79) == "0.6-0.8"
    assert _bucket_conf(0.8) == ">=0.8"
    assert _bucket_conf(1.0) == ">=0.8"


# ---- 假 DB：覆盖 endpoint 的三种 db.query(...) 用法 ----
class _Chain:
    """模拟 SQLAlchemy Query 链：filter/order_by/limit 均幂等返回自身。"""

    def __init__(self, result):
        self._result = result
        self.limit_n = None

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def all(self):
        return self._result

    def scalar(self):
        return self._result


class _FakeDb:
    def __init__(self, rows, total, agg):
        self._rows, self._total, self._agg = rows, total, agg
        self.items_chain = None
        self.agg_chain = None

    def query(self, *entities):
        if len(entities) == 1 and entities[0] is ResponseLog:
            self.items_chain = _Chain(self._rows)
            return self.items_chain
        if len(entities) == 2:
            self.agg_chain = _Chain(self._agg)
            return self.agg_chain
        return _Chain(self._total)  # func.count(...)


def _call(db, **kwargs):
    """直调 endpoint：FastAPI 的 Query(...) 默认值不会自动求值，需显式传参。"""
    params = dict(confidence_max=0.6, days=7, engine=None, limit=200)
    params.update(kwargs)
    return api_low_confidence_questions(db=db, user_id="u1", **params)


def _row(**overrides):
    base = dict(
        id="r1",
        folder_safe="exam",
        paper_name="p1.jpg",
        engine="vlm",
        question_id="1",
        question_content="第 1 题：计算 3+5",
        status="wrong",
        score=0,
        max_score=5,
        confidence=0.4,
        created_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---- 空数据：空 items + 全 0 分布 ----
def test_low_confidence_empty_data():
    db = _FakeDb(rows=[], total=0, agg=[])
    data = _call(db).data

    assert data["items"] == []
    assert data["count"] == 0
    assert data["total_low_conf"] == 0
    assert data["distribution"] == {"<0.3": 0, "0.3-0.6": 0, "0.6-0.8": 0, ">=0.8": 0}
    assert data["engines"] == {}


# ---- items 序列化：字段映射 + question_content 截断前 200 字符 ----
def test_low_confidence_items_serialization_truncates_content():
    long_content = "题" * 300
    rows = [
        _row(id="r1", question_content=long_content, created_at=datetime(2026, 8, 1, 12, 0, 0)),
        _row(id="r2", question_content=None, created_at=datetime(2026, 8, 1, 12, 0, 1)),
    ]
    db = _FakeDb(rows=rows, total=2, agg=[])
    data = _call(db).data

    assert data["count"] == 2
    assert data["items"][0]["id"] == "r1"
    assert data["items"][0]["folder_safe"] == "exam"
    assert data["items"][0]["paper_name"] == "p1.jpg"
    assert data["items"][0]["engine"] == "vlm"
    assert data["items"][0]["question_id"] == "1"
    assert data["items"][0]["status"] == "wrong"
    assert data["items"][0]["score"] == 0
    assert data["items"][0]["max_score"] == 5
    assert data["items"][0]["confidence"] == 0.4
    assert data["items"][0]["created_at"] == "2026-08-01T12:00:00"
    assert len(data["items"][0]["question_content"]) == 200
    assert data["items"][0]["question_content"] == long_content[:200]
    assert data["items"][1]["question_content"] == ""


# ---- 分布分桶 + engines 分组（基于全量低置信行）----
def test_low_confidence_distribution_and_engines():
    rows = [
        _row(id="r1", confidence=0.2),
        _row(id="r2", confidence=0.5),
    ]
    agg = [(0.2, "vlm"), (0.5, "vlm"), (0.7, "baidu"), (0.9, None)]
    db = _FakeDb(rows=rows, total=4, agg=agg)
    data = _call(db).data

    assert data["total_low_conf"] == 4
    assert data["distribution"] == {"<0.3": 1, "0.3-0.6": 1, "0.6-0.8": 1, ">=0.8": 1}
    assert data["engines"] == {"vlm": 2, "baidu": 1, "unknown": 1}


# ---- engine 参数仅过滤 items，distribution/engines 保持全量 ----
def test_engine_filter_only_affects_items():
    rows = [_row(id="r1", confidence=0.4)]
    agg = [(0.2, "baidu"), (0.5, "vlm")]
    db = _FakeDb(rows=rows, total=2, agg=agg)
    data = _call(db, engine="vlm").data

    assert data["total_low_conf"] == 2  # 不含 engine 过滤
    assert data["distribution"] == {"<0.3": 1, "0.3-0.6": 1, "0.6-0.8": 0, ">=0.8": 0}
    assert data["engines"] == {"baidu": 1, "vlm": 1}


# ---- limit clamp 到 [1, 500] ----
def test_low_confidence_limit_clamped():
    db = _FakeDb(rows=[], total=0, agg=[])
    _call(db, limit=0)
    assert db.items_chain.limit_n == 1

    db = _FakeDb(rows=[], total=0, agg=[])
    _call(db, limit=9999)
    assert db.items_chain.limit_n == 500

    db = _FakeDb(rows=[], total=0, agg=[])
    _call(db, limit=200)
    assert db.items_chain.limit_n == 200
