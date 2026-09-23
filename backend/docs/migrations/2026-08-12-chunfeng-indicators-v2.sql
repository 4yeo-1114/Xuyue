-- ============================================================================
-- 种春风 Wave 2 · 学校二级指标字典 + 画像接入（integration 收口）
-- 日期: 2026-08-12
--
-- 内容:
--   1) 新表 indicator_definitions（学校二级评价指标字典，19 条系统默认种子）
--   2) student_growth_records 幂等补列 indicator_id + 索引 + FK fk_sgr_indicator
--   3) 19 条系统默认指标种子（school_id=NULL，INSERT IGNORE 幂等）
--
-- 口径说明:
--   indicator_id 纯归类标签，画像评分口径零改动（assessment_engine.py 不碰）；
--   手动成长记录按指标归类，C 域自动加分（实践/社团全勤/阅读之星/健康留痕）映射到对应指标。
--
-- 幂等性: CREATE TABLE IF NOT EXISTS；ALTER 先查 information_schema 判断列/索引/
-- 约束是否存在；种子用 INSERT IGNORE；重复执行安全。
-- 前置: 需先执行 2026-08-11-chunfeng-v1.sql（student_growth_records 已存在）。
-- 用法: mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-08-12-chunfeng-indicators-v2.sql
-- ============================================================================
SET NAMES utf8mb4;

-- ────────────────────────────────────────────────────────────
-- 1. 新表 indicator_definitions（幂等）
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `indicator_definitions` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `dimension` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '五育维度: moral/intellectual/physical/aesthetic/labor',
  `code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '指标编码，维度内唯一',
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '指标名称',
  `description` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `sort_order` int NOT NULL DEFAULT '0',
  `is_active` int NOT NULL DEFAULT '1',
  `school_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'NULL=系统默认指标',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_id_code_school` (`code`,`school_id`),
  KEY `idx_id_dim_active` (`dimension`,`is_active`),
  KEY `ix_indicator_definitions_dimension` (`dimension`),
  KEY `ix_indicator_definitions_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ────────────────────────────────────────────────────────────
-- 2. student_growth_records 幂等补列 indicator_id + 索引 + FK
--    （information_schema 检查 + PREPARE/EXECUTE，与 v1 同风格）
-- ────────────────────────────────────────────────────────────
SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'student_growth_records');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'student_growth_records' AND COLUMN_NAME = 'indicator_id');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE student_growth_records ADD COLUMN indicator_id VARCHAR(36) NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @i = (SELECT COUNT(*) FROM information_schema.STATISTICS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'student_growth_records' AND INDEX_NAME = 'ix_student_growth_records_indicator_id');
SET @s = IF(@t = 0 OR @i > 0, 'SELECT 1', "ALTER TABLE student_growth_records ADD INDEX ix_student_growth_records_indicator_id (indicator_id)");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @f = (SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
          WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'student_growth_records' AND CONSTRAINT_NAME = 'fk_sgr_indicator');
SET @s = IF(@t = 0 OR @f > 0, 'SELECT 1', "ALTER TABLE student_growth_records ADD CONSTRAINT fk_sgr_indicator FOREIGN KEY (indicator_id) REFERENCES indicator_definitions (id) ON DELETE SET NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ────────────────────────────────────────────────────────────
-- 3. 19 条系统默认指标种子（school_id=NULL，id=ind-<dim>-<code>）
--    INSERT IGNORE：主键/唯一键重复自动跳过，幂等
-- ────────────────────────────────────────────────────────────
INSERT IGNORE INTO `indicator_definitions`
  (`id`, `dimension`, `code`, `name`, `description`, `sort_order`, `is_active`, `school_id`)
VALUES
  -- moral 德
  ('ind-moral-behavior',      'moral', 'moral_behavior',      '日常行为表现', '日常言谈举止、校规遵守等', 1, 1, NULL),
  ('ind-moral-activity',      'moral', 'moral_activity',      '品德活动参与', '主题活动、班会、志愿服务等', 2, 1, NULL),
  ('ind-moral-responsibility','moral', 'moral_responsibility','责任担当',     '值日尽责、班级事务担当等', 3, 1, NULL),
  ('ind-moral-conduct',       'moral', 'moral_conduct',       '品行记录',     '奖惩记录、诚信表现等', 4, 1, NULL),
  -- intellectual 智
  ('ind-intellectual-grade',     'intellectual', 'intellectual_grade',    '学科成绩',   '学科测验、期中期末成绩表现', 1, 1, NULL),
  ('ind-intellectual-class',     'intellectual', 'intellectual_class',    '课堂表现',   '课堂参与、回答问题、专注度', 2, 1, NULL),
  ('ind-intellectual-homework',  'intellectual', 'intellectual_homework', '作业情况',   '作业完成度与质量', 3, 1, NULL),
  ('ind-intellectual-ability',   'intellectual', 'intellectual_ability',  '学习能力',   '自主学习、学习方法、思维拓展', 4, 1, NULL),
  ('ind-intellectual-analysis',  'intellectual', 'intellectual_analysis', '学情分析',   '学情诊断、错题订正、靶向提升', 5, 1, NULL),
  -- physical 体
  ('ind-physical-fitness', 'physical', 'physical_fitness', '身体素质', '体能锻炼、运动表现、社团活动等', 1, 1, NULL),
  ('ind-physical-metrics', 'physical', 'physical_metrics', '体质指标', '身高体重、视力、晨午检留痕等', 2, 1, NULL),
  ('ind-physical-mental',  'physical', 'physical_mental',  '心理健康', '心理状态、情绪调节、适应性', 3, 1, NULL),
  ('ind-physical-habit',   'physical', 'physical_habit',   '生活习惯', '作息规律、用眼卫生、锻炼习惯', 4, 1, NULL),
  -- aesthetic 美
  ('ind-aesthetic-music',    'aesthetic', 'aesthetic_music',    '音乐',       '音乐课表现、合唱器乐活动', 1, 1, NULL),
  ('ind-aesthetic-art',      'aesthetic', 'aesthetic_art',      '美术',       '美术课表现、书画创作', 2, 1, NULL),
  ('ind-aesthetic-activity', 'aesthetic', 'aesthetic_activity', '美育活动',   '艺术展演、社团美育活动', 3, 1, NULL),
  -- labor 劳
  ('ind-labor-practice',   'labor', 'labor_practice',   '劳动实践', '家务劳动、校园劳动、志愿服务劳动', 1, 1, NULL),
  ('ind-labor-outdoor',    'labor', 'labor_outdoor',    '校外实践', '社会实践、研学劳动体验', 2, 1, NULL),
  ('ind-labor-innovation', 'labor', 'labor_innovation', '创新实践', '手工制作、科技创新、劳创结合', 3, 1, NULL);
