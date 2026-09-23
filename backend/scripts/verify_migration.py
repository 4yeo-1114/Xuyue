#!/usr/bin/env python3
"""P3-E3: 迁移后深度校验(FK 完整性 / JSON 合法 / 时区一致)。

在 E1(scripts/copy_rows.py, MySQL→PG school_mig 影子 schema)与
E2(scripts/verify_counts.py 逐表对账)完成后独立运行, 对迁移质量做三项深度校验:

  A. FK 完整性  从 MySQL information_schema 读全部外键定义, 对已迁入 school_mig 的
                表(子表与父表都在 school_mig, 约 103 条)在 PG 侧查孤儿行
                (LEFT JOIN 后父列 IS NULL 且子列非 NULL)。孤儿计数全 0 才 PASS。
  B. JSON 合法  从 PG information_schema 列 school_mig 全部 jsonb 列, 每列抽样
                (最多 100 行)用 json.loads 反序列化验证。PG jsonb 插入即校验,
                本项确认迁移无损坏。
  C. 时区一致  对含 MySQL datetime/timestamp 列的表, 每表按主键抽 3 行(头/中/尾),
                逐时间列比较 MySQL 值 vs PG 值。PG 列为 timestamp without time zone
                直比; 若为 timestamptz 则归一化到 UTC 后比较。

安全约定(与 copy_rows/verify_counts 一致):
  - 只读: 对 PG 仅 SELECT information_schema / school_mig, 绝不 DDL/DML/DROP,
    绝不触碰 public schema; 对 MySQL 仅 SELECT information_schema / 表数据。
  - 凭据只从 .env(DB_*) / .env.bak_a2_20260830(ASSETS_DB_*) 读取(或已有环境变量),
    脚本内无明文密码字面量。
  - 检测到 PG 连接用户为只读 grade_school_ro 时 fail-fast。
  - PG public schema 非备份表数在脚本结尾复核(期望 193 = 142 迁移前 + 51 E4 新建,
    动态排除 *_backup_YYYYMMDD 备份表), 确认脚本未触碰 public。

用法:
  python scripts/verify_migration.py [--env FILE] [--bak FILE]

退出码:
  0 全 PASS(A/B/C 三项孤儿/非法 JSON/时区差异全 0, 报告可存档)
  1 存在任一差异
  2 配置/连接错误
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import pymysql
    import psycopg2
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover
    print("缺少依赖: pip install pymysql psycopg2-binary python-dotenv", file=sys.stderr)
    sys.exit(1)

SCHEMA = "school_mig"
# 4 张废弃表: MySQL 0 行, PG 资产权威, E1 跳过迁移, 其 FK 不参与校验
SKIP_TABLES = {"knowledge_points", "subject_units", "wrong_questions", "parent_students"}
JSON_SAMPLE_LIMIT = 100   # B 项每 jsonb 列最多抽样行数
_KEYS = ("HOST", "PORT", "USER", "PASSWORD", "NAME")
# public 表数基线(E 迁移后): 142 张迁移前基线 + 51 张 E4 merge 新建 = 193 非备份表。
# public 实际总表数可能因灵犀侧 *_backup_YYYYMMDD 备份表(如 questions_chid_safe_backup_20260830)
# 而 > 此值, 属预期; 断言前动态排除备份表, 避免备份表数量变化导致误报。
EXPECT_PUBLIC_TABLES = 193
BACKUP_TABLE_RE = re.compile(r"_backup_\d{8}$")


def _force_utf8_stdio() -> None:
    """强制 stdout/stderr 使用 UTF-8, 保证报告可存档(避免 Windows 管道被 locale
    编码成 GBK 导致乱码)。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # 非文本流或老版本解释器
            pass


_force_utf8_stdio()


# ---------------------------------------------------------------------------
# 环境文件定位与凭据加载(与 scripts/copy_rows.py / verify_counts.py 一致)
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


