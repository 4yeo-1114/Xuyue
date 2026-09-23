"""
student_portfolio / student_growth_record / report_snapshot / assessment_comment 数据访问层。

设计（种春风融合：学情 → 成长记录画像）：
  - GET /portfolio 实时重算并幂等写回 student_portfolios 缓存（不做事件钩子）。
  - 智育事件原始行来自源表（wrong_questions / exam_scores JOIN exams /
    targeted_improvement_reports），列如 class_avg/class_rank/status/corrected_at/
    knowledge_point_id/school_id 由幂等 ALTER 脚本补齐（99 §4.1 ALTER 段），故此处用 raw SQL。
"""
from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.assessment_comment import AssessmentComment
from app.models.assessment_definition import AssessmentDefinition
from app.models.assessment_result import AssessmentResult
from app.models.badge_award import BadgeAward
from app.models.badge_definition import BadgeDefinition
from app.models.class_model import Class
from app.models.credit_account import CreditAccount
from app.models.credit_transaction import CreditTransaction
from app.models.evaluation_archive import EvaluationArchive
from app.models.indicator_definition import IndicatorDefinition
from app.models.report_snapshot import ReportSnapshot
from app.models.student_growth_record import StudentGrowthRecord
from app.models.student_memory import StudentMemory
from app.models.student_portfolio import StudentPortfolio
from app.services.portfolio.assessment_engine import (
    assemble_dual_track,
    class_rank_metrics,
    composite_metrics,
    compute_intellectual_events,
    flatten_baseline,
    group_raw_by_student,
    merge_student_metrics,
    school_z_metrics,
)
from app.services.portfolio.comment import FALLBACK_COMMENT
from app.services.portfolio.event_catalog import DIMENSIONS, get_catalog, get_tau_days

# P2 未接入的源表清单（德体美劳灰态占位明示缺哪些 P2 源表，不造假数据）
_MISSING_SOURCE_TABLES: dict[str, list[str]] = {
    "moral": ["attendance", "behavior_record"],
    "physical": ["physical_test"],
    "aesthetic": ["art_activity"],
    "labor": ["labor_record"],
    "intellectual": [],  # 智育源表（wrong_question/exam_score/targeted_improvement_report）已接入
    "ai_literacy": [],   # E02 AI 素养：成长记录直接驱动（ai_course/ai_project），无额外源表
}


def _json_safe(obj):
    """把 dict/list 中的 datetime/date/Decimal 转成 JSON 可序列化形态（落 JSON 列前调用）。"""
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _iso(v):
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _parse_term_range(term):
    """解析 '2025-2026-1' → (date_from, date_to)（UTC）。

    与 router._parse_term 同口径，但异常/缺省不抛错：term 为空或非法 → (None, None)，
    由 compute_dossier 视作全量区间降级。
    """
    if not term:
        return None, None
    m = re.match(r"^(\d{4})-(\d{4})-([12])$", str(term))
    if not m:
        return None, None
    y1, y2, half = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y2 != y1 + 1:
        return None, None
    tz = datetime.timezone.utc
    if half == 1:  # 上学期：当年 9/1 ~ 次年 1/31
        return (datetime.datetime(y1, 9, 1, tzinfo=tz),
                datetime.datetime(y2, 1, 31, 23, 59, 59, tzinfo=tz))
    # 下学期：当年 2/1 ~ 当年 7/31
    return (datetime.datetime(y2, 2, 1, tzinfo=tz),
            datetime.datetime(y2, 7, 31, 23, 59, 59, tzinfo=tz))


# 全量区间兜底（term=None 时用；max 用 9999 避免 DATETIME 越界）
_EPOCH_MIN = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
_EPOCH_MAX = datetime.datetime(9999, 12, 31, 23, 59, 59, tzinfo=datetime.timezone.utc)


def _growth_record_dict(r, indicator_names=None) -> dict:
    """成长记录序列化（与 router 口径一致，避免循环依赖）。"""
    indicator_id = getattr(r, "indicator_id", None)
    indicator_name = (indicator_names or {}).get(indicator_id) if indicator_id else None
    return {
        "id": r.id,
        "student_id": r.student_id,
        "class_id": r.class_id,
        "dimension": r.dimension,
        "source_type": r.source_type,
        "source_id": r.source_id,
        "indicator_id": indicator_id,
        "indicator_name": indicator_name,
        "growth_point": r.growth_points,
        "evidence": r.evidence,
        "note": r.note,
        "created_by": r.created_by,
        "occurred_at": _iso(r.occurred_at),
        "created_at": _iso(r.created_at),
    }


