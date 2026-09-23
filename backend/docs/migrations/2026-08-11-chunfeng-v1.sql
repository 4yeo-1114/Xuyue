-- ============================================================================
-- 种春风 Wave 1 · 生产迁移脚本 v1（integration 收口）
-- 日期: 2026-08-11 | 契约权威: docs/contracts/99-reconciliation.md
--
-- 内容:
--   1) 5 张新表（A 画像域）: student_portfolios / student_growth_records /
--      report_snapshots / assessment_comments / mentors
--   2) 5 张新表（B 测评域）: assessment_definitions / assessment_sessions /
--      assessment_results / assessment_answers / parent_students
--   3) 14 张新表（C 学生运营域）: badge_definitions / badge_awards / credit_accounts /
--      credit_transactions / reward_products / redemption_records / practice_records /
--      campus_clubs / club_enrollments / club_attendance / book_borrows /
--      reading_records / health_checks / student_tasks
--   4) 3 张既有表幂等 ALTER: exam_scores / wrong_questions / students
--
-- 幂等性: 全部 CREATE TABLE IF NOT EXISTS；ALTER 先查 information_schema 判断列/索引/
-- 表是否存在，不存在即跳过，重复执行安全。
-- 前置: 基础表（users/classes/students 及 exam_scores/wrong_questions）须已存在；
--      本脚本不建基础表（若表缺失，对应 ALTER 自动跳过，不影响新表创建）。
-- 用法: mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> <DB> < docs/migrations/2026-08-11-chunfeng-v1.sql
-- ============================================================================
SET NAMES utf8mb4;

-- ────────────────────────────────────────────────────────────
-- 1. 新表（按外键依赖顺序，全部幂等）
-- ────────────────────────────────────────────────────────────

-- student_portfolios
CREATE TABLE IF NOT EXISTS `student_portfolios` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `school_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `base_points` int NOT NULL DEFAULT '100',
  `dimensions` json NOT NULL,
  `detail` json DEFAULT NULL,
  `auto_detail` json DEFAULT NULL,
  `total_growth_point` decimal(10,2) NOT NULL DEFAULT '0.00',
  `last_calculated_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sp_student_id` (`student_id`),
  KEY `idx_sp_class_id` (`class_id`),
  CONSTRAINT `student_portfolios_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `student_portfolios_ibfk_2` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- student_growth_records
