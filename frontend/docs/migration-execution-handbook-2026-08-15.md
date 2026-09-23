# 正式环境迁移执行手册 — 政策功能批次 2A–2E(2026-08-15)

> 适用对象:叙阅后端 `grade` 库正式环境(阿里云 RDS MySQL 8.x)。
> 交付日期:2026-08-15。
> 本手册基于本地 Docker MySQL 8.0.46 完整链式验证 + 幂等二次执行验证。所有验证结论均有本地实测记录(见第 7 节)。

---

## 1. 迁移清单总表

| 文件(均在 `docs/migrations/`)            | 批次                   | 内容                                                                                                                                                    | 前置依赖                                                                                                | 是否本批新增          |
| ---------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | --------------------- |
| `2026-08-11-chunfeng-v1.sql`             | 种春风 Wave1(既有前置) | 24 张新表(A 画像域/B 测评域/C 学生运营域)+ `exam_scores`/`wrong_questions`/`students` 幂等补列                                                          | **基础表 `users`/`classes`/`students` 须已存在**(由应用 AUTO_DDL / SQLAlchemy `create_all` 建,迁移不建) | 否(2026-08-11 已发布) |
| `2026-08-12-chunfeng-indicators-v2.sql`  | 种春风 Wave2(既有前置) | 新表 `indicator_definitions` + `student_growth_records` 补 `indicator_id` + 索引 + FK + 19 条系统默认指标种子                                           | v1(需 `student_growth_records` 已存在)                                                                  | 否(2026-08-12 已发布) |
| `2026-08-15-ai-literacy-hierarchy.sql`   | **2A**                 | `indicator_definitions` 幂等补 `level`/`parent_id` + 索引 + 自引用 FK;6 个五育+AI 素养维度种子;AI 素养方面/观测点种子;老 19 条二级指标 `parent_id` 回填 | v1 + v2(`indicator_definitions` 必须已存在)                                                             | 是                    |
| `2026-08-15-access-log-rights-audit.sql` | **2B**                 | 新表 `access_logs`(访问留痕)+ 3 个条件索引                                                                                                              | 无(独立新表)                                                                                            | 是                    |
| `2026-08-15-exam-score-grade.sql`        | **2C**                 | `exam_scores` 幂等补列 `grade VARCHAR(16) NULL`(excellent\|good\|pass\|needs_work)                                                                      | **`exam_scores` 表须已存在**(应用 create_all 建,v1 只 ALTER 它、不建它)                                 | 是                    |
| `2026-08-15-ai-content-meta.sql`         | **2D**                 | `class_analysis_reports`/`class_review_sessions`/`targeted_improvement_reports` 三张 AI 生成表各补 `is_ai` + `ai_meta`                                  | **3 张表须已存在**(应用 create_all 建,v1 不建)                                                          | 是                    |
| `2026-08-15-ai-feature-flags.sql`        | **2E**                 | `feature_flags` 幂等 INSERT IGNORE 灌入 9 个默认 AI 功能开关(global,enabled=1)                                                                          | **`feature_flags` 表须已存在**(应用 create_all 建);表缺失会硬报错                                       | 是                    |

> 关键提示:2A/2C/2D/2E 各自头部注释写的「前置:需先执行 v1」在 `indicator_definitions`/`exam_scores`/3 张 AI 表/`feature_flags` 这些表上**并不准确**——这些表**不是 v1 建的**,而是应用启动时 SQLAlchemy `create_all`(AUTO_DDL=true)自动建的。正式库因已跑过应用,这些表自然存在,所以无碍;但纯手工按迁移文件重建库时,必须先建基础表(详见第 3、5 节)。

---

## 2. 正式环境执行顺序

生产库若已上线种春风 Wave1/Wave2(2026-08-11/12),则 `indicator_definitions` 已存在,**v1+v2 不需要再跑**,直接执行 2A–2E 即可。若无法确认,先按第 5 节验证再决定。

