# 性格兴趣测评题组契约

> 版本: 1.0 | 日期: 2026-08-11 | 数据库: MySQL 8.0+ | 后端: FastAPI + SQLAlchemy | 前端: React + TypeScript
>
> 对应需求：自研轻量性格/兴趣测评题组，参考霍兰德（RIASEC）+ MBTI 维度设计，不照搬版权量表。
> 目的：生成学生性格兴趣画像，作为五育画像（student_portfolio）的补充维度（参考维，不进五育评分）。
> 参考实现：teacher-ai-platform（种春风）P1-C 评估域。

---

## 目录

1. [设计原则与学术安全线](#1-设计原则与学术安全线)
2. [表结构（MySQL DDL）](#2-表结构mysql-ddl)
3. [题组内容规范](#3-题组内容规范)
4. [白名单标签体系与伦理闸门](#4-白名单标签体系与伦理闸门)
5. [施测/计分流程](#5-施测计分流程)
6. [监护人同意流程](#6-监护人同意流程)
7. [API 契约](#7-api-契约)
8. [与画像的关系](#8-与画像的关系)
9. [验收标准](#9-验收标准)

---

## 1. 设计原则与学术安全线

### 1.1 三层物理隔离

```
锚点层（assessment_result）  → 只存测评原始结果 + 白名单标签，不进评分
证据层（tag_schema.labels）   → 白名单闸门过滤后的标签，只作参考维
评分层（student_portfolio）   → 闭合 number 结构，不接收标签/文本
```

**核心约束**：
- `assessment_result.purpose` 只允许 `'anchor'`（DB CHECK 约束兜底）
- 五育综合分引擎不消费 `assessment_result` 表
- 标签只写 `assessment_result.tag_schema`，绝不写 `student_portfolio.dimensions`

### 1.2 学术安全红线

| 红线 | 机制 |
|------|------|
| 不贴人格归因标签 | 白名单闸门（fail-closed）+ 禁止词列表 |
| 不做信效度宣称 | 文案仅做行为倾向描述，不标注"类型""性格" |
| 不照搬版权量表 | 自研维度命名 + 自研题面，规避 VARK/DISC/MI/Holland 商标 |
| 未成年人测评需监护人同意 | consent 状态机（not_required/granted/withdrawn） |
| 数据可撤回不删除 | withdraw 冻结展示，保留审计 |

### 1.3 维度设计（自研 5+4 维）

参考 RIASEC（6 维）+ MBTI（4 维）的学术框架，但不使用其命名与题项，落地为更适配 K12 场景的自研维度：

**核心 5 维（行为观察层，对应参考实现 seed data）**：

| 维度键 | 中文名 | 理论参考 | 说明 |
|--------|--------|---------|------|
| `learning_style` | 学习方式偏好 | MBTI S/N + VARK 启发 | 观察学生获取/处理信息的习惯方式 |
| `interest` | 兴趣领域 | RIASEC 启发 | 观察学生在动手/阅读/运动/社交上的偏好分布 |
| `social_style` | 交往风格 | MBTI E/I 启发 | 观察学生在群体活动中的参与模式 |
| `emotion_regulation` | 情绪调节方式 | 自研 | 观察学生面对情绪波动时的应对方式 |
| `challenge_coping` | 挑战应对倾向 | 自研 | 观察学生面对难题/挫折时的策略 |

**扩展 4 维（v2 预留，不要求 v1 实现）**：

| 维度键 | 中文名 | 说明 |
|--------|--------|------|
| `task_persistence` | 任务坚持度 | 做事持久性/专注度 |
| `cognitive_flexibility` | 认知灵活性 | 切换思维模式的能力倾向 |
| `collaboration_style` | 协作风格 | 团队中的角色偏好 |
| `self_efficacy` | 自我效能感 | 对自身能力的信心程度 |

### 1.4 根-叶映射五育（标签不进评分，作参考维）

测评白名单标签 **不参与** 五育综合分计算，但可作为 AI 评语/学期报告的补充维度输入：

```
测评标签 → assessment_profile（报告数据）→ AI 评语生成 prompt（"该生偏好动手实践，建议多安排实验类任务"）
                                                      ↑ 教师确认后方可写入报告快照
```

**映射关系（仅作 AI 评语生成建议，不量化加分）**：

| 测评维度 | 建议映射五育 | 评语示例 |
|---------|------------|---------|
| learning_style | 智育 | "建议提供多感官学习材料" |
| interest | 美育/劳育 | "对动手创作类活动兴趣高" |
| social_style | 德育 | "班级活动中偏向主动组织" |
| emotion_regulation | 德育/体育 | "情绪调节方式较灵活" |
| challenge_coping | 智育 | "面对难题倾向坚持解决" |

---

## 2. 表结构（MySQL DDL）

> 命名规范对齐叙阅现有基线：
> - 主键：`VARCHAR(36)`，默认 `gen_uuid()`（Python uuid4）
> - 字段名：snake_case
> - 时间：DATETIME，存 UTC
> - 引擎：InnoDB，字符集：utf8mb4
> - 外键策略：`ON DELETE CASCADE`（业务数据）/ `ON DELETE SET NULL`（可选关联）
> - JSON 字段：MySQL 原生 `JSON` 类型

### 2.1 assessment_definitions（题组定义表）

**用途**：存储自研轻量题组定义，包括题面、选项、维度映射、计分规则。运营人员可动态增删改。

```sql
CREATE TABLE assessment_definitions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name VARCHAR(128) NOT NULL COMMENT '题组名称，如"班级自我认识轻量问卷（自研）"',
    domain VARCHAR(64) NOT NULL COMMENT '测评域: personality/interest/learning_style/self_built_survey',
    grade_range VARCHAR(32) NOT NULL DEFAULT 'all' COMMENT '适用学段: primary/junior/senior/all',
    version INT NOT NULL DEFAULT 1 COMMENT '版本号，从1开始递增',
    status VARCHAR(16) NOT NULL DEFAULT 'draft' COMMENT '状态: draft/active/retired',
    consent_required TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否需要监护人同意，0=否 1=是',
    questions JSON NOT NULL COMMENT '题面数组，见下方结构说明',
    description TEXT NULL COMMENT '题组说明/指导语',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间（UTC）',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（UTC）',

    INDEX idx_ad_domain (domain),
    INDEX idx_ad_status (status),
    INDEX idx_ad_domain_status (domain, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**`questions` JSON 字段结构**（数组，每题一个对象）：

```json
[
  {
    "id": "ls_q1",
    "dim": "learning_style",
    "text": "学习新内容时，你更习惯哪种方式？",
    "reverse_scored": false,
    "options": [
      {
        "key": "a",
        "text": "先看老师演示或例题",
        "dim": "ls_watch_example",
        "score": 1
      },
      {
        "key": "b",
        "text": "自己先试着做一做",
        "dim": "ls_try_self",
        "score": 1
      },
      {
        "key": "c",
        "text": "边做边翻书查资料",
        "dim": "ls_mixed",
        "score": 1
      }
    ]
  }
]
```

**字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 题号，题组内唯一，如 `ls_q1`（learning_style 第1题） |
| `dim` | string | 是 | 顶层维度键（5维之一） |
| `text` | string | 是 | 题干文字，适配小学3年级以上阅读水平 |
| `reverse_scored` | bool | 否 | 是否反向计分，默认 false（v1 暂不使用，预留） |
| `options` | array | 是 | 选项数组，2-4个 |
| `options[].key` | string | 是 | 选项键，如 `a`/`b`/`c`/`d` |
| `options[].text` | string | 是 | 选项文字 |
| `options[].dim` | string | 是 | 子维度键，映射到 LABEL_MAP 白名单标签 |
| `options[].score` | int | 否 | 选项分值，默认 1（v1 等权计分，预留加权） |

### 2.2 assessment_sessions（施测会话表）

**用途**：记录每次施测的会话，支持 `class_batch`（教师集中批次）和 `self`（学生自主重测）两种模式。

**状态机**：

```
pending ─→ in_progress ─→ submitted ─→ graded
  │                                      │
  └────────────── canceled ←─────────────┘（仅 pending/in_progress 可取消）
```

```sql
CREATE TABLE assessment_sessions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID → students.id',
    definition_id VARCHAR(36) NOT NULL COMMENT '题组定义ID → assessment_definitions.id',
    test_mode VARCHAR(16) NOT NULL DEFAULT 'class_batch' COMMENT '施测模式: class_batch/self',
    batch_id VARCHAR(36) NULL COMMENT '批次ID（class_batch模式下关联同一批次）',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '状态: pending/in_progress/submitted/graded/canceled',
    proctored_by VARCHAR(36) NULL COMMENT '监考/施测教师ID → users.id',
    created_by VARCHAR(36) NULL COMMENT '会话创建者ID → users.id',
    taken_at DATETIME NULL COMMENT '学生开始作答时间',
    submitted_at DATETIME NULL COMMENT '提交时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_as_student (student_id),
    INDEX idx_as_definition (definition_id),
    INDEX idx_as_status (status),
    INDEX idx_as_batch (batch_id),
    INDEX idx_as_student_def (student_id, definition_id),
    CONSTRAINT fk_as_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_as_definition FOREIGN KEY (definition_id) REFERENCES assessment_definitions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2.3 assessment_results（锚点结果表）

**用途**：存储学生作答后的锚点结果，物理隔离于五育评分体系。每份作答生成一条记录。

**学术红线**：`purpose` 字段有 CHECK 约束强制 `'anchor'`，防止评分用途误入。

**guardian_consent 状态机**：

```
not_required ─→ granted ─→ withdrawn ─→ granted ─→ ...（可反复撤回/恢复）
                                                    version 每次恢复 +1
```

```sql
CREATE TABLE assessment_results (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID → students.id',
    definition_id VARCHAR(36) NULL COMMENT '题组定义ID → assessment_definitions.id',
    session_id VARCHAR(36) NULL COMMENT '关联会话ID → assessment_sessions.id',
    domain VARCHAR(64) NOT NULL COMMENT '测评域，继承自题组的domain',
    purpose VARCHAR(16) NOT NULL DEFAULT 'anchor' COMMENT '用途: 强制anchor（锚点），DB约束兜底',
    tag_schema JSON NOT NULL COMMENT '白名单标签结果 {labels, dimension_percents, generated_at}',
    raw_score JSON NULL COMMENT '原始作答数据 {answers, dimension_points, total_answered}',
    guardian_consent JSON NOT NULL COMMENT '监护人同意状态 {status, version, granted_at, withdrawn_at}',
    created_by VARCHAR(36) NULL COMMENT '创建者ID → users.id（教师代录=教师ID，学生自测=学生user_id）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_ar_student (student_id),
    INDEX idx_ar_domain (domain),
    INDEX idx_ar_definition (definition_id),
    INDEX idx_ar_session (session_id),
    CONSTRAINT fk_ar_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_ar_definition FOREIGN KEY (definition_id) REFERENCES assessment_definitions(id) ON DELETE SET NULL,
    CONSTRAINT fk_ar_session FOREIGN KEY (session_id) REFERENCES assessment_sessions(id) ON DELETE SET NULL,
    CONSTRAINT chk_ar_purpose CHECK (purpose = 'anchor')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**`tag_schema` JSON 结构**：

```json
{
  "labels": ["偏好先看例题再动笔", "对动手创作类活动兴趣高", "班级活动中偏向主动组织"],
  "dimension_percents": {
    "learning_style": 25.0,
    "interest": 20.0,
    "social_style": 20.0,
    "emotion_regulation": 20.0,
    "challenge_coping": 15.0
  },
  "dimension_points": {
    "learning_style": 5,
    "interest": 4,
    "social_style": 4,
    "emotion_regulation": 4,
    "challenge_coping": 3
  },
  "generated_at": "2026-08-11T08:30:00Z"
}
```

**`guardian_consent` JSON 结构**：

```json
{
  "status": "not_required",
  "version": 1,
  "granted_at": null,
  "withdrawn_at": null
}
```

### 2.4 assessment_answers（作答明细表）

**用途**：存储每题作答明细（可选的细粒度留存，v1 推荐直接写 raw_score JSON，本表用于需要逐题分析/审计时启用）。

```sql
CREATE TABLE assessment_answers (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    result_id VARCHAR(36) NOT NULL COMMENT '锚点结果ID → assessment_results.id',
    question_id VARCHAR(32) NOT NULL COMMENT '题号，如 ls_q1',
    option_key VARCHAR(8) NOT NULL COMMENT '选择的选项键',
    dim VARCHAR(64) NOT NULL COMMENT '顶层维度键',
    option_dim VARCHAR(64) NULL COMMENT '子维度键',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_aa_result (result_id),
    INDEX idx_aa_result_question (result_id, question_id),
    CONSTRAINT fk_aa_result FOREIGN KEY (result_id) REFERENCES assessment_results(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

> **v1 决策建议**：`assessment_answers` 表为可选。如果不需要逐题明细查询，仅依赖 `assessment_results.raw_score.answers` 字段（JSON 内嵌）即可。本表在需要跨学生聚合某题作答分布时启用。

---

## 3. 题组内容规范

### 3.1 种子题组（v1 首个内置题组）

**题组标识**：`"班级自我认识轻量问卷（自研）v1"`
**domain**：`self_built_survey`
**grade_range**：`all`（小学3年级+ / 初中 / 高中通用措辞）
**consent_required**：`true`
**题目数**：≥20 题（5 维 × 4-5 题）

### 3.2 题项编写规范

| 规范项 | 规则 |
|--------|------|
| 措辞 | 避免抽象词汇（如"价值观""认知偏好"），用日常用语 |
| 题干长度 | ≤40 汉字，适配手机竖屏展示 |
| 选项数 | 2-4 个，互斥且穷举 |
| 选项长度 | ≤20 汉字 |
| 反向计分 | v1 不使用（等权计分），`reverse_scored` 字段预留 v2 |
| 版权合规 | 不照搬任何已知量表题项，不标注"类型""人格""性格" |
| 子维度键 | 对应 LABEL_MAP 白名单键，每个选项必须标注 `dim` |
| 指导语 | 每次施测显示指导语："本问卷帮助你了解自己的学习和交往习惯，没有对错，请按真实情况选择。" |

### 3.3 完整种子题面（21题，对齐参考实现 seed_assessment_definition.py）

以下为题组 `self_learning_survey_v1` 的完整种子题面（JSON 格式，即 `assessment_definitions.questions` 的内容）：

<details>
<summary>点击展开完整 21 题 JSON</summary>

```json
[
  {"id":"ls_q1","dim":"learning_style","text":"学习新内容时，你更习惯哪种方式？","options":[{"key":"a","text":"先看老师演示或例题","dim":"ls_watch_example"},{"key":"b","text":"自己先试着做一做","dim":"ls_try_self"},{"key":"c","text":"边做边翻书查资料","dim":"ls_mixed"}]},
  {"id":"ls_q2","dim":"learning_style","text":"记住新知识时，你更习惯怎么做？","options":[{"key":"a","text":"读几遍文字来记住","dim":"ls_read"},{"key":"b","text":"听别人讲一遍记住","dim":"ls_listen"},{"key":"c","text":"动手写一遍或做一遍记住","dim":"ls_handson"}]},
  {"id":"ls_q3","dim":"learning_style","text":"遇到一道新题时，你通常先做什么？","options":[{"key":"a","text":"先看例题模仿做法","dim":"ls_watch_example"},{"key":"b","text":"自己先想办法试试","dim":"ls_try_self"},{"key":"c","text":"和同学讨论一下","dim":"ls_discuss"}]},
  {"id":"ls_q4","dim":"learning_style","text":"小组讨论时，你更愿意怎么参与？","options":[{"key":"a","text":"先听别人讲，再提问","dim":"ls_listen"},{"key":"b","text":"自己发言讲想法","dim":"ls_discuss"},{"key":"c","text":"边听边记笔记","dim":"ls_read"}]},
  {"id":"ls_q5","dim":"learning_style","text":"做手工或实验时，你更喜欢？","options":[{"key":"a","text":"照着步骤一步步来","dim":"ls_watch_example"},{"key":"b","text":"自己琢磨新做法","dim":"ls_try_self"},{"key":"c","text":"边做边改进","dim":"ls_handson"}]},
  {"id":"int_q1","dim":"interest","text":"空闲时间，你更想做什么？","options":[{"key":"a","text":"动手做手工、画画或拼装","dim":"int_making"},{"key":"b","text":"看书或想事情","dim":"int_reading"},{"key":"c","text":"出去跑跳运动","dim":"int_sports"},{"key":"d","text":"找朋友聊天一起玩","dim":"int_social"}]},
  {"id":"int_q2","dim":"interest","text":"学校社团如果有这些，你最想选哪个？","options":[{"key":"a","text":"手工或科学实验社","dim":"int_making"},{"key":"b","text":"阅读或写作社","dim":"int_reading"},{"key":"c","text":"田径或球类社","dim":"int_sports"},{"key":"d","text":"合唱或演讲社","dim":"int_social"}]},
  {"id":"int_q3","dim":"interest","text":"周末你更愿意怎么安排？","options":[{"key":"a","text":"做一件小制作","dim":"int_making"},{"key":"b","text":"读一本书","dim":"int_reading"},{"key":"c","text":"去户外活动","dim":"int_sports"},{"key":"d","text":"和家人朋友聚会","dim":"int_social"}]},
  {"id":"int_q4","dim":"interest","text":"上课时，哪类课最能让你提起精神？","options":[{"key":"a","text":"美术、劳动或科学课","dim":"int_making"},{"key":"b","text":"语文、阅读课","dim":"int_reading"},{"key":"c","text":"体育课","dim":"int_sports"},{"key":"d","text":"班会或交流多的课","dim":"int_social"}]},
  {"id":"ss_q1","dim":"social_style","text":"班里组织活动时，你更常扮演什么角色？","options":[{"key":"a","text":"主动出主意、组织大家","dim":"ss_organize"},{"key":"b","text":"配合大家、完成任务","dim":"ss_participate"},{"key":"c","text":"有时组织、有时配合","dim":"ss_mixed"}]},
  {"id":"ss_q2","dim":"social_style","text":"和同学一起做任务时，你更喜欢？","options":[{"key":"a","text":"带头分工、安排步骤","dim":"ss_organize"},{"key":"b","text":"认真完成分到的部分","dim":"ss_participate"},{"key":"c","text":"大家一起商量决定","dim":"ss_mixed"}]},
  {"id":"ss_q3","dim":"social_style","text":"班里要选一个活动负责人，你会？","options":[{"key":"a","text":"主动报名","dim":"ss_organize"},{"key":"b","text":"觉得别人做更合适","dim":"ss_participate"},{"key":"c","text":"有人推选我就做","dim":"ss_mixed"}]},
  {"id":"ss_q4","dim":"social_style","text":"参加集体游戏时，你更愿意？","options":[{"key":"a","text":"当队长给大家分工","dim":"ss_organize"},{"key":"b","text":"认真玩好自己这一份","dim":"ss_participate"},{"key":"c","text":"随大家一起玩","dim":"ss_mixed"}]},
  {"id":"er_q1","dim":"emotion_regulation","text":"心情不好的时候，你更愿意？","options":[{"key":"a","text":"一个人待一会儿","dim":"er_alone"},{"key":"b","text":"找人说一说","dim":"er_talk"},{"key":"c","text":"做点别的事分散注意","dim":"er_mixed"}]},
  {"id":"er_q2","dim":"emotion_regulation","text":"遇到委屈的事，你会？","options":[{"key":"a","text":"自己消化，慢慢就好","dim":"er_alone"},{"key":"b","text":"告诉信任的人","dim":"er_talk"},{"key":"c","text":"过一会儿就忘了","dim":"er_mixed"}]},
  {"id":"er_q3","dim":"emotion_regulation","text":"考试没考好，你通常？","options":[{"key":"a","text":"自己安静想一想","dim":"er_alone"},{"key":"b","text":"找老师或朋友聊聊","dim":"er_talk"},{"key":"c","text":"去跑一跑、活动一下","dim":"er_mixed"}]},
  {"id":"er_q4","dim":"emotion_regulation","text":"感到有压力时，哪种方式对你最有用？","options":[{"key":"a","text":"独处放松一下","dim":"er_alone"},{"key":"b","text":"说出来心里好受些","dim":"er_talk"},{"key":"c","text":"用兴趣爱好转移注意","dim":"er_mixed"}]},
  {"id":"cc_q1","dim":"challenge_coping","text":"遇到很难的题目，你通常？","options":[{"key":"a","text":"坚持想办法解出来","dim":"cc_persist"},{"key":"b","text":"先跳过，做完其他再回来","dim":"cc_skip_then_back"},{"key":"c","text":"请老师或同学讲解","dim":"cc_ask_help"}]},
  {"id":"cc_q2","dim":"challenge_coping","text":"任务做到一半发现很难，你会？","options":[{"key":"a","text":"坚持做完再休息","dim":"cc_persist"},{"key":"b","text":"休息一下再继续","dim":"cc_mixed"},{"key":"c","text":"换个任务，之后再说","dim":"cc_skip_then_back"}]},
  {"id":"cc_q3","dim":"challenge_coping","text":"一道题做错了，你会？","options":[{"key":"a","text":"马上找原因改过来","dim":"cc_persist"},{"key":"b","text":"对照答案看一遍","dim":"cc_mixed"},{"key":"c","text":"记下来问别人","dim":"cc_ask_help"}]},
  {"id":"cc_q4","dim":"challenge_coping","text":"新学的知识有点难懂，你会？","options":[{"key":"a","text":"反复看直到弄懂","dim":"cc_persist"},{"key":"b","text":"先记下来慢慢理解","dim":"cc_skip_then_back"},{"key":"c","text":"找老师或同学讲解","dim":"cc_ask_help"}]}
]
```

</details>

---

## 4. 白名单标签体系与伦理闸门

### 4.1 设计约束

- **fail-closed**：标签生成强制过白名单，不在白名单直接丢弃，含禁止词直接丢弃
- **不外造词**：`generate_labels` 只从 `LABEL_MAP` 取值，不做 LLM 自由生成
- **不写评分**：标签只写 `assessment_result.tag_schema`，绝不写 `student_portfolio.dimensions`

### 4.2 白名单标签库（LABEL_MAP）

> 文案全部为行为观察 / 学习方式 / 兴趣倾向描述，避开人格归因表达。

| 子维度键 | 白名单标签文案 | 所属维度 |
|---------|-------------|---------|
| `ls_watch_example` | 偏好先看例题再动笔 | learning_style |
| `ls_try_self` | 偏好先动手尝试再对答案 | learning_style |
| `ls_handson` | 偏好动手实践 | learning_style |
| `ls_listen` | 适合听觉输入 | learning_style |
| `ls_read` | 适合文字阅读输入 | learning_style |
| `ls_discuss` | 适合讨论互动式学习 | learning_style |
| `ls_mixed` | 学习方式较灵活 | learning_style |
| `int_making` | 对动手创作类活动兴趣高 | interest |
| `int_reading` | 对阅读思考类活动兴趣高 | interest |
| `int_sports` | 对运动户外类活动兴趣高 | interest |
| `int_social` | 对与人交流类活动兴趣高 | interest |
| `int_balanced` | 兴趣领域较均衡 | interest |
| `ss_organize` | 班级活动中偏向主动组织 | social_style |
| `ss_participate` | 班级活动中偏向配合参与 | social_style |
| `ss_mixed` | 组织与参与较均衡 | social_style |
| `er_alone` | 情绪波动时偏向独处调节 | emotion_regulation |
| `er_talk` | 情绪波动时偏向找人倾诉 | emotion_regulation |
| `er_mixed` | 情绪调节方式较灵活 | emotion_regulation |
| `cc_persist` | 面对难题倾向坚持解决 | challenge_coping |
| `cc_skip_then_back` | 面对难题倾向先跳过再回看 | challenge_coping |
| `cc_ask_help` | 遇到难题倾向主动求助 | challenge_coping |
| `cc_mixed` | 面对难题策略较灵活 | challenge_coping |

### 4.3 禁止词列表（FORBIDDEN_WORDS）

标签文案一旦包含任一禁止词即丢弃（fail-closed 双保险）：

```python
FORBIDDEN_WORDS = [
    "粗心", "懒惰", "态度差", "性格缺陷", "内向", "外向", "多动",
    "自闭", "智力低下", "笨", "迟钝", "自卑", "自大", "叛逆", "爱捣乱",
    "自私", "孤僻", "不合群", "心理", "性格", "人格", "品行",
    # 叙阅扩展禁止词（对齐教育场景）
    "没救了", "差生", "坏学生", "问题学生", "不正常", "有病",
    "天生", "智商", "情商", "缺陷", "障碍"
]
```

### 4.4 标签生成规则（计分服务伪代码）

```python
def score_answers(questions: list[dict], answers: dict[str, str]) -> dict:
    """
    answers: {question_id: option_key}
    返回: {dimension_points, dimension_percents, labels, total_answered}
    """
    dim_points = defaultdict(int)
    selected_labels = []

    for q in questions:
        qid = q["id"]
        if qid not in answers:
            continue
        dim = q["dim"]
        opt_key = answers[qid]
        selected = next((o for o in q["options"] if o["key"] == opt_key), None)
        if not selected:
            continue
        dim_points[dim] += 1
        label = LABEL_MAP.get(selected.get("dim"))
        if label:
            selected_labels.append(label)

    total = sum(dim_points.values())
    percents = {d: round(pts / total * 100, 2) for d, pts in dim_points.items()} if total else {}

    # 过白名单闸门
    labels = filter_labels(selected_labels)

    return {
        "dimension_points": dict(dim_points),
        "dimension_percents": percents,
        "total_answered": total,
        "labels": labels,
    }


def filter_labels(labels: list[str]) -> list[str]:
    """fail-closed: 不在白名单丢弃，含禁止词丢弃，去重"""
    out = []
    for label in labels:
        if label not in ALLOWED_LABELS_SET:
            continue
        if any(w in label for w in FORBIDDEN_WORDS):
            continue
        if label not in out:
            out.append(label)
    return out
```

### 4.5 标签冲突裁决规则

当同一维度出现多个标签时（如学生在 `learning_style` 中同时命中 `ls_watch_example` 和 `ls_try_self`）：

| 规则 | 说明 |
|------|------|
| 并列保留 | 同维度允许多个标签并存（不做强制排他），完整呈现学生行为多样性 |
| 次数阈值 | v1 不作阈值过滤（选了1次就出标签），v2 可加 `min_count≥2` 过滤 |
| 百分位展示 | `dimension_percents` 按维度归一化展示各维占比，标签仅作补充说明不排名 |
| 兜底 | 若某生所有题均选择 `mixed` 类选项，标签全部为均衡描述，不计为"数据无效" |

---

## 5. 施测/计分流程

### 5.1 端到端流程

```
┌─────────────┐    ┌───────────────┐    ┌──────────────┐    ┌─────────────┐
│ 1.创建题组   │ → │ 2.创建施测会话  │ → │ 3.学生作答    │ → │ 4.自动计分   │
│ (运营维护)   │    │ (教师/学生)    │    │ (提交answers) │    │ (score_answers)│
└─────────────┘    └───────────────┘    └──────────────┘    └──────┬──────┘
                                                                     │
┌─────────────┐    ┌───────────────┐    ┌──────────────┐            │
│ 7.AI评语    │ ← │ 6.报告引用     │ ← │ 5.锚点写入    │ ←──────────┘
│ (可选引用)  │    │ (画像补充维)  │    │ (tag_schema)  │
└─────────────┘    └───────────────┘    └──────────────┘
```

### 5.2 会话状态流转

```
                    ┌──────────┐
                    │  pending │ ← 教师/学生创建会话
                    └────┬─────┘
                         │ 学生开始作答 → taken_at
                    ┌────▼──────┐
                    │in_progress│
                    └────┬──────┘
                         │ 提交答案 → submitted_at
                    ┌────▼──────┐
                    │ submitted │ ← 答案已提交，锚点已写入
                    └────┬──────┘
                         │ （可选）教师复核 → 人工评分/备注
                    ┌────▼──────┐
                    │  graded   │ ← v1 等同于 submitted，预留人工复核
                    └───────────┘

    pending/in_progress ──→ canceled（教师取消 / 学生放弃）
    已 submitted/graded 不允许取消
```

### 5.3 计分算法

**v1 简化规则（等权累加 + 归一化）**：

```
1. 遍历 questions 数组，逐个匹配 answers 中对应题号的选项
2. 按题目 dim（顶层维度）累加作答次数 → dimension_points
3. 归一化到百分比：各维 points / total_answered × 100 → dimension_percents
4. 逐个选项取 option.dim（子维度键）→ LABEL_MAP 白名单文案 → 过闸门筛选
5. 输出：labels（去重白名单标签） + dimension_percents（归一化占比）
```

**v2 预留扩展**：
- `option.score` 加权计分（当前所有选项等权 score=1）
- `reverse_scored` 反向计分（当题干 `reverse_scored=true` 且选项 dim 带 `_r` 后缀时取反）
- 信效度一致性校验（同一维度下选项 dim 一致性检查，如全选 mixed 则标注"区分度偏低"）

---

## 6. 监护人同意流程

### 6.1 同意状态机

```
                    ┌──────────────┐
                    │ not_required │ ← 初始状态：题组 consent_required=false 或首测未确认
                    └──────┬───────┘
                           │ 监护人确认 / 教师代确认 (restore 端点)
                    ┌──────▼───────┐
                    │   granted    │ ← version=1, granted_at=now
                    └──────┬───────┘
                           │ 监护人撤回 (withdraw 端点)
                    ┌──────▼───────┐
                    │  withdrawn   │ ← withdrawn_at=now，结果冻结只读
                    └──────┬───────┘
                           │ 重新确认 (restore 端点)
                    ┌──────▼───────┐
                    │   granted    │ ← version=2, granted_at=now
                    └──────────────┘
```

### 6.2 关键约束

| 约束 | 说明 |
|------|------|
| 撤回不删数据 | `withdraw` 仅置 `status='withdrawn'`，数据完整保留（审计/数据主体权利） |
| 撤回后冻结 | 撤回后的结果在家长端/学生端展示为"已冻结"，标签不出现在活跃画像中 |
| 恢复带版本 | 每次 `restore` 使 version+1，可追溯同意/撤回历史次数 |
| 版本不可跳 | `restore` 仅当 status='withdrawn' 时可调用，防止重复确认 |
| 首测默认 | `consent_required=true` 的题组，首测写入时 `status='not_required'`（至少不默认 granted） |
| 权限 | 撤回/恢复权限：super_admin、school_admin（本校）、该生被指派的 mentor 教师 |

### 6.3 监护人可见性规则

| 监护人绑定状态 | consent 状态 | 可见锚点 |
|-------------|-------------|---------|
| 已绑定（parent_student active） | granted | 可见 |
| 已绑定 | not_required | 不可见 |
| 已绑定 | withdrawn | 不可见 |
| 未绑定 | 任意 | 不可见（仅看到自己绑定孩子的数据） |

---

## 7. API 契约

> 基础路径：`/api/v1/assessment` | 鉴权：JWT Bearer Token
>
> 角色枚举：`super_admin` / `org_admin` / `school_admin` / `teacher` / `student` / `parent`（叙阅当前无 `parent` 角色，需新增）
>
> ⚠️ 叙阅当前鉴权模型：`get_current_user_id` 仅解析 JWT 返回 user_id，无角色信息。测评模块需要扩展鉴权中间件以支持角色校验。本节 API 契约标记了"鉴权角色"用于指导实现，具体中间件升级不在本契约范围。

### 7.1 题组定义 API

#### GET /api/v1/assessment/definitions

**用途**：列出 active 状态的题组定义（教师选题施测、学生读题面）
**鉴权**：登录即可（全角色）

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `domain` | string | 否 | 按 domain 过滤，如 `self_built_survey` |

**成功响应 (200)**：

```json
{
  "data": {
    "rows": [
      {
        "id": "uuid",
        "name": "班级自我认识轻量问卷（自研）",
        "domain": "self_built_survey",
        "grade_range": "all",
        "version": 1,
        "status": "active",
        "consent_required": true,
        "description": "本问卷帮助你了解自己的学习和交往习惯...",
        "question_count": 21,
        "questions": [
          {
            "id": "ls_q1",
            "dim": "learning_style",
            "text": "学习新内容时，你更习惯哪种方式？",
            "reverse_scored": false,
            "options": [
              {"key": "a", "text": "先看老师演示或例题", "dim": "ls_watch_example"},
              {"key": "b", "text": "自己先试着做一做", "dim": "ls_try_self"},
              {"key": "c", "text": "边做边翻书查资料", "dim": "ls_mixed"}
            ]
          }
        ],
        "created_at": "2026-08-11T08:30:00Z"
      }
    ],
    "total": 1
  },
  "message": "success"
}
```

> **注意**：列表接口返回的 `questions` 包含完整题面和选项，前端可直接渲染。若题组过大（>50题），可增加 `?brief=true` 参数仅返回 `question_count` 不含 `questions`。

#### POST /api/v1/assessment/definitions

**用途**：创建/更新自研题组定义
**鉴权**：`super_admin` / `org_admin`

**请求体**：

```json
{
  "name": "string",              // 必填，题组名称，1-128字符
  "domain": "string",            // 必填，personality/interest/learning_style/self_built_survey
  "grade_range": "all",          // 选填，primary/junior/senior/all，默认 all
  "version": 1,                  // 选填，版本号，默认1
  "status": "active",            // 选填，draft/active/retired，默认 draft
  "consent_required": true,      // 选填，是否需要监护人同意，默认 true
  "description": "string",       // 选填，题组说明/指导语
  "questions": [...]             // 必填，题面数组（格式见 §2.1 questions JSON 结构）
}
```

**成功响应 (200)**：

```json
{
  "data": {
    "id": "uuid",
    "name": "string",
    "domain": "string",
    "grade_range": "all",
    "version": 1,
    "status": "active",
    "consent_required": true,
    "question_count": 21,
    "created_at": "2026-08-11T08:30:00Z"
  },
  "message": "题组定义已创建"
}
```

**错误响应**：

| HTTP 状态码 | error 字段 | 触发条件 |
|------------|-----------|---------|
| 400 | `validation_error` | questions 为空或格式不合规 |
| 400 | `invalid_domain` | domain 不在允许值内 |
| 401 | `unauthorized` | 未登录 |
| 403 | `forbidden` | 非 super_admin/org_admin |

### 7.2 施测会话 API

#### POST /api/v1/assessment/sessions

**用途**：创建施测会话（class_batch 批量 / self 自主）
**鉴权**：class_batch 需 teacher/school_admin/org_admin/super_admin；self 需 student

**请求体**：

```json
{
  "definition_id": "string",     // 必填，题组定义ID
  "test_mode": "class_batch",    // 必填，class_batch/self
  "student_ids": ["uuid", ...],  // class_batch模式必填，学生ID列表（teacher限本班学生）
  "student_id": "string",        // self模式必填，学生本人student记录ID
  "batch_id": "string"           // 选填，集中施测批次标识（同批次会话可批量查询）
}
```

**成功响应 (200)**：

```json
{
  "data": {
    "rows": [
      {
        "id": "uuid",
        "student_id": "uuid",
        "definition_id": "uuid",
        "test_mode": "class_batch",
        "batch_id": null,
        "status": "pending",
        "proctored_by": "uuid",
        "created_by": "uuid",
        "taken_at": null,
        "submitted_at": null,
        "created_at": "2026-08-11T08:30:00Z"
      }
    ],
    "total": 1
  },
  "message": "已创建 1 个施测会话"
}
```

**错误响应**：

| HTTP 状态码 | error 字段 | 触发条件 |
|------------|-----------|---------|
| 400 | `validation_error` | class_batch缺少student_ids 或 self缺少student_id |
| 400 | `definition_not_active` | 题组定义非 active 状态 |
| 403 | `forbidden` | teacher为其他班学生建会话 / student为别人建self |
| 403 | `not_own_class` | class_batch中学生的班级不在教师任教范围内 |
| 404 | `definition_not_found` | 题组定义不存在 |
| 404 | `student_not_found` | 学生不存在 |

#### GET /api/v1/assessment/sessions

**用途**：施测会话列表
**鉴权**：登录即可（按角色过滤：student 只看到自己，teacher 看到本班/自己创建的）

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `student_id` | string | 否 | 按学生过滤 |
| `status` | string | 否 | 按状态过滤：pending/in_progress/submitted/graded |

**成功响应 (200)**：

```json
{
  "data": {
    "rows": [
      {
        "id": "uuid",
        "student_id": "uuid",
        "student_name": "张三",
        "definition_id": "uuid",
        "definition_name": "班级自我认识轻量问卷",
        "test_mode": "class_batch",
        "status": "submitted",
        "taken_at": "2026-08-11T08:00:00Z",
        "submitted_at": "2026-08-11T08:15:00Z",
        "created_at": "2026-08-11T07:30:00Z"
      }
    ],
    "total": 1
  },
  "message": "success"
}
```

#### GET /api/v1/assessment/sessions/{session_id}

**用途**：施测会话详情
**鉴权**：登录即可（权限应用层收紧：本人/创建者/mentor/管理员）

**成功响应 (200)**：

```json
{
  "data": {
    "id": "uuid",
    "student_id": "uuid",
    "student_name": "张三",
    "definition_id": "uuid",
    "definition_name": "班级自我认识轻量问卷",
    "questions": [...],
    "test_mode": "class_batch",
    "status": "in_progress",
    "proctored_by": "uuid",
    "created_by": "uuid",
    "taken_at": "2026-08-11T08:00:00Z",
    "submitted_at": null,
    "created_at": "2026-08-11T07:30:00Z"
  },
  "message": "success"
}
```

> **注意**：会话详情返回 `questions` 供前端渲染答题界面。若会话状态为 `pending`，前端可基于此渲染题面；若为 `submitted`，则需另行调用结果接口查看答案。

#### POST /api/v1/assessment/sessions/{session_id}/cancel

**用途**：取消施测会话（仅 pending/in_progress 状态可取消）
**鉴权**：会话创建者 / super_admin / org_admin

**请求体**：空

**成功响应 (200)**：

```json
{
  "data": {
    "id": "uuid",
    "status": "canceled",
    "updated_at": "2026-08-11T08:30:00Z"
  },
  "message": "会话已取消"
}
```

**错误响应**：

| HTTP 状态码 | error 字段 | 触发条件 |
|------------|-----------|---------|
| 400 | `invalid_status` | 会话已 submitted/graded，不可取消 |
| 404 | `session_not_found` | 会话不存在 |

### 7.3 作答与计分 API

#### POST /api/v1/assessment/sessions/{session_id}/answers

**用途**：提交答案 → 自动计分 → 生成白名单标签 → 写入锚点结果 → 会话置 submitted
**鉴权**：student（本人）/ teacher（本班/mentor/施测人）/ school_admin（本校）/ 管理员

> ⚠️ 这是整个测评模块的**核心事务端点**，包含：答案校验 → 计分 → 白名单闸门过滤 → 写 assessment_result → 会话状态更新。至少需要应用层数据库事务包裹。

**请求体**：

```json
{
  "answers": [
    {"question_id": "ls_q1", "option_key": "b"},
    {"question_id": "ls_q2", "option_key": "c"},
    {"question_id": "int_q1", "option_key": "a"}
  ]
}
```

**成功响应 (200)**：

```json
{
  "data": {
    "result_id": "uuid",
    "session_id": "uuid",
    "labels": ["偏好先动手尝试再对答案", "偏好动手实践", "对动手创作类活动兴趣高"],
    "dimension_percents": {
      "learning_style": 25.0,
      "interest": 20.0,
      "social_style": 20.0,
      "emotion_regulation": 20.0,
      "challenge_coping": 15.0
    },
    "total_answered": 20,
    "consent_status": "not_required"
  },
  "message": "答案已提交，锚点结果已写入"
}
```

**错误响应**：

| HTTP 状态码 | error 字段 | 触发条件 |
|------------|-----------|---------|
| 400 | `validation_error` | answers 为空或格式错误 |
| 400 | `no_match` | 答案未匹配到任何题目（question_id全部无效） |
| 400 | `already_submitted` | 会话已提交，不可重复作答 |
| 403 | `forbidden` | 无权为该学生提交 |
| 404 | `session_not_found` | 会话不存在 |
| 404 | `definition_not_found` | 关联的题组定义不存在 |
| 500 | `scoring_error` | 计分过程异常 |

### 7.4 锚点结果 API

#### GET /api/v1/assessment/students/{student_id}/results

**用途**：查看学生全部锚点结果
**鉴权**：student（本人） / teacher（本班/mentor） / school_admin（本校） / parent（已绑定且 consent=granted）

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `domain` | string | 否 | 按 domain 过滤 |
| `include_withdrawn` | bool | 否 | 是否包含已撤回结果，默认 false |

**成功响应 (200)**：

```json
{
  "data": {
    "rows": [
      {
        "id": "uuid",
        "student_id": "uuid",
        "definition_id": "uuid",
        "definition_name": "班级自我认识轻量问卷",
        "domain": "self_built_survey",
        "purpose": "anchor",
        "tag_schema": {
          "labels": ["偏好先动手尝试再对答案", "对动手创作类活动兴趣高"],
          "dimension_percents": {
            "learning_style": 25.0,
            "interest": 20.0,
            "social_style": 20.0,
            "emotion_regulation": 20.0,
            "challenge_coping": 15.0
          },
          "generated_at": "2026-08-11T08:30:00Z"
        },
        "guardian_consent": {
          "status": "granted",
          "version": 1,
          "granted_at": "2026-08-11T09:00:00Z",
          "withdrawn_at": null
        },
        "session_id": "uuid",
        "created_by": "uuid",
        "created_at": "2026-08-11T08:30:00Z"
      }
    ],
    "total": 1
  },
  "message": "success"
}
```

> **注意**：`raw_score` 字段默认不返回（含完整作答明细，体量较大）。需 `?include_raw=true` 参数显式请求。

### 7.5 监护人同意 API

#### POST /api/v1/assessment/students/{student_id}/results/{result_id}/withdraw

**用途**：撤回监护人同意，冻结结果展示
**鉴权**：super_admin / school_admin（本校）/ 该生 mentor 教师

**请求体**：空

**成功响应 (200)**：

```json
{
  "data": {
    "id": "uuid",
    "guardian_consent": {
      "status": "withdrawn",
      "version": 1,
      "granted_at": "2026-08-11T09:00:00Z",
      "withdrawn_at": "2026-08-11T10:00:00Z"
    },
    "updated_at": "2026-08-11T10:00:00Z"
  },
  "message": "已撤回监护人同意，结果冻结"
}
```

**错误响应**：

| HTTP 状态码 | error 字段 | 触发条件 |
|------------|-----------|---------|
| 400 | `already_withdrawn` | 结果已经是 withdrawn 状态 |
| 400 | `not_required` | 结果 consent 状态是 not_required（无同意可撤回） |
| 403 | `forbidden` | 无权操作该测评结果 |
| 404 | `result_not_found` | 结果不存在或不属于该学生 |

#### POST /api/v1/assessment/students/{student_id}/results/{result_id}/restore

**用途**：撤销撤回，恢复监护人同意
**鉴权**：super_admin / school_admin（本校）/ 该生 mentor 教师

**请求体**：空

**成功响应 (200)**：

```json
{
  "data": {
    "id": "uuid",
    "guardian_consent": {
      "status": "granted",
      "version": 2,
      "granted_at": "2026-08-11T11:00:00Z",
      "withdrawn_at": null
    },
    "updated_at": "2026-08-11T11:00:00Z"
  },
  "message": "已撤销撤回，监护人同意恢复"
}
```

**错误响应**：

| HTTP 状态码 | error 字段 | 触发条件 |
|------------|-----------|---------|
| 400 | `not_withdrawn` | 结果当前状态非 withdrawn（只有已撤回的可恢复） |
| 403 | `forbidden` | 无权操作该测评结果 |
| 404 | `result_not_found` | 结果不存在或不属于该学生 |

### 7.6 家长-学生绑定 API（新增）

> ⚠️ 叙阅当前无 `parent` 角色和 `parent_students` 表，需新增。此 API 属于测评模块的前置依赖。

#### POST /api/v1/parent-students

**用途**：绑定家长与学生的关系
**鉴权**：teacher / school_admin / org_admin / super_admin

**请求体**：

```json
{
  "parent_id": "uuid",          // 必填，家长 user ID（role='parent'）
  "student_id": "uuid",         // 必填，学生 ID
  "relation": "guardian"        // 选填，guardian/father/mother/other，默认 guardian
}
```

**成功响应 (200)**：

```json
{
  "data": {
    "id": "uuid",
    "parent_id": "uuid",
    "student_id": "uuid",
    "relation": "guardian",
    "status": "active",
    "created_at": "2026-08-11T08:30:00Z"
  },
  "message": "家长绑定成功"
}
```

#### GET /api/v1/parent-students

**用途**：查询家长绑定列表
**鉴权**：parent（本人）/ teacher（本班）/ school_admin（本校）

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `parent_id` | string | 否 | 按家长过滤 |
| `student_id` | string | 否 | 按学生过滤 |

**成功响应 (200)**：

```json
{
  "data": {
    "rows": [
      {
        "id": "uuid",
        "parent_id": "uuid",
        "parent_name": "监护人甲",
        "student_id": "uuid",
        "student_name": "张三",
        "relation": "guardian",
        "status": "active",
        "created_at": "2026-08-11T08:30:00Z"
      }
    ],
    "total": 1
  },
  "message": "success"
}
```

---

## 8. 与画像的关系

### 8.1 标签如何进 student_portfolio

**核心原则**：测评标签是"参考维"，不进 `student_portfolio.dimensions`（闭合 number 结构），而是作为独立的 `assessment_profile` 出现在报告数据中。

```
student_portfolio
├── dimensions（闭合 number 五育值）        ← 测评标签不写这里
├── detail（FLEXIBLE JSON，证据明细）       ← 测评标签不写这里
├── auto_detail（FLEXIBLE JSON，自动证据）  ← 测评标签不写这里
└── [新增] assessment_profile ← 测评标签写这里（v2 扩展，v1 走独立查询）
```

**v1 实现方案**（不修改 `student_portfolio` 表结构）：

```
学期报告 GET /api/v1/students/{id}/portfolio/report 返回：
{
  ...
  "assessment_profile": {
    "has_data": true,
    "result_count": 2,
    "labels": ["偏好先看例题再动笔", "对动手创作类活动兴趣高"],
    "by_dimension": {
      "learning_style": ["偏好先看例题再动笔", "适合听觉输入"],
      "interest": ["对动手创作类活动兴趣高"]
    },
    "dimension_percents": { ... },
    "generated_at": "2026-08-11T08:30:00Z",
    "domains": ["self_built_survey"]
  },
  ...
}
```

**`assessment_profile` 聚合规则**：

| 规则 | 说明 |
|------|------|
| 取最新一份 | 按该学期时间范围取最新 `created_at` 的锚点结果 |
| 过滤已撤回 | `guardian_consent.status = 'withdrawn'` 的锚点不纳入聚合 |
| 多份合并 | 若一学期内有多份不同 domain 的测评，合并 labels 数组去重 |
| 空值兜底 | 该学期无有效锚点时 `has_data=false, labels=[]` |

### 8.2 如何被 AI 评语引用

AI 评语生成时，`assessment_profile` 作为 prompt 上下文输入（不修改五育综合分）：

```
系统 Prompt 片段：
"以下是该生的行为观察标签（参考维，不作价值判断）：
 - 学习方式偏好：偏好先看例题再动笔、适合讨论互动式学习
 - 兴趣领域：对动手创作类活动兴趣高
 - 交往风格：班级活动中偏向主动组织

请基于以上信息，在评语中自然地融入对学习习惯的观察建议，不要贴人格标签。"
```

**约束**：
- AI 评语仅做"基于观察的建议"，不做"基于类型/性格的预设"
- 评语生成后过词表闸门（`FORBIDDEN_WORDS`），含禁止词的句子清洗或兜底
- 教师确认后方可写入报告快照（`assessment_comment` / `report_snapshot.payload`）

### 8.3 报告前端展示（对齐参考实现 StudentReport.tsx）

在学期报告页面中，测评画像作为独立卡片展示：

```
┌─────────────────────────────────────┐
│ 行为画像标签                         │
│                                     │
│ 学习方式偏好                         │
│ [偏好先看例题再动笔] [适合听觉输入]    │
│                                     │
│ 兴趣领域                             │
│ [对动手创作类活动兴趣高]              │
│                                     │
│ 交往风格                             │
│ [班级活动中偏向主动组织]              │
│                                     │
│ 情绪调节方式                         │
│ [情绪波动时偏向找人倾诉]              │
│                                     │
│ 挑战应对倾向                         │
│ [面对难题倾向坚持解决]                │
└─────────────────────────────────────┘
```

标签为普通展示（不使用颜色编码，避免"好/坏"视觉暗示），标注为"行为观察参考，不作价值判断"。

---

## 9. 验收标准

### 9.1 表结构验收 (C1)

| # | 验收项 | 判定标准 | 验证方法 |
|---|--------|---------|---------|
| C1.1 | assessment_definitions 表存在 | DDL 执行成功，种子题组可插入 | `CREATE TABLE` 不报错 |
| C1.2 | assessment_sessions 表存在 | 含状态字段 + 外键约束 | `DESC assessment_sessions` 确认字段 |
| C1.3 | assessment_results 表存在 | purpose CHECK 约束生效 | 尝试插入 purpose='score' 被数据库拒绝 |
| C1.4 | JSON 字段可写入 | questions/tag_schema/raw_score JSON 正常读写 | 写入 21 题题面再读出，结构一致 |
| C1.5 | 外键级联生效 | 删除学生 → 关联 sessions/results 级联删除 | 删除学生后查询 sessions 返回空 |

### 9.2 题组内容验收 (C2)

| # | 验收项 | 判定标准 | 验证方法 |
|---|--------|---------|---------|
| C2.1 | 种子题组写入成功 | 21 题，5 维度，status='active' | `POST /api/v1/assessment/definitions` 或数据库直接插入 |
| C2.2 | 题组 API 可读 | `GET /definitions` 返回完整题面 | 验证返回的 questions 数组长度 ≥20 |
| C2.3 | 题面字段完整 | 每题含 id/dim/text/options，每选项含 key/text/dim | JSON Schema 校验 |
| C2.4 | consent_required=true | 种子题组的 consent_required 为 true | 读取确认 |
| C2.5 | 措辞合规 | 题面不含"类型""人格""性格"等词 | 全文检索 |

### 9.3 施测与计分验收 (C3)

| # | 验收项 | 判定标准 | 验证方法 |
|---|--------|---------|---------|
| C3.1 | teacher 建 class_batch 会话 | 200 + sessions.rows 非空 | API 测试 |
| C3.2 | student 建 self 会话 | 200 + sessions.rows 非空 | API 测试 |
| C3.3 | teacher 不能建 self 会话 | 403 forbidden | 越权测试 |
| C3.4 | student 不能为别人建 self | 403 forbidden | 越权测试 |
| C3.5 | 提交答案→锚点写入 | 200 + result_id 非空 + purpose='anchor' | API 测试 |
| C3.6 | 已提交不可重复提交 | 400 already_submitted | 重复提交测试 |
| C3.7 | 会话置 submitted | 提交后 GET 会话 status='submitted' | API 测试 |
| C3.8 | 锚点 consent 不得默认 granted | 首测提交后 consent='not_required' | 验证 guardian_consent.status |

### 9.4 白名单标签验收 (C4)

| # | 验收项 | 判定标准 | 验证方法 |
|---|--------|---------|---------|
| C4.1 | 标签非空（正常作答） | labels 数组非空 | 基于种子题面选 a 选项提交 |
| C4.2 | 标签全部命中白名单 | 所有 label ∈ ALLOWED_LABELS | 逐条 `is_allowed_label()` 校验 |
| C4.3 | 标签不进 student_portfolio | student_portfolio.dimensions 值全为 number | 类型检查 |
| C4.4 | 白名单词保留 | filter_labels(["偏好先看例题再动笔"]) 保留 | 单元测试 |
| C4.5 | 人格归因词丢弃 | filter_labels(["该生懒惰", "态度差"]) 返回空 | 单元测试 |
| C4.6 | 白名单不含禁止词 | 全量 ALLOWED_LABELS 逐词检查 | 单元测试 |

### 9.5 监护人同意验收 (C5)

| # | 验收项 | 判定标准 | 验证方法 |
|---|--------|---------|---------|
| C5.1 | 家长绑定成功 | POST /parent-students 返回 200 | API 测试 |
| C5.2 | 未 granted 时监护人不可见锚点 | parent GET /results 返回空列表 | consent 闸门测试 |
| C5.3 | withdraw → status='withdrawn' | 200 + guardian_consent.status='withdrawn' | API 测试 |
| C5.4 | restore → status='granted' + version+1 | 200 + version 递增 | API 测试 |
| C5.5 | not_required 不可撤回 | 400 拒绝 | 状态机测试 |
| C5.6 | granted 后监护人可见锚点 | parent GET /results 返回数据 | consent 闸门测试 |
| C5.7 | 未绑定家长不可见 | 非绑定 parent GET /results 返回空 | 权限测试 |
| C5.8 | 不可对 withdrawn 再次撤回 | 400 already_withdrawn | 幂等性测试 |

### 9.6 综合分不变验收 (C6)（学术安全线核心）

| # | 验收项 | 判定标准 | 验证方法 |
|---|--------|---------|---------|
| C6.1 | 写锚点前后智育分不变 | before==after | 写锚点前 GET /portfolio 记基线，写后再次 GET 对比 |
| C6.2 | 写锚点前后整幅 dimensions 不变 | before==after（全键值对一致） | 同上，对比全量 dimensions |
| C6.3 | 撤回/恢复不影响综合分 | withdraw/restore 前后 dimensions 不变 | GET /portfolio 前后对比 |

### 9.7 报告集成验收 (C7)

| # | 验收项 | 判定标准 | 验证方法 |
|---|--------|---------|---------|
| C7.1 | 报告返回 assessment_profile | report 响应含 assessment_profile 字段 | GET /portfolio/report |
| C7.2 | 撤回后不聚合 | withdrawn 成果不进入 assessment_profile.labels | 撤回后再查报告 |
| C7.3 | AI 评语引用测评标签 | generate 接口 prompt 含 assessment_profile 上下文 | 检查服务端日志/prompt 日志 |
| C7.4 | 前端展示标签 | 学期报告页显示行为画像卡片 | 前端截图验证 |

### 9.8 性能与安全验收 (C8)

| # | 验收项 | 判定标准 | 验证方法 |
|---|--------|---------|---------|
| C8.1 | 单次计分 <200ms | 21 题计分时间 <200ms | 性能基准测试 |
| C8.2 | 批量建会话成功率 ≥99% | 一个班 50 人批量建会话，失败数 ≤1 | 压力测试 |
| C8.3 | 不返回 password_hash | 所有 API 响应不含密码相关字段 | 响应审计 |
| C8.4 | SQL 注入防护 | 所有数据库操作走参数化查询/SQLAlchemy ORM | 代码审查 |

---

## 附录 A：种子数据脚本（MySQL版）

> 对应参考实现 `scripts/seed_assessment_definition.py`，叙阅版本直接写入 MySQL。

```sql
-- 种子题组定义（幂等：先查再插）
INSERT INTO assessment_definitions (id, name, domain, grade_range, version, status, consent_required, description, questions)
SELECT
    UUID(),
    '班级自我认识轻量问卷（自研）',
    'self_built_survey',
    'all',
    1,
    'active',
    1,
    '本问卷帮助你了解自己的学习和交往习惯，没有对错，请按真实情况选择。',
    '[${完整21题JSON，见§3.3}]'
WHERE NOT EXISTS (
    SELECT 1 FROM assessment_definitions
    WHERE domain = 'self_built_survey' AND status = 'active' AND version = 1
);
```

> 实际插入时 `questions` 值使用 §3.3 的完整 JSON 数组。建议后端实现 `seed_assessment_definition()` 函数，在 `init_db()` 或 `AUTO_DDL=true` 时调用。

## 附录 B：角色与权限矩阵

| 操作 | super_admin | org_admin | school_admin | teacher | student | parent |
|------|:--:|:--:|:--:|:--:|:--:|:--:|
| 创建/编辑题组定义 | Y | Y | N | N | N | N |
| 查看题组列表 | Y | Y | Y | Y | Y | N |
| 创建class_batch会话 | Y | Y | Y | Y(本班) | N | N |
| 创建self会话 | N | N | N | N | Y(本人) | N |
| 提交答案 | Y | Y | Y(本校) | Y(本班/mentor) | Y(本人) | N |
| 查看锚点结果 | Y | Y | Y(本校) | Y(本班/mentor) | Y(本人) | Y(绑定+granted) |
| 撤回监护人同意 | Y | N | Y(本校) | Y(mentor) | N | N |
| 恢复监护人同意 | Y | N | Y(本校) | Y(mentor) | N | N |
| 绑定家长-学生 | N | N | Y(本校) | Y(本班) | N | N |
| 查看学期报告 | Y | Y(本org) | Y(本校) | Y(本班/mentor) | Y(本人) | Y(绑定) |

## 附录 C：环境变量与配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `ASSESSMENT_SEED_ENABLED` | 是否在启动时自动插入种子题组 | `true` |
| `ASSESSMENT_AUTO_CREATE_TABLES` | 是否自动创建测评表（受AUTO_DDL控制） | `false` |
| `ASSESSMENT_MAX_QUESTIONS_PER_SET` | 单个题组最大题目数 | `100` |

---

## 变更记录

（暂无 — v1.0 初始版本）
