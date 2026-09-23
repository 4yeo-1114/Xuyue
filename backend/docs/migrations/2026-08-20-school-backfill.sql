-- ============================================================================
-- DL2 · 默认学校 seed + school_id 回填（2026-08-20）
-- D1/F1 区域多校视图的数据层回填：DL1 已建 schools 锚表（初始为空），本脚本负责
-- 种出默认学校并把既有孤儿 school_id 级联回填，让 regions/schools 真正可查可用。
--
-- ⚠️ 运维模板：真实部署前需按部署确认"默认学校"语义（校名、profile id）；
--    本脚本全部幂等，重复执行安全（第二次命中空跑/0 行）。
--
-- 背景（已拍板设计口径）：
--   schools 表刚建为空，回填有"先有鸡还是先有蛋"问题。
--   解法 = 每部署种一默认学校：多租户现状 = 每客户一库
--   （multi_project_settings.json 的 db_profiles grade/ky/hn），
--   单部署库内所有班级归属同一部署学校。
--
-- 内容:
--   1) seed：幂等插入默认学校行（WHERE NOT EXISTS 守卫，按 profile+库名唯一）
--      - id           = 固定确定性 UUID（占位），保证同库重复执行不产生重复行
--      - name         = CONCAT('默认学校-', LEFT(@db_profile_id,8))，运维可改为真实校名
--      - region_id    = NULL（区域归属由 D1/F1 后续维护）
--      - db_profile_id= @db_profile_id（当前部署 profile，跨库注册锚点）
--      - db_name      = DATABASE()（当前库名）
--   2) 回填 classes.school_id：NULL → 默认学校（已回填的不再动）
--   3) 级联回填孤儿列（全部带 WHERE school_id IS NULL，幂等）：
--      - students        ：students.class_id → classes.school_id（class_id 非空）
--      - wrong_questions ：wq.class_id       → classes.school_id（class_id 非空）
--      - exam_scores     ：优先 es.class_id  → classes.school_id；
--                          若 class_id 为空（alter_schema 补列但应用层未写 class_id），
--                          退而按 es.student_id → students.school_id 兜底
--      - indicator_definitions / student_portfolios / student_growth_records /
--        report_snapshots / assessment_comments：虽有 school_id 列但无明确、稳定的
--        数据源，本批不回填，需手动/后续确认（见契约 14 §6 备忘）。
--
-- 幂等性: schools 表不存在 → 全脚本空跑；seed 用 WHERE NOT EXISTS；
--         所有 UPDATE 带 WHERE school_id IS NULL；重复执行安全。
-- 前置:   先执行 docs/migrations/2026-08-20-school-region.sql（DL1：锚表 + classes.school_id）。
--         本脚本假设 students/exam_scores/wrong_questions 已存在且含 school_id 列
--         （app/services/portfolio/alter_schema.py 已幂等补齐；表/列缺失时对应语句空跑）。
-- 用法:   mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-08-20-school-backfill.sql
-- ============================================================================
SET NAMES utf8mb4;

-- ────────────────────────────────────────────────────────────
-- 0. 运维必填 + 前置守卫
-- ────────────────────────────────────────────────────────────
-- ⚠️ 运维必填：当前部署的 profile id（multi_project_settings.json db_profiles[].id）。
--    例：grade 库 '88b88f93-19da-4933-8e8d-8a9748cda215'；ky 库
--        '801df40a-585a-4395-826e-6670aa03c0f7'；hn 库 'a697fd24-b731-458a-a7bf-4ffb474474f5'。
--    未替换时 seed 会以占位值注册（幂等但不推荐），务必按部署替换后再执行。
SET @db_profile_id = 'REPLACE_WITH_PROFILE_ID';

SET @t_schools = (SELECT COUNT(*) FROM information_schema.TABLES
                  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'schools');
SET @t_classes = (SELECT COUNT(*) FROM information_schema.TABLES
                  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'classes');
