# 数据层基线规范 + 智能体平台预留架构

> 版本: 1.0 | 日期: 2026-08-11 | 适用范围: 叙阅 MySQL 数据库全表
> 状态: **契约级别** — 以下所有规则为硬性约束，新增表/改表必须遵守，不得例外。
>
> **⚠️ 覆盖声明（2026-08-11 对账后）**：第 5 节「种春风新增表 DDL」已被 `99-reconciliation.md` 裁决覆盖——
> §5.1-5.4（画像/成长流水/积分）以 99 §4.1 为准；§5.5-5.7（测评三表）以 B0 契约为准；§5.9 `student_badges` 删除；
> `student_point_accounts`/`student_point_transactions` 删除。本文件第 1-4 节（数据层约定/建表机制/智能体预留/命名规范）仍为有效权威。
> 第 5 节仅作为设计追溯保留，**建表以 99-reconciliation.md 为准**。

---

## 目录

1. [数据层硬性约定](#1-数据层硬性约定)
2. [建表/迁移机制](#2-建表迁移机制)
3. [智能体平台预留架构](#3-智能体平台预留架构)
4. [命名/目录规范](#4-命名目录规范)
5. [种春风新增表 DDL](#5-种春风新增表-ddl)
6. [现有 ai_chat 演进评估](#6-现有-ai_chat-演进评估)

---

## 1. 数据层硬性约定

以下规则由现有代码库反向提取 + 规范化补充而来，新增所有表（含种春风/智能体平台）必须遵守。

### 1.1 主键规范

| 规则 | 详情 |
|------|------|
| 类型 | `VARCHAR(36)` — 与现有全部表一致 |
| 生成方式 | `gen_uuid()` = `str(uuid.uuid4())`，定义在 `app/models/user.py`，所有 model 文件 `from app.models.user import gen_uuid` |
| 字段名 | 统一命名为 `id` |
| 建表 DDL | `id VARCHAR(36) NOT NULL PRIMARY KEY` |
| SQLAlchemy 声明 | `id = Column(String(36), primary_key=True, default=gen_uuid)` |
| **反模式禁止** | 不得使用自增整数、不得使用复合主键（唯一约束放 `__table_args__`） |

### 1.2 时间戳规范

| 规则 | 详情 |
|------|------|
| 字段名 | 每表必须含 `created_at` + `updated_at`（只读快照表可省略 `updated_at`） |
| 类型 | `DATETIME`（非 `TIMESTAMP`），存储 UTC 时间 |
| SQLAlchemy 声明 | `Column(DateTime(timezone=True), server_default=func.now())` |
| DDL | `created_at DATETIME DEFAULT CURRENT_TIMESTAMP` / `updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` |
| 软删除 | 删除操作用 `deleted_at DATETIME NULL DEFAULT NULL`（NULL 表示未删除），参考 `wrong_questions` 表 |

### 1.3 外键规范

所有外键**必须**引用以下三张锚表，不得越级引用：

| 外键字段 | 指向 | 说明 |
|----------|------|------|
| `user_id` | `users.id` | 数据归属教师/管理员，`ON DELETE CASCADE` |
| `class_id` | `classes.id` | 班级维度，`ON DELETE CASCADE` |
| `student_id` | `students.id` | 学生维度，`ON DELETE CASCADE`（批改结果可用 `SET NULL`） |

**约束**：
- 外键字段**必须**建索引（`index=True` / `KEY idx_...`），现有表已全部照此执行
- 外键联级策略参考现有惯例：`user_id`/`class_id` 一般 CASCADE，`student_id` 可选 SET NULL
- **不得**创建指向 `users`/`classes`/`students` 之外的"自由外键"（智能体审计表例外见第3节）

### 1.4 字符集/存储引擎

| 配置项 | 值 | 来源 |
|--------|---|------|
| 字符集 | `utf8mb4` | `database.py:19` |
| 排序规则 | `utf8mb4_unicode_ci` | `database.py:19` |
| 存储引擎 | `InnoDB` | `database.py:124` (`_ensure_grading_daily_stats_table` DDL) |

**DDL 声明模板**：`ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`

### 1.5 命名风格

| 层面 | 规则 | 示例 |
|------|------|------|
| 数据库表名 | **蛇形复数**（snake_case, plural） | `users`, `students`, `exam_scores`, `knowledge_points` |
| Python Model 类名 | **大驼名单数**（PascalCase, singular） | `User`, `Student`, `ExamScore`, `KnowledgePoint` |
| Model 文件名 | **蛇形单数**（snake_case, singular） | `user.py`, `student.py`, `exam_score.py` |
| 路由文件名 | **蛇形单数** 或 **蛇形描述** | `auth.py`, `lesson_plans.py`, `student_analysis.py` |
| 字段名 | **蛇形** | `student_id`, `created_at`, `display_name` |
| 索引名 | `idx_{table}_{fields}` | `idx_exam_scores_student_id` |
| 唯一约束名 | `uq_{table}_{fields}` 或 `uq_{descriptive}` | `uq_exam_student`, `uq_targeted_report_class_student_subject` |

**现有不一致之处（已知，新表不效仿）**：
- `student_analysis` 表名为单数（应为 `student_analyses`），但已是历史表，不改
- `student_score_history` 表名为单数（应为 `student_score_histories`），同上
- `student_wrong_questions` 表名为复数（正确），但 model 类 `StudentWrongQuestion` 把 "Questions" 去掉了
- `grading_daily_stats` 已是复数（正确）
- `class_review_sessions` 已是复数（正确）
- `targeted_improvement_reports` 已是复数（正确）

### 1.6 Model 文件独立新建

| 规则 | 详情 |
|------|------|
| 一个 model 类 = 一个 `.py` 文件 | 放在 `app/models/` 下，如 `app/models/student_portfolio.py` |
| 注册 | 新建后必须在 `app/models/__init__.py` 中 import + 加入 `__all__` |
| 注册到 `sync_database_schema()` | 在 `app/database.py` 的 `sync_database_schema` 函数内新增 `from app.models import {new_model}` 行 |
| Base 来源 | `from app.database import Base`，不自己创建 Base |

### 1.7 特殊字段类型约定

| 场景 | MySQL 类型 | SQLAlchemy 类型 | 说明 |
|------|-----------|----------------|------|
| JSON 大文本 | `LONGTEXT` | `LONGTEXT` (from `sqlalchemy.dialects.mysql`) | AI 生成的 JSON 分析结果，如 `ai_raw_json`、`diagnosis_json` |
| 普通 JSON | `JSON` | `JSON` (from `sqlalchemy.dialects.mysql`) | 结构化数据如 `prerequisite`、`questions` |
| 长文本 | `TEXT` | `Text` | 错题内容、教案正文等 |
| 布尔值 | `TINYINT(1)` | `Boolean` (default=0/False) | `is_weak`、`enabled` |
| 浮点分数 | `FLOAT` | `Float` | 考试成绩分数 |
| 小数字段 | `DECIMAL(10,2)` | — | 金额类（目前只在参考平台中出现，叙阅尚未用到） |

---

## 2. 建表/迁移机制

### 2.1 核心原则

**生产环境 `AUTO_DDL=false`（默认值，安全）**，所有建表/改表必须通过**手工 DDL 脚本**执行。DB 账号建议收敛为 DML-only（仅 SELECT/INSERT/UPDATE/DELETE），DDL 操作走人工审批。

### 2.2 操作路径

#### 路径 A：开发环境快速迭代（本地/测试）

```bash
# 1. 在 .env 中开启:
AUTO_DDL=true

# 2. 在 database.py 的 sync_database_schema() 中
#    确认新增 model 已被 import（第80-105行的 from app.models import 块）

# 3. 启动服务，init_db() 会自动执行:
#    - Base.metadata.create_all(bind=engine)  → 创建新表
#    - _ensure_* 函数 → 增量补列

# 4. 完成后建议关掉 AUTO_DDL，验证生产路径能走通:
AUTO_DDL=false
```

#### 路径 B：生产环境（必须走手工 DDL）

```bash
# 1. 编写 DDL 脚本（遵循下方模板）
# 2. 由 DBA/运维人工审核后执行
# 3. 执行后部署新代码（model 定义已存在但 create_all 不执行）
```

### 2.3 DDL 脚本模板

```sql
-- ============================================================
-- 迁移: {迁移描述，如：种春风-学生成长画像表}
-- 日期: YYYY-MM-DD
-- 执行前检查: SELECT DATABASE(); 确认连接的是目标库
-- 回滚: DROP TABLE IF EXISTS {table_name};
-- ============================================================

START TRANSACTION;

-- 表1: {table_name}
CREATE TABLE IF NOT EXISTS `{table_name}` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4 主键',
    -- 业务字段
    `user_id` VARCHAR(36) NOT NULL COMMENT '归属教师/管理员',
    `class_id` VARCHAR(36) NOT NULL COMMENT '归属班级',
    `student_id` VARCHAR(36) NULL COMMENT '关联学生',
    -- ... 其他业务字段 ...

    -- 审计字段（必须）
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间(UTC)',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间(UTC)',
    -- 软删除字段（按需）
    `deleted_at` DATETIME NULL DEFAULT NULL COMMENT '软删除时间，NULL为未删除',

    PRIMARY KEY (`id`),
    KEY `idx_{table}_user_id` (`user_id`),
    KEY `idx_{table}_class_id` (`class_id`),
    KEY `idx_{table}_student_id` (`student_id`),
    -- ... 其他索引 ...
    CONSTRAINT `fk_{table}_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_{table}_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_{table}_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='{表说明}';

COMMIT;

-- 验证
SHOW CREATE TABLE `{table_name}`;
SELECT COUNT(*) FROM `{table_name}`;
```

### 2.4 增量补列安全约定

现有 `_ensure_*` 函数模式（逐列 try/except ALTER TABLE ADD COLUMN）仅限开发/测试环境 `AUTO_DDL=true` 下运行，**生产环境禁用**。生产增量列同样走手工 DDL：

```sql
ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {type} {nullable} COMMENT '{说明}';
-- 如需索引:
-- CREATE INDEX idx_{table}_{col} ON `{table_name}` (`{column_name}`);
```

---

## 3. 智能体平台预留架构

> **核心设计原则**：种春风新增的所有数据（画像/成长记录/测评结果/积分）都要**结构化、有稳定 id、可被未来智能体作为工具读取**。智能体平台不是今天做，但数据库和接口的"接入面"今天就要定好。

### 3.1 AI 能力层抽象 — LLM 网关统一接口

**设计目标**：从当前"只调千问"演进到"模型无关、可配置、按租户隔离"。

#### 3.1.1 网关架构（参考 teacher-ai-platform `llm_gateway.py`）

```
┌──────────────────────────────────────────┐
│           FastAPI 路由层                  │
│  ai_chat / agent / grading / portfolio   │
└────────────┬─────────────────────────────┘
             │ 统一调用 LLMGateway.chat()
             ▼
┌──────────────────────────────────────────┐
│         LLMGateway（统一网关）            │
│  - chat(request: LLMRequest) → LLMResponse│
│  - stream_chat(request) → AsyncIterator   │
│  - resolve_api_key(org_id) → (key, src)  │
├──────────────────────────────────────────┤
│  Provider Registry（可插拔）              │
│  ├─ DashScopeProvider  (qwen 系列)       │
│  ├─ DeepSeekProvider   (deepseek-chat)   │
│  ├─ OpenAIProvider     (预留)            │
│  ├─ MockProvider       (测试兜底)        │
│  └─ CustomProvider     (客户私有模型)    │
├──────────────────────────────────────────┤
│  计量层（按 user_id + model 聚合）        │
│  - tokens_used / cost_cent / latency_ms  │
└──────────────────────────────────────────┘
```

#### 3.1.2 统一请求/响应结构

```python
# 请求结构
@dataclass
class LLMRequest:
    provider: str              # "dashscope" | "deepseek" | "openai"
    model: str                 # "qwen3.7-plus" | "deepseek-chat" ...
    messages: list[dict]       # OpenAI 兼容消息格式
    images: list[str]          # base64/URL 多模态
    max_tokens: int
    temperature: float
    user_id: str               # 计量归属
    tools: list[dict] | None   # Function calling 工具定义

# 响应结构
@dataclass
class LLMResponse:
    ok: bool
    content: str
    model: str
    tokens_used: int
    cost_cent: int
    error: str
```

#### 3.1.3 当前状态 → 目标状态

| 当前（叙阅） | 目标（智能体平台） |
|---------------|-------------------|
| 硬编码 DashScope | Provider Registry，配置驱动 |
| 仅千问 `qwen3.7-plus` | 多模型可配置切换 |
| API Key 全局一份 | 支持教师配置自己的 Key（含加密存储） |
| 无成本/用量统计 | LLMResponse 带 tokens_used/cost_cent |
| 无 MockProvider | 开发/测试可用 Mock 全链路跑通 |

#### 3.1.4 预留表：`agent_llm_configs`（DDL）

智能体平台未来允许教师/管理员配置自己的模型偏好和 API Key。该表作为预留，今天不建但接口约定已定：

```sql
CREATE TABLE IF NOT EXISTS `agent_llm_configs` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY,
    `user_id` VARCHAR(36) NOT NULL COMMENT '归属教师',
    `provider` VARCHAR(32) NOT NULL COMMENT 'dashscope|deepseek|openai|custom',
    `model` VARCHAR(64) NOT NULL COMMENT '模型名',
    `api_key_encrypted` TEXT NOT NULL COMMENT 'AES-256-GCM 加密的 API Key',
    `base_url` VARCHAR(512) NULL COMMENT '自定义 endpoint（OpenAI 兼容模式）',
    `is_default` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否默认',
    `max_tokens` INT NULL COMMENT '单次最大 token 数',
    `temperature` FLOAT NULL DEFAULT 0.7 COMMENT '默认温度',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `deleted_at` DATETIME NULL DEFAULT NULL,
    KEY `idx_alc_user_id` (`user_id`),
    CONSTRAINT `fk_alc_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='智能体LLM配置表（预留）';
```

### 3.2 工具注册表（Tool Registry）规范

**设计目标**：智能体的"技能"（查数据库、调 API、发通知等）通过统一的工具注册机制管理，教师可在前端自定义角色指令时选择启用哪些工具。

#### 3.2.1 工具注册接口标准

```python
# 每个工具必须实现的接口（Python Protocol）
class AgentTool(Protocol):
    name: str                    # 唯一标识，如 "query_students"
    description: str             # 给 LLM 看的 function description
    parameters: dict             # JSON Schema 格式的参数定义
    category: str                # "data" | "action" | "notification" | "external"
    requires_approval: bool      # 是否需要人工确认（如发通知）
    
    async def execute(self, args: dict, context: AgentContext) -> ToolResult:
        ...
```

#### 3.2.2 工具分类

| 分类 | 示例工具 | 说明 |
|------|---------|------|
| `data` | `query_students`, `query_exam_scores`, `query_portfolio` | 只读查询，不产生副作用 |
| `action` | `create_todo`, `send_notification`, `update_score` | 写操作，需要审计 |
| `notification` | `send_wechat_msg`, `send_sms` | 外部通知，需要人工确认 |
| `external` | `sync_sis_data`, `call_third_party_api` | 对接校务系统，需要审批 |

#### 3.2.3 预留表：`agent_tools` + `agent_tool_instances`（DDL）

```sql
-- 工具定义表（全局，由平台管理员维护）
CREATE TABLE IF NOT EXISTS `agent_tools` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY,
    `name` VARCHAR(64) NOT NULL COMMENT '工具唯一标识',
    `display_name` VARCHAR(128) NOT NULL COMMENT '中文名',
    `description` TEXT NOT NULL COMMENT '给 LLM 的功能描述',
    `parameters_schema` JSON NOT NULL COMMENT 'JSON Schema 参数定义',
    `category` VARCHAR(32) NOT NULL COMMENT 'data|action|notification|external',
    `requires_approval` TINYINT(1) NOT NULL DEFAULT 0,
    `is_builtin` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '系统内置 or 第三方接入',
    `handler_path` VARCHAR(255) NULL COMMENT 'app/services/agent_tools/xxx.py:handler_fn',
    `enabled` TINYINT(1) NOT NULL DEFAULT 1,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_agent_tools_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='智能体工具注册表（预留）';

-- 工具实例表（教师启用/配置具体工具）
CREATE TABLE IF NOT EXISTS `agent_tool_instances` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY,
    `user_id` VARCHAR(36) NOT NULL COMMENT '教师',
    `tool_id` VARCHAR(36) NOT NULL COMMENT '工具定义',
    `agent_role_id` VARCHAR(36) NULL COMMENT '所属智能体角色（未来 agent_roles 表）',
    `config` JSON NULL COMMENT '教师自定义配置（如：允许查询的班级范围）',
    `enabled` TINYINT(1) NOT NULL DEFAULT 1,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY `idx_ati_user_id` (`user_id`),
    KEY `idx_ati_tool_id` (`tool_id`),
    CONSTRAINT `fk_ati_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ati_tool` FOREIGN KEY (`tool_id`) REFERENCES `agent_tools` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='智能体工具实例表（预留）';
```

### 3.3 会话记忆存储模式

**设计目标**：智能体跨会话记住学生信息/上下文，避免每次对话都从零开始。

#### 3.3.1 三级记忆模型

```
┌────────────────────────────────────┐
│ L1 短期记忆（会话内上下文窗口）      │
│ = LLM messages 列表，不持久化       │
│ 上限: model context_window tokens   │
├────────────────────────────────────┤
│ L2 中期记忆（跨会话摘要缓存）        │
│ = agent_conversation_summaries 表   │
│ 每 N 轮对话生成一次摘要存储          │
├────────────────────────────────────┤
│ L3 长期记忆（结构化知识）            │
│ = 学生画像/考试记录/错题本已有数据   │
│ = 智能体通过 Tool 查询获取           │
└────────────────────────────────────┘
```

**核心决策**：L3 长期记忆**不另建向量库**，智能体通过 Tool 直接查 MySQL。叙阅是单机定制产品，数据量在十万级，MySQL 全文搜索 + 结构化查询完全够用。未来如果数据上到百万级且确实有语义搜索需求（"找类似错题"），再引入向量索引。

#### 3.3.2 预留表：`agent_conversations` + `agent_conversation_messages`（DDL）

```sql
-- 对话会话表
CREATE TABLE IF NOT EXISTS `agent_conversations` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY,
    `user_id` VARCHAR(36) NOT NULL COMMENT '对话所属教师',
    `agent_role_id` VARCHAR(36) NULL COMMENT '智能体角色（未来 agent_roles 表）',
    `title` VARCHAR(255) NULL COMMENT '对话标题（可由 LLM 自动生成）',
    `summary` TEXT NULL COMMENT '对话摘要（L2 记忆，定期更新）',
    `context_snapshot` JSON NULL COMMENT '对话上下文快照（当前关联的学生/班级/考试等）',
    `message_count` INT NOT NULL DEFAULT 0 COMMENT '消息数',
    `total_tokens` INT NOT NULL DEFAULT 0 COMMENT '累计 token 消耗',
    `total_cost_cent` INT NOT NULL DEFAULT 0 COMMENT '累计成本(分)',
    `status` VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT 'active|archived',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY `idx_aconv_user_id` (`user_id`),
    KEY `idx_aconv_status` (`status`),
    KEY `idx_aconv_created_at` (`created_at`),
    CONSTRAINT `fk_aconv_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='智能体对话会话表（预留）';

-- 对话消息表（一条消息 = 一行，支持 user/assistant/tool/system 角色）
CREATE TABLE IF NOT EXISTS `agent_conversation_messages` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY,
    `conversation_id` VARCHAR(36) NOT NULL COMMENT '所属对话',
    `role` VARCHAR(16) NOT NULL COMMENT 'user|assistant|tool|system',
    `content` LONGTEXT NOT NULL COMMENT '消息内容',
    `tool_name` VARCHAR(64) NULL COMMENT '如果是 tool 消息，记录工具名',
    `tool_call_id` VARCHAR(64) NULL COMMENT '如果是 tool 消息，关联 tool_call id',
    `tool_result_json` LONGTEXT NULL COMMENT '工具执行结果（JSON 原文）',
    `model` VARCHAR(64) NULL COMMENT '使用的模型（assistant 消息）',
    `tokens_used` INT NULL COMMENT '该轮消耗 token 数',
    `cost_cent` INT NULL COMMENT '该轮成本(分)',
    `seq` INT NOT NULL DEFAULT 0 COMMENT '消息序号（会话内自增）',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY `idx_acmsg_conversation_id` (`conversation_id`),
    KEY `idx_acmsg_seq` (`conversation_id`, `seq`),
    CONSTRAINT `fk_acmsg_conversation` FOREIGN KEY (`conversation_id`) REFERENCES `agent_conversations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='智能体对话消息表（预留）';
```

### 3.4 事件留痕表（审计）

**设计目标**：智能体平台的每一条操作（查询/修改/外部调用）都必须留痕，满足"全程留痕审计"要求。该表也覆盖现有 ai_chat 的工具调用日志。

#### 3.4.1 预留表：`agent_audit_logs`（DDL）

```sql
-- 智能体审计日志表（每一条工具调用/模型调用/人工确认都记录）
CREATE TABLE IF NOT EXISTS `agent_audit_logs` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY,
    `user_id` VARCHAR(36) NOT NULL COMMENT '操作教师',
    `conversation_id` VARCHAR(36) NULL COMMENT '关联对话',
    `event_type` VARCHAR(32) NOT NULL COMMENT 'tool_call|tool_result|llm_request|llm_response|human_approval|error',
    `event_subtype` VARCHAR(64) NULL COMMENT '细分: execute_mysql_query|send_notification|...',
    `tool_name` VARCHAR(64) NULL COMMENT '工具名（tool_call/tool_result 时）',
    `tool_args_json` JSON NULL COMMENT '工具入参（脱敏后）',
    `tool_result_summary` TEXT NULL COMMENT '工具结果摘要（完整结果太大时不存）',
    `tool_success` TINYINT(1) NULL COMMENT '工具执行是否成功',
    `model` VARCHAR(64) NULL COMMENT '使用的模型（llm_request/response 时）',
    `tokens_used` INT NULL COMMENT 'token 消耗',
    `cost_cent` INT NULL COMMENT '成本(分)',
    `latency_ms` INT NULL COMMENT '耗时(毫秒)',
    `approval_status` VARCHAR(16) NULL COMMENT 'pending|approved|rejected（human_approval 时）',
    `approval_reason` TEXT NULL COMMENT '审批备注',
    `ip_address` VARCHAR(45) NULL COMMENT '操作 IP',
    `user_agent` VARCHAR(512) NULL COMMENT 'User-Agent',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY `idx_aaal_user_id` (`user_id`),
    KEY `idx_aaal_event_type` (`event_type`),
    KEY `idx_aaal_conversation_id` (`conversation_id`),
    KEY `idx_aaal_created_at` (`created_at`),
    CONSTRAINT `fk_aaal_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='智能体审计日志表（预留，全程留痕）';
```

### 3.5 智能体平台整体数据架构概览

```
                       ┌──────────────────────┐
                       │    agent_roles        │
                       │  (教师自定义角色指令)   │
                       │  未来建表               │
                       └──────┬───────────────┘
                              │ 1:N
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
┌─────────────────┐ ┌──────────────┐ ┌──────────────┐
│ agent_tool_     │ │ agent_llm_   │ │ agent_       │
│ instances       │ │ configs      │ │ conversations│
│ (角色关联工具)   │ │ (角色关联模型) │ │ (角色关联对话) │
└─────────────────┘ └──────────────┘ └──────┬───────┘
                                            │ 1:N
                                    ┌───────▼───────┐
                                    │ agent_        │
                                    │ conversation_ │
                                    │ messages      │
                                    └───────────────┘

所有操作 ──────► agent_audit_logs（审计）
```

---

## 4. 命名/目录规范

### 4.1 新增域的文件组织

叙阅当前按**扁平化**组织 models 和 routers：

```
app/
├── models/           # 所有 model 平铺（一个文件一个 model）
├── routers/          # 所有 router 平铺
├── services/         # 业务逻辑（含 ai_chat_*.py 系列）
├── grading/          # 批改引擎独立目录
└── utils/            # 工具函数
```

**新增三个域的约定**：

#### 域 1: portfolio（五育成长画像）

| 文件 | 路径 | 说明 |
|------|------|------|
| Model | `app/models/student_portfolio.py` | `StudentPortfolio` 类 |
| Model | `app/models/student_growth_record.py` | `StudentGrowthRecord` 类 |
| Model | `app/models/student_point_account.py` | `StudentPointAccount` 积分账户 |
| Model | `app/models/student_point_transaction.py` | `StudentPointTransaction` 积分流水 |
| Router | `app/routers/portfolio.py` | 画像查询/更新 API |
| Router | `app/routers/points.py` | 积分相关 API |
| Service | `app/services/portfolio_engine.py` | 画像计算引擎 |

#### 域 2: assessment（测评）

| 文件 | 路径 | 说明 |
|------|------|------|
| Model | `app/models/assessment_definition.py` | `AssessmentDefinition` 测评题组定义 |
| Model | `app/models/assessment_session.py` | `AssessmentSession` 施测会话 |
| Model | `app/models/assessment_result.py` | `AssessmentResult` 测评结果锚点 |
| Router | `app/routers/assessment.py` | 测评 CRUD + 施测 API |
| Service | `app/services/assessment_engine.py` | 测评计分/标签映射逻辑 |

#### 域 3: student-ops（学生端运营）

| 文件 | 路径 | 说明 |
|------|------|------|
| Model | `app/models/student_task.py` | `StudentTask` 学生任务/打卡 |
| Model | `app/models/student_badge.py` | `StudentBadge` 徽章/成就 |
| Router | `app/routers/student_ops.py` | 学生端 API（任务/徽章/排行） |
| Service | `app/services/student_ops_engine.py` | 运营逻辑 |

### 4.2 智能体平台预留目录

未来智能体平台代码放独立目录，不污染现有结构：

```
app/
├── agent/                    # 智能体平台目录（未来）
│   ├── __init__.py
│   ├── gateway.py            # LLM Gateway 实现
│   ├── providers/            # 各模型 Provider
│   │   ├── __init__.py
│   │   ├── dashscope.py
│   │   ├── deepseek.py
│   │   └── mock.py
│   ├── tools/                # 内置工具实现
│   │   ├── __init__.py
│   │   ├── base.py           # AgentTool 基类
│   │   ├── registry.py       # 工具注册表
│   │   ├── query_students.py
│   │   ├── query_portfolio.py
│   │   └── create_todo.py
│   ├── memory/               # 记忆管理
│   │   ├── __init__.py
│   │   └── summary_manager.py
│   ├── audit/                # 审计留痕
│   │   └── audit_logger.py
│   └── router.py             # 智能体 API 路由
├── routers/                  # 现有路由
│   └── ai_chat.py            # 保持现有，逐步迁到 agent/
└── services/
    └── ai_chat_*.py          # 保持现有，agent/ 引用其工具执行逻辑
```

### 4.3 智能体工具如何读取种春风数据

**关键契约**：种春风所有表必须有结构化 `id`（UUID v4），智能体工具通过以下模式访问：

```python
# app/agent/tools/query_portfolio.py（未来示例）
class QueryPortfolioTool:
    name = "query_portfolio"
    description = "查询学生的五育成长画像，包括德智体美劳各维度得分和总分"
    parameters = {
        "type": "object",
        "properties": {
            "student_name": {"type": "string", "description": "学生姓名"},
            "class_name": {"type": "string", "description": "班级名称，可选"}
        },
        "required": ["student_name"]
    }
    
    async def execute(self, args, context):
        student_name = args["student_name"]
        # 通过 student_id JOIN student_portfolios 查询
        sql = """
            SELECT sp.*, s.name as student_name
            FROM student_portfolios sp
            JOIN students s ON s.id = sp.student_id
            JOIN classes c ON c.id = sp.class_id
            WHERE s.name = :name AND c.user_id = :user_id
        """
        # ... 执行 + 返回
```

**结论**：种春风表只要遵守第 1 节的数据层约定（有 UUID、有外键、有时间戳），未来的智能体就可以无痛接入。不要求额外的适配层。

---

## 5. 种春风新增表 DDL

以下 DDL 均遵循本章第 1-2 节规范，可直接用于生产手工迁移。

### 5.1 `student_portfolios` — 学生五育成长画像

```sql
CREATE TABLE IF NOT EXISTS `student_portfolios` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `student_id` VARCHAR(36) NOT NULL COMMENT '学生ID',
    `class_id` VARCHAR(36) NOT NULL COMMENT '班级ID',
    `base_points` INT NOT NULL DEFAULT 100 COMMENT '基础积分',
    `dimension_moral` FLOAT NULL DEFAULT 0 COMMENT '德育维度得分',
    `dimension_intellectual` FLOAT NULL DEFAULT 0 COMMENT '智育维度得分',
    `dimension_physical` FLOAT NULL DEFAULT 0 COMMENT '体育维度得分',
    `dimension_aesthetic` FLOAT NULL DEFAULT 0 COMMENT '美育维度得分',
    `dimension_labor` FLOAT NULL DEFAULT 0 COMMENT '劳育维度得分',
    `dimension_total` FLOAT NULL DEFAULT 0 COMMENT '五育综合总分',
    `detail_json` LONGTEXT NULL COMMENT '画像明细(非结构化，供前端渲染)',
    `auto_detail_json` LONGTEXT NULL COMMENT '自动计算明细(机器可读)',
    `total_growth_points` INT NOT NULL DEFAULT 0 COMMENT '累计成长积分',
    `last_calculated_at` DATETIME NULL COMMENT '最近一次重算时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_sp_student_id` (`student_id`),
    KEY `idx_sp_class_id` (`class_id`),
    CONSTRAINT `fk_sp_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_sp_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='学生五育成长画像主表';
```

### 5.2 `student_growth_records` — 成长记录流水

```sql
CREATE TABLE IF NOT EXISTS `student_growth_records` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `student_id` VARCHAR(36) NOT NULL COMMENT '学生ID',
    `class_id` VARCHAR(36) NOT NULL COMMENT '班级ID',
    `user_id` VARCHAR(36) NOT NULL COMMENT '创建教师ID',
    `dimension` VARCHAR(16) NOT NULL COMMENT '五育维度: moral|intellectual|physical|aesthetic|labor',
    `source_type` VARCHAR(32) NOT NULL DEFAULT 'manual' COMMENT '来源: exam|wrong_question|assessment|task|manual',
    `source_id` VARCHAR(36) NULL COMMENT '来源记录ID（exam_scores.id / wrong_questions.id / assessment_results.id 等）',
    `growth_points` INT NOT NULL COMMENT '本次成长积分(+/-)',
    `evidence_json` JSON NULL COMMENT '证据数据(结构化，供智能体读取)',
    `note` VARCHAR(512) NULL COMMENT '教师备注',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY `idx_sgr_student_id` (`student_id`),
    KEY `idx_sgr_class_id` (`class_id`),
    KEY `idx_sgr_user_id` (`user_id`),
    KEY `idx_sgr_dimension` (`dimension`),
    KEY `idx_sgr_source_type` (`source_type`),
    KEY `idx_sgr_created_at` (`created_at`),
    CONSTRAINT `fk_sgr_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_sgr_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_sgr_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='学生成长记录流水表';
```

### 5.3 `student_point_accounts` — 学生积分账户

```sql
CREATE TABLE IF NOT EXISTS `student_point_accounts` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `student_id` VARCHAR(36) NOT NULL COMMENT '学生ID',
    `class_id` VARCHAR(36) NOT NULL COMMENT '班级ID',
    `total_points` INT NOT NULL DEFAULT 0 COMMENT '累计积分余额',
    `frozen_points` INT NOT NULL DEFAULT 0 COMMENT '冻结积分（待核销）',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_spa_student_id` (`student_id`),
    KEY `idx_spa_class_id` (`class_id`),
    CONSTRAINT `fk_spa_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_spa_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='学生积分账户表';
```

### 5.4 `student_point_transactions` — 积分流水

```sql
CREATE TABLE IF NOT EXISTS `student_point_transactions` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `student_id` VARCHAR(36) NOT NULL COMMENT '学生ID',
    `class_id` VARCHAR(36) NOT NULL COMMENT '班级ID',
    `user_id` VARCHAR(36) NULL COMMENT '操作教师ID（系统自动为空）',
    `type` VARCHAR(16) NOT NULL COMMENT '类型: earn|spend|adjust|expire',
    `amount` INT NOT NULL COMMENT '积分变动(+/-)',
    `balance_after` INT NOT NULL COMMENT '变动后余额',
    `reason` VARCHAR(32) NOT NULL COMMENT '原因分类: exam_top3|task_complete|behavior_reward|manual|...',
    `source_type` VARCHAR(32) NULL COMMENT '来源表: growth_records|tasks|manual',
    `source_id` VARCHAR(36) NULL COMMENT '来源记录ID',
    `note` VARCHAR(255) NULL COMMENT '备注',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY `idx_spt_student_id` (`student_id`),
    KEY `idx_spt_class_id` (`class_id`),
    KEY `idx_spt_type` (`type`),
    KEY `idx_spt_reason` (`reason`),
    KEY `idx_spt_created_at` (`created_at`),
    CONSTRAINT `fk_spt_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_spt_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='学生积分变动流水表';
```

### 5.5 `assessment_definitions` — 测评题组定义

```sql
CREATE TABLE IF NOT EXISTS `assessment_definitions` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `name` VARCHAR(255) NOT NULL COMMENT '测评名称',
    `domain` VARCHAR(32) NOT NULL COMMENT '测评领域: personality|interest|learning_style|self_built',
    `grade_range` VARCHAR(16) NOT NULL DEFAULT 'all' COMMENT '适用学段: primary|junior|senior|all',
    `version` INT NOT NULL DEFAULT 1 COMMENT '版本号',
    `status` VARCHAR(16) NOT NULL DEFAULT 'draft' COMMENT 'draft|active|retired',
    `questions_json` JSON NOT NULL COMMENT '题组定义 [{id,text,options:[{key,text,dimension}]}]',
    `consent_required` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否需要家长知情同意',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY `idx_ad_domain` (`domain`),
    KEY `idx_ad_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='测评题组定义表';
```

### 5.6 `assessment_sessions` — 施测会话

```sql
CREATE TABLE IF NOT EXISTS `assessment_sessions` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `student_id` VARCHAR(36) NOT NULL COMMENT '学生ID',
    `definition_id` VARCHAR(36) NOT NULL COMMENT '测评题组ID',
    `class_id` VARCHAR(36) NOT NULL COMMENT '班级ID',
    `user_id` VARCHAR(36) NULL COMMENT '施测教师ID（自主测评为空）',
    `test_mode` VARCHAR(16) NOT NULL DEFAULT 'class_batch' COMMENT 'class_batch|self',
    `status` VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending|in_progress|submitted|graded',
    `answers_json` JSON NULL COMMENT '学生作答 [{question_id, selected_key}]',
    `taken_at` DATETIME NULL COMMENT '开始作答时间',
    `submitted_at` DATETIME NULL COMMENT '提交时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY `idx_ases_student_id` (`student_id`),
    KEY `idx_ases_definition_id` (`definition_id`),
    KEY `idx_ases_class_id` (`class_id`),
    KEY `idx_ases_status` (`status`),
    CONSTRAINT `fk_ases_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ases_definition` FOREIGN KEY (`definition_id`) REFERENCES `assessment_definitions` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ases_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='测评施测会话表';
```

### 5.7 `assessment_results` — 测评结果锚点

```sql
CREATE TABLE IF NOT EXISTS `assessment_results` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `session_id` VARCHAR(36) NOT NULL COMMENT '施测会话ID',
    `student_id` VARCHAR(36) NOT NULL COMMENT '学生ID',
    `definition_id` VARCHAR(36) NOT NULL COMMENT '测评题组ID',
    `class_id` VARCHAR(36) NOT NULL COMMENT '班级ID',
    `domain` VARCHAR(32) NOT NULL COMMENT '测评领域',
    `purpose` VARCHAR(16) NOT NULL DEFAULT 'anchor' COMMENT '用途: 仅允许anchor(锚点，不进五育评分)',
    `tag_schema_json` JSON NOT NULL COMMENT '标签体系结果 {dimension_key: {label, score, percentile}}',
    `raw_score_json` JSON NULL COMMENT '原始得分',
    `guardian_consent_status` VARCHAR(16) NOT NULL DEFAULT 'not_required' COMMENT 'not_required|granted|withdrawn',
    `guardian_consent_granted_at` DATETIME NULL COMMENT '家长知情同意时间',
    `guardian_consent_withdrawn_at` DATETIME NULL COMMENT '家长撤回同意时间',
    `created_by` VARCHAR(36) NULL COMMENT '创建教师ID',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_ar_session_id` (`session_id`),
    KEY `idx_ar_student_id` (`student_id`),
    KEY `idx_ar_definition_id` (`definition_id`),
    KEY `idx_ar_class_id` (`class_id`),
    KEY `idx_ar_domain` (`domain`),
    CONSTRAINT `fk_ar_session` FOREIGN KEY (`session_id`) REFERENCES `assessment_sessions` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ar_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ar_definition` FOREIGN KEY (`definition_id`) REFERENCES `assessment_definitions` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ar_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='测评结果锚点表（不进五育评分，独立存储）';
```

### 5.8 `student_tasks` — 学生任务/打卡

```sql
CREATE TABLE IF NOT EXISTS `student_tasks` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `student_id` VARCHAR(36) NOT NULL COMMENT '学生ID',
    `class_id` VARCHAR(36) NOT NULL COMMENT '班级ID',
    `user_id` VARCHAR(36) NULL COMMENT '发布教师ID',
    `title` VARCHAR(255) NOT NULL COMMENT '任务标题',
    `description` TEXT NULL COMMENT '任务描述',
    `task_type` VARCHAR(32) NOT NULL DEFAULT 'daily' COMMENT 'daily|weekly|custom',
    `dimension` VARCHAR(16) NULL COMMENT '关联五育维度(可选)',
    `reward_points` INT NOT NULL DEFAULT 0 COMMENT '完成奖励积分',
    `due_date` DATE NULL COMMENT '截止日期',
    `status` VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending|done|expired',
    `completed_at` DATETIME NULL COMMENT '完成时间',
    `evidence_json` JSON NULL COMMENT '完成证据（图片/文字）',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY `idx_st_student_id` (`student_id`),
    KEY `idx_st_class_id` (`class_id`),
    KEY `idx_st_user_id` (`user_id`),
    KEY `idx_st_status` (`status`),
    KEY `idx_st_due_date` (`due_date`),
    CONSTRAINT `fk_st_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_st_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='学生任务/打卡表';
```

### 5.9 `student_badges` — 学生徽章/成就

```sql
CREATE TABLE IF NOT EXISTS `student_badges` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `student_id` VARCHAR(36) NOT NULL COMMENT '学生ID',
    `class_id` VARCHAR(36) NOT NULL COMMENT '班级ID',
    `badge_code` VARCHAR(64) NOT NULL COMMENT '徽章编码: top_scorer|improvement_star|full_attendance|...',
    `badge_name` VARCHAR(128) NOT NULL COMMENT '徽章名称',
    `badge_icon_url` VARCHAR(512) NULL COMMENT '徽章图标URL',
    `award_reason` VARCHAR(255) NULL COMMENT '获奖原因',
    `awarded_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '获奖时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY `idx_sb_student_id` (`student_id`),
    KEY `idx_sb_class_id` (`class_id`),
    KEY `idx_sb_badge_code` (`badge_code`),
    CONSTRAINT `fk_sb_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_sb_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='学生徽章/成就表';
```

### 5.10 `report_snapshots` — 学期报告快照

```sql
CREATE TABLE IF NOT EXISTS `report_snapshots` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `student_id` VARCHAR(36) NOT NULL COMMENT '学生ID',
    `class_id` VARCHAR(36) NOT NULL COMMENT '班级ID',
    `user_id` VARCHAR(36) NULL COMMENT '生成教师ID',
    `term` VARCHAR(32) NOT NULL COMMENT '学期标识: 2025-spring|2025-autumn',
    `version` INT NOT NULL DEFAULT 1 COMMENT '版本号（同学生同学期每次freeze +1）',
    `parent_id` VARCHAR(36) NULL COMMENT '指向前一版本（版本链）',
    `payload_json` JSON NOT NULL COMMENT '完整报告内容(冻结快照，不可变)',
    `generated_by` VARCHAR(36) NULL COMMENT '生成者用户ID',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_rs_student_term_version` (`student_id`, `term`, `version`),
    KEY `idx_rs_term` (`term`),
    CONSTRAINT `fk_rs_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_rs_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='学期报告快照表（冻结不可变）';
```

### 5.11 `assessment_comments` — AI 学期评语

```sql
CREATE TABLE IF NOT EXISTS `assessment_comments` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `student_id` VARCHAR(36) NOT NULL COMMENT '学生ID',
    `class_id` VARCHAR(36) NOT NULL COMMENT '班级ID',
    `user_id` VARCHAR(36) NULL COMMENT '生成教师ID',
    `term` VARCHAR(32) NOT NULL COMMENT '学期标识',
    `status` VARCHAR(16) NOT NULL DEFAULT 'ai_generated' COMMENT 'ai_generated|confirmed|ai_failed',
    `ai_content` TEXT NULL COMMENT 'AI 生成的原始评语',
    `confirmed_content` TEXT NULL COMMENT '教师确认/修改后的评语',
    `ai_model` VARCHAR(64) NULL COMMENT '使用的 AI 模型',
    `tokens_used` INT NULL COMMENT '消耗 token 数',
    `cost_cent` INT NULL COMMENT '成本(分)',
    `gate_flagged` TINYINT(1) NULL COMMENT '词表闸门是否标记',
    `confirmed_by` VARCHAR(36) NULL COMMENT '确认教师ID',
    `confirmed_at` DATETIME NULL COMMENT '确认时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_ac_student_term` (`student_id`, `term`),
    KEY `idx_ac_class_id` (`class_id`),
    KEY `idx_ac_status` (`status`),
    CONSTRAINT `fk_ac_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ac_class` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='AI学期评语表';
```

### 5.12 `mentors` — 学生导师指派

```sql
CREATE TABLE IF NOT EXISTS `mentors` (
    `id` VARCHAR(36) NOT NULL PRIMARY KEY COMMENT 'UUID v4',
    `student_id` VARCHAR(36) NOT NULL COMMENT '学生ID',
    `user_id` VARCHAR(36) NOT NULL COMMENT '导师教师ID',
    `role` VARCHAR(16) NOT NULL DEFAULT 'tutor' COMMENT 'tutor|guardian（guardian留位未来家长绑定）',
    `assigned_by` VARCHAR(36) NULL COMMENT '指派者ID',
    `status` VARCHAR(16) NOT NULL DEFAULT 'active' COMMENT 'active|revoked',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uq_mtr_student_user` (`student_id`, `user_id`),
    KEY `idx_mtr_user_id` (`user_id`),
    CONSTRAINT `fk_mtr_student` FOREIGN KEY (`student_id`) REFERENCES `students` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_mtr_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='学生导师指派表';
```

---

## 6. 现有 ai_chat 演进评估

### 6.1 现有架构总览

叙阅当前 AI 助手由 `app/services/ai_chat_*.py` 系列文件和 `app/routers/ai_chat.py` 组成：

```
ai_chat.py (路由)
├── ai_chat_prompt.py         # 系统 Prompt 构建 + 数据字典注入
├── ai_chat_tools.py          # Tool 调度（execute_ai_chat_tool）
├── ai_chat_mysql_executor.py # MySQL 只读 SELECT 执行器（权限控制 + SQL 安全校验）
├── ai_chat_local_executor.py # 本地批改数据查询（local_* 虚拟表）
├── ai_chat_auto_tools.py     # 意图识别 + 预查（规则匹配，非 LLM 驱动）
├── ai_chat_intent_queries.py # 意图→SQL 模板映射
├── ai_chat_guard.py          # 预查结果格式化
├── ai_chat_privacy.py        # 隐私问题拒绝
├── ai_chat_access.py         # 数据问题识别
├── ai_chat_mysql_scope.py    # MySQL 表访问范围控制
├── ai_chat_sql_utils.py      # SQL 解析/校验
├── ai_chat_data_schema.py    # 数据字典构建
├── ai_chat_math_style.py     # 数学格式规则
├── ai_chat_feature_knowledge.py    # 功能使用问答
├── ai_chat_tutorials.py      # 功能引导
└── ai_chat_tutorial_semantics.py   # 意图语义判断
```

### 6.2 优点（可作为底座的部分）

| 组件 | 价值 | 复用方式 |
|------|------|---------|
| `ai_chat_mysql_executor.py` | **SQL 安全执行器**：SELECT-only + 表白名单 + user_id 自动注入 + 隐私列过滤。这是智能体数据查询工具的核心。 | 直接作为 `execute_mysql_query` tool 的实现层 |
| `ai_chat_mysql_scope.py` | **表级权限控制**：`ACCOUNT_ISOLATED_TABLES`（教案/组卷仅自己帐号）、`ADMIN_ONLY_MYSQL_TABLES`（管理表拒查） | 智能体工具注册时声明每工具的 allowed_tables |
| `ai_chat_privacy.py` | **隐私保护**：拒查 users/profiles/password 相关查询 | 智能体系统 Prompt 继承此规则 |
| `ai_chat_sql_utils.py` | **SQL 解析/校验**：提取表名、校验 SELECT | 智能体工具的 SQL 预处理层 |
| `ai_chat_prompt.py` 的 data_schema | **数据字典注入**：自动构建表结构说明注入 Prompt | 智能体 system prompt 复用此机制 |
| 多轮 tool call 循环 | `_run_tool_rounds` 支持 5 轮 tool call 循环 | 智能体编排的核心循环 |
| SSE 流式输出 | `_iter_qwen_sse` + `StreamingResponse` | 智能体对话保持流式体验 |

### 6.3 差距（做智能体平台必须重构的部分）

| 差距 | 严重度 | 当前状态 | 需要的改动 |
|------|--------|---------|-----------|
| **单模型硬编码** | 高 | 只调 `qwen3.7-plus`，API Key 全局一份 | 改为 LLM Gateway Provider 模式（第 3.1 节） |
| **无工具注册表** | 高 | `execute_ai_chat_tool` 是 if/elif 硬编码，2 个工具 | 改为 Tool Registry（第 3.2 节），支持教师自定义启用/禁用 |
| **无会话持久化** | 高 | 消息仅在前端 state 中，后端无会话记录 | 加 `agent_conversations` + `agent_messages`（第 3.3.2 节） |
| **无审计日志** | 高 | 工具调用不记录任何日志 | 加 `agent_audit_logs`（第 3.4.1 节） |
| **意图识别靠规则** | 中 | 正则 + 关键词匹配，无 NLU | 改为 LLM function calling 驱动（千问已支持） |
| **工具参数靠 LLM 生成 SQL** | 中 | 直接让 LLM 写 SELECT，风险高 | 改为"参数化工具"：LLM 只填参数，工具内部拼接 SQL |
| **无多角色支持** | 中 | 系统 Prompt 写死"AI 助教"一个角色 | 加 `agent_roles` 表，教师可自定义角色指令 |
| **无人工确认机制** | 低 | 所有操作自动执行 | 加 `requires_approval` 标志位 + 审批流程 |
| **无跨会话记忆** | 低 | 每次对话从零开始 | 加 L2 摘要缓存（第 3.3.1 节） |
| **无模型计量/成本** | 低 | 不统计 token / 成本 | LLMResponse 加 tokens_used / cost_cent |

### 6.4 演进路径建议

```
阶段 0（当前，已完成）：
  意图识别(规则) + 工具执行(SQL) + 单模型(千问)
  
阶段 1（种春风同期，1-2 周）：
  ├── 建 agent_audit_logs 表，ai_chat.py 每次工具调用写审计日志
  ├── 建 agent_conversations + agent_conversation_messages 表，对话落库
  ├── 重构 ai_chat_prompt.py 的 tools 定义为 Tool Registry 基础版（仍硬编码，但结构统一）
  └── 意图识别改为 LLM function calling 驱动（千问已支持，去掉规则匹配）

阶段 2（智能体平台 MVP，2-3 周）：
  ├── 实现 LLMGateway（先支持 DashScope + MockProvider）
  ├── 建 agent_llm_configs 表，支持教师配置自己的 API Key
  ├── 建 agent_roles 表，教师可自定义系统 Prompt
  └── 建 agent_tools + agent_tool_instances 表，角色可关联工具

阶段 3（完整智能体，后续）：
  ├── 多模型支持（DeepSeek / 客户私有模型）
  ├── 工作流编排（DAG 执行图）
  ├── 知识库挂载（RAG，先考虑用 MySQL 全文索引，再评估向量数据库）
  ├── 定时任务（cron 触发智能体主动推送）
  └── 校务系统对接工具
```

### 6.5 关键风险提示

1. **SQL 生成风险**：当前让 LLM 直接生成 SQL 的模式在智能体平台中不安全。建议在阶段 1 就改为"参数化工具"模式——工具定义好参数（如 `student_name`、`exam_title`），工具内部拼接 SQL，LLM 只填参数不写 SQL。现有 `execute_mysql_query` 仅作为 fallback 保留给高级用户。

2. **会话记忆膨胀**：如果不控制 context window，长对话会导致 token 消耗指数增长。阶段 1 就需要 L2 摘要机制，每 N 轮对话自动生成摘要并截断历史消息。

3. **外键耦合**：审计表 `agent_audit_logs` 的 `conversation_id` 外键不应强制级联删除（对话删除后审计日志保留），建议用 `ON DELETE SET NULL` 或在应用层处理。

4. **单机瓶颈**：叙阅目前是单机部署，MySQL 在十万级数据量下完全没问题。但智能体平台的高频审计写入（每次 tool call 一条）可能成为瓶颈——建议 `agent_audit_logs` 异步批量写入（攒 10 条或 5 秒刷一次）。

---

## 变更记录

（初始版本，无变更）

