# -*- coding: utf-8 -*-
"""结构化扣分项（deduction_items）测试：归一 / 持久化往返 / 整体覆盖 / 旧记录安全 / 台账共存。

数据存 grading_history item JSON（不建表不加列）；key 与统分键一致
「第N题」「第N题-作答区M」；points 为正数扣分。
"""
import json
import threading

from app.grading import router as r
from app.grading.correction_ledger import diff_score_map_rows
from app.grading.router import _normalize_deduction_items, _save_manual_slot_decisions


# ── 纯函数：_normalize_deduction_items ─────────────────────────────────


def test_normalize_none_means_unchanged():
    assert _normalize_deduction_items(None) is None


def test_normalize_filters_garbage_and_coerces_points():
    raw = {
        "第3题": [
            {"label": "步骤不全", "points": 1},
            {"label": "结果错", "points": "1.5"},
            {"label": "", "points": -0.5},  # 负数取绝对值
            "not-a-dict",
            {"label": "", "points": 0},  # 全空丢弃
            {"label": "有标签", "points": "abc"},  # 非法分丢弃
        ],
        "": [{"label": "x", "points": 1}],  # 空 key 丢弃
        "第5题-作答区2": [{"label": "错别字", "points": 0.5}],
    }
    out = _normalize_deduction_items(raw)
    assert set(out.keys()) == {"第3题", "第5题-作答区2"}
    assert out["第3题"] == [
        {"label": "步骤不全", "points": 1.0},
        {"label": "结果错", "points": 1.5},
        {"label": "", "points": 0.5},  # 负分取绝对值后保留
        # {"label": "有标签", "points": "abc"} 非法分被丢弃
    ]
    assert out["第5题-作答区2"] == [{"label": "错别字", "points": 0.5}]


def test_normalize_non_dict_raw_becomes_empty_clear():
    assert _normalize_deduction_items("junk") == {}
    assert _normalize_deduction_items([1, 2]) == {}


def test_normalize_keeps_empty_list_per_key():
    # 空列表 = 该题清空扣分项，保留键
    out = _normalize_deduction_items({"第1题": [], "第2题": [{"label": "a", "points": 1}]})
    assert out["第1题"] == []
    assert out["第2题"] == [{"label": "a", "points": 1.0}]


# ── 持久化：_save_manual_slot_decisions ────────────────────────────────


def _make_item():
    return {
        "name": "s1.jpg",
        "result": json.dumps(
            {
                "type": "manual_analyze",
                "manual_status": "analyzed",
                "blocks": [
                    {
                        "index": 3,
                        "sub_index": None,
                        "slot_id": "q3-s1",
                        "title": "第3题",
                        "max_score": 5,
                        "status": "ungraded",
                        "score": None,
                        "bbox": [0, 0, 10, 10],
                    },
                    {
                        "index": 5,
                        "sub_index": 2,
                        "slot_id": "q5-s2",
                        "title": "第5题-作答区2",
                        "is_sub": True,
                        "max_score": 3,
                        "status": "ungraded",
                        "score": None,
                        "bbox": [0, 0, 10, 10],
                    },
                ],
            }
        ),
    }


def _decisions():
    return {
        "q3-s1": {"status": "partial", "score": 3.5},
        "q5-s2": {"status": "partial", "score": 2.5},
    }


def _mock_side_effects(monkeypatch):
    monkeypatch.setattr(r, "_persist_grading_success", lambda *a, **k: None)
    monkeypatch.setattr(r, "_schedule_response_log_write", lambda *a, **k: None)
    monkeypatch.setattr(r, "_schedule_wrong_annotation_generation", lambda *a, **k: None)
    monkeypatch.setattr(r, "_regenerate_wrong_annotation_marks", lambda *a, **k: None)
    monkeypatch.setattr(r, "_write_grading_history", lambda *a, **k: None)
    monkeypatch.setattr(r, "_read_grading_history", lambda *a, **k: {})
    monkeypatch.setattr(r, "get_grading_user_id", lambda: "u1")
    monkeypatch.setattr(r, "_grading_history_lock", threading.Lock())


def test_save_manual_slot_decisions_persists_deduction_items(monkeypatch):
    _mock_side_effects(monkeypatch)
    item = _make_item()
    res_json = json.loads(item["result"])
    deductions = {
        "第3题": [{"label": "步骤不全", "points": 1.0}, {"label": "结果错", "points": 1.5}],
        "第5题-作答区2": [{"label": "错别字", "points": 0.5}],
    }
    saved = _save_manual_slot_decisions(
        "exam",
        "s1.jpg",
        item,
        res_json,
        _decisions(),
        generate_marks=False,
        question_notes={},
        paper_note="",
        deduction_items=deductions,
    )
    assert saved["deduction_items"] == deductions
    inner = json.loads(saved["result"])
    assert inner["deduction_items"] == deductions


