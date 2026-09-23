"""G3 综评档案聚合接口测试。

覆盖：
- compute_dossier 聚合 dict 含 report + 6 类明细键（成长记录/照片/奖章/学分流水/测评/成档状态）
- 空数据（各源无行）→ 列表 [] / archive_status None，不抛异常
- term 过滤生效：有 term 时成长记录/流水按学期区间过滤；term=None 走全量区间
- 明细序列化（badges 带章名/分值、growth_records 带维度）
- dossier 路由已注册

模式参照 tests/test_report_credit.py：fake session + monkeypatch repository 方法。
"""
from __future__ import annotations

import datetime

from app.services.portfolio import repository as repo_mod
from app.services.portfolio.repository import PortfolioRepository


STUDENT = {"id": "stu-1", "name": "张小明", "class_id": "cls-1"}
_UTC = datetime.timezone.utc


# ── fake session：按 model 喂行，其余模型返回空 ──

class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *a, **k):
        return self

    def order_by(self, *a):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows=None):
        self._rows = rows or {}

    def query(self, model):
        return _FakeQuery(self._rows.get(model, []))


def _base_report() -> dict:
    return {
        "student_id": "stu-1",
        "name": "张小明",
        "class_id": "cls-1",
        "grade": "三年级",
        "term": "2025-2026-1",
        "dimensions": {},
        "data_status": {},
        "baseline": {},
        "assessment_profile": {},
        "credit": {},
        "comment": {},
    }


def _make_repo(monkeypatch, session=None, report=None):
    """构造 repo：monkeypatch compute_report_for_student（隔离报告聚合，聚焦 dossier 明细）。"""
    repo = PortfolioRepository(db=session or _FakeSession())
    monkeypatch.setattr(
        repo, "compute_report_for_student",
        lambda *a, **k: report if report is not None else _base_report(),
    )
    return repo


# ── 聚合 dict 结构 ────────────────────────────────

def test_dossier_contains_report_and_six_details(monkeypatch):
    repo = _make_repo(monkeypatch)
    monkeypatch.setattr(repo, "_dossier_growth_records", lambda *a, **k: [{"id": "gr1"}])
    monkeypatch.setattr(repo, "_dossier_memories", lambda *a, **k: [{"id": "m1"}])
    monkeypatch.setattr(repo, "_dossier_badges", lambda *a, **k: [{"id": "b1"}])
    monkeypatch.setattr(repo, "_dossier_credit_txns", lambda *a, **k: [{"id": "c1"}])
    monkeypatch.setattr(repo, "_dossier_assessment_results", lambda *a, **k: [{"id": "r1"}])
    monkeypatch.setattr(repo, "_dossier_archive_status", lambda *a, **k: {"status": "archived"})
    monkeypatch.setattr(repo, "_class_name", lambda cid: "三年一班")

    d = repo.compute_dossier(STUDENT, term="2025-2026-1", grade="三年级")

    assert d["student_id"] == "stu-1"
    assert d["name"] == "张小明"
    assert d["class_id"] == "cls-1"
    assert d["class_name"] == "三年一班"
    assert d["grade"] == "三年级"
    assert d["term"] == "2025-2026-1"
    assert d["report"]["term"] == "2025-2026-1"
    assert d["growth_records"] == [{"id": "gr1"}]
    assert d["memories"] == [{"id": "m1"}]
    assert d["badges"] == [{"id": "b1"}]
    assert d["credit_transactions"] == [{"id": "c1"}]
    assert d["assessment_results"] == [{"id": "r1"}]
    assert d["archive_status"] == {"status": "archived"}


def test_dossier_empty_data_returns_empty_lists(monkeypatch):
    """各数据源无行 → [] / None，不抛异常（真实 _dossier_* 跑在空 fake session 上）。"""
    repo = _make_repo(monkeypatch)
    d = repo.compute_dossier(STUDENT, term="2025-2026-1", grade="三年级")

    assert d["report"]["term"] == "2025-2026-1"
    assert d["growth_records"] == []
    assert d["memories"] == []
    assert d["badges"] == []
    assert d["credit_transactions"] == []
    assert d["assessment_results"] == []
    assert d["archive_status"] is None
    assert d["class_name"] is None


def test_dossier_empty_data_no_term_does_not_raise(monkeypatch):
    """term=None（全量区间）+ 空数据 → 不抛异常。"""
    repo = _make_repo(monkeypatch)
    d = repo.compute_dossier(STUDENT, term=None)
    assert d["term"] is None
    assert d["growth_records"] == []
    assert d["archive_status"] is None


