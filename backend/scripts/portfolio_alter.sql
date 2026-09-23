-- ============================================================================
-- 种春风 · 五育画像域 幂等建表 + 增量列脚本（A-agent）
-- 契约权威：docs/contracts/99-reconciliation.md §4.1（DDL）+ §5.12（mentors）
--
-- 内容：
--   1. CREATE TABLE IF NOT EXISTS —— 5 张新表（A 域自有）：
--        student_portfolios / student_growth_records / report_snapshots /
--        assessment_comments / mentors
--   2. ALTER（information_schema 检查 + PREPARE/EXECUTE，幂等）——
--         exam_scores  ：class_avg / class_rank / class_id / school_id
--         wrong_questions：status / corrected_at / knowledge_point_id / school_id + 3 索引
--         students     ：school_id
--
-- 用法（本地验收/集成接入）：
--   mysql -h127.0.0.1 -P3307 -uroot -proot_pw_2026 grade < scripts/portfolio_alter.sql
-- 重复执行安全：已存在列/索引会被跳过，不报错、无副作用。
--
-- 依赖顺序：students / classes / users 表须先存在（create_all 或集成先跑），
-- 否则新表的外键约束会失败。
-- ============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- 1. 新表（幂等）
-- ────────────────────────────────────────────────────────────────────────────