def test_save_deduction_items_wholesale_overwrite(monkeypatch):
    _mock_side_effects(monkeypatch)
    item = _make_item()
    res_json = json.loads(item["result"])
    first = {"第3题": [{"label": "旧", "points": 1.0}]}
    saved = _save_manual_slot_decisions(
        "exam", "s1.jpg", item, res_json, _decisions(),
        generate_marks=False, question_notes={}, paper_note="",
        deduction_items=first,
    )
    assert saved["deduction_items"] == first

    # 第二次整体覆盖：旧的「旧」被替换，不在新 map 里的键消失
    res_json2 = json.loads(saved["result"])
    second = {"第5题-作答区2": [{"label": "新", "points": 0.5}]}
    saved2 = _save_manual_slot_decisions(
        "exam", "s1.jpg", saved, res_json2, _decisions(),
        generate_marks=False, question_notes={}, paper_note="",
        deduction_items=second,
    )
    assert saved2["deduction_items"] == second
    assert "第3题" not in saved2["deduction_items"]


def test_save_without_deduction_items_keeps_old(monkeypatch):
    _mock_side_effects(monkeypatch)
    item = _make_item()
    res_json = json.loads(item["result"])
    first = {"第3题": [{"label": "保留", "points": 1.0}]}
    saved = _save_manual_slot_decisions(
        "exam", "s1.jpg", item, res_json, _decisions(),
        generate_marks=False, question_notes={}, paper_note="",
        deduction_items=first,
    )
    # 第二次不带 deduction_items（None = 本次不改）
    res_json2 = json.loads(saved["result"])
    saved2 = _save_manual_slot_decisions(
        "exam", "s1.jpg", saved, res_json2, _decisions(),
        generate_marks=False, question_notes={}, paper_note="",
        deduction_items=None,
    )
    assert saved2.get("deduction_items") == first


def test_old_record_without_deduction_items_does_not_crash(monkeypatch):
    # 旧记录 res_json/item 都没有 deduction_items：正常保存、读出也不炸
    _mock_side_effects(monkeypatch)
    item = _make_item()
    res_json = json.loads(item["result"])
    assert "deduction_items" not in res_json
    assert "deduction_items" not in item
    saved = _save_manual_slot_decisions(
        "exam", "s1.jpg", item, res_json, _decisions(),
        generate_marks=False, question_notes={}, paper_note="",
        deduction_items=None,
    )
    # 无字段 = 不新增（旧记录语义）
    assert "deduction_items" not in saved or saved.get("deduction_items") is None


def test_ledger_coexistence_score_change_preserves_deduction_items(monkeypatch):
    """纯调分台账不受影响：改分后 deduction_items 保留，台账行正常产出。"""
    _mock_side_effects(monkeypatch)
    item = _make_item()
    res_json = json.loads(item["result"])
    deductions = {"第3题": [{"label": "步骤不全", "points": 1.0}]}
    saved = _save_manual_slot_decisions(
        "exam", "s1.jpg", item, res_json, _decisions(),
        generate_marks=False, question_notes={}, paper_note="",
        deduction_items=deductions,
    )
    # 模拟「已批过再改分」：prev status 非 ungraded
    res_json2 = json.loads(saved["result"])
    for blk in res_json2["blocks"]:
        blk["status"] = "partial"
        blk["score"] = 1.0
    saved["result"] = json.dumps(res_json2, ensure_ascii=False)
    saved2 = _save_manual_slot_decisions(
        "exam", "s1.jpg", saved, res_json2, _decisions(),
        generate_marks=False, question_notes={}, paper_note="",
        deduction_items=deductions,
    )
    assert saved2["deduction_items"] == deductions
    # 纯调分台账：prev 有分、new 不等 → 有行
    prev_scores = {"第3题": 1.0, "第5题-作答区2": 1.0}
    new_scores = {"第3题": 3.5, "第5题-作答区2": 2.5}
    rows = diff_score_map_rows(prev_scores, new_scores)
    assert len(rows) == 2
    assert rows[0]["index"] == "3"
    assert rows[0]["was_score"] == 1.0 and rows[0]["new_score"] == 3.5


def test_clear_semantics_empty_dict_wipes(monkeypatch):
    _mock_side_effects(monkeypatch)
    item = _make_item()
    res_json = json.loads(item["result"])
    first = {"第3题": [{"label": "旧", "points": 1.0}]}
    saved = _save_manual_slot_decisions(
        "exam", "s1.jpg", item, res_json, _decisions(),
        generate_marks=False, question_notes={}, paper_note="",
        deduction_items=first,
    )
    res_json2 = json.loads(saved["result"])
    saved2 = _save_manual_slot_decisions(
        "exam", "s1.jpg", saved, res_json2, _decisions(),
        generate_marks=False, question_notes={}, paper_note="",
        deduction_items={},  # 显式空 = 清空
    )
    assert saved2["deduction_items"] == {}
    inner = json.loads(saved2["result"])
    assert inner["deduction_items"] == {}
