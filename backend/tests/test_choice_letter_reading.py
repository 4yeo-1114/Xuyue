# -*- coding: utf-8 -*-
"""选择题手写字母识别加固（20261117 用户反馈：越线/连笔时读成相邻选项、读对却判错）：
1) 只读括号区域（墨迹定位，非纸张专属硬编码）；
2) 双读一致才给结论，不一致 → 待确认；
3) 低置信不自动判，留 read_uncertain + reason + 日志；
4) 连续 ≥3 道选择题判错 → 打复核标记（不改判定）。
"""
import numpy as np
import pytest
from PIL import Image, ImageDraw

import app.grading.answer_key_grading as ak


# ── 工具 ───────────────────────────────────────────────────────────────


def _make_choice_page(tmp_path, name="page.png"):
    """白底 400x120：左侧画「1. A. B. C. D.」印刷选项，右侧 (330,75) 画手写作答括号。"""
    img = Image.new("RGB", (400, 120), "white")
    d = ImageDraw.Draw(img)
    # 靠左的印刷题号 + 选项字母（识别时绝不能把它们当学生答案）
    for x in (10, 45, 80, 115, 150):
        d.text((x, 45), "ABCD"[x % 4] + ".", fill="black")
    # 右侧作答括号（手写墨迹），落在 bbox 内、明显靠右
    d.rectangle((325, 50, 350, 84), outline="black", width=3)
    path = tmp_path / name
    img.save(path)
    return str(path)


def _black_crop(image, box):
    """crop 里是否含深墨迹（用于断言读的是括号而不是整块/印刷区）。"""
    a = np.asarray(image.convert("L").crop(tuple(int(v) for v in box)))
    return a.min() < 100


@pytest.fixture
def letter_stub(monkeypatch):
    """打桩单次读：只有裁到「右侧括号」才读出 C（模拟模型行为），返回调用记录。"""
    calls = []

    def _fake_once(image, box):
        calls.append(tuple(int(v) for v in box))
        return "C" if _black_crop(image, box) else "A"

    monkeypatch.setattr(ak, "_vl_read_choice_once", _fake_once)
    return calls


def _grade_one_choice(path, monkeypatch, *, vl_doc, expected="C", extra_blocks=None):
    block = {
        "slot_id": "c1",
        "label": "1_1",
        "kind": "choice",
        "index": 1,
        "max_score": 4,
        "choice_options": ["A", "B", "C", "D"],
        "bbox": [300, 40, 370, 96],
    }
    blocks = [block] + list(extra_blocks or [])
    monkeypatch.setattr(ak, "_ocr_choice_answers", lambda *a, **k: {})
    monkeypatch.setattr(ak, "_omr_choice_answer", lambda *a, **k: None)
    monkeypatch.setattr(
        ak,
        "_vl_read_choice_answer",
        lambda *a, detailed=False, **k: dict(vl_doc) if detailed else vl_doc.get("letters"),
    )
    monkeypatch.setattr(ak, "_store_answer_key_cache", lambda *a, **k: None)
    decisions = ak.grade_paper_by_answer_key(path, blocks, {"1_1": expected})
    return block, decisions


# ── 1. 括号定位：混有印刷选项字母时只取手写区域 ────────────────────────


def test_bracket_crop_focuses_rightmost_ink(tmp_path):
    path = _make_choice_page(tmp_path)
    with Image.open(path) as im:
        im = im.convert("RGB")
        box, located = ak._bracket_crop_box(im, [0, 40, 380, 100])
    assert located is True
    x1, _, x2, _ = box
    # 只框住右侧括号，印刷的「1. A. B. C. D.」（x<200）被排除
    assert x1 > 250 and x2 < 380
    assert x2 - x1 < 200


def test_detailed_reading_ignores_printed_options(tmp_path, letter_stub):
    path = _make_choice_page(tmp_path)
    doc = ak._vl_read_choice_answer_detailed(path, [0, 40, 380, 100])
    # 整块里印刷了 A/B/C/D，但只读右侧括号 → 单字母 C、高置信
    assert doc["letters"] == "C"
    assert doc["bracket_located"] is True
    assert doc["confidence"] >= 0.8
    assert all(box[0] > 250 for box in letter_stub)


