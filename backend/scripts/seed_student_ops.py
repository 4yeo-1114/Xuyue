# -*- coding: utf-8 -*-
"""激励中心造数：争章(badge_definitions/badge_awards) + 学分银行(credit_accounts) + 校外实践(practice_records)。

目标：演示-小学三年级 1~4 班（204 名学生），让激励中心各 tab 对演示账号有数据。
一致性：
  - 颁章/实践审核走真实服务函数 apply_credit_change + write_growth_record，
    保证 credit_accounts.balance == SUM(credit_transactions.amount)，并联动五育画像。
  - 对 demo_seed 既有 33 条 redeem 流水（负值且无账户）做补发 reconcile，
    最后按 (created_at, id) 重算所有流水的 balance_after 使账本自洽。

幂等：
  - badge_definitions 用固定主键 id（INSERT IGNORE）；
  - badge_awards 按 (student_id, badge_definition_id) 去重；
  - practice_records 用确定性 uuid5 主键 id（INSERT IGNORE）；
  - reconcile 用 source_type='seed_reconcile' 去重。
凭据复用后端根目录 .env（app.config.Settings 自动加载），需在 backend 根目录运行。
用法：cd grade-buddy-scan-back_end && python scripts/seed_student_ops.py
"""
import hashlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.badge_definition import BadgeDefinition  # noqa: E402
from app.models.badge_award import BadgeAward  # noqa: E402
from app.models.practice_record import PracticeRecord  # noqa: E402
from app.services.student_ops.credits import apply_credit_change  # noqa: E402
from app.services.student_ops.growth import write_growth_record  # noqa: E402

TARGET_GRADE = "小学三年级"

# (固定 id, 名称, 五育 category, 颁发积分, 描述)
BADGES = [
    ("badge-moral-star",        "品德之星",     "moral",        15, "品德表现优秀，乐于助人"),
    ("badge-moral-citizen",     "文明小公民",   "moral",        10, "文明守礼，遵守校规"),
    ("badge-moral-volunteer",   "志愿服务之星", "moral",        15, "积极参与志愿服务"),
    ("badge-intellectual-excel","学习标兵",     "intellectual", 20, "学业表现突出"),
    ("badge-intellectual-prog", "进步之星",     "intellectual", 15, "学业进步显著"),
    ("badge-intellectual-read", "阅读之星",     "intellectual", 10, "热爱阅读，阅读量领先"),
    ("badge-physical-athlete",  "运动健将",     "physical",     15, "体育表现优异"),
    ("badge-aesthetic-artist",  "艺术之星",     "aesthetic",    15, "才艺表现突出"),
    ("badge-labor-practice",    "劳动小能手",   "labor",        10, "劳动实践积极认真"),
    ("badge-ai-literate",       "AI 探索者",    "ai_literacy",  20, "AI 课程表现优秀"),
]

# 五育维度中文名（颁章 reason 展示用）
DIM_CN = {
    "moral": "品德",
    "intellectual": "学业",
    "physical": "身心",
    "aesthetic": "审美",
    "labor": "劳动",
    "ai_literacy": "AI素养",
}

# 校外实践类型 → (标题, 地点) 池
PRACTICE_POOL = {
    "housework": [("独立整理房间", "家庭"), ("学做一道家常菜", "家庭"), ("清洗整理自己的衣物", "家庭")],
    "volunteer": [("社区垃圾分类志愿服务", "社区"), ("敬老院爱心慰问", "社区敬老院"), ("校园环保志愿行动", "学校")],
    "talent":    [("参加钢琴才艺展示", "少年宫"), ("参加校园舞蹈演出", "学校"), ("参加绘画比赛", "青少年宫")],
    "study_tour":[("参观科技馆研学活动", "市科技馆"), ("参观博物馆研学活动", "市博物馆"), ("农业基地劳动研学", "农业实践基地")],
}

_PRACTICE_TYPE_LABELS = {
    "housework": "家务劳动",
    "volunteer": "志愿服务",
    "talent": "校外才艺",
    "study_tour": "研学活动",
}
_PRACTICE_GROWTH_DIMENSIONS = {
    "housework": ["labor"],
    "volunteer": ["moral", "labor"],
    "talent": ["aesthetic"],
    "study_tour": ["intellectual"],
}
_PRACTICE_INDICATOR_CODES = {
    "housework": {"labor": "labor_practice"},
    "volunteer": {"moral": "moral_activity", "labor": "labor_practice"},
    "talent": {"aesthetic": "aesthetic_activity"},
    "study_tour": {"intellectual": "intellectual_analysis"},
}

