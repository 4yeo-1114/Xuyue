"""C 域（学生运营）验收 + 冒烟测试。

前置：
- 本地 Docker MySQL 8 运行在 127.0.0.1:3307，root/root_pw_2026，数据库 grade
- 依赖已安装（fastapi/sqlalchemy/pymysql/jose/bcrypt/httpx）

本脚本不可修改任何现有文件；仅用于验收 C 域 model/router 逻辑。
流程：
  1) 设置环境变量（必须在 import app.* 之前）
  2) 注册 14 张新表到 Base.metadata，raw DDL 建 student_growth_records
  3) Base.metadata.create_all 建表
  4) 播种测试数据（管理员/班级/学生/学生账户 user）
  5) TestClient 冒烟：建章定义 → 颁章(三方写入) → 手动加减分 → 兑换(同事务+防超卖并发) → 实践提交/审核
"""
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

# ---- 1) 环境变量（必须先于 app.* import）----
os.environ["DB_HOST"] = "127.0.0.1"
os.environ["DB_PORT"] = "3307"
os.environ["DB_USER"] = "root"
os.environ["DB_PASSWORD"] = "root_pw_2026"
os.environ["DB_NAME"] = "grade"
os.environ["JWT_SECRET_KEY"] = "dev_secret_key_at_least_32_chars_long_123456"
os.environ["AUTO_DDL"] = "true"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

# ---- 2) 注册 model ----
from app.database import Base, engine, SessionLocal

# 基础模型（被新表 FK 引用）
import app.models.user  # noqa: F401
import app.models.class_model  # noqa: F401
import app.models.class_teacher  # noqa: F401
import app.models.student  # noqa: F401

# C 域 14 张表
import app.models.badge_definition  # noqa: F401
import app.models.badge_award  # noqa: F401
import app.models.credit_account  # noqa: F401
import app.models.credit_transaction  # noqa: F401
import app.models.reward_product  # noqa: F401
import app.models.redemption_record  # noqa: F401
import app.models.practice_record  # noqa: F401
import app.models.campus_club  # noqa: F401
import app.models.club_enrollment  # noqa: F401
import app.models.club_attendance  # noqa: F401
import app.models.book_borrow  # noqa: F401
import app.models.reading_record  # noqa: F401
import app.models.health_check  # noqa: F401
import app.models.student_task  # noqa: F401

from app.models.user import User, gen_uuid
from app.models.class_model import Class
from app.models.student import Student
from app.utils.security import create_access_token
from app.routers.student_ops import router as student_ops_router