def test_bracket_fallback_when_no_ink(tmp_path):
    img = Image.new("RGB", (200, 100), "white")
    path = tmp_path / "blank.png"
    img.save(path)
    with Image.open(path) as im:
        box, located = ak._bracket_crop_box(im.convert("RGB"), [20, 20, 180, 80])
    assert located is False
    # 失败退回原 bbox（外扩后）而不是抛异常
    assert box[2] > box[0] and box[3] > box[1]


def test_detailed_low_confidence_when_no_bracket(monkeypatch, tmp_path):
    img = Image.new("RGB", (200, 100), "white")
    path = tmp_path / "blank.png"
    img.save(path)
    monkeypatch.setattr(ak, "_vl_read_choice_once", lambda image, box: "C")
    doc = ak._vl_read_choice_answer_detailed(str(path), [20, 20, 180, 80])
    assert doc["letters"] == "C"
    assert doc["bracket_located"] is False
    # 没定位到括号 → 置信度被打折（低于正常 0.9）
    assert doc["confidence"] < 0.9


# ── 2. 双读一致 → 单字母 + 高置信 ──────────────────────────────────────


def test_two_reads_agree_returns_single_letter_high_conf(tmp_path, monkeypatch):
    img = Image.new("RGB", (400, 120), "white")
    ImageDraw.Draw(img).rectangle((325, 50, 350, 84), outline="black", width=3)
    path = tmp_path / "p.png"
    img.save(path)
    monkeypatch.setattr(ak, "_vl_read_choice_once", lambda image, box: "C")
    doc = ak._vl_read_choice_answer_detailed(str(path), [300, 40, 370, 96])
    assert doc["letters"] == "C"
    assert doc["confidence"] >= 0.8
    assert doc["error"] is False
    # 向后兼容：非 detailed 仍返回 str
    assert ak._vl_read_choice_answer(str(path), [300, 40, 370, 96]) == "C"


def test_vl_raw_multi_letter_noise_is_deduped(monkeypatch):
    # 模型输出 "C. B" 这类带噪声 → 解析成两个字母 → 双读集合不一致/多字母，不给单字母结论
    assert ak._parse_choice_letters("c / C") == ["C"]
    assert ak._parse_choice_letters("answer: B") == ["B"]
    assert ak._parse_choice_letters("13") == []


# ── 3. 双读不一致 → None / 低置信 → 待确认 ──────────────────────────────


def test_two_reads_disagree_returns_none_low_conf(tmp_path, monkeypatch):
    img = Image.new("RGB", (400, 120), "white")
    ImageDraw.Draw(img).rectangle((325, 50, 350, 84), outline="black", width=3)
    path = tmp_path / "p.png"
    img.save(path)
    seq = iter(["C", "A"])
    monkeypatch.setattr(ak, "_vl_read_choice_once", lambda image, box: next(seq))
    doc = ak._vl_read_choice_answer_detailed(str(path), [300, 40, 370, 96])
    assert doc["letters"] is None
    assert doc["confidence"] < 0.6
    assert doc["raw1"] == "C" and doc["raw2"] == "A"


def test_disagree_marks_read_uncertain(tmp_path, monkeypatch):
    path = _make_choice_page(tmp_path)
    block, decisions = _grade_one_choice(
        path,
        monkeypatch,
        vl_doc={"letters": None, "confidence": 0.2, "raw1": "C", "raw2": "A", "bracket_located": True, "error": False},
        expected="C",
    )
    assert "c1" not in decisions
    assert block.get("read_uncertain") is True
    assert "人工确认" in str(block.get("reason") or "")
    assert block.get("result") == "待确认"


def test_disagree_with_single_shared_letter_falls_back_low_conf(tmp_path, monkeypatch):
    """双读不一致但模型两次输出都含同一字母（如 C/13-C 混淆）→ 低置信兜底比对。"""
    path = _make_choice_page(tmp_path)
    block, decisions = _grade_one_choice(
        path,
        monkeypatch,
        vl_doc={"letters": None, "confidence": 0.2, "raw1": "C", "raw2": "C?", "bracket_located": True, "error": False},
        expected="C",
    )
    # 兜底置信 0.3 < 0.6 → 仍转待人工确认（不自动判对/判错）
    assert "c1" not in decisions
    assert block.get("read_uncertain") is True


