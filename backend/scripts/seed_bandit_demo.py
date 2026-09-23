# -*- coding: utf-8 -*-
"""R6b 合成种子脚本：桥表 + PG 题生成演示推荐（输入演示学生 → 输出推荐列表）。

不写库（bandit_arm_stats 为可选非关键落库，默认 dry-run 不写），供验收与无 reward 演示用。
依赖：本地 MySQL（主库）+ PG 资产库（ASSETS_DB_ENABLED=true，见 .env）。

用法：
  python scripts/seed_bandit_demo.py                                   # 自动挑错题最多的学生演示
  python scripts/seed_bandit_demo.py --student <student_id>            # 指定学生
  python scripts/seed_bandit_demo.py --student <id> --subject 数学 --limit 5
  python scripts/seed_bandit_demo.py --list-students                   # 列出错题最多的前 5 名学生

验收锚点：response_logs 0 行 → 推荐必走 explore（确定性薄弱点推荐），不报错。
"""
import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.services import bandit_recommender as br  # noqa: E402


def list_top_students(limit: int = 5):
    from sqlalchemy import text
    from app.database import engine

    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT s.id, s.name, s.class_id, COUNT(w.id) AS wq "
            "FROM students s JOIN student_wrong_questions w ON w.student_name = s.name "
            "GROUP BY s.id, s.name, s.class_id ORDER BY wq DESC LIMIT :lim"
        ), {"lim": limit}).fetchall()
    return rows


def main():
    ap = argparse.ArgumentParser(description="R6b bandit 错题推荐合成种子演示")
    ap.add_argument("--student", type=str, default="", help="学生 id（缺省自动挑错题最多）")
    ap.add_argument("--subject", type=str, default="数学", help="学科")
    ap.add_argument("--limit", type=int, default=5, help="推荐条数")
    ap.add_argument("--seed", type=int, default=42, help="explore 随机种子（同 seed 可复现）")
    ap.add_argument("--list-students", action="store_true", help="列出错题最多的前 N 名学生")
    ap.add_argument("--write-stats", action="store_true", help="同时落 bandit_arm_stats（默认不写库）")
    args = ap.parse_args()

    if args.list_students:
        rows = list_top_students()
        print("=== 错题最多的学生（演示候选） ===")
        for r in rows:
            print(f"  {r[0]}  {r[1]}  班级={r[2]}  错题={r[3]}")
        return 0

    if not args.student:
        rows = list_top_students(1)
        if not rows:
            print("无错题数据，无法演示。")
            return 1
        args.student = rows[0][0]
        print(f"[auto] 选用错题最多学生: {rows[0][1]} ({rows[0][0]})")

    if args.write_stats:
        # 幂等建表（AUTO_DDL=false 时本地库表可能未建）
        from app.database import _ensure_bandit_arm_stats_table
        _ensure_bandit_arm_stats_table()

    # service 层需要 db session + asset_db session；这里用注入式 API 直连
    from sqlalchemy.orm import sessionmaker

    from app.assets.database import assets_engine, assets_session
    from app.database import SessionLocal

    db = SessionLocal()
    asset_db = assets_session() if assets_engine is not None else None

    rng = random.Random(args.seed)
    try:
        result = br.recommend_for_student(
            db=db,
            asset_db=asset_db,
            student_id=args.student,
            subject=args.subject,
            limit=args.limit,
            rng=rng,
        )
    finally:
        db.close()
        if asset_db is not None:
            asset_db.close()

    print(f"\n=== R6b bandit 错题推荐（student={args.student}, subject={args.subject}） ===")
    print(f"mode: {result.get('mode')}  reason: {result.get('reason') or '-'}")
    print(f"items: {len(result.get('items', []))}\n")
    for i, item in enumerate(result.get("items", []), 1):
        q = item["question"]
        reason = item["reason"]
        print(f"--- 推荐 {i} ---")
        print(f"  kp_name   : {reason.get('kp_name')}")
        print(f"  错因      : {', '.join(reason.get('error_types', []))}")
        print(f"  错误次数  : {reason.get('error_count')}  置信度: {reason.get('confidence')}")
        print(f"  推荐模式  : {reason.get('mode')}  ucb_score: {reason.get('ucb_score', '-')}")
        print(f"  difficulty: {q.get('difficulty')}")
        stem = (q.get("question") or "").replace("\n", " ").strip()
        print(f"  题干      : {stem[:80]}{'…' if len(stem) > 80 else ''}")
        ans = (q.get("answer") or "").replace("\n", " ").strip()
        print(f"  答案      : {ans[:60]}{'…' if len(ans) > 60 else ''}")
        anl = (q.get("analysis") or "").replace("\n", " ").strip()
        print(f"  解析      : {anl[:60]}{'…' if len(anl) > 60 else ''}")

    if result.get("mode") == "fallback":
        print(f"\n[fallback] {result.get('reason')} —— 该学生该科无薄弱知识点或无匹配变式题。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
