# -*- coding: utf-8 -*-
"""全局导入兜底班级端到端测试（直连路由函数，跑完自动清理临时数据）。

场景：
  A. 只有「姓名」列 + fallback_class_id → 全部导入兜底班级
  B. 「姓名+学号」列 + fallback_class_id → 导入且带学号
  C. 只有「姓名」列、不给 fallback → 400（提示补列或选班级）
  D. 「年级+班级+姓名」全列、无 fallback → 按班级分组导入（原行为不回归）
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import openpyxl
from fastapi import UploadFile
from fastapi import HTTPException

from app.database import SessionLocal
from app.models.user import User, gen_uuid
from app.models.class_model import Class
from app.models.student import Student
from app.routers.students import import_students_global

MARK = "__global_import_e2e__"


def _xlsx(headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _upload(buf):
    return UploadFile(filename="t.xlsx", file=buf)


def _count(db, class_id, prefix="学生"):
    return db.query(Student).filter(
        Student.class_id == class_id, Student.name.like(f"{prefix}%")
    ).count()


def main():
    db = SessionLocal()
    uid = gen_uuid()
    cid = gen_uuid()
    user = User(id=uid, email=f"{MARK}_{uid}@test.local", password_hash="x",
                display_name=MARK, roles="系统管理员")
    cls = Class(id=cid, user_id=uid, school_level="小学", grade="三年级",
                name=f"{MARK}班", student_count=0)
    db.add(user)
    db.commit()  # 先落 user，classes 才过得了 FK
    db.add(cls)
    db.commit()

    ok = True
    try:
        # A: 只有姓名 + 兜底班级
        buf = _xlsx(["姓名"], [["学生A1"], ["学生A2"], ["学生A3"]])
        r = import_students_global(file=_upload(buf), fallback_class_id=cid,
                                   user_id=uid, db=db)
        n = _count(db, cid, "学生A")
        assert r.data == 3 and n == 3, f"A failed: data={r.data} rows={n}"
        print(f"A name-only + fallback -> {r.data} imported OK")

        # B: 姓名+学号 + 兜底班级
        buf = _xlsx(["姓名", "学号"], [["学生B1", "S001"]])
        r = import_students_global(file=_upload(buf), fallback_class_id=cid,
                                   user_id=uid, db=db)
        s = db.query(Student).filter(Student.class_id == cid,
                                     Student.name == "学生B1").first()
        assert r.data == 1 and s and s.student_number == "S001", \
            f"B failed: data={r.data} num={getattr(s, 'student_number', None)}"
        print(f"B name+student_number + fallback -> number={s.student_number} OK")

        # C: 只有姓名、无兜底 → 400
        buf = _xlsx(["姓名"], [["学生C1"]])
        try:
            import_students_global(file=_upload(buf), fallback_class_id=None,
                                   user_id=uid, db=db)
            raise AssertionError("C should raise 400")
        except HTTPException as e:
            assert e.status_code == 400 and "年级" in e.detail, f"C bad error: {e.detail}"
            print(f"C name-only no fallback -> 400 OK ({e.detail})")

        # D: 全列、无兜底 → 按年级班级分组（建第二个班级验证原行为）
        # 注意：导入会把「三年级」归一为「小学三年级」，班级 grade 要用归一后的值
        cid2 = gen_uuid()
        cls2 = Class(id=cid2, user_id=uid, school_level="小学",
                     grade="小学三年级", name="四班", student_count=0)
        db.add(cls2)
        db.commit()
        buf = _xlsx(["年级", "班级", "姓名"],
                    [["三年级", "四班", "学生D1"], ["三年级", "四班", "学生D2"]])
        r = import_students_global(file=_upload(buf), fallback_class_id=None,
                                   user_id=uid, db=db)
        n2 = db.query(Student).filter(Student.class_id == cid2,
                                      Student.name.like("学生D%")).count()
        assert r.data == 2 and n2 == 2, f"D failed: data={r.data} rows={n2}"
        print(f"D full columns classic grouping -> {r.data} OK")

        # E: 有列但该行班级不存在 → 落兜底班级
        buf = _xlsx(["年级", "班级", "姓名"], [["三年级", "不存在的班", "学生E1"]])
        r = import_students_global(file=_upload(buf), fallback_class_id=cid,
                                   user_id=uid, db=db)
        ne = _count(db, cid, "学生E")
        assert r.data == 1 and ne == 1, f"E failed: data={r.data} rows={ne}"
        print(f"E unknown class row -> fallback class OK")
    except Exception as e:
        ok = False
        print(f"FAILED: {e}")
        db.rollback()
    finally:
        # 清理：临时学生（按归属用户）+ 两个临时班 + 用户
        db.query(Student).filter(Student.user_id == uid).delete(
            synchronize_session=False)
        db.query(Student).filter(Student.class_id == cid).delete(
            synchronize_session=False)
        db.query(Class).filter(Class.user_id == uid).delete(
            synchronize_session=False)
        db.query(User).filter(User.id == uid).delete(synchronize_session=False)
        db.commit()
        db.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
