#!/usr/bin/env python3
"""P3-E2: MySQL → PG school_mig 影子 schema 逐表对账脚本(只读, 独立验收)。

在 E1(scripts/copy_rows.py)迁移完成后独立运行, 对 PG school_mig 影子 schema
下的 63 张表做二次一致性验收, 不依赖 copy_rows.py 迁移时的行数校验。对账项:

  1. 行数       MySQL count(*) vs PG school_mig count(*) 差异必须全 0
  2. 列数对齐   MySQL 列(名称+顺序) vs PG school_mig 列逐表一致
  3. 主键完整性 从 PG information_schema 读主键列, 校验 PG 侧主键无 NULL、
                无重复(GROUP BY 主键 HAVING count(*)>1 计数为 0)
  4. sample 抽样 每表按主键抽 3 行(头/中/尾), 以主键值回查另一侧对应行,
                逐列值比对; float/double 用容差(abs diff < 1e-6),
                datetime 归一化比较, json/jsonb 反序列化后深比较,
                NULL 对 NULL 一致

安全约定:
  - 只读对账: 对 PG 仅 SELECT information_schema / school_mig, 绝不
    DDL/DML/DROP, 绝不触碰 public schema; 对 MySQL 仅 SELECT count/主键/sample。
  - 凭据只从 .env(DB_*)/ .env.bak_a2_20260830(ASSETS_DB_*) 读取, 脚本内无明文密码。
  - 检测到 PG 连接用户为只读 grade_school_ro 时 fail-fast(该用户是给应用只读
    用的, 对账避免用只读账号误判权限问题)。

用法:
  python scripts/verify_counts.py [--env FILE] [--bak FILE] [--tables a,b,c] [--schema public]
                                   [--expected-extra-cols curriculum]

说明:
  --schema 默认 school_mig(影子 schema 对账); 传 public 可对账并入后的 PG 主库
  (MySQL vs public), 供 E4 scripts/merge_to_public.py --run 完成后做最终对账。
  列比较为集合比较(顺序不同不算差异); PG 允许比 MySQL 多出 --expected-extra-cols
  白名单列(默认 curriculum, 灵犀家长端在 public 空壳表上的扩展列, 迁移方案 C)。

退出码:
  0 全 PASS(行数/列数/主键/抽样差异全 0, 报告可存档)
  1 存在任一差异
  2 配置/连接错误
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

try:
    import pymysql
    import psycopg2
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover
    print("缺少依赖: pip install pymysql psycopg2-binary python-dotenv", file=sys.stderr)
    sys.exit(1)

SCHEMA = "school_mig"
# 4 张废弃表: MySQL 0 行, PG 资产权威, E1 跳过迁移
SKIP_TABLES = {"knowledge_points", "subject_units", "wrong_questions", "parent_students"}
FLOAT_TOL = 1e-6
_KEYS = ("HOST", "PORT", "USER", "PASSWORD", "NAME")

# 预期列差异白名单: 灵犀家长端在 public 空壳表上的扩展列(迁移方案 C 设计如此,
# 显式列映射填充时保留)。PG 列集合 = MySQL 列集合 ∪ 白名单内列时视为一致;
# 白名单外的任何列差异仍判 FAIL, 不放宽。
EXPECTED_EXTRA_COLS = frozenset({"curriculum"})
# public 表数基线(E 迁移后): 142 张迁移前基线 + 51 张 E4 merge 新建 = 193 非备份表。
# public 实际总表数可能因灵犀侧 *_backup_YYYYMMDD 备份表(如 questions_chid_safe_backup_20260830)
# 而 > 此值, 属预期; 断言前动态排除备份表, 避免备份表数量变化导致误报。
EXPECT_PUBLIC_TABLES = 193
BACKUP_TABLE_RE = re.compile(r"_backup_\d{8}$")


def _force_utf8_stdio() -> None:
    """强制 stdout/stderr 使用 UTF-8, 保证对账报告可存档(避免 Windows 管道被
    locale 编码成 GBK 导致乱码)。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # 非文本流或老版本解释器
            pass


_force_utf8_stdio()


# ---------------------------------------------------------------------------
# 环境文件定位与凭据加载(与 scripts/copy_rows.py 一致)
# ---------------------------------------------------------------------------