def connect(mysql_cfg: dict, pg_cfg: dict):
    """建立只读连接(MySQL 会话保持 UTF-8, PG 只读事务)。"""
    m_conn = pymysql.connect(
        host=mysql_cfg["DB_HOST"],
        port=int(mysql_cfg["DB_PORT"] or 3306),
        user=mysql_cfg["DB_USER"],
        password=mysql_cfg["DB_PASSWORD"],
        database=mysql_cfg["DB_NAME"],
        charset="utf8mb4",
    )
    p_conn = psycopg2.connect(
        host=pg_cfg["ASSETS_DB_HOST"],
        port=int(pg_cfg["ASSETS_DB_PORT"] or 5432),
        user=pg_cfg["ASSETS_DB_USER"],
        password=pg_cfg["ASSETS_DB_PASSWORD"],
        dbname=pg_cfg["ASSETS_DB_NAME"],
    )
    p_conn.autocommit = True
    # 只读快照: 整脚本只见迁移完成时的一致视图, 不依赖外部写入
    try:
        cur = p_conn.cursor()
        cur.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cur.close()
    except Exception:  # noqa: BLE001 已 autocommit, 兼容无法显式 BEGIN 的环境
        pass
    return m_conn, p_conn


def list_migrated_tables(p_conn) -> list[str]:
    cur = p_conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name",
        (SCHEMA,),
    )
    tables = [r[0] for r in cur.fetchall()]
    cur.close()
    return tables


def quote_ident(name: str) -> str:
    """双引号标识符并转义内部双引号(元数据来自 information_schema, 仍防御性转义)。"""
    return '"' + name.replace('"', '""') + '"'


def pg_pks(p_conn, tables: list[str]) -> dict[str, list[str]]:
    cur = p_conn.cursor()
    in_list = ", ".join(["%s"] * len(tables))
    cur.execute(
        f"""SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=%s
              AND tc.table_name IN ({in_list})
            ORDER BY tc.table_name, kcu.ordinal_position""",
        (SCHEMA, *tables),
    )
    pks: dict[str, list[str]] = {}
    for t, c in cur.fetchall():
        pks.setdefault(t, []).append(c)
    cur.close()
    return pks


# ---------------------------------------------------------------------------
# A. FK 完整性: 从 MySQL information_schema 读 FK 定义, PG school_mig 查孤儿
# ---------------------------------------------------------------------------


def read_mysql_fks(m_conn, db_name: str) -> list[dict]:
    """返回按 (子表, 约束名) 聚合的外键列表。

    用 KEY_COLUMN_USAGE(带 ORDINAL_POSITION 排序, 兼容复合外键)取列映射,
    referenced_table_name 取父表。外键列在父表侧必为唯一索引列, LEFT JOIN
    孤儿查询安全。
    """
    cur = m_conn.cursor()
    cur.execute(
        """SELECT tc.table_name, kcu.column_name, kcu.referenced_table_name,
                  kcu.referenced_column_name, kcu.constraint_name, kcu.ordinal_position
           FROM information_schema.table_constraints tc
           JOIN information_schema.key_column_usage kcu
             ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
           WHERE tc.table_schema=%s AND tc.constraint_type='FOREIGN KEY'
             AND kcu.referenced_table_name IS NOT NULL
           ORDER BY tc.table_name, kcu.constraint_name, kcu.ordinal_position""",
        (db_name,),
    )
    rows = cur.fetchall()
    cur.close()

    agg: "OrderedDict[tuple[str, str], dict]" = OrderedDict()
    for t, cname, rtable, rcol, cname_c, pos in rows:
        key = (t, cname_c)
        agg.setdefault(
            key,
            {"child": t, "child_cols": [], "parent": rtable, "parent_cols": [], "constraint": cname_c},
        )
        agg[key]["child_cols"].append((pos, cname))
        agg[key]["parent_cols"].append((pos, rcol))
    return [
        {
            "child": v["child"],
            "child_cols": [c for _, c in sorted(v["child_cols"])],
            "parent": v["parent"],
            "parent_cols": [c for _, c in sorted(v["parent_cols"])],
            "constraint": v["constraint"],
        }
        for v in agg.values()
    ]