# ── term 过滤 ─────────────────────────────────────

def test_dossier_term_filters_growth_and_txns(monkeypatch):
    repo = _make_repo(monkeypatch)
    captured: dict = {}

    def capture_growth(sid, date_from, date_to, limit=50):
        captured["growth"] = (date_from, date_to)
        return []

    def capture_txns(sid, date_from, date_to, limit=20):
        captured["txns"] = (date_from, date_to)
        return []

    monkeypatch.setattr(repo, "_dossier_growth_records", capture_growth)
    monkeypatch.setattr(repo, "_dossier_credit_txns", capture_txns)

    repo.compute_dossier(STUDENT, term="2025-2026-1")
    g_from, g_to = captured["growth"]
    assert g_from == datetime.datetime(2025, 9, 1, tzinfo=_UTC)
    assert g_to == datetime.datetime(2026, 1, 31, 23, 59, 59, tzinfo=_UTC)
    assert captured["txns"] == captured["growth"]

    captured.clear()
    repo.compute_dossier(STUDENT, term=None)
    g_from, g_to = captured["growth"]
    assert g_from < datetime.datetime(2025, 1, 1, tzinfo=_UTC)
    assert g_to.year == 9999


def test_parse_term_range_semantics():
    assert repo_mod._parse_term_range("2025-2026-1") == (
        datetime.datetime(2025, 9, 1, tzinfo=_UTC),
        datetime.datetime(2026, 1, 31, 23, 59, 59, tzinfo=_UTC),
    )
    assert repo_mod._parse_term_range("2025-2026-2") == (
        datetime.datetime(2026, 2, 1, tzinfo=_UTC),
        datetime.datetime(2026, 7, 31, 23, 59, 59, tzinfo=_UTC),
    )
    assert repo_mod._parse_term_range(None) == (None, None)
    assert repo_mod._parse_term_range("") == (None, None)
    assert repo_mod._parse_term_range("bad-term") == (None, None)
    assert repo_mod._parse_term_range("2025-2027-1") == (None, None)


# ── 明细序列化（真实 _dossier_* 走 fake session 行）──

def test_dossier_growth_records_serialize(monkeypatch):
    from app.models.student_growth_record import StudentGrowthRecord

    now = datetime.datetime(2026, 1, 10, tzinfo=_UTC)
    rec = StudentGrowthRecord(
        id="gr1", student_id="stu-1", class_id="cls-1",
        dimension="intellectual", source_type="manual",
        growth_points=5, note="完成数学订正",
        occurred_at=now, created_at=now,
    )
    repo = _make_repo(monkeypatch, session=_FakeSession({StudentGrowthRecord: [rec]}))
    d = repo.compute_dossier(STUDENT, term="2025-2026-1")
    assert len(d["growth_records"]) == 1
    row = d["growth_records"][0]
    assert row["dimension"] == "intellectual"
    assert row["growth_point"] == 5
    assert row["occurred_at"] == now.isoformat()


def test_dossier_growth_limit_applied(monkeypatch):
    from app.models.student_growth_record import StudentGrowthRecord

    rows = [StudentGrowthRecord(
        id=f"gr{i}", student_id="stu-1", class_id="cls-1",
        dimension="moral", source_type="manual", growth_points=1,
        occurred_at=None, created_at=None,
    ) for i in range(5)]
    repo = _make_repo(monkeypatch, session=_FakeSession({StudentGrowthRecord: rows}))
    d = repo.compute_dossier(STUDENT, term="2025-2026-1", growth_limit=2)
    assert len(d["growth_records"]) == 2


def test_dossier_memories_serialize(monkeypatch):
    from app.models.student_memory import StudentMemory

    now = datetime.datetime(2026, 1, 10, tzinfo=_UTC)
    mem = StudentMemory(
        id="m1", student_id="stu-1", class_id="cls-1",
        image_path="2026-01/abc.jpg", caption="运动会合影",
        source_type="memory", created_at=now,
    )
    repo = _make_repo(monkeypatch, session=_FakeSession({StudentMemory: [mem]}))
    d = repo.compute_dossier(STUDENT, term="2025-2026-1")
    assert len(d["memories"]) == 1
    assert d["memories"][0]["image_path"] == "2026-01/abc.jpg"
    assert d["memories"][0]["caption"] == "运动会合影"