def find_env_file(name: str, explicit: str | None) -> Path | None:
    """定位 env 文件: 显式参数 > cwd > scripts/ 上级 > 沿目录树向上查找。"""
    if explicit:
        p = Path(explicit).resolve()
        return p if p.exists() else None
    cwd = Path.cwd().resolve()
    script_root = Path(__file__).resolve().parent.parent
    candidates: list[Path] = [cwd / name, script_root / name]
    p = cwd
    while True:
        f = p / name
        if f.exists():
            candidates.append(f)
        if p == p.parent:
            break
        p = p.parent
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
    """从 env 文件读取指定 key; 文件优先, 缺失时回退环境变量。"""
    raw: dict[str, str] = {}
    if path and path.exists():
        raw = {k: v for k, v in dotenv_values(path).items() if v is not None}
    out: dict[str, str] = {}
    for k in keys:
        out[k] = (raw.get(k) or os.environ.get(k) or "").strip()
    return out


# ---------------------------------------------------------------------------
# 元数据读取(只读 information_schema)
# ---------------------------------------------------------------------------


def list_tables(p_conn, schema: str) -> list[str]:
    cur = p_conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name",
        (schema,),
    )
    tables = [r[0] for r in cur.fetchall()]
    cur.close()
    return tables


def mysql_meta(m_conn, db_name: str, tables: list[str]) -> dict:
    """{table: {'cols': [名称有序], 'col_types': {col: mysql_data_type}, 'pk': [...]}}"""
    cur = m_conn.cursor()
    in_list = ", ".join(["%s"] * len(tables))
    cur.execute(
        f"""SELECT table_name, column_name, data_type, ordinal_position
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name IN ({in_list})
            ORDER BY table_name, ordinal_position""",
        (db_name, *tables),
    )
    meta: dict[str, dict] = {t: {"cols": [], "col_types": {}, "pk": []} for t in tables}
    for t, cname, dtype, _pos in cur.fetchall():
        meta[t]["cols"].append(cname)
        meta[t]["col_types"][cname] = dtype

    cur.execute(
        f"""SELECT table_name, column_name FROM information_schema.statistics
            WHERE table_schema=%s AND index_name='PRIMARY' AND table_name IN ({in_list})
            ORDER BY table_name, seq_in_index""",
        (db_name, *tables),
    )
    for t, cname in cur.fetchall():
        meta[t]["pk"].append(cname)
    cur.close()
    return meta


def pg_meta(p_conn, schema: str, tables: list[str]) -> dict:
    """{table: {'cols': [名称有序], 'col_types': {col: pg_data_type}, 'pk': [...]}}"""
    cur = p_conn.cursor()
    in_list = ", ".join(["%s"] * len(tables))
    cur.execute(
        f"""SELECT table_name, column_name, data_type, ordinal_position
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name IN ({in_list})
            ORDER BY table_name, ordinal_position""",
        (schema, *tables),
    )
    meta: dict[str, dict] = {t: {"cols": [], "col_types": {}, "pk": []} for t in tables}
    for t, cname, dtype, _pos in cur.fetchall():
        meta[t]["cols"].append(cname)
        meta[t]["col_types"][cname] = dtype

    cur.execute(
        f"""SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=%s
              AND tc.table_name IN ({in_list})
            ORDER BY tc.table_name, kcu.ordinal_position""",
        (schema, *tables),
    )
    for t, cname in cur.fetchall():
        meta[t]["pk"].append(cname)
    cur.close()
    return meta


# ---------------------------------------------------------------------------
# 值比对
# ---------------------------------------------------------------------------


def norm_json(v):
    """jsonb 可能已被 psycopg2 解析为 dict/list, 也可能仍是 str, 统一成对象。"""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return v
    return v