PRACTICE_REWARD_POINTS = 50
BASE_DAY = datetime.now(timezone.utc) - timedelta(days=40)


def _seed_int(sid: str) -> int:
    return int(hashlib.md5(sid.encode()).hexdigest(), 16)


def _dt(sid: str, salt: int) -> datetime:
    rng = _seed_int(sid)
    off = (rng >> salt) % 40
    hour = 8 + (rng >> (salt + 3)) % 10
    return BASE_DAY + timedelta(days=off, hours=hour)


def _award_dt(sid: str, salt: int) -> datetime:
    return _dt(sid, 7 + salt)


def _practice_dt(sid: str, salt: int) -> datetime:
    return _dt(sid, 20 + salt)


def _get_or_create_creator(db: Session) -> str:
    row = db.execute(
        text("SELECT id FROM users WHERE email = 'headteacher@grade.local'")
    ).first()
    return row[0]


def seed_badge_definitions(db: Session, creator: str) -> int:
    """固定主键插入章定义（幂等）。"""
    inserted = 0
    for i, (bid, name, cat, pts, desc) in enumerate(BADGES):
        res = db.execute(
            text(
                "INSERT IGNORE INTO badge_definitions "
                "(id, name, description, badge_type, category, icon_url, points_awarded, "
                " min_grade, max_grade, is_active, sort_order, created_by) "
                "VALUES (:id, :name, :desc, 'school_based', :cat, NULL, :pts, "
                " NULL, NULL, 1, :sort, :cb)"
            ),
            {"id": bid, "name": name, "desc": desc, "cat": cat, "pts": pts,
             "sort": i + 1, "cb": creator},
        )
        inserted += res.rowcount if res.rowcount else 0
    return inserted


def seed_badge_awards(db: Session, students: list, creator: str) -> tuple[int, int]:
    """为每个学生颁 1~2 枚章（去重按 student+badge），联动学分与画像。"""
    badges = BADGES
    n_badges = len(badges)
    awarded = 0
    credit = 0
    for (sid, cid, sname) in students:
        rng = _seed_int(sid)
        count = 1 + (rng % 2)  # 1~2
        picked: set = set()
        for j in range(count):
            k = (rng >> (2 + j * 4)) % n_badges
            if k in picked:
                k = (k + 1) % n_badges
            picked.add(k)
            bid, bname, cat, pts, _desc = badges[k]
            dup = db.execute(
                text(
                    "SELECT id FROM badge_awards WHERE student_id = :s AND badge_definition_id = :b"
                ),
                {"s": sid, "b": bid},
            ).first()
            if dup:
                continue
            adt = _award_dt(sid, j)
            award = BadgeAward(
                student_id=sid, badge_definition_id=bid, class_id=cid,
                awarded_by=creator, award_date=adt.date(),
                reason=f"在{DIM_CN.get(cat, cat)}方面表现突出，特颁【{bname}】以资鼓励",
            )
            db.add(award)
            db.flush()
            _, txn = apply_credit_change(
                db, sid, cid, pts, "badge_award", creator,
                f"获得【{bname}】",
                source_type="badge_definition", source_id=bid,
            )
            txn.created_at = adt
            award.credit_transaction_id = txn.id
            write_growth_record(
                db, sid, cid, cat, "badge_award", award.id, pts,
                note=f"获得【{bname}】", created_by=creator, occurred_at=adt.date(),
            )
            awarded += 1
            credit += 1
    return awarded, credit


def backfill_badge_reason(db: Session) -> int:
    """把颁章 reason 里的 category 代码回填为中文维度名（修正早期种子数据）。"""
    rows = db.execute(
        text(
            "SELECT ba.id, bd.category, bd.name FROM badge_awards ba "
            "JOIN badge_definitions bd ON bd.id = ba.badge_definition_id"
        )
    ).all()
    for aid, cat, bname in rows:
        reason = f"在{DIM_CN.get(cat, cat)}方面表现突出，特颁【{bname}】以资鼓励"
        db.execute(text("UPDATE badge_awards SET reason=:r WHERE id=:id"), {"r": reason, "id": aid})
    return len(rows)


