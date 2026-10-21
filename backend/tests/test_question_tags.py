# -*- coding: utf-8 -*-
"""题库批量打标 API 验收：批量写部分更新 / 幂等 / 按 keys 取 / 用户隔离 / 非法 key / 空 keys。

存储走 grading_data_all/grading_data_{user_id}/question_tags.json，
测试把 grading_data_all_root 指到临时目录，不读不写真数据。
鉴权用 dependency_overrides 注入 get_current_user_id（与 test_layout_templates 同款）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.grading.user_paths as up
from app.dependencies import get_current_user_id
from app.routers import question_tags


USER_A = "u-teacher-a"
USER_B = "u-teacher-b"

# 校本 fingerprint 形态：fp_ + 64hex
KEY_SCHOOL = "fp_" + "a" * 64
# PG 资产 unique_key 形态
KEY_PG = "uk_math_001"


@pytest.fixture(autouse=True)
def _storage_root(monkeypatch, tmp_path):
    """标签存储根指向临时 grading_data_all，避免写真目录。"""
    empty = tmp_path / "grading_data_all"
    empty.mkdir()
    monkeypatch.setattr(up, "grading_data_all_root", lambda: empty)
    yield empty


def _client(viewer: str) -> TestClient:
    app = FastAPI()
    app.include_router(question_tags.router)
    app.dependency_overrides[get_current_user_id] = lambda: viewer
    # 本机 with 上下文可能挂起，故直接 new 出来用（与 test_layout_templates 一致）
    return TestClient(app)


def _batch_put(client: TestClient, keys: list[str], tags: dict, expect: int = 200):
    resp = client.put("/question-tags/batch", json={"keys": keys, "tags": tags})
    assert resp.status_code == expect, resp.text
    return resp.json()


def test_batch_write_and_get_by_keys():
    client = _client(USER_A)
    body = _batch_put(
        client,
        [KEY_SCHOOL, KEY_PG],
        {
            "unit": "第一单元",
            "knowledge_points": ["分数", "小数"],
            "difficulty": "中",
            "question_type": "选择题",
            "source": "pg",
        },
    )
    assert body["data"]["updated"] == 2
    assert set(body["data"]["tags"].keys()) == {KEY_SCHOOL, KEY_PG}

    got = client.get(
        "/question-tags", params={"keys": f"{KEY_SCHOOL},{KEY_PG}"}
    ).json()["data"]
    assert got[KEY_SCHOOL]["unit"] == "第一单元"
    assert got[KEY_SCHOOL]["knowledge_points"] == ["分数", "小数"]
    assert got[KEY_SCHOOL]["difficulty"] == "中"
    assert got[KEY_PG]["question_type"] == "选择题"
    assert got[KEY_PG]["source"] == "pg"
    assert got[KEY_SCHOOL]["updated_at"]


def test_partial_update_only_touches_provided_fields():
    client = _client(USER_A)
    _batch_put(
        client,
        [KEY_PG],
        {
            "unit": "第二单元",
            "knowledge_points": ["力学"],
            "difficulty": "难",
            "question_type": "填空题",
        },
    )
    # 只改 unit，其余字段必须原样保留
    body = _batch_put(client, [KEY_PG], {"unit": "第三单元"})
    row = body["data"]["tags"][KEY_PG]
    assert row["unit"] == "第三单元"
    assert row["knowledge_points"] == ["力学"]
    assert row["difficulty"] == "难"
    assert row["question_type"] == "填空题"


def test_batch_write_is_idempotent():
    client = _client(USER_A)
    tags = {"unit": "U1", "knowledge_points": ["kp-a"], "difficulty": "易", "question_type": "判断题"}
    first = _batch_put(client, [KEY_SCHOOL], tags)["data"]["tags"][KEY_SCHOOL]
    second = _batch_put(client, [KEY_SCHOOL], tags)["data"]["tags"][KEY_SCHOOL]
    # 幂等：两次同参写入内容一致（updated_at 时间戳允许相同或不同）
    assert first["unit"] == second["unit"] == "U1"
    assert first["knowledge_points"] == second["knowledge_points"] == ["kp-a"]
    assert first["difficulty"] == second["difficulty"] == "易"
    assert first["question_type"] == second["question_type"] == "判断题"

    got = client.get("/question-tags", params={"keys": KEY_SCHOOL}).json()["data"]
    assert got[KEY_SCHOOL]["unit"] == "U1"


def test_users_are_isolated():
    client_a = _client(USER_A)
    client_b = _client(USER_B)
    _batch_put(client_a, [KEY_PG], {"unit": "A的单元", "source": "pg"})

    # B 按 keys 取不到 A 的标签
    got_b = client_b.get("/question-tags", params={"keys": KEY_PG}).json()["data"]
    assert got_b == {}
    # B 全量也看不到
    assert client_b.get("/question-tags").json()["data"] == {}

    # B 自己写同 key，互不影响
    _batch_put(client_b, [KEY_PG], {"unit": "B的单元"})
    assert (
        client_a.get("/question-tags", params={"keys": KEY_PG}).json()["data"][KEY_PG][
            "unit"
        ]
        == "A的单元"
    )
    assert (
        client_b.get("/question-tags", params={"keys": KEY_PG}).json()["data"][KEY_PG][
            "unit"
        ]
        == "B的单元"
    )


def test_illegal_keys_rejected():
    client = _client(USER_A)
    for bad in (
        "../secrets",
        "a/b",
        "..",
        "fp_x/../../etc",
        "a\\b",
        "x" * 81,  # 超长
    ):
        resp = client.put(
            "/question-tags/batch",
            json={"keys": [bad], "tags": {"unit": "U"}},
        )
        assert resp.status_code == 422, f"key={bad!r} 应拒绝，实际 {resp.status_code}"

        resp = client.get("/question-tags", params={"keys": bad})
        assert resp.status_code == 422, f"GET key={bad!r} 应拒绝"

    # PUT 空串 / 空白 key 同样拒绝
    for bad in ("", "  "):
        resp = client.put(
            "/question-tags/batch",
            json={"keys": [bad], "tags": {"unit": "U"}},
        )
        assert resp.status_code == 422, f"PUT key={bad!r} 应拒绝"


def test_empty_keys_boundaries():
    client = _client(USER_A)
    # GET keys= 空串 → 空 map（不报错）
    assert client.get("/question-tags", params={"keys": ""}).json()["data"] == {}
    # GET keys=,,  仅逗号 → 空 map
    assert client.get("/question-tags", params={"keys": ",,"}).json()["data"] == {}
    # PUT 空 keys 列表 → 422
    resp = client.put("/question-tags/batch", json={"keys": [], "tags": {"unit": "U"}})
    assert resp.status_code == 422
    # PUT 缺 keys 字段 → 422
    resp = client.put("/question-tags/batch", json={"tags": {"unit": "U"}})
    assert resp.status_code == 422


def test_list_all_returns_full_map_and_file_layout(_storage_root: Path):
    client = _client(USER_A)
    _batch_put(client, [KEY_SCHOOL, KEY_PG], {"unit": "全量单元", "source": "school"})
    all_tags = client.get("/question-tags").json()["data"]
    assert set(all_tags.keys()) == {KEY_SCHOOL, KEY_PG}

    path = _storage_root / up.user_grading_dir_name(USER_A) / "question_tags.json"
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["version"] == 1
    assert set(on_disk["tags"].keys()) == {KEY_SCHOOL, KEY_PG}
    assert on_disk["tags"][KEY_SCHOOL]["unit"] == "全量单元"


def test_clear_field_with_empty_string():
    client = _client(USER_A)
    _batch_put(client, [KEY_PG], {"unit": "要清掉", "difficulty": "中"})
    body = _batch_put(client, [KEY_PG], {"unit": ""})
    row = body["data"]["tags"][KEY_PG]
    assert row["unit"] is None
    assert row["difficulty"] == "中"  # 未传字段保留
