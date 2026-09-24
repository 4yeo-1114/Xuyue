# 独立老师支付系统 · 设计文档

> 版本：**1.1**（设计稿）
> 日期：2026-09-24
> 设计基线：**commit `72c5878`（分支 `feat/independent-teacher`）**，⛔ **不是 `main`**（`main` = `a8da4f7`，不含独立老师那 4 个 commit）
> 状态：**只出设计，零实现代码**。本文件不新增 `.py`、不改前端。
> 作者：software-architect

> ⛔ **坐标来源（本文**全文**适用 —— 上一版 v1.0 在这里踩过坑，故单列一行）**
> 本文所有 `路径:行号` 坐标 = **`feat/independent-teacher` @ `72c5878`**
> （工作树：`F:\xuyue-local\.claude\worktrees\independent-teacher\`）
> **⛔ 不是 `main`（@ `a8da4f7`）** —— `main` 是**收窄前**的代码，`routers/scan_billing.py`、`routers/auth.py`、`Sidebar.tsx` 等文件在两树上的行号**不同**。
> 复核命令（可复跑）：
> ```bash
> git -C F:/xuyue-local rev-parse feat/independent-teacher main
> # 期望输出：72c5878a65d79f78d7fac4217da64c785717d608
> #           a8da4f7609a4ba6f4dd1d28824089b098a68d928
> ```
> **两树坐标一致的引用文件**（本次未受改动影响）：`billing_pricing.py`、`grading_stats.py`、`billing_config.example.json`、`models/*`、`database.py`、`config.py`、`main.py`、`frontend/src/services/api.ts`、`frontend/src/config/api.ts`。
> **其余引用文件的行号一律以本分支为准。**

---

## §0 阅读须知：证据状态图例与本席的作业条件

**本席作业条件（必须先说清，影响本文可信度）：**
本会话**只拿到 `Read` / `Write` 两个工具，没有 shell**。因此：
- ⛔ **无法执行** `git worktree add`（任务要求的第一步隔离环境**没有建起来**）
- ⛔ **无法执行** `git status --short`（任务要求的报告项给不出）
- ⛔ **无法 grep / find**，"支付侧零存在"这类**全仓断言本席无法复核**

**落地位置说明（替代方案）**：`payment-design` worktree 建不出来，本文件写在**同分支线的既有 worktree** 里。移动方式见 §11.5。

**每条现状断言的证据等级：**

| 标记 | 含义 |
|------|------|
| ✅ | 本席**本次实测**，给 `路径:行号`；括号内给可复跑命令 |
| 🟡 | 背景已核实，**本席本次未复核**（原因写明） |
| ❓ | **① 类未拍项**，只有业务方/主导者知道，本席不猜 |

**本文引用的所有路径均为仓内相对路径。** 本席实测时的工作树根为
`F:\xuyue-local\.claude\worktrees\independent-teacher\`（下称 `<WT>`），分支 `feat/independent-teacher` @ `72c5878`。

---

## §1 口径分层 —— 本文最重要的一节

### 1.1 现有「计费」到底是什么口径

✅ **现有计费是「平台自己花了多少钱」的成本核算，不是「向老师收多少钱」。**

证据链（全部实测）：

| # | 断言 | 证据 |
|---|------|------|
| 1 | 模块自述"计费模型对齐七牛云对象存储（Kodo）公开口径"，把「试卷扫描批改」**映射到**存储/请求/数据处理/流量四类**成本项** | `backend/app/services/billing_pricing.py:1-23`（`sed -n '1,23p' backend/app/services/billing_pricing.py`） |
| 2 | 单价默认值自述"**仅作参考**……实际计费请以商务合同为准" | `backend/app/services/billing_pricing.py:37-40` |
| 3 | 配置示例文件的 `note` 写"单价按实际商务合同填写；默认值仅参照七牛云对象存储公开口径，**仅供演示**" | `backend/billing_config.example.json:7` |
| 4 | 计量口径对齐七牛的**成本结算规则**：存储取"月度日均值"、次数类"不足一单位进位" | `billing_pricing.py:7-8`、`billing_pricing.py:314-354` |
| 5 | 6 个消费型端点全是**只读投影**，数据源是旁路累加的 `grading_daily_stats`，**没有任何写路径** | `backend/app/routers/scan_billing.py:11-12` 及下表 |

✅ **`scan_billing.py` 的 9 个端点（全 `@router.get`，零写路径 —— 分支新增的 `resolve_scope_user_id`（`:56-68`）是**读路径收敛**，不是写路径）**：

| # | 路径 | 分支行号 | Depends 行 | scope 收敛接线行 |
|---|------|---------|-----------|----------------|
| 1 | `GET /scan-billing/consumption` | `:89` | `:94` | `:100` |
| 2 | `GET /scan-billing/trends` | `:190` | `:197` | `:203` |
| 3 | `GET /scan-billing/breakdown` | `:267` | `:273` | `:279` |
| 4 | `GET /scan-billing/monthly` | `:324` | `:329` | `:332` |
| 5 | `GET /scan-billing/user-ranking` | `:390` | `:395` | `:403` |
| 6 | `GET /scan-billing/pricing` | `:475` | `:477` | —（无 user_id 参数） |
| 7 | `GET /scan-billing/estimate` | `:555` | `:559` | `:567` |
| 8 | `GET /scan-billing/bill` | `:578` | `:583` | `:592` |
| 9 | `GET /scan-billing/usage-stats` | `:634` | `:643` | `:652` |

（可复跑：`grep -n '@router\.' backend/app/routers/scan_billing.py`）
挂载点：`backend/app/main.py:289-290`，前缀 `/api/v1`。

### 1.2 两个口径的正式定义

| 维度 | **口径 A · 成本核算**（已存在） | **口径 B · 向老师收费**（本文设计） |
|------|-------------------------------|-----------------------------------|
| 回答的问题 | 这套系统**我们**花了多少钱 | 独立老师**该付**我们多少钱 |
| 计量对象 | 平台资源消耗（存储/请求/AI 处理/流量） | 老师消耗的**服务次数**（见 §3.1） |
| 数据源 | `grading_daily_stats` + 文件系统 `mtime` 重建 | **新增** `usage_events`（只增事件流） |
| 价格来源 | `backend/billing_config.json`（`billing_pricing.py:108-111` 的 `project_root()/billing_config.json`） | **新增** `backend/payment_pricing.json` |
| 免费额度语义 | **平台成本允许量**（"这 10GB 我们自己承担"） | **客户权益**（"你套餐里含 500 份"） |
| 可变性 | **可回退**（见 §1.3 陷阱 3） | 必须**只增不改** + 反向分录 |
| 谁看 | 平台运营 / 管理员 | **老师本人** |
| 出错后果 | 估算偏差，可接受 | **收错钱 / 老师投诉 / 无法对账** |

### 1.3 三条真实的污染路径（为什么"混用"不是洁癖问题）

**陷阱 1 —— `free_quota` / `resource_pack` 是成本概念，被误当成客户余额。**
`billing_config.example.json:51-53` 定义：
- `free_quota` = "每月免费额度（按该项 unit 计），先于资源包与阶梯价抵扣"
- `resource_pack` = "**已购资源包余量**（按该项 unit 计），在免费额度之后抵扣"

`resource_pack` 的措辞（"已购资源包余量"）与"预充值余额"**长得一模一样**。最危险的实现是：**把老师的余额写进 `billing_config.json` 的 `resource_pack`**。
后果：① `billing_config.json` 是**全局单文件**（`billing_pricing.py:111`），全班老师共用一个数字；② 写它等于给全平台老师改价；③ 每次改动还要落盘 JSON，无事务、无审计、无并发保护。
⛔ **本设计明令禁止任何把客户余额/套餐额度写入 `billing_*` 配置的行为。**

**陷阱 2 —— `meter_divisor` 是七牛的计量单位换算，不是业务计价单位。**
`billing_pricing.py:99-104`：`upload` 除以 10000（次→万次）、`grading` 除以 1000（次→千次）。`round_up` 还会"不足 1 千次按 1 千次计"（`billing_pricing.py:216-218`）。
这是**为七牛账单口径服务的进位规则**。若客户计价沿用，会出现"老师批改了 1 份，被按 1 千次计价"的荒谬结果。
⛔ **口径 B 独立定义计价单位与进位规则，不复用 `meter_divisor` / `round_up`。**

**陷阱 3 —— 口径 A 的"用量"是可变存量，账本必须是不可变流水。**
✅ `grading_stats.py` **存在多条扣减路径**：

| 路径 | 行为 | 行号 |
|------|------|------|
| `record_upload_decrement` / `record_grade_decrement` | 按天倒序扣减计数 | `grading_stats.py:223-228` / `186-220` |
| `record_paper_deleted_for_file` | 删除试卷 → 可能扣上传/批改 | `grading_stats.py:231-247` |
| `remove_folder_stats` | **清空整个文件夹的统计行** | `grading_stats.py:250-265` |
| `record_graded_state_change` | 已批改→未批改时 **-1** | `grading_stats.py:294-325`（L320-323 是关键分支） |

⇒ 老师的"用量数字"**会变小**。若账本直接读这个数字来算钱，那么"删掉试卷"就等于"退款"，且 `remove_folder_stats`（L250-265）会**一次性抹掉历史**。
⇒ 更糟：`_increment` 的异常被**静默吞掉**（`grading_stats.py:161-162`），`record_graded_state_change` 整个函数包在 `try/except: pass` 里（`grading_stats.py:304-325`）。
**对成本核算**：少统计几笔，估算偏差，可接受。
**对收费**：账本会**静默少收/多收**，且没有任何错误日志 ← 这是不可接受的。
⛔ **口径 B 必须有独立的、不被吞异常的计量写入路径**（§7.1）。

### 1.4 共享阶梯价引擎？—— 拆开看：一个函数可以，其余不行

✅ `tiered_price(quantity, tiers)`（`billing_pricing.py:141-192`）是**纯函数**：入参数量 + 阶梯，出参金额与分段明细，**无 I/O、无全局状态、不读配置**。

**结论：**

| 组件 | 能否跨口径共用 | 理由 |
|------|---------------|------|
| `tiered_price()` | ✅ **复用** | 无状态纯算法；复制一份必然分叉（两处累进逻辑分别演化 = 两份 bug） |
| `calc_item_fee()` | ⛔ 不复用 | 绑定了 `meter_divisor` / `round_up` / `free_quota` / `resource_pack`（`billing_pricing.py:195-239`），全是成本口径语义 |
| `calc_total()` / `load_config()` | ⛔ 不复用 | 绑定 `billing_config.json` 单文件与"免费额度→资源包→阶梯价"抵扣顺序（`billing_pricing.py:42`、`242-252`） |
| `monthly_avg_storage_gb()` | ⛔ 不复用 | 半年 `mtime` 重建的**近似**口径，自述"历史值会低估"（`billing_pricing.py:270-271`）。收费不能用近似值 |

**复用的代价与对策**：跨口径共用一个函数 = 一个接缝。对策是**在 `tiered_price` 上加显式注释**声明"本函数为口径 A/B 共享的公共算法，改动需同时验证两侧"，并要求两侧各有用例（防止"单摘一条仍全绿"）。这是我愿意付的代价，好过两份累进实现。

### 1.5 ⚠️ 一个已经发生的混用风险（现存问题，本批只报告）

✅ `frontend/src/constants/systemRoles.ts:65-66` 把 **`scan-consumption`（扫描消耗）与 `usage-summary`（用量汇总）**放进了独立老师导航白名单。
✅ 这两个入口渲染的正是**口径 A 的成本核算页面**：`frontend/src/components/scan-billing/ScanConsumptionPage.tsx`（顶部导入 `fetchUsageStats/fetchBreakdown`，`:20-28`）与 `UsageSummaryPage.tsx`（导入 `fetchEstimate/fetchBill/fetchPricing`，`:20-27`）；后端对应 `scan_billing.py` 的 6 个消费型端点。

⇒ **独立老师现在打开"用量汇总"，看到的是七牛口径的平台成本数字（含 `¥0.6/千次` 这类单价），页面上没有任何"这是平台成本口径、不是你的账单"的标注。** 老师极易把它当成自己的账单。
⇒ 这**不是**本设计要修的东西（本批零代码改动），但它是"口径必须分层"的**现实论据**，并且给实现批留了一条硬要求：**口径 B 上线时，这两个页面的标题/说明必须显式标注口径 A，或改用口径 B 的数据源**。列为 §9 Phase 0 的验收项之一。

---

## §2 通道适配层 —— 把 ① 类未拍项隔离在一个壳里

### 2.1 设计目标

让**除通道外的全部工作**（账本、计量、套餐、账单投影、前端页面）**在通道未定之前就能做完并验收**。
手段：所有"钱真的动起来"的动作，只允许经过一个**窄接口**；接口之下按通道实现，未定之前挂一个"未实现/人工"的实现。

### 2.2 接口契约（抽象，不落实现）

```python
# app/services/payment/channels/base.py（设计示意，本批不写）

class ChannelCapabilities(TypedDict):
    supports_callback: bool      # 是否有异步回调（对公转账 = False，需人工核销）
    supports_refund: bool        # 是否支持原路退回
    requires_payee_entity: bool  # 是否绑定收款主体（①② 未定 → 现在无值可填）
    fee_rate_bps: int | None     # 通道手续费（bps），None = 未定

class PaymentChannelAdapter(Protocol):
    channel: str  # "wechat_pay" | "alipay" | "bank_transfer" | "manual" | "unset"

    def capabilities(self) -> ChannelCapabilities: ...
    def create_payment(self, order: "PaymentOrder") -> "ChannelIntent": ...
    def parse_callback(self, raw_body: bytes, headers: Mapping[str, str]) -> "ChannelCallback | None": ...
    def query_payment(self, channel_trade_no: str) -> "ChannelPaymentStatus": ...
    def create_refund(self, req: "RefundRequest") -> "ChannelRefundResult": ...
```

**`UnsetChannelAdapter`（默认注册项）行为**：`capabilities()` 返回 `channel="unset"`；
`create_payment` 抛 `HTTPException(status_code=501, detail="收款通道尚未配置")`；
`parse_callback` 恒返回 `None`。
⇒ **未定 = 一个可运行、可测试、明确报错的实现，而不是"到处 if 判断"或"留白"。** 这样账本侧代码**一条都不用改**，通道定了只需新增一个 adapter 并改注册项。

### 2.3 账本侧对通道的唯一依赖（保持窄）

账本只认识**一个事实**：`订单 X 已被通道确认收款`。
⇒ 账本服务提供一个幂等入口 `apply_payment_confirmed(order_id, channel_trade_no, paid_amount_fen, paid_at)`，由 adapter 的回调解析器或人工核销入口调用。
**账本永不 import 任何通道 SDK。** 这条边界就是"通道未定也能力开发"的保证。

---

## §3 账本模型（预充值余额）

### 3.1 计费的「量」是什么（口径 B 的计价项）

✅ 口径 A 有 4 个计量项（`billing_pricing.py:43-97` 的 `items`）：`storage` / `upload` / `grading` / `download`。

**口径 B 的选择（技术判断，③ 类）：**

| 口径 A 项 | 口径 B 是否收费 | 理由 |
|-----------|----------------|------|
| `grading`（AI 批改处理） | ✅ **主项**，单位 = **"份"**（按学生·份，见下） | 与真实成本最相关、事件边界最清晰、老师最容易理解 |
| `upload`（上传请求） | 🟡 **可选次项**，默认**不收** | 已有"同一学生多张仅计 1 份"的去重语义（`grading_stats.py:171-179`），单独收费价值低、争议高 |
| `storage`（存储） | ⛔ **不按量收** | ① 口径 A 用的是"月度日均值"（`billing_pricing.py:320-323`），是**近似值**且自述低估；② 它**最容易回退**（删文件夹 → `remove_folder_stats` 清零，`grading_stats.py:250-265`）。**日均存量不适合按量扣款**——可作为套餐的"包含额度"（软上限），不单独计费 |
| `download`（导出流量） | ⛔ **不收** | ✅ 口径 A 自己都标注"**预留，当前无埋点**"（`billing_pricing.py:19`、`scan_billing.py:530`）。没有数据的事不做 |

**"份"的定义**（与现存语义对齐，避免第二套口径）：
✅ `grading_stats.py:27-31` 的 `get_stat_student_key` 把 `张三_1.jpg / 张三_2.jpg` 归为同一学生「张三」；`record_graded_state_change`（`:294-325`）按**学生维度**做增量。
⇒ 口径 B 的 1 份 = **（用户, 文件夹, 学生）三元组的"已批改"状态发生 0→1 跃迁**。与口径 A 的批改计数**同源**，但**不同表、不同写路径**（§7.1）。

⚠️ 单价数值（每一份多少钱 / 有没有免费额度 / 免费额度多少）＝ **① 类未拍项**，见 §10 Q4。本设计的账本**不依赖具体数值**。

> ⚠️ **已订正（2026-09-24）**：上一行的"**单价数值**＝ ① 类未拍项"**已部分消解** —— 主导者拍定 **Q4 定价 = 0.5 元 / 份**，且**逐字澄清**：用户说的「**一页**」**就是**本节的「**份**」（即上面这条三元组 0→1 跃迁的定义）⇒ `backend/app/services/payment/pricing.py` 的兜底价 **50 分零改动**。⚠️ 上一行中的**免费额度**部分**仍未拍**（本次答复未给）。逐条订正见 **§10「✅ 已拍定（2026-09-24，主导者 CC）」**。

### 3.2 表结构（新增 3 张；命名沿用本仓习惯）

✅ 本仓既有约定（实测）：表名复数蛇形、主键 `id VARCHAR(36)`（UUID）、`created_at/updated_at = DateTime(timezone=True) server_default=func.now()`、索引前缀 `uk_` / `idx_` / `uq_`。范例：`backend/app/models/grading_daily_stat.py:14-30`、`credit_account.py:8-20`。
✅ 本仓**已有账本范式**可直接照抄结构（但**不是**可直接复用的表）：`credit_accounts`（账户：`balance` / `total_earned` / `total_spent`，`credit_account.py:14-20`）+ `credit_transactions`（**只追加、无 `updated_at`**，含 `amount` / `balance_after` / `source_type` / `source_id` / `operator_id` / `description`，`credit_transaction.py:8-24`）。
⇒ 该范式与 §3.3 的不变量高度一致，**照抄结构 = 复用仓库习惯**；但⛔ **绝不复用这两张表**（它们是学生积分，subject 是 `students.id`，与老师钱包无关）。

**表 1 `payment_accounts`（老师钱包账户，一师一行）**

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | VARCHAR(36) | PK | UUID |
| `user_id` | VARCHAR(36) | NOT NULL, FK `users.id` ON DELETE CASCADE | 老师账号 |
| `balance_fen` | INT | NOT NULL, DEFAULT 0 | **余额，单位：分**（整数，不用浮点） |
| `total_recharged_fen` | INT | NOT NULL, DEFAULT 0 | 累计充值（对账用） |
| `total_consumed_fen` | INT | NOT NULL, DEFAULT 0 | 累计消费 |
| `status` | VARCHAR(16) | NOT NULL, DEFAULT 'active' | `active` \| `suspended`（风控冻结） |
| `created_at` / `updated_at` | DATETIME | 同仓约定 | |

`UNIQUE KEY uk_payment_account_user (user_id)`　`KEY idx_payment_account_status (status)`

**表 2 `usage_events`（用量事件流，**只增不改**）**

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | VARCHAR(36) | PK | UUID |
| `user_id` | VARCHAR(36) | NOT NULL, FK `users.id` | 用量归属 |
| `kind` | VARCHAR(32) | NOT NULL | `grade` \| `upload`（计价项） |
| `folder_safe` | VARCHAR(255) | NOT NULL | 与 `grading_daily_stats.folder_safe` 同源 |
| `subject_key` | VARCHAR(255) | NOT NULL | 学生 key（`grading_stats.get_stat_student_key` 的产物） |
| `delta` | SMALLINT | NOT NULL | `+1`（产生）/ `-1`（冲正） |
| `event_uid` | VARCHAR(64) | NOT NULL | 上游事件的稳定标识 |
| `occurred_at` | DATETIME | NOT NULL | 业务发生时刻（UTC） |
| `created_at` | DATETIME | 同仓约定 | 落库时刻 |

`UNIQUE KEY uk_usage_event_uid (event_uid)`　`KEY idx_usage_event_user_kind_time (user_id, kind, occurred_at)`
`KEY idx_usage_event_business (user_id, kind, folder_safe, subject_key)`

**表 3 `ledger_entries`（资金流水，**只增不改，无 `updated_at`** —— 与 `credit_transactions` 一致）**

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | VARCHAR(36) | PK | UUID |
| `account_id` | VARCHAR(36) | NOT NULL, FK `payment_accounts.id` | |
| `entry_type` | VARCHAR(32) | NOT NULL | `recharge` \| `consume` \| `refund` \| `grant` \| `expire` \| `adjust` |
| `amount_fen` | INT | NOT NULL | **有符号**：充值/授予 = 正，消费 = 负，冲正 = 正 |
| `balance_after_fen` | INT | NOT NULL | 记账后余额快照（**可复算**，见 §3.3 I3） |
| `idempotency_key` | VARCHAR(191) | NOT NULL | **幂等键**，唯一索引 |
| `usage_event_id` | VARCHAR(36) | NULL, FK `usage_events.id` | 消费分录指向用量事件 |
| `order_id` | VARCHAR(36) | NULL | 充值分录指向订单 |
| `operator_id` | VARCHAR(36) | NULL, FK `users.id` ON DELETE RESTRICT | 人工调整的操作者 |
| `description` | VARCHAR(512) | NULL | 人类可读理由（**冲正必填**） |
| `created_at` | DATETIME | 同仓约定 | 记账时刻 |

`UNIQUE KEY uk_ledger_idempotency (idempotency_key)`　`KEY idx_ledger_account_time (account_id, created_at)`
`KEY idx_ledger_type_time (entry_type, created_at)`（对账用，§6）

> `idempotency_key` 长度取 191：✅ MySQL 8 + utf8mb4 下唯一索引键长上限 3072 字节（单列 3072/4=768），191 是**安全余量**的惯例值，也兼容未来可能的 `utf8mb3` 索引前缀限制。

### 3.3 不变量（这是账本的宪法，实现批必须逐条写用例）

| # | 不变量 | 强制手段 | 违反时的表现 |
|---|--------|---------|-------------|
| **I1** | **同一笔用量不能扣两次** | `ledger_entries.uk_ledger_idempotency` **唯一索引**（数据库层，不靠应用层 `if`） | 重复回调/重试 → 唯一键冲突 → 被当作"已处理"丢弃，**不报错** |
| **I2** | **余额不可为负** | 写路径在**同一事务**内 `SELECT ... FOR UPDATE` 锁账户行后校验 `balance_fen + amount_fen >= 0`，否则拒绝 | 余额被扣穿；后续老师看到负数 |
| **I3** | **每笔变动可追溯、余额可复算** | 每行落 `balance_after_fen`；恒等式：`SUM(amount_fen) == payment_accounts.balance_fen`，且**最新一行的 `balance_after_fen` == 账户余额** | 账实不符，对账断裂 |
| **I4** | **流水只增不改** | 应用层**禁止**对 `ledger_entries` 做 UPDATE/DELETE；不设 `updated_at`（照抄 `credit_transaction.py:1` 的"只追加账本"做法） | 历史被篡改，无法审计 |
| **I5** | **冲正 = 反向分录，绝不就地改数** | 例：批改撤销 → 插一条 `entry_type='consume'` 但 `amount_fen > 0` 的反向分录，`description='冲正：<原分录 id>'` | 与 I4 冲突的"聪明实现" |
| **I6** | **口径 A 的用量变动不直接改账本** | `grading_stats.py` 的任何 `*_decrement`（`:186-265`）**不得**直接写账本；账本只认 `usage_events` 的 `delta` | 一次 `remove_folder_stats` 抹掉全部历史账 |

### 3.4 并发扣减：行锁，不用乐观锁

**选型：`SELECT ... FOR UPDATE`（MySQL InnoDB 行锁）**（③ 类技术判断，理由如下）：

1. **本仓现状**：全仓没有任何乐观锁 version 列（实测 `models/*.py` 未见），引入 version 等于**新造一套并发范式**（七级阶梯第 ② 级的反面）。
2. **本仓已有同类做法**：`credit_accounts` + `credit_transactions` 就是"账户行 + 只增流水 + `balance_after`"，说明团队已接受这个范式。
3. **竞争度**：锁粒度是**单个老师的账户行**，同一老师的并发扣费几乎只发生在"同时开两个批改任务"这种低频场景 ⇒ **行锁的代价可忽略**。
4. **正确性**：行锁天然序列化"读余额→校验非负→写流水→更新余额"，无需重试逻辑。

**必须与 I1 配对**：行锁解决"同一老师并发"，唯一索引解决"同一事件重复投递/重试"。两者**缺一不可**——只有行锁挡不住"回调重放"（重放是串行的，锁不住）。

**伪代码（示意，本批不实现）**：
```
with db.begin():                                   # 单事务
    acct = SELECT * FROM payment_accounts
           WHERE user_id = :uid FOR UPDATE          # ← 行锁
    if acct.balance_fen + amount_fen < 0:
        raise InsufficientBalance                 # ← I2
    INSERT INTO ledger_entries(
        idempotency_key=:key, amount_fen=:amt,
        balance_after_fen=acct.balance_fen+amt, ...)   # ← I1 由唯一索引兜底
    UPDATE payment_accounts
       SET balance_fen = balance_fen + :amt,
           total_consumed_fen = total_consumed_fen + (-:amt if amt<0 else 0)
     WHERE id = acct.id
```
捕获 `IntegrityError` on `uk_ledger_idempotency` ⇒ 视为**已处理**，返回既有分录（幂等语义，不抛错）。

### 3.5 幂等键的构造（本设计最容易做错的一处）

**目标**：① 同一次操作重试不重复扣；② 老师"删了再改、改了再删"的振荡要能**正确回退**且不重复。

**反例（不要这么做）**：幂等键取"事件 id/时间戳"。重试会产生新时间戳 ⇒ 每次重试都扣一次。
**反例 2**：幂等键取 `(user, folder, student)` ⇒ 第二次"删除后又批改"会与第一次撞键被吞掉 ⇒ **少扣**。

**本设计采用"业务键 + 净额"组合键（`net-diff` 记账法）**：

1. `usage_events` 只增记录**状态跃迁**：`delta=+1`（0→1）/ `delta=-1`（1→0），`event_uid` 由上游稳定标识（见 §7.1）保证**同一次跃迁重复投递只落一行**。
2. 记账时对同一 `business_key = (user_id, kind, folder_safe, subject_key)` **原子求净额**：
   `net_now = SELECT SUM(delta) FROM usage_events WHERE business_key = :bk`
3. 只在 **净额发生变化**时产生分录，且：
   **`idempotency_key = f"{business_key}|net={net_now}"`**
4. 于是：重复投递同一状态 ⇒ 净额不变 ⇒ 无新键 ⇒ 无新分录（**幂等** ✅）；删除 ⇒ 净额 0 ⇒ 键 `…|net=0` ⇒ 产生**待冲正**；再批改 ⇒ 净额 1 ⇒ 键 `…|net=1` **与第一次不同** ⇒ 会扣第二次（**正确** ✅）。

> 副作用说明：`net=0` 的偶数次振荡不需要"撤销再重扣"两条分录——只需让**未结清量**回到 0。实现时把 `net` 理解成"当前应计份数"，分录键即"应计份数快照"，差额 = 新分录金额。**这条要写清楚，否则实现批会做成"事件驱动扣款"而漏掉振荡。**

---

## §4 扣费时点与口径

### 4.1 时点：**前置闸门 + 成功后扣 + 反向冲正**（不做冻结）

| 方案 | 评估 | 结论 |
|------|------|------|
| A. 请求前**冻结**（预授权）+ 成功后结算 + 失败退回 | 需要两阶段状态、超时释放、释放任务的幂等……为一个"单次几分钱"的扣费引入分布式事务式复杂度 | ⛔ **不采用** |
| B. **前置闸门 + 成功后扣** | 余额/额度不足 ⇒ **拒绝发起**（学生看不到"批改失败但扣了钱"）；成功后按 §3.5 幂等键扣；失败/撤销 ⇒ 反向分录 | ✅ **采用** |

**前置闸门的具体判据**（放在批改请求入口）：
`可服务余额 = payment_accounts.balance_fen + 套餐剩余额度折算值`
若 `<= 0` ⇒ 返回 `402`（见 §7.3）+ 明确中文提示"余额/额度已用完，请充值或续订"。
⚠️ 闸门只挡"**发起新批改**"，**绝不**中途打断已在跑的批改（老师已上传 40 张卷子，不能扣到一半报错）。

**为什么不做冻结**（七级阶梯：不加没人要的复杂度）：批改耗时但金额小；冻结带来的"超时释放 → 释放失败 → 幽灵冻结"故障模式，代价高于它防的"少量欠费"风险。**代价用"闸门阈值"换**：余额接近 0 时前端提前告警（§9 Phase 0）。

### 4.2 「量」的口径（复核 §3.1）

- **主项**：`kind='grade'`，单位 = **学生·份**，语义 = 0→1 跃迁（与 `grading_stats.py:294-325` 同源）
- **次项**：`kind='upload'`，**默认关闭**（配置可开）
- ⛔ **不含 storage / download**（理由见 §3.1 表）

### 4.3 幂等（三层，任一层单独都够，三层互为兜底）

| 层 | 机制 | 防的是 |
|----|------|--------|
| L1 事件层 | `usage_events.uk_usage_event_uid` | 同一跃迁被重复投递 |
| L2 记账层 | `ledger_entries.uk_ledger_idempotency`（`business_key|net=N`） | 同一净额被重复记账 |
| L3 事务层 | 行锁 + 单事务 | 并发下的读改写竞态 |

---

## §5 订阅套餐模型

### 5.1 套餐定义（新增 2 张表）

**表 4 `payment_plans`（套餐定义，配置型数据）**

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | VARCHAR(36) | PK | |
| `code` | VARCHAR(64) | NOT NULL, UNIQUE | 如 `indie_basic_monthly` |
| `name` | VARCHAR(128) | NOT NULL | 展示名 |
| `price_fen` | INT | NOT NULL | 售价（分） |
| `period_unit` | VARCHAR(16) | NOT NULL | `month` \| `quarter` \| `year` |
| `period_count` | INT | NOT NULL, DEFAULT 1 | 周期数 |
| `included_grade_quota` | INT | NOT NULL, DEFAULT 0 | 周期内包含的**批改份数** |
| `overage_policy` | VARCHAR(16) | NOT NULL, DEFAULT 'wallet' | 超额处置：`wallet`（转余额按量）\| `block`（停止服务） |
| `is_active` | TINYINT(1) | NOT NULL, DEFAULT 1 | 下架标记（不物理删，保护历史订阅） |
| `created_at` / `updated_at` | DATETIME | | |

`UNIQUE KEY uk_plan_code (code)`

**表 5 `subscriptions`（订阅，一师同时最多 1 个生效）**

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | VARCHAR(36) | PK | |
| `user_id` | VARCHAR(36) | NOT NULL, FK `users.id` | |
| `plan_id` | VARCHAR(36) | NOT NULL, FK `payment_plans.id` | |
| `status` | VARCHAR(16) | NOT NULL | `active` \| `expired` \| `cancelled` \| `refunded` |
| `period_start` | DATETIME | NOT NULL | 本周期起（UTC） |
| `period_end` | DATETIME | NOT NULL | 本周期止（**独占**边界：`[start, end)`） |
| `included_grade_quota` | INT | NOT NULL | **下单时快照**套餐额度（套餐改价/改额度不影响已购订阅） |
| `cancel_at` | DATETIME | NULL | 预约到期不续 |
| `source_order_id` | VARCHAR(36) | NULL | 由哪笔订单开通（人工开通时为空） |
| `created_at` / `updated_at` | DATETIME | | |

`KEY idx_subscription_user_status (user_id, status)`　`KEY idx_subscription_period_end (period_end)`（到期扫描用）

> **额度用量不落表**：`已在周期内消耗的份数 = COUNT/SUM(usage_events WHERE user_id=? AND kind='grade' AND occurred_at ∈ [period_start, period_end))`。
> 理由：额度用量是 `usage_events` 的**投影**，落第二张表必然与事件流分叉（七级阶梯：不加冗余状态）。⚠️ 前提是 `usage_events` 的 `occurred_at` 不可变（它只增不改，✅ 满足）。

### 5.2 生命周期（生效 / 续期 / 过期 / 退款）

```
          下单支付成功           到期日到
 (无) ─────────────────► active ────────► [续期成功 → active(新周期)]
                          │                └─► [未续期 → expired]
                          │
                          └─ 退款 → refunded（周期内剩余权益作废，见下）
```

| 状态 | 触发 | 对服务的影响 |
|------|------|-------------|
| `active` | 支付成功回调 / 后台人工开通 | 额度抵扣优先于余额 |
| `expired` | `period_end` 到期且未续期 | 额度不再抵扣；**服务不中断**，转为纯余额按量（余额为 0 才被闸门拒）⇒ 避免"到期即停课"的恶体验 |
| `cancelled` | 老师主动停止续费（`cancel_at` 到期） | 同 `expired`，但语义是"不愿续" |
| `refunded` | 通道退款成功 | 同 `expired`；**已消耗的额度不退**（按量已发生），只退未消耗部分（**金额口径 = ① 类，见 §10 Q3**） |

> ⚠️ **已订正（2026-09-24）**（针对上表 `refunded` 行）：退款规则**已拍**（§10 Q5）= **余额不可退；只退套餐未使用部分** ⇒ 该行"只退未消耗部分"**与该口径一致、无需改**；但**具体金额公式（按比例 / 按剩余份数）仍未拍**，故该行"金额口径 = ① 类"**仍成立**。⚠️ 另注：该行原引"见 §10 **Q3**"，从上下文看**应为 §10 Q5**（Q3 是"是否开票"）—— 本席**未删改原文**，仅在此标注该疑点，**请主导者裁**。

**过期扫描**：复用本仓**已有的常驻任务范式**——`app/main.py:69-106` 的 `AUTO_TODO_NOTIFY_ENABLED` 后台 `asyncio` 循环（自带 `app.state.todo_wakeup` 唤醒事件与 `max_sleep`）。⛔ **不新建调度框架**（七级阶梯：平台原生/已有特性优先）。建议**不新增常驻循环**，而是在**读路径惰性判定**（查订阅时若 `period_end <= now` 则落 `expired`），避免多一个后台任务；到期提醒若有需要，挂到已有 todo 循环里。

### 5.3 套餐额度与按量扣的**关系**：串行，套餐优先

**抵扣顺序（口径 B，⛔ 与口径 A 的 `free_quota → resource_pack → tiered_price` 无关）：**

```
① 本周期套餐剩余额度   ──有──►  扣额度（不产生 ledger_entries，只产生 usage_events）
                       ──无──►  ②
② 预充值余额            ──有──►  扣余额（产生 ledger_entries: consume）
                       ──无──►  ③
③ 闸门拒绝（402），提示充值/续订
```

**关键设计判断：套餐内消耗是否产生 `ledger_entries`？**
⇒ **不产生。** 只在 `usage_events` 里留痕。理由：`ledger_entries` 是**资金**流水，套餐额度是**权益**消耗，混进去会破坏 §3.3 I3（`SUM(amount_fen) == balance_fen`）——权益消耗没有对应的资金变动。
⇒ **"超额转按量"是天然结果**：额度用完时，抵扣顺序自动落到 ②。

⚠️ **`overage_policy='block'`**（额度用完即停）作为一种套餐形态保留，但**默认是 `wallet`**（超额转余额）。是否提供 `block` 形态 = **① 类**，见 §10 Q4。

---

## §6 对账与冲突

### 6.1 三本账

| 账 | 数据源 | 谁维护 | 时点 |
|----|--------|--------|------|
| **A. 老师视角余额/账单** | `payment_accounts.balance_fen` + `ledger_entries` + `usage_events` | 本系统 | 实时 |
| **B. 平台实际收入** | `payment_orders`（已支付）+ `ledger_entries(entry_type IN ('recharge','grant'))` | 本系统 | 支付确认时 |
| **C. 通道流水** | 通道对账单（下载文件 / 查询 API）——**格式 = ① 类** | 通道 | 日/月 |

### 6.2 对账口径与恒等式

| 等式 | 内容 | 频率 |
|------|------|------|
| **E1（内部自洽）** | `SUM(ledger_entries.amount_fen) == payment_accounts.balance_fen`，逐账户 | 每次记账后（生产上可每日全量巡检） |
| **E2（收入一致）** | `SUM(ledger_entries WHERE entry_type='recharge') == SUM(payment_orders WHERE status='paid')`（减去退款、手续费口径见下） | 每日 |
| **E3（通道一致）** | 我方 `payment_orders`（`status='paid'`，按 `channel_trade_no` 聚合）↔ 通道对账单逐笔 | 每日/每结算周期 |
| **E4（用量一致）** | `SUM(usage_events.delta) WHERE kind='grade'` ↔ `SUM(grading_daily_stats.grade_count)`（口径 A）**允许差异**（口径 A 会因 `remove_folder_stats` 归零，口径 B 不会） | 每周巡检，**差异只登记不报警** |

**E4 的存在本身就是"两个口径必须分层"的证明**：两条线**注定不等**，若强行合并，对账将永久不平。

### 6.3 差异分类与处置（实现批必须有这张表）

| 差异类型 | 典型场景 | 处置 |
|---------|---------|------|
| **D1 通道有、我方无** | 回调丢失、验签失败被丢弃 | 由对账文件**补单**（幂等入口 `apply_payment_confirmed` 直接调用，§2.3 保证安全） |
| **D2 我方有、通道无** | 伪造回调、重复回调、测试单 | 人工核查；**不自动冲销**（防被伪造回调打成负账） |
| **D3 金额不符** | 优惠/手续费被算进支付金额 | 以**通道实收**入账，差额落 `entry_type='adjust'` 并记 `description` |
| **D4 手续费** | 通道费率（`capabilities().fee_rate_bps`，§2.2） | ⚠️ **手续费不影响老师余额**；它是**平台成本**，属口径 A 的领域（或另起 `platform_fee_entries`）。❓ 手续费由谁承担 = **① 类**，见 §10 Q1 |
| **D5 退款** | 老师申请退款 | 反向走 adapter `create_refund`；成功后落 `entry_type='refund'`（负额），⛔ **不得**删改原 `recharge` 分录（I4/I5） |

### 6.4 对账的落地形态

⛔ **不新建对账脚本/常驻服务**（归队验收判据："为证明某一次改动而写一个专用门禁脚本，是增生源不是验收"）。
✅ **对账 = 一条只读 SQL + 一份可复算的报告**，挂在已有的后台能力上（如 `admin` 侧只读端点，或直接手工 SQL）。E1/E2 是纯 SQL，无需代码。


### 6.5 E3 的落点（订正 2026-09-24）

**本节只做一件事：把 §6 与 §13 里对不上的三处原文摆在一起，给出本阶段的裁定与将来落点的前提。**
⛔ 本节**不删改上文任何一个字**（就地追加标记，照本批既有纪律）。

**原文矛盾（行号 = 本节插入前的版本；插入后 §6.4 之后的全部行号整体后移，见 §14 v1.3）**

- **§6.2 L461** 要求 **E3（通道一致）**：「我方 `payment_orders`（`status='paid'`，按 `channel_trade_no` 聚合）↔ 通道对账单逐笔」，频率「每日/每结算周期」⇒ 它**必须有真实对账单 + 逐笔匹配键**。
- **§6.4 L476〜479**：L478 逐字「⛔ **不新建对账脚本/常驻服务**」；L479 逐字「✅ **对账 = 一条只读 SQL + 一份可复算的报告**，挂在已有的后台能力上……**E1/E2 是纯 SQL，无需代码**」⇒ 这个「纯 SQL」的口**只开给 E1/E2**，**E3 没有落点** —— E3 天然是「文件 ↔ 库」的逐笔比对，不是一条 SQL。
- **§13 L806**（自我约束声明第 4 条）逐字：「⛔ **不新建调度框架、不新增常驻脚本、不新增门禁**（对账用纯 SQL；过期用惰性判定……）」⇒ L461 要的「每日」在这个约束下**没有任何执行者**（没有常驻服务，就没有"每日"）。

⇒ 三处并存的结果：**E3 被要求（L461）、又被排除（L478/L806）、且没有任何合法形态（L479 的纯 SQL 口只覆盖 E1/E2）**。

**本阶段裁定：E3 不落地。** 三条理由：

1. **无商户号 ⇒ 拿不到真实对账单 ⇒ 解析器写了也无法验证。** 「通道对账单」是 **① 类**外部真值（字段集/编码/分隔随通道而异），本阶段取不到样本 ⇒ 写出来的解析器**没有一条能判红的用例**（判据必须有自己的红，否则是假绿）。
2. **设计稿自相矛盾**（上列三处）——按 L478/L806，E3 既不能做成脚本、也不能做成常驻服务；按 L479，纯 SQL 的口只开给 E1/E2 ⇒ **E3 在当前约束下没有合法载体**，实现它必然先破一条已拍约束。
3. **D1 补单没有入口**（§6.3 L470「由对账文件**补单**（幂等入口 `apply_payment_confirmed` 直接调用）」）：补单要写库，而 admin **写**端点不在本批范围（`routers/payment.py:16`）⇒ 即便 E3 跑出差异，**处置动作也没有入口**，做出来的只是一张"看得见、动不了"的差异表。

**本阶段实际落地的（§6.4 允许的那一半）**：E1/E2 已挂成**只读**端点
`GET /api/v1/payment/admin/reconciliation`（管理员鉴权；E1 复用 `services/payment/ledger.py::verify_invariant_e1()`，⛔ 未重写判据；E2 = §6.2 L460 的纯 SQL）。⛔ 该响应里**不含** E3 字段 —— 没落地的等式不许长成一个看着"已经在跑"的字段。

**将来落点的三个前提（缺一不可；三条都属 ① 类，需主导者裁定）**：

1. **商户号开通、能取到真实对账单**（至少一份真实样本，含 `channel_trade_no`）—— 否则 E3 的判据写不出自己的红。
2. **§13 L806「不新增调度框架/常驻脚本」是否给对账开例外**：要么明确开例外（允许一个常驻/定时对账），要么改走手工路径（见下）。
3. **D1 补单入口放行**：admin 写端点，或明确「手工 SQL 补单」为唯一路径。⛔ 没有它，E3 的差异无从处置。

**两条路的代价（各一句；⛔ 本席不拍自动还是手工，留给主导者）**：

- **自动路**：常驻/定时任务定期拉对账单 → 落差异表 → 自动调补单 ⇒ 实时性最好，但要**破 §13 L806 的「不新增常驻脚本」**，并新增调度框架与差异表两项维护成本。
- **手工路**：人工下载对账单 → 一次性核对 → 差异抄进工单 ⇒ **不破任何已拍约束**（正合 §6.4 L478/L479 的口径），代价是**触发靠人工**、L461 的「每日」实际降级为「每结算周期或按需」。

---

## §7 与现有代码的接缝

### 7.1 计量写入（**唯一最关键的新增接缝**）

**现状**：所有用量走 `backend/app/grading/grading_stats.py` 的**单一漏斗**（✅ `scan_billing.py:11-12` 自述"由 app/grading/grading_stats.py 在批改主流程旁路累加"）：`record_upload`（`:167`）/ `record_grade`（`:182`）/ `record_graded_state_change`（`:294`）/ 各 `*_decrement`（`:186-265`）。

**接缝方案：新增** `app/services/payment/metering.py`，提供 `emit_usage_event(...)`，由 `grading_stats.py` 在**同一处调用点**旁路调用。

⛔ **禁忌（本节最重要的一条）**：**不要把 `emit_usage_event` 塞进 `grading_stats._increment` 的 `try` 块内**。
理由：`_increment` 的异常被吞（`grading_stats.py:161-162`），`record_graded_state_change` 整个包 `try/except: pass`（`:324-325`，注意 `:304` 的 `try` 与 `:325` 的 `pass`）。**计费事件被静默吞掉 = 静默少收钱**。
⇒ 计量写入必须走**自己的 session + 自己的异常处理**（失败要 `logging.error` + 不阻塞批改主流程，但要**留痕**）。

**`event_uid`（§3.5 需要"上游事件的稳定标识"）的构造**：取业务状态跃迁的稳定指纹，如
`sha1(f"{user_id}|grade|{folder_safe}|{subject_key}|{delta_sign}")`
配合 §3.5 的"净额记账法"，同一次跃迁重复投递 ⇒ 同 `event_uid` ⇒ 被 `uk_usage_event_uid` 吞掉 ⇒ 幂等。

### 7.2 需要新增/改动的文件清单

| 类型 | 路径 | 动作 |
|------|------|------|
| 新增 | `backend/app/models/payment_account.py` | `PaymentAccount` |
| 新增 | `backend/app/models/usage_event.py` | `UsageEvent` |
| 新增 | `backend/app/models/ledger_entry.py` | `LedgerEntry` |
| 新增 | `backend/app/models/payment_plan.py` | `PaymentPlan` |
| 新增 | `backend/app/models/subscription.py` | `Subscription` |
| 新增 | `backend/app/models/payment_order.py` | `PaymentOrder`（§8 之后） |
| **改** | `backend/app/models/__init__.py` | 加 import（`:1-87` 区）+ `__all__`（`:89-172` 区） |
| **改** | `backend/app/database.py` | ① `sync_database_schema` 的模型 import 列表（`:87-158`）加支付模型；② 新增 `_ensure_payment_tables()` 并挂到 `init_db()`（`:65-76`）与 `sync_database_schema()`（`:159-176`），**照抄 `_ensure_flow_tables`（`:221-249`）的幂等建表范式** |
| 新增 | `backend/app/services/payment/ledger.py` | 账户/流水/幂等核心（§3） |
| 新增 | `backend/app/services/payment/metering.py` | 用量事件（§7.1） |
| 新增 | `backend/app/services/payment/subscription.py` | 套餐与抵扣顺序（§5） |
| 新增 | `backend/app/services/payment/pricing.py` | 口径 B 价格表（**复用** `billing_pricing.tiered_price`，§1.4） |
| 新增 | `backend/app/services/payment/channels/` | 通道适配层（§2） |
| **改** | `backend/app/grading/grading_stats.py` | 在 4 个调用点旁路 `emit_usage_event`（⛔ 不进 `try` 吞异常区） |
| 新增 | `backend/app/routers/payment.py` | 路由（§7.3） |
| **改** | `backend/app/main.py` | 在 `:289-290`（scan_billing 挂载点）附近 `app.include_router(payment.router, prefix="/api/v1")` |
| 新增 | `backend/app/schemas/payment.py` | 请求/响应模型 |
| 新增 | `backend/payment_pricing.example.json` | 口径 B 价格表样例（**与 `billing_config.example.json` 并列，⛔ 不合并**） |
| 新增 | `frontend/src/services/paymentApi.ts` | 客户端（照抄 `services/scanBillingApi.ts` 的 `request()` 范式，`:1`） |
| 新增 | `frontend/src/components/payment/*` | 余额/账单/套餐页面 |
| **改** | `frontend/src/components/Sidebar.tsx` | ① `NAV_ITEMS`（`:76-270`，可扩展 `:261-269` 的 `system-ops` 组或新增组）；② `NAV_SECTIONS`（`:279-316`，必须同步，否则新组不显示） |
| **改** | `frontend/src/constants/systemRoles.ts` | `TEACHER_NAV_WHITELIST`（`:34-67`）加入新 nav id |

> ⚠️ **改导航要动三处**（`NAV_ITEMS` + `NAV_SECTIONS` + `TEACHER_NAV_WHITELIST`），漏一处表现为"白名单放行了但侧边栏不渲染"或反之。这是本仓的一个**隐性接缝**，实现批必须知道。

### 7.3 后端路由（口径 B 命名空间，与口径 A 物理分离）

新增 `app/routers/payment.py`，`prefix="/payment"`，挂到 `/api/v1`：

| 方法 | 路径 | 用途 | 闸门 |
|------|------|------|------|
| `GET` | `/api/v1/payment/account` | 我的余额（分）+ 状态 | 登录 |
| `GET` | `/api/v1/payment/ledger` | 我的资金流水（分页） | 登录 |
| `GET` | `/api/v1/payment/usage` | 我的用量（**口径 B**，非口径 A） | 登录 |
| `GET` | `/api/v1/payment/plans` | 可购套餐列表 | 登录 |
| `GET` | `/api/v1/payment/subscription` | 我的订阅与剩余额度 | 登录 |
| `POST` | `/api/v1/payment/orders` | 下单（返回通道支付参数） | 登录（**Phase 2**，依赖 §2） |
| `POST` | `/api/v1/payment/callback/{channel}` | 通道回调 | **签名校验**（Phase 2） |
| `POST` | `/api/v1/payment/admin/grant` | 后台人工开通/调整 | 仅管理员 |

⛔ **`scan_billing.py` 的 9 个只读端点一个都不改。** 理由：它们是口径 A 的权威投影，任何"接到账本上"的改动都会让两个口径在同一个端点里分叉。**并存方式 = 两套端点、两套数据源**，前端用**位置与标签**区分（§1.5）。

⚠️ 响应格式：✅ 本仓统一 `ApiResponse{code:int=0, message:str, data:T}`（`backend/app/schemas/common.py:8-11`），错误走 FastAPI 的 `HTTPException(detail=...)` → `{"detail": "..."}`，前端在 `frontend/src/services/api.ts:57-67` 读 `errorBody.detail`。
⇒ ⛔ **不要**引入 `{error, message}` 风格（本仓不存在这套）。新增错误码建议：`402`（余额/额度不足，闸门拒绝）、`409`（订单已处理）、`501`（通道未配置）。

### 7.4 前端页面落点

- ✅ 已有页面容器：`frontend/src/components/scan-billing/`（`ScanConsumptionPage.tsx`、`UsageSummaryPage.tsx`），在 `frontend/src/pages/Index.tsx:143-153` 以 `lazy()` 挂载。
- ✅ 白名单已放行两个 id：`systemRoles.ts:65-66` 的 `scan-consumption` / `usage-summary`。
- 新增支付页建议**新建独立目录** `frontend/src/components/payment/`，在 `Index.tsx` 同样 `lazy()` 挂载，并新增 nav id（如 `payment-wallet`），**同时**加进 `TEACHER_NAV_WHITELIST`。
- ⚠️ 前端 API 前缀机制：`frontend/src/config/api.ts:12-13` 的 `API_PREFIX = API_BASE_URL + "/api/v1"`，打包时 `VITE_USE_RELATIVE_API=true` ⇒ 走同源相对路径。⇒ 新客户端写 `request("/payment/account")`（`request` 已含前缀，见 `services/api.ts:51`），**⛔ 不要自己拼 `/api/v1`**。
- ✅ **灰度开关免费**：`NavChild.featureKey`（`Sidebar.tsx:66`）+ 过滤逻辑（`Sidebar.tsx:388-389`）+ `useFeatureFlags` 已经能按学校隐藏入口。⚠️ 已知限制：现有过滤是 `!child.featureKey || !disabledFeatureKeys.has(child.featureKey)`，即 `disabledFeatureKeys` 来自**全校**开关；独立老师是"无学校"账号（不绑班、无 school）⇒ **需要确认 feature flag 对无学校账号的返回语义**（本席未验证 `useFeatureFlags` 对无 school 用户的行为，列为实现批的前置检查）。
- ✅ **角色闸的唯一权威判据在 `frontend/src/lib/adminAccess.ts`**（⛔ 别在 `Sidebar.tsx` 里另建第二份谓词，那里 `:380` 的注释已明令）：
  - 侧栏：`isNavItemVisible(user, item)` — `lib/adminAccess.ts:52-64`，由 `Sidebar.tsx:388` 调用
  - 深链（手输 `/nav/:navId`）：`isNavPageAllowed(user, navId)` — `lib/adminAccess.ts:71-77`
  - 两者**都**读同一个白名单 `TEACHER_NAV_WHITELIST`（`systemRoles.ts:34-67`）⇒ **新增 nav id 只改白名单一处即可**，侧栏与深链同时放行；⛔ 不要在两处各加一份判断。

---

## §8 迁移与灰度

### 8.1 存量老师：**不需要迁移**

✅ 本批独立老师是通过 `/api/v1/auth/register` 自助注册的**全新账号**：`backend/app/schemas/auth.py:15` 的 `RegisterRole = Literal["任课教师"]` 是唯一注册闸门；✅ 注册后**不绑定任何班级**（`routers/auth.py:85-93` 的注释明确"不再挑选演示班（原 `_pick_demo_class` / `DEMO_CLASS_PREFIX` 已删）"，具体在该注释 `:89-90`）。

⇒ **这批老师全部零用量**，账本是空的，**不存在存量数据迁移**。
⇒ **账户惰性创建**：`get_or_create_account(user_id)`（首个 `usage_events` 或首个充值/订阅时创建）。⛔ 不做一次性 backfill 脚本（没有数据要填）。

### 8.2 校内老师（其他角色）怎么办？

⇒ **先不纳入口径 B。** 理由：① 授权口径（校内老师的费用谁付：学校？老师？）是 **① 类未拍项**；② 现有"独立老师先行，支付后置"的时序口径（背景逐字）支持先做个体。
⇒ 但表结构与服务**按多租户设计**（`user_id` 为键，不假设"有学校"），未来纳入只需放开闸门判定，不改表。
⇒ **闸门判定建议**：`isTeacherOnlyAccount(roles)`（✅ 已存在，`frontend/src/constants/systemRoles.ts:83-88`）作为"是否属于口径 B 适用人群"的**唯一判据**——与导航白名单**同源**，避免第二份口径。⚠️ 后端若也需同一判据，注意 `scan_billing.py:36-53` 已有一份**后端实现**（`_roles_are_teacher_only` / `_is_teacher_only_account`，两处文件顶部注释均声明"与前端同口径"）；实现批应**复用后端这一份**，⛔ 不要再抄第三份。

### 8.3 灰度三阶段

| 阶段 | 行为 | 验收 |
|------|------|------|
| **影子模式** | 只写 `usage_events`，**不扣费、不拒绝服务**；余额恒 0 | `E4`（§6.2）差异率与预估值一致；老师完全无感 |
| **内部白名单** | 对指定几个账号开启真扣费 + 闸门 | 手工跑通"充值 → 批改 → 扣款 → 余额减少 → 流水可查" |
| **全量** | 特征开关按学校/账号放开 | 对账 E1/E2 每日平 |

⚠️ 影子模式**必须能一键回退到"不扣费"**（改配置/开关，不需要回滚代码）。

---

## §9 分期建议（哪些能先开工）

> ⚠️ **已订正（2026-09-24）** —— §10 五条①类已拍定（见 §10 上方「✅ 已拍定（2026-09-24，主导者 CC）」），本节各表**就地**加了订正标记：P2-1/P2-2/P2-3 **已落**（commit `528974c`）、**P3-2 已提前到 Phase 2 落地**、**Phase 1 范围缩减**（套餐后置）、**P2-4 范围缩到"只退套餐未使用部分"**。⛔ 本节原文**一字未删**，只在原地追加标记。
>
> **本节逐项计数（按下列各表逐项数，⛔ 不是估）**：
>
> | Phase | 表内项数 | 已落 | 剩余 | 剩余项的卡点现状（含证据） |
> |-------|---------|------|------|--------------------------|
> | Phase 0 | 9（P0-1〜P0-9） | 8 | **1**（P0-8 影子模式开关） | ⛔ **不卡 ① 类**（Phase 0 本就不需要 §10 任何一项）⇒ 属**待做**、非**待拍**。证据：`backend/app/config.py` 无对应开关项、`backend/app/services/payment/` 全目录（`__init__/ledger/metering/orders/pricing/channels`）无 shadow 命中、`backend/tests/test_payment_p0.py` 无 P0-8 用例 |
> | Phase 1 | 4（P1-1〜P1-4） | 0 | **4** | **整段后置**（Q4b 套餐后置）⇒ 四项验收栏全部依赖套餐/额度/订阅，本阶段无实现对象 |
> | Phase 2 | 5（P2-1〜P2-5） | 3（P2-1/P2-2/P2-3） | **2**（P2-4/P2-5） | P2-4：**可退对象暂不存在**（Q5 ＋ 套餐后置）；P2-5：**对账单格式**（Q2 已定通道，对账单格式**未拍**） |
> | Phase 3 | 3（P3-1〜P3-3） | 1（P3-2） | **2**（P3-1/P3-3） | P3-1：**税率数值 / 专票 vs 普票 / 电子 vs 纸质 仍未拍**；P3-3：手续费承担方（D4）**未拍** |
> | **合计** | **21** | **12** | **9** | — |
>
> ⚠️ "已落"的判据 = 有**载体**（commit / 文件 / 用例），**不是**"看起来做了"；逐项依据见下表各行的就地标记。

> ⚠️ **已订正（2026-09-24，批 6 · commit `3d2beb0`）—— 上表「Phase 3」行已过期**：该行逐字为「3（P3-1〜P3-3） | 1（P3-2） | **2**（P3-1/P3-3）」 ⇒ **订正为 已落 3 / 剩余 0**（P3-1、P3-3 本批已落，载体见下方 Phase 3 的逐行标记）。⛔ 上文原文**一字未删**，订正只写在这里。
>
> **订正后逐 Phase 计数（求和过程写在合计行内）**：
>
> | Phase | 表内项数 | 已落 | 剩余 |
> |-------|---------|------|------|
> | Phase 0 | 9（P0-1〜P0-9） | 8 | 1（P0-8 影子模式开关） |
> | Phase 1 | 4（P1-1〜P1-4） | 0 | 4 |
> | Phase 2 | 5（P2-1〜P2-5） | 3（P2-1/P2-2/P2-3） | 2（P2-4/P2-5） |
> | Phase 3 | 3（P3-1〜P3-3） | **3**（P3-1/P3-2/P3-3） | **0** |
> | **合计** | 9+4+5+3 = **21** | 8+0+3+3 = **14** | 1+4+2+0 = **7** |
>
> ⚠️ **卡点现状列：只有 Phase 3 行变化** —— Phase 0/1/2 三行的卡点现状**照上表原文、未变**；**Phase 3 行 ⇒ 无剩余项**（原文该行的「P3-1：税率数值 / 专票 vs 普票 / 电子 vs 纸质 仍未拍；P3-3：手续费承担方（D4）未拍」**已全部消解**：专票/纸质两项由本批口径落码排除 —— 只开普票、只走电子；手续费承担方**已拍 = 平台承担**）。⚠️ **唯一仍属 ① 类待补的是税率数值与税目** —— 那是**数据**（取值），**不是实现项**，故⛔ **不影响「已落」判定**。
>
> ⚠️ **上表「Phase 2」行加注（本批改动，但该行判定不变）**：Phase 2 **仍为 已落 3 / 剩 2**（⛔ **不改**）。本批落的是 **P2-5 的两部分**：① **设计稿补缝** ＝ 新增 §6.5「E3 的落点（订正 2026-09-24）」（裁定本阶段 E3 不落地；载体 = 本文件 §6.5）；② **E1/E2 只读对账端点** ＝ `GET /api/v1/payment/admin/reconciliation`（载体 = `backend/app/routers/payment.py` 的 `@router.get("/admin/reconciliation")`；E1 复用 `services/payment/ledger.py::verify_invariant_e1()`、⛔ 未重写判据；E2 = 纯 SQL；⛔ 无 E3 字段）。⚠️ 但 **P2-5 的 E3 ⛔ 未落**（§6.5 已有明确的不落地裁定）、「对账单格式」**仍未拍** ⇒ **P2-5 整体未落，Phase 2 行照旧**。

### Phase 0 —— **通道未定即可开工**（不需要 §10 任何一项）

| 工作项 | 可执行定义 | 验收（可判定） |
|--------|-----------|---------------|
| P0-1 表结构与模型 | 6 张表 + `models/__init__.py` 注册 + `database.py` 幂等建表 | 真 MySQL 上 `init_db()` 后 6 张表存在；`AUTO_DDL=false` 时靠 `_ensure_payment_tables` 也能建出（照 `flow_*` 范式） |
| P0-2 账本核心服务 | `credit_accounts/credit_transactions` 范式 + 行锁 + 幂等键 | 用例：① 同键重复记账只落 1 行（I1）② 余额扣穿被拒（I2）③ `SUM(amount)==balance`（I3）④ 并发 10 线程同账户扣费，总额与流水一致（§3.4） |
| P0-3 计量事件 | `emit_usage_event` + 挂进 `grading_stats.py` 4 个调用点 | 用例：批量批改 1 个学生 3 张图 ⇒ 恰 1 条 `usage_events(delta=+1)`；删除该学生 ⇒ 恰 1 条 `delta=-1`；重复投递同一跃迁 ⇒ 无新行 |
| P0-4 net-diff 记账 | §3.5 的 `business_key|net=N` | 用例：批改→删除→再批改 ⇒ **恰好 2 条 consume 分录**、`SUM(amount)` 对应 1 份净额 |
| P0-5 闸门 | 批改入口余额/额度判定 + 402 | 用例：余额 0 + 无套餐 ⇒ 发起批改被拒 402；**已在跑的批改不被中断** |
| P0-6 只读账单投影 | `GET /payment/account|ledger|usage` | 分页、`code/message/data` 格式与全仓一致；错误走 `detail` |
| P0-7 前端余额/账单页 | `components/payment/` + `services/paymentApi.ts` + 三处导航 | 独立老师登录可见余额与流水；校内老师登录**看不到**（白名单生效） |
| P0-8 影子模式开关 | 写事件但不扣/不拒 | 开关置位后老师无感、余额恒 0 |
| P0-9 §1.5 的口径标注 | 标注"扫描消耗/用量汇总 = 平台成本口径" | 页面上有显式文案；老师不会误认为自己的账单 |

### Phase 1 —— **通道未定即可开工**（套餐可后台人工开通，不需要支付）

> ⚠️ **已订正（2026-09-24）**：**Q4b = 套餐后置** ⇒ **本 Phase 范围缩减为「只做预充值余额按量扣」**，订阅套餐推到后面。下表的 **P1-1〜P1-4 全部属套餐**（逐行看验收栏：四项均依赖 `payment_plans` / `subscriptions` / 额度 / `overage_policy`）⇒ **四项整段后置**，本阶段无实现对象（已落 0 / 剩 4）。⛔ 原文保留，未删。**"预充值余额按量扣"侧的载体见 Phase 0**（`payment_accounts` / `ledger_entries` / 402 闸门，已落 `c17ea05`）。

| 工作项 | 验收 |
|--------|------|
| P1-1 `payment_plans` / `subscriptions` + 生命周期 | 后台人工开通套餐 ⇒ 老师看到订阅与剩余额度 |
| P1-2 抵扣顺序（套餐→余额→拒） | 用例：额度 5 份、余额 100 分 ⇒ 前 5 份不产生 `ledger_entries`，第 6 份产生 consume 分录 |
| P1-3 `overage_policy` 两态 | `wallet` 转余额；`block` 到额度即拒 |
| P1-4 惰性过期 | `period_end` 过后首次查询自动落 `expired`，且**服务不中断**（转纯余额） |

### Phase 2 —— **必须等 §10 Q2（通道）拍完**

> ⚠️ **已订正（2026-09-24）**：**Q2 已拍**（微信支付 ＋ 支付宝）⇒ 本 Phase **解锁**。**P2-1 / P2-2 / P2-3 已落**（commit `528974c`）；**P2-4 / P2-5 未落**（P2-4 见下表**下方的逐行订正**；P2-5 的对账单格式**仍未拍**）。已落 3 / 剩 2。
>
> ⚠️ **再订正（2026-09-24，批 6 · commit `3d2beb0`）**：上句「已落 3 / 剩 2」**仍成立、未改**（P2-5 **整体仍未落** —— 其 E3 按 §6.5 不落地）。本批**落了 P2-5 的两部分**：① **补缝** ＝ 新增 **§6.5「E3 的落点（订正 2026-09-24）」**（载体 = 本文件 §6.5）；② **E1/E2 只读对账端点** ＝ **`GET /api/v1/payment/admin/reconciliation`**（载体 = `backend/app/routers/payment.py` 的 `@router.get("/admin/reconciliation")`，E1 复用 `services/payment/ledger.py::verify_invariant_e1()`、⛔ 未重写判据，E2 = 纯 SQL，⛔ 无 E3 字段）。⚠️ 本批落的是 **P2-5 的一部分、不是全部** ⇒ **P2-5 ⛔ 未落**、其「对账单格式」**仍未拍**。

| 工作项 | 被什么卡住 |
|--------|-----------|
| P2-1 `payment_orders` + 下单 | 通道能力（是否有回调、是否需要 payee 主体） |
| P2-2 `channels/*` 实现 + `UnsetChannelAdapter` 替换 | 通道选型 |
| P2-3 回调验签 + `apply_payment_confirmed` 接线 | 通道协议 |
| P2-4 退款流程 | 通道是否支持原路退回 |
| P2-5 对账 E3（通道流水导入/解析） | 对账单格式 |

> ⚠️ **已订正（2026-09-24）逐行**（⛔ 上表原文一字未删，标记写在此处）：
> - **P2-1** ✅ **已落**（commit `528974c`）：`POST /payment/orders`，真 JWT、⛔ 不接 `user_id`、凭据缺失 ⇒ 501 且**零 DB 行**；订单带 `payee_entity_id`（Q1 已拍 ⇒ 本行"是否需要 payee 主体"**已解**）。
> - **P2-2** ✅ **已落**（`528974c`）：`channels/wechat.py` / `alipay.py` / `unset.py`（= Q2 已拍的两条通道 ＋ 「未配置通道」态）；退款与查单如实 `NotImplementedError`（⛔ 不静默假成功）。
> - **P2-3** ✅ **已落**（`528974c`）：`POST /payment/callback/{channel}`，**身份只来自验签**，入账唯一走 `ledger.apply_payment_confirmed`，幂等键 `pay-confirm|<order_id>`。
> - **P2-4** ⚠️ **范围订正**：**只退套餐未使用部分；⛔ 余额不可退**（Q5）。本行"被什么卡住"**已改变** —— Q5 排除了"可退"支 ⇒ **不再**卡"通道是否支持原路退回"；**现行卡点 = 套餐已后置（Q4b）⇒ 可退对象暂不存在**。
> - **P2-5** ⛔ **仍未拍**：对账单格式（本次五条答复未涉及）。

### Phase 3 —— **必须等 §10 Q1/Q3 拍完**

> ⚠️ **已订正（2026-09-24）**：**Q1 / Q3 已拍**（公司主体 / 要开票）⇒ 本 Phase **解锁**；**P3-2 已提前到 Phase 2 落地**。**仍卡**的是：P3-1 的**税率数值 / 专票 vs 普票 / 电子 vs 纸质**（**未拍**）、P3-3 的手续费承担方（D4，**未拍**）。已落 1 / 剩 2。⚠️ **联动**：Q5「余额不可退」**削弱**了红冲（红字发票）场景 ⇒ 本 Phase **变轻**，但"开票与退款的口径耦合"（原文 Q3 末句）**仍须在此定**（范围收窄到"套餐"一处）。
>
> ⚠️ **再订正（2026-09-24，批 6 · commit `3d2beb0`）**：上句「已落 1 / 剩 2」**已过期** ⇒ **订正为 已落 3 / 剩 0**（P3-1、P3-3 本批已落；P3-2 已于 Phase 2 提前落地）。**载体**：`payment_invoices` 表（`backend/app/models/payment_invoice.py`，建表挂 `backend/app/database.py::init_db()` 的**无条件段**）＋ 老师侧 `POST/GET /api/v1/payment/invoices`（`backend/app/routers/payment.py`）＋ 状态机 `requested → issued → void` 的**数据层**（`backend/app/services/payment/invoices.py` 的 `mark_issued` / `mark_void`，⛔ 本批无写路由）＋ 用例 `backend/tests/test_payment_p3.py`。
> ⚠️ **P3-1 的税率数值仍属 ① 类待补**（连同税目）—— 但那是**数据**（取值）、**不是实现项** ⇒ ⛔ **不影响「已落」判定**（本阶段走「老师申请 → 人工开票」，税额**不由本系统算**、⛔ 不硬编）。
> ⚠️ **P3-3 的手续费承担方已拍**（2026-09-24，主导者 CC）= **平台承担**；且**本阶段声明不做红冲**（`void` = **作废**，⛔ 不是红字发票）。⇒ **P3-3 口径已落**（`3d2beb0`）。

| 工作项 | 被什么卡住 |
|--------|-----------|
| P3-1 发票 | 是否开票、开什么票、税率 |
| P3-2 价税分离字段 | 若需开票，金额需拆 `amount_excl_tax` / `tax_amount`（现设计是纯"分"整数） |
| P3-3 手续费口径（D4） | 谁承担通道手续费 |

> ⚠️ **已订正（2026-09-24）逐行**（⛔ 上表原文一字未删，标记写在此处）：
> - **P3-1** ⚠️ **前半已解、后半仍卡**：**"要开票"已拍**（Q3）⇒ 本行"是否开票"**已解**；**仍卡** = **税率数值**、**专票 vs 普票**、**电子 vs 纸质**（**均未拍**）。另注：`payment_invoices` 表**属本项、仍属 Phase 3**（**未落**）。
> - **P3-1（再订正 2026-09-24，批 6）** ✅ **已落（commit `3d2beb0`）** —— 上句「`payment_invoices` 表……（**未落**）」**已过期**：表已建（`backend/app/models/payment_invoice.py`），建表调用挂在 `backend/app/database.py::init_db()` 的**无条件段**；老师侧端点 `POST /api/v1/payment/invoices`（提交申请，一单一票）与 `GET /api/v1/payment/invoices`（我的申请，分页）已挂（`backend/app/routers/payment.py`）。⚠️ 上句「仍卡 = 税率数值 / **专票 vs 普票** / **电子 vs 纸质**」中，**后两项已由本批口径落码消解**：**只开普票**（⛔ 无专票那四项开票信息）、**只走电子**（⛔ 无邮寄/收件地址字段）—— 载体 = `backend/app/models/payment_invoice.py` 的口径注释 ＋ `backend/tests/test_payment_p3.py::test_p3_10`（负向断言表：给模型或真库加回任一口径外字段 ⇒ 立刻判红）。⇒ **仍属 ① 类待补的只剩「税率数值 ＋ 税目」**（数据、非实现项 ⇒ **本项已落**）。
> - **P3-2** ✅ **已于 Phase 2 落地**（提前，commit `528974c`）：`payment_orders` 加 3 个**可空**列 `amount_excl_tax_fen` / `tax_amount_fen` / `tax_rate_bps`，承诺 = `backend/app/database.py::_ensure_payment_order_tax_columns()` 挂 `init_db()` 的**无条件段**。⚠️ 只**立列**、**不填值**（税率未拍）；`ledger_entries` **不动**（含税记账）。
> - **P3-3** ⛔ **仍未拍**：谁承担通道手续费（本次五条答复未涉及）。
> - **P3-3（再订正 2026-09-24，批 6）** ✅ **已落（commit `3d2beb0`）** —— 手续费承担方**已拍（2026-09-24，主导者 CC）= 平台承担**；且**本阶段声明不做红冲**。口径**逐字落码**：只开普票 / 电子发票 / 含税价（0.5 元含税）/ 手续费平台承担 / 本阶段不做红冲 ⇒ 一切「专票 / 邮寄 / 税 / 红冲 / 手续费」字段**一个都不建**（载体 = `backend/app/services/payment/invoices.py` ＋ `backend/tests/test_payment_p3.py::test_p3_10` 与 `test_p3_11`：模型列集合、真库列集合、请求体三处逐项钉住，**改口径即判红**）。⚠️ 手续费**不进老师账本**（平台承担）。

> **为什么 Phase 0/1 加起来是"除支付外的全部"**：因为账本的**资金入口**被隔离在 §2.2 的单一方法 `apply_payment_confirmed` 后面。Phase 0/1 全部工作都可以用"手工插入一笔 recharge 分录"来验收（`entry_type='grant'` + `operator_id`），完全绕开通道。

---

## §10 ① 类未拍项清单（本席不猜、不选、不挂默认）

> ⚠️ 以下各项**只有业务方/主导者知道**。每项给：**问题 / 卡住了什么 / 答案会怎样改变设计**。

> ⚠️ **已订正（2026-09-24）—— 本节标题已部分失效**：标题写的"**① 类未拍项**"，**对 Q1〜Q5 的各项主体已不再成立**（主导者已于 2026-09-24 拍定，见紧邻下一节「✅ 已拍定」）。⛔ **标题与下方 Q1〜Q5 原文一律保留、不改**（它们是问题定义与历史留痕）；**当前仍属未拍的只有**：`tax_rate_bps` 的**税率数值**、**专票 vs 普票**、**电子 vs 纸质**、**免费额度 / 套餐档位数**、**P2-5 对账单格式**、**P3-3 手续费承担方（D4）**。

### ✅ 已拍定（2026-09-24，主导者 CC）

> ⚠️ 本节是**增补的订正**，⛔ **不是替换**：下方 Q1〜Q5 的原文**逐字保留**（它是问题定义，也是历史留痕）。
> 拍定值**逐字采用主导者 2026-09-24 的选择题答复**；本席⛔ 不改写、⛔ 不补充、⛔ 不自创。
> ⛔ **下列三项**在本次答复中**未给** ⇒ **仍属未拍**，下文各 Q 的「答案如何改变设计」里与之相关的分支**不得**被当成已选：
> ① `tax_rate_bps` 的**税率数值**；② **专票 vs 普票**（Q3 只说"要开票（普票/专票）"，没说哪种）；③ **电子 vs 纸质**。

| # | 裁定值（逐字） | 反转 / 消解了原清单里的哪个问题 | 对后续相位的影响 |
|---|--------------|--------------------------------|------------------|
| **Q1** 收款主体 | **公司主体** | 原 Q1 列了「个人 / 公司 / 聚合」三支，让"公司主体"只是**假设分支之一**；拍定后**分支收敛到该支**。同时**消解**了原文"若个人主体 ⇒ 大概率无法开企业票 ⇒ Q3 退化为不开发票；通道可能被迫选对公转账/线下 ⇒ 必须保留人工核销路径（`/payment/admin/grant` 从后台补开升级为主链路）" 整支 | ⇒ 走「**可开票**」分支；订单需带 `payee_entity_id`（P2-1 **已落**，`528974c`）；§2.2 `requires_payee_entity=True`；Q3 由此可用 |
| **Q2** 支付通道 | **微信支付 ＋ 支付宝**（两条通道**均已实现**：`backend/app/services/payment/channels/wechat.py`、`backend/app/services/payment/channels/alipay.py`；另有 `unset.py` 表示「未配置通道」态） | 原 Q2 的「对公转账（人工核销）」与「聚合」两支**被排除** ⇒ `capabilities().supports_callback = True`，**无需**把 `/payment/admin/grant` 升级为唯一入账入口、**无需**为此新设财务角色；`channel_detail_json` **不**用于"聚合方明细"语义 | **Phase 2 解锁**：P2-1 / P2-2 / P2-3 **已落**（commit `528974c`）；P2-4 / P2-5 **未落**（P2-4 见 Q5、P2-5 见下"仍未拍"） |
| **Q3** 是否开票 | **要开票（普票 / 专票）** ⇒ **价税分离** | 原 Q3 的「**不开票** ⇒ 现在设计原样可用（纯"分"整数），P3 整段删除；对账简化为 E2」一支**被排除**；「开普票/专票 ⇒ **必须价税分离**」一支**被选中** | ⇒ **P3-2 已提前到 Phase 2 并落地**：`payment_orders` 新增 3 个**可空**列 `amount_excl_tax_fen` / `tax_amount_fen` / `tax_rate_bps`（单位＝分 / 整数基点；承诺 = `backend/app/database.py::_ensure_payment_order_tax_columns()`，挂 `init_db()` 的**无条件段**）。⚠️ 但 `payment_invoices` 表**仍属 Phase 3**（**未落**）；⚠️ 税率数值 / 专票 vs 普票 / 电子 vs 纸质 **仍属未拍**（见上方 ⛔） |
| **Q4** 定价 / 计价 | **0.5 元 / 份** | 原 Q4 自述"**结构不变，只填数**"**被证实** —— 拍定值是**数据**，不动任何表结构（§5.1 的"多档可叠加 ⇒ `subscriptions` 需支持同人多订阅"风险由 **Q4b** 单项消解，见下） | ⚠️ **关键澄清：用户说的「一页」就是本设计稿的「份」** —— 「份」的定义见 **§3.1** =（用户, 文件夹, 学生）三元组的「已批改」状态发生 **0→1 跃迁** ⇒ `backend/app/services/payment/pricing.py` 的兜底价 **50 分零改动**。⚠️ **免费额度 / 套餐档位数**未在本次答复中给出 ⇒ 仍未拍（原 Q4 内） |
| **Q4b** 套餐 | **后置** | **消解**了原 Q4 末句的表结构风险 —— 原文"⚠️ 但**档位数量**会影响表：若套餐是'多档可选、可叠加'，`subscriptions` 需支持同人多订阅（现设计是**同时最多 1 个 active**）"：套餐不在本阶段 ⇒ **该风险随之后置**，本阶段**不必现在裁决** | ⇒ **Phase 1 范围缩减**为「只做**预充值余额按量扣**」，订阅套餐推到后面（见 §9 的订正标记） |
| **Q5** 退款 | **余额不可退；只退套餐未使用部分** | 原 Q5 的「**可退** ⇒ 需定义按比例退款公式（涉及套餐单价与已用量），且**通道必须支持原路退回**（回压 Q2）」一支**被排除**（连带**不再**对 Q2 形成"必须支持原路退回"的回压）；「**余额不可退** ⇒ 需在**服务条款**与**前端**明示，且 `refund` 只支持'套餐未使用部分'」一支**被选中** | ⇒ **P2-4 范围缩到「只退套餐未使用部分」**；⚠️ 原文**逐字要求**「需在**服务条款**与**前端**明示」⇒ 前端侧**已落**、服务条款侧**未落地**（见下"前端明示落地状态"）。⚠️ **套餐已后置（Q4b）⇒ 可退对象暂不存在** ⇒ P2-4 本阶段**无可实现对象**（⛔ 措辞不得写成"退款被禁"） |

**联动一条（必须记）**：
- **「要开票」（Q3）原本激活了**「开票与退款的口径耦合（红字发票）须在 Phase 3 定」—— 原文 Q3 末句逐字：*"**开票与退款的口径耦合**（红字发票）需在 Phase 3 一并定。"*
- 而 **「余额不可退」（Q5）削弱了红冲场景**：余额侧**不再**产生"退款 ⇒ 需红冲已开发票"这条路径。
- ⚠️ **但未清零**：**套餐未使用部分若可退、且该套餐已开过票**，红冲场景**仍然存在** —— 只是从"余额 ＋ 套餐"两处**收窄到"套餐"一处**。
- ⇒ **结论：Phase 3 变轻（范围更小），但该条仍须在 Phase 3 定**（⛔ 不是"可删除"）。

**前端明示（Q5 原文要求）落地状态**：
- ✅ **已落（本批，2026-09-24）**：`frontend/src/components/payment/PaymentWalletPage.tsx` 新增「退款规则」标注，口径**逐字** = **「余额不可退，只退套餐未使用部分」**。
- ⚠️ **服务条款明示：未落地** —— 实测仓内**无**服务条款 / 用户协议页面：`frontend/` 全目录（排除 `node_modules`、`dist`）grep `服务条款|用户协议|服务协议|隐私政策` **零命中**；`frontend/src/App.tsx:94-134` 共 7 条 `<Route>`（含 1 条 `*` 兜底），**无**任何条款页路由。⇒ **本席⛔ 不自造法律文本**（属 ① 类业务真值），**留给主导者裁**。

### Q1 收款主体 / 商户资质
- **问题**：钱收到谁的账上？个人（老师个人码？平台负责人个人？）还是公司（哪张营业执照？经营范围含"教育服务/技术服务"吗？）
- **卡住了什么**：`payment_orders.payee_*` 字段与主体标识；**退款主体**（谁把钱退回去）；**通道能否开通**（企业资质是微信/支付宝商户号的前置）；**发票抬头**（Q3 依赖它）；**手续费承担方**（D4：个人收款无法开票、限额低、费率不同）
- **答案如何改变设计**：
  - 若**公司主体** ⇒ 可开票（Q3 走"可开票"分支）、金额需**价税分离**（P3-2 提前到 Phase 2）、订单需带 `payee_entity_id`。
  - 若**个人主体** ⇒ 大概率**无法开企业票** ⇒ Q3 退化为"不开发票"；需在**服务条款**里明示（本设计不涉及条款，但需提醒）；通道可能被迫选"对公转账/线下"，则 `capabilities().supports_callback = False` ⇒ **必须保留人工核销路径**（`POST /payment/admin/grant` 从"后台补开"升级为"主链路"）。
  - 若**聚合服务商** ⇒ 引入第三方 SDK，`channels/` 多一层；我方 `payment_orders` 仍需保存对方交易号。
- ⚠️ **已订正（2026-09-24）**：主导者拍定 = **公司主体** ⇒ 走本节**第一支**（可开票、金额需价税分离、订单需带 `payee_entity_id`）。⛔ 上述三支**原文保留为历史**；"个人主体""聚合服务商"两支**未采用**。逐条订正见上方「✅ 已拍定（2026-09-24，主导者 CC）」。

### Q2 支付通道（微信支付 / 支付宝 / 对公转账 / 聚合）
- **问题**：老师用什么付钱？
- **卡住了什么**：**整个 Phase 2**（P2-1〜P2-5）；订单状态机形态；是否需要 `payee` 主体；手续费计提（D4）；对账文件格式（E3）
- **答案如何改变设计**：
  - **微信/支付宝** ⇒ 有异步回调 ⇒ `supports_callback=True` ⇒ 回调验签 + `apply_payment_confirmed` 自动入账（Phase 2 按本设计走）。
  - **对公转账（人工核销）** ⇒ **无回调** ⇒ 订单停在 `pending` 等财务确认；`capabilities().supports_callback=False`；`/payment/admin/grant` 成为**唯一**入账入口 ⇒ 需要**财务角色与审计**（复用本仓已有 `admin_audit`/`access_log`，见 `main.py:281-282` 的 `admin_audit` 挂载）。
  - **聚合** ⇒ 我方只对接聚合方，`channel` 字段语义变为"聚合方"，渠道明细落在 `payment_orders.channel_detail_json`。
- ⚠️ **已订正（2026-09-24）**：主导者拍定 = **微信支付 ＋ 支付宝**（两条通道**均已实现**，另有 `unset.py` = 「未配置通道」态）⇒ 走本节**第一支**（有异步回调、`supports_callback=True`）。⛔ "对公转账（人工核销）""聚合"两支**未采用**，原文保留为历史。**Phase 2 由此解锁**，P2-1 / P2-2 / P2-3 已落（`528974c`）。逐条订正见上方「✅ 已拍定」。

### Q3 是否开票、开什么票
- **问题**：老师要发票吗？要专票/普票？电子还是纸质？
- **卡住了什么**：Phase 3（P3-1/P3-2）；**金额模型**（价税分离 vs 纯含税整数）
- **答案如何改变设计**：
  - **不开票** ⇒ 现在设计**原样可用**（纯"分"整数），P3 整段删除；对账简化为 E2。
  - **开普票/专票** ⇒ **必须价税分离**：`payment_orders` 增 `amount_excl_tax_fen` / `tax_amount_fen` / `tax_rate_bps`；`ledger_entries` 是否按含税记账需明确（建议**含税记账**，税额只在订单层拆，避免账本多一套一致性约束）；新增 `payment_invoices` 表；**开票与退款的口径耦合**（红字发票）需在 Phase 3 一并定。
- ⚠️ **已订正（2026-09-24）**：主导者拍定 = **要开票（普票 / 专票）** ⇒ **价税分离**，走本节**第二支**（"不开票 ⇒ P3 整段删除"一支**未采用**）。本支**已提前落地**：3 个列已加（见上方「✅ 已拍定」Q3 行的承诺与坐标）；`ledger_entries` 按原文建议**含税记账、不动**（`528974c` 已遵守）。⚠️ **仍未拍**：`tax_rate_bps` 数值、**专票 vs 普票**、**电子 vs 纸质**。⚠️ **联动**："开票与退款的口径耦合（红字发票）"因 Q5「余额不可退」而**范围收窄**（见上方"联动一条"），但**仍须在 Phase 3 定**。

### Q4 定价数值与计价单位（本席必须提出的第 4 项）
- **问题**：每一份批改**收多少钱**？有没有**免费额度**（新用户送 N 份）？套餐**几档**、每档多少钱、含多少份？额度用完是**转余额**还是**停服务**？
- **卡住了什么**：`payment_pricing.json` 的**全部数值**；`payment_plans` 的**全部行**；§4.1 的**闸门阈值**（余额低于多少告警）；§5.3 的 `overage_policy` 默认值
- **答案如何改变设计**：**结构不变，只填数**。这是本设计的刻意选择——所有价格都是配置/数据，**不在代码里**（除 `tiered_price` 的算法）。⚠️ 但**档位数量**会影响表：若套餐是"多档可选、可叠加"，`subscriptions` 需支持同人多订阅（现设计是**同时最多 1 个 active**）。
- ⚠️ **已订正（2026-09-24）**（**分两问**，勿混）：
  - **Q4 定价 / 计价 = 0.5 元 / 份** ⇒ 原句"**结构不变，只填数**"**被证实**：拍定值是**数据**，不动表结构。⚠️ **关键澄清**：用户说的「**一页**」**就是**本设计稿的「**份**」（定义见 **§3.1** =（用户, 文件夹, 学生）三元组「已批改」0→1 跃迁）⇒ `backend/app/services/payment/pricing.py` 的兜底价 **50 分零改动**。⚠️ 原文里的**免费额度**、以及**套餐档位数**，**本次答复未给** ⇒ **仍未拍**。
  - **Q4b 套餐 = 后置** ⇒ 原文末句"⚠️ 但**档位数量**会影响表（…`subscriptions` 需支持同人多订阅）"这一**风险随之后置**（套餐不在本阶段，不必现在裁决）。**Phase 1 范围缩减**见 §9 订正标记。

### Q5 退款规则（相邻未拍项，必须点名）
- **问题**：预充值余额能退吗？套餐未用完能退吗？退款时限（如 7 天无理由）？
- **卡住了什么**：Phase 2 的 P2-4；§5.2 的 `refunded` 语义（**已消耗额度退不退**）
- **答案如何改变设计**：若"余额不可退"⇒ 需在**服务条款**与前端明示，且 `refund` 只支持"套餐未使用部分"；若"可退"⇒ 需定义**按比例退款公式**（涉及套餐单价与已用量），且**通道必须支持原路退回**（回压 Q2）。
- ⚠️ **已订正（2026-09-24）**：主导者拍定 = **余额不可退；只退套餐未使用部分** ⇒ 走本节**第一支**（"可退"一支**未采用**，连带**不再**对 Q2 形成"必须支持原路退回"的回压）。原文**逐字要求**的「需在**服务条款**与**前端**明示」：**前端侧已落**（`frontend/src/components/payment/PaymentWalletPage.tsx`，文案逐字「余额不可退，只退套餐未使用部分」）；**服务条款侧未落地**（实测仓内无此页，⛔ 本席不自造法律文本 —— 见上方「✅ 已拍定」末节）。⚠️ **套餐已后置（Q4b）⇒ 可退对象暂不存在** ⇒ P2-4 本阶段无可实现对象（⛔ 措辞不得写成"退款被禁"）。

---

## §11 本席实测到的、与给定背景不一致的地方

> 逐条给出结论与证据。**"以代码为准"已在下列各条执行。**
> ⚠️ 本节所有坐标同 §0 的钉法：**= `feat/independent-teacher` @ `72c5878`**。凡引用 `main` 坐标处均已显式标注。

### 11.1 ⚠️【最重要】主树不在 `feat/independent-teacher` 上，背景所述的 4 个 commit 不在主树
- **背景**：独立老师改动在 `feat/independent-teacher` 分支（`d1a15ad a52539a b048751 72c5878`）。
- **实测**：`F:\xuyue-local\.git\HEAD` → `ref: refs/heads/main`；`refs/heads/main` = `a8da4f76…`；`refs/heads/feat/independent-teacher` = `72c5878a…`。
⇒ 我最初读主树时，看到的是**收窄前**的注册逻辑（**`main` 坐标**：`routers/auth.py:88` 是旧的 5 角色白名单、`:237-247` 仍绑演示班），差点误判"背景过期"。
⇒ **正确基线是 `72c5878`**（工作树在 `F:\xuyue-local\.claude\worktrees\independent-teacher\`）。**背景没说错，是我一开始站错树**——但这条对后续所有 agent 都重要：**设计/实现的基线必须锁 `72c5878`，⛔ 不是 `main`**。
⇒ **本文件 v1.0 曾把这一错误后果带进正文**（`scan_billing.py` 等文件的行号取自 `main`），v1.1 已逐条重取，见 §14 变更记录。
- 未复核：`d1a15ad / a52539a / b048751` 三个 hash 本席**无法**用 git log 复核（无 shell）；只复核了 `72c5878` 是分支头。

### 11.2 `billing_config.example.json` 的位置：在 `backend/` 下，不在仓根
- **背景**：`billing_config.example.json` 是配置。
- **实测**：`<WT>/billing_config.example.json` → 不存在；`<WT>/backend/billing_config.example.json` → **存在**（`:1-56`）。
- **吻合**：真正加载的路径是 `project_root()/"billing_config.json"`（`billing_pricing.py:108-111`），而 `project_root()` = `<repo>/backend`（`user_paths.py:18-21`：`Path(__file__).parent.parent.parent`）⇒ 即 `backend/billing_config.json`。

### 11.3 ✅ 背景所述"导航白名单见 `frontend/src/constants/systemRoles.ts`"属实（但在 `main` 上不存在 —— 见 11.1）
- **实测**（`<WT>` = `72c5878`）：`frontend/src/constants/systemRoles.ts:34-67` 的 `TEACHER_NAV_WHITELIST`，`:65-66` 正是 `scan-consumption` / `usage-summary`；`:83-88` `isTeacherOnlyAccount`；`:91-93` isNavAllowedForTeacher。✅ **背景完全正确。**
- ⚠️ 但同一文件在 `main` 上只有 `SYSTEM_ROLES`（`:1-13`），**没有白名单** ⇒ 再次印证 11.1。

### 11.4 ⚠️ 背景/架构模板的三处"事实偏差"（会直接影响实现，必须改）
| # | 模板/预设 | 本仓实际 | 证据 |
|---|----------|---------|------|
| 1 | 统一响应 `{error, message}` | `ApiResponse{code:int=0, message:str, data:T}`；错误走 `{"detail": "..."}` | `backend/app/schemas/common.py:8-11`；`frontend/src/services/api.ts:57-67` |
| 2 | 主键 `BIGINT UNSIGNED AUTO_INCREMENT` | `id VARCHAR(36)` UUID 字符串 | `models/grading_daily_stat.py:19`、`models/user.py:14` |
| 3 | 迁移用 alembic | **无 `alembic.ini`**（实测不存在）；迁移 = `AUTO_DDL` 开关（默认 `False`，`config.py:63`）+ `sync_database_schema()` 的模型注册表（`database.py:87-158`）+ 一堆幂等 `_ensure_*`（如 `database.py:221-249`） | `backend/app/database.py:65-177` |

### 11.5 ⚠️ 背景未提及、但对本设计是**硬约束**的一条：口径 A 的用量是**可回退**的
`grading_stats.py` 有 4 条扣减路径（`:186-265`、`:294-325`）。⇒ "用量数字"不是单调递增的。背景把它描述为"成本核算"，但没提**它能变小、能被清空**（`remove_folder_stats`，`:250-265`）。**这直接否决了"账本挂在现有用量数字上"的做法**（§1.3 陷阱 3、§3.1 storage 不收的理由）。

### 11.6 ⚠️ 能力边界声明（不是背景错误，是本席的取证缺口）
- 🟡 **"支付侧零存在"（`微信支付/支付宝/alipay/wxpay/充值/钱包/套餐/订单` 全仓零命中）**：背景称已实测；**本席无 shell，无法复跑 grep 复核**。本席能确认的是：**未读到**任何支付相关模型/路由（`models/__init__.py:1-172` 的 172 行清单、`main.py:158-302` 的挂载清单里均无）。**建议实现批开工前自己复跑一次那句 grep。**
- 🟡 **`scan_billing.py` 端点计数**：背景称 9 个；本席**逐个读到 9 个且全为 `@router.get`**（§1.1 表）✅ **复核通过**。
- ⚠️ `scan_billing.py` 顶部 docstring（`:4-9`）**只列了 5 个端点**，与实际 9 个不符 ⇒ **该 docstring 已过期**（非支付问题，仅登记）。

### 11.7 落地位置（替代方案）
`payment-design` worktree 未建成（无 shell）。本文件落在同分支线的既有 worktree：
`F:\xuyue-local\.claude\worktrees\independent-teacher\docs\payment\payment-design.md`（未跟踪新文件）。搬入正式 worktree 的方式见 §14。

---

## §12 顺手发现的问题（与支付无关，**本批只报告、未改**）

> 铁律：本批只出设计、零代码改动。下列各项**不碰**，只为后续批次留证。

| # | 位置 | 问题 | 与支付的关系 |
|---|------|------|-------------|
| 1 | `backend/app/grading/grading_stats.py:161-162`（`_increment` 的 `except Exception: db.rollback()`，无日志） | 统计写入失败**静默吞掉**，无任何日志 | ⚠️ **高危**：若把计量挂进这条链，等于"静默少收钱"（§7.1 明文禁止） |
| 2 | `backend/app/grading/grading_stats.py:304-325`（`record_graded_state_change` 整函数 `try/except: pass`） | 同上，且吞的是**批改状态跃迁**（正是计费的触发源） | 同上 |
| 3 | `backend/app/database.py:204-205`、`217-218`、`248-249` 等 | 多处 `except Exception: pass` —— 建表/补列失败静默 | 新增支付表若沿用此范式，**建表失败不会被发现**，首次记账才 500。建议支付表的 `_ensure_*` **至少打一条 error 日志**（与 `flow_*` 保持结构一致，但补日志） |
| 4 | `backend/app/config.py:91` `ALLOW_PUBLIC_REGISTRATION: bool = True` | 默认放开自助注册（注释：生产置 False） | ⚠️ **支付前必须复核**：公网自助注册 + 计费 = 恶意注册刷免费额度/刷用量。建议把"注册即建账户、余额 0、无赠送额度"作为默认 |
| 5 | `backend/app/routers/scan_billing.py:4-9` docstring 只列 5 个端点 | 文档过期（实际 9 个） | — |
| 6 | `backend/app/routers/scan_billing.py` —— **分支已加 `resolve_scope_user_id()`**：定义 `:56-68`（辅助 `_roles_are_teacher_only` `:36-43`、`_is_teacher_only_account` `:46-53`），接线 **8 处** `:100/:203/:279/:332/:403/:567/:592/:652`（第 9 处 `:56` 是函数定义本身 ⇒ 全文件 9 次命中）。**残留**：收敛**只覆盖「仅任课教师」账号**；**非**「仅任课教师」的账号（如校级管理者 / 年级组长 / 班主任 / 测试账号）传 `?user_id=<别人>` **仍可查他人** —— 这是**有意保留**（管理员本就需要看别人），⛔ **不是漏洞**，`resolve_scope_user_id` 的 docstring `:59-65` 已明写"其他角色……原样透传，None 仍表示全平台" | 「**任意**登录用户可越权查他人用量」**在本分支上已不成立**（我 v1.0 读的是 `main`，该结论已失效）。分支真实状态 = **已收敛到「仅任课教师」，其余角色有意放行** | ✅ **判断不变，理由要换**：新支付端点**仍必须自己做"只能查自己"的强校验**，⛔ 不要照抄 `user_id` 参数范式 —— 不是"现在完全没管"，而是"现在的收敛只覆盖『仅任课教师』一类账号，**支付端点的面比它窄不了**（余额/流水/账单天生强隐私），必须自己再收一道" |
| 7 | `backend/app/routers/scan_billing.py:530` `"download": 0.0,  # 预留：当前无导出流量埋点` | 计量项预留但无埋点 | 本设计顺带不采纳该计价项（§3.1） |

---

## §13 本设计的自我约束声明（给实现批的交接）

1. ⛔ **零实现**：本批只出本文件，未新增任何 `.py`、未改前端、未 commit。
2. ⛔ **口径 A 零改动**：`scan_billing.py` 9 端点、`billing_pricing.py`、`billing_config.example.json` 一行未改。
3. ⛔ **不替主导者拍板 §10 的任何一项**；Phase 0/1 的设计保证它们在通道/主体/开票未定的情况下**不构成阻塞**。
4. ⛔ **不新建调度框架、不新增常驻脚本、不新增门禁**（对账用纯 SQL；过期用惰性判定；后台循环复用 `main.py:69-106` 的既有范式）。
5. ✅ **复用声明**：`tiered_price()`（`billing_pricing.py:141-192`，纯函数）；账本**结构**照抄 `credit_accounts`/`credit_transactions`（`models/credit_account.py`、`models/credit_transaction.py`）；幂等建表照抄 `_ensure_flow_tables`（`database.py:221-249`）；前端灰度复用 `NavChild.featureKey`（`Sidebar.tsx:66/388-389`）；客户身份判据复用 `isTeacherOnlyAccount`（`systemRoles.ts:83-88`；后端已有对应实现 `scan_billing.py:36-53`，§8.2）；导航角色闸复用 `lib/adminAccess.ts:52-64` + `:71-77`。
6. ⛔ **坐标纪律**：本文件所有行号 = `feat/independent-teacher` @ `72c5878`（见 §0 顶部钉法）。⛔ 引用任何行号前先 `git rev-parse` 确认树。

---

## §14 变更记录

### v1.0（2026-09-24）
**触发原因**：主导者立"独立老师支付系统"新线，要求先出架构与数据模型设计。
**交付**：本文件（§1〜§13）。
**未达成项（如实申报）**：
- 未建立 `payment-design` worktree（本会话只有 `Read`/`Write`，无 shell）
- 未提供 `git status --short`（同上）
- 未复核"支付侧零存在"的全仓 grep（同上，标 🟡）
- §11.1 的三个 commit hash 未复核

### v1.1（2026-09-24）
**触发原因**：主导者复核发现 **v1.0 的 `scan_billing.py` 等行号坐标取自主树 `main`（= 收窄前代码），不是本设计要服务的分支**；此类错会让下一个实现批照错行号动手。属**返工**。
**修改内容**（逐条旧值 → 新值，详见下表）：

| # | 位置 | 旧值 | 新值 |
|---|------|------|------|
| 1 | §0 顶部（新增） | —（无坐标来源声明） | 新增**坐标钉**：全文行号 = `feat/independent-teacher` @ `72c5878`，⛔ 非 `main`(@`a8da4f7`)；附 `git rev-parse` 复核命令；并列出两树坐标一致的文件清单 |
| 2 | §1.1 9 路由表 | `:50 / :149 / :224 / :279 / :344 / :419 / :499 / :521 / :576` | `:89 / :190 / :267 / :324 / :390 / :475 / :555 / :578 / :634`；并**新增两列**（Depends 行 `:94/:197/:273/:329/:395/:477/:559/:583/:643`、scope 收敛接线行 `:100/:203/:279/:332/:403/:567/:592/:652`）；补一行说明分支新增的 `resolve_scope_user_id`（`:56-68`）是读路径收敛、非写路径 |
| 3 | §1.1 挂载点 | `main.py:288-290` | `main.py:289-290` |
| 4 | §3.1 表格 `download` 行 | `scan_billing.py:474` | `scan_billing.py:530` |
| 5 | §7.2 `Sidebar.tsx` 行 | `NAV_ITEMS`（`:76-265`）/ `system-ops` 组 `:256-264` / `NAV_SECTIONS`（`:274-311`） | `NAV_ITEMS`（`:76-270`）/ `system-ops` 组 `:261-269` / `NAV_SECTIONS`（`:279-316`） |
| 6 | §7.2 `main.py` 行 | `:288-290` | `:289-290` |
| 7 | §7.4 `Sidebar.tsx` 行 | `featureKey`（`:67`）、过滤逻辑（`:389`） | `featureKey`（`:66`）、过滤逻辑（`:388-389`） |
| 8 | §7.4 角色闸（新增） | —（未写角色闸落点） | 新增：`isNavItemVisible`（`lib/adminAccess.ts:52-64`，由 `Sidebar.tsx:388` 调用）+ `isNavPageAllowed`（`:71-77`）共用同一白名单 ⇒ **新增 nav id 只改白名单一处**；⛔ 不在 `Sidebar.tsx` 另建第二份谓词（其 `:380` 注释已明令） |
| 9 | §8.1 注册注释行 | `routers/auth.py:88-90` | `routers/auth.py:85-93`（"不再挑选演示班"具体在 `:89-90`） |
| 10 | §8.2 闸门判据（新增） | — | 新增：后端已有同口径实现 `scan_billing.py:36-53`（`_roles_are_teacher_only` / `_is_teacher_only_account`）⇒ **复用后端这一份**，⛔ 不抄第三份 |
| 11 | §10 Q2 挂载行 | `main.py:281` | `main.py:281-282` |
| 12 | §11.1 | 把 `routers/auth.py:88` / `:237-247` 当作一般证据 | 显式标注为 **`main` 坐标**（收窄前）；补一句"v1.0 已把该错误后果带进正文，v1.1 已重取" |
| 13 | §11.5（新增） | — | 新增"落地位置（替代方案）"小节（原 §0 内的说明提升为独立条目，并指向 §14 搬迁命令） |
| 14 | **§12 第 6 条（结论失效，非仅行号）** | 「`scan_billing.py:55-56` 等 6 个消费端点只 `Depends(get_current_user_id)`；**任意**登录用户可 `?user_id=<别人>` 查**其他人**用量」 | 改写为**分支真实状态 + 残留**：分支已加 `resolve_scope_user_id()`（定义 `:56-68`，接线 8 处 `:100/:203/:279/:332/:403/:567/:592/:652`，全文件 9 次命中）；收敛**只覆盖「仅任课教师」账号**；**非**该类账号（校级管理者等）传 `?user_id=` 仍可查他人 —— **有意保留、⛔ 不是漏洞**。**判断不变、理由更换**：支付端点仍必须自做"只能查自己"，理由是"支付的隐私面比该收敛窄不了"，而非"现在完全没管" |
| 15 | §12 第 7 条 | `scan_billing.py:474` | `scan_billing.py:530` |
| 16 | §13 复用声明 | `Sidebar.tsx:67/389` | `Sidebar.tsx:66/388-389`；补后端判据 `scan_billing.py:36-53`、`lib/adminAccess.ts:52-64` / `:71-77`；新增第 6 条**坐标纪律** |
| 17 | 文档版本 | 1.0 | 1.1 |

**未复核（如实申报）**：
- §1.1 表中 `user-ranking` 的 `:390/:395/:403`、`trends`/`breakdown`/`monthly` 的 Depends 行与接线行，本席**已逐个实读确认**（`:190/:197/:203`、`:267/:273/:279`、`:324/:329/:332`、`:390/:395/:403`）；`pricing` 无 `user_id` 参数故接线列记"—"（`:475/:477`）。
- 仍未复核：`d1a15ad / a52539a / b048751`；"支付侧零存在"的全仓 grep（无 shell）。
- ⛔ 本次**未** commit。

**影响范围**：v1.1 是**坐标勘误 + 一条结论改写**，§2〜§6、§9 的数据模型与分期结论未变；实现批可用本版直接动手。搬迁命令（落点仍留原地，由主导者决定）：
```bash
git -C F:/xuyue-local worktree add .claude/worktrees/payment-design -b feat/payment-design feat/independent-teacher
cp -r F:/xuyue-local/.claude/worktrees/independent-teacher/docs/payment F:/xuyue-local/.claude/worktrees/payment-design/docs/
```

### v1.2（2026-09-24）
**触发原因**：主导者（CC）已于 **2026-09-24** 通过选择题**拍定 §10 的五条 ① 类业务真值**，而 v1.1 的 §10 仍整节写着"未拍项清单" ⇒ **文档在撒谎**（会误导下一个实现批把已定的事当未定，或反之）。属**订正**。
**修改内容**（⛔ **只增订正标记**；原文**一字未删**）：

| # | 位置 | 改法 |
|---|------|------|
| 1 | §10 开头（新增节） | 新增「✅ 已拍定（2026-09-24，主导者 CC）」：6 行表（Q1/Q2/Q3/Q4/Q4b/Q5）逐条给 **裁定值（逐字） / 反转消解了原清单的哪个问题 / 对后续相位的影响**；另记**联动一条**（Q3 激活的红冲耦合被 Q5 削弱、但未清零）＋「前端明示落地状态」 |
| 2 | §10 Q1〜Q5 **各自末尾** | 就地加「⚠️ 已订正（2026-09-24）：…」，逐条指向被选中的那一支、并明写哪些支**未采用** |
| 3 | §9 开头（新增计数块） | 新增「本节逐项计数」表：Phase 0/1/2/3 各 **表内项数 / 已落 / 剩余** ＋ 剩余项的卡点现状（**合计 21 项 / 已落 12 / 剩 9**） |
| 4 | §9 Phase 1 标题下 | 就地加：**范围缩减为「只做预充值余额按量扣」**，套餐后置（Q4b） |
| 5 | §9 Phase 2 标题下 ＋ P2-1/P2-2/P2-3 行 | 就地加：**已落（commit `528974c`）**（含各行的落点摘要） |
| 6 | §9 P2-4 行 | 就地加：**范围 = 只退套餐未使用部分；⛔ 余额不可退**；并注明其"被什么卡住"**已改变**（不再卡"原路退回"，改卡"可退对象暂不存在"） |
| 7 | §9 Phase 3 标题下 ＋ P3-2 行 | 就地加：**P3-2 已于 Phase 2 落地**（提前）；P3-1 拆成"已解的前半 / 仍卡的三项"；P3-3 标注仍未拍 |
| 8 | §3.1 单价段末（新增） | 就地加：上一行"单价数值 = ① 类未拍项"**已部分消解**（Q4 = 0.5 元/份；「一页」＝「份」；`pricing.py` 兜底 50 分零改动）；**免费额度**部分**仍未拍** |
| 9 | §5.2 `refunded` 行（新增） | 就地加：退款口径**已拍**（Q5）与本行"只退未消耗部分"**一致、无需改**；**金额公式仍未拍**故"金额口径 = ① 类"仍成立；⚠️ 并标注该行原引"见 §10 **Q3**"疑为 **Q5** 之误（**未删改原文，请主导者裁**） |
| 10 | 配套代码（本批同批交付） | `frontend/src/components/payment/PaymentWalletPage.tsx` 加「退款规则」标注，口径逐字 = **「余额不可退，只退套餐未使用部分」**（Q5 原文要求的"前端明示"） |
| 11 | 文档版本 | 1.1 → 1.2 |

**⛔ 仍未拍（本版**刻意保留**在"未拍"态，⛔ 不得被当成已选）**：`tax_rate_bps` 的**税率数值**；**专票 vs 普票**；**电子 vs 纸质**；**免费额度 / 套餐档位数**；**P2-5 对账单格式**；**P3-3 手续费承担方（D4）**。

**未落地（如实申报，留给主导者裁）**：**服务条款的口径明示** —— 实测仓内**无**服务条款/用户协议页（`frontend/` 全目录 grep `服务条款|用户协议|服务协议|隐私政策` **零命中**；`src/App.tsx` 的 7 条 `<Route>` 中无此页）⇒ **本席⛔ 不自造法律文本**（属 ① 类）。

**未复核／未跑（如实申报）**：本版**未**改动任何 `backend/` 文件（一个字节未碰）；本版**未** commit、**未** `git add`。

**影响范围**：v1.2 是**订正 + 一处前端标注**，§1〜§8 的数据模型与 §2.2 接口契约**未变**；§9 的分期**结构未变**（只有 4 处就地状态标记 ＋ 1 张计数表）；§10 的**问题清单原文未变**（新增的是答案）。

### v1.3（2026-09-24）
**触发原因**：主导者裁定「修设计稿的缝」—— **§6.2 L461 要求 E3（通道一致），而 §6.4 L478/L479 与 §13 L806 又不给它任何合法形态**；这个矛盾不写清楚，下一个实现批会在同一处反复。
**修改内容**（⛔ **只新增 §6.5 一节 + 本条记录 + 一处版本号**；原文**一字未删**）：

| # | 位置 | 改法 |
|---|------|------|
| 1 | §6.4 之后（**新增 §6.5**） | 新增「E3 的落点（订正 2026-09-24）」：三处原文矛盾逐条引行号；本阶段裁定 **E3 不落地** ＋ 三条理由；将来落点的**三个前提（缺一不可）**；**自动路 / 手工路两条路的代价各一句**（⛔ 本席未拍自动还是手工，留主导者裁） |
| 2 | 本文件行号基线（新增说明） | §6.5 的插入使 **§6.4 之后的全部行号整体 +34**（例：§13 第 4 条「不新建调度框架…」原 L806 → 今 L840；§7 原 L483 → 今 L517）。§6.5 内引用的 `L461 / L476〜479 / L806` = **插入前**的行号，取自 `feat/independent-teacher` @ `b5f7b5c`。⛔ §13 第 6 条的「坐标纪律」仍钉 `72c5878`，本版**未改该钉**（要不要重钉由主导者定） |
| 3 | 文档版本 | 1.2 → 1.3 |

**同批交付的代码（⛔ 未 commit）**：只读端点 `GET /api/v1/payment/admin/reconciliation`（E1 复用 `services/payment/ledger.py::verify_invariant_e1()`，⛔ 未重写判据；E2 = §6.2 L460 的纯 SQL；⛔ 无 E3 字段）。
**仍未拍（留给主导者）**：E3 走**自动路**还是**手工路**（见 §6.5 末）；**D1 补单入口**是否放行（admin 写端点 / 手工 SQL）。
**未复核（如实申报）**：本版**未**跑测试（测试在 P3-1 批的 `backend/tests/test_payment_p3.py`）；本版**未** commit。

### v1.4（2026-09-24）
**触发原因**：批 6（commit `3d2beb0`）落了 **Phase 3 的 P3-1**（`payment_invoices` 表 ＋ `POST/GET /api/v1/payment/invoices` ＋ 状态机 `requested`→`issued`→`void`）与 **P3-3**（口径逐字落码），但**未同步** §9 的逐项计数表与就地标记 ⇒ §9 当时仍写「Phase 3 已落 1 / 剩 2」「`payment_invoices` 表……（**未落**）」，**已过期**。属**订正**。
**修改内容**（⛔ **只在本文件就地追加订正标记**；原文**一字未删**，**删除行数 = 0**）：

| # | 位置 | 改法 |
|---|------|------|
| 1 | §9 开头计数表**下方**（新增订正块） | 原 **Phase 3 行**「1（P3-2）/ **2**（P3-1/P3-3）」⇒ **订正为 已落 3 / 剩 0**；给**订正后**逐 Phase 计数表（**求和写在合计行内**：表内项数 9+4+5+3 = **21**、已落 8+0+3+3 = **14**、剩余 1+4+2+0 = **7**）；卡点现状列只 Phase 3 行变化；并给 **Phase 2 行加注**（**仍为 已落 3 / 剩 2，⛔ 不变** —— 本批落的是 P2-5 的 ① 补缝 §6.5 ② E1/E2 只读端点，其 **E3 ⛔ 未落**） |
| 2 | §9 Phase 2 标题下 | 追加：本批落 P2-5 两部分（载体 = 本文件 §6.5；`GET /api/v1/payment/admin/reconciliation`，见 `backend/app/routers/payment.py`）；⛔ E3 未落、「对账单格式」仍未拍 ⇒ **已落 3 / 剩 2 不变** |
| 3 | §9 Phase 3 标题下 | 「已落 1 / 剩 2」⇒ **已落 3 / 剩 0**；注明 **P3-1 的税率数值仍属 ① 类待补**（数据、非实现项 ⇒ ⛔ 不影响「已落」判定）；**P3-3 手续费承担方已拍 = 平台承担**、**本阶段声明不做红冲** |
| 4 | §9 P3-1 行 | 追加 **✅ 已落（commit `3d2beb0`）**：表 ＋ 两端点 ＋ 建表挂 `init_db()` **无条件段**；并注明「专票 vs 普票 / 电子 vs 纸质」**由本批口径落码消解**（只开普票 / 只走电子） |
| 5 | §9 P3-3 行 | 追加：**已拍（2026-09-24，主导者 CC）= 平台承担**；本阶段**声明不做红冲** ⇒ **已落（commit `3d2beb0`）** |
| 6 | 文档版本 | 1.3 → 1.4 |

**未跑测试（如实申报）**：本版是**纯文档改动**（只改 `docs/payment/payment-design.md`；⛔ 未碰任何代码、⛔ 未碰 §6.5 与 §14 的 v1.3 任何一字、⛔ 未碰其他文件）⇒ **本版未跑测试**。本版唯一的机械验证 = 本文件相对 commit `3d2beb0` 基线的 `git diff --numstat`（**删除数必须为 0**）。
**未复核／未 commit（如实申报）**：本版**未** commit、**未** `git add`。⚠️ 文件头「版本：**1.1**」自 v1.2 起**即未同步**（属**既存**遗留、非本版引入），本版**未动它**。
