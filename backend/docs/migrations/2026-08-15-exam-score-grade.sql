-- ============================================================================
-- E04 · 成绩等级制：exam_scores 补 grade 列（2026-08-15）
-- 对齐：《未成年人学校保护规定》（成绩以等级呈现、不公开不排名）
--
-- 内容:
--   1) exam_scores 幂等补列 grade VARCHAR(16) NULL
--      - 取值契约：excellent | good | pass | needs_work
--      - score 为空 → grade 为空（由后端 grade_for_score 计算/落库）
--
-- 幂等性: information_schema 检查列不存在才 ALTER；重复执行安全（第二次命中 SELECT 1 空跑）。
-- 兼容性:
--   - 仅新增可空列，不阻塞既有读写；老数据 grade 为空由后端读取时按分数派生。
-- 前置: 需先执行 2026-08-11-chunfeng-v1.sql（exam_scores 表已存在）。
-- 用法: mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-08-15-exam-score-grade.sql
-- ============================================================================
SET NAMES utf8mb4;

-- ────────────────────────────────────────────────────────────
-- 1. exam_scores 幂等补列 grade
-- ────────────────────────────────────────────────────────────
SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores' AND COLUMN_NAME = 'grade');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1',
            "ALTER TABLE exam_scores ADD COLUMN grade VARCHAR(16) NULL COMMENT '成绩等级:excellent|good|pass|needs_work'");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