CREATE TABLE IF NOT EXISTS `student_growth_records` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `school_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `dimension` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `growth_points` int NOT NULL DEFAULT '0',
  `evidence` text COLLATE utf8mb4_unicode_ci,
  `note` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_by` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `occurred_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_sgr_student` (`student_id`),
  KEY `ix_sgr_source` (`source_type`,`source_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- report_snapshots
CREATE TABLE IF NOT EXISTS `report_snapshots` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `school_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `term` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `version` int NOT NULL,
  `parent_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `payload` json NOT NULL,
  `generated_by` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rs_student_term_version` (`student_id`,`term`,`version`),
  KEY `parent_id` (`parent_id`),
  KEY `generated_by` (`generated_by`),
  KEY `idx_rs_class_term` (`class_id`,`term`),
  CONSTRAINT `report_snapshots_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `report_snapshots_ibfk_2` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `report_snapshots_ibfk_3` FOREIGN KEY (`parent_id`) REFERENCES `report_snapshots` (`id`) ON DELETE SET NULL,
  CONSTRAINT `report_snapshots_ibfk_4` FOREIGN KEY (`generated_by`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- assessment_comments
CREATE TABLE IF NOT EXISTS `assessment_comments` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `school_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `term` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ai_content` text COLLATE utf8mb4_unicode_ci,
  `confirmed_content` text COLLATE utf8mb4_unicode_ci,
  `ai_model` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `tokens_used` int DEFAULT NULL,
  `cost_cent` int DEFAULT NULL,
  `gate_flagged` tinyint(1) NOT NULL DEFAULT '0',
  `created_by` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `confirmed_by` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `confirmed_at` datetime DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ac_student_term` (`student_id`,`term`),
  KEY `created_by` (`created_by`),
  KEY `confirmed_by` (`confirmed_by`),
  KEY `idx_ac_class_term` (`class_id`,`term`),
  CONSTRAINT `assessment_comments_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `assessment_comments_ibfk_2` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `assessment_comments_ibfk_3` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `assessment_comments_ibfk_4` FOREIGN KEY (`confirmed_by`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- mentors
CREATE TABLE IF NOT EXISTS `mentors` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `assigned_by` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_mtr_student_user` (`student_id`,`user_id`),
  KEY `idx_mtr_user_id` (`user_id`),
  CONSTRAINT `mentors_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `mentors_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- assessment_definitions
CREATE TABLE IF NOT EXISTS `assessment_definitions` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '题组名称',
  `domain` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '测评域: personality/interest/learning_style/self_built_survey',
  `grade_range` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '适用学段: primary/junior/senior/all',
  `version` int NOT NULL COMMENT '版本号，从1开始递增',
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '状态: draft/active/retired',
  `consent_required` tinyint(1) NOT NULL COMMENT '是否需要监护人同意',
  `questions` json NOT NULL COMMENT '题面数组（见 B0 §2.1 questions JSON 结构）',
  `description` text COLLATE utf8mb4_unicode_ci COMMENT '题组说明/指导语',
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `idx_ad_domain` (`domain`),
  KEY `idx_ad_status` (`status`),
  KEY `idx_ad_domain_status` (`domain`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- assessment_sessions
CREATE TABLE IF NOT EXISTS `assessment_sessions` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '学生ID → students.id',
  `definition_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '题组定义ID → assessment_definitions.id',
  `test_mode` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '施测模式: class_batch/self',
  `batch_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '批次ID（class_batch模式下关联同一批次）',
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '状态: pending/in_progress/submitted/graded/canceled',
  `proctored_by` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '监考/施测教师ID → users.id',
  `created_by` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '会话创建者ID → users.id',
  `taken_at` datetime DEFAULT NULL COMMENT '学生开始作答时间',
  `submitted_at` datetime DEFAULT NULL COMMENT '提交时间',
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `student_id` (`student_id`),
  KEY `idx_as_definition` (`definition_id`),
  CONSTRAINT `assessment_sessions_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `assessment_sessions_ibfk_2` FOREIGN KEY (`definition_id`) REFERENCES `assessment_definitions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- assessment_results
CREATE TABLE IF NOT EXISTS `assessment_results` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '学生ID → students.id',
  `definition_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '题组定义ID → assessment_definitions.id',
  `session_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '关联会话ID → assessment_sessions.id',
  `domain` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '测评域，继承自题组的domain',
  `purpose` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用途: 强制anchor（锚点），DB约束兜底',
  `tag_schema` json NOT NULL COMMENT '白名单标签结果 {labels, dimension_percents, generated_at}',
  `raw_score` json DEFAULT NULL COMMENT '原始作答数据 {answers, dimension_points, total_answered}',
  `guardian_consent` json NOT NULL COMMENT '监护人同意状态 {status, version, granted_at, withdrawn_at}',
  `created_by` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '创建者ID → users.id',
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `idx_ar_domain` (`domain`),
  KEY `idx_ar_session` (`session_id`),
  KEY `idx_ar_definition` (`definition_id`),
  KEY `idx_ar_student` (`student_id`),
  CONSTRAINT `assessment_results_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `assessment_results_ibfk_2` FOREIGN KEY (`definition_id`) REFERENCES `assessment_definitions` (`id`) ON DELETE SET NULL,
  CONSTRAINT `assessment_results_ibfk_3` FOREIGN KEY (`session_id`) REFERENCES `assessment_sessions` (`id`) ON DELETE SET NULL,
  CONSTRAINT `chk_ar_purpose` CHECK ((`purpose` = _utf8mb4'anchor'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- assessment_answers
CREATE TABLE IF NOT EXISTS `assessment_answers` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '锚点结果ID → assessment_results.id',
  `question_id` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '题号，如 ls_q1',
  `option_key` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '选择的选项键',
  `dim` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '顶层维度键',
  `option_dim` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '子维度键',
  `created_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `idx_aa_result` (`result_id`),
  KEY `idx_aa_result_question` (`result_id`,`question_id`),
  CONSTRAINT `assessment_answers_ibfk_1` FOREIGN KEY (`result_id`) REFERENCES `assessment_results` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- parent_students
CREATE TABLE IF NOT EXISTS `parent_students` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `parent_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '家长 user ID → users.id（role 应含 parent）',
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '学生ID → students.id',
  `relation` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '关系: guardian/father/mother/other',
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '状态: active/inactive',
  `created_by` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '创建者ID → users.id',
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ps_pair` (`parent_id`,`student_id`),
  KEY `idx_ps_parent` (`parent_id`),
  KEY `idx_ps_student` (`student_id`),
  CONSTRAINT `parent_students_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `parent_students_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- badge_definitions
CREATE TABLE IF NOT EXISTS `badge_definitions` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `badge_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `category` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `icon_url` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `points_awarded` int NOT NULL,
  `min_grade` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `max_grade` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_active` int NOT NULL,
  `sort_order` int NOT NULL,
  `created_by` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_badge_definitions_category` (`category`),
  KEY `ix_badge_definitions_is_active` (`is_active`),
  KEY `ix_badge_definitions_created_by` (`created_by`),
  KEY `ix_badge_definitions_badge_type` (`badge_type`),
  CONSTRAINT `badge_definitions_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- badge_awards
CREATE TABLE IF NOT EXISTS `badge_awards` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `badge_definition_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `awarded_by` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `award_date` date NOT NULL,
  `reason` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `credit_transaction_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_student_badge_date` (`student_id`,`badge_definition_id`,`award_date`),
  KEY `ix_badge_awards_award_date` (`award_date`),
  KEY `ix_badge_awards_badge_definition_id` (`badge_definition_id`),
  KEY `ix_badge_awards_awarded_by` (`awarded_by`),
  KEY `ix_badge_awards_student_id` (`student_id`),
  KEY `ix_badge_awards_class_id` (`class_id`),
  CONSTRAINT `badge_awards_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `badge_awards_ibfk_2` FOREIGN KEY (`badge_definition_id`) REFERENCES `badge_definitions` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `badge_awards_ibfk_3` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `badge_awards_ibfk_4` FOREIGN KEY (`awarded_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- credit_accounts
CREATE TABLE IF NOT EXISTS `credit_accounts` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `balance` int NOT NULL,
  `total_earned` int NOT NULL,
  `total_spent` int NOT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_credit_account_student` (`student_id`),
  KEY `ix_credit_accounts_student_id` (`student_id`),
  CONSTRAINT `credit_accounts_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- credit_transactions
CREATE TABLE IF NOT EXISTS `credit_transactions` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount` int NOT NULL,
  `transaction_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `balance_after` int NOT NULL,
  `source_type` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `operator_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_credit_transactions_transaction_type` (`transaction_type`),
  KEY `ix_credit_transactions_class_id` (`class_id`),
  KEY `ix_credit_transactions_student_id` (`student_id`),
  KEY `ix_credit_transactions_created_at` (`created_at`),
  KEY `idx_ct_source` (`source_type`,`source_id`),
  KEY `ix_credit_transactions_operator_id` (`operator_id`),
  CONSTRAINT `credit_transactions_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `credit_transactions_ibfk_2` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `credit_transactions_ibfk_3` FOREIGN KEY (`operator_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- reward_products
CREATE TABLE IF NOT EXISTS `reward_products` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `image_url` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `product_type` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `points_required` int NOT NULL,
  `stock` int NOT NULL,
  `stock_warning` int NOT NULL,
  `is_active` int NOT NULL,
  `exchange_limit_per_student` int NOT NULL,
  `sort_order` int NOT NULL,
  `created_by` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_reward_products_product_type` (`product_type`),
  KEY `ix_reward_products_created_by` (`created_by`),
  KEY `ix_reward_products_is_active` (`is_active`),
  CONSTRAINT `reward_products_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- redemption_records
CREATE TABLE IF NOT EXISTS `redemption_records` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `product_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `points_spent` int NOT NULL,
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `operator_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `approver_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `approved_at` datetime DEFAULT NULL,
  `delivered_at` datetime DEFAULT NULL,
  `notes` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `credit_transaction_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_redemption_records_student_id` (`student_id`),
  KEY `ix_redemption_records_status` (`status`),
  KEY `ix_redemption_records_approver_id` (`approver_id`),
  KEY `ix_redemption_records_created_at` (`created_at`),
  KEY `ix_redemption_records_operator_id` (`operator_id`),
  KEY `ix_redemption_records_class_id` (`class_id`),
  KEY `ix_redemption_records_product_id` (`product_id`),
  CONSTRAINT `redemption_records_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `redemption_records_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `reward_products` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `redemption_records_ibfk_3` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `redemption_records_ibfk_4` FOREIGN KEY (`operator_id`) REFERENCES `users` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `redemption_records_ibfk_5` FOREIGN KEY (`approver_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- practice_records
CREATE TABLE IF NOT EXISTS `practice_records` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `practice_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `practice_date` date NOT NULL,
  `duration_hours` decimal(4,1) DEFAULT NULL,
  `location` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `evidence_images` json DEFAULT NULL,
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reviewer_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `review_comment` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reviewed_at` datetime DEFAULT NULL,
  `credit_transaction_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `recorded_by` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_practice_records_practice_date` (`practice_date`),
  KEY `ix_practice_records_recorded_by` (`recorded_by`),
  KEY `ix_practice_records_student_id` (`student_id`),
  KEY `ix_practice_records_practice_type` (`practice_type`),
  KEY `ix_practice_records_status` (`status`),
  KEY `ix_practice_records_reviewer_id` (`reviewer_id`),
  KEY `ix_practice_records_class_id` (`class_id`),
  CONSTRAINT `practice_records_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `practice_records_ibfk_2` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `practice_records_ibfk_3` FOREIGN KEY (`reviewer_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `practice_records_ibfk_4` FOREIGN KEY (`recorded_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- campus_clubs
CREATE TABLE IF NOT EXISTS `campus_clubs` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `teacher_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `max_members` int NOT NULL,
  `is_active` int NOT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_campus_clubs_teacher_id` (`teacher_id`),
  CONSTRAINT `campus_clubs_ibfk_1` FOREIGN KEY (`teacher_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- club_enrollments
CREATE TABLE IF NOT EXISTS `club_enrollments` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `club_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `enrolled_at` date NOT NULL,
  `left_at` date DEFAULT NULL,
  `recorded_by` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_student_club` (`student_id`,`club_id`),
  KEY `ix_club_enrollments_club_id` (`club_id`),
  KEY `ix_club_enrollments_status` (`status`),
  KEY `ix_club_enrollments_student_id` (`student_id`),
  KEY `ix_club_enrollments_class_id` (`class_id`),
  KEY `ix_club_enrollments_recorded_by` (`recorded_by`),
  CONSTRAINT `club_enrollments_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `club_enrollments_ibfk_2` FOREIGN KEY (`club_id`) REFERENCES `campus_clubs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `club_enrollments_ibfk_3` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `club_enrollments_ibfk_4` FOREIGN KEY (`recorded_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- club_attendance
CREATE TABLE IF NOT EXISTS `club_attendance` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `club_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_date` date NOT NULL,
  `attend_status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `remarks` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `recorded_by` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_student_club_date` (`student_id`,`club_id`,`session_date`),
  KEY `ix_club_attendance_recorded_by` (`recorded_by`),
  KEY `ix_club_attendance_club_id` (`club_id`),
  KEY `ix_club_attendance_session_date` (`session_date`),
  KEY `ix_club_attendance_student_id` (`student_id`),
  KEY `ix_club_attendance_class_id` (`class_id`),
  CONSTRAINT `club_attendance_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `club_attendance_ibfk_2` FOREIGN KEY (`club_id`) REFERENCES `campus_clubs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `club_attendance_ibfk_3` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `club_attendance_ibfk_4` FOREIGN KEY (`recorded_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- book_borrows
CREATE TABLE IF NOT EXISTS `book_borrows` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `book_title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `book_isbn` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `book_author` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `borrowed_at` datetime NOT NULL,
  `due_at` datetime NOT NULL,
  `returned_at` datetime DEFAULT NULL,
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `recorded_by` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `notes` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_book_borrows_due_at` (`due_at`),
  KEY `ix_book_borrows_student_id` (`student_id`),
  KEY `ix_book_borrows_status` (`status`),
  KEY `ix_book_borrows_recorded_by` (`recorded_by`),
  KEY `ix_book_borrows_class_id` (`class_id`),
  CONSTRAINT `book_borrows_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `book_borrows_ibfk_2` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `book_borrows_ibfk_3` FOREIGN KEY (`recorded_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- reading_records
CREATE TABLE IF NOT EXISTS `reading_records` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `book_title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `pages_read` int NOT NULL,
  `reading_minutes` int NOT NULL,
  `reading_date` date NOT NULL,
  `recorded_by` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_reading_records_reading_date` (`reading_date`),
  KEY `ix_reading_records_class_id` (`class_id`),
  KEY `ix_reading_records_student_id` (`student_id`),
  KEY `ix_reading_records_recorded_by` (`recorded_by`),
  CONSTRAINT `reading_records_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `reading_records_ibfk_2` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `reading_records_ibfk_3` FOREIGN KEY (`recorded_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- health_checks
CREATE TABLE IF NOT EXISTS `health_checks` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `check_type` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `check_date` date NOT NULL,
  `temperature` decimal(3,1) DEFAULT NULL,
  `health_status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `symptoms` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `is_alert` int NOT NULL,
  `handled_by` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `handle_notes` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `recorded_by` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_student_check` (`student_id`,`check_type`,`check_date`),
  KEY `ix_health_checks_class_id` (`class_id`),
  KEY `ix_health_checks_student_id` (`student_id`),
  KEY `ix_health_checks_is_alert` (`is_alert`),
  KEY `ix_health_checks_recorded_by` (`recorded_by`),
  KEY `ix_health_checks_handled_by` (`handled_by`),
  KEY `ix_health_checks_check_date` (`check_date`),
  CONSTRAINT `health_checks_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `health_checks_ibfk_2` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `health_checks_ibfk_3` FOREIGN KEY (`handled_by`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `health_checks_ibfk_4` FOREIGN KEY (`recorded_by`) REFERENCES `users` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- student_tasks
CREATE TABLE IF NOT EXISTS `student_tasks` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `student_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `class_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description` text COLLATE utf8mb4_unicode_ci,
  `task_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `dimension` varchar(16) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reward_points` int NOT NULL,
  `due_date` date DEFAULT NULL,
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `completed_at` datetime DEFAULT NULL,
  `evidence_json` json DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `ix_student_tasks_student_id` (`student_id`),
  KEY `ix_student_tasks_user_id` (`user_id`),
  KEY `ix_student_tasks_due_date` (`due_date`),
  KEY `ix_student_tasks_class_id` (`class_id`),
  KEY `ix_student_tasks_status` (`status`),
  CONSTRAINT `student_tasks_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
  CONSTRAINT `student_tasks_ibfk_2` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `student_tasks_ibfk_3` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ────────────────────────────────────────────────────────────
-- 2. 既有表增量列 / 索引（幂等: information_schema 检查 + PREPARE/EXECUTE）
--    99 §4.1 ALTER 段，与 scripts/portfolio_alter.sql 同源
-- ────────────────────────────────────────────────────────────

-- 2.1 exam_scores
SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores' AND COLUMN_NAME = 'class_avg');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE exam_scores ADD COLUMN class_avg DECIMAL(10,2) NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores' AND COLUMN_NAME = 'class_rank');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE exam_scores ADD COLUMN class_rank INT NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores' AND COLUMN_NAME = 'class_id');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE exam_scores ADD COLUMN class_id VARCHAR(36) NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'exam_scores' AND COLUMN_NAME = 'school_id');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE exam_scores ADD COLUMN school_id VARCHAR(36) NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- 2.2 wrong_questions
SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND COLUMN_NAME = 'status');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE wrong_questions ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'open'");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND COLUMN_NAME = 'corrected_at');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE wrong_questions ADD COLUMN corrected_at DATETIME NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND COLUMN_NAME = 'knowledge_point_id');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE wrong_questions ADD COLUMN knowledge_point_id VARCHAR(36) NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND COLUMN_NAME = 'school_id');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE wrong_questions ADD COLUMN school_id VARCHAR(36) NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions');
SET @i = (SELECT COUNT(*) FROM information_schema.STATISTICS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND INDEX_NAME = 'idx_wq_status');
SET @s = IF(@t = 0 OR @i > 0, 'SELECT 1', "ALTER TABLE wrong_questions ADD INDEX idx_wq_status (student_id, status)");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions');
SET @i = (SELECT COUNT(*) FROM information_schema.STATISTICS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND INDEX_NAME = 'idx_wq_kp');
SET @s = IF(@t = 0 OR @i > 0, 'SELECT 1', "ALTER TABLE wrong_questions ADD INDEX idx_wq_kp (student_id, knowledge_point_id, status)");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions');
SET @i = (SELECT COUNT(*) FROM information_schema.STATISTICS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wrong_questions' AND INDEX_NAME = 'idx_wq_corrected');
SET @s = IF(@t = 0 OR @i > 0, 'SELECT 1', "ALTER TABLE wrong_questions ADD INDEX idx_wq_corrected (student_id, corrected_at)");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;

-- 2.3 students
SET @t = (SELECT COUNT(*) FROM information_schema.TABLES
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'students');
SET @c = (SELECT COUNT(*) FROM information_schema.COLUMNS
          WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'students' AND COLUMN_NAME = 'school_id');
SET @s = IF(@t = 0 OR @c > 0, 'SELECT 1', "ALTER TABLE students ADD COLUMN school_id VARCHAR(36) NULL");
PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