def compare_value(mval, pval, mtype: str, ptype: str):
    """逐值比对, 返回 (ok: bool, detail: str|None)。mtype/ptype 为 data_type。"""
    if mval is None and pval is None:
        return True, None
    if mval is None or pval is None:
        return False, f"NULL 不一致 MySQL={mval!r} PG={pval!r}"

    # boolean: MySQL tinyint(1) 0/1 -> PG boolean
    if ptype == "boolean":
        if bool(mval) != bool(pval):
            return False, f"boolean 不一致 MySQL={mval!r} PG={pval!r}"
        return True, None

    # float / double: 容差比较
    if mtype in ("float", "double") or ptype == "double precision":
        try:
            mf, pf = float(mval), float(pval)
        except (TypeError, ValueError):
            return False, f"非数值 float MySQL={mval!r} PG={pval!r}"
        if abs(mf - pf) >= FLOAT_TOL:
            return False, f"float 超容差({FLOAT_TOL}) MySQL={mf!r} PG={pf!r}"
        return True, None

    # decimal / numeric: 精确比较
    if mtype in ("decimal", "numeric") or ptype == "numeric":
        try:
            md, pd = Decimal(str(mval)), Decimal(str(pval))
        except Exception:  # noqa: BLE001
            return False, f"decimal 解析失败 MySQL={mval!r} PG={pval!r}"
        if md != pd:
            return False, f"decimal 不一致 MySQL={md} PG={pd}"
        return True, None

    # json / jsonb: 反序列化后深比较(忽略键序/空白)
    if mtype == "json" or ptype == "jsonb":
        if norm_json(mval) != norm_json(pval):
            return False, f"json 不一致 MySQL={mval!r} PG={pval!r}"
        return True, None

    # datetime / timestamp: 归一化(去 tzinfo)后比较
    if isinstance(mval, datetime) or isinstance(pval, datetime):
        m2 = mval.replace(tzinfo=None) if isinstance(mval, datetime) else mval
        p2 = pval.replace(tzinfo=None) if isinstance(pval, datetime) else pval
        if m2 != p2:
            return False, f"datetime 不一致 MySQL={mval!r} PG={pval!r}"
        return True, None

    # date
    if isinstance(mval, date) or isinstance(pval, date):
        if mval != pval:
            return False, f"date 不一致 MySQL={mval!r} PG={pval!r}"
        return True, None

    # 其余(varchar/text/int/smallint/bigint 等): 直接比较
    if mval != pval:
        return False, f"值不一致 MySQL={mval!r} PG={pval!r}"
    return True, None


# ---------------------------------------------------------------------------
# 对账核心
# ---------------------------------------------------------------------------


def count_mysql(m_conn, table: str) -> int:
    cur = m_conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM `{table}`")
    n = int(cur.fetchone()[0])
    cur.close()
    return n


def count_pg(p_conn, table: str) -> int:
    cur = p_conn.cursor()
    cur.execute(f'SELECT COUNT(*) FROM "{SCHEMA}"."{table}"')
    n = int(cur.fetchone()[0])
    cur.close()
    return n


def check_pk_integrity(p_conn, table: str, pk: list[str]) -> tuple[int, int]:
    """返回 (NULL 行数, 重复组数)。"""
    cur = p_conn.cursor()
    null_cond = " OR ".join(f'"{c}" IS NULL' for c in pk)
    cur.execute(f'SELECT COUNT(*) FROM "{SCHEMA}"."{table}" WHERE {null_cond}')
    null_cnt = int(cur.fetchone()[0])
    group_cols = ", ".join(f'"{c}"' for c in pk)
    cur.execute(
        f'SELECT COUNT(*) FROM (SELECT {group_cols} FROM "{SCHEMA}"."{table}" '
        f"GROUP BY {group_cols} HAVING COUNT(*)>1) s"
    )
    dup_cnt = int(cur.fetchone()[0])
    cur.close()
    return null_cnt, dup_cnt