def seed_practice_records(db: Session, students: list, creator: str) -> tuple[int, int, int]:
    """为每个学生造 1~2 条已审核通过的校外实践（确定性 uuid5 主键幂等）。"""
    records = 0
    credit = 0
    growth = 0
    types = list(PRACTICE_POOL.keys())
    n_types = len(types)
    for (sid, cid, sname) in students:
        rng = _seed_int(sid)
        count = 1 + ((rng >> 5) % 2)  # 1~2
        for j in range(count):
            ti = (rng >> (6 + j * 3)) % n_types
            ptype = types[ti]
            pool = PRACTICE_POOL[ptype]
            title, loc = pool[(rng >> (6 + j * 3 + 2)) % len(pool)]
            rid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"practice:{sid}:{ptype}:{j}"))
            dup = db.execute(text("SELECT id FROM practice_records WHERE id = :id"), {"id": rid}).first()
            if dup:
                continue
            pdt = _practice_dt(sid, j)
            rec = PracticeRecord(
                id=rid, student_id=sid, class_id=cid,
                practice_type=ptype, title=title,
                description=f"学生参与{_PRACTICE_TYPE_LABELS[ptype]}：{title}",
                practice_date=pdt.date(),
                duration_hours=1.0 + ((rng >> (6 + j * 3 + 4)) % 30) / 10.0,
                location=loc, evidence_images=[],
                status="approved", reviewer_id=creator,
                review_comment="表现优秀，予以通过", reviewed_at=pdt + timedelta(hours=6),
                recorded_by=creator,
            )
            db.add(rec)
            db.flush()
            _, txn = apply_credit_change(
                db, sid, cid, PRACTICE_REWARD_POINTS, "practice_approved", creator,
                f"【{rec.title}】实践审核通过",
                source_type="practice_record", source_id=rid,
            )
            txn.created_at = pdt + timedelta(hours=6)
            rec.credit_transaction_id = txn.id
            label = _PRACTICE_TYPE_LABELS[ptype]
            for dim in _PRACTICE_GROWTH_DIMENSIONS[ptype]:
                write_growth_record(
                    db, sid, cid, dim, "practice_record", rid, PRACTICE_REWARD_POINTS,
                    note=f"【{label}】{title}", created_by=creator, occurred_at=pdt.date(),
                    indicator_code=_PRACTICE_INDICATOR_CODES[ptype].get(dim),
                )
                growth += 1
            records += 1
            credit += 1
    return records, credit, growth


def reconcile_redeem_students(db: Session, creator: str) -> int:
    """对齐 demo_seed 既有 redeem 流水（负值、无对应账户）导致的账本不一致。

    demo_seed 直接写了 redeem 负值流水却没建账户，造成 balance != SUM(amount)。
    这里对每个有扣减流水（amount<0）的学生：
      - earned = 正流水之和（颁章/实践已入账）
      - spent  = 负流水绝对值之和（redeem）
      补一条 opening manual_add 流水（amount = spent + 300），并直接对齐账户
      balance/total_earned/total_spent，使 SUM(amount) == balance 自洽（最终余额 earned+300）。
    幂等：先删掉历史 seed_reconcile 流水，再按当前账本重算重建。
    """
    db.execute(text("DELETE FROM credit_transactions WHERE source_type = 'seed_reconcile'"))
    rows = db.execute(
        text(
            "SELECT t.student_id, MAX(t.class_id) AS cid, "
            "       SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) AS earned, "
            "       SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS spent "
            "FROM credit_transactions t GROUP BY t.student_id "
            "HAVING SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) > 0"
        )
    ).all()
    granted = 0
    for sid, cid, earned, spent in rows:
        earned = int(earned or 0)
        spent = int(spent or 0)
        grant = spent + 300                       # opening 补发
        final_balance = earned + 300              # 目标余额（>0）
        final_earned = earned + grant
        src = "reconcile_" + hashlib.md5(sid.encode()).hexdigest()[:16]
        db.execute(
            text(
                "INSERT INTO credit_transactions "
                "(id, student_id, class_id, amount, transaction_type, balance_after, "
                " source_type, source_id, operator_id, description, created_at) "
                "VALUES (:id,:sid,:cid,:amt,'manual_add',:bal,'seed_reconcile',:src,:op,:desc,:ts)"
            ),
            {
                "id": str(uuid.uuid4()), "sid": sid, "cid": cid, "amt": grant,
                "bal": final_balance, "src": src, "op": creator,
                "desc": "演示初始化补发积分", "ts": BASE_DAY - timedelta(days=1),
            },
        )
        acct = db.execute(
            text("SELECT id FROM credit_accounts WHERE student_id = :s"), {"s": sid}
        ).first()
        if acct:
            db.execute(
                text(
                    "UPDATE credit_accounts SET balance=:b, total_earned=:e, total_spent=:sp "
                    "WHERE student_id=:s"
                ),
                {"b": final_balance, "e": final_earned, "sp": spent, "s": sid},
            )
        else:
            db.execute(
                text(
                    "INSERT INTO credit_accounts (id, student_id, balance, total_earned, total_spent) "
                    "VALUES (:id, :s, :b, :e, :sp)"
                ),
                {"id": str(uuid.uuid4()), "s": sid, "b": final_balance,
                 "e": final_earned, "sp": spent},
            )
        granted += 1
    return granted