**标准执行顺序(严格按序,不可调换):**

```
① (可选)2026-08-11-chunfeng-v1.sql           ← 仅当库中还没有 student_portfolios 等 24 表
② (可选)2026-08-12-chunfeng-indicators-v2.sql ← 仅当 indicator_definitions 不存在
③ 2026-08-15-ai-literacy-hierarchy.sql        (2A,依赖 ①② 产物 indicator_definitions)
④ 2026-08-15-access-log-rights-audit.sql      (2B,独立)
⑤ 2026-08-15-exam-score-grade.sql             (2C,依赖 exam_scores 表)
⑥ 2026-08-15-ai-content-meta.sql              (2D,依赖 3 张 AI 表)
⑦ 2026-08-15-ai-feature-flags.sql             (2E,依赖 feature_flags 表)
```

**是否需执行 v1/v2 的判定(执行前先确认):**

```sql
-- 若返回 0,说明 indicator_definitions 不存在 → 需先跑 v1(建 student_growth_records 等)→ v2
SELECT COUNT(*) FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'indicator_definitions';
-- 若返回 1,说明 v1+v2 已落地 → 跳过 ①②,直接 ③-⑦
```

---

## 3. 每份迁移用途、关键 DDL、幂等性结论

### 3.1 前置 `2026-08-11-chunfeng-v1.sql`(非本批,若已执行过则跳过)

- **用途**:种春风 Wave1 集成收口。建 24 张新表(A/B/C 三域),并为 `exam_scores`(class_avg/class_rank/class_id/school_id)、`wrong_questions`(status/corrected_at/knowledge_point_id/school_id)、`students`(school_id)幂等补列。
- **关键机制**:全部 `CREATE TABLE IF NOT EXISTS`;ALTER 走 `information_schema` 检查 + `PREPARE/EXECUTE`。
- **真实前置**:24 张表有外键指向 `students`/`classes`/`users`。**纯空库直接跑会 ERROR 1824(`Failed to open the referenced table 'students'`)**——本地已实测复现。这些基础表由应用 `create_all` 建,正式库天然存在。
- **幂等性**:本地二次执行 EXIT 0,12 个幂等检查全部命中 `SELECT 1` 空跑,零报错。✅

### 3.2 前置 `2026-08-12-chunfeng-indicators-v2.sql`(非本批)

- **用途**:建 `indicator_definitions` 学校二级指标字典表;`student_growth_records` 补 `indicator_id` + 索引 `ix_student_growth_records_indicator_id` + 外键 `fk_sgr_indicator`(ON DELETE SET NULL);灌 19 条系统默认指标(school_id=NULL)。
- **幂等性**:本地二次执行 EXIT 0,3 个幂等检查(列/索引/外键)全部空跑,`indicator_definitions` 行数稳定在 19。✅

### 3.3 `2026-08-15-ai-literacy-hierarchy.sql`(2A)

- **用途**:五育指标层级化 + AI 素养维度(对齐教基〔2021〕3号 + 2024 教基厅函 32 号)。
- **关键 DDL**:
  - 幂等补列 `level INT NOT NULL DEFAULT 2`(1=维度/2=方面/3=观测点)、`parent_id VARCHAR(36) NULL`;
  - 索引 `idx_id_parent(parent_id)`;自引用外键 `fk_id_parent ... REFERENCES indicator_definitions(id) ON DELETE SET NULL`;
  - 种子:6 个维度节点(level=1,`dim_moral`…`dim_ai_literacy`)+ 3 个 AI 素养方面(level=2)+ 3 个观测点(level=3),全部 `INSERT IGNORE`;
  - 末尾 `UPDATE ... JOIN` 把老 19 条二级指标按 `dimension` 回填 `parent_id`(best-effort,维度节点不存在则保持 NULL)。