def sample_compare(m_conn, p_conn, m_meta: dict, p_meta: dict, table: str, n: int):
    """按主键抽 3 行(头/中/尾)比对全列值。

    从 MySQL 侧按主键排序取 OFFSET 行, 再用主键值回查 PG 侧对应行, 逐列比对。
    用主键值回查而非两侧各自 OFFSET, 可规避 MySQL/PG 对字符串主键排序规则
    差异导致选到不同行的问题。
    返回 (失败明细列表, 实际抽样行数)。
    """
    if n == 0:
        return [], 0
    pk = p_meta[table]["pk"]
    cols = m_meta[table]["cols"]
    m_cols = m_meta[table]["col_types"]
    p_cols = p_meta[table]["col_types"]

    m_sel = ", ".join(f"`{c}`" for c in cols)
    # PG 侧 jsonb 用 ::text 取出: 区分 SQL NULL(仍为 NULL) 与 JSON null(文本 'null'),
    # 避免 psycopg2 把 JSON null 也解析成 Python None 而与 SQL NULL 混淆。
    p_sel_items = []
    for c in cols:
        if p_cols.get(c) == "jsonb":
            p_sel_items.append(f'"{c}"::text AS "{c}"')
        else:
            p_sel_items.append(f'"{c}"')
    p_sel = ", ".join(p_sel_items)
    order_m = ", ".join(f"`{c}`" for c in pk)
    pk_cond_p = " AND ".join(f'"{c}"=%s' for c in pk)

    offsets = sorted({0, n // 2, n - 1})
    failures: list[str] = []
    for off in offsets:
        m_cur = m_conn.cursor()
        m_cur.execute(f"SELECT {m_sel} FROM `{table}` ORDER BY {order_m} LIMIT 1 OFFSET {int(off)}")
        m_row = m_cur.fetchone()
        m_cur.close()
        if m_row is None:
            failures.append(f"offset {off}: MySQL 侧无行")
            continue
        pk_vals = tuple(m_row[cols.index(c)] for c in pk)
        p_cur = p_conn.cursor()
        p_cur.execute(f'SELECT {p_sel} FROM "{SCHEMA}"."{table}" WHERE {pk_cond_p}', pk_vals)
        p_row = p_cur.fetchone()
        p_cur.close()
        if p_row is None:
            failures.append(f"offset {off} 主键 {pk_vals!r}: PG 侧无对应行")
            continue
        for i, c in enumerate(cols):
            ok, detail = compare_value(m_row[i], p_row[i], m_cols.get(c, ""), p_cols.get(c, ""))
            if not ok:
                failures.append(f"offset {off} 列 `{c}`: {detail}")
    return failures, len(offsets)


def verify_table(m_conn, p_conn, m_meta: dict, p_meta: dict, table: str,
                 expected_extra: frozenset[str] = frozenset()):
    """对单表执行全部对账, 返回 (status, row_diff, parts, fails)。

    expected_extra: PG 允许比 MySQL 多出的扩展列白名单(见 EXPECTED_EXTRA_COLS)。
    """
    fails: list[str] = []
    parts: list[str] = []

    m_cols = m_meta[table]["cols"]
    p_cols = p_meta[table]["cols"]
    if not m_cols:
        # MySQL 侧无此表(information_schema 无列): 结构性缺失
        return "FAIL", 0, [f"rows ?=?"], ["MySQL 侧无此表(information_schema 无列)"]
    if not p_cols:
        return "FAIL", 0, [f"rows ?=?"], ["PG 侧无此表(information_schema 无列)"]

    # 1) 行数
    mc = count_mysql(m_conn, table)
    pc = count_pg(p_conn, table)
    row_diff = abs(mc - pc)
    parts.append(f"rows {mc}={pc}")
    if mc != pc:
        fails.append(f"行数不一致 MySQL={mc} PG={pc} diff={mc - pc}")

    # 2) 列对齐(集合比较: 顺序不同不算差异; PG 允许存在白名单扩展列)
    parts.append(f"cols {len(m_cols)}={len(p_cols)}")
    m_set, p_set = set(m_cols), set(p_cols)
    if m_set != p_set:
        missing_pg = sorted(m_set - p_set)
        extra_pg = sorted(p_set - m_set)
        unexpected = sorted(p_set - m_set - expected_extra)
        if missing_pg or unexpected:
            fails.append(f"列集合不一致 MySQL={m_cols} PG={p_cols}")
            if missing_pg:
                fails.append(f"PG 缺失列: {missing_pg}")
            if unexpected:
                fails.append(f"PG 额外列(非白名单 {sorted(expected_extra)}): {unexpected}")
        else:
            # 预期差异: PG 多出列全在白名单(灵犀家长端在 public 空壳表上的扩展列, 迁移方案 C)
            parts.append(f"extra cols: {extra_pg}")

    # 3) 主键完整性(PG 侧) + 主键列与 MySQL 一致
    m_pk = m_meta[table]["pk"]
    p_pk = p_meta[table]["pk"]
    if m_pk != p_pk:
        fails.append(f"主键列不一致 MySQL={m_pk} PG={p_pk}")
    if not p_pk:
        fails.append("PG 侧无主键")
    else:
        null_cnt, dup_cnt = check_pk_integrity(p_conn, table, p_pk)
        parts.append(f"pk NULL {null_cnt}/dup {dup_cnt}")
        if null_cnt:
            fails.append(f"主键存在 {null_cnt} 个 NULL")
        if dup_cnt:
            fails.append(f"主键存在 {dup_cnt} 组重复")

    # 4) sample 抽样
    if not fails:
        samp_fails, samp_n = sample_compare(m_conn, p_conn, m_meta, p_meta, table, mc)
        parts.append(f"sample {samp_n}/3")
        if samp_fails:
            fails.extend(samp_fails)
    else:
        parts.append("sample skip")
        fails.append("sample 跳过(前置项失败)")

    status = "PASS" if not fails else "FAIL"
    return status, row_diff, parts, fails


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="MySQL → PG school_mig 影子 schema 逐表对账(只读)")
    ap.add_argument("--env", help="MySQL 凭据 .env 文件路径(默认自动查找)")
    ap.add_argument("--bak", help="PG 凭据 .env.bak_a2_20260830 路径(默认自动查找)")
    ap.add_argument("--tables", help="仅对账指定表(逗号分隔), 默认全部 63 张")
    ap.add_argument(
        "--schema",
        default="school_mig",
        help="对账目标 schema(默认 school_mig; 传 public 对账并入后的 PG 主库, E4 最终对账用)",
    )
    ap.add_argument(
        "--expected-extra-cols",
        action="append",
        default=[],
        metavar="COL",
        help="预期 PG 比 MySQL 多出的扩展列名(可多次传); 默认取模块常量 "
             "EXPECTED_EXTRA_COLS(curriculum)。白名单外的列差异仍判 FAIL。",
    )
    return ap.parse_args()


def main() -> int:
    global SCHEMA
    args = parse_args()
    SCHEMA = args.schema
    expected_extra = set(EXPECTED_EXTRA_COLS)
    if args.expected_extra_cols:
        expected_extra.update(c.strip() for c in args.expected_extra_cols if c.strip())
    expected_extra = frozenset(expected_extra)
    env_path = find_env_file(".env", args.env)
    bak_path = find_env_file(".env.bak_a2_20260830", args.bak)
    if env_path is None or not env_path.exists():
        print("找不到 .env(MySQL 凭据)。可用 --env 指定, 或在仓库根目录运行。", file=sys.stderr)
        return 2
    if bak_path is None or not bak_path.exists():
        print("找不到 .env.bak_a2_20260830(PG 凭据)。可用 --bak 指定。", file=sys.stderr)
        return 2

    mysql = load_env(env_path, tuple("DB_" + k for k in _KEYS))
    pg = load_env(bak_path, tuple("ASSETS_DB_" + k for k in _KEYS))

    if not all([mysql["DB_HOST"], mysql["DB_USER"], mysql["DB_PASSWORD"], mysql["DB_NAME"]]):
        print("MySQL 凭据缺失(DB_HOST/DB_USER/DB_PASSWORD/DB_NAME)。", file=sys.stderr)
        return 2
    # 本地 PG 多为 trust 认证, ASSETS_DB_PASSWORD 允许为空(仍保留环境变量引用)
    if not all([pg["ASSETS_DB_HOST"], pg["ASSETS_DB_USER"], pg["ASSETS_DB_NAME"]]):
        print("PG 凭据缺失(ASSETS_DB_* 来自 .env.bak_a2_20260830)。", file=sys.stderr)
        return 2
    if pg["ASSETS_DB_USER"] == "grade_school_ro":
        print(
            "错误: 检测到 PG 连接用户是只读 grade_school_ro, 对账需要超管连接。"
            "请从 .env.bak_a2_20260830 读取 postgres 超管凭据(或用环境变量 ASSETS_DB_USER=postgres 覆盖)。",
            file=sys.stderr,
        )
        return 2

    # ---- 连接 ----
    try:
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
    except Exception as e:  # noqa: BLE001
        print(f"数据库连接失败: {e}", file=sys.stderr)
        return 2
    p_conn.autocommit = True

    print(f"[env] MySQL {mysql['DB_HOST']}:{mysql['DB_PORT'] or 3306}/{mysql['DB_NAME']} | "
          f"PG {pg['ASSETS_DB_HOST']}:{pg['ASSETS_DB_PORT'] or 5432}/{pg['ASSETS_DB_NAME']}")

    # ---- 表清单 ----
    pg_tables = list_tables(p_conn, SCHEMA)
    if SCHEMA == "school_mig":
        print(f"[1/5] PG school_mig 表清单: {len(pg_tables)} 张")
        if len(pg_tables) != 63:
            print(f"  [FAIL] school_mig 表数 {len(pg_tables)} != 63(期望 63, 跳过废弃 4 张)", file=sys.stderr)
            m_conn.close()
            p_conn.close()
            return 1
    else:
        # 非默认 schema(如 public): 只对账 MySQL 存在且非废弃的迁移表,
        # 避免把 parent_* / 资产表(MySQL 无对应)误判为差异
        cur = m_conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=%s AND table_type='BASE TABLE'",
            (mysql["DB_NAME"],),
        )
        mysql_tables = {r[0] for r in cur.fetchall()}
        cur.close()
        pg_tables = [t for t in pg_tables if t in mysql_tables and t not in SKIP_TABLES]
        print(f"[1/5] PG {SCHEMA} 迁移表清单(限 MySQL 非废弃): {len(pg_tables)} 张")

    m_meta = mysql_meta(m_conn, mysql["DB_NAME"], pg_tables)
    p_meta = pg_meta(p_conn, SCHEMA, pg_tables)

    if args.tables:
        requested = {x.strip() for x in args.tables.split(",") if x.strip()}
        missing = requested - set(pg_tables)
        if missing:
            print(f"  [warn] 指定表不存在于 school_mig: {sorted(missing)}", file=sys.stderr)
        pg_tables = [t for t in pg_tables if t in requested]
    print(f"  对账表数: {len(pg_tables)}")

    # ---- 逐表对账 ----
    print("[2/5] 逐表对账(行数/列数/主键完整性/sample 抽样)")
    all_failures: dict[str, list[str]] = {}
    row_diff_total = 0
    for t in pg_tables:
        status, row_diff, parts, fails = verify_table(m_conn, p_conn, m_meta, p_meta, t, expected_extra)
        line = f"  [{status}] {t} | " + " | ".join(parts)
        print(line)
        row_diff_total += row_diff
        if fails:
            all_failures[t] = fails
            for f in fails:
                print(f"      - {f}")

    # ---- public 未触碰检查(仅默认 school_mig 对账时断言; 传 --schema public 时跳过) ----
    # 备份表(*_backup_YYYYMMDD, 灵犀侧)在计数与断言前动态排除, 避免数量变化误报。
    cur = p_conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
    )
    public_tables = [r[0] for r in cur.fetchall()]
    cur.close()
    public_backups = [t for t in public_tables if BACKUP_TABLE_RE.search(t)]
    public_non_backup = [t for t in public_tables if not BACKUP_TABLE_RE.search(t)]
    public_count = len(public_tables)
    if SCHEMA == "school_mig":
        print(f"[3/5] PG public schema 表数(只读, 未触碰): {public_count} "
              f"(非备份 {len(public_non_backup)}, 备份 {len(public_backups)})")
        if public_backups:
            print(f"      备份表({len(public_backups)}): {sorted(public_backups)}")
    else:
        print(f"[3/5] PG public schema 表数(对账目标即 public, 不作未触碰断言): {public_count}")

    # ---- 汇总 ----
    print("[4/5] 汇总")
    n_pass = len(pg_tables) - len(all_failures)
    print(f"  {len(pg_tables)} 表: {n_pass} PASS / {len(all_failures)} FAIL")
    print(f"  行数差异总量: {row_diff_total}")
    pk_null = sum(1 for fs in all_failures.values() if any("主键存在" in f and "NULL" in f for f in fs))
    pk_dup = sum(1 for fs in all_failures.values() if any("主键存在" in f and "重复" in f for f in fs))
    col_mismatch = sum(1 for fs in all_failures.values()
                       if any("列集合不一致" in f or "缺失列" in f or "额外列" in f for f in fs))
    samp_mismatch = sum(1 for fs in all_failures.values() if any("offset" in f for f in fs))
    print(
        f"  列数/列名不对齐: {col_mismatch}  主键 NULL/重复: {pk_null}/{pk_dup}  "
        f"sample 不一致: {samp_mismatch}"
    )

    m_conn.close()
    p_conn.close()

    if all_failures or row_diff_total or (
        SCHEMA == "school_mig" and len(public_non_backup) != EXPECT_PUBLIC_TABLES
    ):
        print(f"\n结果: FAIL(存在差异) 失败表: {sorted(all_failures)}", file=sys.stderr)
        return 1
    print(f"\n结果: PASS({len(pg_tables)} 表对账差异全 0, 报告可存档)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
