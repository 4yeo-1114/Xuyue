# -*- coding: utf-8 -*-
"""初始化 20 个测试老师账号（单科任课教师），独立学校，各 2000 面额度。

用法（在 backend 目录下，需先配置好 .env 指向目标库）：
    python scripts/seed_test_teachers.py

幂等：重复执行不重复建账号、不重复充值（按 email 判存在）。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.database import SessionLocal, engine, init_db  # noqa: E402
from app.models.grading_quota import GradingQuota  # noqa: E402
from app.models.school import School  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_role import UserRole  # noqa: E402
from app.utils.security import hash_password  # noqa: E402

SCHOOL_NAME = "测试学校"
SCHOOL_DB_NAME = "test_school_demo"
PASSWORD = "test123456"
SUBJECTS = ["语文", "数学", "英语", "科学"]
COUNT = 20
QUOTA_PAGES = 2000


def main() -> None:
    init_db()
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

        created = 0
        for i in range(1, COUNT + 1):
            email = f"t{i:02d}@test.cn"
            subject = SUBJECTS[(i - 1) % len(SUBJECTS)]
            display_name = f"测试老师{i:02d}"
            u = db.query(User).filter(User.email == email).first()
            if u is None:
                u = User(
                    email=email,
                    password_hash=hash_password(PASSWORD),
                    display_name=display_name,
                    teaching_subject=subject,
                    roles="任课教师",
                )
                db.add(u)
                db.flush()
                created += 1

            # 学校归属（数据隔离锚点，经 user_roles.school_id）
            has_role = (
                db.query(UserRole)
                .filter(UserRole.user_id == u.id, UserRole.school_id == school.id)
                .first()
            )
            if not has_role:
                db.add(UserRole(user_id=u.id, role="school_teacher", school_id=school.id))

            # 额度：首次建号给 2000 面；已存在则不重复加
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
            db.commit()

        print(f"账号：本次新建 {created} 个，共 {COUNT} 个（每个 {QUOTA_PAGES} 面，密码 {PASSWORD}）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