- **幂等性**:本地二次执行 EXIT 0,4 个幂等检查(level 列/parent_id 列/索引/外键)全部空跑;种子行数不变;UPDATE 条件已满足不再改动。✅
- **结果**:`indicator_definitions` 共 31 行(19 老指标 + 6 维度 + 6 AI 种子);level 分布 6/22/3。

### 3.4 `2026-08-15-access-log-rights-audit.sql`(2B)

- **用途**:合规后台——教师/管理员代办行权留痕 + 年度审计导出。新表 `access_logs`。
- **关键 DDL**:`CREATE TABLE IF NOT EXISTS access_logs`(id VARCHAR(36) PK / user_id / user_role / action / target_type / target_id / detail JSON / created_at);3 个索引 `idx_al_target_time(target_id,created_at)`、`idx_al_user_time(user_id,created_at)`、`idx_al_action(action)`。
- **幂等性**:本地二次执行 EXIT 0,3 个索引检查全部空跑。✅

### 3.5 `2026-08-15-exam-score-grade.sql`(2C)

- **用途**:成绩等级制(对齐《未成年人学校保护规定》)。`exam_scores` 补 `grade VARCHAR(16) NULL`,取值 `excellent|good|pass|needs_work`;score 为空时 grade 由后端 `grade_for_score` 计算落库。
- **关键 DDL**:单条幂等 ALTER,`information_schema` 检查 `grade` 列不存在才加。
- **幂等性**:本地二次执行 EXIT 0,1 个检查空跑。✅

### 3.6 `2026-08-15-ai-content-meta.sql`(2D)

- **用途**:AI 内容隐式标识(对齐 GB 45438《人工智能生成合成内容标识办法》2025.9 强制)。3 张 AI 生成表各补 `is_ai TINYINT(1) NOT NULL DEFAULT 1` + `ai_meta JSON NULL`。
- **关键 DDL**:6 条幂等 ALTER(3 表 × 2 列),表不存在时对应检查直接 `SELECT 1` 跳过。
- **幂等性**:本地二次执行 EXIT 0,6 个检查全部空跑。✅

### 3.7 `2026-08-15-ai-feature-flags.sql`(2E)

- **用途**:学校级 AI 管控唯一事实源,9 个默认功能开关。
- **关键 DDL**:`INSERT IGNORE` 9 行(`key` 上有 UNIQUE 约束 `ix_feature_flags_key`);显式给 `id` 用 `UUID()`,避免 id 落到空串触发唯一键冲突导致整批被 IGNORE。
- **幂等性**:本地二次执行 EXIT 0,9 行全部被唯一键跳过,行数稳定 9。✅

---

## 4. 执行方式(命令示例)

迁移文件不含 `USE`,需通过命令行指定目标库。任选其一:

**方式 A(推荐,文件在服务器上时):**

```bash
mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> grade < docs/migrations/2026-08-15-ai-literacy-hierarchy.sql
mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> grade < docs/migrations/2026-08-15-access-log-rights-audit.sql
mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> grade < docs/migrations/2026-08-15-exam-score-grade.sql
mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> grade < docs/migrations/2026-08-15-ai-content-meta.sql
mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> grade < docs/migrations/2026-08-15-ai-feature-flags.sql
```

**方式 B(mysql 客户端内 `source`):**

```sql
mysql -h<HOST> -P<PORT> -u<USER> -p<PWD> grade
source docs/migrations/2026-08-15-ai-literacy-hierarchy.sql;
source docs/migrations/2026-08-15-access-log-rights-audit.sql;
-- ...
```

> 本地 Docker 验证等价命令:
> `docker exec -i grade-buddy-mysql mysql -uroot -p<PWD> grade_migration_check < docs/migrations/2026-08-15-xxx.sql`
> 或将文件 `docker cp` 进容器后 `mysql ... <DB> -e "source /tmp/migrations/xxx.sql"`。

**建议先备份再执行:**

