-- ============================================================================
-- R3 · 身份统一 identity_link 桥表（2026-08-29）
-- 打通学校端学生（主平台 MySQL students）↔ 家长端学生（家长端 PG students）。
-- 两库身份完全割裂（id/student_number 交集均 0、学校端手机号 0 覆盖），
-- 桥表只能人工/导入起步，无法自动回填 → 桥表放家长端 PG（同库可做真 FK）。
--
-- 内容:
--   1) identity_link 表（school_db_profile_id 支持多租户，默认 'local'）
--
-- 幂等性: CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS；
--         重复执行安全（第二次命中空跑，无副作用）。
--         内联 REFERENCES 外键仅随 CREATE TABLE 首次建表时生效，重跑跳过。
-- 前置:   PG 库 students / users 表需已存在（identity_link 引用其 id 作 FK）。
-- 用法:   psql -h 127.0.0.1 -p 5432 -U postgres -d grade \
--              -f docs/migrations/2026-08-29-identity-link.sql
--         （或 psycopg2 读文件执行，见验收流程）
-- 红线:   主平台绝不写家长端 PG（identity_link 写入只走 SQL 脚本 / 人工）。
-- ============================================================================

-- ────────────────────────────────────────────────────────────
-- 1. identity_link 桥表
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS identity_link (
    id varchar(36) NOT NULL,
    school_db_profile_id varchar(36) NOT NULL DEFAULT 'local',
    school_student_id varchar(36) NOT NULL,
    parent_student_id varchar(36) NOT NULL REFERENCES students(id),
    parent_user_id varchar(36) NOT NULL REFERENCES users(id),
    link_method varchar(16) NOT NULL DEFAULT 'manual',
    confidence numeric(4,3) NOT NULL DEFAULT 0,
    source varchar(32) NULL,
    matched_by jsonb NULL,
    status varchar(16) NOT NULL DEFAULT 'active',
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    CONSTRAINT identity_link_pkey PRIMARY KEY (id),
    CONSTRAINT uq_identity_link_school UNIQUE (school_db_profile_id, school_student_id, parent_student_id),
    CONSTRAINT uq_identity_link_parent_s UNIQUE (parent_student_id),
    CONSTRAINT uq_identity_link_parent_u UNIQUE (parent_user_id, school_db_profile_id, school_student_id)
);

-- ────────────────────────────────────────────────────────────
-- 2. 索引
-- ────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_identity_link_school ON identity_link (school_db_profile_id, school_student_id);
CREATE INDEX IF NOT EXISTS idx_identity_link_parent_s ON identity_link (parent_student_id);
CREATE INDEX IF NOT EXISTS idx_identity_link_parent_u ON identity_link (parent_user_id);

-- ────────────────────────────────────────────────────────────
-- 3. 表/列注释（幂等：重复执行覆盖同名注释，无副作用）
-- ────────────────────────────────────────────────────────────
COMMENT ON TABLE identity_link IS 'R3 身份统一桥表：学校端学生(MySQL) ↔ 家长端学生(PG)';
COMMENT ON COLUMN identity_link.school_db_profile_id IS '多租户：学校端数据库 profile id，默认 local';
COMMENT ON COLUMN identity_link.school_student_id IS '学校端学生 id（主平台 MySQL students.id）';
COMMENT ON COLUMN identity_link.parent_student_id IS '家长端学生 id（家长端 PG students.id）';
COMMENT ON COLUMN identity_link.parent_user_id IS '家长端用户 id（家长端 PG users.id，家长账号）';
COMMENT ON COLUMN identity_link.link_method IS '关联方式：manual/auto/import';
COMMENT ON COLUMN identity_link.confidence IS '匹配置信度 0-1（numeric(4,3)）';
COMMENT ON COLUMN identity_link.source IS '来源标记（如 import-xxx）';
COMMENT ON COLUMN identity_link.matched_by IS '匹配依据 JSON 快照（姓名/手机号/学号等字段）';
COMMENT ON COLUMN identity_link.status IS 'active/inactive/revoked';

-- ────────────────────────────────────────────────────────────
-- 4. 验证（人工确认）
-- ────────────────────────────────────────────────────────────
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'identity_link'
ORDER BY ordinal_position;

SELECT conname, contype
FROM pg_constraint
WHERE conrelid = 'identity_link'::regclass
ORDER BY conname;