def test_dossier_badges_serialize_with_definition(monkeypatch):
    from app.models.badge_award import BadgeAward
    from app.models.badge_definition import BadgeDefinition

    now = datetime.datetime(2026, 1, 5, tzinfo=_UTC)
    award = BadgeAward(
        id="b1", student_id="stu-1", class_id="cls-1",
        badge_definition_id="def-1", awarded_by="u-1",
        award_date=datetime.date(2026, 1, 5), reason="表现优秀",
        created_at=now,
    )
    definition = BadgeDefinition(
        id="def-1", name="学习之星", badge_type="school_based",
        category="intellectual", points_awarded=10, is_active=1,
        sort_order=0, created_by="u-1",
    )
    repo = _make_repo(
        monkeypatch,
        session=_FakeSession({BadgeAward: [award], BadgeDefinition: [definition]}),
    )
    d = repo.compute_dossier(STUDENT, term="2025-2026-1")
    assert len(d["badges"]) == 1
    row = d["badges"][0]
    assert row["badge_name"] == "学习之星"
    assert row["badge_category"] == "intellectual"
    assert row["points_awarded"] == 10
    assert row["award_date"] == "2026-01-05"
    assert row["reason"] == "表现优秀"


def test_dossier_credit_txns_serialize(monkeypatch):
    from app.models.credit_transaction import CreditTransaction

    now = datetime.datetime(2026, 1, 5, tzinfo=_UTC)
    txn = CreditTransaction(
        id="t1", student_id="stu-1", class_id="cls-1", amount=10,
        transaction_type="homework", balance_after=25,
        description="完成作业奖励", operator_id="u-1", created_at=now,
    )
    repo = _make_repo(monkeypatch, session=_FakeSession({CreditTransaction: [txn]}))
    d = repo.compute_dossier(STUDENT, term="2025-2026-1")
    assert len(d["credit_transactions"]) == 1
    row = d["credit_transactions"][0]
    assert row["amount"] == 10
    assert row["transaction_type"] == "homework"
    assert row["description"] == "完成作业奖励"
    assert row["created_at"] == now.isoformat()


def test_dossier_assessment_results_serialize(monkeypatch):
    from app.models.assessment_definition import AssessmentDefinition
    from app.models.assessment_result import AssessmentResult

    now = datetime.datetime(2026, 1, 5, tzinfo=_UTC)
    result = AssessmentResult(
        id="r1", student_id="stu-1", definition_id="def-1", session_id=None,
        domain="moral", purpose="anchor",
        tag_schema={"labels": ["乐于助人"], "dimension_percents": {"moral": 80.0}},
        raw_score={"answers": []},
        guardian_consent={"status": "not_required"},
        created_at=now,
    )
    definition = AssessmentDefinition(
        id="def-1", name="品德锚点测评", domain="moral", version=1,
        status="published", consent_required=False,
    )
    repo = _make_repo(
        monkeypatch,
        session=_FakeSession({AssessmentResult: [result], AssessmentDefinition: [definition]}),
    )
    d = repo.compute_dossier(STUDENT, term="2025-2026-1")
    assert len(d["assessment_results"]) == 1
    row = d["assessment_results"][0]
    assert row["definition_name"] == "品德锚点测评"
    assert row["dimension_percents"] == {"moral": 80.0}
    assert row["labels"] == ["乐于助人"]


def test_dossier_archive_status_present(monkeypatch):
    from app.models.evaluation_archive import EvaluationArchive

    now = datetime.datetime.now(_UTC)
    row = EvaluationArchive(
        id="a1", class_id="cls-1", student_id="stu-1", term="2025-2026-1",
        status="publicity",
        publicity_end_at=now + datetime.timedelta(days=7),
        created_at=now,
    )
    repo = _make_repo(monkeypatch, session=_FakeSession({EvaluationArchive: [row]}))
    d = repo.compute_dossier(STUDENT, term="2025-2026-1")
    st = d["archive_status"]
    assert st is not None
    assert st["status"] == "publicity"
    assert st["term"] == "2025-2026-1"
    assert st["publicity_expired"] is False


def test_dossier_archive_status_none_without_term(monkeypatch):
    from app.models.evaluation_archive import EvaluationArchive

    now = datetime.datetime(2026, 1, 10, tzinfo=_UTC)
    row = EvaluationArchive(
        id="a1", class_id="cls-1", student_id="stu-1", term="2025-2026-1",
        status="archived", archived_at=now, created_at=now,
    )
    repo = _make_repo(monkeypatch, session=_FakeSession({EvaluationArchive: [row]}))
    d = repo.compute_dossier(STUDENT, term=None)
    assert d["archive_status"] is None


# ── 路由注册 ──────────────────────────────────────

def test_dossier_route_registered():
    from app.routers.portfolio import router

    paths = [r.path for r in router.routes]
    assert "/portfolio/students/{student_id}/dossier" in paths