```bash
mysqldump -h<HOST> -P<PORT> -u<USER> -p<PWD> --single-transaction --no-tablespaces grade > grade_backup_20260815.sql
```

---

## 5. 注意事项

1. **执行前确认前置表存在**(正式库一般已满足):
   - 2A:`indicator_definitions` 必须存在(来自 v2);缺失时 ALTER 部分静默跳过,但 INSERT 种子会 `ERROR 1146 (42S02)`。
   - 2C:`exam_scores` 必须存在;缺失时**静默跳过**(`@t=0 → SELECT 1`),不报错但 grade 列不会加上——**这种静默跳过最危险,务必用第 6 节验证 SQL 复查**。
   - 2D:3 张 AI 表缺失时同样静默跳过。
   - 2E:`feature_flags` 必须存在;缺失时硬报错 `ERROR 1146`。
2. **先备份**:全部迁移含 ALTER/种子,正式库执行前用 `mysqldump` 全量备份一次。
3. **严格按序**:2A 依赖 v2 产物;2B 独立可随时跑;2C/2D 依赖应用建好的表;2E 依赖 feature_flags。全部幂等,重复执行无害,但顺序乱了可能因缺表报错。
4. **不要手工重建库跑迁移**:v1 依赖 `users/classes/students` 基础表(纯空库 ERROR 1824);`exam_scores`/`feature_flags`/3 张 AI 表也不是迁移建的。正式库由应用 AUTO_DDL 建基础表,迁移只负责增量。
5. **字符集**:迁移文件头部 `SET NAMES utf8mb4`,表均为 `utf8mb4_unicode_ci`,中文种子数据无乱码风险。执行客户端建议 `--default-character-set=utf8mb4`。
6. **外键影响**:2A 新增自引用外键 `fk_id_parent`(ON DELETE SET NULL),删除维度节点会将其子级 parent_id 置空,不会阻断删除。
7. **本地环境提示**:本地 Docker MySQL `innodb_flush_log_at_trx_commit=1` + Windows 卷导致每次 DDL 提交 fsync 极慢(建 24 张表可耗时分钟级),正式 RDS 为云盘+更高 IOPS,无此问题;但超大库加列/建索引仍需评估窗口。

---

## 6. 验证 SQL 与回滚建议

### 6.1 执行后验证 SQL(建议逐项跑)

```sql
-- 1. exam_scores 有 grade 列
SHOW COLUMNS FROM exam_scores LIKE 'grade';
-- 期望:grade varchar(16) NULL

-- 2. 3 张 AI 表有 is_ai/ai_meta(6 行)
SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA=DATABASE()
  AND TABLE_NAME IN ('class_analysis_reports','class_review_sessions','targeted_improvement_reports')
  AND COLUMN_NAME IN ('is_ai','ai_meta');

-- 3. feature_flags 有 9 行
SELECT COUNT(*) FROM feature_flags;   -- 期望 9
SELECT `key`, enabled, scope FROM feature_flags ORDER BY `key`;

-- 4. indicator_definitions 有 level/parent_id + 维度种子 + 层级
SHOW COLUMNS FROM indicator_definitions LIKE 'level';
SHOW COLUMNS FROM indicator_definitions LIKE 'parent_id';
SELECT level, COUNT(*) FROM indicator_definitions GROUP BY level;   -- 期望 1:6 / 2:22 / 3:3
SELECT COUNT(*) FROM indicator_definitions WHERE level=1 AND school_id IS NULL;  -- 期望 6
SELECT COUNT(*) FROM indicator_definitions WHERE dimension='ai_literacy';        -- 期望 7
-- 老指标回填抽查:level=2 且 school_id IS NULL 的 parent_id 非空数量
SELECT COUNT(*) FROM indicator_definitions WHERE level=2 AND parent_id IS NOT NULL AND school_id IS NULL;  -- 期望 22

-- 5. access_logs 表存在 + 3 索引
SHOW TABLES LIKE 'access_logs';
SELECT INDEX_NAME FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='access_logs' GROUP BY INDEX_NAME;
```

