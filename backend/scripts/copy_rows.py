#!/usr/bin/env python3
"""P3-E1: MySQL → PG 影子 schema(school_mig) 全量业务表复制脚本。

用途: 把 MySQL 业务库(默认 grade, 67 张表中的 63 张)结构 + 数据复制到
PG 的 school_mig 影子 schema。目标库是影子 schema, 绝不动 PG public schema
已有表(灵犀家长表 parent_* / 资产表 questions / knowledge_points 等)。

跳过 4 张废弃表(MySQL 0 行, PG 资产为权威): knowledge_points / subject_units
/ wrong_questions / parent_students。

安全约定:
  - 凭据只从 .env / .env.bak_a2_20260830 读取(或已有环境变量), 脚本内不写明文密码。
  - 建 schema/写数据需要 PG 超管权限, 超管连接取 .env.bak_a2_20260830 的
    ASSETS_DB_* (postgres 账号); .env 的 ASSETS_DB_* 是只读 grade_school_ro,
    仅用于最后 GRANT SELECT 只读验证。
  - 本脚本不删 MySQL 任何表、不动 MySQL 数据、不提交任何含密码的文件。

用法: python scripts/copy_rows.py [--tables a,b,c] [--env FILE] [--bak FILE] [--batch N]
可重复运行: 每次重建 school_mig.<表> 后全量复制, 幂等、第二次跑 0 新增不报错。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

try:
    import pymysql
    import psycopg2
    from dotenv import dotenv_values
    from psycopg2.extras import execute_values
except ImportError:  # pragma: no cover
    print("缺少依赖: pip install pymysql psycopg2-binary python-dotenv", file=sys.stderr)
    sys.exit(1)

# 4 张废弃表: MySQL 0 行, PG 资产权威, 跳过迁移
SKIP_TABLES = {"knowledge_points", "subject_units", "wrong_questions", "parent_students"}

SCHEMA = "school_mig"
DEFAULT_BATCH = 500

# ---------------------------------------------------------------------------
# 环境文件定位与凭据加载
# ---------------------------------------------------------------------------


def find_env_file(name: str, explicit: str | None) -> Path | None:
    """定位 env 文件: 显式参数 > cwd > scripts/ 上级 > 沿目录树向上查找。

    兼容两种运行方式:
      - 主仓库根目录运行: cwd 即仓库根, 直接命中。
      - 隔离 worktree 运行: 沿目录树向上找到主仓库根(.env 所在)。
    """
    if explicit:
        p = Path(explicit).resolve()
        return p if p.exists() else None
    cwd = Path.cwd().resolve()
    script_root = Path(__file__).resolve().parent.parent
    candidates: list[Path] = [cwd / name, script_root / name]
    # 从 cwd 向上逐级查找(优先带 scripts/ 兄弟目录的仓库根)
    p = cwd
    while True:
        f = p / name
        if f.exists():
            candidates.append(f)
        if p == p.parent:
            break
        p = p.parent
    # 去重保序, 只保留真实存在的文件, 优先带 scripts/ 的目录(仓库根), 其次 .git 存在的目录
    seen: set[Path] = set()
    ordered: list[Path] = []
    for f in candidates:
        rp = f.resolve()
        if rp in seen or not rp.exists():
            continue
        seen.add(rp)
        ordered.append(rp)

    def _rank(path: Path) -> int:
        s = 0
        if (path.parent / "scripts").is_dir():
            s -= 2
        if (path.parent / ".git").exists():
            s -= 1
        return s

    ordered.sort(key=_rank)
    return ordered[0] if ordered else None


def load_env(path: Path | None, keys: tuple[str, ...]) -> dict[str, str]:
    """从 env 文件读取指定 key; 文件优先, 缺失时回退环境变量。

    文件优先是为防止外部 shell 已 source 过 .env 导致 ASSETS_DB_USER 被
    污染成只读 grade_school_ro(那样将无法建 schema)。
    """
    raw: dict[str, str] = {}
    if path and path.exists():
        raw = {k: v for k, v in dotenv_values(path).items() if v is not None}
    out: dict[str, str] = {}
    for k in keys:
        out[k] = (raw.get(k) or os.environ.get(k) or "").strip()
    return out


# ---------------------------------------------------------------------------
# 类型映射 (MySQL -> PG)
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "tinyint(1)": "boolean",
    "tinyint": "smallint",
    "int": "integer",
    "integer": "integer",
    "smallint": "smallint",
    "bigint": "bigint",
    "float": "double precision",
    "double": "double precision",
    "text": "text",
    "longtext": "text",
    "mediumtext": "text",
    "tinytext": "text",
    "datetime": "timestamp",
    "timestamp": "timestamp",
    "date": "date",
    "time": "time",
    "json": "jsonb",
}


def map_type(ctype: str) -> str:
    t = ctype.lower().strip()
    if t.startswith("decimal"):
        return "numeric" + t[len("decimal"):]
    if t.startswith("numeric"):
        return "numeric" + t[len("numeric"):]
    if t.startswith("varchar"):
        return t
    if t.startswith("char("):
        return t
    if t in _TYPE_MAP:
        return _TYPE_MAP[t]
    raise ValueError(f"未知 MySQL 列类型: {ctype}")


def default_sql(pg_type: str, mysql_default: str | None) -> str:
    """把 MySQL column_default 转成 PG 的 DEFAULT 子句(空串表示无默认)。"""
    if not mysql_default:
        return ""
    d = mysql_default.strip()
    if d.lower() in ("now()", "current_timestamp"):
        return " DEFAULT CURRENT_TIMESTAMP"
    if pg_type.startswith(("integer", "smallint", "bigint", "numeric", "double precision", "real")):
        try:
            float(d)  # 校验是数字
            return f" DEFAULT {d}"
        except ValueError:
            pass
    if pg_type == "boolean":
        low = d.lower()
        if low in ("1", "true", "t", "yes"):
            return " DEFAULT true"
        if low in ("0", "false", "f", "no"):
            return " DEFAULT false"
    # 字符串字面量默认值
    return f" DEFAULT '{d.replace(chr(39), chr(39) * 2)}'"


# ---------------------------------------------------------------------------
# 读 MySQL 结构 (information_schema)
# ---------------------------------------------------------------------------


def read_mysql_schema(conn, db_name: str) -> dict:
    cur = conn.cursor()
    cur.execute(
        """SELECT table_name FROM information_schema.tables
           WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name""",
        (db_name,),
    )
    tables = [r[0] for r in cur.fetchall()]

    cur.execute(
        """SELECT table_name, column_name, column_type, is_nullable, column_default,
                  column_key, ordinal_position
           FROM information_schema.columns
           WHERE table_schema=%s ORDER BY table_name, ordinal_position""",
        (db_name,),
    )
    columns: dict[str, list[dict]] = {}
    for t, cname, ctype, nullable, default, key, pos in cur.fetchall():
        columns.setdefault(t, []).append(
            {
                "name": cname,
                "ctype": ctype,
                "nullable": nullable == "YES",
                "default": default,
                "key": key,
                "pos": pos,
            }
        )

    cur.execute(
        """SELECT table_name, column_name, seq_in_index FROM information_schema.statistics
           WHERE table_schema=%s AND index_name='PRIMARY'
           ORDER BY table_name, seq_in_index""",
        (db_name,),
    )
    pks: dict[str, list[str]] = {}
    for t, cname, _seq in cur.fetchall():
        pks.setdefault(t, []).append(cname)

    cur.execute(
        """SELECT table_name, index_name, column_name, seq_in_index, non_unique
           FROM information_schema.statistics
           WHERE table_schema=%s AND index_name<>'PRIMARY'
           ORDER BY table_name, index_name, seq_in_index""",
        (db_name,),
    )
    indexes: dict[str, dict[str, dict]] = {}
    for t, iname, cname, _seq, nu in cur.fetchall():
        idx = indexes.setdefault(t, {}).setdefault(iname, {"cols": [], "unique": nu == 0})
        idx["cols"].append(cname)

    cur.execute(
        """SELECT table_name, column_name, referenced_table_name, referenced_column_name, constraint_name
           FROM information_schema.key_column_usage
           WHERE table_schema=%s AND referenced_table_name IS NOT NULL
           ORDER BY table_name, ordinal_position""",
        (db_name,),
    )
    fks: dict[str, list[dict]] = {}
    for t, col, ref_table, ref_col, constraint in cur.fetchall():
        fks.setdefault(t, []).append(
            {"col": col, "ref_table": ref_table, "ref_col": ref_col, "constraint": constraint}
        )
    cur.close()
    return {"tables": tables, "columns": columns, "pks": pks, "indexes": indexes, "fks": fks}


# ---------------------------------------------------------------------------
# DDL 生成
# ---------------------------------------------------------------------------


def build_create_table(schema: dict, table: str) -> str:
    parts = []
    for c in schema["columns"][table]:
        pg_type = map_type(c["ctype"])
        line = f'  "{c["name"]}" {pg_type}'
        if not c["nullable"]:
            line += " NOT NULL"
        line += default_sql(pg_type, c["default"])
        parts.append(line)
    pk = schema["pks"].get(table, [])
    if pk:
        parts.append("  PRIMARY KEY (" + ", ".join(f'"{p}"' for p in pk) + ")")
    return f'CREATE TABLE "{SCHEMA}"."{table}" (\n' + ",\n".join(parts) + "\n)"


def make_index_name(table: str, iname: str) -> str:
    # 用 MySQL 原始索引名做基底(表内唯一), 前缀表名避免跨表/跨 schema 冲突
    raw = f"school_mig_{table}_{iname}"
    if len(raw) <= 63:
        return raw
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]
    return raw[: 63 - 9] + "_" + digest


def create_indexes(p_conn, schema: dict, table: str) -> None:
    cur = p_conn.cursor()
    pk = schema["pks"].get(table, [])
    for iname, info in schema["indexes"].get(table, {}).items():
        cols = info["cols"]
        if cols == pk:  # PG 主键已自带索引
            continue
        uniq = "UNIQUE " if info["unique"] else ""
        col_sql = ", ".join(f'"{c}"' for c in cols)
        ddl = f'CREATE {uniq}INDEX "{make_index_name(table, iname)}" ON "{SCHEMA}"."{table}" ({col_sql})'
        cur.execute(ddl)


# ---------------------------------------------------------------------------
# 数据复制
# ---------------------------------------------------------------------------


def copy_table(m_conn, p_conn, schema: dict, table: str) -> None:
    cols = [c["name"] for c in schema["columns"][table]]
    pg_types = [map_type(c["ctype"]) for c in schema["columns"][table]]
    pk = schema["pks"].get(table, [])

    col_sql = ", ".join(f'"{c}"' for c in cols)
    if pk:
        pk_sql = ", ".join(f'"{p}"' for p in pk)
        insert_sql = (
            f'INSERT INTO "{SCHEMA}"."{table}" ({col_sql}) VALUES %s '
            f"ON CONFLICT ({pk_sql}) DO NOTHING"
        )
    else:
        insert_sql = f'INSERT INTO "{SCHEMA}"."{table}" ({col_sql}) VALUES %s'

    m_cur = m_conn.cursor(pymysql.cursors.SSCursor)
    m_cur.execute("SELECT " + ", ".join(f"`{c}`" for c in cols) + f" FROM `{table}`")
    p_cur = p_conn.cursor()

    while True:
        rows = m_cur.fetchmany(DEFAULT_BATCH)
        if not rows:
            break
        converted = [
            tuple(bool(v) if (pg_types[i] == "boolean" and v is not None) else v for i, v in enumerate(row))
            for row in rows
        ]
        execute_values(p_cur, insert_sql, converted, page_size=len(converted))
    m_cur.close()
    p_cur.close()


def count_mysql(m_conn, table: str) -> int:
    cur = m_conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM `{table}`")
    n = cur.fetchone()[0]
    cur.close()
    return int(n)


def count_pg(p_conn, table: str) -> int:
    cur = p_conn.cursor()
    cur.execute(f'SELECT COUNT(*) FROM "{SCHEMA}"."{table}"')
    n = cur.fetchone()[0]
    cur.close()
    return int(n)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="MySQL → PG school_mig 影子 schema 迁移")
    ap.add_argument("--tables", help="仅迁移指定表(逗号分隔), 默认迁移全部 63 张")
    ap.add_argument("--env", help="MySQL 凭据 .env 文件路径(默认自动查找)")
    ap.add_argument("--bak", help="PG 超管凭据 .env.bak_a2_20260830 路径(默认自动查找)")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH, help="每批插入行数(默认 500)")
    return ap.parse_args()


def main() -> int:
    global DEFAULT_BATCH
    args = parse_args()
    DEFAULT_BATCH = args.batch

    env_path = find_env_file(".env", args.env)
    bak_path = find_env_file(".env.bak_a2_20260830", args.bak)
    if env_path is None or not env_path.exists():
        print("找不到 .env(MySQL 凭据)。可用 --env 指定, 或在仓库根目录运行。", file=sys.stderr)
        return 2
    if bak_path is None or not bak_path.exists():
        print(
            "找不到 .env.bak_a2_20260830(PG 超管凭据)。可用 --bak 指定。",
            file=sys.stderr,
        )
        return 2

    _KEYS = ("HOST", "PORT", "USER", "PASSWORD", "NAME")
    mysql = load_env(env_path, tuple("DB_" + k for k in _KEYS))
    pg = load_env(bak_path, tuple("ASSETS_DB_" + k for k in _KEYS))
    ro_user = (load_env(env_path, ("ASSETS_DB_USER",)) or {}).get("ASSETS_DB_USER") or "grade_school_ro"

    if not all([mysql["DB_HOST"], mysql["DB_USER"], mysql["DB_PASSWORD"], mysql["DB_NAME"]]):
        print("MySQL 凭据缺失(DB_HOST/DB_USER/DB_PASSWORD/DB_NAME)。", file=sys.stderr)
        return 2
    # 注意: 本地 PG 多为 trust 认证, ASSETS_DB_PASSWORD 允许为空(仍可用 .env.bak_a2_20260830 覆盖)
    if not all([pg["ASSETS_DB_HOST"], pg["ASSETS_DB_USER"], pg["ASSETS_DB_NAME"]]):
        print("PG 超管凭据缺失(ASSETS_DB_* 来自 .env.bak_a2_20260830)。", file=sys.stderr)
        return 2
    if pg["ASSETS_DB_USER"] == "grade_school_ro":
        print(
            "错误: 检测到 PG 连接用户是只读 grade_school_ro, 无法建 schema。"
            "请从 .env.bak_a2_20260830 读取 postgres 超管凭据(或用环境变量 ASSETS_DB_USER=postgres 覆盖)。",
            file=sys.stderr,
        )
        return 2

    # ---- 连接 ----
    m_conn = pymysql.connect(
        host=mysql["DB_HOST"],
        port=int(mysql["DB_PORT"] or 3306),
        user=mysql["DB_USER"],
        password=mysql["DB_PASSWORD"],
        database=mysql["DB_NAME"],
        charset="utf8mb4",
    )
    p_conn = psycopg2.connect(
        host=pg["ASSETS_DB_HOST"],
        port=int(pg["ASSETS_DB_PORT"] or 5432),
        user=pg["ASSETS_DB_USER"],
        password=pg["ASSETS_DB_PASSWORD"],
        dbname=pg["ASSETS_DB_NAME"],
    )
    p_conn.autocommit = True

    print(f"[1/5] 读取 MySQL 结构: {mysql['DB_NAME']}")
    schema = read_mysql_schema(m_conn, mysql["DB_NAME"])
    all_tables = [t for t in schema["tables"] if t not in SKIP_TABLES]
    for t in sorted(SKIP_TABLES):
        if t not in schema["tables"]:
            print(f"  [warn] 跳过表 {t} 不在 MySQL 中", file=sys.stderr)
    if args.tables:
        requested = {x.strip() for x in args.tables.split(",") if x.strip()}
        missing = requested - set(all_tables)
        if missing:
            print(f"  [warn] 请求的表不存在或已被跳过: {sorted(missing)}", file=sys.stderr)
        all_tables = [t for t in all_tables if t in requested]
    print(f"  将迁移 {len(all_tables)} 张表: {', '.join(all_tables)}")

    cur = p_conn.cursor()
    print(f"[2/5] 重建影子 schema: {SCHEMA}")
    cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
    failures: list[str] = []
    for t in all_tables:
        try:
            cur.execute(f'DROP TABLE IF EXISTS "{SCHEMA}"."{t}" CASCADE')
            cur.execute(build_create_table(schema, t))
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {t} 建表失败: {e}")
            failures.append(t)
    cur.close()

    print("[3/5] 复制数据 + 建索引")
    for t in all_tables:
        if t in failures:
            continue
        try:
            copy_table(m_conn, p_conn, schema, t)
            create_indexes(p_conn, schema, t)
            mc = count_mysql(m_conn, t)
            pc = count_pg(p_conn, t)
            diff = mc - pc
            status = "OK " if diff == 0 else "DIFF"
            print(f"  {status} {t} | MySQL {mc} | PG {pc} | diff {diff}")
            if diff != 0:
                failures.append(t)
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {t} 复制失败: {e}")
            failures.append(t)

    print(f"[4/5] 授权只读用户 {ro_user}")
    try:
        cur = p_conn.cursor()
        cur.execute(f'GRANT USAGE ON SCHEMA "{SCHEMA}" TO "{ro_user}"')
        cur.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{SCHEMA}" TO "{ro_user}"')
        cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{SCHEMA}" GRANT SELECT ON TABLES TO "{ro_user}"')
        cur.close()
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] GRANT 失败(不影响数据): {e}", file=sys.stderr)

    print("[5/5] 对账汇总")
    total_diff = 0
    ok_count = 0
    cur = p_conn.cursor()
    for t in all_tables:
        if t in failures:
            print(f"  SKIP {t}: 失败表不参与对账")
            continue
        mc = count_mysql(m_conn, t)
        pc = count_pg(p_conn, t)
        diff = mc - pc
        total_diff += abs(diff)
        ok_count += 1 if diff == 0 else 0
    cur.execute(
        "SELECT count(*) FROM information_schema.tables "
        f"WHERE table_schema='{SCHEMA}' AND table_type='BASE TABLE'"
    )
    pg_table_count = cur.fetchone()[0]
    cur.close()

    # 逐表列数对齐检查
    col_mismatch = []
    cur = p_conn.cursor()
    cur.execute(
        f"""SELECT table_name, count(*) FROM information_schema.columns
            WHERE table_schema='{SCHEMA}' GROUP BY table_name"""
    )
    pg_cols = {r[0]: r[1] for r in cur.fetchall()}
    cur.close()
    for t in all_tables:
        if t in failures:
            continue
        if pg_cols.get(t) != len(schema["columns"][t]):
            col_mismatch.append(t)

    print(f"  迁移成功表: {ok_count}/{len(all_tables)}  表总数差异: {total_diff}")
    print(f"  PG school_mig 表数: {pg_table_count} (期望 {len(all_tables)})")
    if col_mismatch:
        print(f"  [FAIL] 列数不对齐: {col_mismatch}", file=sys.stderr)
        failures.extend(col_mismatch)

    # 供 E3 校验用的结构元数据(含 FK 关系), 写入 gitignored temp/
    try:
        import json

        meta = {
            "source": "mysql",
            "schema": SCHEMA,
            "tables": {t: schema["columns"][t] for t in all_tables},
            "pks": {t: schema["pks"][t] for t in all_tables if t in schema["pks"]},
            "indexes": {t: schema["indexes"].get(t, {}) for t in all_tables},
            "fks": {t: schema["fks"].get(t, []) for t in all_tables},
            "fk_summary": {t: len(schema["fks"].get(t, [])) for t in all_tables},
        }
        meta_dir = Path.cwd() / "temp"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_path = meta_dir / "mysql_schema_meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"  结构元数据(含 FK 关系)已写入: {meta_path}")
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] 元数据落盘失败: {e}", file=sys.stderr)

    m_conn.close()
    p_conn.close()

    if failures or total_diff != 0 or pg_table_count != len(all_tables):
        print(f"\n结果: FAIL(差异非 0 或存在失败表) failures={failures}", file=sys.stderr)
        return 1
    print("\n结果: PASS(63 表差异全 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