def orphan_count(p_conn, fk: dict) -> int:
    """PG school_mig 侧单条 FK 的孤儿计数。子列全非 NULL 且父侧无匹配。"""
    child = quote_ident(SCHEMA) + "." + quote_ident(fk["child"])
    parent = quote_ident(SCHEMA) + "." + quote_ident(fk["parent"])
    joins = " AND ".join(
        f'c.{quote_ident(cc)} = p.{quote_ident(pc)}'
        for cc, pc in zip(fk["child_cols"], fk["parent_cols"])
    )
    parent_null = " AND ".join(f'p.{quote_ident(pc)} IS NULL' for pc in fk["parent_cols"])
    child_notnull = " AND ".join(f'c.{quote_ident(cc)} IS NOT NULL' for cc in fk["child_cols"])
    sql = (
        f"SELECT COUNT(*) FROM {child} c "
        f"LEFT JOIN {parent} p ON {joins} "
        f"WHERE {parent_null} AND {child_notnull}"
    )
    cur = p_conn.cursor()
    cur.execute(sql)
    n = int(cur.fetchone()[0])
    cur.close()
    return n


def orphan_samples(p_conn, fk: dict, pk: list[str], limit: int = 5) -> list[list]:
    """孤儿样例行: 子表主键 + 子列值, 便于定位。"""
    child = quote_ident(SCHEMA) + "." + quote_ident(fk["child"])
    parent = quote_ident(SCHEMA) + "." + quote_ident(fk["parent"])
    joins = " AND ".join(
        f'c.{quote_ident(cc)} = p.{quote_ident(pc)}'
        for cc, pc in zip(fk["child_cols"], fk["parent_cols"])
    )
    parent_null = " AND ".join(f'p.{quote_ident(pc)} IS NULL' for pc in fk["parent_cols"])
    child_notnull = " AND ".join(f'c.{quote_ident(cc)} IS NOT NULL' for cc in fk["child_cols"])
    sel_cols = list(pk) + list(fk["child_cols"])
    seen: set[str] = set()
    sel_items: list[str] = []
    for c in sel_cols:
        if c in seen:
            continue
        seen.add(c)
        sel_items.append(f"c.{quote_ident(c)}")
    sql = (
        f"SELECT {', '.join(sel_items)} FROM {child} c "
        f"LEFT JOIN {parent} p ON {joins} "
        f"WHERE {parent_null} AND {child_notnull} LIMIT {int(limit)}"
    )
    cur = p_conn.cursor()
    cur.execute(sql)
    rows = [list(r) for r in cur.fetchall()]
    cur.close()
    return rows


# ---------------------------------------------------------------------------
# B. JSON 合法: 枚举 school_mig jsonb 列, 抽样 json.loads 验证
# ---------------------------------------------------------------------------


def list_jsonb_columns(p_conn) -> list[tuple[str, str]]:
    cur = p_conn.cursor()
    cur.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema=%s AND data_type='jsonb' "
        "ORDER BY table_name, column_name",
        (SCHEMA,),
    )
    cols = [(t, c) for t, c in cur.fetchall()]
    cur.close()
    return cols


def sample_json_column(p_conn, table: str, column: str) -> tuple[int, int, list[str]]:
    """抽样反序列化, 返回 (抽样数, 非法数, 非法样例)。"""
    sql = (
        f"SELECT {quote_ident(column)}::text FROM {quote_ident(SCHEMA)}.{quote_ident(table)} "
        f"WHERE {quote_ident(column)} IS NOT NULL LIMIT {JSON_SAMPLE_LIMIT}"
    )
    cur = p_conn.cursor()
    cur.execute(sql)
    vals = [r[0] for r in cur.fetchall()]
    cur.close()
    bad: list[str] = []
    for v in vals:
        try:
            json.loads(v)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{v!r}({e})")
            if len(bad) >= 5:
                break
    return len(vals), len(bad), bad


# ---------------------------------------------------------------------------
# C. 时区一致: 逐表按主键抽 头/中/尾 3 行, 比较 MySQL/PG 时间列
# ---------------------------------------------------------------------------


