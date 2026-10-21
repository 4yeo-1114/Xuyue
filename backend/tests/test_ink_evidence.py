# -*- coding: utf-8 -*-
"""ink_evidence（VL 笔迹证据复核）单测：候选谓词 / 三档策略 / fail-safe / 合成网格。

用 fake client 注入 VL 响应，不发真实请求。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from app.grading.ink_evidence import (
    _as_bool,
    _compose_labeled_crops,
    _json_array_from_text,
    verify_handwriting_with_vl,
)


class FakeClient:
    """contents 队列按调用顺序取响应（超出重复最后一个）；两段式=网格初筛+单面板确认。"""

    def __init__(
        self,
        content: str = "",
        error: Exception | None = None,
        contents: list | None = None,
    ):
        self.content = content
        self.contents = list(contents) if contents is not None else None
        self.error = error
        self.calls = 0
        self.requests: list = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        self.requests.append(kwargs)
        if self.error is not None:
            raise self.error
        content = (
            self.contents[min(self.calls - 1, len(self.contents) - 1)]
            if self.contents is not None
            else self.content
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


def _image(tmp_path: Path) -> str:
    path = Path(tmp_path) / "paper.png"
    Image.new("RGB", (200, 200), "white").save(path)
    return str(path)


def _blk(
    *,
    index=1,
    sub_index=1,
    result="错",
    is_slot=True,
    has_hw=True,
    bbox=None,
    guard=None,
):
    box = bbox or [10, 10, 80, 80]
    block = {
        "index": index,
        "sub_index": sub_index,
        "result": result,
        "comment": "原评语",
        "partial_ratio": 0.5 if result == "半对" else None,
        "baidu_correct_result": {"对": 1, "错": 2, "未作答": 3, "半对": 4}.get(result),
        "baidu_is_slot": is_slot,
        "has_handwriting_location": has_hw,
        "bbox": box,
        "reference_vlm_answer_bbox": box,
    }
    if guard:
        block["form_guard"] = guard
    return block


def test_candidates_exclude_stems_unanswered_and_downgraded(tmp_path, monkeypatch):
    monkeypatch.delenv("INK_EVIDENCE_VL", raising=False)
    stem = _blk(index=1, is_slot=False, has_hw=False)
    unanswered = _blk(index=2, result="未作答")
    already = _blk(index=3, guard={"action": "downgraded", "was_result": "错"})
    real = _blk(index=4)
    client = FakeClient(content='[{"id": 1, "has_handwriting": false, "confidence": 0.9}]')
    changes = verify_handwriting_with_vl(
        _image(tmp_path), [stem, unanswered, already, real], client=client
    )
    # 只有真作答区进候选：题干块 / 未作答 / 已降级一律不动
    assert client.calls == 2  # 网格初筛 1 次 + 唯一 false 面板单面板确认 1 次
    assert stem["result"] == "错" and "ink_evidence" not in stem
    assert unanswered["result"] == "未作答" and "ink_evidence" not in unanswered
    assert already["result"] == "错" and "ink_evidence" not in already
    assert real["result"] == "未作答"
    assert len(changes) == 1
    assert changes[0]["action"] == "downgraded"
    assert changes[0]["was_result"] == "错"


def test_no_handwriting_high_confidence_downgrades(tmp_path, monkeypatch):
    monkeypatch.delenv("INK_EVIDENCE_VL", raising=False)
    blk = _blk(result="错", bbox=[10, 10, 120, 120])
    client = FakeClient(content='[{"id": 1, "has_handwriting": false, "confidence": 0.85}]')
    changes = verify_handwriting_with_vl(_image(tmp_path), [blk], client=client)
    # 强降级字段集与 form_guard 完全一致
    assert blk["result"] == "未作答"
    assert blk["comment"] == ""
    assert blk["partial_ratio"] is None
    assert blk["baidu_correct_result"] == 3
    assert blk["ink_evidence"] == {
        "action": "downgraded",
        "has_handwriting": False,
        "confidence": 0.85,
        "was_result": "错",
        "confirmed": True,
    }
    assert changes == [
        {
            "index": 1,
            "sub_index": 1,
            "action": "downgraded",
            "has_handwriting": False,
            "confidence": 0.85,
            "was_result": "错",
            "confirmed": True,
        }
    ]


def test_no_handwriting_gray_confidence_flags_only(tmp_path, monkeypatch):
    monkeypatch.delenv("INK_EVIDENCE_VL", raising=False)
    blk = _blk(result="对")
    client = FakeClient(content='[{"id": 1, "has_handwriting": false, "confidence": 0.5}]')
    changes = verify_handwriting_with_vl(_image(tmp_path), [blk], client=client)
    assert blk["result"] == "对"  # 不改判
    assert blk["ink_evidence"]["suspicious"] is True
    assert blk["ink_evidence"]["action"] == "flagged"
    assert changes[0]["action"] == "flagged"
    assert changes[0]["was_result"] == "对"


def test_no_handwriting_low_confidence_no_action(tmp_path, monkeypatch):
    monkeypatch.delenv("INK_EVIDENCE_VL", raising=False)
    blk = _blk()
    client = FakeClient(content='[{"id": 1, "has_handwriting": false, "confidence": 0.3}]')
    changes = verify_handwriting_with_vl(_image(tmp_path), [blk], client=client)
    assert blk["result"] == "错"
    assert "ink_evidence" not in blk
    assert changes == []


def test_policy_boundary_gray_band(tmp_path, monkeypatch):
    monkeypatch.delenv("INK_EVIDENCE_VL", raising=False)
    # 三档看【确认】置信：0.7 落灰区上界（只标）；>0.7 才强降级；0.4 落灰区下界（只标）
    blk_a, blk_b, blk_c = _blk(index=1), _blk(index=2), _blk(index=3)
    grid = (
        '[{"id": 1, "has_handwriting": false, "confidence": 1.0},'
        ' {"id": 2, "has_handwriting": false, "confidence": 1.0},'
        ' {"id": 3, "has_handwriting": false, "confidence": 1.0}]'
    )
    client = FakeClient(
        contents=[
            grid,
            '[{"id": 1, "has_handwriting": false, "confidence": 0.7}]',
            '[{"id": 1, "has_handwriting": false, "confidence": 0.71}]',
            '[{"id": 1, "has_handwriting": false, "confidence": 0.4}]',
        ]
    )
    verify_handwriting_with_vl(_image(tmp_path), [blk_a, blk_b, blk_c], client=client)
    assert blk_a["result"] == "错" and blk_a["ink_evidence"]["action"] == "flagged"
    assert blk_b["result"] == "未作答" and blk_b["ink_evidence"]["action"] == "downgraded"
    assert blk_c["result"] == "错" and blk_c["ink_evidence"]["action"] == "flagged"


def test_grid_false_confirm_true_keeps_result(tmp_path, monkeypatch):
    """两段式核心：网格误杀真笔迹时，单面板确认见到笔迹 → 不降级（e2e 2_1/2_3/1_1 回归）。"""
    monkeypatch.delenv("INK_EVIDENCE_VL", raising=False)
    blk = _blk(result="对", bbox=[10, 10, 120, 120])
    client = FakeClient(
        contents=[
            '[{"id": 1, "has_handwriting": false, "confidence": 1.0}]',
            '[{"id": 1, "has_handwriting": true, "confidence": 0.95}]',
        ]
    )
    changes = verify_handwriting_with_vl(_image(tmp_path), [blk], client=client)
    assert blk["result"] == "对"
    assert "ink_evidence" not in blk
    assert changes == []


def test_confirm_failure_fails_open(tmp_path, monkeypatch):
    """确认调用异常 → 不动块（fail-open），也不标 suspicious。"""
    monkeypatch.delenv("INK_EVIDENCE_VL", raising=False)
    blk = _blk(result="对")
    client = FakeClient(
        contents=['[{"id": 1, "has_handwriting": false, "confidence": 1.0}]']
    )
    calls = {"n": 0}
    orig = client._create

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("确认挂了")
        return orig(**kwargs)

    client.chat.completions.create = flaky
    changes = verify_handwriting_with_vl(_image(tmp_path), [blk], client=client)
    assert blk["result"] == "对"
    assert "ink_evidence" not in blk
    assert changes == []


def test_has_handwriting_untouched(tmp_path, monkeypatch):
    monkeypatch.delenv("INK_EVIDENCE_VL", raising=False)
    blk = _blk()
    client = FakeClient(content='[{"id": 1, "has_handwriting": true, "confidence": 0.9}]')
    changes = verify_handwriting_with_vl(_image(tmp_path), [blk], client=client)
    assert blk["result"] == "错"
    assert "ink_evidence" not in blk
    assert changes == []


def test_vl_error_or_garbage_returns_no_changes(tmp_path, monkeypatch):
    monkeypatch.delenv("INK_EVIDENCE_VL", raising=False)
    path = _image(tmp_path)
    blk = _blk()
    boom = FakeClient(error=RuntimeError("VL挂了"))
    assert verify_handwriting_with_vl(path, [blk], client=boom) == []
    assert blk["result"] == "错"

    garbage = FakeClient(content="这不是JSON")
    assert verify_handwriting_with_vl(path, [blk], client=garbage) == []
    assert blk["result"] == "错"

    empty = FakeClient(content="[]")
    assert verify_handwriting_with_vl(path, [blk], client=empty) == []
    assert blk["result"] == "错"


def test_env_disabled_skips_vl_call(tmp_path, monkeypatch):
    monkeypatch.setenv("INK_EVIDENCE_VL", "0")
    blk = _blk()
    client = FakeClient(content='[{"id": 1, "has_handwriting": false, "confidence": 0.99}]')
    changes = verify_handwriting_with_vl(_image(tmp_path), [blk], client=client)
    assert changes == []
    assert client.calls == 0
    assert blk["result"] == "错"


def test_per_paper_cap_leaves_extra_untouched(tmp_path, monkeypatch):
    monkeypatch.delenv("INK_EVIDENCE_VL", raising=False)
    monkeypatch.setenv("INK_EVIDENCE_MAX_PER_PAPER", "1")
    blocks = [_blk(index=1), _blk(index=2), _blk(index=3)]
    client = FakeClient(content='[{"id": 1, "has_handwriting": false, "confidence": 0.9}]')
    changes = verify_handwriting_with_vl(_image(tmp_path), blocks, client=client)
    assert blocks[0]["result"] == "未作答"
    assert blocks[1]["result"] == "错" and "ink_evidence" not in blocks[1]
    assert blocks[2]["result"] == "错" and "ink_evidence" not in blocks[2]
    assert len(changes) == 1


def test_over_20_candidates_split_into_batches(tmp_path, monkeypatch):
    monkeypatch.delenv("INK_EVIDENCE_VL", raising=False)
    blocks = [_blk(index=i, bbox=[10 + (i % 5) * 30, 10 + (i // 5) * 30, 30 + (i % 5) * 30, 30 + (i // 5) * 30]) for i in range(1, 23)]
    # 每批面板编号从 1 重启：批1 id=1 → 第1块，批2 id=1 → 第21块
    client = FakeClient(content='[{"id": 1, "has_handwriting": false, "confidence": 0.9}]')
    changes = verify_handwriting_with_vl(_image(tmp_path), blocks, client=client)
    assert client.calls == 4  # 22 候选 → 网格 2 批 + 2 个 false 面板各确认 1 次
    assert blocks[0]["result"] == "未作答"
    assert blocks[20]["result"] == "未作答"
    assert blocks[19]["result"] == "错" and "ink_evidence" not in blocks[19]
    assert blocks[21]["result"] == "错" and "ink_evidence" not in blocks[21]
    assert len(changes) == 2


def test_compose_labeled_crops_grid_and_label_boxes():
    image = Image.new("RGB", (200, 200), "white")
    grid = _compose_labeled_crops(image, [[10, 10, 60, 60], [70, 70, 120, 120], [130, 10, 180, 60]])
    assert grid is not None
    assert grid.size == (3 * 400, 400)  # 3 面板一排（≤5 列）
    # 每个面板左上角烧录了编号（描边黑字）：标签区必有暗像素
    for cell_x in (0, 400, 800):
        region = grid.crop((cell_x, 0, cell_x + 52, 30))
        assert min(region.convert("L").getdata()) < 80
    # 21 个面板 → 5×4 + 1 排
    grid = _compose_labeled_crops(image, [[0, 0, 50, 50]] * 21)
    assert grid.size == (5 * 400, 5 * 400)
    assert _compose_labeled_crops(image, []) is None


def test_json_array_parser_tolerates_fences():
    assert _json_array_from_text('```json\n[{"id": 1}]\n```') == [{"id": 1}]
    assert _json_array_from_text("前置 [\"a\"] 后置") == ["a"]
    assert _json_array_from_text("没有数组") == []
    assert _json_array_from_text("{not array}") == []


def test_as_bool_parses_string_false():
    assert _as_bool(False) is False
    assert _as_bool("false") is False
    assert _as_bool("true") is True
    assert _as_bool(None) is None
    assert _as_bool("瞎写") is None