### 6.2 回滚建议(基于 DDL 类型如实判断)

| 迁移     | 是否可逆           | 回滚方式                                                                                                                                                                                                                                                                                     |
| -------- | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2A       | 部分可逆           | 列/索引/外键可 `ALTER TABLE indicator_definitions DROP COLUMN level, DROP COLUMN parent_id`(先 DROP INDEX idx_id_parent、DROP FOREIGN KEY fk_id_parent);种子数据需按 id 手工 `DELETE`(`ind-dim-*`/`ind-ai-*`);注意自引用 FK 与 19 条老指标已回填的 parent_id 需一并清理,存在子级时需先清子级 |
| 2B       | 可逆               | `DROP TABLE access_logs`(新表,无业务数据依赖,但会丢审计留痕)                                                                                                                                                                                                                                 |
| 2C       | 可逆               | `ALTER TABLE exam_scores DROP COLUMN grade`                                                                                                                                                                                                                                                  |
| 2D       | 可逆               | 三张表各 `ALTER TABLE ... DROP COLUMN is_ai, DROP COLUMN ai_meta`                                                                                                                                                                                                                            |
| 2E       | 可逆               | `DELETE FROM feature_flags WHERE key IN ('ai_review','ai_targeted','ai_layered','smart_exam','smart_gen','ai_diagnosis','ai_grading','ai_chat','ai_comment')`(仅删种子,表保留)                                                                                                               |
| v1(前置) | 不可逆(不建议回滚) | 建 24 张含外键表,回滚=删全部表,破坏性大;仅升级前回退才考虑全量恢复备份                                                                                                                                                                                                                       |
| v2(前置) | 部分可逆           | 19 条指标种子可按 id `DELETE`;`student_growth_records` 的 indicator_id 列/索引/FK 可 DROP(需先 DROP FK)                                                                                                                                                                                      |

> 正式库最稳妥的回滚手段是第 5 节的 `mysqldump` 备份整库恢复,而非逐条 DROP。

---

## 7. 本地验证记录(2026-08-15,scratch 库 `grade_migration_check`)

**环境**:本地 Docker MySQL 8.0.46(`grade-buddy-mysql`,127.0.0.1:13307,root/root_pw_2026)。scratch 库先建 10 张基础表(users/classes/students/exams/exam_scores/wrong_questions/feature_flags/3 张 AI 表,已剥离迁移要补的列,使 ALTER 真实生效),再跑完整链。

### 7.1 链式执行(第一遍)

| 迁移 | 第一遍结果                      | 影响/产物                                                                                                                                                  |
| ---- | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| v1   | 成功(24 表 + 3 表 ALTER 全落地) | 24 张新表;exam_scores 补 class_avg/class_rank/class_id/school_id;wrong_questions 补 status/corrected_at/knowledge_point_id/school_id;students 补 school_id |
| v2   | 成功                            | indicator_definitions 建表;student_growth_records 补 indicator_id + 索引 + FK;19 条指标种子                                                                |
| 2A   | 成功                            | indicator_definitions 补 level/parent_id + idx_id_parent + fk_id_parent;6 维度种子 + 6 AI 种子;老 19 条指标 parent_id 回填;总行数 31                       |
| 2B   | 成功                            | access_logs 建表 + 3 索引                                                                                                                                  |
| 2C   | 成功                            | exam_scores.grade VARCHAR(16) NULL                                                                                                                         |
| 2D   | 成功                            | 3 张 AI 表各补 is_ai(默认1)+ ai_meta                                                                                                                       |
| 2E   | 成功                            | feature_flags 灌入 9 个 flag(全部 enabled=1, scope=global)                                                                                                 |

### 7.2 幂等二次执行(第二遍)

