"""对照 model 定义同步本地演示库缺失列（一次性修复脚本，非项目代码）。

用法：cd back_end && python scripts/sync_schema_diff.py
只 ADD COLUMN，不删不改现有列；dry-run 传 --dry。
"""
import sys
from sqlalchemy import inspect, text
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateColumn

from app.database import Base, engine
import app.models  # noqa: F401  注册全部表

DRY = "--dry" in sys.argv


def compile_col(col) -> str:
    return str(CreateColumn(col).compile(dialect=mysql.dialect()))


insp = inspect(engine)
total_missing = 0
with engine.begin() as conn:
    for name, table in Base.metadata.tables.items():
        if not insp.has_table(name):
            print(f"SKIP {name}: 表不存在")
            continue
        db_cols = {c["name"] for c in insp.get_columns(name)}
        adds = [c for c in table.columns.values() if c.name not in db_cols]
        if not adds:
            continue
        print(f"\n== {name} 缺 {len(adds)} 列 ==")
        for col in adds:
            ddl = compile_col(col)
            total_missing += 1
            if DRY:
                print(f"  [dry] ADD {ddl}")
                continue
            try:
                conn.execute(text(f"ALTER TABLE `{name}` ADD COLUMN {ddl}"))
                print(f"  OK  ADD {ddl}")
            except Exception as e:
                print(f"  FAIL ADD {ddl}: {e}")

print(f"\n{'[dry-run] ' if DRY else ''}合计缺失列: {total_missing}")
