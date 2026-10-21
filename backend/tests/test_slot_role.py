# -*- coding: utf-8 -*-
"""slot_role v3（题干/作答区角色甄别）单测：组合调用 / 保护阀 / 比例护栏 /
单面板视觉 / 双路语义终审 / fail-open。

用 fake client 注入 VL 响应，不发真实请求。每题调用序列：
①组合调用（逐框 role/has_marks + QUESTION.answer_location）
②单面板纯视觉（每个未作答框 1 次）
③终审（无证据题→带上下文；串扰矛盾框→无上下文；其余不调）。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from app.grading.slot_role import (
    _as_bool,
    _as_id,
    _as_location,
    _as_role,
    _clipped_crop_boxes,
    _question_item_id,
    filter_stem_slots,
)


class FakeClient:
    """contents 队列按调用顺序取响应（超出重复最后一个）。"""

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
    Image.new("RGB", (400, 400), "white").save(path)
    return str(path)


def _blk(*, index=3, sub_index=1, result="未作答", bbox=None, baidu_original=6, q_bbox=None):
    box = bbox or [50, 50, 120, 120]
    block = {
        "index": index,
        "sub_index": sub_index,
        "result": result,
        "comment": "",
        "partial_ratio": None,
        "baidu_correct_result": 3,
        "baidu_is_slot": True,
        "bbox": box,
        "baidu_question_bbox": q_bbox or [10, 10, 380, 380],
    }
    if baidu_original is not None:
        block["baidu_original_index"] = baidu_original
    return block


def _combined(slots, location="elsewhere", conf=0.95):
    """slots: [(字母, role, has_marks), ...] → 组合调用 JSON。"""
    items = [
        f'{{"id":"{letter}","role":"{role}","has_marks":{str(marks).lower()},"confidence":{conf}}}'
        for letter, role, marks in slots
    ]
    items.append(
        f'{{"id":"QUESTION","answer_location":"{location}","confidence":{conf}}}'
    )
    return "[" + ",".join(items) + "]"


def _visual(role="stem", conf=0.95):
    return f'[{{"id":1,"role":"{role}","confidence":{conf}}}]'


def _repair(slots, conf=0.95):
    """终审（带上下文=组合格式；无上下文=同格式，QUESTION 可有可无）。"""
    return _combined(slots, location="elsewhere", conf=conf)


def test_parse_helpers():
    assert _as_role("stem") == "stem"
    assert _as_role("题干素材") == "stem"
    assert _as_role("answer") == "answer"
    assert _as_role("空白书写处") == "answer"
    assert _as_role("") is None
    assert _as_location("elsewhere") == "elsewhere"
    assert _as_location("答案写在填空括号里") == "elsewhere"
    assert _as_location("on_items") == "on_items"
    assert _as_location("在图案上圈选") == "on_items"
    assert _as_location("mixed") == "mixed"
    assert _as_location("两者都有") == "mixed"
    assert _as_location(None) is None
    assert _as_bool("true") is True
    assert _as_bool("false") is False
    assert _as_bool("无") is False
    assert _as_bool(True) is True
    assert _as_id("a.") == "A"
    assert _as_id("B") == "B"
    assert _as_id(2) == "2"
    assert _as_id(None) is None
    # QUESTION 固定项必须整词识别（_as_id 会收成 Q，与第 17 角标撞号）
    assert _question_item_id("QUESTION") is True
    assert _question_item_id("question") is True
    assert _question_item_id("Q") is False
    assert _question_item_id("A") is False


def test_card_removed_tier1_with_evidence(tmp_path):
    # Q3 型：印刷卡片（stem）+ 手写填空（graded 错=证据）→ 卡片剔除、填空重编号
    # 一层候选即使题内有证据也走带上下文终审（无直接剔除通道，防 2_2 型被剔）
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="错", bbox=[100, 100, 300, 160]),
    ]
    client = FakeClient(
        contents=[
            _combined([("A", "stem", False), ("B", "answer", True)]),
            _visual("stem", 0.95),  # A 未作答 → 视觉判纯印刷
            _visual("answer", 0.95),  # B 已判错 → d) 通道也过视觉，见作答处 → 留
            _repair([("A", "stem", False)]),  # 带上下文终审确认 stem → 剔
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert [c["action"] for c in changes] == ["removed_stem"]
    assert changes[0]["sub_index"] == 1 and changes[0]["confirmed"] is True
    assert len(blocks) == 1
    assert blocks[0]["result"] == "错" and blocks[0]["sub_index"] == 1
    assert client.calls == 4


def test_ratio_guardrail_singleton_flake_keeps(tmp_path):
    # 零星 stem 误判（如圈一圈里该圈没圈的图）不足半数 → 整题不动
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="对", bbox=[100, 100, 160, 160]),
        _blk(sub_index=3, result="对", bbox=[200, 200, 260, 260]),
    ]
    client = FakeClient(
        contents=[
            _combined(
                [("A", "stem", False), ("B", "answer", True), ("C", "answer", True)],
                location="on_items",
            ),
            _visual("stem", 0.95),  # A 像纯印刷
            _visual("answer", 0.95),  # B/C 是真作答（圈过）
            _visual("answer", 0.95),
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 3
    assert client.calls == 4


def test_veto_no_evidence_on_items_keeps(tmp_path):
    # 全空的圈一圈：无作答证据 + on_items → 保护阀拦下，防幻觉清空
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="未作答", bbox=[100, 100, 160, 160]),
    ]
    client = FakeClient(
        contents=[
            _combined(
                [("A", "answer", False), ("B", "answer", False)], location="on_items"
            )
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 2
    assert client.calls == 1


def test_no_evidence_elsewhere_cards_removed_via_ctx_repair(tmp_path):
    # 全空「分一分」（type=elsewhere）：一层候选需带上下文终审确认 stem 才剔（闸b）
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="未作答", bbox=[100, 100, 160, 160]),
    ]
    client = FakeClient(
        contents=[
            _combined([("A", "stem", False), ("B", "stem", False)]),
            _visual("stem", 0.95),
            _visual("stem", 0.95),
            _repair([("A", "stem", False), ("B", "stem", False)]),
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert [c["action"] for c in changes] == ["removed_stem", "removed_stem"]
    assert len(blocks) == 0
    assert client.calls == 4


def test_no_evidence_ctx_repair_answer_keeps(tmp_path):
    # 终审说作答区（如全空圈一圈 elsewhere 误报）→ fail-open 不动
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="未作答", bbox=[100, 100, 160, 160]),
    ]
    client = FakeClient(
        contents=[
            _combined([("A", "stem", False), ("B", "stem", False)]),
            _visual("stem", 0.95),
            _visual("stem", 0.95),
            _repair([("A", "answer", False), ("B", "answer", False)]),
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 2
    assert client.calls == 4


def test_marks_contradiction_solo_repair_removes(tmp_path):
    # F/G 型串扰：组合说有笔迹但单面板=纯印刷 → 无上下文终审 stem → 剔（闸a）
    # 实测 F/G 在「分一分」= elsewhere；A/B 一层候选走带上下文终审，C 串扰走 solo
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="未作答", bbox=[100, 20, 160, 80]),
        _blk(sub_index=3, result="未作答", bbox=[200, 20, 260, 80]),
        _blk(sub_index=4, result="错", bbox=[20, 200, 300, 260]),
    ]
    client = FakeClient(
        contents=[
            _combined(
                [
                    ("A", "stem", False),
                    ("B", "stem", False),
                    ("C", "answer", True),  # 被串扰
                    ("D", "answer", True),
                ],
                location="elsewhere",
            ),
            _visual("stem", 0.95),
            _visual("stem", 0.95),
            _visual("stem", 0.95),
            _visual("answer", 0.95),  # D 判错的真作答 → 视觉见作答处 → 留
            _repair([("A", "stem", False), ("B", "stem", False)]),  # 上下文终审 A/B
            _repair([("C", "stem", False)]),  # 无上下文终审（内容同格式）
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    removed = {c["sub_index"] for c in changes}
    assert removed == {1, 2, 3}
    assert len(blocks) == 1
    assert blocks[0]["result"] == "错" and blocks[0]["sub_index"] == 1
    assert client.calls == 7


def test_marks_contradiction_solo_says_answer_keeps(tmp_path):
    # 终审说作答区/有笔迹 → 串扰矛盾框 fail-open 留
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="未作答", bbox=[100, 20, 160, 80]),
        _blk(sub_index=3, result="未作答", bbox=[200, 20, 260, 80]),
        _blk(sub_index=4, result="错", bbox=[20, 200, 300, 260]),
    ]
    client = FakeClient(
        contents=[
            _combined(
                [
                    ("A", "stem", False),
                    ("B", "stem", False),
                    ("C", "answer", True),
                    ("D", "answer", True),
                ],
                location="elsewhere",
            ),
            _visual("stem", 0.95),
            _visual("stem", 0.95),
            _visual("stem", 0.95),
            _visual("answer", 0.95),  # D 判错的真作答 → 留
            _repair([("A", "stem", False), ("B", "stem", False)]),  # 上下文终审 A/B
            _repair([("C", "answer", True)]),
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    removed = {c["sub_index"] for c in changes}
    assert removed == {1, 2}
    assert len(blocks) == 2
    assert client.calls == 7


def test_role_answer_no_marks_keeps(tmp_path):
    # 2_2 型（圈一圈里该圈没圈的图）：组合 role=answer 且无笔迹 → 组合语义可信用，直接留
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="未作答", bbox=[100, 20, 160, 80]),
        _blk(sub_index=3, result="未作答", bbox=[200, 20, 260, 80]),
    ]
    client = FakeClient(
        contents=[
            _combined(
                [("A", "stem", False), ("B", "stem", False), ("C", "answer", False)],
                location="elsewhere",
            ),
            _visual("stem", 0.95),
            _visual("stem", 0.95),
            _visual("stem", 0.95),  # C 视觉也是纯印刷，但不走剔除
            _repair([("A", "stem", False), ("B", "stem", False)]),  # 无证据题闸b终审
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    removed = {c["sub_index"] for c in changes}
    assert removed == {1, 2}
    assert len(blocks) == 1
    assert blocks[0]["result"] == "未作答" and blocks[0]["sub_index"] == 1
    assert client.calls == 5


def test_visual_answer_keeps(tmp_path):
    # 单面板见到作答处（空白书写处/笔迹）→ 不剔
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="对", bbox=[100, 100, 160, 160]),
    ]
    client = FakeClient(
        contents=[
            _combined([("A", "stem", False), ("B", "answer", True)]),
            _visual("answer", 0.95),  # A 视觉见作答处 → 留
            _visual("answer", 0.95),  # B 已判 → d) 通道也过视觉 → 留
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 2
    assert client.calls == 3


def test_visual_gray_band_flags_but_keeps(tmp_path):
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="对", bbox=[100, 100, 160, 160]),
    ]
    client = FakeClient(
        contents=[
            _combined([("A", "stem", False), ("B", "answer", True)]),
            _visual("stem", 0.5),  # 灰带 [0.4, 0.7]
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 2
    assert blocks[0]["slot_role"]["suspicious"] is True


def test_visual_failure_fails_open(tmp_path):
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="错", bbox=[100, 100, 300, 160]),
    ]

    def flaky(**kwargs):
        flaky.calls += 1
        if flaky.calls >= 2:
            raise RuntimeError("visual boom")
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=_combined([("A", "stem", False), ("B", "answer", True)])
                    )
                )
            ]
        )

    flaky.calls = 0
    client = FakeClient()
    client.chat.completions.create = flaky
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 2 and blocks[0]["result"] == "未作答"


def test_vl_error_keeps_all(tmp_path):
    blocks = [_blk(sub_index=1), _blk(sub_index=2, result="对")]
    client = FakeClient(error=RuntimeError("vl down"))
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 2


def test_env_off_makes_no_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("SLOT_ROLE_FILTER", "0")
    blocks = [_blk(sub_index=1)]
    client = FakeClient(contents=[_combined([("A", "stem", False)])])
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert client.calls == 0
    assert len(blocks) == 1


def test_non_baidu_blocks_untouched(tmp_path):
    # 无 baidu_original_index（人工切题/aliyun 产物）：不进候选
    blocks = [_blk(sub_index=1, baidu_original=None)]
    client = FakeClient(contents=[_combined([("A", "stem", False)])])
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert client.calls == 0
    assert len(blocks) == 1


def test_question_item_id_parsed_for_veto(tmp_path):
    # QUESTION 整题项必须解析出 answer_location（回归：_as_id 会收成 Q 致 location 恒空）。
    # 无证据 + elsewhere → 过保护阀进终审（若解析失败会 1 次调用就停）。
    blocks = [_blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80])]
    client = FakeClient(
        contents=[
            _combined([("A", "stem", False)], location="elsewhere"),
            _visual("stem", 0.95),
            _repair([("A", "stem", False)]),
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert [c["action"] for c in changes] == ["removed_stem"]
    assert len(blocks) == 0
    assert client.calls == 3


def test_mixed_location_allows_cleanup(tmp_path):
    # mixed 与 elsewhere 同待遇：无证据也过保护阀
    blocks = [_blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80])]
    client = FakeClient(
        contents=[
            _combined([("A", "stem", False)], location="mixed"),
            _visual("stem", 0.95),
            _repair([("A", "stem", False)]),
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert [c["action"] for c in changes] == ["removed_stem"]
    assert client.calls == 3


def test_questions_gated_separately(tmp_path):
    # 题1：全空 elsewhere 两卡片 → 终审后剔除；题2：全空 on_items → 保护阀整题不碰
    blocks = [
        _blk(index=3, sub_index=1, bbox=[20, 20, 80, 80], baidu_original=6),
        _blk(index=3, sub_index=2, bbox=[100, 20, 160, 80], baidu_original=6),
        _blk(index=2, sub_index=1, bbox=[200, 200, 260, 260], baidu_original=5),
    ]
    client = FakeClient(
        contents=[
            _combined([("A", "stem", False), ("B", "stem", False)]),  # 题1 组合
            _visual("stem", 0.95),
            _visual("stem", 0.95),
            _repair([("A", "stem", False), ("B", "stem", False)]),  # 题1 闸b终审
            _combined([("A", "answer", False)], location="on_items"),  # 题2 → 阀拦
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert [c["action"] for c in changes] == ["removed_stem", "removed_stem"]
    assert len(blocks) == 1 and blocks[0]["index"] == 2
    assert client.calls == 5


def test_graded_stem_cards_removed_triple_confirm(tmp_path):
    # d) 通道：百度把印刷卡片幻觉判「对」（实测 7 卡全对）——只剔未作答永远清不掉。
    # 视觉+无上下文终审双「纯印刷无笔迹」→ 剔；真手写填空（判错）过视觉留。
    blocks = [
        _blk(sub_index=i, result="对", bbox=[20 + i * 60, 20, 70 + i * 60, 80])
        for i in range(1, 8)
    ] + [_blk(sub_index=8, result="错", bbox=[100, 200, 500, 260])]
    slots = [(chr(ord("A") + i), "stem", False) for i in range(7)] + [("H", "answer", True)]
    client = FakeClient(
        contents=[
            _combined(slots),
            *[_visual("stem", 0.95) for _ in range(7)],
            _visual("answer", 0.95),
            _repair([(chr(ord("A") + i), "stem", False) for i in range(7)]),
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert {c["sub_index"] for c in changes} == set(range(1, 8))
    assert all(c["was_result"] == "对" and c["action"] == "removed_stem" for c in changes)
    assert len(blocks) == 1
    assert blocks[0]["result"] == "错" and blocks[0]["sub_index"] == 1  # 重编号
    assert client.calls == 1 + 8 + 1


def test_graded_solo_marks_keeps(tmp_path):
    # d) 通道终审见到笔迹（或组合/视觉见作答处）→ fail-open 留，不毁已判块
    blocks = [
        _blk(sub_index=1, result="对", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="错", bbox=[100, 200, 500, 260]),
    ]
    client = FakeClient(
        contents=[
            _combined([("A", "stem", False), ("B", "answer", True)]),
            _visual("stem", 0.95),
            _visual("answer", 0.95),
            _repair([("A", "stem", True)]),  # 终审见到笔迹 → 留
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 2
    assert client.calls == 4


def test_all_removed_cancels(tmp_path):
    # 整题会被清空 → 全部保留（fail-safe：防真作答区被连锅端）
    blocks = [
        _blk(sub_index=1, result="对", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="对", bbox=[100, 20, 160, 80]),
    ]
    client = FakeClient(
        contents=[
            _combined([("A", "stem", False), ("B", "stem", False)]),
            _visual("stem", 0.95),
            _visual("stem", 0.95),
            _repair([("A", "stem", False), ("B", "stem", False)]),
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 2


def test_graded_combined_answer_no_marks_keeps(tmp_path):
    # 2_2 型已判块：组合说 answer+无笔迹 → 信组合直接留，连视觉都不用过
    blocks = [
        _blk(sub_index=1, result="对", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="错", bbox=[100, 200, 500, 260]),
    ]
    client = FakeClient(
        contents=[
            _combined([("A", "answer", False), ("B", "answer", True)]),
            _visual("answer", 0.95),  # 只有 B 进 d) 通道视觉
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 2
    assert client.calls == 2


def test_on_items_circled_siblings_keep_unselected(tmp_path):
    # Q2 回归：圈一圈 4 真圈选（视觉见笔迹）+ 2 该圈没圈（组合闪变 stem）——
    # 纯印刷观感的不足半数 → 比例护栏整题不动，真作答区一块都不能少。
    blocks = [
        _blk(sub_index=1, result="对", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="未作答", bbox=[100, 20, 160, 80]),
        _blk(sub_index=3, result="对", bbox=[200, 20, 260, 80]),
        _blk(sub_index=4, result="未作答", bbox=[20, 100, 80, 160]),
        _blk(sub_index=5, result="对", bbox=[100, 100, 160, 160]),
        _blk(sub_index=6, result="对", bbox=[200, 100, 260, 160]),
    ]
    client = FakeClient(
        contents=[
            _combined(
                [
                    ("A", "answer", True),
                    ("B", "stem", False),  # 组合闪变：该圈没圈的选项
                    ("C", "answer", True),
                    ("D", "stem", False),
                    ("E", "answer", True),
                    ("F", "answer", True),
                ],
                location="on_items",
            ),
            _visual("answer", 0.95),  # 真圈选：留边后圈画可见 → 作答处
            _visual("stem", 0.95),
            _visual("answer", 0.95),
            _visual("stem", 0.95),
            _visual("answer", 0.95),
            _visual("answer", 0.95),
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 6
    assert client.calls == 7


def test_on_items_unselected_option_needs_ctx_confirm(tmp_path):
    # Q2 回归：真圈选被认出后该圈没圈的只剩少数候选（过比例护栏）——
    # 一层候选也必须带上下文终审，终审认出「要圈的目标」→ 留。
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="未作答", bbox=[100, 20, 160, 80]),
        _blk(sub_index=3, result="错", bbox=[20, 100, 260, 140]),
    ]
    client = FakeClient(
        contents=[
            _combined(
                [("A", "stem", False), ("B", "stem", False), ("C", "answer", True)],
                location="on_items",
            ),
            _visual("stem", 0.95),
            _visual("stem", 0.95),
            _visual("answer", 0.95),
            _repair([("A", "answer", False), ("B", "answer", False)]),  # 认出是圈选目标
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert changes == []
    assert len(blocks) == 3
    assert client.calls == 5


def test_tier1_ctx_stem_removes_even_with_evidence(tmp_path):
    # 终审（带上下文）确认题干素材才剔——一层候选无直接剔除通道。
    blocks = [
        _blk(sub_index=1, result="未作答", bbox=[20, 20, 80, 80]),
        _blk(sub_index=2, result="未作答", bbox=[100, 20, 160, 80]),
        _blk(sub_index=3, result="错", bbox=[20, 100, 260, 140]),
    ]
    client = FakeClient(
        contents=[
            _combined(
                [("A", "stem", False), ("B", "stem", False), ("C", "answer", True)],
                location="on_items",
            ),
            _visual("stem", 0.95),
            _visual("stem", 0.95),
            _visual("answer", 0.95),
            _repair([("A", "stem", False), ("B", "stem", False)]),  # 确认是分类素材 → 剔
        ]
    )
    changes = filter_stem_slots(_image(tmp_path), blocks, client=client)
    assert {c["sub_index"] for c in changes} == {1, 2}
    assert len(blocks) == 1
    assert blocks[0]["result"] == "错" and blocks[0]["sub_index"] == 1
    assert client.calls == 5


def test_clipped_crop_boxes_pad_and_clip():
    # 无邻块：自适应留边（0.3*68≈20，夹在 [8,40]）
    (box,) = _clipped_crop_boxes([[100, 100, 168, 168]])
    assert box == (80, 80, 188, 188)
    # 左侧邻块压进留边区 → 左边收在邻块右缘（空隙保留、不进邻块），其余三边留边照常
    left, top, right, bottom = _clipped_crop_boxes(
        [[100, 100, 168, 168], [20, 100, 84, 168]]
    )[0]
    assert left == 84 and top == 80 and right == 188 and bottom == 188
    # 邻块与原框重叠（松框贴脸）→ 对应边收到原框边，不缩进原框以内
    left, top, right, bottom = _clipped_crop_boxes(
        [[100, 100, 168, 168], [150, 150, 300, 300]]
    )[0]
    assert left == 80 and top == 80 and right == 168 and bottom == 168
