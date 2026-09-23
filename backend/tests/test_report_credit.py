"""G2 学期报告「学分银行」测试。

覆盖：
- compute_report_for_student 的 credit 键聚合：
  有账户+有流水 / 无账户 / 有账户无流水 / by_type 分组
- render_report_pdf 的「学分银行」区块：
  带 credit 数据 / 无 credit 键 / balance=None 灰态占位
"""
from __future__ import annotations

import datetime

from app.models.credit_account import CreditAccount
from app.models.credit_transaction import CreditTransaction
from app.services.portfolio import repository as repo_mod
from app.services.portfolio.pdf import render_report_pdf
from app.services.portfolio.repository import PortfolioRepository

try:
    import fitz  # PyMuPDF

    HAS_FITZ = True
except Exception:  # noqa: BLE001
    HAS_FITZ = False


def _pdf_text(pdf_bytes: bytes) -> str:
    """抽 PDF 文本流（仅断言用，非生产路径）。"""
    if not HAS_FITZ:
        return ""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def _txn(amount: int, transaction_type: str, created_at) -> CreditTransaction:
    return CreditTransaction(
        student_id="stu-1",
        class_id="cls-1",
        amount=amount,
        transaction_type=transaction_type,
        balance_after=0,
        operator_id="u-1",
        created_at=created_at,
    )


# ── fake session：只喂 CreditAccount / CreditTransaction 行，其余模型返回空 ──

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
    def __init__(self, account=None, txns=None):
        self._account = account
        self._txns = txns or []

    def query(self, model):
        if model is CreditAccount:
            return _FakeQuery([self._account] if self._account is not None else [])
        if model is CreditTransaction:
            return _FakeQuery(self._txns)
        return _FakeQuery([])


_FAKE_AUTO = {
    "total": 0.0,
    "activity_count": 0,
    "by_event": {},
    "raw_by_event": {},
    "events": [],
}


def _compute_report(session, monkeypatch) -> dict:
    """调用 compute_report_for_student，隔离非 credit 依赖，让 credit 聚合真实执行。"""
    repo = PortfolioRepository(db=session)
    monkeypatch.setattr(repo, "find_portfolio", lambda sid: None)
    monkeypatch.setattr(repo, "sum_growth_by_dimension_in_range", lambda sid, df, dt: {})
    monkeypatch.setattr(repo, "source_stats_in_range", lambda sid, df, dt: {})
    monkeypatch.setattr(
        repo, "raw_intellectual_events",
        lambda sid, df, dt: {"corrected": [], "reports": [], "exam_scores": [], "wrong_total": 0},
    )
    monkeypatch.setattr(repo_mod, "compute_intellectual_events", lambda *a, **k: _FAKE_AUTO)
    monkeypatch.setattr(repo, "_term_baseline", lambda *a, **k: {})
    monkeypatch.setattr(repo, "merged_trend_by_month", lambda sid, df, dt: [])
    monkeypatch.setattr(repo, "assessment_profile_for_term", lambda sid, df, dt: {"labels": []})
    monkeypatch.setattr(repo, "get_comment_section",
                        lambda sid, term: {"status": "absent", "content": None})

    student = {"id": "stu-1", "name": "张小明", "class_id": "cls-1"}
    date_from = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    date_to = datetime.datetime(2026, 3, 31, tzinfo=datetime.timezone.utc)
    return repo.compute_report_for_student(student, "2025-2026-1", date_from, date_to)


# ── credit 键聚合 ───────────────────────────────────

def test_credit_with_account_and_txns(monkeypatch):
    account = CreditAccount(student_id="stu-1", balance=25, total_earned=80, total_spent=55)
    session = _FakeSession(
        account=account,
        txns=[
            _txn(10, "homework", datetime.datetime(2026, 1, 10, tzinfo=datetime.timezone.utc)),
            _txn(5, "homework", datetime.datetime(2026, 2, 5, tzinfo=datetime.timezone.utc)),
            _txn(-3, "redeem", datetime.datetime(2026, 3, 1, tzinfo=datetime.timezone.utc)),
        ],
    )
    report = _compute_report(session, monkeypatch)
    credit = report["credit"]
    assert credit["balance"] == 25
    assert credit["total_earned"] == 80
    assert credit["total_spent"] == 55
    assert credit["term_earned"] == 15
    assert credit["term_spent"] == 3
    assert credit["term_net"] == 12
    assert credit["txn_count"] == 3
    assert credit["by_type"] == {"homework": 2, "redeem": 1}


