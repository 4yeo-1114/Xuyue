-- ============================================================================
-- R2 · 多校归属收敛（school_id 级联回填，幂等可重跑）（2026-08-29）
-- 背景：
--   2026-08-20 已把 classes.school_id / user_roles.school_id 回填到「演示小学」
--   （d23434aa-1b7f-4c7b-8e88-38fbb5104686），但 students（1222 行）与
--   exam_scores（13850 行）的 school_id 仍全为 NULL（DB 有列、model 未声明/未回填）。
--   本脚本做三表级联收敛，全部以 classes.school_id / students.school_id 为数据源
--   （不硬编码学校 id，跟随班级真实归属），带 WHERE school_id IS NULL 幂等守卫。
--
-- 内容：
--   1) students       ：students.class_id → classes.school_id
--   2) exam_scores    ：优先 es.class_id → classes.school_id；
--                       若 class_id 为空（ALTER 补列但应用层未写），
--                       退而按 es.student_id → students.school_id 兜底
--   3) wrong_questions：wq.class_id → classes.school_id（当前空表，幂等空跑）
--
-- 幂等性：所有 UPDATE 带 WHERE school_id IS NULL；重复执行安全（第二次命中 0 行）。
-- 前置：classes.school_id 已回填（2026-08-20-school-backfill.sql 第 2 段）。
--       表/列缺失时 information_schema 守卫让对应语句空跑。
-- 用法：mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-08-29-school-id-convergence.sql
-- ============================================================================
SET NAMES utf8mb4;

SET @t_classes = (SELECT COUNT(*) FROM information_schema.TABLES
                  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'classes');
SET @t_students = (SELECT COUNT(*) FROM information_schema.TABLES
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'students');
SET @t_exam_scores = (SELECT COUNT(*) FROM information_schema.TABLES
                      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores');
SET @t_wrong_questions = (SELECT COUNT(*) FROM information_schema.TABLES
                          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions');

-- ────────────────────────────────────────────────────────────
-- 1. students：class_id → classes.school_id
-- ────────────────────────────────────────────────────────────
SET @s = IF(@t_classes = 0 OR @t_students = 0, 'SELECT 1', CONCAT(
    "UPDATE students st LEFT JOIN classes c ON c.id = st.class_id ",
    "SET st.school_id = c.school_id ",
    "WHERE st.school_id IS NULL AND c.school_id IS NOT NULL"));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ────────────────────────────────────────────────────────────
-- 2. exam_scores：优先 class_id → classes.school_id；
--                  class_id 为空则 student_id → students.school_id 兜底
-- ────────────────────────────────────────────────────────────
SET @s = IF(@t_classes = 0 OR @t_exam_scores = 0, 'SELECT 1', CONCAT(
    "UPDATE exam_scores es LEFT JOIN classes c ON c.id = es.class_id ",
    "SET es.school_id = c.school_id ",
    "WHERE es.school_id IS NULL AND c.school_id IS NOT NULL"));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @s = IF(@t_exam_scores = 0 OR @t_students = 0, 'SELECT 1', CONCAT(
    "UPDATE exam_scores es LEFT JOIN students st ON st.id = es.student_id ",
    "SET es.school_id = st.school_id ",
    "WHERE es.school_id IS NULL AND st.school_id IS NOT NULL"));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ────────────────────────────────────────────────────────────
-- 3. wrong_questions：class_id → classes.school_id
-- ────────────────────────────────────────────────────────────
SET @s = IF(@t_classes = 0 OR @t_wrong_questions = 0, 'SELECT 1', CONCAT(
    "UPDATE wrong_questions wq LEFT JOIN classes c ON c.id = wq.class_id ",
    "SET wq.school_id = c.school_id ",
    "WHERE wq.school_id IS NULL AND c.school_id IS NOT NULL"));
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ────────────────────────────────────────────────────────────
-- 4. 验证（人工确认）：目标 0 行 NULL
-- ────────────────────────────────────────────────────────────
SELECT COUNT(*) AS student_null_school FROM students WHERE school_id IS NULL;
SELECT COUNT(*) AS exam_null_school FROM exam_scores WHERE school_id IS NULL;
SELECT COUNT(*) AS wq_null_school FROM wrong_questions WHERE school_id IS NULL;
SELECT COUNT(*) AS student_cnt, COUNT(school_id) AS student_with_school FROM students;
SELECT COUNT(*) AS exam_cnt, COUNT(school_id) AS exam_with_school FROM exam_scores;