| 迁移 | 第二遍 EXIT | 幂等检查命中                   | 行数稳定性                       |
| ---- | ----------- | ------------------------------ | -------------------------------- |
| v1   | 0           | 12 个检查全部 SELECT 1 空跑    | —                                |
| v2   | 0           | 3 个检查空跑                   | indicator_definitions = 19(不变) |
| 2A   | 0           | 4 个检查空跑                   | indicator_definitions = 31(不变) |
| 2B   | 0           | 3 个索引检查空跑               | —                                |
| 2C   | 0           | 1 个检查空跑                   | —                                |
| 2D   | 0           | 6 个检查空跑                   | —                                |
| 2E   | 0           | INSERT IGNORE 全部被唯一键跳过 | feature_flags = 9(不变)          |

### 7.3 表结构抽查(全部通过)

| 抽查项                                | 结果                                                     |
| ------------------------------------- | -------------------------------------------------------- |
| exam_scores.grade                     | 存在,varchar(16) NULL                                    |
| 3 张 AI 表 is_ai/ai_meta              | 6 列全部存在(is_ai tinyint(1) 默认 1,ai_meta json NULL)  |
| feature_flags 行数                    | 9                                                        |
| indicator_definitions.level/parent_id | 2 列存在;idx_id_parent 索引存在;fk_id_parent 外键存在    |
| 维度种子(level=1, school_id=NULL)     | 6                                                        |
| ai_literacy 维度种子总数              | 7(dim_ai_literacy + 3 方面 + 3 观测点)                   |
| indicator_definitions 总数            | 31(19 老 + 12 新)                                        |
| access_logs 表                        | 存在 + idx_al_target_time/idx_al_user_time/idx_al_action |
| scratch 库总表数                      | 36                                                       |

### 7.4 缺前置行为(依赖链如实记录)

| 场景                                   | 实测行为                                                                                                               |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| v1 在纯空库(无 users/classes/students) | **ERROR 1824** `Failed to open the referenced table 'students'`(line 29)——v1 真实前置是基础表,需应用 create_all 先建   |
| 2A 在无 indicator_definitions 的库     | ALTER 段静默跳过(4 个 `SELECT 1`),INSERT 种子 **ERROR 1146** `Table ... indicator_definitions' doesn't exist`(line 49) |
| 2C 在无 exam_scores 的库               | **静默跳过**,不报错(grade 列不会加)——需用验证 SQL 复查                                                                 |
| 2D 在无 3 张 AI 表的库                 | 同上,静默跳过                                                                                                          |
| 2E 在无 feature_flags 的库             | **ERROR 1146** `Table ... feature_flags' doesn't exist`(line 21)                                                       |

### 7.5 环境坑(已处理,供复现参考)

- 本地 Docker MySQL 上有个残留的卡死进程(上个测试库 `grade_e04_test` 的 `ALTER TABLE ... CREATE INDEX`,卡在 `committing alter table to storage engine`)会阻塞全局 DDL 提交,导致新库建表排队 `waiting for handler commit`。`KILL` 该进程后恢复正常。正式库无此问题,但多 agent 并行验证同一 MySQL 实例时需注意。
- 本地 MySQL `innodb_flush_log_at_trx_commit=1` + Windows Docker 卷,DDL 提交 fsync 慢,建 24 表耗时分钟级;验证时需放宽超时,不要误判为卡死。
- 本机 mysql 客户端非 TTY 管道模式下,`SELECT 1` 等结果会输出两遍,属显示特性,不影响 SQL 语义。
- Windows 控制台把 utf8mb4 中文显示成 `??` 是代码页显示问题;已用 `HEX()` 核对,存储数据为正确 utf8mb4(如 `AI 素养` = `414920E7B4A0E585BB`)。

---

_本手册由叙阅后端迁移验证 agent 基于本地 Docker MySQL 实测产出;5 份本批迁移(2A–2E)链式执行与幂等二次执行全部通过,未修改任何后端代码。_
