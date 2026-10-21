# -*- coding: utf-8 -*-
"""B 项修正/复核记账测试：ai-correct 差分纯函数 / guard 记账行 / 台账读写 / 端点。

sqlite monkeypatch 范本：tests/test_users_dingtalk_userid_upgrade.py:84-96；
端点 FakeDb 范本：tests/test_low_confidence_questions.py:24-68。
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.grading import correction_ledger as cl
from app.grading.correction_ledger import (
    _diff_ai_correct_blocks,
    _score_key_to_index_pair,
    correction_ledger_rows,
    correction_stats,
    diff_note_rows,
    diff_score_map_rows,
    guard_changes_to_ledger_rows,
    record_corrections,
    snapshot_ai_correct_fields,
    void_folder_corrections,
)
from app.grading.response_log_db import _derive_status
from app.models.correction_ledger import CorrectionLedger


# ── B1 纯函数：_diff_ai_correct_blocks ─────────────────────────────────


def _blk(index=1, sub_index=1, result="对", comment="不错", partial_ratio=None, score=None, **extra):
    block = {
        "index": index,
        "sub_index": sub_index,
        "result": result,
        "comment": comment,
        "partial_ratio": partial_ratio,
    }
    if score is not None:
        block["score"] = score
    block.update(extra)
    return block


def test_diff_result_change_yields_ledger_row_and_stamps():
    before = snapshot_ai_correct_fields([_blk(result="错", comment="答错")])
    after = [_blk(result="对", comment="老师改判对")]
    rows, changed = _diff_ai_correct_blocks(before, after)

    assert len(rows) == 1 and len(changed) == 1
    row = rows[0]
    assert row["source"] == "human_ai_correct"
    assert row["was_result"] == "错" and row["new_result"] == "对"
    assert row["was_comment"] == "答错" and row["new_comment"] == "老师改判对"
    blk = changed[0]
    assert blk is after[0]  # 就地盖章（随 blocks 进 history）
    assert blk["ai_original_result"] == "错"
    assert blk["corrected_by"] == "human"
    assert blk["status"] == "correct"


def test_diff_comment_only_change_still_ledger_row():
    before = snapshot_ai_correct_fields([_blk(result="对", comment="旧评语")])
    after = [_blk(result="对", comment="新评语")]
    rows, changed = _diff_ai_correct_blocks(before, after)

    assert len(rows) == 1 and len(changed) == 1
    assert rows[0]["was_result"] == "对" and rows[0]["new_result"] == "对"
    assert changed[0]["status"] == "correct"  # 结果没变也盖人工终态


def test_diff_score_only_change_enters_ledger():
    # 纯调分：进台账（was=new=原判，was_score/new_score 记改动），且不重复记两遍
    before = snapshot_ai_correct_fields([_blk(index=2, result="对", score=2)])
    after = [_blk(index=2, result="对", score=3)]
    rows, changed = _diff_ai_correct_blocks(before, after)

    assert len(rows) == 1 and len(changed) == 1
    row = rows[0]
    assert row["source"] == "human_ai_correct"
    assert row["was_result"] == "对" and row["new_result"] == "对"
    assert row["was_score"] == 2.0 and row["new_score"] == 3.0
    assert changed[0]["corrected_by"] == "human"


def test_diff_partial_ratio_only_change_skips_ledger():
    # 比例细化：只回流 response_logs（changed_blocks），不算改判不进台账
    before = snapshot_ai_correct_fields([_blk(index=1, result="半对", partial_ratio=0.5)])
    after = [_blk(index=1, result="半对", partial_ratio=0.8)]
    rows, changed = _diff_ai_correct_blocks(before, after)

    assert rows == []
    assert len(changed) == 1
    assert changed[0]["corrected_by"] == "human"
    assert changed[0]["status"] == "partial"


def test_diff_content_plus_score_single_ledger_row():
    # 内容修正 + 调分同块：只记一行（别重复记两遍）
    before = snapshot_ai_correct_fields([_blk(index=1, result="错", comment="答错", score=0)])
    after = [_blk(index=1, result="对", comment="改对", score=2)]
    rows, changed = _diff_ai_correct_blocks(before, after)

    assert len(rows) == 1 and len(changed) == 1
    assert rows[0]["was_result"] == "错" and rows[0]["new_result"] == "对"
    assert rows[0]["was_score"] == 0.0 and rows[0]["new_score"] == 2.0


def test_diff_no_change_returns_empty():
    before = snapshot_ai_correct_fields([_blk(result="对", score=2.0)])
    after = [_blk(result="对", score=2)]  # 2 == 2.0（float 归一）不算改分
    rows, changed = _diff_ai_correct_blocks(before, after)
    assert rows == [] and changed == []
    assert "corrected_by" not in after[0]


def test_diff_norm_result_absorbs_partial_ratio_suffix():
    # 「半对（0.6）」→「半对」归一后相等：比例细化不算改判
    before = snapshot_ai_correct_fields([_blk(result="半对（0.6）", partial_ratio=0.6)])
    after = [_blk(result="半对", partial_ratio=0.6)]
    rows, changed = _diff_ai_correct_blocks(before, after)
    assert rows == [] and changed == []


def test_diff_only_changed_blocks_returned():
    before = snapshot_ai_correct_fields(
        [_blk(index=1, result="对"), _blk(index=2, result="错", comment=""), _blk(index=3, result="对")]
    )
    after = [
        _blk(index=1, result="对"),
        _blk(index=2, result="对", comment="改对"),
        _blk(index=3, result="未作答", comment=""),
    ]
    rows, changed = _diff_ai_correct_blocks(before, after)

    assert [b["index"] for b in changed] == [2, 3]
    assert [r["index"] for r in rows] == [2, 3]
    assert rows[1]["new_result"] == "未作答"
    assert changed[1]["status"] == "unanswered"


# ── 纯函数：manual-grade 纯调分 ─────────────────────────────────────────


def test_score_key_to_index_pair():
    assert _score_key_to_index_pair("第12题") == ("12", None)
    assert _score_key_to_index_pair("第12题-作答区3") == ("12", "3")
    assert _score_key_to_index_pair("自定义键") == ("自定义键", None)


def test_diff_score_map_rows_only_changed_and_existing():
    rows = diff_score_map_rows(
        {"第1题": 2, "第2题": 0, "第3题": 1},
        {"第1题": 3, "第2题": 0, "第3题": 1, "第4题": 5},
    )
    assert len(rows) == 1
    assert rows[0]["index"] == "1" and rows[0]["sub_index"] is None
    assert rows[0]["was_score"] == 2.0 and rows[0]["new_score"] == 3.0
    assert rows[0]["source"] == "human_ai_correct"
    # 首次打分（prev 无键）不进台账
    assert all(r["index"] != "4" for r in rows)


def test_diff_score_map_rows_empty_prev_is_first_grade():
    assert diff_score_map_rows({}, {"第1题": 5}) == []
    assert diff_score_map_rows(None, None) == []


# ── 纯函数：批注类字段对照（老师批注 / 试卷总评 / 判错批注） ─────────────


def test_diff_note_rows_question_notes_add_change_delete():
    rows = diff_note_rows(
        {"question_notes": {"1": "旧批注", "2": "待删"}},
        {"question_notes": {"1": "新批注", "3": "新加的"}},
    )
    by_key = {(r["index"], r["source"]): r for r in rows}
    assert set(by_key) == {("1", "human_note"), ("2", "human_note"), ("3", "human_note")}
    assert by_key[("1", "human_note")]["was_comment"] == "旧批注"
    assert by_key[("1", "human_note")]["new_comment"] == "新批注"
    assert by_key[("2", "human_note")]["new_comment"] is None  # 删
    assert by_key[("3", "human_note")]["was_comment"] is None  # 增
    for r in rows:
        assert r["was_result"] is None and r["new_result"] is None
        assert r["was_score"] is None and r["new_score"] is None
        assert r["sub_index"] is None


def test_diff_note_rows_paper_note_one_row_no_index():
    rows = diff_note_rows({"paper_note": "旧总评"}, {"paper_note": "新总评"})
    assert len(rows) == 1
    row = rows[0]
    assert row["index"] is None and row["source"] == "human_paper_note"
    assert row["was_comment"] == "旧总评" and row["new_comment"] == "新总评"


def test_diff_note_rows_wrong_annotations_only_text_counts():
    # edited/generated_at 等元数据翻牌不算变更，只对 text
    before = {"1": {"text": "审题不仔细", "edited": False, "generated_at": "2026-10-20T00:00:00Z"}}
    after_same = {"1": {"text": "审题不仔细", "edited": True, "generated_at": "2026-10-20T14:16:15Z"}}
    assert diff_note_rows({"wrong_annotations": before}, {"wrong_annotations": after_same}) == []

    rows = diff_note_rows(
        {"wrong_annotations": before},
        {"wrong_annotations": {"1": {"text": "审题不仔细，注意单位", "edited": True}}},
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "human_wrong_note"
    assert row["index"] == "1"
    assert row["was_comment"] == "审题不仔细" and row["new_comment"] == "审题不仔细，注意单位"


def test_diff_note_rows_same_empty_and_whitespace_are_no_change():
    assert diff_note_rows({}, {}) == []
    assert diff_note_rows({"question_notes": {}, "paper_note": "", "wrong_annotations": {}},
                          {"question_notes": {}, "paper_note": "  ", "wrong_annotations": {}}) == []
    # 空白/空串与「没有这条」同义：删掉空批注不算变更
    assert diff_note_rows({"question_notes": {"1": "  "}}, {"question_notes": {}}) == []


def test_diff_note_rows_mixed_fields_sorted_deterministically():
    rows = diff_note_rows(
        {"question_notes": {"2": "a"}, "paper_note": "p"},
        {"question_notes": {"1": "b"}, "paper_note": "p2", "wrong_annotations": {"3": {"text": "w"}}},
    )
    assert [(r["source"], r["index"]) for r in rows] == [
        ("human_note", "1"),
        ("human_note", "2"),
        ("human_paper_note", None),
        ("human_wrong_note", "3"),
    ]


# ── guard 记账行：form_guard / vl_ink ─────────────────────────────────


def test_guard_changes_to_ledger_rows_downgraded_and_flagged():
    blocks = [
        _blk(index=1, result="未作答", comment="", subject_family="chinese"),
        _blk(index=2, result="错", comment="", subject_family="chinese"),
        _blk(index=3, result="对", comment="好", subject_family="math"),
    ]
    fg_changes = [
        {"index": 1, "sub_index": 1, "action": "downgraded", "was_result": "错", "ink_ratio": 0.0},
        {"index": 2, "sub_index": 1, "action": "flagged", "reason": "判错无理由", "ink_ratio": 0.02},
    ]
    rows = guard_changes_to_ledger_rows(fg_changes, "form_guard", blocks)

    assert rows[0]["source"] == "form_guard"
    assert rows[0]["was_result"] == "错" and rows[0]["new_result"] == "未作答"
    assert rows[0]["subject_family"] == "chinese"
    # flagged：was=new=原判，reason 进 new_comment
    assert rows[1]["was_result"] == "错" and rows[1]["new_result"] == "错"
    assert rows[1]["new_comment"] == "判错无理由"


def test_guard_changes_to_ledger_rows_vl_ink_reason():
    blocks = [_blk(index=3, result="对", comment="好", subject_family="math")]
    vl_changes = [
        {"index": 3, "sub_index": 1, "action": "flagged", "has_handwriting": False, "confidence": 0.5, "was_result": "对"},
        {"index": 3, "sub_index": 1, "action": "downgraded", "has_handwriting": False, "confidence": 0.85, "was_result": "对"},
    ]
    rows = guard_changes_to_ledger_rows(vl_changes, "vl_ink", blocks)

    assert rows[0]["source"] == "vl_ink"
    assert rows[0]["was_result"] == "对" and rows[0]["new_result"] == "对"
    assert "conf=0.5" in rows[0]["new_comment"]
    assert rows[1]["new_result"] == "未作答" and rows[1]["was_result"] == "对"


def test_derive_status_manual_status_wins_over_code():
    # B1 盖的 status 是人工终态：优先于 baidu_correct_result 码
    blk = {"status": "correct", "baidu_correct_result": 2, "result": "对"}
    assert _derive_status(blk) == "correct"
    assert _derive_status({"baidu_correct_result": 2, "result": "对"}) == "wrong"


# ── 台账读写（sqlite monkeypatch）────────────────────────────────────────


@pytest.fixture()
def db_env(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    CorrectionLedger.__table__.create(bind=engine)
    monkeypatch.setattr(cl, "SessionLocal", sessionmaker(bind=engine))
    try:
        yield engine
    finally:
        engine.dispose()


def _insert(engine, **overrides):
    row = dict(
        user_id="u1",
        folder_safe="f1",
        paper_name="p1.jpg",
        engine="baidu",
        index="1",
        sub_index="1",
        source="human_ai_correct",
        was_result="错",
        new_result="对",
        voided=False,
        created_at=datetime.now(timezone.utc),
    )
    row.update(overrides)
    session = sessionmaker(bind=engine)()
    try:
        session.add(CorrectionLedger(**row))
        session.commit()
    finally:
        session.close()


def test_record_corrections_truncates_comment_to_500(db_env):
    long_comment = "改" * 600
    record_corrections(
        "u1", "f1", "p1.jpg", "baidu",
        [
            {
                "index": 1,
                "sub_index": 1,
                "source": "human_ai_correct",
                "was_result": "错",
                "new_result": "对",
                "was_comment": long_comment,
                "new_comment": long_comment,
                "was_score": "2",
                "new_score": 3,
            }
        ],
    )
    session = sessionmaker(bind=db_env)()
    try:
        row = session.query(CorrectionLedger).one()
        assert row.was_comment == "改" * 500
        assert row.new_comment == "改" * 500
        assert row.was_score == 2.0 and row.new_score == 3.0
        assert row.voided is False
    finally:
        session.close()


def test_record_corrections_skips_empty_rows_or_missing_user(db_env):
    record_corrections("", "f1", "p1.jpg", "baidu", [{"source": "human_ai_correct"}])
    record_corrections("u1", "f1", "p1.jpg", "baidu", [])
    record_corrections("u1", "f1", "p1.jpg", "baidu", ["not-a-dict"])
    session = sessionmaker(bind=db_env)()
    try:
        assert session.query(CorrectionLedger).count() == 0
    finally:
        session.close()


def test_void_folder_corrections_idempotent_and_scoped(db_env):
    _insert(db_env, folder_safe="f1", index="1")
    _insert(db_env, folder_safe="f1", index="2")
    _insert(db_env, folder_safe="f2", index="1")

    void_folder_corrections("f1")
    void_folder_corrections("f1")  # 幂等
    void_folder_corrections("")  # 空名不动

    session = sessionmaker(bind=db_env)()
    try:
        f1 = session.query(CorrectionLedger).filter(CorrectionLedger.folder_safe == "f1").all()
        f2 = session.query(CorrectionLedger).filter(CorrectionLedger.folder_safe == "f2").one()
        assert all(r.voided for r in f1)
        assert f2.voided is False
    finally:
        session.close()


def test_correction_stats_matrix_and_voided_filter(db_env):
    _insert(db_env, index="1", source="human_ai_correct", was_result="错", new_result="对")
    _insert(db_env, index="2", source="human_ai_correct", was_result="错", new_result="对")
    _insert(db_env, index="3", source="vl_ink", was_result="对", new_result="未作答")
    _insert(db_env, index="4", source="form_guard", was_result="错", new_result="未作答", voided=True)

    session = sessionmaker(bind=db_env)()
    try:
        matrix = correction_stats(session, "u1", days=30)
        by_key = {(m["source"], m["was"], m["new"]): m["count"] for m in matrix}
        assert by_key[("human_ai_correct", "错", "对")] == 2
        assert by_key[("vl_ink", "对", "未作答")] == 1
        assert ("form_guard", "错", "未作答") not in by_key  # voided 默认排除

        full = correction_stats(session, "u1", days=30, include_voided=True)
        by_key_full = {(m["source"], m["was"], m["new"]): m["count"] for m in full}
        assert by_key_full[("form_guard", "错", "未作答")] == 1

        assert correction_stats(session, "u2", days=30) == []  # 用户隔离
    finally:
        session.close()


def test_correction_ledger_rows_detail_and_filters(db_env):
    _insert(
        db_env,
        index="1",
        source="human_ai_correct",
        was_result="错",
        new_result="对",
        was_score=0,
        new_score=2,
        paper_name="s1.jpg",
    )
    _insert(db_env, index="2", source="vl_ink", was_result="对", new_result="对", paper_name="s2.jpg")
    _insert(db_env, index="3", source="form_guard", was_result="错", new_result="未作答", voided=True)

    session = sessionmaker(bind=db_env)()
    try:
        rows = correction_ledger_rows(session, "u1", days=30)
        assert len(rows) == 2  # voided 默认排除
        by_index = {r["index"]: r for r in rows}
        assert by_index["1"]["paper_name"] == "s1.jpg"
        assert by_index["1"]["was_score"] == 0.0 and by_index["1"]["new_score"] == 2.0
        assert by_index["1"]["source"] == "human_ai_correct"
        assert by_index["2"]["source"] == "vl_ink"

        full = correction_ledger_rows(session, "u1", days=30, include_voided=True)
        assert len(full) == 3
        assert correction_ledger_rows(session, "u2", days=30) == []  # 用户隔离
        assert len(correction_ledger_rows(session, "u1", days=30, limit=1)) == 1
    finally:
        session.close()


# ── B4 端点 FakeDb ─────────────────────────────────────────────────────


class _Chain:
    def __init__(self, result):
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def group_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._result


class _FakeDb:
    def __init__(self, matrix_rows):
        self._rows = matrix_rows

    def query(self, *entities):
        return _Chain(self._rows)


def test_correction_stats_endpoint_shapes():
    from app.grading.router import api_correction_stats

    rows = [
        ("human_ai_correct", "chinese", "错", "对", 3),
        ("human_ai_correct", "chinese", "对", "错", 1),
        ("vl_ink", "math", "对", "未作答", 2),
    ]
    data = api_correction_stats(
        db=_FakeDb(rows), user_id="u1", days=7, include_voided=False
    ).data

    assert data["window_days"] == 7
    by_key = {(m["source"], m["was"], m["new"]): m for m in data["matrix"]}
    assert by_key[("human_ai_correct", "错", "对")]["count"] == 3
    assert by_key[("human_ai_correct", "错", "对")]["subject_family"] == "chinese"
    assert by_key[("human_ai_correct", "对", "错")]["count"] == 1
    assert by_key[("vl_ink", "对", "未作答")]["count"] == 2
    assert data["totals_by_source"] == {"human_ai_correct": 4, "vl_ink": 2}


def test_correction_stats_endpoint_empty():
    from app.grading.router import api_correction_stats

    data = api_correction_stats(db=_FakeDb([]), user_id="u1", days=30, include_voided=False).data
    assert data == {"matrix": [], "totals_by_source": {}, "window_days": 30}


class _FakeLedgerDb:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *_entities):
        return _FakeLedgerChain(self._rows)


class _FakeLedgerChain:
    def __init__(self, result):
        self._result = result

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._result


def test_correction_ledger_endpoint_shapes():
    from types import SimpleNamespace

    from app.grading.router import api_correction_ledger

    fake_rows = [
        SimpleNamespace(
            id="r1",
            created_at=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
            paper_name="s1.jpg",
            folder_safe="f1",
            engine="baidu",
            index="1",
            sub_index=None,
            source="human_ai_correct",
            was_result="错",
            new_result="对",
            was_comment=None,
            new_comment="改对",
            was_score=0.0,
            new_score=2.0,
            subject_family="math",
            voided=False,
        )
    ]
    data = api_correction_ledger(
        db=_FakeLedgerDb(fake_rows), user_id="u1", days=7, include_voided=False, limit=50
    ).data

    assert data["window_days"] == 7
    assert data["count"] == 1
    assert data["rows"][0]["paper_name"] == "s1.jpg"
    assert data["rows"][0]["was_result"] == "错" and data["rows"][0]["new_result"] == "对"
    assert data["rows"][0]["source"] == "human_ai_correct"
    assert data["rows"][0]["created_at"].startswith("2026-10-01")

    empty = api_correction_ledger(
        db=_FakeLedgerDb([]), user_id="u1", days=30, include_voided=False, limit=200
    ).data
    assert empty == {
        "rows": [],
        "count": 0,
        "window_days": 30,
        "include_voided": False,
    }
