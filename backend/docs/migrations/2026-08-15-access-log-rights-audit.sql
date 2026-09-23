-- ============================================================================
-- E03+E14 · access_logs 访问留痕表（2026-08-15）
-- 合规后台：教师/管理员代办行权 + 年度审计导出
--
-- 内容:
--   1) 幂等建 access_logs 表（CREATE TABLE IF NOT EXISTS）
--   2) 三个索引：(target_id, created_at) / (user_id, created_at) / (action)
--
-- 幂等性: CREATE TABLE IF NOT EXISTS + information_schema 检查索引；重复执行安全。
-- 兼容性: 新表增量，不影响既有表；access_logs 写失败在应用层 try/except 兜底，不阻断主流程。
-- 前置: 无（独立新表，可独立执行）。
-- 用法: mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-08-15-access-log-rights-audit.sql
-- ============================================================================
SET NAMES utf8mb4;

-- ────────────────────────────────────────────────────────────
-- 1. access_logs 表
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `access_logs` (
  `id` VARCHAR(36) NOT NULL,
  `user_id` VARCHAR(36) NOT NULL COMMENT '操作用户 → users.id',
  `user_role` VARCHAR(32) NOT NULL COMMENT '中文角色，如 管理员/班主任',
  `action` VARCHAR(32) NOT NULL COMMENT 'view_report|view_portfolio|view_growth|view_archive|ai_report|export|delete|correct|consent_change',
  `target_type` VARCHAR(32) NOT NULL COMMENT 'student|class',
  `target_id` VARCHAR(36) NOT NULL COMMENT 'student_id 或 class_id',
  `detail` JSON NULL COMMENT '补充：report_type/term/字段名等',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='访问留痕（敏感读取 + 高危行权）';

-- ────────────────────────────────────────────────────────────
-- 2. 索引（information_schema 幂等检查，重复执行不报错）
-- ────────────────────────────────────────────────────────────
SET @i = (SELECT COUNT(*) FROM information_schema.STATISTICS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'access_logs' AND INDEX_NAME = 'idx_al_target_time');
SET @s = IF(@i > 0, 'SELECT 1', 'ALTER TABLE `access_logs` ADD INDEX idx_al_target_time (`target_id`, `created_at`)');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @i = (SELECT COUNT(*) FROM information_schema.STATISTICS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'access_logs' AND INDEX_NAME = 'idx_al_user_time');
SET @s = IF(@i > 0, 'SELECT 1', 'ALTER TABLE `access_logs` ADD INDEX idx_al_user_time (`user_id`, `created_at`)');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @i = (SELECT COUNT(*) FROM information_schema.STATISTICS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'access_logs' AND INDEX_NAME = 'idx_al_action');
SET @s = IF(@i > 0, 'SELECT 1', 'ALTER TABLE `access_logs` ADD INDEX idx_al_action (`action`)');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
