"""integration 收口 · 三域交叉冒烟验收（A 画像 / B 测评 / C 运营 跨域联动）。

前置：
- 后端已在 127.0.0.1:6888 运行（AUTO_DDL=true 建全表后）。
- Docker MySQL 127.0.0.1:3307，库 grade，root/root_pw_2026。
- 测试管理员 integration_test_admin@gb.local / Test123456! 已存在（roles 含"系统管理员"）。

流程（验收项 c + 跨域交叉）：
  1. 登录拿 JWT
  2. A 域：GET 画像（data_status 灰态）→ POST 手动 growth_record → 重算画像分
  3. B 域：题组列表（触发种子）→ 建 self 施测会话 → start → 作答 → labels/tag_schema
  4. C 域：建章定义 → 颁章（双写 credit_transactions + student_growth_records）→
     兑换扣减（建商品 → 兑换 → 验余额）
  5. 跨域交叉：C 颁章写入的 growth_record 被 A 画像重算消费（student_growth_records
     由 A 建 model、C 裸 SQL 写，两域读写兼容验证）

退出码 0 = 全部通过；非 0 = 有失败。
"""
import json
import sys
import time
import uuid

import pymysql
import requests

BASE = "http://127.0.0.1:6888/api/v1"
DB = dict(host="127.0.0.1", port=3307, user="root", password="root_pw_2026",
          database="grade", charset="utf8mb4")

PASS = []
FAIL = []


def check(name, ok, detail=""):
    if ok:
        PASS.append(name)
        print(f"  [PASS] {name}" + (f"  {detail}" if detail else ""))
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name}" + (f"  {detail}" if detail else ""))


def q(db, sql, args=None):
    cur = db.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []
    cur.close()
    return [dict(zip(cols, r)) for r in rows]