# ── 4. 置信度低于阈值 → read_uncertain=True 且有 reason ─────────────────


def test_low_confidence_marks_read_uncertain_with_reason(tmp_path, monkeypatch):
    path = _make_choice_page(tmp_path)
    block, decisions = _grade_one_choice(
        path,
        monkeypatch,
        vl_doc={"letters": "D", "confidence": 0.5, "raw1": "D", "raw2": "B", "bracket_located": False, "error": False},
        expected="C",
    )
    assert "c1" not in decisions
    assert block.get("read_uncertain") is True
    assert "手写字母识别置信度低" in str(block.get("reason") or "")
    assert "0.5" in str(block.get("reason") or "")


def test_high_confidence_still_grades(tmp_path, monkeypatch):
    path = _make_choice_page(tmp_path)
    block, decisions = _grade_one_choice(
        path,
        monkeypatch,
        vl_doc={"letters": "C", "confidence": 0.9, "raw1": "C", "raw2": "C", "bracket_located": True, "error": False},
        expected="C",
    )
    assert decisions.get("c1", {}).get("status") == "correct"
    assert not block.get("read_uncertain")


def test_low_confidence_but_ocr_clear_still_grades(tmp_path, monkeypatch):
    """OCR 已给出明确答案时，VL 低置信不阻断判定。"""
    path = _make_choice_page(tmp_path)
    block = {
        "slot_id": "c1", "label": "1_1", "kind": "choice", "index": 1,
        "max_score": 4, "bbox": [300, 40, 370, 96],
    }
    monkeypatch.setattr(ak, "_ocr_choice_answers", lambda *a, **k: {1: "C"})
    monkeypatch.setattr(ak, "_omr_choice_answer", lambda *a, **k: None)
    monkeypatch.setattr(ak, "_store_answer_key_cache", lambda *a, **k: None)
    decisions = ak.grade_paper_by_answer_key(path, [block], {"1_1": "C"})
    assert decisions["c1"]["status"] == "correct"


# ── 5. 连续错判复核（纯函数） ───────────────────────────────────────────


def _choice(idx, slot=None):
    return {"slot_id": slot or f"s{idx}", "index": idx, "kind": "choice"}


def test_three_consecutive_wrong_flagged():
    blocks = [_choice(i) for i in (1, 2, 3)]
    decisions = {"s1": {"status": "wrong"}, "s2": {"status": "wrong"}, "s3": {"status": "wrong"}}
    ak._flag_consecutive_wrong(blocks, decisions)
    assert all(b.get("needs_review") is True for b in blocks)
    assert all("连续3题" in str(b.get("reason") or "") for b in blocks)
    # 只打标记，不改判定
    assert all(decisions[f"s{i}"]["status"] == "wrong" for i in (1, 2, 3))


def test_two_consecutive_wrong_not_flagged():
    blocks = [_choice(1), _choice(2)]
    decisions = {"s1": {"status": "wrong"}, "s2": {"status": "wrong"}}
    ak._flag_consecutive_wrong(blocks, decisions)
    assert not any(b.get("needs_review") for b in blocks)
    assert not any(b.get("reason") for b in blocks)


def test_wrong_chain_broken_by_correct():
    blocks = [_choice(i) for i in (1, 2, 3, 4)]
    decisions = {
        "s1": {"status": "wrong"}, "s2": {"status": "wrong"},
        "s3": {"status": "correct"}, "s4": {"status": "wrong"},
    }
    ak._flag_consecutive_wrong(blocks, decisions)
    assert not any(b.get("needs_review") for b in blocks)


def test_block_without_decision_breaks_chain():
    blocks = [_choice(1), _choice(2), _choice(3)]
    decisions = {"s1": {"status": "wrong"}, "s3": {"status": "wrong"}}  # s2 待确认
    ak._flag_consecutive_wrong(blocks, decisions)
    assert not any(b.get("needs_review") for b in blocks)


def test_run_flagging_keeps_existing_reason():
    blocks = [_choice(i) for i in (1, 2, 3)]
    blocks[0]["reason"] = "原有说明"
    decisions = {f"s{i}": {"status": "wrong"} for i in (1, 2, 3)}
    ak._flag_consecutive_wrong(blocks, decisions)
    assert "原有说明" in blocks[0]["reason"]
    assert "连续3题" in blocks[0]["reason"]
