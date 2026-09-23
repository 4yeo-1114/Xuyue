# -*- coding: utf-8 -*-
"""R6a 错题→知识点桥接回填脚本（wrong_question_kp_bridge）。

把 student_wrong_questions 历史错题的 question_title 跨库匹配到 PG 资产库知识点
（家长端 questions.knowledge_point / knowledge_points.name），命中结果写入主 MySQL
桥表，供 R6b/c 端点消费。PG 只读，跨库匹配全部在 Python 侧完成，不做跨库 SQL。

@MySQL-only：含 ON DUPLICATE KEY UPDATE / NOW() 方言，P3 PG 统一后不适用，归档保留。

匹配策略（按序尝试，记录 match_method，失败不写桥表——诚实）：
  1. question_exact      标题与 PG 题目文本逐字相等 → 取该题 knowledge_point
  2. question_includes   标题出现在题目文本内 → 对同题知识点做聚合投票
                         （支持度 ≥3 且头部占比 ≥0.4 才采信，避免首条噪声）
  3. kp_exact            标题与知识点名称逐字相等
  4. kp_includes         知识点名 ⊆ 标题（优先），或标题 ⊆ 知识点名
  5. kp_keyword          标题 2/3 字切分 + 知识点名包含命中（兜底弱信号）

幂等：写桥表用 ON DUPLICATE KEY UPDATE，可重复运行不报错、不重复插行。

用法：
  python scripts/backfill_wrong_question_kp.py                      # 全量
  python scripts/backfill_wrong_question_kp.py --limit 5 --dry-run  # 小样本只读
  python scripts/backfill_wrong_question_kp.py --subjects 数学,语文  # 限定学科
  python scripts/backfill_wrong_question_kp.py --dry-run            # 只出报告不落库
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text  # noqa: E402

from app.assets.database import assets_engine  # noqa: E402
from app.database import engine  # noqa: E402

# 导入幂等建表函数（仅写模式调用；dry-run 保持纯只读）
from app.database import _ensure_wrong_question_kp_bridge_table  # noqa: E402

# 洗牌辅助：去空格 / 全角空白 / 标点，统一小写（中文不受影响）
_PUNCT_RE = re.compile(r"[，。！？、；：,.!?;:\"'（）()\[\]【】《》〈〉<>「」『』~～·\-—_/\\|]")

# 题库「标签段」前缀：这类 knowledge_point 段描述题型/考点，不是知识点，进 kp 池只会引入噪声
_LABEL_PREFIXES = ("题型", "考点", "经典题", "易错题")

# question_includes 聚合投票的 lift 下限：头部 kp 在匹配题中的占比 ÷ 学科基线占比，
# 低于该值说明只是学科默认桶（如语文题库 66% 是「成语填空」），不是标题的特异关联。
_MIN_QUESTION_INCLUDES_LIFT = 2.5


def clean_text(s: str) -> str:
    """通用清洗：去空白、标点、统一小写。"""
    if not s:
        return ""
    s = str(s).replace(" ", "").replace("　", "")
    s = _PUNCT_RE.sub("", s)
    return s.lower()


def clean_title(s: str) -> str:
    """清洗题目标题：剥掉开头序号（一、/1./(一)）后去空白、标点、统一小写。

    注意顺序：必须**先**剥序号（此时 '、'/'．'/'-' 等分隔符还在），
    再清标点，否则 '五、作文' 会被清成 '五作文' 而剥不掉开头序号。
    """
    s = str(s or "").replace(" ", "").replace("　", "")
    s = re.sub(r"^[一二三四五六七八九十百\d]+\s*[、.．:：\-]", "", s)
    s = re.sub(r"^[（(][一二三四五六七八九十百\d]+[)）]", "", s)
    s = _PUNCT_RE.sub("", s)
    return s.lower()


def grams(s: str, n: int):
    """长度为 n 的连续子串切分。"""
    return [s[i:i + n] for i in range(len(s) - n + 1)]


def load_distinct_titles(subjects=None, limit: int = 0):
    """从 MySQL 读出去重后的 (subject, question_title, 行数)，按行数降序。"""
    q = (
        "SELECT subject, question_title, COUNT(*) AS c FROM student_wrong_questions "
        "WHERE question_title IS NOT NULL AND question_title != '' "
    )
    params = {}
    if subjects:
        q += " AND subject IN :subjs"
        params["subjs"] = tuple(subjects)
    q += " GROUP BY subject, question_title ORDER BY c DESC"
    with engine.connect() as conn:
        rows = conn.execute(text(q), params).fetchall()
    items = [(r[0], r[1], r[2]) for r in rows]
    if limit:
        items = items[:limit]
    return items


def load_kp_pools():
    """从 PG 加载知识点池。

    返回：
      kp_id_map          : clean(knowledge_points.name) -> id（knowledge_points 权威 id）
      subject_kp_pool    : {subject: set(clean kp 名称)}，来源：
                           questions.knowledge_point 按 '/' 切开后清洗得到的段（len>=2），
                           学科由 questions.subject 限定。
      subject_kp_clean   : {subject: set(clean kp 名称)}，只保留存在于 knowledge_points.name
                           的段（权威知识点名，先匹配更可靠）。
      subject_kp_count   : {subject: Counter(clean kp 段)}，用于 question_includes 的
                           学科基线占比（lift 质量控制，防默认桶噪声）。
      subject_q_total    : {subject: int} 各学科带 kp 的题量。
    """
    kp_id_map = {}
    subject_kp_pool = {}
    subject_kp_count = {}
    subject_q_total = {}
    with assets_engine.connect() as c:
        for name, kid in c.execute(text("SELECT name, id FROM knowledge_points")):
            cn = clean_text(name)
            if cn:
                kp_id_map.setdefault(cn, kid)  # 同名取第一个 id

        for subj, kp in c.execute(
            text(
                "SELECT subject, knowledge_point FROM questions "
                "WHERE knowledge_point IS NOT NULL AND knowledge_point != ''"
            )
        ):
            subject_q_total[subj] = subject_q_total.get(subj, 0) + 1
            for seg in kp.split("/"):
                cseg = clean_text(seg)
                if len(cseg) >= 2 and not cseg.startswith(_LABEL_PREFIXES):
                    subject_kp_pool.setdefault(subj, set()).add(cseg)
                    subject_kp_count.setdefault(subj, Counter())[cseg] += 1
    subject_kp_clean = {
        subj: {seg for seg in segs if seg in kp_id_map}
        for subj, segs in subject_kp_pool.items()
    }
    return kp_id_map, subject_kp_pool, subject_kp_clean, subject_kp_count, subject_q_total


def clean_kp_repr(kp: str, kp_id_map: dict) -> str:
    """把题目 knowledge_point（可能是 'a/b/c' 复合串）折成一个可落库的单值：
    优先取存在于 knowledge_points.name 的段，否则取首段。"""
    segs = [clean_text(s) for s in kp.split("/") if clean_text(s)]
    for seg in segs:
        if seg in kp_id_map:
            return seg
    return segs[0] if segs else ""


def match_kp_side(title_clean: str, subject: str, subject_kp_pool: dict, subject_kp_clean: dict):
    """kp 侧匹配：kp_exact → kp_includes → kp_keyword。返回 (method, kp_name) 或 None。

    - 优先在「知识库名称池」（subject_kp_clean，knowledge_points.name 段）里匹配，
      命中更可靠；再回退到「全量段池」（subject_kp_pool，含题库标签，噪声更多）。
    - kp_keyword：3 字切分命中任意长度；2 字切分仅接受短知识点名（≤5 字），
      避免 '表达'/'选择' 等泛词命中长串无关知识点。
    """
    if not title_clean:
        return None
    pools = [
        sorted(subject_kp_clean.get(subject, ()), key=lambda x: (-len(x), x)),
        sorted(subject_kp_pool.get(subject, ()), key=lambda x: (-len(x), x)),
    ]

    # kp_exact：标题 == 知识点名
    for pool in pools:
        if title_clean in pool:
            return ("kp_exact", title_clean)

    # kp_includes：知识点名 ⊆ 标题（优先），或标题 ⊆ 知识点名
    for pool in pools:
        for kp in pool:
            if kp in title_clean:
                return ("kp_includes", kp)
    for pool in pools:
        for kp in pool:
            if title_clean in kp:
                return ("kp_includes", kp)

    # kp_keyword：3 字切分；2 字切分仅命中短知识点名（≤5 字）
    for pool in pools:
        for n in (3, 2):
            for g in grams(title_clean, n):
                for kp in pool:
                    if g in kp and (n >= 3 or len(kp) <= 5):
                        return ("kp_keyword", kp)
    return None


def run(subjects=None, limit: int = 0, dry_run: bool = False):
    if not assets_engine:
        print("PG 资产库未启用（ASSETS_DB_ENABLED=false），无法跨库匹配。")
        return 1
    if not dry_run:
        _ensure_wrong_question_kp_bridge_table()

    distinct = load_distinct_titles(subjects=subjects, limit=limit)
    if not distinct:
        print("student_wrong_questions 无有效标题，退出。")
        return 1

    kp_id_map, subject_kp_pool, subject_kp_clean, subject_kp_count, subject_q_total = load_kp_pools()
    subjects_here = sorted({s for s, _, _ in distinct})

    print("=== R6a 错题→知识点桥接回填 ===")
    print(f"去重标题: {len(distinct)}（行覆盖 {sum(c for _, _, c in distinct)}）")
    print(f"PG 资产库: enabled=True, subjects={subjects_here}")
    print(f"kp 池: knowledge_points.id={len(kp_id_map)}, 学科限定去重 kp 段="
          f"{sum(len(subject_kp_pool.get(s, ())) for s in subjects_here)}, "
          f"其中知识库名称段="
          f"{sum(len(subject_kp_clean.get(s, ())) for s in subjects_here)}")

    # ── 逐标题匹配 ──────────────────────────────────────────────
    title_to_raw = {}  # (subject, clean_title) -> set(raw_title)
    for subj, raw, _ in distinct:
        ct = clean_title(raw)
        if ct:
            title_to_raw.setdefault((subj, ct), set()).add(raw)

    matches = {}  # (subject, clean_title) -> (method, kp_name, confidence, kp_id)

    # ① question 侧：流式扫 PG 题目文本，收集 exact 与 includes 投票
    q_exact = {}        # (subj, ct) -> kp_repr
    q_includes_tally = {}  # (subj, ct) -> Counter(kp_repr)
    for subj in subjects_here:
        candidates = [(ct, raws) for (s, ct), raws in title_to_raw.items() if s == subj]
        cand_clean = [ct for ct, _ in candidates if len(ct) >= 2]
        if not cand_clean:
            continue
        cand_set = set(cand_clean)
        with assets_engine.connect() as c:
            for qtext, kp in c.execute(
                text(
                    "SELECT question, knowledge_point FROM questions "
                    "WHERE subject = :s AND knowledge_point IS NOT NULL AND knowledge_point != ''"
                ),
                {"s": subj},
            ):
                cq = clean_text(qtext)
                if not cq:
                    continue
                # question_exact
                if cq in cand_set and (subj, cq) not in q_exact:
                    q_exact[(subj, cq)] = clean_kp_repr(kp, kp_id_map)
                # question_includes 投票
                for ct in cand_clean:
                    if ct in cq:
                        q_includes_tally.setdefault((subj, ct), Counter())[
                            clean_kp_repr(kp, kp_id_map)
                        ] += 1

    # ② kp 侧：精确 / 包含 / 关键词
    for (subj, ct), raws in title_to_raw.items():
        method = kp_name = None
        # ① question_exact
        if (subj, ct) in q_exact:
            method, kp_name = "question_exact", q_exact[(subj, ct)]
        # ① question_includes（聚合投票 + 支持度阈值 + lift 质量控制）
        if method is None and (subj, ct) in q_includes_tally:
            tally = q_includes_tally[(subj, ct)]
            top, top_n = tally.most_common(1)[0]
            total = sum(tally.values())
            share = top_n / total if total else 0.0
            baseline = (
                subject_kp_count.get(subj, Counter()).get(top, 0)
                / subject_q_total.get(subj, 0)
                if subject_q_total.get(subj, 0)
                else 0.0
            )
            lift = share / baseline if baseline > 0 else float("inf")
            if top_n >= 3 and total > 0 and share >= 0.4 and lift >= _MIN_QUESTION_INCLUDES_LIFT:
                method, kp_name, conf_override = "question_includes", top, round(share, 2)
        # ② kp 侧
        if method is None:
            r = match_kp_side(ct, subj, subject_kp_pool, subject_kp_clean)
            if r:
                method, kp_name = r
        if method and kp_name:
            if method == "question_includes":
                conf = conf_override
            elif method == "question_exact":
                conf = 1.0
            elif method == "kp_exact":
                conf = 1.0
            elif method == "kp_includes":
                conf = 0.8
            else:  # kp_keyword
                conf = 0.6
            kp_id = kp_id_map.get(kp_name)
            matches[(subj, ct)] = (method, kp_name, conf, kp_id)

    # ── 报告：逐标题 ─────────────────────────────────────────────
    print("\n--- 逐标题匹配结果 ---")
    for subj, raw, cnt in distinct:
        ct = clean_title(raw)
        m = matches.get((subj, ct))
        if m:
            method, kp_name, conf, kp_id = m
            print(f"  {cnt:>5}  {subj}  {raw!r:16} -> {method:18} kp={kp_name!r} conf={conf:.2f} id={kp_id or '-'}")
        else:
            print(f"  {cnt:>5}  {subj}  {raw!r:16} -> NO MATCH")

    # ── 唯一标题命中率 ────────────────────────────────────────────
    matched_titles = len(matches)
    total_titles = len([ct for ct in (clean_title(r) for _, r, _ in distinct) if ct])
    hit_rate = matched_titles / total_titles if total_titles else 0.0

    # ── 行级覆盖（按标题行数汇总，subject 限定）──────────────────────
    def covered_rows_for(subj: str, ct: str) -> int:
        return sum(c for s, raw, c in distinct if s == subj and clean_title(raw) == ct)

    row_covered = sum(covered_rows_for(s, ct) for (s, ct) in matches)
    row_total = sum(c for _, _, c in distinct)
    row_rate = row_covered / row_total if row_total else 0.0

    print(f"\n--- 唯一标题命中率 ---")
    print(f"匹配 {matched_titles}/{total_titles} = {hit_rate:.1%}")
    print(f"--- 行级覆盖 ---")
    print(f"桥接行 {row_covered}/{row_total} = {row_rate:.1%}")

    # ── method / subject 分布 ────────────────────────────────────
    print("\n--- match_method 分布（唯一标题） ---")
    mc = Counter(m[0] for m in matches.values())
    for m, n in sorted(mc.items(), key=lambda x: -x[1]):
        print(f"  {m:18} {n:>3}  {n / total_titles:.1%}")

    print("\n--- 按 subject 分布（行级） ---")
    for subj in subjects_here:
        subj_total = sum(c for s, _, c in distinct if s == subj)
        subj_covered = sum(covered_rows_for(subj, ct) for (s, ct) in matches if s == subj)
        print(f"  {subj}: 行覆盖 {subj_covered}/{subj_total} = "
              f"({subj_covered / subj_total:.1%})")

    # ── 落库 ─────────────────────────────────────────────────────
    if dry_run:
        print("\n[dry-run] 未写库。")
        return 0

    # 按 (subject, raw_title) 取回错题 id 并写桥表
    write_rows = 0
    affected = 0
    with engine.begin() as conn:
        for (subj, ct), (method, kp_name, conf, kp_id) in matches.items():
            raws = title_to_raw[(subj, ct)]
            if not raws:
                continue
            ids = []
            for raw in raws:
                ids += [
                    r[0]
                    for r in conn.execute(
                        text(
                            "SELECT id FROM student_wrong_questions "
                            "WHERE subject = :s AND question_title = :t"
                        ),
                        {"s": subj, "t": raw},
                    )
                ]
            if not ids:
                continue
            params = [
                {
                    "id": wid,
                    "kp_id": kp_id,
                    "kp_name": kp_name,
                    "subject": subj,
                    "method": method,
                    "conf": conf,
                }
                for wid in ids
            ]
            write_rows += len(params)
            sql = (
                "INSERT INTO wrong_question_kp_bridge "
                "(wrong_question_id, kp_id, kp_name, subject, match_method, confidence, matched_at) "
                "VALUES (:id, :kp_id, :kp_name, :subject, :method, :conf, NOW()) "
                "ON DUPLICATE KEY UPDATE "
                "kp_id=VALUES(kp_id), kp_name=VALUES(kp_name), subject=VALUES(subject), "
                "match_method=VALUES(match_method), confidence=VALUES(confidence), "
                "matched_at=NOW()"
            )
            for i in range(0, len(params), 1000):
                r = conn.execute(text(sql), params[i:i + 1000])
                affected += r.rowcount or 0

    with engine.connect() as conn:
        after = conn.execute(
            text("SELECT COUNT(*) FROM wrong_question_kp_bridge")
        ).scalar()

    print(f"\n写库完成：本次写入 {write_rows} 行（ON DUPLICATE 幂等，受影响行 {affected}），"
          f"桥表当前总行数 {after}。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="R6a 错题→知识点桥接回填")
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 个去重标题（0=全部）")
    ap.add_argument("--subjects", type=str, default="", help="限定学科，逗号分隔，如 数学,语文")
    ap.add_argument("--dry-run", action="store_true", help="只出报告不落库")
    args = ap.parse_args()

    subjects = [s.strip() for s in args.subjects.split(",") if s.strip()] or None
    return run(subjects=subjects, limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
