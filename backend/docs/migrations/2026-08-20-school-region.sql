-- ============================================================================
-- DL1 · 学校/区域锚表 + classes.school_id（2026-08-20）
-- D1/F1 区域多校视图的数据层前置：本批只建锚表与 classes.school_id 列，不碰业务。
--
-- 内容:
--   1) regions 表（区域层级锚表：1=省 2=市 3=区县，parent_id 自引用）
--   2) schools 表（学校锚表，region_id → regions.id；db_profile_id/db_name 为跨库注册锚点）
--   3) classes 幂等补列 school_id VARCHAR(36) NULL（锚点 schools.id）
--   4) classes.school_id 外键 fk_classes_school → schools(id)（幂等）
--
-- 幂等性: CREATE TABLE IF NOT EXISTS + information_schema 检查列/外键存在才 ALTER；
--         重复执行安全（第二次命中 SELECT 1 空跑，无副作用）。
-- 前置:   classes 表需已存在（2026-08-11-chunfeng-v1.sql 已建）；schools/regions 由本脚本自建。
-- 用法:   mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-08-20-school-region.sql
-- ============================================================================
SET NAMES utf8mb4;

-- ────────────────────────────────────────────────────────────
-- 1. regions 锚表
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `regions` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4 主键',
    `name` VARCHAR(128) NOT NULL COMMENT '区域名称',
    `level` TINYINT NOT NULL DEFAULT 1 COMMENT '区域层级:1=省 2=市 3=区县',
    `parent_id` VARCHAR(36) NULL COMMENT '父区域ID（自引用，NULL=顶层）',
    `code` VARCHAR(32) NULL COMMENT '区域编码（如行政区划码）',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间(UTC)',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间(UTC)',
    `deleted_at` DATETIME NULL DEFAULT NULL COMMENT '软删除时间，NULL为未删除',
    KEY `idx_regions_parent_id` (`parent_id`),
    KEY `idx_regions_code` (`code`),
    CONSTRAINT `fk_regions_parent` FOREIGN KEY (`parent_id`) REFERENCES `regions` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='区域层级锚表';

-- ────────────────────────────────────────────────────────────
-- 2. schools 锚表
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `schools` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4 主键',
    `name` VARCHAR(128) NOT NULL COMMENT '学校名称',
    `region_id` VARCHAR(36) NULL COMMENT '所属区域ID，锚点 regions.id',
    `db_profile_id` VARCHAR(36) NULL COMMENT '跨库注册锚点，对应 multi_project_settings 的 profile',
    `db_name` VARCHAR(128) NULL COMMENT '对应库名（多租户每客户一库）',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间(UTC)',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间(UTC)',
    `deleted_at` DATETIME NULL DEFAULT NULL COMMENT '软删除时间，NULL为未删除',
    KEY `idx_schools_name` (`name`),
    KEY `idx_schools_db_profile_id` (`db_profile_id`),
    KEY `idx_schools_region_id` (`region_id`),
    CONSTRAINT `fk_schools_region` FOREIGN KEY (`region_id`) REFERENCES `regions` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学校锚表';

-- ────────────────────────────────────────────────────────────
-- 3. classes 幂等补列 school_id
--    （classes 不存在或列已存在 → 空跑，确保二次执行不报错）
-- ────────────────────────────────────────────────────────────
SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'classes');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'classes' AND COLUMN_NAME = 'school_id');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1',
            "ALTER TABLE classes ADD COLUMN school_id VARCHAR(36) NULL COMMENT '学校 ID，锚点 schools.id'");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ────────────────────────────────────────────────────────────
-- 4. classes.school_id 外键 fk_classes_school（幂等）
--    先决条件：classes 存在、school_id 列已存在（上面第 3 步）、schools 表已建（上面第 2 步）。
--    已存在约束 → 空跑；schools 表缺失 → 跳过（由第 2 步 CREATE TABLE IF NOT EXISTS 兜底）。
-- ────────────────────────────────────────────────────────────
SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'classes');
SET @col = (SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'classes' AND COLUMN_NAME = 'school_id');
SET @fk = (SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
           WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'classes' AND CONSTRAINT_NAME = 'fk_classes_school');
SET @s = IF(@t = 0 OR @col = 0 OR @fk > 0, 'SELECT 1',
            "ALTER TABLE classes ADD CONSTRAINT fk_classes_school FOREIGN KEY (school_id) REFERENCES schools (id) ON DELETE SET NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ────────────────────────────────────────────────────────────
-- 5. 验证（人工确认）
-- ────────────────────────────────────────────────────────────
SHOW CREATE TABLE `regions`;
SHOW CREATE TABLE `schools`;
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'classes' AND COLUMN_NAME = 'school_id';
SELECT CONSTRAINT_NAME, TABLE_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'classes' AND CONSTRAINT_NAME = 'fk_classes_school';
