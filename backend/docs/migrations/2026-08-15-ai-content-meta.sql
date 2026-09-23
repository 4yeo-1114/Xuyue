-- ============================================================================
-- E05 · AI 内容统一标识（隐式标识）—— 3 张 AI 生成内容表补 is_ai + ai_meta（2026-08-15）
-- 对齐：GB 45438《人工智能生成合成内容标识办法》(2025.9 强制) —— AI 生成内容必须带隐式标识(元数据)。
-- 参照：app/models/assessment_comment.py 已达标(status + ai_content + ai_model)。
--
-- 内容:
--   1) class_analysis_reports        补 is_ai TINYINT(1) NOT NULL DEFAULT 1 + ai_meta JSON NULL
--   2) class_review_sessions         补 is_ai TINYINT(1) NOT NULL DEFAULT 1 + ai_meta JSON NULL
--   3) targeted_improvement_reports  补 is_ai TINYINT(1) NOT NULL DEFAULT 1 + ai_meta JSON NULL
--
-- 取值契约（前后端锁定，勿改字段名）:
--   - is_ai   : 1 = AI 生成。这几张表全部由 AI 生成，生成时显式写 1，缺省也是 1。
--   - ai_meta : 生成元数据，如 {"generator": "qwen", "model": "qwen3.7-plus"}。
--
-- 幂等性: information_schema 检查列不存在才 ALTER；重复执行安全（第二次命中 SELECT 1 空跑）。
-- 兼容性:
--   - 仅新增列，不阻塞既有读写；老数据 is_ai 取默认 1（本就是 AI 生成），ai_meta 为空。
--   - 本批不做：assessment_comments（已达标）、report_snapshots.payload、SSE 流、grading 本地 JSON 历史。
-- 前置: 需先执行 2026-08-11-chunfeng-v1.sql（三张表均已存在）。
-- 用法: mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-08-15-ai-content-meta.sql
-- ============================================================================
SET NAMES utf8mb4;

-- ────────────────────────────────────────────────────────────
-- 1. class_analysis_reports 补列
-- ────────────────────────────────────────────────────────────
SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'class_analysis_reports');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'class_analysis_reports' AND COLUMN_NAME = 'is_ai');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1',
            "ALTER TABLE class_analysis_reports ADD COLUMN is_ai TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'AI内容统一标识(GB45438):1=AI生成'");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'class_analysis_reports');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'class_analysis_reports' AND COLUMN_NAME = 'ai_meta');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1',
            "ALTER TABLE class_analysis_reports ADD COLUMN ai_meta JSON NULL COMMENT 'AI生成元数据:{generator,model}'");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ────────────────────────────────────────────────────────────
-- 2. class_review_sessions 补列
-- ────────────────────────────────────────────────────────────
SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'class_review_sessions');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'class_review_sessions' AND COLUMN_NAME = 'is_ai');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1',
            "ALTER TABLE class_review_sessions ADD COLUMN is_ai TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'AI内容统一标识(GB45438):1=AI生成'");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'class_review_sessions');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'class_review_sessions' AND COLUMN_NAME = 'ai_meta');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1',
            "ALTER TABLE class_review_sessions ADD COLUMN ai_meta JSON NULL COMMENT 'AI生成元数据:{generator,model}'");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ────────────────────────────────────────────────────────────
-- 3. targeted_improvement_reports 补列
-- ────────────────────────────────────────────────────────────
SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'targeted_improvement_reports');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'targeted_improvement_reports' AND COLUMN_NAME = 'is_ai');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1',
            "ALTER TABLE targeted_improvement_reports ADD COLUMN is_ai TINYINT(1) NOT NULL DEFAULT 1 COMMENT 'AI内容统一标识(GB45438):1=AI生成'");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'targeted_improvement_reports');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'targeted_improvement_reports' AND COLUMN_NAME = 'ai_meta');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1',
            "ALTER TABLE targeted_improvement_reports ADD COLUMN ai_meta JSON NULL COMMENT 'AI生成元数据:{generator,model}'");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