SET @t_students = (SELECT COUNT(*) FROM information_schema.TABLES
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'students');
SET @t_exam_scores = (SELECT COUNT(*) FROM information_schema.TABLES
                      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores');
SET @t_wrong_questions = (SELECT COUNT(*) FROM information_schema.TABLES
                          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions');

-- 默认学校 ID：固定确定性字面量（占位）。单部署库内只有一所默认学校，同库重复执行只产生一行；
-- 跨库唯一注册锚点是 (db_profile_id, db_name)，D1/F1 跨校聚合以 db_profile_id 为准，
-- 局部 school.id 不要求全局唯一（多部署各自库内独立）。若未来单库确需多校，
-- 请改用由 db_profile_id 派生的 UUID v5 id 并保持幂等守卫（见契约 14 §5）。
SET @default_school_id = '11111111-1111-4111-8111-111111111111';

-- ────────────────────────────────────────────────────────────
-- 1. seed：幂等插入默认学校
-- ────────────────────────────────────────────────────────────
-- 注：比较两侧用 BINARY 强制字节比较，规避 user variable / DATABASE() 的连接 charset
-- （MySQL 8 默认 utf8mb4_0900_ai_ci、旧版 utf8mb3）与列 collation（utf8mb4_unicode_ci）
-- 不一致导致的 1267/1253 错误；<=> 为 null-safe 相等，@db_profile_id 为 NULL 时也幂等。
SET @s = IF(@t_schools = 0, 'SELECT 1', CONCAT(
    "INSERT INTO schools (id, name, region_id, db_profile_id, db_name, created_at, updated_at) ",
    "SELECT @default_school_id, CONCAT('默认学校-', COALESCE(LEFT(@db_profile_id, 8), 'unknown')), ",
    "NULL, @db_profile_id, DATABASE(), NOW(), NOW() ",
    "WHERE NOT EXISTS (SELECT 1 FROM schools s ",
    "WHERE BINARY s.db_profile_id <=> BINARY @db_profile_id ",
    "AND BINARY s.db_name <=> BINARY DATABASE())"));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ────────────────────────────────────────────────────────────
-- 2. 回填 classes.school_id → 默认学校（已回填的不再动）
-- ────────────────────────────────────────────────────────────
SET @s = IF(@t_schools = 0 OR @t_classes = 0, 'SELECT 1', CONCAT(
    "UPDATE classes SET school_id = @default_school_id WHERE school_id IS NULL"));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ────────────────────────────────────────────────────────────
-- 3. 级联回填孤儿列（均带 WHERE school_id IS NULL，幂等）
-- ────────────────────────────────────────────────────────────
-- 3.1 students：class_id → classes.school_id
SET @s = IF(@t_schools = 0 OR @t_classes = 0 OR @t_students = 0, 'SELECT 1', CONCAT(
    "UPDATE students st LEFT JOIN classes c ON c.id = st.class_id ",
    "SET st.school_id = c.school_id ",
    "WHERE st.school_id IS NULL AND c.school_id IS NOT NULL"));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- 3.2 wrong_questions：class_id → classes.school_id
SET @s = IF(@t_schools = 0 OR @t_classes = 0 OR @t_wrong_questions = 0, 'SELECT 1', CONCAT(
    "UPDATE wrong_questions wq LEFT JOIN classes c ON c.id = wq.class_id ",
    "SET wq.school_id = c.school_id ",
    "WHERE wq.school_id IS NULL AND c.school_id IS NOT NULL"));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- 3.3 exam_scores：优先 class_id → classes.school_id；
--     若 class_id 为空，退而按 student_id → students.school_id 兜底
SET @s = IF(@t_schools = 0 OR @t_classes = 0 OR @t_exam_scores = 0, 'SELECT 1', CONCAT(
    "UPDATE exam_scores es LEFT JOIN classes c ON c.id = es.class_id ",
    "SET es.school_id = c.school_id ",
    "WHERE es.school_id IS NULL AND c.school_id IS NOT NULL"));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @s = IF(@t_schools = 0 OR @t_exam_scores = 0 OR @t_students = 0, 'SELECT 1', CONCAT(
    "UPDATE exam_scores es LEFT JOIN students st ON st.id = es.student_id ",
    "SET es.school_id = st.school_id ",
    "WHERE es.school_id IS NULL AND st.school_id IS NOT NULL"));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- 3.4 复杂表备注（本批不回填，需手动/后续确认）：
--     indicator_definitions / student_portfolios / student_growth_records /
--     report_snapshots / assessment_comments 均有 school_id 列
--     （app/services/portfolio/alter_schema.py:39-124），但 rows 依赖画像域计算链路写入，
--     直接 SQL 回填可能引入脏数据；已登记为"列已存在、model 后续补 / 后续链路写入"
--     （契约 14 §5 备忘），不在本批 SQL 强制 join。

-- ────────────────────────────────────────────────────────────
-- 4. 验证（人工确认）
-- ────────────────────────────────────────────────────────────
SELECT COUNT(*) AS default_school_cnt FROM schools;
SELECT COUNT(*) AS class_null_school FROM classes WHERE school_id IS NULL;
SELECT COUNT(*) AS student_null_school FROM students WHERE school_id IS NULL;
SELECT COUNT(*) AS exam_null_school FROM exam_scores WHERE school_id IS NULL;
SELECT COUNT(*) AS wq_null_school FROM wrong_questions WHERE school_id IS NULL;
SELECT id, name, region_id, db_profile_id, db_name FROM schools;