class PortfolioRepository:
    """五育成长画像域数据访问。"""

    DIMENSIONS = DIMENSIONS

    def __init__(self, db: Session):
        self.db = db

    # ── 学生基础（raw SQL：school_id 由 ALTER 补齐，ORM 未声明）────────

    def get_student(self, student_id: str) -> Optional[dict]:
        row = self.db.execute(
            text("SELECT * FROM students WHERE id = :sid"), {"sid": student_id}
        ).mappings().first()
        return dict(row) if row else None

    def list_students_by_class(self, class_id: str) -> list[dict]:
        rows = self.db.execute(
            text("SELECT * FROM students WHERE class_id = :cid"), {"cid": class_id}
        ).mappings().all()
        return [dict(r) for r in rows]

    def list_students_by_school(self, school_id: str) -> list[dict]:
        rows = self.db.execute(
            text("SELECT * FROM students WHERE school_id = :sid"), {"sid": school_id}
        ).mappings().all()
        return [dict(r) for r in rows]

    # ── student_portfolios ─────────────────────────

    def find_portfolio(self, student_id: str) -> Optional[StudentPortfolio]:
        return (self.db.query(StudentPortfolio)
                .filter(StudentPortfolio.student_id == student_id).first())

    def create_portfolio(self, student_id: str, class_id: str, school_id: str,
                         base_points: int = 100) -> Optional[StudentPortfolio]:
        p = StudentPortfolio(
            student_id=student_id,
            class_id=class_id,
            school_id=school_id or None,
            base_points=base_points,
            dimensions={"moral": 0, "intellectual": 0, "physical": 0,
                        "aesthetic": 0, "labor": 0, "ai_literacy": 0, "total": 0},
            total_growth_point=Decimal("0.00"),
        )
        self.db.add(p)
        self.db.commit()
        self.db.refresh(p)
        return p

    def update_dimensions(self, portfolio: StudentPortfolio, dimensions: dict,
                          total_growth_point: float,
                          detail: Optional[dict] = None,
                          auto_detail: Optional[dict] = None) -> None:
        dims = dict(dimensions)
        dims["total"] = round(float(total_growth_point or 0), 2)
        portfolio.dimensions = dims
        portfolio.total_growth_point = Decimal(str(round(float(total_growth_point or 0), 2)))
        portfolio.detail = _json_safe(detail or {})
        portfolio.auto_detail = _json_safe(auto_detail or {})
        portfolio.last_calculated_at = datetime.datetime.now(datetime.timezone.utc)
        self.db.commit()

    # ── student_growth_records ─────────────────────

    def create_growth_record(self, student_id: str, class_id: str, school_id: str,
                             dimension: str, source_type: str, growth_point: int,
                             created_by: str, source_id: str = None,
                             evidence: dict = None, note: str = None,
                             indicator_id: Optional[str] = None) -> Optional[StudentGrowthRecord]:
        """录入成长流水。幂等：同一 (student_id, source_type, source_id) 已存在则跳过。

        indicator_id：二级指标字典ID（纯归类标签），可空。
        """
        if source_id:
            existing = (self.db.query(StudentGrowthRecord)
                        .filter(StudentGrowthRecord.student_id == student_id,
                                StudentGrowthRecord.source_type == source_type,
                                StudentGrowthRecord.source_id == source_id)
                        .first())
            if existing:
                return existing
        rec = StudentGrowthRecord(
            student_id=student_id,
            class_id=class_id,
            school_id=school_id or None,
            dimension=dimension,
            source_type=source_type,
            source_id=source_id or None,
            indicator_id=indicator_id or None,
            growth_points=int(growth_point),
            evidence=_json_safe(evidence or {}),
            note=note,
            created_by=created_by,
            occurred_at=datetime.datetime.now(datetime.timezone.utc),
        )
        self.db.add(rec)
        self.db.commit()
        self.db.refresh(rec)
        return rec

    # ── 二级指标字典 ─────────────────────────────

    @staticmethod
    def _indicator_dict(ind: IndicatorDefinition) -> dict:
        return {
            "id": ind.id,
            "dimension": ind.dimension,
            "code": ind.code,
            "name": ind.name,
            "description": ind.description,
            "level": ind.level,          # E01：1=维度 / 2=方面 / 3=观测点
            "parent_id": ind.parent_id,  # E01：父节点（方面/维度），NULL=顶层
            "sort_order": ind.sort_order,
            "is_active": bool(ind.is_active),
            "school_id": ind.school_id,
        }

    def get_indicator(self, indicator_id: str) -> Optional[dict]:
        """按 id 查指标（含停用），未找到返回 None。"""
        if not indicator_id:
            return None
        ind = (self.db.query(IndicatorDefinition)
               .filter(IndicatorDefinition.id == indicator_id).first())
        return self._indicator_dict(ind) if ind else None

    def indicator_map(self) -> dict[str, str]:
        """id → name 映射（含停用，保证历史成长记录仍能回显指标名），供 enrich indicator_name。"""
        rows = self.db.query(IndicatorDefinition).all()
        return {ind.id: ind.name for ind in rows}

    def list_indicators(self, dimension: str = None,
                        include_inactive: bool = False) -> list[dict]:
        """指标字典列表（扁平）。按 dimension、level、sort_order 排序；include_inactive=False 时只返回启用项。"""
        q = self.db.query(IndicatorDefinition)
        if dimension:
            q = q.filter(IndicatorDefinition.dimension == dimension)
        if not include_inactive:
            q = q.filter(IndicatorDefinition.is_active == 1)
        rows = (q.order_by(IndicatorDefinition.dimension, IndicatorDefinition.level,
                           IndicatorDefinition.sort_order, IndicatorDefinition.id).all())
        return [self._indicator_dict(ind) for ind in rows]

    def list_indicator_tree(self, dimension: str = None,
                            include_inactive: bool = False) -> list[dict]:
        """层级指标树（E01）：维度(level=1) → 方面(level=2) → 观测点(level=3)。

        dimension 给定时只返回该维度子树；否则返回全部维度树。
        返回嵌套结构 [{...indicator, children: [...]}]，children 递归挂接。
        历史数据兼容：老 19 条系统默认指标 level 默认 2（方面），parent_id NULL（顶层挂根）。
        """
        rows = self.list_indicators(dimension=dimension, include_inactive=include_inactive)
        by_id = {n["id"]: n for n in rows}
        tree: list[dict] = []
        for n in rows:
            n["children"] = []
            pid = n["parent_id"]
            parent = by_id.get(pid) if pid else None
            if parent is not None:
                parent["children"].append(n)
            else:
                tree.append(n)
        return tree

    def list_growth_records(self, student_id: str, dimension: str = None,
                            date_from=None, date_to=None,
                            page: int = 1, page_size: int = 20) -> dict:
        q = self.db.query(StudentGrowthRecord).filter(StudentGrowthRecord.student_id == student_id)
        if dimension:
            q = q.filter(StudentGrowthRecord.dimension == dimension)
        if date_from is not None:
            q = q.filter(StudentGrowthRecord.occurred_at >= date_from)
        if date_to is not None:
            q = q.filter(StudentGrowthRecord.occurred_at <= date_to)
        total = q.count()
        rows = (q.order_by(StudentGrowthRecord.created_at.desc())
                .offset((page - 1) * page_size).limit(page_size).all())
        return {"rows": rows, "total": total, "page": page, "pageSize": page_size}

    def sum_growth_by_dimension(self, student_id: str) -> dict:
        """全量按维度聚合成长点 → {dim: {"points", "count"}}。"""
        rows = self.db.execute(text(
            "SELECT dimension, SUM(growth_points) AS total, COUNT(*) AS cnt "
            "FROM student_growth_records WHERE student_id = :sid GROUP BY dimension"
        ), {"sid": student_id}).mappings().all()
        return self._dim_map(rows)

    def sum_growth_by_dimension_in_range(self, student_id: str, date_from, date_to) -> dict:
        rows = self.db.execute(text(
            "SELECT dimension, SUM(growth_points) AS total, COUNT(*) AS cnt "
            "FROM student_growth_records "
            "WHERE student_id = :sid AND occurred_at >= :from AND occurred_at <= :to "
            "GROUP BY dimension"
        ), {"sid": student_id, "from": date_from, "to": date_to}).mappings().all()
        return self._dim_map(rows)

    def source_stats_in_range(self, student_id: str, date_from, date_to) -> dict:
        rows = self.db.execute(text(
            "SELECT source_type, SUM(growth_points) AS total, COUNT(*) AS cnt "
            "FROM student_growth_records "
            "WHERE student_id = :sid AND occurred_at >= :from AND occurred_at <= :to "
            "GROUP BY source_type"
        ), {"sid": student_id, "from": date_from, "to": date_to}).mappings().all()
        out: dict = {}
        for r in rows:
            src = r["source_type"]
            out[src] = {"points": int(r["total"] or 0), "count": int(r["cnt"] or 0)}
        return out

    def trend_by_month(self, student_id: str) -> list[dict]:
        """按月分组成长点（实时画像 trend=true 用，口径与 merged_trend_by_month 一致）。"""
        rows = (self.db.query(StudentGrowthRecord.created_at, StudentGrowthRecord.growth_points)
                .filter(StudentGrowthRecord.student_id == student_id).all())
        buckets: dict = {}
        for created_at, growth_points in rows:
            if created_at is None:
                continue
            month = created_at.strftime("%Y-%m")
            b = buckets.setdefault(month, {"month": month, "events": 0, "points": 0})
            b["events"] += 1
            b["points"] += int(growth_points or 0)
        return [buckets[k] for k in sorted(buckets.keys())]

    @staticmethod
    def _dim_map(rows) -> dict:
        out: dict = {}
        for r in rows or []:
            dim = r.get("dimension")
            if dim:
                out[dim] = {"points": int(r.get("total") or 0), "count": int(r.get("cnt") or 0)}
        return out

    @staticmethod
    def _count_map(rows) -> dict:
        out: dict = {}
        for r in rows or []:
            sid = r.get("student_id")
            if sid:
                out[str(sid)] = int(r.get("cnt") or 0)
        return out

    # ── 智育自动事件原始行（raw SQL：ALTER 补齐列）────

    def raw_intellectual_events(self, student_id: str,
                                date_from=None, date_to=None) -> dict:
        """单生智育自动事件原始行 → {corrected, wrong_total, reports, exam_scores}。"""
        params: dict = {"sid": student_id}
        cw = ["student_id = :sid", "status = 'corrected'"]
        ww = ["student_id = :sid"]
        rw = ["student_id = :sid"]
        ew = ["es.student_id = :sid"]
        if date_from is not None:
            cw.append("corrected_at >= :from")
            ww.append("created_at >= :from")
            rw.append("generated_at >= :from")
            ew.append("e.exam_date >= :from")
            params["from"] = date_from
        if date_to is not None:
            cw.append("corrected_at <= :to")
            ww.append("created_at <= :to")
            rw.append("generated_at <= :to")
            ew.append("e.exam_date <= :to")
            params["to"] = date_to

        corrected = self.db.execute(text(
            "SELECT id, knowledge_point_id AS knowledge_point, corrected_at "
            f"FROM wrong_questions WHERE {' AND '.join(cw)}"), params).mappings().all()
        wrong_total = self.db.execute(text(
            f"SELECT COUNT(*) AS cnt FROM wrong_questions WHERE {' AND '.join(ww)}"),
            params).scalar() or 0
        reports = self.db.execute(text(
            "SELECT id, generated_at AS created_at "
            f"FROM targeted_improvement_reports WHERE {' AND '.join(rw)}"), params).mappings().all()
        exam_scores = self.db.execute(text(
            "SELECT es.id, e.subject, es.score, es.class_avg, es.class_rank, e.exam_date "
            "FROM exam_scores es JOIN exams e ON es.exam_id = e.id "
            f"WHERE {' AND '.join(ew)} ORDER BY e.exam_date"), params).mappings().all()
        return {
            "corrected": [dict(r) for r in corrected],
            "wrong_total": int(wrong_total or 0),
            "reports": [dict(r) for r in reports],
            "exam_scores": [dict(r) for r in exam_scores],
        }

    def raw_class_events(self, class_id: str,
                         term_from=None, term_to=None) -> dict:
        """班级级一次拉取全部智育事件原始行（避免 N+1）。"""
        params: dict = {"cid": class_id}
        cw = ["class_id = :cid", "status = 'corrected'"]
        ww = ["class_id = :cid"]
        rw = ["class_id = :cid"]
        ew = ["e.class_id = :cid"]
        if term_from is not None:
            cw.append("corrected_at >= :from")
            ww.append("created_at >= :from")
            rw.append("generated_at >= :from")
            ew.append("e.exam_date >= :from")
            params["from"] = term_from
        if term_to is not None:
            cw.append("corrected_at <= :to")
            ww.append("created_at <= :to")
            rw.append("generated_at <= :to")
            ew.append("e.exam_date <= :to")
            params["to"] = term_to

        corrected = self.db.execute(text(
            "SELECT id, student_id, knowledge_point_id AS knowledge_point, corrected_at "
            f"FROM wrong_questions WHERE {' AND '.join(cw)}"), params).mappings().all()
        wrong_total = self.db.execute(text(
            f"SELECT student_id, COUNT(*) AS cnt FROM wrong_questions WHERE {' AND '.join(ww)} "
            "GROUP BY student_id"), params).mappings().all()
        reports = self.db.execute(text(
            "SELECT id, student_id, generated_at AS created_at "
            f"FROM targeted_improvement_reports WHERE {' AND '.join(rw)}"), params).mappings().all()
        exam_scores = self.db.execute(text(
            "SELECT es.id, es.student_id, e.subject, es.score, es.class_avg, es.class_rank, "
            "e.exam_date FROM exam_scores es JOIN exams e ON es.exam_id = e.id "
            f"WHERE {' AND '.join(ew)}"), params).mappings().all()
        return {
            "corrected": [dict(r) for r in corrected],
            "wrong_total": self._count_map(wrong_total),
            "reports": [dict(r) for r in reports],
            "exam_scores": [dict(r) for r in exam_scores],
        }

    def raw_school_events(self, school_id: str,
                          term_from=None, term_to=None) -> dict:
        """学校级一次拉取全部智育事件原始行（z-score 学校级标准化用）。

        注：exam_scores/wrong_questions 的 school_id 冗余列由 ALTER 补齐但可能未回填，
        此处统一 JOIN students.school_id 保证命中（99 §7 #2 对齐）。
        """
        params: dict = {"sid": school_id}
        cw = ["s.school_id = :sid", "wq.status = 'corrected'"]
        ww = ["s.school_id = :sid"]
        rw = ["s.school_id = :sid"]
        ew = ["s.school_id = :sid"]
        if term_from is not None:
            cw.append("wq.corrected_at >= :from")
            ww.append("wq.created_at >= :from")
            rw.append("tir.generated_at >= :from")
            ew.append("e.exam_date >= :from")
            params["from"] = term_from
        if term_to is not None:
            cw.append("wq.corrected_at <= :to")
            ww.append("wq.created_at <= :to")
            rw.append("tir.generated_at <= :to")
            ew.append("e.exam_date <= :to")
            params["to"] = term_to

        corrected = self.db.execute(text(
            "SELECT wq.id, wq.student_id, wq.knowledge_point_id AS knowledge_point, "
            "wq.corrected_at FROM wrong_questions wq JOIN students s ON wq.student_id = s.id "
            f"WHERE {' AND '.join(cw)}"), params).mappings().all()
        wrong_total = self.db.execute(text(
            "SELECT wq.student_id, COUNT(*) AS cnt FROM wrong_questions wq "
            "JOIN students s ON wq.student_id = s.id "
            f"WHERE {' AND '.join(ww)} GROUP BY wq.student_id"), params).mappings().all()
        reports = self.db.execute(text(
            "SELECT tir.id, tir.student_id, tir.generated_at AS created_at "
            "FROM targeted_improvement_reports tir JOIN students s ON tir.student_id = s.id "
            f"WHERE {' AND '.join(rw)}"), params).mappings().all()
        exam_scores = self.db.execute(text(
            "SELECT es.id, es.student_id, e.subject, es.score, es.class_avg, es.class_rank, "
            "e.exam_date FROM exam_scores es "
            "JOIN exams e ON es.exam_id = e.id JOIN students s ON es.student_id = s.id "
            f"WHERE {' AND '.join(ew)}"), params).mappings().all()
        return {
            "corrected": [dict(r) for r in corrected],
            "wrong_total": self._count_map(wrong_total),
            "reports": [dict(r) for r in reports],
            "exam_scores": [dict(r) for r in exam_scores],
        }

    def class_growth_map(self, class_id: str) -> dict:
        """班级成长流水按 (student_id → {dim: {points, count}}) 聚合。"""
        rows = self.db.execute(text(
            "SELECT student_id, dimension, SUM(growth_points) AS total, COUNT(*) AS cnt "
            "FROM student_growth_records WHERE class_id = :cid "
            "GROUP BY student_id, dimension"), {"cid": class_id}).mappings().all()
        out: dict = {}
        for r in rows:
            sid = str(r["student_id"])
            out.setdefault(sid, {})[r["dimension"]] = {
                "points": int(r["total"] or 0), "count": int(r["cnt"] or 0)}
        return out

    def school_growth_map(self, school_id: str) -> dict:
        rows = self.db.execute(text(
            "SELECT student_id, dimension, SUM(growth_points) AS total, COUNT(*) AS cnt "
            "FROM student_growth_records WHERE school_id = :sid "
            "GROUP BY student_id, dimension"), {"sid": school_id}).mappings().all()
        out: dict = {}
        for r in rows:
            sid = str(r["student_id"])
            out.setdefault(sid, {})[r["dimension"]] = {
                "points": int(r["total"] or 0), "count": int(r["cnt"] or 0)}
        return out

    def _scope_scores(self, scope_type: str, scope_id: str,
                      now: datetime.datetime = None,
                      tau_days: float = None,
                      term_from: datetime.datetime = None,
                      term_to: datetime.datetime = None) -> dict:
        """{class|school} 作用域全体学生成就分 + 活跃轨 + data_status。

        批量聚合：事件原始行 + 成长流水一次拉取，避免对每个学生 N+1。
        """
        if scope_type == "class":
            students = self.list_students_by_class(scope_id)
            growth_map = self.class_growth_map(scope_id)
            raw = self.raw_class_events(scope_id, term_from=term_from, term_to=term_to)
        else:
            students = self.list_students_by_school(scope_id)
            growth_map = self.school_growth_map(scope_id)
            raw = self.raw_school_events(scope_id, term_from=term_from, term_to=term_to)

        grouped = group_raw_by_student(raw)
        scores: dict = {}
        status: dict = {}
        activity: dict = {}
        for s in students:
            sid = str(s["id"])
            g = grouped.get(sid) or {"corrected": [], "reports": [],
                                     "exam_scores": [], "wrong_total": 0}
            auto = compute_intellectual_events(
                g["corrected"], g["reports"], g["exam_scores"], g["wrong_total"],
                now=now, tau_days=tau_days, term_from=term_from, term_to=term_to)
            growth_by_dim = {
                dim: {"points": meta.get("points", 0), "count": meta.get("count", 0)}
                for dim, meta in (growth_map.get(sid) or {}).items()
            }
            dual = assemble_dual_track(growth_by_dim, auto)
            scores[sid] = dict(dual["dimensions"])
            scores[sid]["total"] = dual["total"]
            status[sid] = dual["data_status"]
            activity[sid] = dual["activity_track"]
        return {"scores": scores, "status": status, "activity": activity}

    # ── 组合：实时计算画像 ────────────────────────

    @staticmethod
    def _intel_detail(auto: dict) -> dict:
        raw = auto.get("raw_by_event") or {}
        return {
            "corrected_wrong_questions": (raw.get("wrong_question_corrected") or {}).get("count", 0),
            "rank_improvements": (raw.get("exam_rank_up") or {}).get("count", 0),
            "targeted_reports": (raw.get("targeted_report") or {}).get("count", 0),
            "above_class_avg": (raw.get("above_class_avg") or {}).get("count", 0),
            "weak_point_conquered": (raw.get("weak_point_conquered") or {}).get("count", 0),
            "correction_rate_high": (raw.get("correction_rate_high") or {}).get("count", 0),
        }

    def compute_portfolio(self, student: dict, grade: str = None,
                          with_trend: bool = False,
                          now: datetime.datetime = None,
                          tau_days: float = None) -> dict:
        """实时聚合五育画像（双轨制 + 班级百分位/档位 + 学校 z + 综合分），幂等写回缓存。"""
        tau_days = tau_days if tau_days is not None else get_tau_days()
        student_id = str(student["id"])
        class_id = str(student.get("class_id") or "")
        school_id = str(student.get("school_id") or "")

        portfolio = self.find_portfolio(student_id)
        base_points = 100
        portfolio_id = None
        if portfolio:
            base_points = int(portfolio.base_points or 100)
            portfolio_id = portfolio.id
        else:
            created = self.create_portfolio(student_id, class_id, school_id, base_points)
            if created:
                portfolio_id = created.id

        growth = self.sum_growth_by_dimension(student_id)
        raw = self.raw_intellectual_events(student_id)
        auto = compute_intellectual_events(raw["corrected"], raw["reports"], raw["exam_scores"],
                                           raw["wrong_total"], now=now, tau_days=tau_days)
        dual = assemble_dual_track(growth, auto)

        baseline = None
        if class_id:
            try:
                class_data = self._scope_scores("class", class_id, now=now, tau_days=tau_days)
                school_data = (self._scope_scores("school", school_id, now=now, tau_days=tau_days)
                               if school_id else {"scores": {}, "status": {}, "activity": {}})
                rank_metrics = class_rank_metrics(class_data["scores"], class_data["status"])
                z_metrics = school_z_metrics(school_data["scores"], school_data["status"])
                composite = composite_metrics(z_metrics)
                baseline = merge_student_metrics(student_id, rank_metrics, z_metrics, composite)
            except Exception:  # noqa: BLE001 —— 基准线计算失败不阻断主画像返回
                baseline = None

        if portfolio_id:
            try:
                p = self.find_portfolio(student_id)
                if p:
                    self.update_dimensions(
                        p, dual["dimensions"], dual["total"],
                        detail=self._intel_detail(auto), auto_detail=auto["by_event"])
            except Exception:  # noqa: BLE001 —— 写回缓存失败不阻断返回
                pass

        result: dict = {
            "student_id": student_id,
            "name": student.get("name"),
            "class_id": class_id,
            "grade": grade,
            "base_points": base_points,
            "dimensions": dual["dimensions"],
            "total_growth_point": dual["total"],
            "activity_track": dual["activity_track"],
            "data_status": dual["data_status"],
            "intellectual_auto": auto["by_event"],
            "intellectual_events": auto["events"],
        }
        if baseline:
            flat = flatten_baseline(baseline)
            result["percentile"] = flat["percentile"]
            result["tier"] = flat["tier"]
            result["z_score"] = flat["z_score"]
            result["composite"] = flat["composite"]
            result["rank"] = flat["rank"]
            result["n"] = flat["n"]
        if with_trend:
            # 契约 §6.1：实时画像 trend 也走多源合并趋势（成长流水 + 智育事件源表）
            result["trend"] = self.merged_trend_by_month(student_id)
        return result

    # ── 学期报告 ────────────────────────────────

    def _term_baseline(self, student: dict, term_from, term_to,
                       now: datetime.datetime = None,
                       tau_days: float = None) -> Optional[dict]:
        """学期内班级/学校作用域归一化基准线 → 该生 baseline 段（雷达数据源）。"""
        student_id = str(student["id"])
        class_id = str(student.get("class_id") or "")
        school_id = str(student.get("school_id") or "")
        if not class_id:
            return None
        try:
            class_data = self._scope_scores("class", class_id, now=now, tau_days=tau_days,
                                            term_from=term_from, term_to=term_to)
            school_data = (self._scope_scores("school", school_id, now=now, tau_days=tau_days,
                                              term_from=term_from, term_to=term_to)
                           if school_id else {"scores": {}, "status": {}, "activity": {}})
            rank_metrics = class_rank_metrics(class_data["scores"], class_data["status"])
            z_metrics = school_z_metrics(school_data["scores"], school_data["status"])
            composite = composite_metrics(z_metrics)
            baseline = merge_student_metrics(student_id, rank_metrics, z_metrics, composite)
            flat = flatten_baseline(baseline)
            return {
                "percentile": flat["percentile"],
                "tier": flat["tier"],
                "z_score": flat["z_score"],
                "composite": flat["composite"],
                "rank": flat["rank"],
                "n": flat["n"],
            }
        except Exception:  # noqa: BLE001
            return None

    def merged_trend_by_month(self, student_id: str, date_from=None, date_to=None) -> list[dict]:
        """按月合并趋势：成长流水 + 智育事件源表（错题订正 / 考试 / 靶向报告）。

        date_from/date_to 可空（实时画像全量趋势）；学期报告传学期边界。
        """
        buckets: dict = {}

        def _add(ts, points, events: int = 1) -> None:
            if ts is None:
                return
            month = ts.strftime("%Y-%m") if hasattr(ts, "strftime") else str(ts)[:7]
            b = buckets.setdefault(month, {"month": month, "points": 0, "events": 0})
            b["points"] += points
            b["events"] += events

        def _clause(col: str, alias: str) -> str:
            parts = [f"{col} = :sid"]
            if date_from is not None:
                parts.append(f"{alias} >= :from")
            if date_to is not None:
                parts.append(f"{alias} <= :to")
            return " AND ".join(parts)

        params: dict = {"sid": student_id}
        if date_from is not None:
            params["from"] = date_from
        if date_to is not None:
            params["to"] = date_to

        gr = self.db.execute(text(
            f"SELECT occurred_at, growth_points FROM student_growth_records "
            f"WHERE {_clause('student_id', 'occurred_at')}"), params).mappings().all()
        for r in gr:
            _add(r.get("occurred_at"), int(r.get("growth_points") or 0))

        wq = self.db.execute(text(
            f"SELECT corrected_at FROM wrong_questions "
            f"WHERE status = 'corrected' AND {_clause('student_id', 'corrected_at')}"),
            params).mappings().all()
        for r in wq:
            _add(r.get("corrected_at"), 1)

        esc = self.db.execute(text(
            "SELECT e.exam_date AS exam_date FROM exam_scores es "
            "JOIN exams e ON es.exam_id = e.id "
            f"WHERE {_clause('es.student_id', 'e.exam_date')}"), params).mappings().all()
        for r in esc:
            _add(r.get("exam_date"), 1)

        rpt = self.db.execute(text(
            f"SELECT generated_at FROM targeted_improvement_reports "
            f"WHERE {_clause('student_id', 'generated_at')}"), params).mappings().all()
        for r in rpt:
            _add(r.get("generated_at"), 1)

        return [buckets[k] for k in sorted(buckets.keys())]

    def assessment_profile_for_term(self, student_id: str, date_from, date_to) -> dict:
        """聚合该生该学期锚点标签 → assessment_profile（P2 对接锚点层，当前空结构占位）。

        Wave 1 测评域（B-agent）尚未建表，此处返回灰态空结构（has_data=False），绝不查不存在的表。
        """
        return {
            "has_data": False,
            "result_count": 0,
            "labels": [],
            "by_dimension": {},
            "dimension_percents": {},
            "generated_at": None,
            "domains": [],
        }

    def get_comment_section(self, student_id: str, term: str) -> dict:
        """取评语段（供 GET report / freeze / PDF / comment 端点复用，防口径分裂）。"""
        c = (self.db.query(AssessmentComment)
             .filter(AssessmentComment.student_id == student_id,
                     AssessmentComment.term == term).first())
        if not c:
            return {"status": "absent", "content": None}

        base = {
            "ai_model": c.ai_model,
            "gate_flagged": bool(c.gate_flagged),
        }
        if c.status == "confirmed":
            return {
                **base,
                "status": "confirmed",
                "content": c.confirmed_content or c.ai_content,
                "confirmed_by": c.confirmed_by,
                "confirmed_at": _iso(c.confirmed_at),
                "is_draft": False,
                "comment_id": c.id,
                "ai_content": c.ai_content,
                "confirmed_content": c.confirmed_content,
                "created_by": c.created_by,
                "created_at": _iso(c.created_at),
            }
        if c.status == "ai_failed":
            return {
                **base,
                "status": "ai_failed",
                "content": c.ai_content or FALLBACK_COMMENT,
                "is_draft": False,
                "comment_id": c.id,
                "ai_content": c.ai_content,
                "confirmed_content": c.confirmed_content,
                "created_by": c.created_by,
                "created_at": _iso(c.created_at),
            }
        # ai_generated（待教师确认）
        return {
            **base,
            "status": "pending",
            "content": c.ai_content,
            "is_draft": True,
            "comment_id": c.id,
            "ai_content": c.ai_content,
            "confirmed_content": c.confirmed_content,
            "created_by": c.created_by,
            "created_at": _iso(c.created_at),
        }

    def _credit_summary(self, student_id: str, date_from, date_to) -> dict:
        """学分银行聚合（G2）：账户余额 + 区间内流水统计，供学期报告「学分银行」区块。

        - 账户：credit_accounts 每学生一行，无账户 → balance/total_earned/total_spent 为 None。
        - 区间流水：credit_transactions 按 created_at 对齐学期（无 term 列），
          amount > 0 计挣得、amount < 0 计支出（绝对值）、净变动 = SUM(amount)。
        - 无流水 → term_* 为 0，txn_count 为 0，by_type 为 {}。
        """
        account = (self.db.query(CreditAccount)
                   .filter(CreditAccount.student_id == student_id)
                   .first())
        txns = (self.db.query(CreditTransaction)
                .filter(CreditTransaction.student_id == student_id,
                        CreditTransaction.created_at >= date_from,
                        CreditTransaction.created_at <= date_to)
                .order_by(CreditTransaction.created_at.asc())
                .all())

        term_earned = 0
        term_spent = 0
        term_net = 0
        by_type: dict = {}
        for t in txns:
            amt = int(t.amount or 0)
            term_net += amt
            if amt > 0:
                term_earned += amt
            else:
                term_spent += -amt
            by_type[t.transaction_type] = by_type.get(t.transaction_type, 0) + 1

        return {
            "balance": int(account.balance) if account else None,
            "total_earned": int(account.total_earned) if account else None,
            "total_spent": int(account.total_spent) if account else None,
            "term_earned": term_earned,
            "term_spent": term_spent,
            "term_net": term_net,
            "txn_count": len(txns),
            "by_type": by_type,
        }

    def compute_report_for_student(self, student: dict, term: str,
                                   date_from, date_to,
                                   grade: str = None,
                                   now: datetime.datetime = None,
                                   tau_days: float = None) -> dict:
        """实时聚合学期报告（智育深度 + 五育骨架 + 归一化基准线 + 评语段）。

        GET /report、freeze、comment/generate 共用本方法（防口径分裂）。
        """
        student_id = str(student["id"])
        portfolio = self.find_portfolio(student_id)
        base_points = int(portfolio.base_points or 100) if portfolio else 100

        dim_stats = self.sum_growth_by_dimension_in_range(student_id, date_from, date_to)
        source_stats = self.source_stats_in_range(student_id, date_from, date_to)
        raw = self.raw_intellectual_events(student_id, date_from, date_to)
        auto = compute_intellectual_events(
            raw["corrected"], raw["reports"], raw["exam_scores"], raw["wrong_total"],
            now=now, apply_decay=False, term_from=date_from, term_to=date_to)
        raw_ev = auto["raw_by_event"]

        dimensions: dict = {}
        data_status: dict = {}
        data_sources_missing: dict = {}
        for dim in self.DIMENSIONS:
            stat = dim_stats.get(dim) or {}
            growth_pts = int(stat.get("points") or 0)
            growth_cnt = int(stat.get("count") or 0)
            auto_pts = 0.0
            detail = None
            has_data = growth_cnt > 0
            if dim == "intellectual":
                auto_pts = auto["total"]
                has_data = has_data or auto["activity_count"] > 0
                detail = {
                    "corrected_wrong_questions": raw_ev.get("wrong_question_corrected", {}).get("count", 0),
                    "rank_improvements": raw_ev.get("exam_rank_up", {}).get("count", 0),
                    "targeted_reports": raw_ev.get("targeted_report", {}).get("count", 0),
                    "above_class_avg": raw_ev.get("above_class_avg", {}).get("count", 0),
                    "weak_point_conquered": raw_ev.get("weak_point_conquered", {}).get("count", 0),
                    "correction_rate_high": raw_ev.get("correction_rate_high", {}).get("count", 0),
                }
            dimensions[dim] = {
                "growth_records": growth_cnt,
                "auto_points": round(auto_pts, 2),
                "total": round(growth_pts + auto_pts, 2),
            }
            if detail is not None:
                dimensions[dim]["detail"] = detail
                dimensions[dim]["auto_detail"] = auto["by_event"]
            data_status[dim] = "has_data" if has_data else "insufficient"
            data_sources_missing[dim] = list(_MISSING_SOURCE_TABLES.get(dim, []))

        total_growth_point = sum(d["total"] for d in dimensions.values())
        growth_records_count = sum(d["growth_records"] for d in dimensions.values())

        baseline = self._term_baseline(student, date_from, date_to, now=now, tau_days=tau_days)

        catalog = get_catalog()
        epoch = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
        milestones = [
            {
                "event_type": e["event_type"],
                "name": (catalog.get(e["event_type"]) or {}).get("name") or e["event_type"],
                "points": e.get("points"),
                "occurred_at": e.get("occurred_at"),
                "decay_weight": e.get("decay_weight"),
            }
            for e in auto["events"]
        ]
        milestones.sort(key=lambda x: (x.get("occurred_at") or epoch), reverse=True)

        trend = self.merged_trend_by_month(student_id, date_from, date_to)
        assessment_profile = self.assessment_profile_for_term(student_id, date_from, date_to)
        comment = self.get_comment_section(student_id, term)
        credit = self._credit_summary(student_id, date_from, date_to)

        return {
            "student_id": student_id,
            "name": student.get("name"),
            "class_id": str(student.get("class_id") or ""),
            "grade": grade,
            "term": term,
            "date_from": date_from.date().isoformat(),
            "date_to": date_to.date().isoformat(),
            "base_points": base_points,
            "dimensions": dimensions,
            "source_stats": source_stats,
            "growth_records_count": growth_records_count,
            "total_growth_point": round(total_growth_point, 2),
            "raw_total": round(total_growth_point, 2),
            "data_status": data_status,
            "data_sources_missing": data_sources_missing,
            "baseline": baseline,
            "milestones": milestones,
            "trend": trend,
            "assessment_profile": assessment_profile,
            "credit": credit,
            "comment": comment,
        }

    # ── 综评档案聚合（G3，只读）─────────────────

    def compute_dossier(self, student: dict, term: Optional[str] = None,
                        grade: str = None,
                        now: datetime.datetime = None,
                        tau_days: float = None,
                        growth_limit: int = 50,
                        memory_limit: int = 50,
                        badge_limit: int = 50,
                        txn_limit: int = 20,
                        result_limit: int = 20) -> dict:
        """综评档案聚合：学期报告（compute_report_for_student 全量）+ 6 类明细。

        供前端档案页与档案册 PDF 复用。只读聚合，不写库。
        - term：'2025-2026-1' 格式；None/非法 → 全量区间（各明细取最近 N 条）。
        - 各明细缺失 → 空列表 / None，降级不报错。
        """
        student_id = str(student["id"])
        class_id = str(student.get("class_id") or "")

        date_from, date_to = _parse_term_range(term)
        from_dt = date_from or _EPOCH_MIN
        to_dt = date_to or _EPOCH_MAX

        report = self.compute_report_for_student(
            student, term, from_dt, to_dt, grade=grade, now=now, tau_days=tau_days)

        growth_records = self._dossier_growth_records(
            student_id, from_dt, to_dt, limit=growth_limit)
        memories = self._dossier_memories(
            student_id, from_dt, to_dt, limit=memory_limit)
        badges = self._dossier_badges(
            student_id, from_dt, to_dt, limit=badge_limit)
        credit_transactions = self._dossier_credit_txns(
            student_id, from_dt, to_dt, limit=txn_limit)
        assessment_results = self._dossier_assessment_results(
            student_id, limit=result_limit)
        archive_status = self._dossier_archive_status(student_id, class_id, term)

        return {
            "student_id": student_id,
            "name": student.get("name"),
            "class_id": class_id,
            "class_name": self._class_name(class_id),
            "grade": grade,
            "term": term,
            "report": report,
            "growth_records": growth_records,
            "memories": memories,
            "badges": badges,
            "credit_transactions": credit_transactions,
            "assessment_results": assessment_results,
            "archive_status": archive_status,
        }

    def _class_name(self, class_id: str) -> Optional[str]:
        if not class_id:
            return None
        c = (self.db.query(Class).filter(Class.id == class_id).first())
        return c.name if c else None

    def _dossier_growth_records(self, student_id: str, date_from, date_to,
                                limit: int = 50) -> list:
        """最近 N 条成长记录明细（occurred_at 学期区间内）。"""
        rows = (self.db.query(StudentGrowthRecord)
                .filter(StudentGrowthRecord.student_id == student_id,
                        StudentGrowthRecord.occurred_at >= date_from,
                        StudentGrowthRecord.occurred_at <= date_to)
                .order_by(StudentGrowthRecord.occurred_at.desc())
                .all())
        indicator_names = self.indicator_map()
        return [_growth_record_dict(r, indicator_names) for r in rows[:limit]]

    def _dossier_memories(self, student_id: str, date_from, date_to,
                          limit: int = 50) -> list:
        """最近 N 张成长照片（created_at 学期区间内，image/caption）。"""
        rows = (self.db.query(StudentMemory)
                .filter(StudentMemory.student_id == student_id,
                        StudentMemory.created_at >= date_from,
                        StudentMemory.created_at <= date_to)
                .order_by(StudentMemory.created_at.desc())
                .all())
        return [{
            "id": r.id,
            "image_path": r.image_path,
            "caption": r.caption,
            "source_type": r.source_type,
            "created_at": _iso(r.created_at),
        } for r in rows[:limit]]

    def _dossier_badges(self, student_id: str, date_from, date_to,
                        limit: int = 50) -> list:
        """最近 N 条颁章记录（award_date 学期区间内，含章名/分值）。"""
        d_from = date_from.date() if hasattr(date_from, "date") else date_from
        d_to = date_to.date() if hasattr(date_to, "date") else date_to
        rows = (self.db.query(BadgeAward)
                .filter(BadgeAward.student_id == student_id,
                        BadgeAward.award_date >= d_from,
                        BadgeAward.award_date <= d_to)
                .order_by(BadgeAward.award_date.desc())
                .all())
        def_ids = {a.badge_definition_id for a in rows if a.badge_definition_id}
        badge_names: dict = {}
        badge_categories: dict = {}
        badge_points: dict = {}
        if def_ids:
            for b in (self.db.query(BadgeDefinition)
                      .filter(BadgeDefinition.id.in_(def_ids)).all()):
                badge_names[b.id] = b.name
                badge_categories[b.id] = b.category
                badge_points[b.id] = b.points_awarded
        return [{
            "id": a.id,
            "badge_definition_id": a.badge_definition_id,
            "badge_name": badge_names.get(a.badge_definition_id),
            "badge_category": badge_categories.get(a.badge_definition_id),
            "points_awarded": badge_points.get(a.badge_definition_id),
            "award_date": _iso(a.award_date),
            "reason": a.reason,
            "created_at": _iso(a.created_at),
        } for a in rows[:limit]]

    def _dossier_credit_txns(self, student_id: str, date_from, date_to,
                             limit: int = 20) -> list:
        """最近 N 条学分流水（created_at 学期区间内）。"""
        rows = (self.db.query(CreditTransaction)
                .filter(CreditTransaction.student_id == student_id,
                        CreditTransaction.created_at >= date_from,
                        CreditTransaction.created_at <= date_to)
                .order_by(CreditTransaction.created_at.desc())
                .all())
        return [{
            "id": t.id,
            "amount": t.amount,
            "transaction_type": t.transaction_type,
            "balance_after": t.balance_after,
            "description": t.description,
            "created_at": _iso(t.created_at),
        } for t in rows[:limit]]

    def _dossier_assessment_results(self, student_id: str,
                                    limit: int = 20) -> list:
        """最近 N 条锚点测评结果（含 dimension_percents / labels）。"""
        rows = (self.db.query(AssessmentResult)
                .filter(AssessmentResult.student_id == student_id)
                .order_by(AssessmentResult.created_at.desc())
                .all())
        def_ids = {r.definition_id for r in rows if r.definition_id}
        def_names: dict = {}
        if def_ids:
            for d in (self.db.query(AssessmentDefinition)
                      .filter(AssessmentDefinition.id.in_(def_ids)).all()):
                def_names[d.id] = d.name
        return [{
            "id": r.id,
            "definition_id": r.definition_id,
            "definition_name": def_names.get(r.definition_id),
            "domain": r.domain,
            "purpose": r.purpose,
            "tag_schema": r.tag_schema or {},
            "dimension_percents": (r.tag_schema or {}).get("dimension_percents", {}),
            "labels": (r.tag_schema or {}).get("labels", []),
            "guardian_consent": r.guardian_consent or {},
            "created_at": _iso(r.created_at),
        } for r in rows[:limit]]

    def _dossier_archive_status(self, student_id: str, class_id: str,
                                term: Optional[str]) -> Optional[dict]:
        """该生该学期成档状态（evaluation_archives 班级级状态流）；无记录 → None。"""
        if not term:
            return None
        q = self.db.query(EvaluationArchive).filter(
            EvaluationArchive.student_id == student_id,
            EvaluationArchive.term == term)
        if class_id:
            q = q.filter(EvaluationArchive.class_id == class_id)
        row = q.first()
        if not row:
            return None
        now = datetime.datetime.now(datetime.timezone.utc)
        return {
            "id": row.id,
            "class_id": row.class_id,
            "student_id": row.student_id,
            "term": row.term,
            "status": row.status,
            "selected_at": _iso(row.selected_at),
            "publicity_at": _iso(row.publicity_at),
            "publicity_end_at": _iso(row.publicity_end_at),
            "archived_at": _iso(row.archived_at),
            "operator_id": row.operator_id,
            "created_at": _iso(row.created_at),
            "publicity_expired": bool(
                row.status == "publicity"
                and row.publicity_end_at is not None
                and row.publicity_end_at < now
            ),
        }

    # ── report_snapshots 版本链 ─────────────────

    def create_report_snapshot(self, student_id: str, term: str,
                               class_id: str, school_id: str,
                               payload: dict,
                               generated_by: str) -> Optional[ReportSnapshot]:
        """落报告快照：版本号 = 同 (student_id, term) 现有最大 version + 1（幂等新增版本，不覆盖）。"""
        maxv = (self.db.query(func.max(ReportSnapshot.version))
                .filter(ReportSnapshot.student_id == student_id,
                        ReportSnapshot.term == term).scalar()) or 0
        version = int(maxv) + 1
        parent_id = None
        if int(maxv) > 0:
            prev = (self.db.query(ReportSnapshot.id)
                    .filter(ReportSnapshot.student_id == student_id,
                            ReportSnapshot.term == term,
                            ReportSnapshot.version == int(maxv)).first())
            parent_id = prev.id if prev else None

        snap = ReportSnapshot(
            student_id=student_id,
            term=term,
            version=version,
            parent_id=parent_id,
            class_id=class_id,
            school_id=school_id or None,
            generated_by=generated_by,
            payload=_json_safe(payload),
        )
        self.db.add(snap)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return None
        self.db.refresh(snap)
        return snap

    def find_report_snapshot(self, student_id: str, term: str,
                             version: int = None) -> Optional[ReportSnapshot]:
        q = self.db.query(ReportSnapshot).filter(
            ReportSnapshot.student_id == student_id, ReportSnapshot.term == term)
        if version is not None:
            return q.filter(ReportSnapshot.version == version).first()
        return q.order_by(ReportSnapshot.version.desc()).first()

    def list_report_snapshots(self, student_id: str, term: str = None) -> list[dict]:
        q = self.db.query(ReportSnapshot).filter(ReportSnapshot.student_id == student_id)
        if term:
            q = q.filter(ReportSnapshot.term == term)
        rows = q.order_by(ReportSnapshot.term, ReportSnapshot.version).all()
        return [{
            "id": r.id,
            "student_id": r.student_id,
            "term": r.term,
            "version": r.version,
            "parent_id": r.parent_id,
            "generated_by": r.generated_by,
            "created_at": _iso(r.created_at),
        } for r in rows]

    # ── 班级画像总览 ────────────────────────────

    def compute_class_assessment(self, class_id: str,
                                 now: datetime.datetime = None,
                                 tau_days: float = None) -> dict:
        """班级全体学生动态评估：双轨制 + 班级百分位/档位 + 学校 z + 综合分。"""
        tau_days = tau_days if tau_days is not None else get_tau_days()
        students = self.list_students_by_class(class_id)
        school_id = str(students[0].get("school_id") or "") if students else ""

        class_data = self._scope_scores("class", class_id, now=now, tau_days=tau_days)
        school_data = (self._scope_scores("school", school_id, now=now, tau_days=tau_days)
                       if school_id else {"scores": {}, "status": {}, "activity": {}})

        rank_metrics = class_rank_metrics(class_data["scores"], class_data["status"])
        z_metrics = school_z_metrics(school_data["scores"], school_data["status"])
        composite = composite_metrics(z_metrics)

        students_out: list[dict] = []
        for s in students:
            sid = str(s["id"])
            dims = {d: class_data["scores"][sid][d]
                    for d in self.DIMENSIONS if d in class_data["scores"][sid]}
            baseline = merge_student_metrics(sid, rank_metrics, z_metrics, composite)
            flat = flatten_baseline(baseline)
            students_out.append({
                "student_id": sid,
                "name": s.get("name"),
                "student_number": s.get("student_number"),
                "dimensions": dims,
                "total_growth_point": class_data["scores"][sid]["total"],
                "activity_track": class_data["activity"][sid],
                "data_status": class_data["status"][sid],
                "percentile": flat["percentile"],
                "tier": flat["tier"],
                "z_score": flat["z_score"],
                "composite": flat["composite"],
                "rank": flat["rank"],
                "n": flat["n"],
            })

        n = len(students_out)
        averages: dict = {}
        tier_dist: dict = {"A+": 0, "A": 0, "B": 0, "C": 0, "D": 0}
        if n:
            for dim in self.DIMENSIONS:
                vals = [class_data["scores"][sid][dim]
                        for sid in class_data["scores"]
                        if class_data["status"].get(sid, {}).get(dim) == "has_data"]
                averages[dim] = round(sum(vals) / len(vals), 2) if vals else 0.0
            totals = [class_data["scores"][sid]["total"] for sid in class_data["scores"]]
            averages["total"] = round(sum(totals) / len(totals), 2) if totals else 0.0
            for sid, meta in (rank_metrics.get("total") or {}).items():
                tier = meta.get("tier")
                if tier:
                    tier_dist[tier] = tier_dist.get(tier, 0) + 1

        return {
            "class_id": class_id,
            "school_id": school_id,
            "student_count": n,
            "students": students_out,
            "averages": averages,
            "tier_distribution": tier_dist,
        }
