-- ============================================================================
-- AI 生成历史（ai_generation_history）：智能生成课件/学案/多媒体资源「生成即落库」。
-- 对应 model: app/models/ai_generation_history.py（AiGenerationHistory）
-- 前端「智能生成」页侧边历史列表：GET /ai-resources/history（列表）+ /history/{id}（详情回填）。
-- 幂等：CREATE TABLE IF NOT EXISTS，可重复执行。
-- 用法: mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-09-07-ai-generation-history.sql
-- ============================================================================
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS ai_generation_history (
    `id` VARCHAR(36) NOT NULL,
    `user_id` VARCHAR(36) NOT NULL COMMENT '生成者 user_id（对应 users.id）',
    `gen_type` VARCHAR(32) NOT NULL COMMENT 'courseware/worksheet/multimedia',
    `subject` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '学科',
    `grade` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '年级',
    `title` VARCHAR(256) NOT NULL DEFAULT '' COMMENT '资源标题',
    `content` TEXT NOT NULL COMMENT 'Markdown 正文',
    `created_at` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_ai_gen_history_user_created` (`user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
