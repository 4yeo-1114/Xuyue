# 数据层契约 · 学校/区域锚表 + school_id 回填

> 版本: 1.0 | 日期: 2026-08-20 | 归属专项: 数据层专项 DL2（D1/F1 区域多校视图的数据层前置）
> 基线: 以 `00-data-layer-baseline.md` 第 1-4 节为硬性约束；本契约只描述学校/区域域的新增数据结构与回填规则，不引入新的业务端点。
> 前置: `docs/migrations/2026-08-20-school-region.sql`（DL1）已合入 master（commit 6ab227e）。

---

## 目录

1. [范围与边界](#1-范围与边界)
2. [regions 表结构](#2-regions-表结构)
3. [schools 表结构](#3-schools-表结构)
4. [classes.school_id 语义与回填规则](#4-classesschool_id-语义与回填规则)
5. [跨库注册语义（db_profile_id / db_name）与 D1/F1 边界](#5-跨库注册语义db_profile_id--db_name与-d1f1-边界)
6. [已知缺口备忘](#6-已知缺口备忘)
7. [验收对照](#7-验收对照)

---

## 1. 范围与边界

**本契约管辖**：

- `regions` / `schools` 两张锚表的表结构、约束、索引、外键（DL1 建表 + 本 DL 回填）。
- `classes.school_id` 的语义、回填规则与幂等保证。
- `schools.db_profile_id` / `db_name` 的跨库注册锚点语义。
- alter_schema 已补列的孤儿 `school_id`（students / exam_scores / wrong_questions）的级联回填规则。

**明确不做（边界）**：

- 不实现任何 D1/F1 业务端点（区域多校视图查询、跨校聚合接口一律不在本专项落地）。
- 不补模型层孤儿列映射（exam_score.py 等暂不映射 school_id/class_id，见 §6）。
- 不回填 `indicator_definitions` / `student_portfolios` / `student_growth_records` / `report_snapshots` / `assessment_comments` 的 school_id（见 §6 备忘）。

---

## 2. regions 表结构

**模型**: `app/models/school.py:16-31`（`Region`）| **DDL**: `docs/migrations/2026-08-20-school-region.sql:21-33`

| 字段         | 类型           | 约束                                       | 说明                                                              |
| ------------ | -------------- | ------------------------------------------ | ----------------------------------------------------------------- |
| `id`         | `VARCHAR(36)`  | PK，NOT NULL                               | UUID v4 主键（`gen_uuid()`，见 `00-data-layer-baseline.md` §1.1） |
| `name`       | `VARCHAR(128)` | NOT NULL                                   | 区域名称                                                          |
| `level`      | `TINYINT`      | NOT NULL，默认 1                           | 区域层级：1=省 2=市 3=区县                                        |
| `parent_id`  | `VARCHAR(36)`  | NULL                                       | 父区域 ID，**自引用** `regions.id`；NULL=顶层                     |
| `code`       | `VARCHAR(32)`  | NULL                                       | 区域编码（如行政区划码）                                          |
| `created_at` | `DATETIME`     | NOT NULL，默认 CURRENT_TIMESTAMP           | 创建时间(UTC)                                                     |
| `updated_at` | `DATETIME`     | NOT NULL，默认 CURRENT_TIMESTAMP ON UPDATE | 更新时间(UTC)                                                     |
| `deleted_at` | `DATETIME`     | NULL                                       | 软删除时间，NULL=未删除                                           |

**索引**：`idx_regions_parent_id (parent_id)`、`idx_regions_code (code)`
**外键**：`fk_regions_parent` — `parent_id` → `regions.id`（`ON DELETE SET NULL`，自引用，`00-data-layer-baseline.md` §1.3 之外的锚表内自引用）
**字符集/引擎**：`ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`（`00-data-layer-baseline.md` §1.4）

---

## 3. schools 表结构

**模型**: `app/models/school.py:34-50`（`School`）| **DDL**: `docs/migrations/2026-08-20-school-region.sql:38-51`

| 字段            | 类型           | 约束                                       | 说明                                                                        |
| --------------- | -------------- | ------------------------------------------ | --------------------------------------------------------------------------- |
| `id`            | `VARCHAR(36)`  | PK，NOT NULL                               | UUID v4 主键                                                                |
| `name`          | `VARCHAR(128)` | NOT NULL                                   | 学校名称                                                                    |
| `region_id`     | `VARCHAR(36)`  | NULL                                       | 所属区域 ID，锚点 `regions.id`                                              |
| `db_profile_id` | `VARCHAR(36)`  | NULL                                       | **跨库注册锚点**，对应 `multi_project_settings.json` 的 profile id（见 §5） |
| `db_name`       | `VARCHAR(128)` | NULL                                       | 对应库名（多租户每客户一库）                                                |
| `created_at`    | `DATETIME`     | NOT NULL，默认 CURRENT_TIMESTAMP           | 创建时间(UTC)                                                               |
| `updated_at`    | `DATETIME`     | NOT NULL，默认 CURRENT_TIMESTAMP ON UPDATE | 更新时间(UTC)                                                               |
| `deleted_at`    | `DATETIME`     | NULL                                       | 软删除时间，NULL=未删除                                                     |

**索引**：`idx_schools_name (name)`、`idx_schools_db_profile_id (db_profile_id)`、`idx_schools_region_id (region_id)`
**外键**：`fk_schools_region` — `region_id` → `regions.id`（`ON DELETE SET NULL`）
**字符集/引擎**：同 regions。

---

## 4. classes.school_id 语义与回填规则

### 4.1 语义

- `classes.school_id` 是班级到学校的归属列，类型 `VARCHAR(36)` NULL，锚点 `schools.id`。
- **每部署默认学校**（已拍板设计口径）：多租户现状 = 每客户一库（`multi_project_settings.json` 的 grade/ky/hn profile），**单部署库内所有班级归属同一部署学校**。schools 表刚建为空，故先 seed 默认学校再回填，规避"先有鸡还是先有蛋"。

### 4.2 回填规则（`docs/migrations/2026-08-20-school-backfill.sql`）

执行顺序（全脚本幂等）：

1. **seed 默认学校**：幂等插入一行 `schools`，守卫 `WHERE NOT EXISTS (… BINARY s.db_profile_id <=> BINARY @db_profile_id AND BINARY s.db_name <=> BINARY DATABASE())`（`<=>` null-safe，`BINARY` 规避连接 charset 与列 collation 不一致导致的 1267/1253）。
   - `id` = 固定确定性 UUID 占位 `11111111-1111-4111-8111-111111111111`（同库重复执行不产生重复行）。
   - `name` = `CONCAT('默认学校-', LEFT(@db_profile_id,8))`，运维可改为真实校名。
   - `region_id` = NULL（区域归属由 D1/F1 后续维护）。
   - `db_profile_id` = 运维必填变量 `@db_profile_id`（当前部署 profile，见文件头注释）；`db_name` = `DATABASE()`。
2. **回填 classes.school_id**：`UPDATE classes SET school_id = @default_school_id WHERE school_id IS NULL`（已回填的不再动）。
3. **级联回填孤儿列**（均带 `WHERE school_id IS NULL`，幂等）：
   - `students`：`students.class_id → classes.school_id`（class_id 非空，模型 `app/models/student.py:12`）。
   - `wrong_questions`：`wrong_questions.class_id → classes.school_id`（class_id 非空，模型 `app/models/wrong_question.py:14`）。
   - `exam_scores`：优先 `exam_scores.class_id → classes.school_id`（class_id 为 alter_schema 补列，可空）；若 class_id 为空，退而按 `exam_scores.student_id → students.school_id` 兜底。

### 4.3 幂等保证

- schools 表不存在 → 全脚本空跑（information_schema 守卫，`SET @s = IF(cond, 'SELECT 1', …)` + `PREPARE/EXECUTE/DEALLOCATE`）。
- seed 用 `WHERE NOT EXISTS`；所有 UPDATE 带 `WHERE school_id IS NULL`。
- 重复执行安全：第二次命中空跑/0 行，无副作用。

---

## 5. 跨库注册语义（db_profile_id / db_name）与 D1/F1 边界

- **注册锚点**：`schools.db_profile_id`（+ `db_name` 作库名佐证）是**跨库聚合的唯一注册锚点**，值取自 `multi_project_settings.json` 的 `db_profiles[].id`（当前三 profile：grade / ky / hn，见 `multi_project_settings.json:5-38`）。
- **为什么不是 school.id**：school.id 在单部署库内局部唯一即可；跨库 D1/F1 聚合按 `(db_profile_id, db_name)` 归一各库注册的学校，再统一分配区域归属（region_id）。
- **跨库只读聚合方向已拍板**：D1/F1 只做跨库**只读**聚合（各库 SELECT，汇总层拼装），不跨库写。本专项不落地任何 D1/F1 端点，仅在本契约钉死注册锚点语义。
- **单库多校扩展位**：若未来单库确需多学校，将 seed 的固定 UUID 改为由 `db_profile_id` 派生的 UUID v5 id，并保持 `WHERE NOT EXISTS` 幂等守卫；本契约登记为扩展位，不阻塞当前单部署单校模型。

---

## 6. 已知缺口备忘

> 本专项**不补模型映射、不新增列**，以下缺口如实登记，供后续 DL 收敛。

| 表                       | alter_schema 补列位置                                                     | 模型层现状                                                      | 缺口说明                                                                          |
| ------------------------ | ------------------------------------------------------------------------- | --------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `exam_scores`            | `class_id`（`alter_schema.py:179`）、`school_id`（`alter_schema.py:181`） | `app/models/exam_score.py:12-21` **未映射** class_id/school_id  | 列已在 DB 层存在；本 DL 回填后，后续 DL 需补 model 列（含 `__table_args__` 索引） |
| `wrong_questions`        | `school_id`（`alter_schema.py:191`）                                      | `app/models/wrong_question.py:14` 有 class_id、**无 school_id** | 同上，后续补 model 列                                                             |
| `students`               | `school_id`（`alter_schema.py:193`）                                      | `app/models/student.py:12` 有 class_id、**无 school_id**        | 同上，后续补 model 列                                                             |
| `indicator_definitions`  | `school_id`（`alter_schema.py:39`）                                       | 未核对 model                                                    | **不回填**：依赖画像域计算链路写入，直接 SQL join 可能引入脏数据                  |
| `student_portfolios`     | `school_id`（`alter_schema.py:56`）                                       | 未核对 model                                                    | **不回填**：同上                                                                  |
| `student_growth_records` | `school_id`（`alter_schema.py:77`）                                       | 未核对 model                                                    | **不回填**：同上                                                                  |
| `report_snapshots`       | `school_id`（`alter_schema.py:103`）                                      | 未核对 model                                                    | **不回填**：同上                                                                  |
| `assessment_comments`    | `school_id`（`alter_schema.py:124`）                                      | 未核对 model                                                    | **不回填**：同上                                                                  |

**本 DL 只处理** students / exam_scores / wrong_questions 三张有明确 class_id 关联的孤儿列回填；其余表在回填 SQL（`2026-08-20-school-backfill.sql` §3.4 注释）与本契约登记为"列已存在、model 后续补 / 后续链路写入"，不硬写错误的 join。

---

## 7. 验收对照

- 契约覆盖本文件 §1-§6 全部要求；引用路径/行号均以仓库当前 master 为准。
- `tests/test_school_region_schema.py`：
  - models 层断言 regions/schools 表、FK（regions.parent_id 自引用、schools.region_id→regions）与 classes.school_id 列类型/可空；
  - 迁移 SQL 文本层断言 DL1/DL2 幂等守卫；
  - 本地 Docker MySQL（127.0.0.1:13307）可用时，scratch 库链式双跑 DL1+DL2 验证幂等；不可用自动 skip，套件不产生环境 error。
