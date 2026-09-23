#!/usr/bin/env python3
"""P3-E4: school_mig 影子数据并入 PG public schema(正式落库, PG 统一主库)。

背景:
  E1 scripts/copy_rows.py 已把 MySQL 业务库(63 张, 跳过 4 废弃表)结构+数据复制到
  PG 影子 schema school_mig。E2 scripts/verify_counts.py 对账、E3
  scripts/verify_migration.py 深度校验(FK/JSON/时区)均全 PASS。本脚本(E4)把
  school_mig 影子数据并入 PG public schema, 使 PG 成为统一主库。

三个模式:
  --check    只读前置检查: school_mig 恰好 63 张、public 非备份表恰好
             EXPECT_PUBLIC_TABLES(=142) 张、同名非空壳冲突为 0。非预期即非零
             退出, 不写任何数据。public 实际表数可能因灵犀侧 *_backup_YYYYMMDD
             备份表而 >142, 属预期(校验基线排除此类备份表)。
  --dry-run  只读计划输出: 对 63 张迁移表逐表判定并入方式(CREATE_TABLE /
             EXISTS_EMPTY_FILL / EXISTS_NONEMPTY_ABORT / SKIP_DEPRECATED),
             输出完整计划表与汇总(63 = 建表 N + 空壳填充 M + 跳过 K + ABORT 0)。
             全程只读事务, 脚本末尾对比 public 表数不变验证无真实写入。
  --run      真实并入(逻辑完整): 逐表并入 + 授权 grade_school_ro + 幂等
             (ON CONFLICT DO NOTHING / CREATE TABLE IF NOT EXISTS), 可重复运行。
             并入结果登记 school_mig_meta.merge_done 清单(重跑幂等, 清单外同名非空
             表仍 ABORT)。⚠️ 需 --confirm=yes; 仅在主对话用户确认后由主对话调用。
             本文件验收只允许 --check / --dry-run, 绝不执行真实写入 public。

并入方式判定(逐表, 对 63 张 school_mig 表):
  - CREATE_TABLE          public 无同名 → CREATE TABLE public.x (LIKE school_mig.x
                          INCLUDING ALL) 带索引/约束/默认值 + 全量 INSERT ... SELECT
                          ON CONFLICT (主键) DO NOTHING。
  - EXISTS_EMPTY_FILL     public 已有同名且 0 行(空壳表) → 差异感知合并:
                          ① 列差异分析: public 缺 school_mig 列 → ADD_COLUMN; public
                          独有 NOT NULL 无默认列 → SET_DEFAULT; 公共列类型差异
                          (timestamptz/timestamp、jsonb/json 等) → TYPE_OK, PG 插入
                          自动转换无需 ALTER。
                          ② ALTER 对齐: ADD 缺失列(按 school_mig 类型/可空/默认) +
                          独有列 SET DEFAULT。绝不 DROP, 不触碰既有约束/外键。
                          ③ 显式列映射 INSERT(school_mig 全量列 → public 同名列,
                          public 独有列用默认值, ON CONFLICT (主键) DO NOTHING)。
                          幂等可重跑。
  - EXISTS_NONEMPTY_ABORT public 已有同名且非 0 行(灵犀/资产数据表) → ABORT 报错,
                          绝不覆盖已有数据行。
  - SKIP_DEPRECATED       4 张废弃表(knowledge_points/subject_units/wrong_questions/
                          parent_students) → 跳过(E1 未迁入 school_mig, PG 资产权威)。

安全约定(与 copy_rows/verify_counts/verify_migration 一致):
  - 凭据只从 .env(DB_*)/ .env.bak_a2_20260830(ASSETS_DB_*) 读取(或已有环境变量),
    脚本内无明文密码字面量。
  - PG 连接用户若被污染成只读 grade_school_ro 则 fail-fast(并入 public 需要写权限)。
  - 绝不修改/删除 school_mig 任何数据; 绝不触碰 public 已有数据行。
  - 空壳表 ALTER 只作用于 public 同名 0 行空壳表本身(ADD 列 / 独有列加默认),
    绝不 DROP 重建; 不级联影响灵犀/外部表(parent_wrong_questions / exam_results 等)。
  - public 表数校验排除灵犀侧 *_backup_YYYYMMDD 备份表(如 questions_chid_safe_backup_
    20260830)。实际 public 表数可能因备份表而 > EXPECT_PUBLIC_TABLES, 属预期;
    E4 本身不应建/删任何 *_backup_* 表。
  - 空壳表填充按 public FK 依赖拓扑排序(被引用表先填), 保证 exams 先于 exam_scores。
  - --run 只在主对话用户确认后调用; 验收只用 --check/--dry-run。
  - 不新增依赖: 仅 psycopg2 + PyMySQL + python-dotenv。
  - UTF-8 输出(Windows 管道防乱码)。

用法:
  python scripts/merge_to_public.py --check
  python scripts/merge_to_public.py --dry-run
  python scripts/merge_to_public.py --run --confirm=yes      # 用户确认后执行
  python scripts/merge_to_public.py --verify-public          # 并入后最终对账(MySQL vs public)

退出码:
  0 通过 / 计划就绪 / 对账全 PASS
  1 存在差异/冲突/错误
  2 配置/连接错误
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import pymysql
    import psycopg2
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover
    print("缺少依赖: pip install pymysql psycopg2-binary python-dotenv", file=sys.stderr)
    sys.exit(1)

SCHEMA_MIG = "school_mig"
SCHEMA_PUB = "public"
SCHEMA_META = "school_mig_meta"  # E4 专属 bookkeeping schema(不入 public/school_mig)
# 4 张废弃表: MySQL 0 行, PG 资产权威, E1 跳过迁移, E4 不并入
SKIP_TABLES = {"knowledge_points", "subject_units", "wrong_questions", "parent_students"}
EXPECT_MIG_TABLES = 63
# 非备份表基线(public 实际表数可能因灵犀 *_backup_* 备份表而 > 此值, 属预期)。
# 当前 147 张 = 142 非备份 + 5 张备份(knowledge_points_chid_backup_20260829 /
# question_kp_chid_backup_20260829 / question_kp_chid_remount_backup_20260830 /
# questions_chid_safe_backup_20260830 / questions_difficulty_backup_20260830)。
EXPECT_PUBLIC_TABLES = 142
# 灵犀 CC 备份表命名模式(*_backup_YYYYMMDD): 不在迁移 63 表范围, 校验基线应排除。
BACKUP_TABLE_RE = re.compile(r"_backup_\d{8}$")
READONLY_USER = "grade_school_ro"
_KEYS = ("HOST", "PORT", "USER", "PASSWORD", "NAME")


def is_backup_table(name: str) -> bool:
    """是否灵犀侧 *_backup_YYYYMMDD 备份表(public 表数校验应排除)。"""
    return bool(BACKUP_TABLE_RE.search(name))


def _force_utf8_stdio() -> None:
    """强制 stdout/stderr 使用 UTF-8(避免 Windows 管道被 locale 编码成 GBK 乱码)。"""
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
    """定位 env 文件: 显式参数 > cwd > scripts/ 上级 > 沿目录树向上查找。

    兼容主仓库根运行与隔离 worktree 运行。
    """
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
    """从 env 文件读取指定 key; 文件优先, 缺失时回退环境变量。

    文件优先是为防止外部 shell 已 source 过 .env 导致 ASSETS_DB_USER 被
    污染成只读 grade_school_ro。
    """
    raw: dict[str, str] = {}
    if path and path.exists():
        raw = {k: v for k, v in dotenv_values(path).items() if v is not None}
    out: dict[str, str] = {}
    for k in keys:
        out[k] = (raw.get(k) or os.environ.get(k) or "").strip()
    return out


# ---------------------------------------------------------------------------
# PG 元数据(只读 information_schema)
# ---------------------------------------------------------------------------


def q(name: str) -> str:
    """双引号标识符并转义内部双引号(元数据来自 information_schema, 仍防御性转义)。"""
    return '"' + name.replace('"', '""') + '"'


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


def count_schema_tables(p_conn, schema: str) -> int:
    cur = p_conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema=%s AND table_type='BASE TABLE'",
        (schema,),
    )
    n = int(cur.fetchone()[0])
    cur.close()
    return n


def count_rows(p_conn, schema: str, table: str) -> int:
    cur = p_conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {q(schema)}.{q(table)}")
    n = int(cur.fetchone()[0])
    cur.close()
    return n


def table_exists(p_conn, schema: str, table: str) -> bool:
    cur = p_conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name=%s AND table_type='BASE TABLE'",
        (schema, table),
    )
    n = int(cur.fetchone()[0])
    cur.close()
    return n > 0


def schema_cols(p_conn, schema: str, table: str) -> list[str]:
    cur = p_conn.cursor()
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (schema, table),
    )
    cols = [r[0] for r in cur.fetchall()]
    cur.close()
    return cols


def schema_cols_info(p_conn, schema: str, table: str) -> list[dict]:
    """列元数据: name/data_type/is_nullable/column_default/char_len/num_prec/num_scale。"""
    cur = p_conn.cursor()
    cur.execute(
        "SELECT column_name, data_type, is_nullable, column_default, "
        "character_maximum_length, numeric_precision, numeric_scale "
        "FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
        (schema, table),
    )
    cols = []
    for r in cur.fetchall():
        cols.append({
            "name": r[0], "data_type": r[1], "is_nullable": r[2],
            "column_default": r[3], "char_len": r[4],
            "num_prec": r[5], "num_scale": r[6],
        })
    cur.close()
    return cols


def pg_pk_of(p_conn, schema: str, table: str) -> list[str]:
    cur = p_conn.cursor()
    cur.execute(
        """SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
           WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=%s
             AND tc.table_name=%s
           ORDER BY kcu.ordinal_position""",
        (schema, table),
    )
    pk = [r[0] for r in cur.fetchall()]
    cur.close()
    return pk


def _col_type_ddl(info: dict) -> str:
    """由 information_schema 列元数据构造 ALTER ADD COLUMN 的类型片段。"""
    t = info["data_type"]
    if t == "character varying":
        return f"character varying({info['char_len']})" if info["char_len"] else "character varying"
    if t == "character":
        return f"character({info['char_len']})" if info["char_len"] else "character"
    if t == "numeric":
        if info["num_prec"] is not None:
            return f"numeric({info['num_prec']},{info['num_scale']})"
        return "numeric"
    if t in (
        "text", "integer", "bigint", "smallint", "boolean", "json", "jsonb",
        "double precision", "real", "date", "uuid", "bytea", "interval",
        "timestamp without time zone", "timestamp with time zone",
        "time without time zone", "time with time zone", "inet",
    ):
        return t
    return t  # 罕见类型兜底: 原样 data_type


def _default_literal(info: dict) -> str:
    """为 public 独有 NOT NULL 无默认列构造安全默认值字面量(避免阻塞空壳填充)。"""
    t = info["data_type"]
    if t in ("character varying", "character", "text"):
        return "''"
    if t in ("integer", "bigint", "smallint", "numeric", "double precision", "real"):
        return "0"
    if t == "boolean":
        return "false"
    if t == "date":
        return "CURRENT_DATE"
    if t in ("timestamp without time zone", "timestamp with time zone"):
        return "CURRENT_TIMESTAMP"
    if t in ("json", "jsonb"):
        return f"'{{}}'::{t}"
    raise ValueError(f"无法为 public 独有列自动生成默认值: {info['name']} ({t})")


def shell_diff(p_conn, table: str) -> dict:
    """空壳表两侧列差异明细(差异感知合并数据源, 只读)。

    返回:
      add_cols:     [(col, ddl), ...] public 缺 school_mig 列 → ALTER ADD COLUMN
      set_defaults: [(col, lit), ...] public 独有 NOT NULL 无默认列 → ALTER SET DEFAULT
      insert_cols:  [col, ...]        school_mig 全量列(显式列映射; ALTER 后 public 全具备)
      type_ok:      [(col, pub_t, mig_t), ...] 公共列类型差异(timestamptz/timestamp、
                    jsonb/json 等, PG 插入自动转换, 无需 ALTER)
      only_pub_null: [col, ...]       public 独有可空列(不阻塞, 用 NULL)
    """
    pub = schema_cols_info(p_conn, SCHEMA_PUB, table)
    mig = schema_cols_info(p_conn, SCHEMA_MIG, table)
    pub_by = {c["name"]: c for c in pub}
    mig_by = {c["name"]: c for c in mig}

    add_cols: list[tuple[str, str]] = []
    for c in mig:
        if c["name"] in pub_by:
            continue
        ddl = _col_type_ddl(c)
        if c["is_nullable"] == "NO":
            ddl += " NOT NULL"
        if c["column_default"]:
            ddl += f" DEFAULT {c['column_default']}"
        add_cols.append((c["name"], ddl))

    set_defaults: list[tuple[str, str]] = []
    only_pub_null: list[str] = []
    for c in pub:
        if c["name"] in mig_by:
            continue
        if c["is_nullable"] == "NO" and c["column_default"] is None:
            set_defaults.append((c["name"], _default_literal(c)))
        else:
            only_pub_null.append(c["name"])

    type_ok: list[tuple[str, str, str]] = []
    for c in mig:
        pc = pub_by.get(c["name"])
        if pc and pc["data_type"] != c["data_type"]:
            type_ok.append((c["name"], pc["data_type"], c["data_type"]))

    return {
        "add_cols": add_cols,
        "set_defaults": set_defaults,
        "insert_cols": [c["name"] for c in mig],
        "type_ok": type_ok,
        "only_pub_null": only_pub_null,
    }


def merge_order(p_conn, tables: list[str]) -> list[str]:
    """按 public/school_mig FK 依赖拓扑排序(被引用表先填), 独立表按字母序; 遇环回退。

    空壳表填充需满足 FK 顺序(如 exam_scores.exam_id → exams.id, 必须先填 exams)。
    同时读 public 与 school_mig 的 FK(建表表结构 LIKE 自 school_mig, 其 FK 也会被复制)。
    """
    tset = set(tables)
    if len(tset) < 2:
        return list(tables)
    depends_on: dict[str, list[str]] = {t: [] for t in tset}
    cur = p_conn.cursor()
    edges: set[tuple[str, str]] = set()
    for schema in (SCHEMA_PUB, SCHEMA_MIG):
        cur.execute(
            """SELECT ccu.table_name AS referenced, tc.table_name AS referencing
                 FROM information_schema.table_constraints tc
                 JOIN information_schema.key_column_usage kcu
                   ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                 JOIN information_schema.constraint_column_usage ccu
                   ON tc.constraint_name = ccu.constraint_name
                  AND tc.table_schema = ccu.table_schema
                WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema=%s
                  AND tc.table_name = ANY(%s) AND ccu.table_name = ANY(%s)""",
            (schema, list(tset), list(tset)),
        )
        edges.update(cur.fetchall())
    cur.close()
    for referenced, referencing in edges:
        if referenced in tset and referencing in tset and referenced != referencing:
            depends_on[referencing].append(referenced)

    ordered: list[str] = []
    state: dict[str, int] = {}
    cyclic = False

    def visit(t: str) -> None:
        nonlocal cyclic
        st = state.get(t, 0)
        if st == 2:
            return
        if st == 1:
            cyclic = True
            return
        state[t] = 1
        for d in sorted(depends_on[t]):
            visit(d)
        state[t] = 2
        ordered.append(t)

    for t in sorted(tset):
        visit(t)
    return sorted(tables) if cyclic else ordered


def classify(p_conn, table: str) -> tuple[str, dict | None]:
    """逐表判定并入方式。返回 (mode, detail)。

    mode: CREATE_TABLE / EXISTS_EMPTY_FILL / EXISTS_NONEMPTY_ABORT / SKIP_DEPRECATED
    """
    if table in SKIP_TABLES:
        return "SKIP_DEPRECATED", {"note": "废弃表, PG 资产权威"}
    if not table_exists(p_conn, SCHEMA_PUB, table):
        return "CREATE_TABLE", {}
    n = count_rows(p_conn, SCHEMA_PUB, table)
    if n == 0:
        return "EXISTS_EMPTY_FILL", {"public_rows": n}
    return "EXISTS_NONEMPTY_ABORT", {"public_rows": n}


# ---------------------------------------------------------------------------
# --run 并入动作(真实写入 public; 仅主对话确认后调用)
# ---------------------------------------------------------------------------


def copy_rows(p_conn, table: str, cols: list[str]) -> None:
    """INSERT INTO public.table (cols) SELECT cols FROM school_mig.table
    ON CONFLICT (主键) DO NOTHING。幂等, 可重复运行。"""
    if not cols:
        raise ValueError(f"列交集为空, 无法填充 {table}")
    col_sql = ", ".join(q(c) for c in cols)
    pk = pg_pk_of(p_conn, SCHEMA_PUB, table)
    if pk:
        pk_sql = ", ".join(q(c) for c in pk)
        sql = (
            f"INSERT INTO {q(SCHEMA_PUB)}.{q(table)} ({col_sql}) "
            f"SELECT {col_sql} FROM {q(SCHEMA_MIG)}.{q(table)} "
            f"ON CONFLICT ({pk_sql}) DO NOTHING"
        )
    else:
        sql = (
            f"INSERT INTO {q(SCHEMA_PUB)}.{q(table)} ({col_sql}) "
            f"SELECT {col_sql} FROM {q(SCHEMA_MIG)}.{q(table)} "
            f"ON CONFLICT DO NOTHING"
        )
    cur = p_conn.cursor()
    cur.execute(sql)
    cur.close()


def create_and_copy(p_conn, table: str) -> None:
    """CREATE_TABLE 方式: 用 school_mig 结构建 public 表(LIKE INCLUDING ALL
    带索引/约束/默认值) + 全量插入。"""
    cur = p_conn.cursor()
    cur.execute(
        f"CREATE TABLE IF NOT EXISTS {q(SCHEMA_PUB)}.{q(table)} "
        f"(LIKE {q(SCHEMA_MIG)}.{q(table)} INCLUDING ALL)"
    )
    cur.close()
    copy_rows(p_conn, table, schema_cols(p_conn, SCHEMA_MIG, table))


def _alter_shell(p_conn, table: str, rep: dict) -> None:
    """空壳表 ALTER 对齐(幂等): ADD 缺失列 + 独有列 SET DEFAULT。绝不 DROP。"""
    cur = p_conn.cursor()
    for col, ddl in rep["add_cols"]:
        cur.execute(
            f"ALTER TABLE {q(SCHEMA_PUB)}.{q(table)} ADD COLUMN IF NOT EXISTS {q(col)} {ddl}"
        )
    for col, lit in rep["set_defaults"]:
        cur.execute(
            f"ALTER TABLE {q(SCHEMA_PUB)}.{q(table)} ALTER COLUMN {q(col)} SET DEFAULT {lit}"
        )
    cur.close()


def fill_shell(p_conn, table: str) -> dict:
    """EXISTS_EMPTY_FILL 方式: 差异感知合并(ALTER 对齐 + 显式列映射填充)。

    返回 shell_diff 明细(供 --run 打印 ADD_COLUMN/SET_DEFAULT 等变更)。
    """
    rep = shell_diff(p_conn, table)
    _alter_shell(p_conn, table, rep)
    copy_rows(p_conn, table, rep["insert_cols"])
    return rep


def grant_readonly(p_conn, tables: list[str], ro_user: str) -> None:
    """给 grade_school_ro 授权: public schema USAGE + 各并入表 SELECT +
    默认权限(保证后续重跑新建的表也可读)。幂等。"""
    cur = p_conn.cursor()
    cur.execute(f"GRANT USAGE ON SCHEMA {q(SCHEMA_PUB)} TO {q(ro_user)}")
    for t in tables:
        cur.execute(f"GRANT SELECT ON {q(SCHEMA_PUB)}.{q(t)} TO {q(ro_user)}")
    cur.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {q(SCHEMA_PUB)} "
        f"GRANT SELECT ON TABLES TO {q(ro_user)}"
    )
    cur.close()


def _ensure_manifest(p_conn) -> None:
    """建 school_mig_meta.merge_done 清单表(记录已并入 public 的表与方式, 供重跑幂等)。"""
    cur = p_conn.cursor()
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {q(SCHEMA_META)}")
    cur.execute(
        f"CREATE TABLE IF NOT EXISTS {q(SCHEMA_META)}.merge_done ("
        "table_name text PRIMARY KEY, "
        "mode text NOT NULL, "
        "merged_at timestamptz NOT NULL DEFAULT now())"
    )
    cur.close()


def _read_manifest(p_conn) -> dict[str, str]:
    """读取已并入清单 {table: mode}。清单表不存在时视为空(首次运行)。"""
    cur = p_conn.cursor()
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name='merge_done'",
        (SCHEMA_META,),
    )
    if not cur.fetchone():
        cur.close()
        return {}
    cur.execute(f"SELECT table_name, mode FROM {q(SCHEMA_META)}.merge_done")
    out = {r[0]: r[1] for r in cur.fetchall()}
    cur.close()
    return out


def _manifest_add(p_conn, table: str, mode: str) -> None:
    """登记并入完成; ON CONFLICT DO NOTHING 幂等。"""
    cur = p_conn.cursor()
    cur.execute(
        f"INSERT INTO {q(SCHEMA_META)}.merge_done (table_name, mode) VALUES (%s, %s) "
        "ON CONFLICT (table_name) DO NOTHING",
        (table, mode),
    )
    cur.close()


# ---------------------------------------------------------------------------
# 三个模式
# ---------------------------------------------------------------------------


def run_check(p_conn) -> int:
    """--check: 只读前置检查, 非预期即非零退出。"""
    ok = True
    mig = list_tables(p_conn, SCHEMA_MIG)
    print(f"[check] school_mig 表数: {len(mig)} (期望 {EXPECT_MIG_TABLES})")
    if len(mig) != EXPECT_MIG_TABLES:
        ok = False
        print(f"  [FAIL] 期望 {EXPECT_MIG_TABLES} 张, 实际 {len(mig)}")
    dep_present = [t for t in sorted(SKIP_TABLES) if t in mig]
    if dep_present:
        ok = False
        print(f"  [FAIL] 废弃表不应出现在 school_mig: {dep_present}")
    else:
        print(f"  [OK]   废弃表不在 school_mig(E1 已跳过): {sorted(SKIP_TABLES)}")

    pub_all = list_tables(p_conn, SCHEMA_PUB)
    pub = [t for t in pub_all if not is_backup_table(t)]
    n_backup = len(pub_all) - len(pub)
    print(f"[check] public 表数: {len(pub)} (期望 {EXPECT_PUBLIC_TABLES} 非备份表; "
          f"实际 {len(pub_all)} 张, 排除灵犀 *_backup_* 备份表 {n_backup} 张)")
    if len(pub) != EXPECT_PUBLIC_TABLES:
        ok = False
        print(f"  [FAIL] 期望 {EXPECT_PUBLIC_TABLES} 张非备份表, 实际 {len(pub)}")

    conflicts: list[tuple[str, int]] = []
    empties: list[str] = []
    for t in mig:
        mode, detail = classify(p_conn, t)
        if mode == "EXISTS_NONEMPTY_ABORT":
            conflicts.append((t, detail["public_rows"]))
        elif mode == "EXISTS_EMPTY_FILL":
            empties.append(t)
    print(f"[check] 同名非空壳冲突(须为 0): {len(conflicts)}")
    for t, n in conflicts:
        ok = False
        print(f"  [FAIL] {t}: public 已有 {n} 行, 需 ABORT 绝不覆盖")
    print(f"[check] 同名空壳表(0 行, 待填充): {len(empties)}")
    need_alter = [
        t for t in empties
        if shell_diff(p_conn, t)["add_cols"] or shell_diff(p_conn, t)["set_defaults"]
    ]
    if need_alter:
        print(f"[check] 空壳表需结构对齐(--run 自动 ALTER, 不阻塞): "
              f"{len(need_alter)} 张 {need_alter}")
    else:
        print(f"[check] 空壳表结构已对齐(无需 ALTER)")
    print(f"[check] 可建表(public 无同名): {len(mig) - len(conflicts) - len(empties)}")
    print(f"[check] public 表数现状 {len(pub)}; 并入后将为 {len(pub) + (len(mig) - len(empties))}"
          f"(新增 {len(mig) - len(empties)} 张建表)")
    if not ok:
        print("\n结果: FAIL(--check 存在非预期项, 请先处置)", file=sys.stderr)
        return 1
    print("\n结果: PASS(--check 前置条件满足, 可进行 --dry-run)")
    return 0


def run_dry_run(p_conn) -> int:
    """--dry-run: 只读计划输出, 不写任何数据(只读事务 + 前后 public 表数对比)。"""
    pub_before = count_schema_tables(p_conn, SCHEMA_PUB)
    mig = list_tables(p_conn, SCHEMA_MIG)
    counts: dict[str, list[str]] = {
        "CREATE_TABLE": [], "EXISTS_EMPTY_FILL": [], "EXISTS_NONEMPTY_ABORT": [], "SKIP_DEPRECATED": [],
    }
    print(f"===== 并入计划(school_mig -> public) 共 {len(mig)} 张迁移表(FK 依赖序) =====")
    for t in merge_order(p_conn, mig):
        mode, detail = classify(p_conn, t)
        counts[mode].append(t)
        if mode == "CREATE_TABLE":
            pk = pg_pk_of(p_conn, SCHEMA_MIG, t)
            n = count_rows(p_conn, SCHEMA_MIG, t)
            print(f"  [CREATE_TABLE]       {t:34s} | school_mig {n:>7d} 行 | PK {','.join(pk)}")
        elif mode == "EXISTS_EMPTY_FILL":
            rep = shell_diff(p_conn, t)
            n = count_rows(p_conn, SCHEMA_MIG, t)
            print(f"  [EXISTS_EMPTY_FILL]  {t:34s} | school_mig {n:>7d} 行 | 插入 {len(rep['insert_cols'])} 列")
            if rep["add_cols"]:
                cols = ", ".join(f"{c}({ddl})" for c, ddl in rep["add_cols"])
                print(f"        ADD_COLUMN:   {cols}")
            else:
                print(f"        ADD_COLUMN:   无(public 已含全部 school_mig 列)")
            if rep["set_defaults"]:
                cols = ", ".join(f"{c} DEFAULT {lit}" for c, lit in rep["set_defaults"])
                print(f"        SET_DEFAULT:  {cols}")
            else:
                print(f"        SET_DEFAULT:  无")
            if rep["type_ok"]:
                typs = ", ".join(f"{c}({mt}->{pt})" for c, pt, mt in rep["type_ok"])
                print(f"        TYPE_OK:      {typs}")
            if rep["only_pub_null"]:
                print(f"        ONLY_PUB:     {', '.join(rep['only_pub_null'])}")
        elif mode == "EXISTS_NONEMPTY_ABORT":
            print(f"  [ABORT]              {t:34s} | public 已有 {detail['public_rows']} 行, 绝不覆盖")
        else:
            print(f"  [SKIP_DEPRECATED]    {t:34s} | 废弃表跳过")

    # 4 张废弃表不在 school_mig(E1 已跳过), 单列说明
    for t in sorted(SKIP_TABLES):
        if t not in mig:
            print(f"  [SKIP_DEPRECATED]    {t:34s} | 不在 school_mig, 废弃表跳过(PG 资产权威)")

    n_create = len(counts["CREATE_TABLE"])
    n_fill = len(counts["EXISTS_EMPTY_FILL"])
    n_abort = len(counts["EXISTS_NONEMPTY_ABORT"])
    n_skip = len(counts["SKIP_DEPRECATED"])
    print("----- 汇总 -----")
    print(f"  63 = 建表 {n_create} + 空壳填充 {n_fill} + 跳过 {n_skip} + ABORT {n_abort}")
    print(f"  其中跳过 {n_skip} 为 school_mig 内含废弃表数(当前 {n_skip}); "
          f"另有 {len(SKIP_TABLES)} 张废弃表不在 school_mig, 直接跳过不并入")
    if n_fill:
        altered = [
            t for t in counts["EXISTS_EMPTY_FILL"]
            if shell_diff(p_conn, t)["add_cols"] or shell_diff(p_conn, t)["set_defaults"]
        ]
        if altered:
            print(f"  [注意] 空壳填充中 {len(altered)} 张需 ALTER 结构对齐"
                  f"(ADD_COLUMN/SET_DEFAULT, 自动处理): {altered}")

    # 无真实写入验证: 只读事务内 public 表数应与进入时一致
    pub_after = count_schema_tables(p_conn, SCHEMA_PUB)
    if pub_after != pub_before:
        print(f"  [FAIL] public 表数发生变化 {pub_before} -> {pub_after}(dry-run 不应写任何数据)",
              file=sys.stderr)
        return 1
    print(f"  public 表数快照: 进入 {pub_before} -> 结束 {pub_after}(不变, 无真实写入)")

    if n_abort > 0:
        print(f"\n结果: FAIL(存在 {n_abort} 张 ABORT 表, 不能安全并入)", file=sys.stderr)
        return 1
    print(f"\n结果: PASS(并入计划完整, 63 表全覆盖, ABORT 0, 无任何真实写入)")
    return 0


def run_merge(p_conn, confirm: bool) -> int:
    """--run: 真实并入 public(逻辑完整, 仅主对话确认后调用)。

    幂等/可重复运行:
      - 首次运行: 逐表按 classify 判定并入, 完成后登记 school_mig_meta.merge_done。
      - 重复运行(全量或中断恢复): 已在清单中的表按记录方式重放(ON CONFLICT DO
        NOTHING / CREATE TABLE IF NOT EXISTS 均幂等, 无重复无报错), 未在清单中的
        表按当前状态并入。清单外同名非空表(灵犀/资产)依旧 ABORT, 绝不覆盖。
    """
    if not confirm:
        print("错误: --run 会真实写入 public。请在主对话用户确认后使用 --run --confirm=yes。",
              file=sys.stderr)
        return 1

    _ensure_manifest(p_conn)
    manifest = _read_manifest(p_conn)
    mig = list_tables(p_conn, SCHEMA_MIG)

    # 首次判定 + ABORT 门控(清单外同名非空表 = 灵犀/资产, 绝不覆盖)
    plan: dict[str, str] = {}
    aborts: list[str] = []
    for t in mig:
        mode, detail = classify(p_conn, t)
        if mode == "EXISTS_NONEMPTY_ABORT" and t not in manifest:
            aborts.append(f"{t}(public {detail['public_rows']} 行)")
            continue
        # 已在清单中的表: 用记录方式重放(幂等); 其余按当前状态
        plan[t] = manifest.get(t, mode)
    if aborts:
        for a in aborts:
            print(f"  [ABORT] {a}: public 已有数据且不在并入清单, 绝不覆盖。请先处置。", file=sys.stderr)
        print(f"结果: FAIL({len(aborts)} 张 ABORT 表, 终止并入)", file=sys.stderr)
        return 1

    print(f"===== 并入执行(school_mig -> public) 共 {len(mig)} 张(FK 依赖序) =====")
    failures: list[str] = []
    created: list[str] = []
    filled: list[str] = []
    for t in merge_order(p_conn, mig):
        mode = plan[t]
        try:
            if mode == "CREATE_TABLE":
                n_src = count_rows(p_conn, SCHEMA_MIG, t)
                if table_exists(p_conn, SCHEMA_PUB, t):
                    # 重复运行: 表已存在, 直接幂等重放 INSERT(结构为 LIKE 同构)
                    copy_rows(p_conn, t, schema_cols(p_conn, SCHEMA_MIG, t))
                    print(f"  [CREATE_TABLE] {t}: 表已存在, 幂等重放 {n_src} 行(无重复)")
                else:
                    create_and_copy(p_conn, t)
                    print(f"  [CREATE_TABLE] {t}: 建表+插入 {n_src} 行")
                created.append(t)
            elif mode == "EXISTS_EMPTY_FILL":
                n_src = count_rows(p_conn, SCHEMA_MIG, t)
                rep = fill_shell(p_conn, t)
                filled.append(t)
                changes = []
                if rep["add_cols"]:
                    changes.append(f"ADD_COLUMN {len(rep['add_cols'])}")
                if rep["set_defaults"]:
                    changes.append(f"SET_DEFAULT {len(rep['set_defaults'])}")
                extra = ", ".join(changes) if changes else "结构一致"
                print(f"  [EXISTS_EMPTY_FILL] {t}: 填充 {n_src} 行 | {extra}")
            elif mode == "SKIP_DEPRECATED":
                print(f"  [SKIP_DEPRECATED]   {t}: 废弃表跳过")
            else:
                print(f"  [SKIP] {t}")
            _manifest_add(p_conn, t, mode)
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {t}: {e}", file=sys.stderr)
            failures.append(t)

    # 授权只读用户(对已成功并入的表; 幂等)
    try:
        grant_readonly(p_conn, created + filled, READONLY_USER)
        print(f"[grant] 已授权 {READONLY_USER}: public USAGE + "
              f"{len(created + filled)} 张并入表 SELECT + 默认权限")
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] GRANT 失败(不影响数据): {e}", file=sys.stderr)

    print("----- 汇总 -----")
    print(f"  建表 {len(created)} / 空壳填充 {len(filled)} / 失败 {len(failures)}")
    if failures:
        print(f"  失败表: {failures}", file=sys.stderr)
        print("\n结果: FAIL(部分表并入失败, 请见上方明细)", file=sys.stderr)
        return 1

    print("\n结果: PASS(63 表全部并入 public)")
    print("下一步(最终对账, 由主对话执行):")
    print("  python scripts/verify_counts.py --schema public   # MySQL vs public 对账")
    print("  python scripts/verify_migration.py                # FK/JSON/时区深度校验")
    return 0


def run_verify_public(p_conn) -> int:
    """--verify-public: 并入后快速对账(只读)。

    逐表比较 school_mig vs public 行数(校验并入完整性), 列对齐差异提示走权威
    verify_counts --schema public 复核。不对 public 做任何写入。
    """
    mig = list_tables(p_conn, SCHEMA_MIG)
    print(f"===== 并入后快速对账(school_mig vs public) 共 {len(mig)} 张 =====")
    fails: list[str] = []
    total_diff = 0
    for t in sorted(mig):
        if not table_exists(p_conn, SCHEMA_PUB, t):
            print(f"  [FAIL] {t}: public 中不存在(未并入)")
            fails.append(t)
            continue
        m = count_rows(p_conn, SCHEMA_MIG, t)
        p = count_rows(p_conn, SCHEMA_PUB, t)
        diff = m - p
        total_diff += abs(diff)
        status = "OK  " if diff == 0 else "FAIL"
        print(f"  [{status}] {t}: school_mig {m} -> public {p} diff {diff}")
        if diff != 0:
            fails.append(f"{t}({m}->{p})")
    print(f"汇总: {len(mig) - len(fails)}/{len(mig)} 行数一致, 差异总量 {total_diff}")
    if fails:
        print(f"行数不一致表: {fails}", file=sys.stderr)
        print("\n结果: FAIL(--verify-public 行数差异非 0)", file=sys.stderr)
        return 1
    print("\n结果: PASS(行数全 0 差异, 并入完整性 OK)")
    print("权威对账(含列对齐/主键/sample, 需 MySQL):")
    print("  python scripts/verify_counts.py --schema public")
    return 0


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="P3-E4: school_mig 影子数据并入 PG public(只读验收/真实并入)")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--check", action="store_true", help="只读前置检查(school_mig 63 / public 145 / 冲突 0)")
    grp.add_argument("--dry-run", action="store_true", help="只读计划输出, 不写任何数据")
    grp.add_argument("--run", action="store_true", help="真实并入 public(需 --confirm=yes, 主对话确认后调用)")
    grp.add_argument("--verify-public", action="store_true", help="并入后最终对账(轻量, 指引走 verify_counts)")
    ap.add_argument("--confirm", default="no", help="--run 确认开关(传 yes 才执行真实写入)")
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
        print("找不到 .env.bak_a2_20260830(PG 超管凭据)。可用 --bak 指定。", file=sys.stderr)
        return 2

    mysql_cfg = load_env(env_path, tuple("DB_" + k for k in _KEYS))
    pg_cfg = load_env(bak_path, tuple("ASSETS_DB_" + k for k in _KEYS))

    if not all([mysql_cfg["DB_HOST"], mysql_cfg["DB_USER"], mysql_cfg["DB_PASSWORD"], mysql_cfg["DB_NAME"]]):
        print("MySQL 凭据缺失(DB_HOST/DB_USER/DB_PASSWORD/DB_NAME)。", file=sys.stderr)
        return 2
    if not all([pg_cfg["ASSETS_DB_HOST"], pg_cfg["ASSETS_DB_USER"], pg_cfg["ASSETS_DB_NAME"]]):
        print("PG 凭据缺失(ASSETS_DB_* 来自 .env.bak_a2_20260830)。", file=sys.stderr)
        return 2
    if pg_cfg["ASSETS_DB_USER"] == READONLY_USER:
        print(
            "错误: 检测到 PG 连接用户是只读 grade_school_ro, 并入 public 需要写权限。"
            "请从 .env.bak_a2_20260830 读取 postgres 超管凭据(或用环境变量 ASSETS_DB_USER=postgres 覆盖)。",
            file=sys.stderr,
        )
        return 2

    # ---- 连接 ----
    try:
        p_conn = psycopg2.connect(
            host=pg_cfg["ASSETS_DB_HOST"],
            port=int(pg_cfg["ASSETS_DB_PORT"] or 5432),
            user=pg_cfg["ASSETS_DB_USER"],
            password=pg_cfg["ASSETS_DB_PASSWORD"],
            dbname=pg_cfg["ASSETS_DB_NAME"],
        )
        p_conn.autocommit = True
        if args.check or args.dry_run or args.verify_public:
            # 只读快照: 整脚本只见一致视图, 且任何误写会直接报错
            try:
                cur = p_conn.cursor()
                cur.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
                cur.close()
            except Exception:  # noqa: BLE001 已 autocommit, 兼容无法显式 BEGIN 的环境
                pass
    except Exception as e:  # noqa: BLE001
        print(f"PG 连接失败: {e}", file=sys.stderr)
        return 2

    print(f"[env] PG {pg_cfg['ASSETS_DB_HOST']}:{pg_cfg['ASSETS_DB_PORT'] or 5432}/{pg_cfg['ASSETS_DB_NAME']} "
          f"as {pg_cfg['ASSETS_DB_USER']}")

    try:
        if args.check:
            rc = run_check(p_conn)
        elif args.dry_run:
            rc = run_dry_run(p_conn)
        elif args.verify_public:
            rc = run_verify_public(p_conn)
        else:
            rc = run_merge(p_conn, args.confirm == "yes")
    finally:
        p_conn.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
