# 五育成长画像功能契约

> 版本: 1.0 | 日期: 2026-08-11 | 基础路径: /api/v1/portfolio
> 基线: 以 `00-data-layer-baseline.md` 为准；若基线尚未产出，本文件按叙阅现有 models 风格（主键 gen_uuid + student_id 外键 + MySQL DDL 规范）定义，后续与基线对齐时以基线为权威来源。
> 参考实现: teacher-ai-platform (SurrealDB) → MySQL 关系模型映射

---

## 目录

1. [前置：现有表扩展](#1-前置现有表扩展)
2. [新增表 DDL](#2-新增表-ddl)
3. [智育事件目录与数据源映射](#3-智育事件目录与数据源映射)
4. [评分公式](#4-评分公式)
5. [SQL 聚合查询](#5-sql-聚合查询)
6. [API 接口契约](#6-api-接口契约)
7. [AI 评语规范](#7-ai-评语规范)
8. [验收标准](#8-验收标准)

---

## 1. 前置：现有表扩展

智育自动聚合依赖以下列，若尚未存在于叙阅现有表，须在实施画像功能前完成 DDL 变更。

### 1.1 exam_scores 表扩展

```sql
-- exam_scores 缺少智育事件必需的字段
ALTER TABLE exam_scores
    ADD COLUMN class_avg  DECIMAL(10, 2) NULL COMMENT '班级均分',
    ADD COLUMN class_rank INT            NULL COMMENT '班级排名（1=最高）',
    ADD COLUMN class_id   VARCHAR(36)    NULL COMMENT '冗余班级ID，加速班级级聚合',
    ADD COLUMN school_id  VARCHAR(36)    NULL COMMENT '冗余学校ID，加速学校级聚合';

-- class_avg / class_rank 由考试导入/批改完成时计算写入（应用层口径：该班该次考试的有效成绩）
-- class_id 从 exams.class_id JOIN 冗余写入
-- school_id 从 classes → 学校的映射冗余写入（若叙阅尚未有 school 表，暂时留空，用 class_id 代理）
```

### 1.2 wrong_questions 表扩展

```sql
-- wrong_questions 缺少订正状态和知识点关联
ALTER TABLE wrong_questions
    ADD COLUMN status             VARCHAR(16)  NOT NULL DEFAULT 'open'  COMMENT 'open=未订正 / corrected=已订正',
    ADD COLUMN corrected_at       DATETIME     NULL                     COMMENT '订正时间（状态变为corrected时写入）',
    ADD COLUMN knowledge_point_id VARCHAR(36)  NULL                     COMMENT '关联知识点（用于薄弱点攻克检测）',
    ADD COLUMN school_id          VARCHAR(36)  NULL                     COMMENT '冗余学校ID（从class_id推导）';

CREATE INDEX idx_wq_status   ON wrong_questions (student_id, status);
CREATE INDEX idx_wq_kp       ON wrong_questions (student_id, knowledge_point_id, status);
CREATE INDEX idx_wq_corrected ON wrong_questions (student_id, corrected_at);
```

### 1.3 students 表扩展

```sql
-- students 需要 school_id 用于学校级 z-score 聚合
ALTER TABLE students
    ADD COLUMN school_id VARCHAR(36) NULL COMMENT '所属学校ID（从班级推导冗余）';
```

---

## 2. 新增表 DDL

### 2.1 student_portfolio（学生五育画像主表）

**用途**: 一个学生一条记录，缓存五育成就轨聚合结果。GET 时实时重算并写回（幂等），不做事件钩子。

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | VARCHAR(36) | PK | gen_uuid() | 主键 |
| student_id | VARCHAR(36) | NOT NULL, FK→students.id | — | 学生 ID |
| class_id | VARCHAR(36) | NOT NULL, FK→classes.id | — | 班级 ID（冗余，加速班级级查询） |
| school_id | VARCHAR(36) | NULL | NULL | 学校 ID（冗余，加速学校级聚合） |
| base_points | INT | NOT NULL | 100 | 基础分（保留字段，不参与五育计分，向后兼容） |
| dimensions | JSON | NOT NULL | — | 五育成就轨缓存：`{"moral": 0, "intellectual": 15.5, "physical": 0, "aesthetic": 0, "labor": 0, "total": 15.5}` |
| detail | JSON | NULL | NULL | 智育明细（仅 intellectual 维度有值）：`{"corrected_wrong_questions": 5, "rank_improvements": 2, ...}` |
| auto_detail | JSON | NULL | NULL | 智育自动事件按类型明细（cap 后）：`{"wrong_question_corrected": {"count": 5, "points": 4.2}, ...}` |
| total_growth_point | DECIMAL(10,2) | NOT NULL | 0 | 综合成就分（Σ dimensions 五维，不含 base_points） |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 创建时间（UTC） |
| updated_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP ON UPDATE | 更新时间（UTC） |

**索引**:
```sql
PRIMARY KEY (id)
UNIQUE INDEX uk_sp_student (student_id)   -- 一个学生一条画像记录
INDEX idx_sp_class (class_id)             -- 按班级查询画像
INDEX idx_sp_school (school_id)           -- 学校级聚合
```

**DDL**:
```sql
CREATE TABLE student_portfolio (
    id                VARCHAR(36)  NOT NULL PRIMARY KEY,
    student_id        VARCHAR(36)  NOT NULL,
    class_id          VARCHAR(36)  NOT NULL,
    school_id         VARCHAR(36)  NULL,
    base_points       INT          NOT NULL DEFAULT 100,
    dimensions        JSON         NOT NULL,
    detail            JSON         NULL,
    auto_detail       JSON         NULL,
    total_growth_point DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_sp_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_sp_class   FOREIGN KEY (class_id)   REFERENCES classes(id)  ON DELETE CASCADE,
    UNIQUE INDEX uk_sp_student (student_id),
    INDEX idx_sp_class (class_id),
    INDEX idx_sp_school (school_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 2.2 student_growth_record（成长记录流水表）

**用途**: 每条记录代表一次成长事件（手动录入或系统自动产生）。source_type + source_id + evidence 构成完整证据链，可回溯。

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | VARCHAR(36) | PK | gen_uuid() | 主键 |
| student_id | VARCHAR(36) | NOT NULL, FK→students.id | — | 学生 ID |
| class_id | VARCHAR(36) | NOT NULL, FK→classes.id | — | 班级 ID |
| school_id | VARCHAR(36) | NULL | NULL | 学校 ID |
| dimension | VARCHAR(32) | NOT NULL | — | 五育维度：moral / intellectual / physical / aesthetic / labor |
| source_type | VARCHAR(32) | NOT NULL | 'manual' | 来源类型：manual / wrong_question / exam / targeted_report / auto_event |
| source_id | VARCHAR(36) | NULL | NULL | 来源记录 ID（如 wrong_question.id、exam_score.id，用于回溯） |
| growth_point | INT | NOT NULL | 0 | 成长分值（可为负，如扣分场景） |
| evidence | JSON | NULL | NULL | 证据快照（如 `{"error_type": "calculation", "question_content": "..."}`） |
| note | VARCHAR(1000) | NULL | NULL | 备注（手动录入时可填写） |
| created_by | VARCHAR(36) | NOT NULL, FK→users.id | — | 录入人 ID（系统自动产生的记录用 system 用户或 NULL） |
| occurred_at | DATETIME | NULL | NULL | 事件发生时间（源数据的业务时间，非入库时间） |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 记录创建时间（UTC） |

**索引**:
```sql
PRIMARY KEY (id)
INDEX idx_sgr_student   (student_id)                  -- 按学生查流水（最频繁）
INDEX idx_sgr_class     (class_id)                    -- 班级聚合
INDEX idx_sgr_dimension (student_id, dimension)        -- 按维度过滤
INDEX idx_sgr_time      (student_id, occurred_at)       -- 按时间范围过滤（学期报告）
INDEX idx_sgr_source    (source_type, source_id)        -- 幂等去重（同 source_id 不重复录入）
```

**DDL**:
```sql
CREATE TABLE student_growth_record (
    id            VARCHAR(36)   NOT NULL PRIMARY KEY,
    student_id    VARCHAR(36)   NOT NULL,
    class_id      VARCHAR(36)   NOT NULL,
    school_id     VARCHAR(36)   NULL,
    dimension     VARCHAR(32)   NOT NULL,
    source_type   VARCHAR(32)   NOT NULL DEFAULT 'manual',
    source_id     VARCHAR(36)   NULL,
    growth_point  INT           NOT NULL DEFAULT 0,
    evidence      JSON          NULL,
    note          VARCHAR(1000) NULL,
    created_by    VARCHAR(36)   NOT NULL,
    occurred_at   DATETIME      NULL,
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_sgr_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_sgr_class   FOREIGN KEY (class_id)   REFERENCES classes(id)  ON DELETE CASCADE,
    CONSTRAINT fk_sgr_creator FOREIGN KEY (created_by) REFERENCES users(id)    ON DELETE CASCADE,
    INDEX idx_sgr_student   (student_id),
    INDEX idx_sgr_class     (class_id),
    INDEX idx_sgr_dimension (student_id, dimension),
    INDEX idx_sgr_time      (student_id, occurred_at),
    INDEX idx_sgr_source    (source_type, source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**幂等约束**: 应用层保证 —— 同一 `(student_id, source_type, source_id)` 不可重复录入。若已存在则跳过（UPDATE 或忽略），不产生重复流水。

---

### 2.3 report_snapshot（学期报告快照表）

**用途**: 显式冻结学期报告，版本链不可变。每次 freeze 落新版本（version+1），parent_id 构成版本链，支持回溯审计。

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | VARCHAR(36) | PK | gen_uuid() | 主键 |
| student_id | VARCHAR(36) | NOT NULL, FK→students.id | — | 学生 ID |
| term | VARCHAR(16) | NOT NULL | — | 学年-学期，如 `2025-2026-1` |
| version | INT | NOT NULL | 1 | 版本号（同 student+term 下自增） |
| parent_id | VARCHAR(36) | NULL, FK→report_snapshot.id | NULL | 前一版本快照 ID（版本链） |
| class_id | VARCHAR(36) | NOT NULL | — | 班级 ID |
| school_id | VARCHAR(36) | NULL | NULL | 学校 ID |
| generated_by | VARCHAR(36) | NOT NULL, FK→users.id | — | 冻结操作人 |
| payload | JSON | NOT NULL | — | 完整报告 JSON（含 dimensions/baseline/milestones/trend/comment，与 GET report 同结构） |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 冻结时间（UTC） |

**索引**:
```sql
PRIMARY KEY (id)
UNIQUE INDEX uk_rs_student_term_version (student_id, term, version)  -- 版本链唯一 + 并发兜底
INDEX idx_rs_term (term)                                              -- 按学期查询
INDEX idx_rs_class_term (class_id, term)                              -- 班级学期报告批量查询
```

**DDL**:
```sql
CREATE TABLE report_snapshot (
    id           VARCHAR(36)  NOT NULL PRIMARY KEY,
    student_id   VARCHAR(36)  NOT NULL,
    term         VARCHAR(16)  NOT NULL,
    version      INT          NOT NULL DEFAULT 1,
    parent_id    VARCHAR(36)  NULL,
    class_id     VARCHAR(36)  NOT NULL,
    school_id    VARCHAR(36)  NULL,
    generated_by VARCHAR(36)  NOT NULL,
    payload      JSON         NOT NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_rs_student FOREIGN KEY (student_id)   REFERENCES students(id)       ON DELETE CASCADE,
    CONSTRAINT fk_rs_parent  FOREIGN KEY (parent_id)    REFERENCES report_snapshot(id) ON DELETE SET NULL,
    CONSTRAINT fk_rs_genby   FOREIGN KEY (generated_by) REFERENCES users(id)           ON DELETE CASCADE,
    UNIQUE INDEX uk_rs_student_term_version (student_id, term, version),
    INDEX idx_rs_term (term),
    INDEX idx_rs_class_term (class_id, term)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**版本链语义**:
- 冻结时: `SELECT MAX(version) FROM report_snapshot WHERE student_id=? AND term=?` → `new_version = max+1`
- 写入: INSERT 新行，`parent_id` 指向前一版本的 `id`
- `UNIQUE(student_id, term, version)` 兜底并发（同版本号并发 INSERT 第二个失败）
- 不可改删: 应用层不提供 update/delete 端点；纠错仅管理员走专用连接删错误快照

---

### 2.4 assessment_comment（AI 评语表）

**用途**: 学期报告 AI 评语存储。一个学生一个学期一条（UPSERT 幂等），状态机: ai_generated → confirmed。含禁词闸门标记供审计。

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | VARCHAR(36) | PK | gen_uuid() | 主键 |
| student_id | VARCHAR(36) | NOT NULL, FK→students.id | — | 学生 ID |
| term | VARCHAR(16) | NOT NULL | — | 学年-学期，如 `2025-2026-1` |
| class_id | VARCHAR(36) | NOT NULL | — | 班级 ID |
| school_id | VARCHAR(36) | NULL | NULL | 学校 ID |
| status | VARCHAR(16) | NOT NULL | 'ai_generated' | ai_generated=AI初稿 / confirmed=已确认 / ai_failed=网关失败 |
| ai_content | TEXT | NULL | NULL | AI 生成的评语原文（经闸门清洗后） |
| confirmed_content | TEXT | NULL | NULL | 教师确认后的评语（可修改） |
| ai_model | VARCHAR(64) | NULL | NULL | 生成评语的模型标识（如 `qwen-plus`） |
| tokens_used | INT | NULL | NULL | 本次生成消耗 token 数 |
| cost_cent | INT | NULL | NULL | 本次生成费用（分） |
| gate_flagged | TINYINT(1) | NOT NULL | 0 | 闸门是否拦截过（0=未拦截，1=曾清洗含禁词句子） |
| created_by | VARCHAR(36) | NOT NULL, FK→users.id | — | 创建人（触发生成者） |
| confirmed_by | VARCHAR(36) | NULL, FK→users.id | NULL | 确认人（教师） |
| created_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP | 创建时间（UTC） |
| confirmed_at | DATETIME | NULL | NULL | 确认时间（UTC） |
| updated_at | DATETIME | NOT NULL | CURRENT_TIMESTAMP ON UPDATE | 更新时间（UTC） |

**索引**:
```sql
PRIMARY KEY (id)
UNIQUE INDEX uk_ac_student_term (student_id, term)  -- 一个学生一个学期一条评语
```

**DDL**:
```sql
CREATE TABLE assessment_comment (
    id                VARCHAR(36)  NOT NULL PRIMARY KEY,
    student_id        VARCHAR(36)  NOT NULL,
    term              VARCHAR(16)  NOT NULL,
    class_id          VARCHAR(36)  NOT NULL,
    school_id         VARCHAR(36)  NULL,
    status            VARCHAR(16)  NOT NULL DEFAULT 'ai_generated',
    ai_content        TEXT         NULL,
    confirmed_content TEXT         NULL,
    ai_model          VARCHAR(64)  NULL,
    tokens_used       INT          NULL,
    cost_cent         INT          NULL,
    gate_flagged      TINYINT(1)   NOT NULL DEFAULT 0,
    created_by        VARCHAR(36)  NOT NULL,
    confirmed_by      VARCHAR(36)  NULL,
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at      DATETIME     NULL,
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_ac_student    FOREIGN KEY (student_id)  REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_ac_creator    FOREIGN KEY (created_by)  REFERENCES users(id)    ON DELETE CASCADE,
    CONSTRAINT fk_ac_confirmer  FOREIGN KEY (confirmed_by) REFERENCES users(id)   ON DELETE SET NULL,
    UNIQUE INDEX uk_ac_student_term (student_id, term),
    INDEX idx_ac_class_term (class_id, term)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 3. 智育事件目录与数据源映射

### 3.1 事件目录总览

| # | event_type | 名称 | 分值 | 学期上限 | 维度 | 来源表 | 启用 |
|---|-----------|------|------|---------|------|--------|------|
| 1 | `wrong_question_corrected` | 错题订正 | +1 | 30 | intellectual | wrong_questions | ✅ |
| 2 | `exam_rank_up` | 成绩排名提升 | +2 | 15 | intellectual | exam_scores | ✅ |
| 3 | `targeted_report` | 靶向提升报告 | +1 | 8 | intellectual | targeted_improvement_reports | ✅ |
| 4 | `manual_growth` | 手动成长记录 | ±N | 无上限 | any | student_growth_record | ✅ |
| 5 | `above_class_avg` | 超班级均分 | +2 | 无上限 | intellectual | exam_scores | ✅ |
| 6 | `correction_rate_high` | 订正率达标 | +3 | 1 | intellectual | wrong_questions | ✅ |
| 7 | `weak_point_conquered` | 薄弱点攻克 | +2 | 10 | intellectual | wrong_questions | ✅ |

> **cap_per_term 语义**: 当前学期内同类型事件按 `occurred_at` 倒序保留最近 N 条参与计分。如错题订正 cap=30，一学期有 50 条订正则只计最近 30 条（防刷分；历史事件由时间衰减自然压低权重）。

### 3.2 数据源映射详表（叙阅现有表 → 事件 → 积分）

| 叙阅源表 | 触发条件 | 事件类型 | 分值 | SQL 聚合逻辑要点 |
|-----------|---------|---------|------|----------------|
| `wrong_questions` | `status = 'corrected'` AND `corrected_at` 在查询范围内 | `wrong_question_corrected` | +1 | `SELECT id, knowledge_point_id, corrected_at FROM wrong_questions WHERE student_id=? AND status='corrected'`，每条计 1 分 |
| `exam_scores` JOIN `exams` | 同 subject 的两次考试中，后一次 `class_rank` < 前一次（数字变小=进步） | `exam_rank_up` | +2 | 按 subject 分组 → 按 exam_date 排序 → 检测 class_rank 下降点。来源: `SELECT es.subject, es.class_rank, e.exam_date FROM exam_scores es JOIN exams e ON es.exam_id=e.id WHERE es.student_id=?` |
| `targeted_improvement_reports` | 记录存在（有 `generated_at`） | `targeted_report` | +1 | `SELECT id, generated_at FROM targeted_improvement_reports WHERE student_id=?`，每份 +1 |
| `student_growth_record` | `source_type='manual'` 的记录（教师手动录入） | `manual_growth` | ±N (取 growth_point 值) | `SELECT growth_point, occurred_at FROM student_growth_record WHERE student_id=? AND source_type='manual'`，原样计分 |
| `exam_scores` JOIN `exams` | `score > class_avg` | `above_class_avg` | +2 | `SELECT es.score, es.class_avg, e.exam_date FROM exam_scores es JOIN exams e ON es.exam_id=e.id WHERE es.student_id=? AND es.score > es.class_avg`，每科次 +2 |
| `wrong_questions` | `COUNT(status='corrected') / COUNT(*) >= 0.8` | `correction_rate_high` | +3 | 先求分母 `SELECT COUNT(*) FROM wrong_questions WHERE student_id=?`；再求分子 `SELECT COUNT(*) FROM wrong_questions WHERE student_id=? AND status='corrected'`；分子/分母 ≥ 0.8 → 触发，取 MAX(corrected_at) 为发生时间 |
| `wrong_questions` | 同一 `knowledge_point_id` 从有错题(dirty)到全部订正(clean) = 被攻克 | `weak_point_conquered` | +2 | `SELECT knowledge_point_id FROM wrong_questions WHERE student_id=? AND status='open' GROUP BY knowledge_point_id`（未攻克）；`SELECT knowledge_point_id, MAX(corrected_at) FROM wrong_questions WHERE student_id=? AND status='corrected' GROUP BY knowledge_point_id`（已攻克）；已攻克且不在未攻克集合中 → 触发，按 knowledge_point_id 去重，每个 +2 |

### 3.3 时间衰减公式

```
w = e^(-Δt / τ)

其中:
  Δt = now - event.occurred_at（天数）
  τ  = 90 天（衰减半衰期，可配置环境变量 ASSESSMENT_DECAY_TAU_DAYS 覆盖）
  w  ∈ (0, 1]，越近权重越大

单事件最终贡献 = weight × w（取小数点后 2 位，四舍五入）
```

**衰减效果示例** (τ=90):
| Δt | w | +2 事件衰减后 |
|----|---|-------------|
| 0 天 | 1.000 | 2.00 |
| 30 天 | 0.717 | 1.43 |
| 60 天 | 0.513 | 1.03 |
| 90 天 | 0.368 | 0.74 |
| 180 天 | 0.135 | 0.27 |
| 365 天 | 0.017 | 0.03 |

> **时间衰减适用场景**: GET /portfolio（实时画像）使用衰减；学期报告快照时 `apply_decay=False`（展示该学期真实获得分）。

### 3.4 学期边界定义

```
上学期：当年 9/1 ~ 次年 1/31（如 2025-2026-1 = 2025-09-01 ~ 2026-01-31）
下学期：当年 2/1 ~ 当年 7/31（如 2025-2026-2 = 2026-02-01 ~ 2026-07-31）
8 月：暑假 → 归入新学年上学期（如 2026-08 属于 2026-2027-1）
```

---

## 4. 评分公式

### 4.1 双轨制

**成就轨（真实成长分）**:
```
S_dim = Σ(该维 growth_records 的 growth_point) + (仅 intellectual 维) Σ(智育自动事件分 × decay_weight)

其中:
  - growth_records: student_growth_record 表中该维全部流水（不限时间，全量）
  - 智育自动事件分: 经 cap_per_term + 时间衰减后的 7 事件加权累计
  - S_total = Σ S_dim  (五维之和)
```

**活跃轨（参与度）**:
```
A_dim = 该维事件参与总次数（cap 前，含 growth_records.count + 智育事件条数）
```

**data_status**:
```
data_status[dim] = "has_data"      if (growth_records.count > 0 OR 智育自动事件数 > 0)
                 = "insufficient"  otherwise  → 前端展示灰态"数据不足"
```

### 4.2 成绩轨归一化与基准线

**班级百分位**:
```
P_dim = (1 - (class_rank - 1) / n_dim) × 100

其中:
  n_dim = 该班该维有数据（data_status="has_data"）的学生总数
  class_rank = 该生该维成就分在该班的降序排名（1=最高）
  P ∈ (0, 100]
```

**五档阈值**:
```
A+ : P >= 90
A  : 75 <= P < 90
B  : 40 <= P < 75
C  : 20 <= P < 40
D  : P < 20
无数据: 不展示档位（返回 null，前端灰态）
```

**学校级 z-score**（跨班可比）:
```
z_dim = (S_dim - μ_school) / σ_school

其中:
  μ_school = 全校该维有数据学生的成就分均值
  σ_school = 全校该维有数据学生的成就分总体标准差
  若 σ_school = 0 或无足够样本: z_dim = 0
```

**综合分（归一化标准分）**:
```
composite_dim = clamp(50 + 10 × z_dim, 0, 100)

即: T-score 映射，均值 50、标准差 10，截断到 [0, 100]
此分跨班可比，不展示原始点数
```

**输出格式约定**（GET /portfolio 和 GET /report 的 baseline 段）:
```json
{
  "percentile": {"moral": 85.0, "intellectual": 72.5, "total": 68.0, ...},
  "tier":       {"moral": "A",   "intellectual": "B",   "total": "B", ...},
  "z_score":    {"moral": 1.23,  "intellectual": 0.56,  "total": 0.42, ...},
  "composite":  {"moral": 62.3,  "intellectual": 55.6,  "total": 54.2, ...},
  "rank":       {"moral": 3,     "intellectual": 7,     "total": 8, ...},
  "n":          {"moral": 42,    "intellectual": 42,    "total": 42, ...}
}
```

> **展示口径**: 前端雷达图/指标卡使用 **composite**（0-100 归一化分）和 **tier**（五档），不展示原始 `S_dim` 绝对值。原始 total 保留为 `raw_total` 内部字段。

### 4.3 班级各维平均计算

```
avg_dim = Σ(has_data 学生的 S[dim]) / count(has_data 学生)

仅统计 data_status="has_data" 的学生，避免 insufficient（0 分）拉低均值。
```

---

## 5. SQL 聚合查询

以下是智育 7 事件的 SQL 查询伪代码。实际实现封装在 `PortfolioRepository` 中。

### 5.1 单生原始事件行（raw_intellectual_events）

```sql
-- 1) 已订正错题
SELECT id, knowledge_point_id, corrected_at
FROM wrong_questions
WHERE student_id = :sid AND status = 'corrected'
  AND corrected_at BETWEEN :date_from AND :date_to;

-- 2) 靶向提升报告
SELECT id, generated_at AS created_at
FROM targeted_improvement_reports
WHERE student_id = :sid
  AND generated_at BETWEEN :date_from AND :date_to;

-- 3) 考试成绩（含 class_avg / class_rank）
SELECT es.id, es.subject, es.score, es.class_avg, es.class_rank,
       e.exam_date
FROM exam_scores es
JOIN exams e ON es.exam_id = e.id
WHERE es.student_id = :sid
  AND e.exam_date BETWEEN :date_from AND :date_to
ORDER BY e.exam_date;

-- 4) 错题总数（订正率分母）
SELECT COUNT(*) AS cnt
FROM wrong_questions
WHERE student_id = :sid
  AND created_at BETWEEN :date_from AND :date_to;
```

### 5.2 班级级批量聚合（raw_class_events）

```sql
-- 已订正错题（按 student_id 分组）
SELECT student_id, id, knowledge_point_id, corrected_at
FROM wrong_questions
WHERE class_id = :cid AND status = 'corrected'
  AND corrected_at BETWEEN :term_from AND :term_to;

-- 错题总数（按 student_id 分组，订正率分母）
SELECT student_id, COUNT(*) AS cnt
FROM wrong_questions
WHERE class_id = :cid
  AND created_at BETWEEN :term_from AND :term_to
GROUP BY student_id;

-- 靶向报告
SELECT id, student_id, generated_at AS created_at
FROM targeted_improvement_reports
WHERE class_id = :cid
  AND generated_at BETWEEN :term_from AND :term_to;

-- 考试成绩
SELECT es.id, es.student_id, es.subject, es.score,
       es.class_avg, es.class_rank, e.exam_date
FROM exam_scores es
JOIN exams e ON es.exam_id = e.id
WHERE es.class_id = :cid
  AND e.exam_date BETWEEN :term_from AND :term_to;
```

### 5.3 学校级批量聚合（raw_school_events）

```sql
-- 结构同班级级，WHERE 条件改为 school_id = :sid
```

### 5.4 成长流水聚合

```sql
-- 按维度聚合全量
SELECT dimension, SUM(growth_point) AS total, COUNT(*) AS cnt
FROM student_growth_record
WHERE student_id = :sid
GROUP BY dimension;

-- 按学期范围聚合
SELECT dimension, SUM(growth_point) AS total, COUNT(*) AS cnt
FROM student_growth_record
WHERE student_id = :sid
  AND occurred_at BETWEEN :date_from AND :date_to
GROUP BY dimension;

-- 按来源类型聚合（学期范围）
SELECT source_type, SUM(growth_point) AS total, COUNT(*) AS cnt
FROM student_growth_record
WHERE student_id = :sid
  AND occurred_at BETWEEN :date_from AND :date_to
GROUP BY source_type;
```

### 5.5 按月趋势（合并多源表）

```sql
-- 合并 4 源：growth_record + wrong_question(corrected) + exam_score + targeted_report
-- 按月分组 → Python 聚合（参见参考平台 merged_trend_by_month）
-- 返回: [{month: '2025-09', points: 8, events: 5}, ...]
```

### 5.6 报告快照版本号获取

```sql
-- 版本链最新版本号
SELECT MAX(version) AS maxv
FROM report_snapshot
WHERE student_id = :sid AND term = :term;

-- 读取指定版本
SELECT payload, version, parent_id, created_at
FROM report_snapshot
WHERE student_id = :sid AND term = :term AND version = :ver;

-- 列出全部版本（审计）
SELECT id, version, parent_id, created_at, generated_by
FROM report_snapshot
WHERE student_id = :sid AND term = :term
ORDER BY version;
```

---

## 6. API 接口契约

### 认证说明

所有接口需要 JWT 鉴权，请求头携带：
```
Authorization: Bearer {JWT_TOKEN}
```

角色权限矩阵:

| 角色 | 查看画像/报告 | 录入成长记录 | 冻结报告 | 生成/确认评语 | 查看班级总览 |
|------|:---------:|:---------:|:------:|:----------:|:---------:|
| 系统管理员 | ✅ 全部 | ✅ 全部 | ✅ 全部 | ✅ 全部 | ✅ 全部 |
| 校级管理者 | ✅ 本校 | ✅ 本校 | ✅ 本校 | ✅ 本校 | ✅ 本校 |
| 任课教师 | ✅ 所教班级 | ✅ 所教班级 | ✅ 所教班级 | ✅ 所教班级 | ✅ 所教班级 |
| 班主任 | ✅ 本班 | ✅ 本班 | ✅ 本班 | ✅ 本班 | ✅ 本班 |

> **跨班隔离**: 非本班/本校学生 ID 请求返回 404（与 student 不存在同处理，防止信息泄露）。

### 统一响应格式

**成功**:
```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

**失败**:
```json
{
  "code": -1,
  "message": "人类可读错误描述",
  "data": null
}
```

**HTTP 状态码约定**:
| 状态码 | 场景 |
|--------|------|
| 200 | 成功 |
| 400 | 参数格式错误、缺少必填项、业务逻辑拒绝（如未生成评语就确认） |
| 401 | 未登录或 token 过期 |
| 403 | 无权限操作该资源 |
| 404 | 学生/班级不存在或跨租户 |
| 422 | 参数校验失败（如 term 格式不合法、dimension 不在枚举中、评语含禁止词） |
| 500 | 服务器内部错误 |

---

### 6.1 学生五育画像

```
GET /api/v1/portfolio/students/{student_id}
```

**用途**: 获取学生五育画像完整数据（双轨制 + 班级百分位 + 学校 z-score + 综合分）。对应 PRD 核心能力 1+2。

**鉴权**: 需要（所有登录用户，跨班隔离）

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| trend | bool | 否 | 是否返回按月分组成长趋势，默认 false |

**成功响应** (200):
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "student_id": "uuid-xxx",
    "name": "张三",
    "class_id": "uuid-yyy",
    "grade": "五年级",
    "base_points": 100,
    "dimensions": {
      "moral": 0,
      "intellectual": 15.5,
      "physical": 0,
      "aesthetic": 0,
      "labor": 0
    },
    "total_growth_point": 15.5,
    "activity_track": {
      "moral": {"count": 0},
      "intellectual": {"count": 12},
      "physical": {"count": 0},
      "aesthetic": {"count": 0},
      "labor": {"count": 0}
    },
    "data_status": {
      "moral": "insufficient",
      "intellectual": "has_data",
      "physical": "insufficient",
      "aesthetic": "insufficient",
      "labor": "insufficient"
    },
    "intellectual_auto": {
      "wrong_question_corrected": {"count": 5, "points": 3.8, "weight": 1},
      "exam_rank_up": {"count": 2, "points": 2.9, "weight": 2},
      "targeted_report": {"count": 1, "points": 0.7, "weight": 1},
      "above_class_avg": {"count": 3, "points": 5.1, "weight": 2},
      "correction_rate_high": {"count": 1, "points": 3.0, "weight": 3},
      "weak_point_conquered": {"count": 0, "points": 0, "weight": 2}
    },
    "intellectual_events": [
      {
        "event_type": "wrong_question_corrected",
        "points": 1,
        "occurred_at": "2025-10-15T08:30:00Z",
        "decay_weight": 0.9139
      }
    ],
    "percentile": {
      "moral": null, "intellectual": 72.5, "physical": null,
      "aesthetic": null, "labor": null, "total": 68.0
    },
    "tier": {
      "moral": null, "intellectual": "B", "physical": null,
      "aesthetic": null, "labor": null, "total": "B"
    },
    "z_score": {
      "moral": null, "intellectual": 0.56, "physical": null,
      "aesthetic": null, "labor": null, "total": 0.42
    },
    "composite": {
      "moral": null, "intellectual": 55.6, "physical": null,
      "aesthetic": null, "labor": null, "total": 54.2
    },
    "rank": {
      "moral": null, "intellectual": 7, "physical": null,
      "aesthetic": null, "labor": null, "total": 8
    },
    "n": {
      "moral": 0, "intellectual": 42, "physical": 0,
      "aesthetic": 0, "labor": 0, "total": 42
    },
    "trend": [
      {"month": "2025-09", "points": 6, "events": 4},
      {"month": "2025-10", "points": 8, "events": 5}
    ]
  }
}
```

**字段说明**:
- `dimensions`: 成就轨（真实成长分），无数据维度为 0（配合 data_status 灰态）
- `intellectual_auto`: 智育自动事件按类型汇总（cap 后 + 时间衰减后）
- `intellectual_events`: 单条事件明细（调试/审计用，含 decay_weight）
- `percentile/tier/z_score/composite`: 无数据维度返回 null
- `trend`: 仅 trend=true 时返回

---

### 6.2 成长记录列表

```
GET /api/v1/portfolio/students/{student_id}/growth-records
```

**用途**: 分页查询学生成长流水。对应 PRD 核心能力 3 的"可回溯"。

**鉴权**: 需要（同画像读权限）

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| dimension | string | 否 | 按维度过滤：moral / intellectual / physical / aesthetic / labor |
| date_from | string | 否 | 起始日期 YYYY-MM-DD |
| date_to | string | 否 | 截止日期 YYYY-MM-DD |
| page | int | 否 | 页码，从 1 开始，默认 1 |
| pageSize | int | 否 | 每页条数，默认 20，最大 100 |

**成功响应** (200):
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "rows": [
      {
        "id": "uuid-001",
        "student_id": "uuid-xxx",
        "dimension": "intellectual",
        "source_type": "wrong_question",
        "source_id": "wq-uuid-123",
        "growth_point": 1,
        "evidence": {"error_type": "calculation", "question_snippet": "3.14×25=?"},
        "note": null,
        "created_by": "uuid-teacher",
        "occurred_at": "2025-10-15T08:30:00Z",
        "created_at": "2025-10-15T08:30:05Z"
      }
    ],
    "total": 35,
    "page": 1,
    "pageSize": 20
  }
}
```

### 6.3 录入成长记录

```
POST /api/v1/portfolio/students/{student_id}/growth-records
```

**用途**: 教师手动录入成长记录（德体美劳为主，智育也可手补）。对应 PRD 核心能力 3。

**鉴权**: 需要（教师及以上角色，本班权限）

**请求体**:
```json
{
  "dimension": "moral",
  "growth_point": 2,
  "source_id": null,
  "evidence": {"description": "主动帮助同学打扫卫生"},
  "note": "值日生请假，张三主动顶替"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| dimension | string | 是 | 五育维度枚举: moral / intellectual / physical / aesthetic / labor |
| growth_point | int | 是 | 成长分值，可为负（扣分场景），范围 [-10, 10] |
| source_id | string | 否 | 关联源记录 ID（如关联某次活动 ID），用于证据链回溯 |
| evidence | object | 否 | 证据 JSON，如 `{"description": "...", "image_urls": [...]}` |
| note | string | 否 | 备注，最长 500 字符 |

**成功响应** (200):
```json
{
  "code": 0,
  "message": "成长记录已录入",
  "data": {
    "id": "uuid-new",
    "student_id": "uuid-xxx",
    "class_id": "uuid-yyy",
    "dimension": "moral",
    "source_type": "manual",
    "source_id": null,
    "growth_point": 2,
    "evidence": {"description": "主动帮助同学打扫卫生"},
    "note": "值日生请假，张三主动顶替",
    "created_by": "uuid-teacher",
    "occurred_at": null,
    "created_at": "2025-10-15T10:00:00Z"
  }
}
```

**错误码**:
| 状态码 | message | 触发条件 |
|--------|---------|---------|
| 400 | dimension 不合法 | dimension 不在五育枚举中 |
| 400 | growth_point 超出范围 | growth_point 不在 [-10, 10] |
| 404 | 学生不存在 | student_id 无效或跨班 |

---

### 6.4 学期报告

```
GET /api/v1/portfolio/students/{student_id}/report
```

**用途**: 获取学期报告（快照优先，无快照实时聚合）。对应 PRD 核心能力 4 的"快照优先→实时聚合"。

**鉴权**: 需要（同画像读权限）

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| term | string | **是** | 学年-学期，如 `2025-2026-1` |
| version | int | 否 | 读取指定版本快照，缺省取最新 |

**成功响应** (200):
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "student_id": "uuid-xxx",
    "name": "张三",
    "class_id": "uuid-yyy",
    "grade": "五年级",
    "term": "2025-2026-1",
    "date_from": "2025-09-01",
    "date_to": "2026-01-31",
    "version": 2,
    "from_snapshot": true,
    "base_points": 100,
    "dimensions": {
      "moral": {
        "growth_records": 1,
        "auto_points": 0,
        "total": 2,
        "detail": null,
        "auto_detail": null
      },
      "intellectual": {
        "growth_records": 0,
        "auto_points": 15.5,
        "total": 15.5,
        "detail": {
          "corrected_wrong_questions": 5,
          "rank_improvements": 2,
          "targeted_reports": 1,
          "above_class_avg": 3,
          "weak_point_conquered": 0,
          "correction_rate_high": 1
        },
        "auto_detail": {
          "wrong_question_corrected": {"count": 5, "points": 3.8},
          "exam_rank_up": {"count": 2, "points": 2.9},
          "targeted_report": {"count": 1, "points": 0.7},
          "above_class_avg": {"count": 3, "points": 5.1},
          "correction_rate_high": {"count": 1, "points": 3.0},
          "weak_point_conquered": {"count": 0, "points": 0}
        }
      },
      "physical": {
        "growth_records": 0,
        "auto_points": 0,
        "total": 0
      },
      "aesthetic": {
        "growth_records": 0,
        "auto_points": 0,
        "total": 0
      },
      "labor": {
        "growth_records": 0,
        "auto_points": 0,
        "total": 0
      }
    },
    "source_stats": {
      "manual": {"points": 2, "count": 1},
      "wrong_question": {"points": 8.5, "count": 8}
    },
    "growth_records_count": 1,
    "total_growth_point": 17.5,
    "raw_total": 17.5,
    "data_status": {
      "moral": "has_data",
      "intellectual": "has_data",
      "physical": "insufficient",
      "aesthetic": "insufficient",
      "labor": "insufficient"
    },
    "data_sources_missing": {
      "moral": [],
      "intellectual": [],
      "physical": ["physical_test"],
      "aesthetic": ["art_activity"],
      "labor": ["labor_record"]
    },
    "baseline": {
      "percentile": {"moral": 85.0, "intellectual": 72.5, "physical": null, "aesthetic": null, "labor": null, "total": 68.0},
      "tier": {"moral": "A", "intellectual": "B", "physical": null, "aesthetic": null, "labor": null, "total": "B"},
      "z_score": {"moral": 1.23, "intellectual": 0.56, "physical": null, "aesthetic": null, "labor": null, "total": 0.42},
      "composite": {"moral": 62.3, "intellectual": 55.6, "physical": null, "aesthetic": null, "labor": null, "total": 54.2},
      "rank": {"moral": 3, "intellectual": 7, "physical": null, "aesthetic": null, "labor": null, "total": 8},
      "n": {"moral": 42, "intellectual": 42, "physical": 0, "aesthetic": 0, "labor": 0, "total": 42}
    },
    "milestones": [
      {
        "event_type": "above_class_avg",
        "name": "超班级均分",
        "points": 2,
        "occurred_at": "2025-12-20T00:00:00Z",
        "decay_weight": 1.0
      }
    ],
    "trend": [
      {"month": "2025-09", "points": 6, "events": 4},
      {"month": "2025-10", "points": 8, "events": 5}
    ],
    "assessment_profile": {
      "has_data": false,
      "result_count": 0,
      "labels": [],
      "by_dimension": {},
      "dimension_percents": {},
      "generated_at": null,
      "domains": []
    },
    "comment": {
      "status": "confirmed",
      "content": "张三同学本学期学习态度端正，坚持订正错题...",
      "confirmed_by": "uuid-teacher",
      "confirmed_at": "2026-01-20T10:00:00Z",
      "is_draft": false,
      "ai_model": "qwen-plus",
      "gate_flagged": false
    }
  }
}
```

**字段说明**:
- `from_snapshot`: true=从 report_snapshot.payload 读取；false=实时聚合
- `version`: 快照版本号；实时聚合时为 null
- `dimensions[dim].detail`: 仅 intellectual 维度有值，其余为 null
- `baseline`: 学期窗口内归一化基准线（雷达图数据源），作为展示主值；`dimensions[dim].total` 为原始成长点（保留兼容，非展示主值）
- `data_sources_missing`: 德体美劳四维标注缺失的 P2 源表（当前仅智育有自动数据源），前端可据此展示"数据待补充"
- `milestones`: 学期内里程碑事件（时间倒序），学期报告场景 `apply_decay=false`
- `comment`: 评语段状态机：absent（未生成）/ pending（AI初稿待确认）/ confirmed（已确认）/ ai_failed（网关失败）
- `assessment_profile`: 行为画像标签（P2 对接锚点层，当前为空结构占位）

---

### 6.5 冻结学期报告

```
POST /api/v1/portfolio/students/{student_id}/report/freeze
```

**用途**: 显式冻结学期报告为快照（学期结束时由教师/管理员触发），幂等新增版本。

**鉴权**: 需要（教师及以上角色，本班权限 + 班主任/校管/管理员额外限制 — 普通任课教师不可冻结他人班级报告）

**请求体**:
```json
{
  "term": "2025-2026-1"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| term | string | 是 | 学年-学期，如 `2025-2026-1`，格式校验 `^\d{4}-\d{4}-[12]$` |

**成功响应** (200):
```json
{
  "code": 0,
  "message": "报告已冻结 (v3)",
  "data": {
    "version": 3,
    "from_snapshot": true,
    "student_id": "uuid-xxx",
    "term": "2025-2026-1",
    "...": "(完整报告结构，同 GET /report)"
  }
}
```

**幂等**: 同一 (student_id, term) 每次调用新增版本（version+1），不覆盖旧快照。

**错误码**:
| 状态码 | message | 触发条件 |
|--------|---------|---------|
| 403 | 只能冻结本班/本校学生报告 | 跨班操作 |
| 403 | 只有该班班主任/任课教师/管理员可冻结报告 | 权限不足 |
| 422 | term 格式应为 学年-学年-学期 | term 格式不合法 |

---

### 6.6 查看 AI 评语

```
GET /api/v1/portfolio/students/{student_id}/report/comment
```

**用途**: 查看指定学期的评语状态（含 AI 初稿、确认内容、闸门标记等原始字段）。

**鉴权**: 需要（同 GET /report 读权限）

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| term | string | **是** | 学年-学期 |

**成功响应** (200):
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "pending",
    "content": "张三同学本学期学习态度端正，坚持订正错题 5 道...",
    "is_draft": true,
    "ai_model": "qwen-plus",
    "gate_flagged": false,
    "comment_id": "uuid-001",
    "ai_content": "张三同学本学期学习态度端正...",
    "confirmed_content": null,
    "created_by": "uuid-teacher",
    "created_at": "2026-01-18T14:00:00Z"
  }
}
```

**评语状态映射**:
| status | content 来源 | is_draft | 含义 |
|--------|-------------|----------|------|
| absent | null | — | 未生成 |
| pending | ai_content | true | AI 初稿，待教师确认 |
| confirmed | confirmed_content（缺省用 ai_content） | false | 已确认 |
| ai_failed | 兜底文案 | false | 网关失败 |

---

### 6.7 生成 AI 评语

```
POST /api/v1/portfolio/students/{student_id}/report/comment/generate
```

**用途**: 基于学期报告数据调用 AI 生成学业评语（复用叙阅现有 `ai_chat_*.py` 的 LLM 能力，千问模型）。含禁词闸门 fail-closed。

**鉴权**: 需要（同冻结权限：本班班主任/任课教师/校管/管理员）

**请求体**:
```json
{
  "term": "2025-2026-1"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| term | string | 是 | 学年-学期 |

**成功响应** (200):
```json
{
  "code": 0,
  "message": "评语已生成（待教师确认）",
  "data": {
    "status": "pending",
    "content": "张三同学本学期学习态度端正...",
    "is_draft": true,
    "ai_model": "qwen-plus",
    "gate_flagged": false
  }
}
```

**含禁词场景**:
```json
{
  "code": 0,
  "message": "评语已生成（含禁词已清洗）",
  "data": {
    "status": "pending",
    "content": "(清洗后的安全内容)",
    "is_draft": true,
    "gate_flagged": true
  }
}
```

**网关失败场景**:
```json
{
  "code": 0,
  "message": "评语生成失败（AI 网关不可用），已记录兜底状态",
  "data": {
    "status": "ai_failed",
    "content": "本学期学业评语暂未生成，请联系班主任当面沟通孩子的成长情况。",
    "is_draft": false
  }
}
```

**处理逻辑**:
1. 实时聚合学期报告数据（调用 `compute_report_for_student`）
2. 组装 prompt（智育指标 + 五育 data_status 骨架 + 标签 + 里程碑 + 趋势）→ 调用千问 LLM
3. LLM 输出过 `FORBIDDEN_WORDS` 闸门（见 7.2 节）：清洗含禁词的句子，清洗后为空 → 用兜底文案
4. UPSERT `assessment_comment`（同 student+term 覆盖写，幂等）
5. 网关异常/超时 → `status='ai_failed'` + 兜底文案，不阻塞主流程

---

### 6.8 确认评语

```
POST /api/v1/portfolio/students/{student_id}/report/comment/confirm
```

**用途**: 教师确认评语（可修改文本后确认）。确认时同样过禁词闸门（fail-closed：含禁词 422 拒绝）。

**鉴权**: 需要（同冻结权限）

**请求体**:
```json
{
  "term": "2025-2026-1",
  "content": "张三同学本学期数学学习有明显进步...（教师可修改 AI 初稿）"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| term | string | 是 | 学年-学期 |
| content | string | 否 | 确认后的评语文本（可修改 AI 初稿），最长 2000 字符。缺省使用 AI 初稿 |

**成功响应** (200):
```json
{
  "code": 0,
  "message": "评语已确认",
  "data": {
    "status": "confirmed",
    "content": "张三同学本学期数学学习有明显进步...",
    "is_draft": false,
    "confirmed_by": "uuid-teacher",
    "confirmed_at": "2026-01-20T10:00:00Z"
  }
}
```

**错误码**:
| 状态码 | message | 触发条件 |
|--------|---------|---------|
| 400 | 该学期尚无评语，请先生成 | assessment_comment 不存在 |
| 400 | 评语生成失败，无法确认，请重新生成 | status=ai_failed |
| 422 | 确认评语含人格归因词，请修改后重试 | content 含禁止词 |

---

### 6.9 下载 PDF 报告

```
GET /api/v1/portfolio/students/{student_id}/report/pdf
```

**用途**: 下载学期报告 PDF（`reportlab` 渲染中文成档）。对应 PRD 核心能力 4 的"PDF 导出"。

**鉴权**: 需要（同 GET /report 读权限）

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| term | string | **是** | 学年-学期 |
| version | int | 否 | 读取指定版本快照，缺省最新 |

**成功响应** (200): `Content-Type: application/pdf`，`Content-Disposition: attachment; filename*=UTF-8''%E5%AD%A6%E6%9C%9F%E6%88%90%E9%95%BF%E6%8A%A5%E5%91%8A_%E5%BC%A0%E4%B8%89_2025-2026-1.pdf`

**PDF 内容结构**:
1. 标题区：学生姓名 / 学校 / 年级 / 学期 / 报告版本号
2. 五育成长表现：每维展示 data_status + 成长分 + 智育明细（intellectual 维度展开 7 事件明细）
3. 智育班级相对位置：综合分 + 档位 + 班级百分位
4. 行为画像标签（无则灰态"暂无测评标签"）
5. 教师评语（confirmed > pending(标注"待教师确认") > ai_failed(兜底文案)）
6. 页脚：生成时间 + 合规声明

**技术选型**: `reportlab`（纯 Python，Windows 部署友好，叙阅已在 Windows 运行，无需额外系统库）。中文字体优先使用 Windows 自带微软雅黑/黑体/宋体，不可用时回退 CID 字体 STSong-Light。

---

### 6.10 班级画像总览

```
GET /api/v1/portfolio/classes/{class_id}
```

**用途**: 全班学生五育画像总览（双轨制 + 排名 + 排序对比 + 档位分布）。对应 PRD 核心能力 5。

**鉴权**: 需要（同班级查看权限）

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| sort | string | 否 | 排序方式：total（默认，按综合成就分降序）/ name（按姓名升序） |

**成功响应** (200):
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "class_id": "uuid-yyy",
    "class_name": "五(3)班",
    "grade": "五年级",
    "school_id": "uuid-school",
    "student_count": 42,
    "sorted_by": "total",
    "students": [
      {
        "student_id": "uuid-001",
        "name": "张三",
        "student_number": "2024001",
        "dimensions": {
          "moral": 0,
          "intellectual": 15.5,
          "physical": 0,
          "aesthetic": 0,
          "labor": 0
        },
        "total_growth_point": 15.5,
        "activity_track": {
          "moral": {"count": 0},
          "intellectual": {"count": 12},
          "physical": {"count": 0},
          "aesthetic": {"count": 0},
          "labor": {"count": 0}
        },
        "data_status": {
          "moral": "insufficient",
          "intellectual": "has_data",
          "physical": "insufficient",
          "aesthetic": "insufficient",
          "labor": "insufficient"
        },
        "percentile": {"intellectual": 72.5, "total": 68.0, "moral": null, "physical": null, "aesthetic": null, "labor": null},
        "tier": {"intellectual": "B", "total": "B", "moral": null, "physical": null, "aesthetic": null, "labor": null},
        "z_score": {"intellectual": 0.56, "total": 0.42, "moral": null, "physical": null, "aesthetic": null, "labor": null},
        "composite": {"intellectual": 55.6, "total": 54.2, "moral": null, "physical": null, "aesthetic": null, "labor": null},
        "rank": {"intellectual": 7, "total": 8, "moral": null, "physical": null, "aesthetic": null, "labor": null},
        "n": {"intellectual": 42, "total": 42, "moral": 0, "physical": 0, "aesthetic": 0, "labor": 0}
      }
    ],
    "averages": {
      "moral": 0,
      "intellectual": 8.2,
      "physical": 0,
      "aesthetic": 0,
      "labor": 0,
      "total": 8.2
    },
    "tier_distribution": {
      "A+": 3,
      "A": 8,
      "B": 18,
      "C": 8,
      "D": 5
    }
  }
}
```

**字段说明**:
- `averages`: 班级各维平均（仅统计 has_data 学生，避免灰态 0 分拉低均值）
- `tier_distribution`: 综合档位分布（total 维度，统计全班）

---

## 7. AI 评语规范

### 7.1 Prompt 模板

```
System: 你是一位经验丰富的班主任，负责撰写学生学期学业评语。
要求：
1. 基于给定的学期成长数据，客观描述孩子的学习过程与行为表现；
2. 语言正向、具体、有温度，多用行为观察（如「本学期坚持订正错题」），少用抽象评价；
3. 严禁人格归因与贴标签：不得出现「粗心」「懒惰」「态度差」「性格缺陷」「内向」「多动」等字眼；
   不得对孩子的智力、性格、品行做定性判断；
4. 篇幅 150~220 字，结尾给 1~2 条可执行的成长建议；
5. 直接输出评语正文，不要加标题或引号。

User: 学生姓名：{name}；年级：{grade}；学期：{term}
一、五育数据状态：道德：{status}；智育：{status}；体育：{status}；美育：{status}；劳育：{status}
二、智育表现：订正错题 X 道；考试成绩提升 X 次；生成靶向提升报告 X 份；超班级均分 X 次；攻克薄弱点 X 次
三、班级相对位置：综合分 XX.X（满分100）；档位 X；班级百分位 PXX
四、本学期里程碑：{(日期) 事件名；...}
五、行为画像白名单标签：（有则列出，无则"暂无测评标签（不虚构）"）
```

### 7.2 禁止词表（闸门 fail-closed）

以下词汇（含同义/近义变形）出现在评语中时触发清洗——去掉含禁止词的整句；清洗后为空则用兜底文案。

```
人格归因禁止词（AI 输出 + 教师人工输入均拦截）:
粗心、马虎、懒惰、懒散、态度差、态度不端正、性格缺陷、性格问题、
内向、孤僻、多动、好动、注意力不集中（可用"课堂专注度有提升空间"替代）、
笨、迟钝、智商、天赋差、不是读书的料、没救了、差生、后进生

教师确认评语也过闸门——含禁词直接 422 拒绝（官方成档内容不降级）。
```

**兜底文案**: `"本学期学业评语暂未生成，请联系班主任当面沟通孩子的成长情况。"`

### 7.3 合规红线

1. 评语只进 `assessment_comment` 表和 `report_snapshot.payload`，**绝不写 `student_portfolio.dimensions` 或参与五育综合分**（评分引擎不消费评语表）
2. AI 评语标注"AI 辅助生成"（PDF 页脚 + 界面提示），教师确认为最终版本
3. 禁止词闸门 fail-closed：宁可误拦不可漏放

---

## 8. 验收标准

### 8.1 功能验收

| # | 验收项 | 验收方法 | 通过标准 |
|---|--------|---------|---------|
| F1 | 错题订正自动计分 | 订正 5 道错题 → 查 GET /portfolio | `intellectual_auto.wrong_question_corrected.count=5`，成就分增加约 4.5（衰减后） |
| F2 | 排名提升自动计分 | 同科两次考试 rank 从 10→5 | `intellectual_auto.exam_rank_up.count=1`，成就分 +2×w |
| F3 | 超均分自动计分 | 数学考 92 分，班级均分 85 | `intellectual_auto.above_class_avg.count=1`，成就分 +2×w |
| F4 | 订正率达标自动计分 | 10 道错题订正 9 道（90%） | `intellectual_auto.correction_rate_high.count=1`，成就分 +3×w |
| F5 | 薄弱点攻克自动计分 | 同一知识点 3 道错题全部订正 | `intellectual_auto.weak_point_conquered.count=1`，成就分 +2×w |
| F6 | 学期上限防刷 | 一学期 50 条订正 | 只计最近 30 条（cap=30） |
| F7 | 时间衰减 | 60 天前的 +2 事件 | 衰减后约 1.03（w≈0.513） |
| F8 | 双轨制输出 | 查 GET /portfolio | 返回 `dimensions`（成就轨）+ `activity_track`（活跃轨）+ `data_status` |
| F9 | 无数据灰态 | 查从未考试的学生 | data_status 全部 `insufficient`，tier/percentile 全部 null |
| F10 | 班级百分位 | 查 GET /portfolio | `percentile.intellectual` 有效值，与排名一致 |
| F11 | 学校 z-score | 查 GET /portfolio | `z_score.intellectual` 在 [-3, 3] 范围 |
| F12 | 综合分归一化 | 查 GET /portfolio | `composite.intellectual` 在 [0, 100] 范围 |
| F13 | 手动录入成长记录 | POST /growth-records | 返回记录，`source_type=manual` |
| F14 | 成长记录可回溯 | GET /growth-records | 返回 evidence + source_id + note |
| F15 | 学期报告快照优先 | freeze 后 GET /report | `from_snapshot=true`，version > 0 |
| F16 | 学期报告实时聚合 | 未 freeze 时 GET /report | `from_snapshot=false`，baseline 非空 |
| F17 | 快照版本链幂等 | freeze 两次同 term | version=2，parent_id 指向 v1 |
| F18 | AI 评语生成 | POST /comment/generate | 返回 state=pending，内容非空 |
| F19 | AI 评语禁词闸门 | 触发含"粗心"的 mock 输出 | 响应 `gate_flagged=true`，内容不含"粗心" |
| F20 | 教师确认评语 | POST /comment/confirm | status=confirmed，confirmed_content 非空 |
| F21 | 确认禁词拦截 | confirm 含"懒惰" | 422 拒绝 |
| F22 | PDF 导出 | GET /report/pdf | Content-Type=application/pdf，文件 > 10KB |
| F23 | 班级画像总览 | GET /classes/{class_id} | students 数组有排名，averages 各维有值，tier_distribution 合计=student_count |
| F24 | 跨班隔离 | 教师 A 查教师 B 班级的学生 | 404（与不存在同处理） |

### 8.2 性能验收

| # | 验收项 | 验收方法 | 通过标准 |
|---|--------|---------|---------|
| P1 | 单生画像响应时间 | GET /portfolio，班级 50 人 | < 500ms（含班级/学校级聚合） |
| P2 | 班级总览响应时间 | GET /classes/{class_id}，50 人 | < 2s |
| P3 | AI 评语生成时间 | POST /comment/generate | < 15s（含 LLM 调用） |
| P4 | PDF 生成时间 | GET /report/pdf | < 5s |
| P5 | 聚合查询无 N+1 | 班级 50 人画像 | 一次班级级批量查询，不对每个学生单独查 |

### 8.3 数据一致性验收

| # | 验收项 | 验收方法 | 通过标准 |
|---|--------|---------|---------|
| D1 | 成就分 = 流水合计 | GET /portfolio 的 total vs Σ growth_records + 智育自动分 | 一致（误差 < 0.1） |
| D2 | 快照不可变 | 修改源数据后读同版本快照 | 快照 payload 不变 |
| D3 | 幂等录入 | 同 source_type + source_id 重复 POST | 不产生重复流水 |
| D4 | 百分比合计 | 班级 tier_distribution | A++A+B+C+D = student_count |
