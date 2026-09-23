-- ============================================================================
-- E01+E02 · 五育指标层级化 + AI 素养维度（2026-08-15）
-- 对齐: 教基〔2021〕3号《义务教育质量评价指南》五方面 + 2024 教基厅函 32 号 AI 素养
--
-- 内容:
--   1) indicator_definitions 幂等补列 level / parent_id + 索引 + 自引用 FK
--   2) 6 个维度节点种子（level=1，对齐国家五方面 + AI 素养）
--   3) AI 素养方面种子（level=2，挂 dim_ai_literacy）+ 观测点种子（level=3，示例）
--   4) 老 19 条二级指标（level 默认 2）幂等回填父维度（parent_id，best-effort 无副作用）
--
-- 幂等性: information_schema 检查 + INSERT IGNORE + 条件 UPDATE；重复执行安全。
-- 兼容性:
--   - student_portfolios.dimensions 是 JSON 列，ai_literacy 为增量键，无需 DDL；
--   - student_growth_records.dimension / source_type 是 VARCHAR(32)，无 CHECK/枚举约束，
--     写入 ai_literacy / ai_course / ai_project 无需迁移，老数据可读。
-- 前置: 需先执行 2026-08-11-chunfeng-v1.sql + 2026-08-12-chunfeng-indicators-v2.sql。
-- 用法: mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-08-15-ai-literacy-hierarchy.sql
-- ============================================================================
SET NAMES utf8mb4;

-- ────────────────────────────────────────────────────────────
-- 1. indicator_definitions 幂等补列 level / parent_id + 索引 + FK
-- ────────────────────────────────────────────────────────────
SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'indicator_definitions');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'indicator_definitions' AND COLUMN_NAME = 'level');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE indicator_definitions ADD COLUMN level INT NOT NULL DEFAULT 2 COMMENT '1=维度 2=方面 3=观测点'");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'indicator_definitions' AND COLUMN_NAME = 'parent_id');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE indicator_definitions ADD COLUMN parent_id VARCHAR(36) NULL COMMENT '父节点ID，自引用'");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @i = (SELECT COUNT(*) FROM information_schema.STATISTICS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'indicator_definitions' AND INDEX_NAME = 'idx_id_parent');
SET @s = IF(@t = 0 OR @i > 0, 'SELECT 1', "ALTER TABLE indicator_definitions ADD INDEX idx_id_parent (parent_id)");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @f = (SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
          WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'indicator_definitions' AND CONSTRAINT_NAME = 'fk_id_parent');
SET @s = IF(@t = 0 OR @f > 0, 'SELECT 1', "ALTER TABLE indicator_definitions ADD CONSTRAINT fk_id_parent FOREIGN KEY (parent_id) REFERENCES indicator_definitions (id) ON DELETE SET NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- ────────────────────────────────────────────────────────────
-- 2. 维度节点种子（level=1，code=dim_<dim>，INSERT IGNORE 幂等）
-- ────────────────────────────────────────────────────────────
INSERT IGNORE INTO `indicator_definitions`
  (`id`, `dimension`, `code`, `name`, `description`, `level`, `parent_id`, `sort_order`, `is_active`, `school_id`)
VALUES
  ('ind-dim-moral',        'moral',        'dim_moral',        '品德发展',       '品德发展与行为规范（教基〔2021〕3号）', 1, NULL, 1, 1, NULL),
  ('ind-dim-intellectual', 'intellectual', 'dim_intellectual', '学业发展',       '学业水平与学习过程', 1, NULL, 2, 1, NULL),
  ('ind-dim-physical',     'physical',     'dim_physical',     '身心发展',       '体质健康与心理健康', 1, NULL, 3, 1, NULL),
  ('ind-dim-aesthetic',    'aesthetic',    'dim_aesthetic',    '审美素养',       '审美感知与艺术表现', 1, NULL, 4, 1, NULL),
  ('ind-dim-labor',        'labor',        'dim_labor',        '劳动与社会实践', '劳动习惯与社会实践', 1, NULL, 5, 1, NULL),
  ('ind-dim-ai',           'ai_literacy',  'dim_ai_literacy',  'AI 素养',        'AI 课程学习过程性成果与素养表现（2024 教基厅函 32 号）', 1, NULL, 6, 1, NULL);

-- ────────────────────────────────────────────────────────────
-- 3. AI 素养方面（level=2）+ 观测点（level=3，示例）种子
-- ────────────────────────────────────────────────────────────
INSERT IGNORE INTO `indicator_definitions`
  (`id`, `dimension`, `code`, `name`, `description`, `level`, `parent_id`, `sort_order`, `is_active`, `school_id`)
VALUES
  -- 方面（level=2）
  ('ind-ai-course',   'ai_literacy', 'ai_literacy_course',   'AI 课程学习', 'AI 课程过程性学习成果（课时/任务/测验）', 2, 'ind-dim-ai', 1, 1, NULL),
  ('ind-ai-project',  'ai_literacy', 'ai_literacy_project',  'AI 作品创作', 'AI 项目式学习作品/创新成果', 2, 'ind-dim-ai', 2, 1, NULL),
  ('ind-ai-quality',  'ai_literacy', 'ai_literacy_quality',  '素养表现',    'AI 伦理意识/协作/表达等素养表现', 2, 'ind-dim-ai', 3, 1, NULL),
  -- 观测点（level=3，示例；学校可自行下挂）
  ('ind-ai-course-basic', 'ai_literacy', 'ai_literacy_course_basic', 'AI 基础认知', 'AI 基本概念/原理理解', 3, 'ind-ai-course', 1, 1, NULL),
  ('ind-ai-course-task',  'ai_literacy', 'ai_literacy_course_task',  'AI 任务完成', 'AI 课程任务/练习完成质量', 3, 'ind-ai-course', 2, 1, NULL),
  ('ind-ai-project-idea', 'ai_literacy', 'ai_literacy_project_idea', '创意构思',   'AI 项目创意与方案设计', 3, 'ind-ai-project', 1, 1, NULL);

-- ────────────────────────────────────────────────────────────
-- 4. 老 19 条二级指标回填父维度（best-effort：维度节点不存在时保持 NULL，无副作用）
-- ────────────────────────────────────────────────────────────
UPDATE `indicator_definitions` t
  JOIN `indicator_definitions` d
    ON d.dimension = t.dimension AND d.level = 1 AND d.school_id IS NULL
   AND d.code = CONCAT('dim_', t.dimension)
   SET t.parent_id = d.id
 WHERE t.level = 2 AND t.parent_id IS NULL AND t.school_id IS NULL;
