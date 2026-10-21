# -*- coding: utf-8 -*-
"""0924 需求 2.2/2.4：demo20 测试账号初始化——单开学校 + 每号 2000 面。

用法（在 backend 目录下，需先配置好 .env 指向目标库；本地与生产共库，跑一次即可）：
    python scripts/seed_demo20_testenv.py

幂等：
- 学校按 name 复用；user_roles 按 (user_id, school_id) 跳过
- 额度：无行则建 2000 面；已有且 total=0 置 2000（demo20-01 同时把 used 清零，
  20 号统一恰好剩 2000）；total>0 不动（防重跑覆盖充值到账结果）
- 班级 school_id 为空才补
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.database import SessionLocal, engine  # noqa: E402
from app.models.class_model import Class  # noqa: E402
from app.models.grading_quota import GradingQuota  # noqa: E402
from app.models.school import School  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_role import UserRole  # noqa: E402

DOMAIN = "xuyue-demo20.cn"
COUNT = 20
QUOTA_PAGES = 2000
SCHOOL_NAME = "叙阅测试学校"
SCHOOL_DB_NAME = "xuyue_demo20"


def main() -> None:
    # schools 为 DL1 锚表；AUTO_DDL=false 时 create_all 不建，这里显式兜底
    School.__table__.create(bind=engine, checkfirst=True)

    db = SessionLocal()
    try:
        school = db.query(School).filter(School.name == SCHOOL_NAME).first()
        if school is None:
            school = School(name=SCHOOL_NAME, db_name=SCHOOL_DB_NAME)
            db.add(school)
            db.flush()
        print(f"学校：{school.name} (id={school.id})")

        rows = []
        missing = 0
        for i in range(1, COUNT + 1):
            email = f"demo20-{i:02d}@{DOMAIN}"
            u = db.query(User).filter(User.email == email).first()
            if u is None:
                print(f"  !! {email} 不存在，跳过（先确认账号已建）")
                missing += 1
                continue

            # 1) 学校归属（user_roles.school_id）
            has_role = (
                db.query(UserRole)
                .filter(UserRole.user_id == u.id, UserRole.school_id == school.id)
                .first()
            )
            if not has_role:
                db.add(UserRole(user_id=u.id, role="school_teacher", school_id=school.id))

            # 2) 额度 2000 面
            quota = db.query(GradingQuota).filter(GradingQuota.user_id == u.id).first()
            if quota is None:
                db.add(
                    GradingQuota(
                        user_id=u.id,
                        total_pages=QUOTA_PAGES,
                        used_pages=0,
                        used_today_pages=0,
                    )
                )
                q_total, q_used = QUOTA_PAGES, 0
            elif quota.total_pages == 0:
                quota.total_pages = QUOTA_PAGES
                # 历史消耗清零：20 号统一恰好剩 2000（demo20-01 曾用 121）
                quota.used_pages = 0
                quota.used_today_pages = 0
                q_total, q_used = QUOTA_PAGES, 0
            else:
                q_total, q_used = quota.total_pages, quota.used_pages

            # 3) 名下班补学校锚点
            db.query(Class).filter(
                Class.user_id == u.id,
                Class.school_id.is_(None),
            ).update({"school_id": school.id}, synchronize_session=False)

            cls_n = db.query(Class).filter(Class.user_id == u.id).count()
            rows.append((email, u.roles, q_total, q_used, cls_n))
        db.commit()

        print(f"\n{'email':34s} {'roles':10s} {'total':>6s} {'used':>6s} {'班':>3s}")
        for email, roles, total, used, cls_n in rows:
            print(f"{email:34s} {str(roles):10s} {total:>6d} {used:>6d} {cls_n:>3d}")
        print(f"\n共 {len(rows)} 个（每个 {QUOTA_PAGES} 面）"
              + (f"，缺失 {missing} 个" if missing else ""))
    finally:
        db.close()


if __name__ == "__main__":
    main()
