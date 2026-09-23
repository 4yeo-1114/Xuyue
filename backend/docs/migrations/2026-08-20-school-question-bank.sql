-- ============================================================================
-- DL4a · C2 校本题库表 school_question_banks（2026-08-20）
-- C2 校本题库的数据层落地：题库唯一键 UNIQUE(school_id, fingerprint)。
-- fingerprint 为 app.utils.question_fingerprint.question_fingerprint() 的输出
-- （fp_ 前缀 + 64 位小写 hex，总长 67 字符），DL3 已交付。
--
-- 内容:
--   1) school_question_banks 表（school_id → schools.id 外键 ON DELETE CASCADE）
--
-- 幂等性: CREATE TABLE IF NOT EXISTS；重复执行安全（第二次命中空跑，无副作用）。
-- 前置:   schools 表需已存在（DL1 2026-08-20-school-region.sql 已建）。
-- 用法:   mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-08-20-school-question-bank.sql
-- ============================================================================
SET NAMES utf8mb4;

-- ────────────────────────────────────────────────────────────
-- 1. school_question_banks 校本题库表
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `school_question_banks` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4 主键',
    `school_id` VARCHAR(36) NOT NULL COMMENT '所属学校 ID，锚点 schools.id',
    `subject` VARCHAR(64) NULL COMMENT '科目',
    `question_type` VARCHAR(32) NULL COMMENT '题型',
    `question_text` TEXT NOT NULL COMMENT '题干（指纹来源）',
    `correct_answer` TEXT NULL COMMENT '参考答案',
    `knowledge_point_id` VARCHAR(36) NULL COMMENT '知识点锚点（预留，知识点锚表未定，不加外键）',
    `fingerprint` VARCHAR(67) NOT NULL COMMENT '题目稳定ID指纹，question_fingerprint 输出 fp_+64hex，总长 67',
    `difficulty` VARCHAR(16) NULL COMMENT '难度',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间(UTC)',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间(UTC)',
    `deleted_at` DATETIME NULL DEFAULT NULL COMMENT '软删除时间，NULL为未删除',
    UNIQUE KEY `uq_sqb_school_fp` (`school_id`, `fingerprint`),
    KEY `idx_sqb_school_id` (`school_id`),
    CONSTRAINT `fk_sqb_school` FOREIGN KEY (`school_id`) REFERENCES `schools` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='校本题库表';

-- ────────────────────────────────────────────────────────────
-- 2. 验证（人工确认）
-- ────────────────────────────────────────────────────────────
SHOW CREATE TABLE `school_question_banks`;
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'school_question_banks' AND COLUMN_NAME = 'fingerprint';