-- 1.1 学生五育画像主表（§4.1.1）
CREATE TABLE IF NOT EXISTS student_portfolios (
    id                   VARCHAR(36)  NOT NULL,
    student_id           VARCHAR(36)  NOT NULL,
    class_id             VARCHAR(36)  NOT NULL,
    school_id            VARCHAR(36)  NULL,
    base_points          INT          NOT NULL DEFAULT 100,
    dimensions           JSON         NOT NULL,
    detail               JSON         NULL,
    auto_detail          JSON         NULL,
    total_growth_point   DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    last_calculated_at   DATETIME     NULL,
    created_at           DATETIME     NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME     NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_sp_student_id (student_id),
    KEY idx_sp_class_id (class_id),
    CONSTRAINT fk_sp_student FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
    CONSTRAINT fk_sp_class   FOREIGN KEY (class_id)   REFERENCES classes  (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1.2 学生成长记录流水表（§4.1.2）
CREATE TABLE IF NOT EXISTS student_growth_records (
    id            VARCHAR(36)  NOT NULL,
    student_id    VARCHAR(36)  NOT NULL,
    class_id      VARCHAR(36)  NOT NULL,
    school_id     VARCHAR(36)  NULL,
    dimension     VARCHAR(32)  NOT NULL,
    source_type   VARCHAR(32)  NOT NULL DEFAULT 'manual',
    source_id     VARCHAR(36)  NULL,
    growth_points INT          NOT NULL DEFAULT 0,
    evidence      JSON         NULL,
    note          VARCHAR(512) NULL,
    created_by    VARCHAR(36)  NULL,
    occurred_at   DATETIME     NULL,
    created_at    DATETIME     NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_sgr_student_id (student_id),
    KEY idx_sgr_student_dim (student_id, dimension),
    KEY idx_sgr_student_time (student_id, occurred_at),
    KEY idx_sgr_source (source_type, source_id),
    CONSTRAINT fk_sgr_student  FOREIGN KEY (student_id)  REFERENCES students (id) ON DELETE CASCADE,
    CONSTRAINT fk_sgr_class    FOREIGN KEY (class_id)    REFERENCES classes  (id) ON DELETE CASCADE,
    CONSTRAINT fk_sgr_creator  FOREIGN KEY (created_by)  REFERENCES users     (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1.3 学期报告快照（§4.1.3，冻结不可变，无 updated_at）
CREATE TABLE IF NOT EXISTS report_snapshots (
    id            VARCHAR(36) NOT NULL,
    student_id    VARCHAR(36) NOT NULL,
    class_id      VARCHAR(36) NOT NULL,
    school_id     VARCHAR(36) NULL,
    term          VARCHAR(32) NOT NULL,
    version       INT         NOT NULL DEFAULT 1,
    parent_id     VARCHAR(36) NULL,
    payload       JSON        NOT NULL,
    generated_by  VARCHAR(36) NOT NULL,
    created_at    DATETIME    NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_rs_student_term_version (student_id, term, version),
    KEY idx_rs_class_term (class_id, term),
    CONSTRAINT fk_rs_student     FOREIGN KEY (student_id)    REFERENCES students (id) ON DELETE CASCADE,
    CONSTRAINT fk_rs_parent      FOREIGN KEY (parent_id)     REFERENCES report_snapshots (id) ON DELETE SET NULL,
    CONSTRAINT fk_rs_generator   FOREIGN KEY (generated_by)  REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_rs_class       FOREIGN KEY (class_id)      REFERENCES classes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1.4 AI 学期评语表（§4.1.4）
CREATE TABLE IF NOT EXISTS assessment_comments (
    id                 VARCHAR(36) NOT NULL,
    student_id         VARCHAR(36) NOT NULL,
    class_id           VARCHAR(36) NOT NULL,
    school_id          VARCHAR(36) NULL,
    term               VARCHAR(32) NOT NULL,
    status             VARCHAR(16) NOT NULL DEFAULT 'ai_generated',
    ai_content         TEXT        NULL,
    confirmed_content  TEXT        NULL,
    ai_model           VARCHAR(64) NULL,
    tokens_used        INT         NULL,
    cost_cent          INT         NULL,
    gate_flagged       TINYINT(1)  NOT NULL DEFAULT 0,
    created_by         VARCHAR(36) NOT NULL,
    confirmed_by       VARCHAR(36) NULL,
    confirmed_at       DATETIME    NULL,
    created_at         DATETIME    NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME    NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ac_student_term (student_id, term),
    KEY idx_ac_class_term (class_id, term),
    CONSTRAINT fk_ac_student      FOREIGN KEY (student_id)   REFERENCES students (id) ON DELETE CASCADE,
    CONSTRAINT fk_ac_class        FOREIGN KEY (class_id)     REFERENCES classes  (id) ON DELETE CASCADE,
    CONSTRAINT fk_ac_creator      FOREIGN KEY (created_by)   REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_ac_confirmer    FOREIGN KEY (confirmed_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 1.5 学生导师指派表（00 §5.12，guardian 留位）
CREATE TABLE IF NOT EXISTS mentors (
    id            VARCHAR(36) NOT NULL,
    student_id    VARCHAR(36) NOT NULL,
    user_id       VARCHAR(36) NOT NULL,
    role          VARCHAR(16) NOT NULL DEFAULT 'tutor',
    assigned_by   VARCHAR(36) NULL,
    status        VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at    DATETIME    NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME    NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_mtr_student_user (student_id, user_id),
    KEY idx_mtr_user_id (user_id),
    CONSTRAINT fk_mtr_student FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
    CONSTRAINT fk_mtr_user    FOREIGN KEY (user_id)    REFERENCES users    (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ────────────────────────────────────────────────────────────────────────────
-- 2. 既有表增量列 / 索引（幂等：information_schema 检查 + PREPARE/EXECUTE）
-- ────────────────────────────────────────────────────────────────────────────

-- 2.1 exam_scores
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores' AND COLUMN_NAME = 'class_avg');
SET @s = IF(@c = 0, 'ALTER TABLE exam_scores ADD COLUMN class_avg DECIMAL(10,2) NULL', 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores' AND COLUMN_NAME = 'class_rank');
SET @s = IF(@c = 0, 'ALTER TABLE exam_scores ADD COLUMN class_rank INT NULL', 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores' AND COLUMN_NAME = 'class_id');
SET @s = IF(@c = 0, 'ALTER TABLE exam_scores ADD COLUMN class_id VARCHAR(36) NULL', 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores' AND COLUMN_NAME = 'school_id');
SET @s = IF(@c = 0, 'ALTER TABLE exam_scores ADD COLUMN school_id VARCHAR(36) NULL', 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- 2.2 wrong_questions（列 + 3 索引）
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND COLUMN_NAME = 'status');
SET @s = IF(@c = 0, "ALTER TABLE wrong_questions ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'open'", 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND COLUMN_NAME = 'corrected_at');
SET @s = IF(@c = 0, 'ALTER TABLE wrong_questions ADD COLUMN corrected_at DATETIME NULL', 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND COLUMN_NAME = 'knowledge_point_id');
SET @s = IF(@c = 0, 'ALTER TABLE wrong_questions ADD COLUMN knowledge_point_id VARCHAR(36) NULL', 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND COLUMN_NAME = 'school_id');
SET @s = IF(@c = 0, 'ALTER TABLE wrong_questions ADD COLUMN school_id VARCHAR(36) NULL', 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @i = (SELECT COUNT(*) FROM information_schema.STATISTICS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND INDEX_NAME = 'idx_wq_status');
SET @s = IF(@i = 0, 'ALTER TABLE wrong_questions ADD INDEX idx_wq_status (student_id, status)', 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @i = (SELECT COUNT(*) FROM information_schema.STATISTICS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND INDEX_NAME = 'idx_wq_kp');
SET @s = IF(@i = 0, 'ALTER TABLE wrong_questions ADD INDEX idx_wq_kp (student_id, knowledge_point_id, status)', 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @i = (SELECT COUNT(*) FROM information_schema.STATISTICS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND INDEX_NAME = 'idx_wq_corrected');
SET @s = IF(@i = 0, 'ALTER TABLE wrong_questions ADD INDEX idx_wq_corrected (student_id, corrected_at)', 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- 2.3 students
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'students' AND COLUMN_NAME = 'school_id');
SET @s = IF(@c = 0, 'ALTER TABLE students ADD COLUMN school_id VARCHAR(36) NULL', 'SELECT 1');
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