def recompute_balance_after(db: Session) -> int:
    """按 (created_at, id) 顺序重算每个学生所有流水的 balance_after（自洽幂等）。"""
    students = db.execute(
        text("SELECT DISTINCT student_id FROM credit_transactions")
    ).all()
    updated = 0
    for (sid,) in students:
        txns = db.execute(
            text(
                "SELECT id, amount FROM credit_transactions "
                "WHERE student_id = :s ORDER BY created_at ASC, id ASC"
            ),
            {"s": sid},
        ).all()
        running = 0
        for tid, amount in txns:
            running += int(amount)
            db.execute(
                text("UPDATE credit_transactions SET balance_after = :b WHERE id = :id"),
                {"b": running, "id": tid},
            )
            updated += 1
    return updated


def main():
    out_lines = ["=== seed_student_ops ==="]
    db = SessionLocal()
    try:
        creator = _get_or_create_creator(db)
        out_lines.append(f"creator(headteacher)={creator}")

        students = db.execute(
            text(
                "SELECT s.id, s.class_id, s.name FROM students s "
                "JOIN classes c ON c.id = s.class_id WHERE c.grade = :g ORDER BY c.name, s.id"
            ),
            {"g": TARGET_GRADE},
        ).all()
        out_lines.append(f"students={len(students)}")

        n_def = seed_badge_definitions(db, creator)
        n_award, n_award_credit = seed_badge_awards(db, students, creator)
        n_prac, n_prac_credit, n_prac_growth = seed_practice_records(db, students, creator)
        n_grant = reconcile_redeem_students(db, creator)
        n_reason = backfill_badge_reason(db)
        n_bal = recompute_balance_after(db)
        db.commit()

        out_lines.append(f"badge_definitions_inserted={n_def}")
        out_lines.append(f"badge_awards={n_award} (credit_txns={n_award_credit})")
        out_lines.append(f"practice_records={n_prac} (credit_txns={n_prac_credit}, growth={n_prac_growth})")
        out_lines.append(f"reconcile_grants={n_grant}")
        out_lines.append(f"badge_reason_backfilled={n_reason}")
        out_lines.append(f"balance_after_updated={n_bal}")

        # 汇总表计数
        for tbl in ["badge_definitions", "badge_awards", "practice_records",
                    "credit_accounts", "credit_transactions"]:
            n = db.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            out_lines.append(f"  {tbl}={n}")

        # 学分账户与流水一致性抽查（按学生 SUM 与 balance 对比）
        mism = db.execute(
            text(
                "SELECT COUNT(*) FROM ("
                "  SELECT a.student_id FROM credit_accounts a "
                "  LEFT JOIN (SELECT student_id, SUM(amount) s FROM credit_transactions GROUP BY student_id) t "
                "  ON t.student_id = a.student_id "
                "  WHERE COALESCE(t.s,0) <> COALESCE(a.balance,0)"
                ") x"
            )
        ).scalar()
        out_lines.append(f"credit_mismatch_students={mism}")

        # 三年级各班颁章/实践覆盖
        per_class = db.execute(
            text(
                "SELECT c.name, "
                "  (SELECT COUNT(DISTINCT ba.student_id) FROM badge_awards ba WHERE ba.class_id=c.id), "
                "  (SELECT COUNT(DISTINCT pr.student_id) FROM practice_records pr WHERE pr.class_id=c.id), "
                "  (SELECT COUNT(DISTINCT ca.student_id) FROM credit_accounts ca JOIN students s ON s.id=ca.student_id WHERE s.class_id=c.id) "
                "FROM classes c WHERE c.grade=:g ORDER BY c.name"
            ),
            {"g": TARGET_GRADE},
        ).all()
        for cn, nb, np_, nc in per_class:
            out_lines.append(f"  {cn}: 有章={nb} 有实践={np_} 有学分账户={nc}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    out_path = ROOT / "scripts" / "seed_student_ops_out.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")
    print(f"done -> {out_path}")


if __name__ == "__main__":
    main()