def test_credit_no_account_returns_none_balance(monkeypatch):
    session = _FakeSession(account=None, txns=[])
    report = _compute_report(session, monkeypatch)
    credit = report["credit"]
    assert credit["balance"] is None
    assert credit["total_earned"] is None
    assert credit["total_spent"] is None
    assert credit["term_earned"] == 0
    assert credit["term_spent"] == 0
    assert credit["term_net"] == 0
    assert credit["txn_count"] == 0
    assert credit["by_type"] == {}


def test_credit_account_without_txns(monkeypatch):
    account = CreditAccount(student_id="stu-1", balance=25, total_earned=80, total_spent=55)
    session = _FakeSession(account=account, txns=[])
    report = _compute_report(session, monkeypatch)
    credit = report["credit"]
    assert credit["balance"] == 25
    assert credit["total_earned"] == 80
    assert credit["total_spent"] == 55
    assert credit["term_earned"] == 0
    assert credit["term_spent"] == 0
    assert credit["term_net"] == 0
    assert credit["txn_count"] == 0
    assert credit["by_type"] == {}


def test_credit_by_type_groups_multiple_types(monkeypatch):
    account = CreditAccount(student_id="stu-1", balance=0, total_earned=0, total_spent=0)
    session = _FakeSession(
        account=account,
        txns=[
            _txn(2, "homework", datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)),
            _txn(3, "homework", datetime.datetime(2026, 1, 2, tzinfo=datetime.timezone.utc)),
            _txn(1, "exam_rank", datetime.datetime(2026, 1, 3, tzinfo=datetime.timezone.utc)),
            _txn(-4, "redeem", datetime.datetime(2026, 1, 4, tzinfo=datetime.timezone.utc)),
            _txn(-1, "redeem", datetime.datetime(2026, 1, 5, tzinfo=datetime.timezone.utc)),
        ],
    )
    credit = _compute_report(session, monkeypatch)["credit"]
    assert credit["term_earned"] == 6
    assert credit["term_spent"] == 5
    assert credit["term_net"] == 1
    assert credit["txn_count"] == 5
    assert credit["by_type"] == {"homework": 2, "exam_rank": 1, "redeem": 2}


# ── PDF 渲染 ────────────────────────────────────────

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
    }


def test_pdf_with_credit_renders():
    report = _base_report()
    report["credit"] = {
        "balance": 25,
        "total_earned": 80,
        "total_spent": 55,
        "term_earned": 15,
        "term_spent": 3,
        "term_net": 12,
        "txn_count": 3,
        "by_type": {"homework": 2, "redeem": 1},
    }
    pdf = render_report_pdf(report)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    if HAS_FITZ:
        text = _pdf_text(pdf)
        assert "学分银行" in text
        assert "当前余额" in text
        assert "本学期挣得" in text


def test_pdf_without_credit_renders_gray_placeholder():
    pdf = render_report_pdf(_base_report())
    assert pdf.startswith(b"%PDF")
    if HAS_FITZ:
        assert "学分数据暂未生成" in _pdf_text(pdf)


def test_pdf_with_credit_balance_none_renders_gray_placeholder():
    report = _base_report()
    report["credit"] = {
        "balance": None,
        "total_earned": None,
        "total_spent": None,
        "term_earned": 0,
        "term_spent": 0,
        "term_net": 0,
        "txn_count": 0,
        "by_type": {},
    }
    pdf = render_report_pdf(report)
    assert pdf.startswith(b"%PDF")
    if HAS_FITZ:
        assert "学分数据暂未生成" in _pdf_text(pdf)
