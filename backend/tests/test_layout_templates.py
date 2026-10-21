# -*- coding: utf-8 -*-
"""布局模板 API 验收：保存 / 列表 / 详情 / 删除 / 逐字节一致 / 非法 id 404。

存储走 grading_data_all/grading_data_{user_id}/layout_templates/*.json，
测试把 grading_data_all_root 指到临时目录，不读不写真数据。
鉴权用 dependency_overrides 注入 get_current_user_id（与 test_scan_billing_scope 同款）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.grading.user_paths as up
from app.dependencies import get_current_user_id
from app.routers import layout_templates


USER_A = "u-teacher-a"
USER_B = "u-teacher-b"


SAMPLE_LAYOUT = {
    "version": 1,
    "pages": [
        {
            "page_no": 1,
            "filename": "std_1.jpg",
            "image_url": "grading/xxx/std_1.jpg",
            "image_size": [1240, 1754],
            "questions": [
                {
                    "question_id": "q-1",
                    "display_no": 1,
                    "question_type": "fill",
                    "question_text": "1+1=?",
                    "regions": [
                        {
                            "region_id": "q-1-r1",
                            "label": "1-A",
                            "role": "question",
                            "order": 1,
                            "bbox": [100, 200, 800, 320],
                        }
                    ],
                    "answer_slots": [
                        {
                            "slot_id": "q-1-s1",
                            "label": "1_1",
                            "order": 1,
                            "regions": [
                                {
                                    "bbox": [120, 330, 500, 400],
                                }
                            ],
                            "bbox": [120, 330, 500, 400],
                            "has_handwriting_location": True,
                        }
                    ],
                }
            ],
        }
    ],
}


@pytest.fixture(autouse=True)
def _storage_root(monkeypatch, tmp_path):
    """模板存储根指向临时 grading_data_all，避免写真目录。"""
    empty = tmp_path / "grading_data_all"
    empty.mkdir()
    monkeypatch.setattr(up, "grading_data_all_root", lambda: empty)
    yield empty


def _client(viewer: str) -> TestClient:
    app = FastAPI()
    app.include_router(layout_templates.router)
    app.dependency_overrides[get_current_user_id] = lambda: viewer
    # 注：本机 with 上下文可能挂起，故直接 new 出来用（与 test_scan_billing_scope 一致）
    return TestClient(app)


def _save(client: TestClient, name: str = "期中数学卷", **extra):
    body = {
        "name": name,
        "layout": json.loads(json.dumps(SAMPLE_LAYOUT)),
        "source_folder": "cls_001__期中",
        "class_id": "001",
        "subject": "数学",
    }
    body.update(extra)
    resp = client.post("/layout-templates", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_save_layout_template_returns_meta_without_full_layout():
    client = _client(USER_A)
    meta = _save(client)
    assert meta["id"].startswith("lt_")
    assert meta["name"] == "期中数学卷"
    assert meta["subject"] == "数学"
    assert meta["class_id"] == "001"
    assert meta["source_folder"] == "cls_001__期中"
    assert meta["page_count"] == 1
    assert "layout" not in meta
    assert meta["created_at"]
    assert meta["updated_at"]


def test_list_layout_templates_and_filters():
    client = _client(USER_A)
    _save(client, name="数学模板", subject="数学", class_id="001")
    _save(client, name="语文模板", subject="语文", class_id="002")

    all_rows = client.get("/layout-templates").json()["data"]
    assert {row["name"] for row in all_rows} == {"数学模板", "语文模板"}

    math_rows = client.get("/layout-templates", params={"subject": "数学"}).json()["data"]
    assert [row["name"] for row in math_rows] == ["数学模板"]

    cls_rows = client.get("/layout-templates", params={"class_id": "002"}).json()["data"]
    assert [row["name"] for row in cls_rows] == ["语文模板"]

    both = client.get(
        "/layout-templates", params={"class_id": "001", "subject": "数学"}
    ).json()["data"]
    assert [row["name"] for row in both] == ["数学模板"]


def test_get_layout_template_layout_byte_identical():
    client = _client(USER_A)
    meta = _save(client)
    detail = client.get(f"/layout-templates/{meta['id']}").json()["data"]
    assert detail["id"] == meta["id"]
    assert detail["name"] == "期中数学卷"
    # layout 逐字节一致（round-trip 后与请求体相同）
    assert detail["layout"] == SAMPLE_LAYOUT
    raw = json.dumps(detail["layout"], ensure_ascii=False, sort_keys=True)
    expected = json.dumps(SAMPLE_LAYOUT, ensure_ascii=False, sort_keys=True)
    assert raw == expected


def test_delete_layout_template():
    client = _client(USER_A)
    meta = _save(client)
    resp = client.delete(f"/layout-templates/{meta['id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] is True

    gone = client.get(f"/layout-templates/{meta['id']}")
    assert gone.status_code == 404

    rows = client.get("/layout-templates").json()["data"]
    assert rows == []


def test_missing_or_illegal_id_returns_404():
    client = _client(USER_A)
    assert client.get("/layout-templates/lt_doesnotexist").status_code == 404
    assert client.delete("/layout-templates/lt_doesnotexist").status_code == 404
    # 路径穿越 / 非法字符一律 404（不暴露路径）
    for bad in ("..", "../secrets", "a/b", "..%2fetc", "lt_x/../y"):
        assert client.get(f"/layout-templates/{bad}").status_code in (404, 422)
        assert client.delete(f"/layout-templates/{bad}").status_code in (404, 422)


def test_templates_are_isolated_per_user():
    client_a = _client(USER_A)
    client_b = _client(USER_B)
    meta = _save(client_a, name="A的模板")

    # B 列表为空，且不能读/删 A 的模板
    assert client_b.get("/layout-templates").json()["data"] == []
    assert client_b.get(f"/layout-templates/{meta['id']}").status_code == 404
    assert client_b.delete(f"/layout-templates/{meta['id']}").status_code == 404
    # A 的还在
    assert client_a.get(f"/layout-templates/{meta['id']}").status_code == 200


def test_save_rejects_empty_name_or_empty_layout():
    client = _client(USER_A)
    resp = client.post(
        "/layout-templates",
        json={"name": "   ", "layout": SAMPLE_LAYOUT},
    )
    assert resp.status_code == 422

    resp = client.post(
        "/layout-templates",
        json={"name": "ok", "layout": {"pages": []}},
    )
    assert resp.status_code == 422


def test_template_file_lives_under_user_layout_templates_dir(_storage_root: Path):
    client = _client(USER_A)
    meta = _save(client)
    path = (
        _storage_root
        / up.user_grading_dir_name(USER_A)
        / "layout_templates"
        / f"{meta['id']}.json"
    )
    assert path.is_file()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["layout"] == SAMPLE_LAYOUT
    assert on_disk["source_folder"] == "cls_001__期中"