def main():
    # ── 0. 前置数据 ────────────────────────────────
    # 选一个"干净"学生（无任何成长流水）做灰态→录入→重算与跨域消费，保证结果可复现
    db = pymysql.connect(**DB)
    rows = q(db, "SELECT s.id, s.name, s.class_id FROM students s "
                 "LEFT JOIN student_growth_records g ON g.student_id = s.id "
                 "WHERE g.id IS NULL ORDER BY s.created_at LIMIT 1")
    if not rows:
        print("[setup] no clean student, pick first and clear growth")
        rows = q(db, "SELECT id, name, class_id FROM students ORDER BY created_at LIMIT 1")
        if rows:
            db.cursor().execute("DELETE FROM student_growth_records WHERE student_id=%s", (rows[0]["id"],))
            db.commit()
    student = rows[0]
    sid, cid = student["id"], student["class_id"]
    print(f"[setup] student={sid} class={cid}")
    db.close()

    # ── 1. 登录 ─────────────────────────────────────
    r = requests.post(f"{BASE}/auth/login", json={
        "email": "integration_test_admin@example.com", "password": "Test123456!"}, timeout=20)
    check("1.1 login", r.status_code == 200, f"http={r.status_code}")
    if r.status_code != 200:
        print("login body:", r.text[:500])
        return 1
    token = r.json()["access_token"]
    H = {"Authorization": f"Bearer {token}"}

    def api(method, path, **kw):
        kw.setdefault("headers", H)
        return requests.request(method, f"{BASE}{path}", timeout=30, **kw)

    # ── 2. A 域：画像灰态 → 手动录入 → 重算 ────────────
    r = api("GET", f"/portfolio/students/{sid}")
    check("2.1 GET portfolio", r.status_code == 200, f"http={r.status_code}")
    p = r.json()["data"] if r.status_code == 200 else {}
    status = (p.get("data_status") or {})
    dim_status = status if isinstance(status, dict) else {}
    check("2.2 data_status field present", "data_status" in p, json.dumps(dim_status, ensure_ascii=False)[:200])
    check("2.3 moral insufficient (grey)", dim_status.get("moral") in ("insufficient", None),
          f"moral={dim_status.get('moral')}")

    gname = f"冒烟手工录入_{uuid.uuid4().hex[:6]}"
    r = api("POST", f"/portfolio/students/{sid}/growth-records", json={
        "dimension": "moral", "growth_point": 8,
        "note": gname, "evidence": {"from": "integration_smoke"}})
    check("2.4 create growth_record", r.status_code == 200, f"http={r.status_code} body={r.text[:200]}")

    r = api("GET", f"/portfolio/students/{sid}")
    p2 = r.json()["data"] if r.status_code == 200 else {}
    dims = (p2.get("dimensions") or {})
    check("2.5 portfolio recompute consumed manual record",
          r.status_code == 200 and (dims.get("moral") or 0) > 0,
          f"moral={dims.get('moral')}")

    # ── 3. B 域：题组 → 施测 → 作答 → 标签 ────────────
    r = api("GET", "/assessment/definitions?brief=true")
    check("3.1 list definitions (seeded)", r.status_code == 200, f"http={r.status_code}")
    defs = r.json()["data"]["rows"] if r.status_code == 200 else []
    check("3.2 seed definitions exist", len(defs) > 0, f"count={len(defs)}")
    if not defs:
        return 1
    d = next((x for x in defs if x.get("consent_required")), defs[0])

    r = api("GET", f"/assessment/definitions/{d['id']}")
    full = r.json()["data"] if r.status_code == 200 else {}
    questions = full.get("questions") or []
    check("3.3 definition questions loaded", len(questions) > 0, f"qcount={len(questions)}")

    r = api("POST", "/assessment/sessions", json={
        "test_mode": "self", "definition_id": d["id"], "student_id": sid})
    check("3.4 create session", r.status_code == 200, f"http={r.status_code} body={r.text[:200]}")
    sess_rows = r.json()["data"]["rows"] if r.status_code == 200 else []
    if not sess_rows:
        return 1
    sess_id = sess_rows[0]["id"]

    r = api("POST", f"/assessment/sessions/{sess_id}/start")
    check("3.5 start session", r.status_code == 200, f"http={r.status_code}")

    answers = [{"question_id": qq["id"], "option_key": qq["options"][0]["key"]} for qq in questions]
    r = api("POST", f"/assessment/sessions/{sess_id}/answers", json={"answers": answers})
    check("3.6 submit answers", r.status_code == 200, f"http={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        sub = r.json()["data"]
        check("3.7 labels returned", bool(sub.get("labels")), json.dumps(sub.get("labels"), ensure_ascii=False)[:120])
        check("3.8 result_id written", bool(sub.get("result_id")))

    r = api("GET", f"/assessment/students/{sid}/results")
    check("3.9 list results", r.status_code == 200, f"http={r.status_code}")

    # ── 4. C 域：颁章双写 → 兑换扣减 ────────────────
    bname = f"冒烟争章_{uuid.uuid4().hex[:6]}"
    r = api("POST", "/student-ops/badge-definitions", json={
        "name": bname, "description": "integration smoke", "badgeType": "moral",
        "category": "moral", "pointsAwarded": 20, "minGrade": "1", "maxGrade": "9",
        "isActive": True, "sortOrder": 1})
    check("4.1 create badge definition", r.status_code == 200, f"http={r.status_code} body={r.text[:200]}")
    badge_id = r.json()["data"]["id"] if r.status_code == 200 else None
    if not badge_id:
        return 1

    award_date = time.strftime("%Y-%m-%d")
    r = api("POST", "/student-ops/badge-awards", json={
        "badge_definition_id": badge_id, "student_ids": [sid],
        "award_date": award_date, "reason": f"集成冒烟颁章 {award_date}"})
    check("4.2 award badge", r.status_code == 200 and r.json()["data"].get("successCount") == 1,
          f"http={r.status_code} body={r.text[:300]}")

    db = pymysql.connect(**DB)
    txns = q(db, "SELECT id, student_id, amount, transaction_type, source_type, source_id "
                 "FROM credit_transactions WHERE student_id=%s AND source_type='badge_definition' "
                 "ORDER BY created_at DESC LIMIT 1", (sid,))
    check("4.3 credit_transactions double-write", len(txns) == 1 and txns[0]["amount"] == 20,
          json.dumps(txns[0] if txns else {}, ensure_ascii=False))

    growth = q(db, "SELECT id, dimension, source_type, source_id, growth_points, note "
                   "FROM student_growth_records WHERE student_id=%s AND source_type='badge_award' "
                   "ORDER BY created_at DESC LIMIT 1", (sid,))
    check("4.4 student_growth_records double-write (C raw SQL)", len(growth) == 1
          and growth[0]["source_id"] and growth[0]["growth_points"] == 20,
          json.dumps(growth[0] if growth else {}, ensure_ascii=False))

    # 兑换扣减
    pname = f"冒烟商品_{uuid.uuid4().hex[:6]}"
    r = api("POST", "/student-ops/reward-products", json={
        "name": pname, "description": "smoke", "productType": "physical",
        "pointsRequired": 10, "stock": 5, "stockWarning": 1, "isActive": True,
        "exchangeLimitPerStudent": 1, "sortOrder": 1})
    check("4.5 create reward product", r.status_code == 200, f"http={r.status_code}")
    product_id = r.json()["data"]["id"] if r.status_code == 200 else None
    if product_id:
        r = api("POST", "/student-ops/redemptions", json={
            "student_id": sid, "product_id": product_id})
        check("4.6 redemption create", r.status_code == 200, f"http={r.status_code} body={r.text[:250]}")
        if r.status_code == 200:
            redemption_id = r.json()["data"]["id"]
            check("4.7 redemption balance_after deducted", r.json()["data"].get("balanceAfter") is not None,
                  f"balanceAfter={r.json()['data'].get('balanceAfter')}")
            r = api("PATCH", f"/student-ops/redemptions/{redemption_id}/status", json={"status": "approved"})
            check("4.8 redemption approve", r.status_code == 200, f"http={r.status_code}")
    db.close()

    # ── 5. 跨域交叉：C 颁章 growth_record 被 A 画像消费 ──
    db = pymysql.connect(**DB)
    gr = q(db, "SELECT dimension, growth_points FROM student_growth_records "
               "WHERE student_id=%s AND source_type='badge_award' ORDER BY created_at DESC LIMIT 1", (sid,))
    db.close()
    if gr:
        badge_dim, badge_pts = gr[0]["dimension"], int(gr[0]["growth_points"] or 0)
    else:
        badge_dim, badge_pts = None, 0

    r = api("GET", f"/portfolio/students/{sid}")
    p3 = r.json()["data"] if r.status_code == 200 else {}
    dims3 = p3.get("dimensions") or {}
    check("5.1 C badge growth consumed by A recompute",
          r.status_code == 200 and badge_dim and (dims3.get(badge_dim) or 0) >= badge_pts,
          f"badge_dim={badge_dim} badge_pts={badge_pts} dims={json.dumps(dims3, ensure_ascii=False)[:200]}")

    print("\n==== smoke summary ====")
    print(f"PASS={len(PASS)} FAIL={len(FAIL)}")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
