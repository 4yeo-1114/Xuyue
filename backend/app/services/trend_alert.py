"""R5 学生级成绩趋势预警（实时派生，不落库）。

学生端成绩趋势目前只有折线展示（GET /student-analysis/score-history，前端
StudentProfilePanel 调用），无趋势预警。本模块从 exam_scores（JOIN exams 取
subject / exam_date）+ class_rank + student_analysis.target_score 实时推导预警项。

预警类型（学生级，区别于 school_warnings.py 的班级级静态阈值）：
  - score_drop    连续下滑：该科尾部连续 ≥2 次考试 score 递减（3 个点成串）
  - below_target  最近一次低于学业目标（student_analysis.target_score）
  - rank_drop     班级排名连续下滑：class_rank 数字连续增大 ≥2 次（数字大 = 名次差）
  - below_pass    最近一次低于及格线（<60，level=red）

数据不足（该科有效考试 < 2 次）→ 该科不预警（诚实，无数据不推断）。
全部科目无足够数据 → 返回空列表。

家长端视角（E04《未成年人学校保护规定》成绩一对一、不公开不排名）：家长视图入口
（filter_rankings_for_parent 见 grade_scores.py、class_analysis parent 分支）已做
函数级契约预埋，本批不做真入口（工作量大，避免撑爆批次），留待后续接入。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.student_analysis import StudentAnalysis

# 及格线（与 grade_scores 等级契约 needs_work 分界一致）
PASS_LINE = 60.0

# 预警级别排序（red 优先展示）
_LEVEL_RANK = {"red": 0, "warning": 1}


def _num(v: Any) -> Optional[float]:
    """宽松数值化，非法值返回 None。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _score_label(v: Optional[float]) -> str:
    """分数转展示字符串：整数去小数位，None 显示 -。"""
    if v is None:
        return "-"
    if float(v).is_integer():
        return str(int(v))
    return f"{v:g}"


def _tail_run(values: Sequence[Optional[float]], *, worse_than) -> int:
    """返回序列尾部「连续变差」的点数。

    worse_than(prev, cur) 为真表示从 prev 到 cur 是变差：
      - 分数下滑：worse_than = lambda a, b: b < a
      - 名次下滑：worse_than = lambda a, b: b > a（rank 数字大 = 名次差）

    None 视为断点（数据缺失不推断连续趋势）。
    示例 [96, 85, 78] → 3（96→85→78 连续 2 次递减）；
         [96, 85, 78, 80] → 1（尾部 78→80 上升，无下滑）。
    """
    run = 1
    for i in range(len(values) - 1, 0, -1):
        prev, cur = values[i - 1], values[i]
        if prev is None or cur is None:
            break
        if worse_than(prev, cur):
            run += 1
        else:
            break
    return run


def build_trend_alerts(db: Session, student_id: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    """为该生实时推导成绩趋势预警项列表。

    - exam_scores JOIN exams 取 subject/exam_date（含 class_avg/class_rank，R2 已回填）；
    - student_analysis.target_score 按 (class_id, subject) 对齐学业目标；
    - 纯函数，只读不写库；无任何成绩数据 → 空列表。
    """
    alerts: List[Dict[str, Any]] = []

    rows = db.execute(
        text(
            """
            SELECT e.subject, e.title, e.exam_date, es.score, es.class_rank,
                   es.class_id, es.class_avg
            FROM exam_scores es
            JOIN exams e ON es.exam_id = e.id
            WHERE es.student_id = :sid
            ORDER BY e.exam_date, e.id
            """
        ),
        {"sid": student_id},
    ).mappings().all()
    if not rows:
        return alerts

    student = db.execute(
        text("SELECT id, name, class_id FROM students WHERE id = :sid"),
        {"sid": student_id},
    ).mappings().first()
    student_name = (student["name"] or "").strip() if student else ""
    student_class_id = str(student["class_id"] or "") if student else ""

    # 学业目标 map：(class_id, subject) → target_score（student_analysis 按姓名关联）
    target_map: Dict[tuple, int] = {}
    if student_name:
        for row in (
            db.query(StudentAnalysis.class_id, StudentAnalysis.subject, StudentAnalysis.target_score)
            .filter(StudentAnalysis.student_name == student_name)
            .all()
        ):
            if row.target_score is not None:
                target_map[(str(row.class_id or ""), row.subject)] = int(row.target_score)

    # 按 (class_id, subject) 分组，保持 exam_date 时间序
    series: Dict[tuple, list] = {}
    for r in rows:
        cid = str(r["class_id"] or student_class_id)
        key = (cid, r["subject"])
        series.setdefault(key, []).append(r)

    for (cid, subject), items in series.items():
        if limit and limit > 0 and len(items) > limit:
            items = items[-limit:]

        scores = [_num(r["score"]) for r in items]
        ranks = [_num(r["class_rank"]) for r in items]
        valid_scores = [s for s in scores if s is not None]
        valid_ranks = [s for s in ranks if s is not None]
        latest_item = items[-1]
        latest_score = valid_scores[-1] if valid_scores else None
        latest_rank = valid_ranks[-1] if valid_ranks else None
        target = target_map.get((cid, subject))

        def _base(atype: str, level: str) -> Dict[str, Any]:
            return {
                "level": level,
                "type": atype,
                "subject": subject,
                "latest_score": latest_score,
                "exam_title": latest_item["title"],
                "exam_date": str(latest_item["exam_date"]) if latest_item["exam_date"] else None,
            }

        # 1. 连续下滑（尾部 ≥2 次连续递减 → 3 个点成串）
        if len(valid_scores) >= 3:
            run = _tail_run(scores, worse_than=lambda a, b: b < a)
            if run >= 3:
                pts = [_score_label(s) for s in scores[-run:]]
                alerts.append({
                    **_base("score_drop", "warning"),
                    "evidence": f"{subject} {'→'.join(pts)} 连续{run}次下滑",
                })

        # 2. 低于目标
        if target is not None and latest_score is not None and latest_score < target:
            alerts.append({
                **_base("below_target", "warning"),
                "target_score": target,
                "evidence": f"{subject} 最近{_score_label(latest_score)}分，低于目标{target}分",
            })

        # 3. 排名连降（class_rank 数字连续增大 ≥2 次）
        if len(valid_ranks) >= 3:
            run = _tail_run(ranks, worse_than=lambda a, b: b > a)
            if run >= 3:
                pts = [_score_label(s) for s in ranks[-run:]]
                alerts.append({
                    **_base("rank_drop", "warning"),
                    "latest_rank": latest_rank,
                    "evidence": f"{subject} 班级排名 {'→'.join(pts)} 连续{run}次排名下滑",
                })

        # 4. 低于及格线
        if latest_score is not None and latest_score < PASS_LINE:
            alerts.append({
                **_base("below_pass", "red"),
                "evidence": (
                    f"{subject} 最近{_score_label(latest_score)}分，"
                    f"低于及格线{PASS_LINE:g}分"
                ),
            })

    # 稳定排序：red 优先，其次 warning；同级按学科名
    alerts.sort(key=lambda a: (_LEVEL_RANK.get(a["level"], 9), a["subject"] or ""))
    return alerts