def mysql_time_cols(m_conn, db_name: str, tables: list[str]) -> dict[str, list[tuple[str, str]]]:
    """{table: [(column, mysql_data_type)]}, 仅 datetime/timestamp 列。"""
    cur = m_conn.cursor()
    in_list = ", ".join(["%s"] * len(tables))
    cur.execute(
        f"""SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema=%s AND data_type IN ('datetime','timestamp')
              AND table_name IN ({in_list})
            ORDER BY table_name, ordinal_position""",
        (db_name, *tables),
    )
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for t, c, dt in cur.fetchall():
        out[t].append((c, dt))
    cur.close()
    return dict(out)


def pg_time_col_types(p_conn) -> dict[tuple[str, str], str]:
    cur = p_conn.cursor()
    cur.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema=%s AND data_type IN "
        "('timestamp without time zone','timestamp with time zone')",
        (SCHEMA,),
    )
    out = {(t, c): dt for t, c, dt in cur.fetchall()}
    cur.close()
    return out


def _normalize_time(v):
    """统一成 naive datetime 便于比较。"""
    if isinstance(v, datetime):
        if v.tzinfo is not None:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v.replace(tzinfo=None)
    return v


def timezone_sample_compare(
    m_conn, p_conn, table: str, pk: list[str], time_cols: list[tuple[str, str]], n: int,
    pg_time_types: dict[tuple[str, str], str],
) -> tuple[int, int, list[str]]:
    """按主键抽 头/中/尾 3 行, 比较全部时间列。

    返回 (抽样行数, 比较列数, 失败明细)。MySQL 侧按主键排序取 OFFSET 行,
    再用主键值回查 PG 侧, 规避两侧排序差异选到不同行的问题。
    """
    if n == 0:
        return 0, 0, []
    offsets = sorted({0, n // 2, n - 1})
    order_m = ", ".join(f"`{c}`" for c in pk)
    pk_cond_p = " AND ".join(f"{quote_ident(c)}=%s" for c in pk)
    time_names = [c for c, _ in time_cols]
    m_sel = ", ".join([f"`{c}`" for c in pk] + [f"`{c}`" for c in time_names])
    failures: list[str] = []

    for off in offsets:
        m_cur = m_conn.cursor()
        m_cur.execute(
            f"SELECT {m_sel} FROM `{table}` ORDER BY {order_m} LIMIT 1 OFFSET {int(off)}"
        )
        m_row = m_cur.fetchone()
        m_cur.close()
        if m_row is None:
            failures.append(f"offset {off}: MySQL 侧无行")
            continue
        pk_vals = tuple(m_row[0:len(pk)])
        m_time_vals = m_row[len(pk):]

        # PG 侧时间列: timestamptz 归一化到 UTC 输出
        p_sel_items = []
        for c in time_names:
            ptype = pg_time_types.get((table, c))
            if ptype == "timestamp with time zone":
                p_sel_items.append(f"{quote_ident(c)} AT TIME ZONE 'UTC'")
            else:
                p_sel_items.append(quote_ident(c))
        p_sel = ", ".join(p_sel_items)
        p_cur = p_conn.cursor()
        p_cur.execute(
            f"SELECT {p_sel} FROM {quote_ident(SCHEMA)}.{quote_ident(table)} WHERE {pk_cond_p}",
            pk_vals,
        )
        p_row = p_cur.fetchone()
        p_cur.close()
        if p_row is None:
            failures.append(f"offset {off} 主键 {pk_vals!r}: PG 侧无对应行")
            continue
        for (c, _mtype), mval, pval in zip(time_cols, m_time_vals, p_row):
            if mval is None and pval is None:
                continue
            if mval is None or pval is None:
                failures.append(f"offset {off} 列 `{c}`: NULL 不一致 MySQL={mval!r} PG={pval!r}")
                continue
            m2 = _normalize_time(mval)
            p2 = _normalize_time(pval)
            if m2 != p2:
                failures.append(f"offset {off} 列 `{c}`: 值不一致 MySQL={mval!r} PG={pval!r}")
    return len(offsets), len(time_names), failures


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="P3-E3 迁移后深度校验(FK/JSON/时区, 只读)")
    ap.add_argument("--env", help="MySQL 凭据 .env 文件路径(默认自动查找)")
    ap.add_argument("--bak", help="PG 凭据 .env.bak_a2_20260830 路径(默认自动查找)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    env_path = find_env_file(".env", args.env)
    bak_path = find_env_file(".env.bak_a2_20260830", args.bak)
    if env_path is None or not env_path.exists():
        print("找不到 .env(MySQL 凭据)。可用 --env 指定, 或在仓库根目录运行。", file=sys.stderr)
        return 2
    if bak_path is None or not bak_path.exists():
        print("找不到 .env.bak_a2_20260830(PG 凭据)。可用 --bak 指定。", file=sys.stderr)
        return 2

    mysql_cfg = load_env(env_path, tuple("DB_" + k for k in _KEYS))
    pg_cfg = load_env(bak_path, tuple("ASSETS_DB_" + k for k in _KEYS))

    if not all([mysql_cfg["DB_HOST"], mysql_cfg["DB_USER"], mysql_cfg["DB_PASSWORD"], mysql_cfg["DB_NAME"]]):
        print("MySQL 凭据缺失(DB_HOST/DB_USER/DB_PASSWORD/DB_NAME)。", file=sys.stderr)
        return 2
    if not all([pg_cfg["ASSETS_DB_HOST"], pg_cfg["ASSETS_DB_USER"], pg_cfg["ASSETS_DB_NAME"]]):
        print("PG 凭据缺失(ASSETS_DB_* 来自 .env.bak_a2_20260830)。", file=sys.stderr)
        return 2
    if pg_cfg["ASSETS_DB_USER"] == "grade_school_ro":
        print(
            "错误: 检测到 PG 连接用户是只读 grade_school_ro。"
            "请从 .env.bak_a2_20260830 读取 postgres 超管凭据(或用环境变量 ASSETS_DB_USER=postgres 覆盖)。",
            file=sys.stderr,
        )
        return 2

    try:
        m_conn, p_conn = connect(mysql_cfg, pg_cfg)
    except Exception as e:  # noqa: BLE001
        print(f"数据库连接失败: {e}", file=sys.stderr)
        return 2

    print(f"[env] MySQL {mysql_cfg['DB_HOST']}:{mysql_cfg['DB_PORT'] or 3306}/{mysql_cfg['DB_NAME']} | "
          f"PG {pg_cfg['ASSETS_DB_HOST']}:{pg_cfg['ASSETS_DB_PORT'] or 5432}/{pg_cfg['ASSETS_DB_NAME']}")

    migrated = list_migrated_tables(p_conn)
    migrated_set = set(migrated)
    print(f"[1/6] PG school_mig 表清单: {len(migrated)} 张")

    pks = pg_pks(p_conn, migrated)

    # =====================================================================
    # A. FK 完整性
    # =====================================================================
    print("[2/6] A. FK 完整性(MySQL FK 元数据 → PG school_mig 查孤儿)")
    all_fks = read_mysql_fks(m_conn, mysql_cfg["DB_NAME"])
    in_scope = [f for f in all_fks if f["child"] in migrated_set and f["parent"] in migrated_set]
    skipped = [f for f in all_fks if f not in in_scope]
    print(f"  MySQL FK 约束总数: {len(all_fks)} | 在 school_mig 范围内: {len(in_scope)} "
          f"| 跳过(涉及废弃 4 表): {len(skipped)}")

    fk_fail: list[str] = []
    fk_orphan_total = 0
    for fk in in_scope:
        n = orphan_count(p_conn, fk)
        fk_orphan_total += n
        line = f"  [{'OK  ' if n == 0 else 'FAIL'}] {fk['child']}.{','.join(fk['child_cols'])}"
        line += f" -> {fk['parent']}.{','.join(fk['parent_cols'])} | 孤儿 {n}"
        print(line)
        if n != 0:
            fk_fail.append(fk)
            samples = orphan_samples(p_conn, fk, pks.get(fk["child"], []), limit=5)
            for s in samples:
                print(f"        orphan 样例: {s!r}")

    # =====================================================================
    # B. JSON 合法
    # =====================================================================
    print("[3/6] B. JSON 合法(school_mig jsonb 列抽样反序列化)")
    json_cols = list_jsonb_columns(p_conn)
    print(f"  jsonb 列总数: {len(json_cols)}")
    json_bad_total = 0
    json_sampled_total = 0
    for t, c in json_cols:
        sampled, bad, samples = sample_json_column(p_conn, t, c)
        json_sampled_total += sampled
        json_bad_total += bad
        status = "OK  " if bad == 0 else "FAIL"
        rate = f"{sampled - bad}/{sampled}" if sampled else "0/0"
        print(f"  [{status}] {t}.{c} | 抽样 {rate} 合法")
        for s in samples:
            print(f"       非法 JSON 样例: {s}")

    # =====================================================================
    # C. 时区一致
    # =====================================================================
    print("[4/6] C. 时区一致(含 datetime/timestamp 列的表, 每表抽 3 行比较)")
    m_time = mysql_time_cols(m_conn, mysql_cfg["DB_NAME"], migrated)
    pg_time_types = pg_time_col_types(p_conn)
    tz_tables = [t for t in migrated if t in m_time and m_time[t]]
    tz_fail: list[str] = []
    tz_rows_total = 0
    tz_col_total = 0
    for t in tz_tables:
        time_cols = m_time[t]
        mc = 0
        cur = m_conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM `{t}`")
        mc = int(cur.fetchone()[0])
        cur.close()
        rows, ncols, fails = timezone_sample_compare(
            m_conn, p_conn, t, pks.get(t, []), time_cols, mc, pg_time_types
        )
        tz_rows_total += rows
        tz_col_total += ncols * rows
        status = "OK  " if not fails else "FAIL"
        print(f"  [{status}] {t} | 抽 {rows} 行 × {ncols} 时间列 | rows {mc}")
        for f in fails:
            print(f"        - {f}")
            tz_fail.append(f"{t}: {f}")

    # =====================================================================
    # public 未触碰检查
    # =====================================================================
    print("[5/6] PG public schema 表数(只读, 未触碰)")
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
    public_ok = len(public_non_backup) == EXPECT_PUBLIC_TABLES
    if public_backups:
        print(f"  public 表数: {public_count} (备份表 {len(public_backups)} 张: {sorted(public_backups)})")
    print(f"  public 非备份表数: {len(public_non_backup)} (期望 {EXPECT_PUBLIC_TABLES}) "
          f"[{'OK' if public_ok else 'FAIL'}]")

    m_conn.close()
    p_conn.close()

    # =====================================================================
    # 汇总
    # =====================================================================
    print("[6/6] 汇总")
    fk_ok = not fk_fail
    json_ok = json_bad_total == 0
    tz_ok = not tz_fail
    print(f"  A. FK 完整性: {len(in_scope)} 条, 孤儿总量 {fk_orphan_total} "
          f"[{'PASS' if fk_ok else 'FAIL'}]")
    print(f"  B. JSON 合法: {len(json_cols)} 列, 抽样 {json_sampled_total} 行, "
          f"非法 {json_bad_total} [{'PASS' if json_ok else 'FAIL'}]")
    print(f"  C. 时区一致: {len(tz_tables)} 表, 抽样 {tz_rows_total} 行, 比较 {tz_col_total} 值, "
          f"不一致 {len(tz_fail)} [{'PASS' if tz_ok else 'FAIL'}]")
    print(f"  public 表数: {len(public_non_backup)} 非备份 (共 {public_count}, "
          f"备份 {len(public_backups)}) [{'PASS' if public_ok else 'FAIL'}]")

    if fk_ok and json_ok and tz_ok and public_ok:
        print("\n结果: PASS(E3 三项校验全过, 报告可存档)")
        return 0
    print("\n结果: FAIL(存在差异)", file=sys.stderr)
    if fk_fail:
        print(f"  FK 孤儿非 0: {[f['child'] for f in fk_fail]}", file=sys.stderr)
    if json_bad_total:
        print(f"  非法 JSON: {json_bad_total} 行", file=sys.stderr)
    if tz_fail:
        print(f"  时区不一致: {len(tz_fail)} 处", file=sys.stderr)
    if not public_ok:
        print(f"  public 非备份表数 {len(public_non_backup)} != {EXPECT_PUBLIC_TABLES} "
              f"(共 {public_count}, 备份 {len(public_backups)} 张)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
