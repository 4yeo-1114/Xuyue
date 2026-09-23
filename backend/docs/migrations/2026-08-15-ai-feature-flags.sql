-- ============================================================================
-- E08 · 学校级 AI 管控：feature_flags 种子（9 个默认 AI 功能开关，enabled=1）
-- 对齐：前端 Supabase seed 的 flag keys，后端 MySQL feature_flags 为唯一事实源。
--
-- 内容:
--   1) 幂等 INSERT IGNORE 写入 9 个默认 flag（key 唯一，重复执行安全）
--      - key       : 与前端 seed 对齐的功能键
--      - label     : 中文展示名
--      - enabled   : 默认 1（开启）
--      - scope     : 'global'；scope_id 留空
--
-- 幂等性: key 列有 UNIQUE 约束，INSERT IGNORE 第二遍命中唯一键跳过，重复执行安全。
-- 前置: feature_flags 表已存在（AUTO_DDL=true 时 create_all 自动建表，或前置迁移）。
--   若表不存在本脚本会报错——请先确认表结构，勿在无表库上执行。
-- 用法: mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-08-15-ai-feature-flags.sql
-- ============================================================================
SET NAMES utf8mb4;

-- 显式给 id 提供 UUID()：feature_flags.id 的缺省是 Python 侧 gen_uuid（无 DB DEFAULT），
-- 若 INSERT 不带 id 会落到空串导致唯一键冲突，整批被 IGNORE。
INSERT IGNORE INTO feature_flags (id, `key`, label, enabled, scope, scope_id, updated_by) VALUES
(UUID(), 'ai_review',     'AI 课堂讲评与班级分析', 1, 'global', NULL, 'system'),
(UUID(), 'ai_targeted',   'AI 靶向提升方案',       1, 'global', NULL, 'system'),
(UUID(), 'ai_layered',    'AI 分层教学建议',       1, 'global', NULL, 'system'),
(UUID(), 'smart_exam',    'AI 智能组卷',           1, 'global', NULL, 'system'),
(UUID(), 'smart_gen',     'AI 智能生成教案/资源',  1, 'global', NULL, 'system'),
(UUID(), 'ai_diagnosis',  'AI 学情诊断',           1, 'global', NULL, 'system'),
(UUID(), 'ai_grading',    'AI 智能批改',           1, 'global', NULL, 'system'),
(UUID(), 'ai_chat',       'AI 助教对话',           1, 'global', NULL, 'system'),
(UUID(), 'ai_comment',    'AI 学业评语',           1, 'global', NULL, 'system');
