"""画像联动写入（student_growth_records，99 §4.1.2 字段名）。

该表归 A 画像 agent 所有；C 域为写入方，使用裸 SQL 写入，
避免与 A 的 model 在 Base.metadata 中同名冲突。
幂等性由应用层保证：(student_id, source_type, source_id) 不重复录入。
"""
import json
from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.user import gen_uuid


def resolve_indicator_id(db: Session, dimension: str, code: str) -> Optional[str]:
    """按 (dimension, code) 解析二级指标字典 id。

    只取 is_active=1，且优先系统默认（school_id IS NULL）。表不存在（OperationalError
    之类）/查不到/任何异常一律返回 None，绝不阻断既有加分逻辑，兼容未迁移环境。
    """
    if not code:
        return None
    try:
        row = db.execute(
            text(
                "SELECT id FROM indicator_definitions "
                "WHERE dimension = :dim AND code = :code AND is_active = 1 "
                "ORDER BY (school_id IS NULL) DESC, sort_order ASC, id ASC LIMIT 1"
            ),
            {"dim": dimension, "code": code},
        ).mappings().first()
        return row["id"] if row else None
    except Exception:  # noqa: BLE001
        return None


def write_growth_record(
    db: Session,
    student_id: str,
    class_id: str,
    dimension: str,
    source_type: str,
    source_id: Optional[str],
    growth_points: int,
    note: Optional[str] = None,
    created_by: Optional[str] = None,
    occurred_at: Optional[datetime | date] = None,
    evidence: Optional[dict] = None,
    indicator_id: Optional[str] = None,
    indicator_code: Optional[str] = None,
) -> str:
    """写入一条成长记录。返回新记录 id。

    indicator_id：二级指标字典ID（纯归类标签），可空；
    indicator_code：indicator_id 为空时按 (dimension, code) 解析（解析失败不阻断写入）。
    仅当解析出非空 indicator_id 时才把该列拼进 INSERT，兼容未迁移（无 indicator_id 列）环境。
    """
    if occurred_at is None:
        occurred_at = datetime.utcnow()
    if not indicator_id and indicator_code:
        indicator_id = resolve_indicator_id(db, dimension, indicator_code)
    rid = gen_uuid()

    cols = [
        "id", "student_id", "class_id", "dimension", "source_type", "source_id",
        "growth_points", "evidence", "note", "created_by", "occurred_at",
    ]
    params: dict = {
        "id": rid,
        "student_id": student_id,
        "class_id": class_id,
        "dimension": dimension,
        "source_type": source_type,
        "source_id": source_id,
        "growth_points": int(growth_points or 0),
        "evidence": json.dumps(evidence, ensure_ascii=False) if evidence else None,
        "note": note,
        "created_by": created_by,
        "occurred_at": occurred_at,
    }
    if indicator_id:
        cols.append("indicator_id")
        params["indicator_id"] = indicator_id
    sql = (
        f"INSERT INTO student_growth_records "
        f"({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)})"
    )
    db.execute(text(sql), params)
    db.flush()
    return rid


def growth_record_exists(
    db: Session,
    student_id: str,
    source_type: str,
    source_id: Optional[str] = None,
    note: Optional[str] = None,
) -> bool:
    """查询是否已存在对应成长记录（去重用）。"""
    sql = "SELECT COUNT(*) FROM student_growth_records WHERE student_id=:s AND source_type=:t"
    params = {"s": student_id, "t": source_type}
    if source_id is not None:
        sql += " AND source_id=:id"
        params["id"] = source_id
    if note is not None:
        sql += " AND note=:n"
        params["n"] = note
    row = db.execute(text(sql), params).fetchone()
    return bool(row and row[0])


def delete_growth_records(
    db: Session,
    source_type: str,
    source_id: str,
) -> None:
    """删除某业务来源关联的成长记录（颁章撤销/实践删除时回滚画像）。"""
    db.execute(
        text("DELETE FROM student_growth_records WHERE source_type=:t AND source_id=:id"),
        {"t": source_type, "id": source_id},
    )
    db.flush()
