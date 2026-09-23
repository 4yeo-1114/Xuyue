# docs/migrations/ 迁移脚本说明

本目录下 **12 个 .sql 文件为 MySQL 迁移历史脚本**（时间跨度 2026-08-11 至 2026-08-29），
全部为 MySQL 方言：

- `ENGINE=InnoDB` 建表/改表语句
- `ON UPDATE CURRENT_TIMESTAMP` 类时间戳更新
- `LONGTEXT` 大文本类型
- 反引号（`` ` ``）包裹表名/列名

**P3 业务库已迁至 PostgreSQL 后这些脚本不适用**，仅作审计追溯保留，请勿在 PG 环境执行。

迁移实施请见：`docs/融合P3-业务库迁移计划.md`。

## 历史脚本清单（12 个）

| 日期       | 文件                                   | 内容                               |
| ---------- | -------------------------------------- | ---------------------------------- |
| 2026-08-11 | 2026-08-11-chunfeng-v1.sql             | 春枫 V1 基线建表                   |
| 2026-08-12 | 2026-08-12-chunfeng-indicators-v2.sql  | 春枫指标 V2                        |
| 2026-08-15 | 2026-08-15-access-log-rights-audit.sql | 访问日志与权限审计                 |
| 2026-08-15 | 2026-08-15-ai-content-meta.sql         | AI 内容统一标识（is_ai / ai_meta） |
| 2026-08-15 | 2026-08-15-ai-feature-flags.sql        | AI 功能开关                        |
| 2026-08-15 | 2026-08-15-ai-literacy-hierarchy.sql   | AI 素养层级                        |
| 2026-08-15 | 2026-08-15-exam-score-grade.sql        | 考试成绩等级派生                   |
| 2026-08-20 | 2026-08-20-school-backfill.sql         | 学校归属回填                       |
| 2026-08-20 | 2026-08-20-school-question-bank.sql    | 学校题库                           |
| 2026-08-20 | 2026-08-20-school-region.sql           | 学校区域                           |
| 2026-08-29 | 2026-08-29-identity-link.sql           | 身份打通                           |
| 2026-08-29 | 2026-08-29-school-id-convergence.sql   | 多校归属收敛（school_id 级联回填） |
