-- R2 作业采集：response_logs 补列（学科/年级/班级/作业类型）
--
-- 说明：
--   * 后端 init_db() 已无条件幂等执行 _ensure_response_log_extra_columns()，
--     正常情况下重启后端即可自动补列，无需手工执行本脚本。
--   * 若生产 DB 账号为 DML-only（无 ALTER 权限），请由 DBA 执行本脚本一次。
--   * 语句为跨方言写法（ADD COLUMN ... VARCHAR NULL），MySQL 与 PostgreSQL 均可执行。
--   * subject/class_id 建表时已含（旧库若缺则一并补上）；grade/homework_type 为新增。

ALTER TABLE response_logs ADD COLUMN subject VARCHAR(64) NULL;
ALTER TABLE response_logs ADD COLUMN class_id VARCHAR(36) NULL;
ALTER TABLE response_logs ADD COLUMN grade VARCHAR(32) NULL;
ALTER TABLE response_logs ADD COLUMN homework_type VARCHAR(64) NULL;