# ---- 3) 建表 ----
_GROWTH_DDL = """
CREATE TABLE IF NOT EXISTS student_growth_records (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL,
    class_id VARCHAR(36) NULL,
    school_id VARCHAR(36) NULL,
    dimension VARCHAR(32) NOT NULL,
    source_type VARCHAR(64) NOT NULL,
    source_id VARCHAR(36) NULL,
    growth_points INT NOT NULL DEFAULT 0,
    evidence TEXT NULL,
    note VARCHAR(512) NULL,
    created_by VARCHAR(36) NULL,
    occurred_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_sgr_student (student_id),
    KEY ix_sgr_source (source_type, source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""
with engine.begin() as conn:
    conn.execute(text(_GROWTH_DDL))
Base.metadata.create_all(bind=engine)
print("[OK] create_all 完成（含 14 张 C 域表 + 基础表）")

# ---- 4) 播种 ----
db = SessionLocal()
_run_key = datetime.utcnow().strftime("%H%M%S%f")

admin = db.query(User).filter(User.email == "c_domain_admin@test.local").first()
if not admin:
    admin = User(email="c_domain_admin@test.local", password_hash="x", display_name="C域管理员", roles="系统管理员")
    db.add(admin)
    db.flush()
klass = db.query(Class).filter(Class.user_id == admin.id, Class.name == f"验1班_{_run_key}").first()
if not klass:
    klass = Class(user_id=admin.id, school_level="primary", grade="五年级", name=f"验1班_{_run_key}")
    db.add(klass)
    db.flush()


def _make_student(name: str, number: str) -> Student:
    u = User(email=f"{number}@test.local", password_hash="x", display_name=name, roles="学生")
    db.add(u)
    db.flush()
    s = Student(class_id=klass.id, user_id=u.id, name=name, student_number=number)
    db.add(s)
    db.flush()
    return s


s1 = _make_student(f"张三_{_run_key}", f"S{_run_key}01")
s2 = _make_student(f"李四_{_run_key}", f"S{_run_key}02")
s3 = _make_student(f"王五_{_run_key}", f"S{_run_key}03")
db.commit()
admin_id, class_id = admin.id, klass.id
print(f"[OK] 种子数据: admin={admin_id}, class={class_id}, students=[{s1.id},{s2.id},{s3.id}]")

# ---- 5) 构建测试 app ----
app = FastAPI()
app.include_router(student_ops_router, prefix="/api/v1")
client = TestClient(app)
token = create_access_token(admin_id)
H = {"Authorization": f"Bearer {token}"}
BASE = "/api/v1"


def _post(path, body, expect_code=200):
    r = client.post(BASE + path, json=body, headers=H)
    assert r.status_code == expect_code, f"{path} -> {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("code") == 0, f"{path} -> code={data.get('code')}: {r.text}"
    return data.get("data")


def _patch(path, body, expect_code=200):
    r = client.patch(BASE + path, json=body, headers=H)
    assert r.status_code == expect_code, f"{path} -> {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("code") == 0, f"{path} -> code={data.get('code')}: {r.text}"
    return data.get("data")


def _get(path, expect_code=200):
    r = client.get(BASE + path, headers=H)
    assert r.status_code == expect_code, f"{path} -> {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("code") == 0, f"{path} -> code={data.get('code')}: {r.text}"
    return data.get("data")


def _delete(path, expect_code=200):
    r = client.delete(BASE + path, headers=H)
    assert r.status_code == expect_code, f"{path} -> {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("code") == 0, f"{path} -> code={data.get('code')}: {r.text}"
    return data.get("data")


def _db_rows(sql, **params):
    with engine.begin() as conn:
        return conn.execute(text(sql), params).fetchall()


PASS = []

# ---- 冒烟 1：建章定义 ----
badge = _post("/student-ops/badge-definitions", {
    "name": f"劳动小能手_{_run_key}", "category": "labor", "pointsAwarded": 10, "isActive": True,
})
badge_id = badge["id"]
assert badge["pointsAwarded"] == 10 and badge["category"] == "labor"
PASS.append("建章定义: POST /badge-definitions")

# ---- 冒烟 2：颁章（验证三方写入）----
award = _post("/student-ops/badge-awards", {
    "studentIds": [s1.id], "badgeDefinitionId": badge_id,
    "awardDate": "2026-08-10", "reason": "验收测试颁章",
})
assert award["successCount"] == 1 and award["failCount"] == 0, award
award_id = award["awards"][0]["id"]

# 2a. credit_accounts 双写
acc = _db_rows("SELECT balance, total_earned, total_spent FROM credit_accounts WHERE student_id=:s", s=s1.id)[0]
assert acc[0] == 10 and acc[1] == 10 and acc[2] == 0, acc
# 2b. credit_transactions 写流水
txn = _db_rows("SELECT amount, transaction_type, balance_after, source_type, source_id FROM credit_transactions WHERE student_id=:s", s=s1.id)[0]
assert txn[0] == 10 and txn[1] == "badge_award" and txn[2] == 10 and txn[3] == "badge_definition", txn
# 2c. student_growth_records 三方写入
gr = _db_rows(
    "SELECT source_type, source_id, dimension, growth_points FROM student_growth_records WHERE student_id=:s AND source_type='badge_award'",
    s=s1.id,
)
assert len(gr) == 1 and gr[0][0] == "badge_award" and gr[0][1] == award_id and gr[0][2] == "labor" and gr[0][3] == 10, gr
PASS.append("颁章: 三方写入 (credit_account + credit_transaction + growth_record)")

# 2d. 重复颁章拦截（uk_student_badge_date）
dup = _post("/student-ops/badge-awards", {
    "studentIds": [s1.id], "badgeDefinitionId": badge_id, "awardDate": "2026-08-10",
})
assert dup["successCount"] == 0 and dup["failCount"] == 1 and dup["failures"][0]["reason"] == "duplicate_entry", dup
PASS.append("颁章: 重复颁章被拦截 (uk_student_badge_date)")

# ---- 冒烟 3：手动加减分 ----
man = _post("/student-ops/credit-transactions/manual", {"studentId": s1.id, "amount": 5, "description": "加分"})
assert man["balanceAfter"] == 15, man
man2 = _post("/student-ops/credit-transactions/manual", {"studentId": s1.id, "amount": -3, "description": "扣分"})
assert man2["balanceAfter"] == 12, man2
# 负余额拦截
r = client.post(BASE + "/student-ops/credit-transactions/manual", json={"studentId": s1.id, "amount": -100, "description": "超额扣分"}, headers=H)
assert r.status_code == 400 and "insufficient_balance" in r.json().get("detail", ""), r.text
PASS.append("手动加减分: +5/-3 生效，负余额被拦截")

# ---- 冒烟 4：兑换（同事务 + 防超卖）----
prod = _post("/student-ops/reward-products", {
    "name": f"文具盲盒_{_run_key}", "productType": "physical", "pointsRequired": 5, "stock": 1, "isActive": True,
})
prod_id = prod["id"]
red = _post("/student-ops/redemptions", {"studentId": s1.id, "productId": prod_id})
assert red["status"] == "pending" and red["pointsSpent"] == 5, red
red_id = red["id"]
# 4a. 扣分 + 库存 + 流水 同事务
acc2 = _db_rows("SELECT balance, total_spent FROM credit_accounts WHERE student_id=:s", s=s1.id)[0]
assert acc2[0] == 7 and acc2[1] == 8, acc2  # balance 12-5=7; total_spent 3(手动扣)+5(兑换)=8
stock = _db_rows("SELECT stock FROM reward_products WHERE id=:p", p=prod_id)[0][0]
assert stock == 0, stock
rtxn = _db_rows("SELECT amount, transaction_type, balance_after, source_type FROM credit_transactions WHERE source_id=:rid", rid=red_id)
assert len(rtxn) == 1 and rtxn[0][0] == -5 and rtxn[0][1] == "redemption" and rtxn[0][2] == 7, rtxn
red_db = _db_rows("SELECT credit_transaction_id FROM redemption_records WHERE id=:rid", rid=red_id)[0][0]
assert red_db, "redemption.credit_transaction_id 未回填"
PASS.append("兑换: 扣分+库存+流水同事务")

# 4b. 超卖拦截（库存 0）——用 s1（仍有余额 7）触发库存拦截
r = client.post(BASE + "/student-ops/redemptions", json={"studentId": s1.id, "productId": prod_id}, headers=H)
assert r.status_code == 400 and "out_of_stock" in r.json().get("detail", ""), r.text
PASS.append("兑换: 库存为 0 被拦截 (out_of_stock)")

# 4c. 并发防超卖（R-03）：新商品 stock=1，两个学生同时兑换，恰好 1 成功 1 失败
prod2 = _post("/student-ops/reward-products", {
    "name": f"限量盲盒_{_run_key}", "productType": "physical", "pointsRequired": 5, "stock": 1, "isActive": True,
})
prod2_id = prod2["id"]
# 给 s2/s3 各充 100 分
_post("/student-ops/credit-transactions/manual", {"studentId": s2.id, "amount": 100, "description": "并发测试充值"})
_post("/student-ops/credit-transactions/manual", {"studentId": s3.id, "amount": 100, "description": "并发测试充值"})

results = []
barrier = threading.Barrier(2)


def _concurrent_redeem(sid):
    barrier.wait()
    r = client.post(BASE + "/student-ops/redemptions", json={"studentId": sid, "productId": prod2_id}, headers=H)
    return r.status_code


with ThreadPoolExecutor(max_workers=2) as ex:
    futs = [ex.submit(_concurrent_redeem, sid) for sid in (s2.id, s3.id)]
    results = [f.result() for f in futs]

ok_cnt = sum(1 for c in results if c == 200)
fail_cnt = sum(1 for c in results if c == 400)
assert ok_cnt == 1 and fail_cnt == 1, f"并发防超卖期望 1 成功 1 失败, 实际 {results}"
stock2 = _db_rows("SELECT stock FROM reward_products WHERE id=:p", p=prod2_id)[0][0]
assert stock2 == 0, f"并发后库存应为 0, 实际 {stock2}"
PASS.append("兑换: 并发防超卖 (SELECT FOR UPDATE) 恰好 1 成功 1 失败")

# 4d. 兑换审核状态机
_patch(f"/student-ops/redemptions/{red_id}/status", {"status": "approved"})
_patch(f"/student-ops/redemptions/{red_id}/status", {"status": "delivered"})
PASS.append("兑换: 审核状态机 pending->approved->delivered")

# ---- 冒烟 5：校外实践提交/审核 ----
pr = _post("/student-ops/practice-records", {
    "studentId": s1.id, "practiceType": "volunteer", "title": "社区志愿服务",
    "description": "打扫社区卫生", "practiceDate": "2026-08-01", "durationHours": 2,
})
pr_id = pr["id"]
assert pr["status"] == "pending", pr
rv = _patch(f"/student-ops/practice-records/{pr_id}/review", {"status": "approved", "reviewComment": "验收通过"})
assert rv["status"] == "approved", rv
# 5a. 审核通过入账 +50
acc3 = _db_rows("SELECT balance FROM credit_accounts WHERE student_id=:s", s=s1.id)[0][0]
assert acc3 == 57, f"实践审核后余额应为 57, 实际 {acc3}"  # 7 + 50
# 5b. 画像写入（volunteer → moral + labor 两条）
pgr = _db_rows(
    "SELECT dimension, growth_points FROM student_growth_records WHERE student_id=:s AND source_type='practice_record' AND source_id=:rid ORDER BY dimension",
    s=s1.id, rid=pr_id,
)
dims = [row[0] for row in pgr]
assert set(dims) == {"moral", "labor"} and all(row[1] == 50 for row in pgr), pgr
PASS.append("校外实践: 审核通过入账 +50 并写入画像 (volunteer→moral+labor)")

# 5c. 驳回不奖励
s2_bal_before = _db_rows("SELECT balance FROM credit_accounts WHERE student_id=:s", s=s2.id)[0][0]
pr2 = _post("/student-ops/practice-records", {
    "studentId": s2.id, "practiceType": "housework", "title": "家务劳动",
    "practiceDate": "2026-08-02",
})
_pr2_id = pr2["id"]
_patch(f"/student-ops/practice-records/{_pr2_id}/review", {"status": "rejected", "reviewComment": "证据不足"})
s2_bal_after = _db_rows("SELECT balance FROM credit_accounts WHERE student_id=:s", s=s2.id)[0][0]
assert s2_bal_after == s2_bal_before, f"驳回不应加积分: before={s2_bal_before} after={s2_bal_after}"
PASS.append("校外实践: 驳回不加分")

# ---- 冒烟 6：对账 ----
rec = _get(f"/student-ops/credit-reconciliation?studentId={s1.id}")["items"][0]
assert rec["status"] == "ok" and rec["accountBalance"] == rec["sumAmount"], rec
assert rec["lastBalanceAfter"] == rec["accountBalance"], rec
PASS.append("对账: balance_after 与 account.balance 一致")

# ---- 冒烟 7：校园生活 ----
club = _post("/student-ops/clubs", {"name": f"编程社_{_run_key}", "description": "学编程", "maxMembers": 20})
club_id = club["id"]
enroll = _post("/student-ops/club-enrollments", {"clubId": club_id, "studentIds": [s1.id, s2.id], "enrolledAt": "2026-08-05"})
assert enroll["successCount"] == 2, enroll
att = _post("/student-ops/club-attendance", {
    "clubId": club_id, "sessionDate": "2026-08-06",
    "records": [
        {"studentId": s1.id, "attendStatus": "present"},
        {"studentId": s2.id, "attendStatus": "present"},
    ],
})
assert att["successCount"] == 2, att
PASS.append("校园生活: 社团创建/报名/考勤")

# 阅读
_rd = _post("/student-ops/reading-records", {"studentId": s1.id, "bookTitle": "西游记", "pagesRead": 30, "readingMinutes": 45, "readingDate": "2026-08-07"})
assert _rd["pagesRead"] == 30, _rd
lb = _get("/student-ops/reading-leaderboard?period=month&classId=" + class_id)["leaderboard"]
assert any(row["studentId"] == s1.id for row in lb), lb
PASS.append("校园生活: 阅读打卡 + 榜单")

# 借阅
br = _post("/student-ops/book-borrows", {
    "studentId": s1.id, "bookTitle": "小王子", "dueAt": "2026-08-30T00:00:00",
})
_br_id = br["id"]
_patch(f"/student-ops/book-borrows/{_br_id}/return", {"notes": "按时归还"})
PASS.append("校园生活: 图书借阅/归还")

# 晨午检 + 预警
hc = _post("/student-ops/health-checks", {
    "classId": class_id, "checkType": "morning", "checkDate": "2026-08-08",
    "records": [{"studentId": s1.id, "temperature": 38.0, "symptoms": "发热"}],
})
assert hc["successCount"] == 1, hc
alerts = _get(f"/student-ops/health-alerts?classId={class_id}")
assert len(alerts["items"]) >= 1, alerts
PASS.append("校园生活: 晨午检自动预警")

# ---- 冒烟 8：文件上传 + 直链 ----
tiny = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
up = client.post(BASE + "/student-ops/upload-evidence", files={"file": ("a.png", tiny, "image/png")}, headers=H)
assert up.status_code == 200 and up.json()["code"] == 0, up.text
_url_rel = up.json()["data"]["url"]
fileurl = _get(f"/student-ops/get-file-url?path={_url_rel}")["downloadUrl"]
r = client.get(fileurl)
assert r.status_code == 200, f"文件直链访问失败: {r.status_code}"
PASS.append("文件: 上传证据 + download ticket 直链访问")

# ---- 冒烟 9：颁章撤销（积分回滚 + 画像清理）----
badge_r = _post("/student-ops/badge-definitions", {
    "name": f"可撤销章_{_run_key}", "category": "aesthetic", "pointsAwarded": 7, "isActive": True,
})
s3_before = _db_rows("SELECT balance FROM credit_accounts WHERE student_id=:s", s=s3.id)[0][0]
aw = _post("/student-ops/badge-awards", {
    "studentIds": [s3.id], "badgeDefinitionId": badge_r["id"], "awardDate": "2026-08-09",
})
aw_id = aw["awards"][0]["id"]
s3_mid = _db_rows("SELECT balance FROM credit_accounts WHERE student_id=:s", s=s3.id)[0][0]
assert s3_mid == s3_before + 7, f"颁章加分失败: {s3_before} -> {s3_mid}"
_delete(f"/student-ops/badge-awards/{aw_id}")
s3_after = _db_rows("SELECT balance FROM credit_accounts WHERE student_id=:s", s=s3.id)[0][0]
assert s3_after == s3_before, f"撤销未回滚积分: before={s3_before} after={s3_after}"
gr_del = _db_rows("SELECT COUNT(*) FROM student_growth_records WHERE source_type='badge_award' AND source_id=:aid", aid=aw_id)[0][0]
assert gr_del == 0, f"撤销后画像记录未清理: {gr_del}"
PASS.append("颁章撤销: 积分回滚 + 画像记录清理")

# ---- 冒烟 10：实践记录删除（退分 + 画像清理）----
s1_before = _db_rows("SELECT balance FROM credit_accounts WHERE student_id=:s", s=s1.id)[0][0]
pr_del = _post("/student-ops/practice-records", {
    "studentId": s1.id, "practiceType": "housework", "title": "家务",
    "practiceDate": "2026-08-03",
})
pr_del_id = pr_del["id"]
_patch(f"/student-ops/practice-records/{pr_del_id}/review", {"status": "approved", "reviewComment": "通过"})
s1_mid = _db_rows("SELECT balance FROM credit_accounts WHERE student_id=:s", s=s1.id)[0][0]
assert s1_mid == s1_before + 50, f"实践审核加分失败: {s1_before} -> {s1_mid}"
_delete(f"/student-ops/practice-records/{pr_del_id}")
s1_after = _db_rows("SELECT balance FROM credit_accounts WHERE student_id=:s", s=s1.id)[0][0]
assert s1_after == s1_before, f"实践删除未退分: before={s1_before} after={s1_after}"
gr_del = _db_rows("SELECT COUNT(*) FROM student_growth_records WHERE source_type='practice_record' AND source_id=:rid", rid=pr_del_id)[0][0]
assert gr_del == 0, f"实践删除后画像记录未清理: {gr_del}"
PASS.append("实践删除: 退分 + 画像记录清理")

db.close()

print("\n===== 冒烟全部通过 =====")
for p in PASS:
    print("  [PASS]", p)
print(f"\n共 {len(PASS)} 项通过")
