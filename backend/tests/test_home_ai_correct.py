# -*- coding: utf-8 -*-
"""首页作业手动修正端点（网页改小程序批改记录的主通道）触碰面测试。

按 (index, sub_index) 对齐覆盖 → 改分台账（human_ai_correct）→ 重画留痕。
FakeRequest 范本：tests/test_essay_rubric_dimensions.py:291-296。
"""
import asyncio
import json
from pathlib import Path

import pytest

from app.grading import router as grading_router


class _FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


@pytest.fixture()
def home_env(tmp_path, monkeypatch):
    """tmp home_img 目录 + 一条带 blocks 的作业记录 + 重绘/台账/链接桩。"""
    monkeypatch.setattr(grading_router, "home_img_dir", lambda: tmp_path)
    monkeypatch.setattr(grading_router, "get_grading_user_id", lambda: "u1")

    redraw_calls = []

    def fake_draw(img_path, blocks, baidu_raw, result_dir, file_stem, **kw):
        redraw_calls.append({"img_path": img_path, "stem": file_stem, "blocks": blocks})
        return f"{file_stem}_orig.jpg", f"{file_stem}_ann.jpg", f"{file_stem}_marks.jpg"

    monkeypatch.setattr(grading_router, "draw_baidu_marks_and_save", fake_draw)
    monkeypatch.setattr(
        grading_router, "build_download_url", lambda path, uid: f"https://x/{path}"
    )

    ledger_calls = []

    def fake_record(user_id, folder, name, engine, rows):
        ledger_calls.append({"user_id": user_id, "folder": folder, "name": name, "rows": rows})

    from app.grading import correction_ledger as cl

    monkeypatch.setattr(cl, "record_corrections", fake_record)

    rec = {
        "id": "job1",
        "name": "张三_数学卷.jpg",
        "user_id": "u1",
        "status": "done",
        "files": {"upload": "job1_upload.jpg"},
        "blocks": [
            {
                "index": 1,
                "sub_index": 1,
                "result": "错",
                "comment": "计算错误",
                "baidu_correct_result": 2,
                "bbox": [0, 0, 10, 10],
            },
            {
                "index": 2,
                "sub_index": 1,
                "result": "对",
                "comment": "",
                "baidu_correct_result": 1,
                "bbox": [0, 20, 10, 30],
            },
        ],
    }
    (tmp_path / "job1.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "job1_upload.jpg").write_bytes(b"img")
    return {"dir": tmp_path, "redraw": redraw_calls, "ledger": ledger_calls}


def _load_record(home_env):
    return json.loads((home_env["dir"] / "job1.json").read_text(encoding="utf-8"))


def test_result_change_updates_blocks_and_ledger(home_env):
    req = _FakeRequest({"blocks": [{"index": 1, "sub_index": 1, "result": "对", "comment": "订正对了"}]})
    resp = asyncio.run(grading_router.api_home_ai_correct("job1", req))

    assert resp["ok"] is True
    rec = _load_record(home_env)
    blk = rec["blocks"][0]
    assert blk["result"] == "对"
    assert blk["baidu_correct_result"] == 1
    assert blk["comment"] == "订正对了"
    assert blk["corrected_by"] == "human"
    assert blk["ai_original_result"] == "错"

    assert len(home_env["ledger"]) == 1
    row = home_env["ledger"][0]["rows"][0]
    assert row["was_result"] == "错"
    assert row["new_result"] == "对"
    assert home_env["ledger"][0]["folder"] == "首页批改"

    assert home_env["redraw"] and home_env["redraw"][0]["stem"] == "job1"
    assert rec["files"]["image_annotated"] == "job1_ann.jpg"
    assert "第1题" in rec["result"] or "对" in rec["result"]


def test_score_only_change_enters_ledger(home_env):
    req = _FakeRequest({"blocks": [{"index": 1, "sub_index": 1, "score": 2.5}]})
    resp = asyncio.run(grading_router.api_home_ai_correct("job1", req))
    assert resp["ok"] is True

    rec = _load_record(home_env)
    assert rec["blocks"][0]["score"] == 2.5
    assert rec["blocks"][0]["result"] == "错"  # 判定没动
    rows = home_env["ledger"][0]["rows"]
    assert rows and rows[0]["was_score"] is None and rows[0]["new_score"] == 2.5


def test_no_change_skips_ledger(home_env):
    # 与原值一致的回传：result_map 非空（过了 400 门槛），但 diff 无变化 → 不写台账
    req = _FakeRequest({"blocks": [{"index": 1, "sub_index": 1, "result": "错", "comment": "计算错误"}]})
    resp = asyncio.run(grading_router.api_home_ai_correct("job1", req))
    assert resp["ok"] is True
    assert home_env["ledger"] == []


def test_blank_result_clears_comment(home_env):
    req = _FakeRequest({"blocks": [{"index": 2, "sub_index": 1, "result": "未作答", "comment": "不该留评语"}]})
    resp = asyncio.run(grading_router.api_home_ai_correct("job1", req))
    assert resp["ok"] is True
    rec = _load_record(home_env)
    blk = rec["blocks"][1]
    assert blk["result"] == "未作答"
    assert blk["comment"] == ""  # 未作答强制清评语


def test_missing_content_400(home_env):
    req = _FakeRequest({"blocks": [{"index": 1, "sub_index": 1}]})
    with pytest.raises(Exception) as ei:
        asyncio.run(grading_router.api_home_ai_correct("job1", req))
    assert "400" in str(ei.value) or "修正内容" in str(ei.value)


def test_owner_mismatch_404(home_env, monkeypatch):
    monkeypatch.setattr(grading_router, "get_grading_user_id", lambda: "u2")
    req = _FakeRequest({"blocks": [{"index": 1, "sub_index": 1, "result": "对"}]})
    with pytest.raises(Exception) as ei:
        asyncio.run(grading_router.api_home_ai_correct("job1", req))
    assert "404" in str(ei.value) or "不存在" in str(ei.value)


def test_missing_job_404(home_env):
    req = _FakeRequest({"blocks": [{"index": 1, "sub_index": 1, "result": "对"}]})
    with pytest.raises(Exception) as ei:
        asyncio.run(grading_router.api_home_ai_correct("nope", req))
    assert "404" in str(ei.value) or "不存在" in str(ei.value)
