# 学生端运营功能 — 技术契约

> 版本: 1.0 | 数据库: MySQL 8.0 | ORM: SQLAlchemy | 后端: FastAPI | 前端: React + TypeScript
> 对应需求: 灵犀岛产品方案板块三「学生端全业务」
> 部署形态: 单客户定制版（湘潭子敬学校），学生功能统一在教师/管理端实现为管理入口（教师代录、代发、代审）

---

## 0. 全局约束与约定

### 0.1 角色说明

本叙阅无学生端/家长端登录。所有"学生端"功能在管理端实现，由教师/管理员代操作。权限粒度：

| 角色 | 可操作班级范围 | 可执行操作 |
|------|-------------|----------|
| 系统管理员 | 全校 | 全部功能 + 章定义管理 + 商品库管理 + 兑换审核 |
| 子系统管理员 | 全校 | 全部功能 + 章定义管理 + 商品库管理 + 兑换审核 |
| 校级管理者 | 全校 | 查看报表、审核实践、录入校园生活 |
| 年级组长 | 所管年级 | 查看报表、审核本年级实践、录入本年级校园生活 |
| 班主任 (head) | 所管班级 | 颁章/学分操作/实践录入审核/校园生活录入/兑换确认 |
| 任课教师 (teacher) | 所协作班级 | 仅查看，不得颁章/加减学分 |
| 班主任 + 任课教师 (deputy) | 所协作班级 | 颁章/学分操作/实践录入/兑换确认 |

基础权限判断沿用 `app/utils/class_access.py` 现有模式（`_is_global_admin` / `can_manage_students` / `get_class_role`），新增 `can_award_badge` / `can_manage_credits` 等细粒度检查函数放在 `app/utils/student_ops_access.py`。

### 0.2 命名规范（照抄叙阅现状）

| 层级 | 规范 | 示例 |
|------|------|------|
| 主键 | `VARCHAR(36)` + `gen_uuid()` | `id = Column(String(36), primary_key=True, default=gen_uuid)` |
| 外键 | `String(36)`, `ForeignKey("xxx.id", ...)` | `student_id = Column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)` |
| 时间 | `DateTime(timezone=True)` + `func.now()` | `created_at = Column(DateTime(timezone=True), server_default=func.now())` |
| 表名 | 复数 snake_case | `badge_definitions`, `credit_accounts` |
| 字段名 | snake_case | `student_id`, `points_awarded` |
| JSON 响应 | camelCase | `studentId`, `pointsAwarded` |
| MySQL DDL | utf8mb4_unicode_ci, ENGINE=InnoDB | — |
| Python 模型 | `class Xxx(Base): __tablename__ = "xxx"` | — |

### 0.3 统一错误码

| HTTP 码 | error | 触发条件 |
|---------|-------|---------|
| 400 | `validation_error` | 参数格式错误/缺少必填项 |
| 400 | `insufficient_balance` | 积分不足，无法兑换 |
| 400 | `out_of_stock` | 商品库存不足 |
| 400 | `duplicate_entry` | 重复操作（如已颁过该章） |
| 401 | `unauthorized` | 未登录或 token 过期 |
| 403 | `forbidden` | 无权限操作（非本班教师/角色不足） |
| 404 | `not_found` | 目标学生/章/商品/记录不存在 |
| 409 | `stock_conflict` | 并发兑换导致库存冲突 |
| 500 | `internal_error` | 服务端异常 |

---

## 1. 表结构（MySQL DDL）

### 1.1 争章颁章

#### badge_definitions — 章定义

```sql
CREATE TABLE badge_definitions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name VARCHAR(128) NOT NULL COMMENT '章名称',
    description VARCHAR(512) NULL COMMENT '章描述',
    badge_type VARCHAR(32) NOT NULL DEFAULT 'school_based' COMMENT '章类型: red_scarf=红领巾章, school_based=校本特色章',
    category VARCHAR(32) NOT NULL DEFAULT 'moral' COMMENT '归属五育维度: moral=德, intellectual=智, physical=体, aesthetic=美, labor=劳',
    icon_url VARCHAR(512) NULL COMMENT '章图标URL',
    points_awarded INT NOT NULL DEFAULT 10 COMMENT '获得该章奖励的积分数',
    min_grade VARCHAR(16) NULL COMMENT '最低适用年级, 如 小学一年级',
    max_grade VARCHAR(16) NULL COMMENT '最高适用年级, NULL表示不限',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用: 0=停用, 1=启用',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '排序序号',
    created_by VARCHAR(36) NOT NULL COMMENT '创建人 user_id',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_badge_def_type (badge_type),
    INDEX idx_badge_def_category (category),
    INDEX idx_badge_def_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='章定义表';
```

#### badge_awards — 颁章记录

```sql
CREATE TABLE badge_awards (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID',
    badge_definition_id VARCHAR(36) NOT NULL COMMENT '章定义ID',
    class_id VARCHAR(36) NOT NULL COMMENT '班级ID',
    awarded_by VARCHAR(36) NOT NULL COMMENT '颁发人 user_id',
    award_date DATE NOT NULL COMMENT '颁发日期',
    reason VARCHAR(512) NULL COMMENT '颁章事由',
    credit_transaction_id VARCHAR(36) NULL COMMENT '关联的学分流水ID（颁章入账）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_badge_award_student (student_id),
    INDEX idx_badge_award_def (badge_definition_id),
    INDEX idx_badge_award_class (class_id),
    INDEX idx_badge_award_date (award_date),
    UNIQUE KEY uk_student_badge_date (student_id, badge_definition_id, award_date),
    CONSTRAINT fk_badge_award_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_badge_award_def FOREIGN KEY (badge_definition_id) REFERENCES badge_definitions(id) ON DELETE RESTRICT,
    CONSTRAINT fk_badge_award_class FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_badge_award_user FOREIGN KEY (awarded_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='颁章记录表';
```

> **设计说明**：`uk_student_badge_date` 防止同一学生在同一天被重复授予同一枚章。

---

### 1.2 学分银行

#### credit_accounts — 积分账户

```sql
CREATE TABLE credit_accounts (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID',
    balance INT NOT NULL DEFAULT 0 COMMENT '当前可用积分余额',
    total_earned INT NOT NULL DEFAULT 0 COMMENT '历史累计获得积分',
    total_spent INT NOT NULL DEFAULT 0 COMMENT '历史累计消费积分',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_credit_account_student (student_id),
    CONSTRAINT fk_credit_account_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='积分账户表（每学生一行）';
```

> **设计说明**：账户随学生创建自动初始化（触发器或服务层懒初始化），初始余额 0。

#### credit_transactions — 积分流水

```sql
CREATE TABLE credit_transactions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID',
    class_id VARCHAR(36) NOT NULL COMMENT '班级ID（冗余，便于报表）',
    amount INT NOT NULL COMMENT '变动金额（正=入账, 负=扣减）',
    transaction_type VARCHAR(32) NOT NULL COMMENT '流水类型: badge_award=颁章入账, manual_add=教师手动加分, redemption=兑换扣减, manual_deduct=教师手动扣分, adjustment=系统调账, expire=过期清零',
    balance_after INT NOT NULL COMMENT '变动后余额',
    source_type VARCHAR(64) NULL COMMENT '来源类型: badge_definition / reward_product / manual',
    source_id VARCHAR(36) NULL COMMENT '来源记录ID（如 badge_awards.id / redemption_records.id）',
    operator_id VARCHAR(36) NOT NULL COMMENT '操作人 user_id',
    description VARCHAR(512) NULL COMMENT '备注说明',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ct_student (student_id),
    INDEX idx_ct_class (class_id),
    INDEX idx_ct_type (transaction_type),
    INDEX idx_ct_created (created_at),
    INDEX idx_ct_source (source_type, source_id),
    CONSTRAINT fk_ct_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_ct_class FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_ct_operator FOREIGN KEY (operator_id) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='积分流水表';
```

> **设计说明**：`balance_after` 用于快速展示余额曲线，避免每笔流水都需重新计算；`class_id` 冗余字段便于按班级出报表。

#### reward_products — 兑换商品

```sql
CREATE TABLE reward_products (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name VARCHAR(255) NOT NULL COMMENT '商品名称',
    description VARCHAR(1024) NULL COMMENT '商品描述',
    image_url VARCHAR(512) NULL COMMENT '商品图片URL',
    product_type VARCHAR(16) NOT NULL DEFAULT 'physical' COMMENT '商品类型: virtual=虚拟奖励（免作业卡等）, physical=实物兑换',
    points_required INT NOT NULL COMMENT '所需积分',
    stock INT NOT NULL DEFAULT 0 COMMENT '库存（实物商品有效，虚拟商品填9999表示不限）',
    stock_warning INT NOT NULL DEFAULT 5 COMMENT '库存预警阈值',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否上架: 0=下架, 1=上架',
    exchange_limit_per_student INT NOT NULL DEFAULT 0 COMMENT '每学生兑换上限, 0=不限',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '排序序号',
    created_by VARCHAR(36) NOT NULL COMMENT '创建人 user_id',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_rp_active (is_active),
    INDEX idx_rp_type (product_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='兑换商品表';
```

#### redemption_records — 兑换记录

```sql
CREATE TABLE redemption_records (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID',
    product_id VARCHAR(36) NOT NULL COMMENT '商品ID',
    class_id VARCHAR(36) NOT NULL COMMENT '班级ID',
    points_spent INT NOT NULL COMMENT '消耗积分',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '状态: pending=待处理, approved=已审核, delivered=已发放, cancelled=已取消',
    operator_id VARCHAR(36) NOT NULL COMMENT '操作教师 user_id（代学生兑换的教师）',
    approver_id VARCHAR(36) NULL COMMENT '审核人 user_id',
    approved_at DATETIME NULL COMMENT '审核时间',
    delivered_at DATETIME NULL COMMENT '发放时间',
    notes VARCHAR(512) NULL COMMENT '备注',
    credit_transaction_id VARCHAR(36) NULL COMMENT '关联的积分流水ID（扣减流水）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_rr_student (student_id),
    INDEX idx_rr_product (product_id),
    INDEX idx_rr_class (class_id),
    INDEX idx_rr_status (status),
    INDEX idx_rr_created (created_at),
    CONSTRAINT fk_rr_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_rr_product FOREIGN KEY (product_id) REFERENCES reward_products(id) ON DELETE RESTRICT,
    CONSTRAINT fk_rr_class FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_rr_operator FOREIGN KEY (operator_id) REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_rr_approver FOREIGN KEY (approver_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='兑换记录表';
```

---

### 1.3 校外实践

#### practice_records — 校外实践记录

```sql
CREATE TABLE practice_records (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID',
    class_id VARCHAR(36) NOT NULL COMMENT '班级ID',
    practice_type VARCHAR(32) NOT NULL COMMENT '实践类型: housework=家务劳动, volunteer=志愿服务, talent=校外才艺, study_tour=研学活动',
    title VARCHAR(255) NOT NULL COMMENT '实践标题',
    description TEXT NULL COMMENT '实践描述',
    practice_date DATE NOT NULL COMMENT '实践日期',
    duration_hours DECIMAL(4,1) NULL COMMENT '时长（小时）',
    location VARCHAR(255) NULL COMMENT '地点',
    evidence_images JSON NULL COMMENT '佐证图片列表, JSON数组, 元素为 {url, thumb_url, upload_at}',
    status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '状态: pending=待审核, approved=已通过, rejected=已驳回',
    reviewer_id VARCHAR(36) NULL COMMENT '审核人 user_id',
    review_comment VARCHAR(512) NULL COMMENT '审核意见',
    reviewed_at DATETIME NULL COMMENT '审核时间',
    credit_transaction_id VARCHAR(36) NULL COMMENT '关联学分流水ID（审核通过时入账）',
    recorded_by VARCHAR(36) NOT NULL COMMENT '录入人 user_id（代学生录入的教师）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_pr_student (student_id),
    INDEX idx_pr_class (class_id),
    INDEX idx_pr_type (practice_type),
    INDEX idx_pr_status (status),
    INDEX idx_pr_date (practice_date),
    CONSTRAINT fk_pr_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_pr_class FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_pr_reviewer FOREIGN KEY (reviewer_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_pr_recorded_by FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='校外实践记录表';
```

> **`evidence_images` JSON 格式**：
> ```json
> [
>   {"url": "student_ops/practice/{practice_id}/img_001.jpg", "thumb_url": "student_ops/practice/{practice_id}/thumb/img_001.jpg", "upload_at": "2026-08-11T10:30:00Z"},
>   {"url": "student_ops/practice/{practice_id}/img_002.jpg", "thumb_url": "student_ops/practice/{practice_id}/thumb/img_002.jpg", "upload_at": "2026-08-11T10:31:00Z"}
> ]
> ```
> 图片通过 download ticket 机制访问，路径中的 `student_ops/...` 为 `build_download_url(resource, user_id)` 的 `resource` 参数。
> **单条实践记录图片上限 9 张，单张大小 ≤ 10MB，格式限定 JPG/PNG/HEIC。**

---

### 1.4 校园生活

#### campus_clubs — 社团

```sql
CREATE TABLE campus_clubs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name VARCHAR(128) NOT NULL COMMENT '社团名称',
    description VARCHAR(1024) NULL COMMENT '社团简介',
    teacher_id VARCHAR(36) NULL COMMENT '负责教师 user_id',
    max_members INT NOT NULL DEFAULT 0 COMMENT '人数上限, 0=不限',
    is_active TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_club_teacher (teacher_id),
    CONSTRAINT fk_club_teacher FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='社团表';
```

#### club_enrollments — 社团报名

```sql
CREATE TABLE club_enrollments (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID',
    club_id VARCHAR(36) NOT NULL COMMENT '社团ID',
    class_id VARCHAR(36) NOT NULL COMMENT '班级ID',
    status VARCHAR(16) NOT NULL DEFAULT 'enrolled' COMMENT '状态: enrolled=在团, left=已退出',
    enrolled_at DATE NOT NULL COMMENT '入团日期',
    left_at DATE NULL COMMENT '退团日期',
    recorded_by VARCHAR(36) NOT NULL COMMENT '录入党人 user_id',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_ce_student (student_id),
    INDEX idx_ce_club (club_id),
    INDEX idx_ce_class (class_id),
    INDEX idx_ce_status (status),
    UNIQUE KEY uk_student_club (student_id, club_id),
    CONSTRAINT fk_ce_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_ce_club FOREIGN KEY (club_id) REFERENCES campus_clubs(id) ON DELETE CASCADE,
    CONSTRAINT fk_ce_class FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_ce_recorded_by FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='社团报名表';
```

#### club_attendance — 社团考勤

```sql
CREATE TABLE club_attendance (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID',
    club_id VARCHAR(36) NOT NULL COMMENT '社团ID',
    class_id VARCHAR(36) NOT NULL COMMENT '班级ID',
    session_date DATE NOT NULL COMMENT '活动日期',
    attend_status VARCHAR(16) NOT NULL DEFAULT 'present' COMMENT '状态: present=出席, absent=缺勤, leave=请假',
    remarks VARCHAR(255) NULL COMMENT '备注',
    recorded_by VARCHAR(36) NOT NULL COMMENT '记录人 user_id',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_ca_student (student_id),
    INDEX idx_ca_club (club_id),
    INDEX idx_ca_date (session_date),
    UNIQUE KEY uk_student_club_date (student_id, club_id, session_date),
    CONSTRAINT fk_ca_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_ca_club FOREIGN KEY (club_id) REFERENCES campus_clubs(id) ON DELETE CASCADE,
    CONSTRAINT fk_ca_class FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_ca_recorded_by FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='社团考勤表';
```

#### book_borrows — 图书借阅

```sql
CREATE TABLE book_borrows (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID',
    class_id VARCHAR(36) NOT NULL COMMENT '班级ID',
    book_title VARCHAR(255) NOT NULL COMMENT '书名',
    book_isbn VARCHAR(32) NULL COMMENT 'ISBN',
    book_author VARCHAR(128) NULL COMMENT '作者',
    borrowed_at DATETIME NOT NULL COMMENT '借阅时间',
    due_at DATETIME NOT NULL COMMENT '应还时间',
    returned_at DATETIME NULL COMMENT '实际归还时间',
    status VARCHAR(16) NOT NULL DEFAULT 'borrowed' COMMENT '状态: borrowed=借阅中, returned=已归还, overdue=已逾期',
    recorded_by VARCHAR(36) NOT NULL COMMENT '记录人 user_id',
    notes VARCHAR(512) NULL COMMENT '备注',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_bb_student (student_id),
    INDEX idx_bb_class (class_id),
    INDEX idx_bb_status (status),
    INDEX idx_bb_due (due_at),
    CONSTRAINT fk_bb_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_bb_class FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_bb_recorded_by FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='图书借阅表';
```

#### reading_records — 阅读榜单（阅读打卡记录）

```sql
CREATE TABLE reading_records (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID',
    class_id VARCHAR(36) NOT NULL COMMENT '班级ID',
    book_title VARCHAR(255) NOT NULL COMMENT '书名',
    pages_read INT NOT NULL DEFAULT 0 COMMENT '本次阅读页数',
    reading_minutes INT NOT NULL DEFAULT 0 COMMENT '本次阅读时长（分钟）',
    reading_date DATE NOT NULL COMMENT '阅读日期',
    recorded_by VARCHAR(36) NOT NULL COMMENT '记录人 user_id',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_rr_student (student_id),
    INDEX idx_rr_class (class_id),
    INDEX idx_rr_date (reading_date),
    CONSTRAINT fk_reading_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_reading_class FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_reading_recorded_by FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='阅读记录表';
```

> **阅读榜单口径**：榜单为实时聚合查询（见 2.5 报表口径），不建物化表，通过 `group by student_id, class_id` + `sum(pages_read)` 或 `sum(reading_minutes)` + 日期范围过滤实现周榜/月榜/学期榜。

#### health_checks — 晨午检记录

```sql
CREATE TABLE health_checks (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL COMMENT '学生ID',
    class_id VARCHAR(36) NOT NULL COMMENT '班级ID',
    check_type VARCHAR(16) NOT NULL COMMENT '检查类型: morning=晨检, afternoon=午检',
    check_date DATE NOT NULL COMMENT '检查日期',
    temperature DECIMAL(3,1) NULL COMMENT '体温（℃）',
    health_status VARCHAR(16) NOT NULL DEFAULT 'normal' COMMENT '健康状态: normal=正常, abnormal=异常',
    symptoms VARCHAR(512) NULL COMMENT '异常症状描述（如头痛、咳嗽、发热等）',
    is_alert TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否触发预警: 0=否, 1=是（体温≥37.3 或 health_status=abnormal 时自动标记）',
    handled_by VARCHAR(36) NULL COMMENT '处理人 user_id',
    handle_notes VARCHAR(512) NULL COMMENT '处理备注',
    recorded_by VARCHAR(36) NOT NULL COMMENT '记录人 user_id',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_hc_student (student_id),
    INDEX idx_hc_class (class_id),
    INDEX idx_hc_date (check_date),
    INDEX idx_hc_alert (is_alert),
    UNIQUE KEY uk_student_check (student_id, check_type, check_date),
    CONSTRAINT fk_hc_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_hc_class FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    CONSTRAINT fk_hc_handler FOREIGN KEY (handled_by) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_hc_recorded_by FOREIGN KEY (recorded_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='晨午检记录表';
```

> **预警规则**：
> - 体温 ≥ 37.3℃ → 自动标记 `is_alert=1`, `health_status='abnormal'`
> - 手动设置 `health_status='abnormal'` → 自动标记 `is_alert=1`
> - 同一学生连续 3 天出现异常 → 在教师端管理面板弹出高亮提醒
> 
> **物理实现建议**：创建 `health_checks` 的 insert/update 触发器，或在后端 service 层做前置校验后一次性写入。

---

### 1.5 ER 关系简图

```
students
  ├── 1:N ── badge_awards ── N:1 ── badge_definitions
  ├── 1:1 ── credit_accounts
  ├── 1:N ── credit_transactions
  ├── 1:N ── redemption_records ── N:1 ── reward_products
  ├── 1:N ── practice_records
  ├── 1:N ── club_enrollments ── N:1 ── campus_clubs
  ├── 1:N ── club_attendance ── N:1 ── campus_clubs
  ├── 1:N ── book_borrows
  ├── 1:N ── reading_records
  └── 1:N ── health_checks

users
  ├── 1:N ── badge_awards (awarded_by)
  ├── 1:N ── credit_transactions (operator_id)
  ├── 1:N ── redemption_records (operator_id / approver_id)
  ├── 1:N ── practice_records (recorded_by / reviewer_id)
  ├── 1:N ── campus_clubs (teacher_id)
  ├── 1:N ── health_checks (recorded_by / handled_by)
  └── 1:N ── 各种 recorded_by

classes
  └── 1:N ── 几乎全部子表 (冗余 class_id 便于报表)
```

---

## 2. 积分联动规则

### 2.1 颁章 → 学分入账

| 触发事件 | 流水类型 | 积分变动 | 操作 |
|---------|---------|---------|------|
| 教师颁发 badge | `badge_award` | `+badge_definitions.points_awarded` | 1. 写入 `badge_awards`<br>2. 写入 `credit_transactions` (amount=+points)<br>3. 更新 `credit_accounts.balance += points`, `total_earned += points`<br>4. 回写 `badge_awards.credit_transaction_id` |
| 教师手动加分 | `manual_add` | `+任意正整数` | 1. 写入 `credit_transactions`<br>2. 更新 `credit_accounts` |
| 教师手动扣分 | `manual_deduct` | `-任意正整数` | 1. 写入 `credit_transactions`（扣减后余额不能为负）<br>2. 更新 `credit_accounts` |
| 实践审核通过 | `practice_approved` | `+固定值（建议50分/次）` | 1. 审核通过后写入 `credit_transactions`<br>2. 更新 `credit_accounts`<br>3. 回写 `practice_records.credit_transaction_id` |

### 2.2 兑换扣减规则

```
兑换 = 教师代学生在管理端操作

前提条件（任一不满足即拒绝）：
  A. credit_accounts.balance >= reward_products.points_required
  B. reward_products.stock > 0（实物）或 product_type = 'virtual'（不限库存）
  C. reward_products.is_active = 1
  D. 该学生对该商品的兑换次数（本月/总计）未超 exchange_limit_per_student（0=不限）

扣减流程（必须在同一数据库事务中完成）：
  1. SELECT ... FOR UPDATE 锁住 credit_accounts 行和 reward_products 行
  2. 验证 A/B/C/D
  3. INSERT 一条 redemption_records（status=pending）
  4. UPDATE credit_accounts SET balance = balance - points, total_spent = total_spent + points
  5. INSERT 一条 credit_transactions（amount=-points, type=redemption, source_type=reward_product, source_id=redemption.id）
  6. 回写 redemption_records.credit_transaction_id
  7. UPDATE reward_products SET stock = stock - 1（仅实物）
  8. COMMIT
```

> **库存原子性**：第 1 步的 `SELECT ... FOR UPDATE` 是关键——MySQL 行锁保证并发兑换不会超卖。代码中对应 `db.query(CreditAccount).filter(...).with_for_update().first()` 和 `db.query(RewardProduct).filter(...).with_for_update().first()`。

### 2.3 兑换审核与发放流程

```
pending → (管理员审核)
  ├─ approved → (教师发放) → delivered
  └─ cancelled (退分: 回滚 balance + total_spent, stock + 1, 写一条 adjustment 流水)
```

退分逻辑：
```
取消兑换 →
  1. UPDATE credit_accounts SET balance = balance + points_spent, total_spent = total_spent - points_spent
  2. INSERT credit_transactions (amount=+points_spent, type=adjustment, description="兑换取消退分, 原兑换ID={id}")
  3. UPDATE reward_products SET stock = stock + 1（仅实物）
  4. UPDATE redemption_records SET status = 'cancelled'
```

### 2.4 数据一致性保障

| 场景 | 保障机制 |
|------|---------|
| 颁章后积分未入账 | 同一事务内完成 badge_award + credit_transaction + credit_account 更新 |
| 并发兑换超卖 | `SELECT ... FOR UPDATE` 行锁 |
| 事务中途失败 | 全部回滚（SQLAlchemy `db.commit()` 异常时 `db.rollback()`） |
| 历史余额对账 | `SUM(credit_transactions.amount)` 应等于 `credit_accounts.balance + total_spent - total_earned` 的累积差。提供对账 API 供管理员按学生/班级抽查 |

### 2.5 报表口径

| 报表 | 查询口径 | 索引利用 |
|------|---------|---------|
| 班级积分排行 | `SELECT class_id, SUM(balance) as total FROM credit_accounts GROUP BY class_id ORDER BY total DESC` | `credit_accounts` 关联 `students.class_id` |
| 学生积分明细 | `SELECT * FROM credit_transactions WHERE student_id=? ORDER BY created_at DESC` | `idx_ct_student` |
| 兑换统计 | `SELECT product_id, COUNT(*), SUM(points_spent) FROM redemption_records WHERE status='delivered' GROUP BY product_id` | `idx_rr_status` |
| 章获取统计 | `SELECT badge_definition_id, COUNT(DISTINCT student_id) FROM badge_awards GROUP BY badge_definition_id` | `idx_badge_award_def` |
| 阅读榜单（周/月/学期） | `SELECT student_id, class_id, SUM(pages_read) as total_pages, SUM(reading_minutes) as total_minutes FROM reading_records WHERE reading_date BETWEEN ? AND ? GROUP BY student_id, class_id ORDER BY total_pages DESC LIMIT 100` | `idx_rr_date` |
| 健康异常汇总 | `SELECT class_id, check_date, COUNT(*) as alert_count FROM health_checks WHERE is_alert=1 AND check_date BETWEEN ? AND ? GROUP BY class_id, check_date` | `idx_hc_alert`, `idx_hc_date` |
| 实践审核待办 | `SELECT * FROM practice_records WHERE status='pending' ORDER BY created_at` | `idx_pr_status` |
| 借阅逾期 | `SELECT * FROM book_borrows WHERE due_at < NOW() AND returned_at IS NULL` | `idx_bb_due` |

---

## 3. 图片佐证方案

### 3.1 决策：新建上传接口，复用 download ticket 机制

叙阅现有下载票机制：
- `create_download_ticket(user_id, resource)` — 签发 10 分钟短时票
- `verify_download_ticket(token, resource)` — 校票
- `build_download_url(resource, user_id)` — 生成带票直链

**方案**：

**(A) 上传接口（新建）**

```
POST /api/v1/student-ops/upload-evidence
```

- 接收 `multipart/form-data`，文件字段名 `file`
- 可选参数 `practice_id`（若已保存实践记录可关联），若无则返回临时 URL
- 后端处理：
  1. 校验文件类型（JPG/PNG/HEIC）和大小（≤10MB）
  2. 生成唯一文件名 `{uuid4}.{ext}`
  3. 存储到 `{project_root}/grading_data_all/student_ops/practice/evidence/{YYYY-MM}/{filename}`
  4. 生成缩略图（宽 400px，Pillow 库）到同目录 `thumb/{filename}`
  5. 返回上传后的 URL 路径（不带票），前端组装为相对路径存入 `evidence_images` JSON

**(B) 查看/下载接口（复用现有 download ticket 模式）**

- 新建静态文件挂载端点：
  ```python
  # app/routers/student_ops.py
  from fastapi.staticfiles import StaticFiles
  # 或在现有 app/main.py 中添加 mount
  app.mount("/api/v1/student-ops/files", StaticFiles(directory=STUDENT_OPS_ROOT), name="student_ops_files")
  ```
- 访问时通过 `file_auth.user_id_from_request(request, resource="student_ops/...")` 校验 ticket
- 前端获取图片 URL 时调用 `GET /api/v1/student-ops/get-file-url?path=student_ops/practice/evidence/2026-08/abc123.jpg`，后端返回带 download ticket 的临时直链

**(C) 存储目录结构**

```
grading_data_all/
└── student_ops/
    └── practice/
        └── evidence/
            ├── 2026-08/
            │   ├── abc123.jpg
            │   └── thumb/
            │       └── abc123.jpg
            └── 2026-09/
                └── ...
```

### 3.2 图片生命周期

- **上传时机**：教师在实践记录表单中上传（支持拖拽多图、批量上传）
- **删除时机**：实践记录删除时，后端同步删除 `evidence_images` 中的文件（可选：先标记后定期清理，避免误删）
- **存储限制**：初期单校使用无上限限制，但后端做个软限制（每学生每学期最多 500 张）便于运维

---

## 4. API 契约

> 基础路径: `/api/v1/student-ops`
> 所有接口需要鉴权，Header: `Authorization: Bearer {JWT_TOKEN}`

### 4.0 通用响应格式

```json
// 成功
{ "code": 0, "message": "success", "data": { ... } }

// 失败
{ "code": 0, "error": "error_code", "message": "人类可读描述", "data": null }
```

分页格式：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [...],
    "total": 150,
    "page": 1,
    "pageSize": 20
  }
}
```

---

### 4.1 争章颁章

#### GET /student-ops/badge-definitions

**用途**：获取章定义列表
**鉴权**：需要（任意已登录教师）

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| badgeType | string | 否 | 筛选类型: red_scarf / school_based |
| category | string | 否 | 筛选五育维度: moral / intellectual / physical / aesthetic / labor |
| isActive | boolean | 否 | 筛选启用状态 |
| page | int | 否 | 页码，默认 1 |
| pageSize | int | 否 | 每页条数，默认 20 |

**成功响应 (200)**：
```json
{
  "data": {
    "items": [
      {
        "id": "uuid-badge-001",
        "name": "红领巾基础章",
        "description": "完成一学期少先队基础任务",
        "badgeType": "red_scarf",
        "category": "moral",
        "iconUrl": "student_ops/badges/red_scarf_basic.png",
        "pointsAwarded": 50,
        "minGrade": "小学一年级",
        "maxGrade": "小学六年级",
        "isActive": true,
        "sortOrder": 1,
        "createdAt": "2026-08-11T10:00:00Z"
      }
    ],
    "total": 25,
    "page": 1,
    "pageSize": 20
  }
}
```

---

#### POST /student-ops/badge-definitions

**用途**：创建章定义（系统管理员/子系统管理员）
**鉴权**：需要（admin）

**请求体**：
```json
{
  "name": "红领巾基础章",
  "description": "完成一学期少先队基础任务",
  "badgeType": "red_scarf",
  "category": "moral",
  "iconUrl": null,
  "pointsAwarded": 50,
  "minGrade": "小学一年级",
  "maxGrade": "小学六年级",
  "isActive": true,
  "sortOrder": 1
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 章名称，最多 128 字符 |
| badgeType | string | 是 | red_scarf / school_based |
| category | string | 是 | moral / intellectual / physical / aesthetic / labor |
| pointsAwarded | int | 是 | 获得该章的奖励积分，≥1 |
| minGrade | string | 否 | 最低适用年级 |
| maxGrade | string | 否 | 最高适用年级 |
| isActive | boolean | 否 | 默认 true |

**成功响应 (200)**：返回完整 badge_definition 对象（同上）

**错误响应**：

| 状态码 | error | 触发条件 |
|--------|-------|---------|
| 403 | `forbidden` | 非管理员 |
| 400 | `validation_error` | name 为空或重复 |

---

#### PATCH /student-ops/badge-definitions/{badge_id}

**用途**：编辑章定义
**鉴权**：需要（admin）

请求体和响应同 POST，所有字段选填，仅更新传入的非 null 字段。

---

#### DELETE /student-ops/badge-definitions/{badge_id}

**用途**：删除章定义（软删除：set is_active=0）
**鉴权**：需要（admin）

**限制**：已有颁章记录的章不允许物理删除，仅可停用。

**错误响应**：

| 状态码 | error | 触发条件 |
|--------|-------|---------|
| 404 | `not_found` | 章定义不存在 |
| 403 | `forbidden` | 非管理员 |

---

#### POST /student-ops/badge-awards

**用途**：教师颁章（单人或批量）
**鉴权**：需要（班主任/副班主任/全局管理员）

**请求体（单个）**：
```json
{
  "studentIds": ["uuid-student-001"],
  "badgeDefinitionId": "uuid-badge-001",
  "awardDate": "2026-08-11",
  "reason": "本学期积极参加少先队活动"
}
```

**请求体（批量，同一枚章颁给多人）**：
```json
{
  "studentIds": ["uuid-student-001", "uuid-student-002", "uuid-student-003"],
  "badgeDefinitionId": "uuid-badge-001",
  "awardDate": "2026-08-11",
  "reason": "本学期积极参加少先队活动"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| studentIds | string[] | 是 | 学生ID列表，最多 200 人 |
| badgeDefinitionId | string | 是 | 章定义ID |
| awardDate | string | 是 | 颁发日期 (YYYY-MM-DD) |
| reason | string | 否 | 颁章事由 |

**成功响应 (200)**：
```json
{
  "data": {
    "successCount": 3,
    "failCount": 0,
    "failures": [],
    "awards": [
      {
        "id": "uuid-award-001",
        "studentId": "uuid-student-001",
        "studentName": "张三",
        "badgeDefinitionName": "红领巾基础章",
        "pointsEarned": 50,
        "awardDate": "2026-08-11"
      }
    ]
  }
}
```

**failures 结构**：
```json
{ "studentId": "uuid-xxx", "studentName": "李四", "reason": "duplicate_entry | student_not_found | no_permission" }
```

**注意事项**：
- 批量颁章内每个学生独立事务（一个失败不影响其他），最终返回汇总
- 重复颁章（同学生+同章+同日期）返回 `duplicate_entry`，不计入 success
- 每个成功颁章自动触发学分入账（±对应章定义的 points_awarded）

---

#### GET /student-ops/badge-awards

**用途**：查询颁章记录
**鉴权**：需要（教师可看所管班级，管理员看全校）

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| classId | string | 否 | 按班级筛选 |
| studentId | string | 否 | 按学生筛选 |
| badgeDefinitionId | string | 否 | 按章类型筛选 |
| startDate | string | 否 | 颁发开始日期 |
| endDate | string | 否 | 颁发结束日期 |
| page | int | 否 | 页码 |
| pageSize | int | 否 | 每页条数 |

**成功响应 (200)**：分页返回 badge_awards 列表，包含 studentName、badgeName 等联表字段。

---

#### DELETE /student-ops/badge-awards/{award_id}

**用途**：撤销颁章（同时回滚关联学分）
**鉴权**：需要（管理员/颁发人本人）

**撤销逻辑**：
1. 查找关联 `credit_transaction_id`
2. 若已有关联积分流水且未被后续操作影响（流水为最近一条且 balance 足够），则回滚积分（credit_accounts.balance -= points, total_earned -= points，写 adjustment 流水）
3. 物理删除 badge_award 记录

**错误响应**：

| 状态码 | error | 触发条件 |
|--------|-------|---------|
| 404 | `not_found` | 记录不存在 |
| 403 | `forbidden` | 非管理员且非颁发人本人 |
| 409 | `credit_rollback_failed` | 积分已后续变动，无法安全回滚（此时仅删除颁章记录，不退分，需人工处理） |

---

### 4.2 学分银行

#### GET /student-ops/credit-accounts

**用途**：查询学生积分账户（按班级聚合）
**鉴权**：需要

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| classId | string | 否 | 按班级筛选（不传则返回所管全部班级） |
| sortBy | string | 否 | 排序: balance_desc(默认) / balance_asc / total_earned_desc |
| page | int | 否 | 页码 |
| pageSize | int | 否 | 每页条数 |

**成功响应 (200)**：
```json
{
  "data": {
    "items": [
      {
        "accountId": "uuid-account-001",
        "studentId": "uuid-student-001",
        "studentName": "张三",
        "className": "小学一年级1班",
        "balance": 320,
        "totalEarned": 500,
        "totalSpent": 180,
        "updatedAt": "2026-08-11T15:30:00Z"
      }
    ],
    "total": 45,
    "page": 1,
    "pageSize": 20
  }
}
```

---

#### GET /student-ops/credit-transactions

**用途**：查询积分流水
**鉴权**：需要

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| studentId | string | 否 | 按学生筛选 |
| classId | string | 否 | 按班级筛选 |
| transactionType | string | 否 | 按类型筛选: badge_award / manual_add / redemption / manual_deduct / adjustment |
| startDate | string | 否 | 开始日期 |
| endDate | string | 否 | 结束日期 |
| page | int | 否 | 页码 |
| pageSize | int | 否 | 每页条数 |

**成功响应 (200)**：
```json
{
  "data": {
    "items": [
      {
        "id": "uuid-txn-001",
        "studentId": "uuid-student-001",
        "studentName": "张三",
        "className": "小学一年级1班",
        "amount": 50,
        "transactionType": "badge_award",
        "balanceAfter": 370,
        "sourceType": "badge_definition",
        "sourceId": "uuid-badge-001",
        "description": "获得【红领巾基础章】",
        "operatorName": "王老师",
        "createdAt": "2026-08-11T10:30:00Z"
      }
    ],
    "total": 120,
    "page": 1,
    "pageSize": 20
  }
}
```

---

#### POST /student-ops/credit-transactions/manual

**用途**：教师手动加减分
**鉴权**：需要（班主任/副班主任/管理员）

**请求体**：
```json
{
  "studentId": "uuid-student-001",
  "amount": 10,
  "description": "课堂表现优秀额外奖励"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| studentId | string | 是 | 学生ID |
| amount | int | 是 | 变动金额，正=加分，负=扣分（不能使余额为负） |
| description | string | 是 | 必填备注，最多 512 字符 |

**错误响应**：

| 状态码 | error | 触发条件 |
|--------|-------|---------|
| 400 | `insufficient_balance` | 扣分超过当前余额 |
| 403 | `forbidden` | 无该学生班级管理权限 |
| 404 | `not_found` | 学生不存在 |

---

#### GET /student-ops/credit-report

**用途**：积分报表
**鉴权**：需要

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| classId | string | 否 | 按班级 |
| grade | string | 否 | 按年级 |
| startDate | string | 否 | 统计开始 |
| endDate | string | 否 | 统计结束 |
| groupBy | string | 否 | 聚合维度: class(默认) / grade / transaction_type |

**成功响应 (200)**：
```json
{
  "data": {
    "summary": {
      "totalStudents": 500,
      "totalBalance": 125000,
      "avgBalance": 250,
      "totalEarnedPeriod": 32000,
      "totalSpentPeriod": 18500
    },
    "byClass": [
      {
        "classId": "uuid-class-001",
        "className": "小学一年级1班",
        "studentCount": 45,
        "totalBalance": 11250,
        "avgBalance": 250,
        "earnedPeriod": 3200,
        "spentPeriod": 1800
      }
    ],
    "byType": [
      { "type": "badge_award", "totalAmount": 20000, "count": 400 },
      { "type": "manual_add", "totalAmount": 5000, "count": 100 },
      { "type": "redemption", "totalAmount": -15000, "count": 300 }
    ]
  }
}
```

---

### 4.3 兑换管理

#### GET /student-ops/reward-products

**用途**：商品列表
**鉴权**：需要

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| productType | string | 否 | virtual / physical |
| isActive | boolean | 否 | 上架状态 |
| keyword | string | 否 | 名称模糊搜索 |
| page | int | 否 | 页码 |
| pageSize | int | 否 | 每页条数 |

**成功响应 (200)**：分页返回 reward_products 列表。

---

#### POST /student-ops/reward-products

**用途**：创建商品
**鉴权**：需要（管理员）

**请求体**：
```json
{
  "name": "免作业卡",
  "description": "可免一次当天家庭作业",
  "productType": "virtual",
  "pointsRequired": 100,
  "stock": 9999,
  "isActive": true,
  "exchangeLimitPerStudent": 3
}
```

---

#### PATCH /student-ops/reward-products/{product_id}

**用途**：编辑商品
**鉴权**：需要（管理员）

请求体同 POST，字段选填。

---

#### DELETE /student-ops/reward-products/{product_id}

**用途**：下架商品（软删除 set is_active=0）
**鉴权**：需要（管理员）

---

#### POST /student-ops/redemptions

**用途**：教师代学生兑换
**鉴权**：需要（班主任/副班主任/管理员）

**请求体**：
```json
{
  "studentId": "uuid-student-001",
  "productId": "uuid-product-001"
}
```

**成功响应 (200)**：
```json
{
  "data": {
    "id": "uuid-redemption-001",
    "studentId": "uuid-student-001",
    "studentName": "张三",
    "productName": "免作业卡",
    "pointsSpent": 100,
    "balanceAfter": 220,
    "status": "pending"
  }
}
```

**错误响应**：

| 状态码 | error | 触发条件 |
|--------|-------|---------|
| 400 | `insufficient_balance` | 积分不足 |
| 400 | `out_of_stock` | 库存不足 |
| 400 | `limit_exceeded` | 超过每学生兑换上限 |
| 403 | `forbidden` | 无权限 |
| 409 | `stock_conflict` | 并发冲突，提示重试 |

---

#### GET /student-ops/redemptions

**用途**：查询兑换记录
**鉴权**：需要

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| classId | string | 否 | 按班级 |
| studentId | string | 否 | 按学生 |
| productId | string | 否 | 按商品 |
| status | string | 否 | pending / approved / delivered / cancelled |
| startDate | string | 否 | 开始时间 |
| endDate | string | 否 | 结束时间 |
| page | int | 否 | 页码 |
| pageSize | int | 否 | 每页条数 |

---

#### PATCH /student-ops/redemptions/{redemption_id}/status

**用途**：更新兑换状态（审核/发放/取消）
**鉴权**：需要（管理员）

**请求体**：
```json
{
  "status": "approved",
  "notes": "已核实"
}
```

**逻辑**：
- `pending → approved`：仅审核通过，不扣库存（已在兑换时扣减）
- `approved → delivered`：标记已发放（实物类）
- `pending/approved → cancelled`：退分+回库存（见 2.3 节）

---

### 4.4 校外实践

#### POST /student-ops/practice-records

**用途**：教师录入/编辑实践记录
**鉴权**：需要（班主任/副班主任/管理员）

**请求体**：
```json
{
  "studentId": "uuid-student-001",
  "practiceType": "volunteer",
  "title": "社区清洁志愿服务",
  "description": "参与社区周末清洁活动",
  "practiceDate": "2026-08-10",
  "durationHours": 2.5,
  "location": "子敬社区中心",
  "evidenceImages": [
    {"url": "student_ops/practice/evidence/2026-08/img_001.jpg", "thumbUrl": "student_ops/practice/evidence/2026-08/thumb/img_001.jpg", "uploadAt": "2026-08-11T10:30:00Z"}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| studentId | string | 是 | 学生ID |
| practiceType | string | 是 | housework / volunteer / talent / study_tour |
| title | string | 是 | 实践标题，最多 255 字符 |
| description | string | 否 | 描述 |
| practiceDate | string | 是 | 实践日期 (YYYY-MM-DD) |
| durationHours | number | 否 | 时长（小时），保留一位小数 |
| location | string | 否 | 地点 |
| evidenceImages | array | 否 | 佐证图片列表，最多 9 张 |

---

#### GET /student-ops/practice-records

**用途**：查询实践记录
**鉴权**：需要

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| classId | string | 否 | 按班级 |
| studentId | string | 否 | 按学生 |
| practiceType | string | 否 | 按类型 |
| status | string | 否 | pending / approved / rejected |
| startDate | string | 否 | 实践日期开始 |
| endDate | string | 否 | 实践日期结束 |
| page | int | 否 | 页码 |
| pageSize | int | 否 | 每页条数 |

---

#### PATCH /student-ops/practice-records/{record_id}

**用途**：编辑实践记录
**鉴权**：需要（录入人/管理员）

请求体同 POST，字段选填。

---

#### PATCH /student-ops/practice-records/{record_id}/review

**用途**：审核实践记录（通过/驳回）
**鉴权**：需要（管理员/年级组长）

**请求体**：
```json
{
  "status": "approved",
  "reviewComment": "活动真实，佐证完整"
}
```

**审核通过自动触发积分入账**（50 分/次，可配置），写入 `credit_transactions` + 更新 `credit_accounts`，回写 `practice_records.credit_transaction_id`。

---

#### DELETE /student-ops/practice-records/{record_id}

**用途**：删除实践记录
**鉴权**：需要（录入人/管理员）

**关联处理**：若已关联积分流水（已审核通过入账），删除时自动回滚积分（写 adjustment 流水）。

---

### 4.5 校园生活

#### 4.5.1 社团管理

| 端点 | 方法 | 说明 | 鉴权 |
|------|------|------|------|
| /student-ops/clubs | GET | 社团列表 | 需要 |
| /student-ops/clubs | POST | 创建社团 | 管理员 |
| /student-ops/clubs/{club_id} | PATCH | 编辑社团 | 管理员 |
| /student-ops/clubs/{club_id} | DELETE | 删除社团（软删除 set is_active=0） | 管理员 |
| /student-ops/clubs/{club_id}/enrollments | GET | 社团成员列表 | 需要 |
| /student-ops/club-enrollments | POST | 批量报名/导入成员 | 班主任/管理员 |
| /student-ops/club-enrollments/{enrollment_id} | PATCH | 更新报名状态（退团） | 班主任/管理员 |
| /student-ops/club-attendance | POST | 批量录入考勤 | 班主任/管理员 |
| /student-ops/club-attendance | GET | 考勤查询（按社团/日期） | 需要 |

**POST /student-ops/club-enrollments（批量报名）**：
```json
{
  "clubId": "uuid-club-001",
  "studentIds": ["uuid-student-001", "uuid-student-002"],
  "enrolledAt": "2026-08-11"
}
```

**POST /student-ops/club-attendance（批量考勤）**：
```json
{
  "clubId": "uuid-club-001",
  "sessionDate": "2026-08-11",
  "records": [
    { "studentId": "uuid-student-001", "attendStatus": "present" },
    { "studentId": "uuid-student-002", "attendStatus": "absent", "remarks": "未到" }
  ]
}
```

---

#### 4.5.2 图书借阅

| 端点 | 方法 | 说明 | 鉴权 |
|------|------|------|------|
| /student-ops/book-borrows | GET | 借阅记录列表（支持按 classId/studentId/status 筛选） | 需要 |
| /student-ops/book-borrows | POST | 录入借阅 | 需要 |
| /student-ops/book-borrows/{borrow_id}/return | PATCH | 归还登记 | 需要 |
| /student-ops/book-borrows/overdue | GET | 逾期列表 | 需要 |

**POST /student-ops/book-borrows**：
```json
{
  "studentId": "uuid-student-001",
  "bookTitle": "小王子",
  "bookIsbn": "978-7-02-004249-4",
  "bookAuthor": "圣埃克苏佩里",
  "borrowedAt": "2026-08-11T10:00:00Z",
  "dueAt": "2026-09-11T10:00:00Z"
}
```

**PATCH /student-ops/book-borrows/{borrow_id}/return**：
```json
{
  "returnedAt": "2026-08-15T14:00:00Z",
  "notes": "完好无损"
}
```

---

#### 4.5.3 阅读打卡

| 端点 | 方法 | 说明 | 鉴权 |
|------|------|------|------|
| /student-ops/reading-records | GET | 阅读记录列表 | 需要 |
| /student-ops/reading-records | POST | 录入阅读打卡 | 需要 |
| /student-ops/reading-records/batch | POST | 批量录入 | 需要 |
| /student-ops/reading-leaderboard | GET | 阅读榜单（支持 week/month/term 周期） | 需要 |

**POST /student-ops/reading-records**：
```json
{
  "studentId": "uuid-student-001",
  "bookTitle": "小王子",
  "pagesRead": 30,
  "readingMinutes": 45,
  "readingDate": "2026-08-11"
}
```

**GET /student-ops/reading-leaderboard 响应**：
```json
{
  "data": {
    "period": "month",
    "startDate": "2026-08-01",
    "endDate": "2026-08-31",
    "leaderboard": [
      {
        "rank": 1,
        "studentId": "uuid-student-001",
        "studentName": "张三",
        "className": "小学一年级1班",
        "totalPages": 450,
        "totalMinutes": 680,
        "booksCount": 5
      }
    ]
  }
}
```

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| period | string | 否 | week / month / term，默认 month |
| classId | string | 否 | 按班级筛选 |
| limit | int | 否 | 榜单长度，默认 50，最大 200 |

---

#### 4.5.4 晨午检

| 端点 | 方法 | 说明 | 鉴权 |
|------|------|------|------|
| /student-ops/health-checks | GET | 晨午检记录列表 | 需要 |
| /student-ops/health-checks | POST | 录入晨午检（批量） | 需要 |
| /student-ops/health-checks/{check_id} | PATCH | 更新检查记录 | 需要 |
| /student-ops/health-alerts | GET | 健康预警列表（异常/连续异常） | 需要 |

**POST /student-ops/health-checks（批量录入）**：
```json
{
  "classId": "uuid-class-001",
  "checkType": "morning",
  "checkDate": "2026-08-11",
  "records": [
    { "studentId": "uuid-student-001", "temperature": 36.5, "healthStatus": "normal" },
    { "studentId": "uuid-student-002", "temperature": 37.8, "healthStatus": "abnormal", "symptoms": "发热、咳嗽" },
    { "studentId": "uuid-student-003", "temperature": 36.3, "healthStatus": "normal" }
  ]
}
```

**GET /student-ops/health-alerts 响应**：
```json
{
  "data": {
    "items": [
      {
        "studentId": "uuid-student-002",
        "studentName": "李四",
        "className": "小学一年级1班",
        "checkDate": "2026-08-11",
        "checkType": "morning",
        "temperature": 37.8,
        "symptoms": "发热、咳嗽",
        "consecutiveAlertDays": 1,
        "isHandled": false
      }
    ],
    "total": 3
  }
}
```

---

### 4.6 文件上传

#### POST /student-ops/upload-evidence

**用途**：上传实践佐证图片
**鉴权**：需要
**Content-Type**: `multipart/form-data`

**表单参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 图片文件 (JPG/PNG/HEIC, ≤10MB) |

**成功响应 (200)**：
```json
{
  "data": {
    "url": "student_ops/practice/evidence/2026-08/abc123def.jpg",
    "thumbUrl": "student_ops/practice/evidence/2026-08/thumb/abc123def.jpg",
    "fileName": "abc123def.jpg"
  }
}
```

---

#### GET /student-ops/get-file-url

**用途**：获取带 download ticket 的临时文件直链
**鉴权**：需要

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| path | string | 是 | 文件相对路径（来自 upload-evidence 返回的 url） |

**成功响应 (200)**：
```json
{
  "data": {
    "downloadUrl": "/api/v1/student-ops/files/student_ops/practice/evidence/2026-08/abc123.jpg?ticket=eyJh..."
  }
}
```

> **ticket 有效期**：10 分钟（与现有 `DOWNLOAD_TICKET_EXPIRE_MINUTES` 一致）。

---

## 5. 前端管理页面

### 5.1 页面清单

> 组件目录：`src/components/student-ops/`
> 页面目录：`src/pages/student-ops/`

| 页面路由 | 页面名称 | 对应功能 | 包含组件 |
|---------|---------|---------|---------|
| `/student-ops/badges` | 颁章管理 | 章定义维护 + 颁章操作 | `BadgeDefinitionList`, `BadgeAwardForm`, `BadgeAwardHistory`, `BatchAwardDialog` |
| `/student-ops/credits` | 学分银行 | 积分账户总览 + 流水查询 + 报表 | `CreditAccountTable`, `CreditTransactionLog`, `CreditReportDashboard`, `ManualCreditDialog` |
| `/student-ops/rewards` | 兑换管理 | 商品管理 + 兑换操作 + 兑换记录 | `RewardProductList`, `RewardProductForm`, `RedemptionDialog`, `RedemptionRecordTable`, `StockWarningBadge` |
| `/student-ops/practice` | 校外实践 | 实践记录录入/编辑/审核 | `PracticeRecordForm`, `PracticeRecordList`, `PracticeReviewPanel`, `EvidenceImageUploader` |
| `/student-ops/campus` | 校园生活 | 社团/考勤/借阅/阅读/晨午检 | `ClubManager`, `ClubAttendanceForm`, `BookBorrowForm`, `ReadingRecordInput`, `ReadingLeaderboard`, `HealthCheckForm`, `HealthAlertPanel` |

### 5.2 组件目录约定

```
src/components/student-ops/
├── badges/
│   ├── BadgeDefinitionList.tsx      # 章定义列表（表格 + 筛选 + 新建/编辑按钮）
│   ├── BadgeDefinitionForm.tsx      # 章定义新增/编辑弹窗表单
│   ├── BadgeAwardDialog.tsx         # 颁章弹窗（选学生 → 选章 → 填日期事由）
│   ├── BatchAwardDialog.tsx         # 批量颁章（多选学生 + 快速颁章）
│   └── BadgeAwardHistory.tsx        # 颁章历史记录表格
├── credits/
│   ├── CreditAccountTable.tsx       # 积分账户列表（排序、按班级筛选）
│   ├── CreditTransactionLog.tsx     # 积分流水分页表格
│   ├── CreditReportDashboard.tsx    # 积分报表（汇总卡片 + 图表）
│   └── ManualCreditDialog.tsx       # 手动加减分弹窗
├── rewards/
│   ├── RewardProductList.tsx        # 商品卡片列表/表格
│   ├── RewardProductForm.tsx        # 商品新增/编辑表单
│   ├── RedemptionDialog.tsx         # 兑换确认弹窗
│   ├── RedemptionRecordTable.tsx    # 兑换记录表格（含状态筛选）
│   └── StockWarningBadge.tsx        # 低库存预警角标
├── practice/
│   ├── PracticeRecordForm.tsx       # 实践记录表单（含图片上传）
│   ├── PracticeRecordList.tsx       # 实践记录列表（支持筛选+审核操作）
│   ├── PracticeReviewPanel.tsx      # 审核面板（批量审核）
│   └── EvidenceImageUploader.tsx    # 图片上传组件（拖拽+多图+预览+缩略图）
├── campus/
│   ├── ClubManager.tsx              # 社团管理（列表+新建+编辑）
│   ├── ClubEnrollmentManager.tsx    # 社团成员管理（报名/退出）
│   ├── ClubAttendanceForm.tsx       # 社团考勤录入（日期+全员勾选）
│   ├── BookBorrowForm.tsx           # 图书借阅录入
│   ├── BookBorrowList.tsx           # 图书借阅记录+归还操作
│   ├── ReadingRecordInput.tsx       # 阅读打卡录入
│   ├── ReadingLeaderboard.tsx       # 阅读榜单展示
│   ├── HealthCheckForm.tsx          # 晨午检录入（班级全员体温表）
│   └── HealthAlertPanel.tsx         # 健康异常预警面板
└── shared/
    ├── StudentSelector.tsx           # 通用学生选择器（树形：年级→班级→学生，支持多选）
    ├── ClassFilter.tsx               # 班级筛选下拉
    └── DateRangeFilter.tsx           # 日期范围筛选
```

### 5.3 前端 API 调用规范

```ts
// src/services/studentOps.ts
const API_BASE = import.meta.env.VITE_API_BASE ?? ''  // ⚠️ 必须使用环境变量前缀

export const studentOpsApi = {
  // 章定义
  getBadgeDefinitions: (params: BadgeQueryParams) =>
    axios.get(`${API_BASE}/api/v1/student-ops/badge-definitions`, { params }),

  // 颁章
  awardBadge: (body: AwardBadgeRequest) =>
    axios.post(`${API_BASE}/api/v1/student-ops/badge-awards`, body),

  // ... 其余接口同理
}
```

---

## 6. 与学生画像联动

### 6.1 画像联动表

> 假设画像系统已定义 `student_growth_records` 表（或 `student_portfolio` + `student_growth_record` 双表），结构兼容灵犀岛"五育画像 SCHEMAFULL"设计。

新功能每次产生有意义的学生事件时，写入一条成长记录（goowth_record），包含：

**student_growth_records 约定字段**：
```sql
-- 学生成长记录表（画像系统定义，此处仅列本契约需要联动的字段）
CREATE TABLE student_growth_records (
    id VARCHAR(36) PRIMARY KEY,
    student_id VARCHAR(36) NOT NULL,
    class_id VARCHAR(36) NOT NULL,
    dimension VARCHAR(32) NOT NULL COMMENT '五育维度: moral=德, intellectual=智, physical=体, aesthetic=美, labor=劳',
    event_type VARCHAR(64) NOT NULL COMMENT '事件类型: 对应 source_type',
    event_title VARCHAR(255) NOT NULL COMMENT '事件标题',
    score_change INT NOT NULL DEFAULT 0 COMMENT '本次贡献的分值',
    source_type VARCHAR(64) NOT NULL COMMENT '来源表: badge_award / practice_record / club_activity / health_check / etc',
    source_id VARCHAR(36) NOT NULL COMMENT '来源记录主键',
    evidence JSON NULL COMMENT '证据摘要',
    recorded_by VARCHAR(36) NOT NULL,
    event_date DATE NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sgr_student_dimension (student_id, dimension),
    INDEX idx_sgr_source (source_type, source_id),
    CONSTRAINT fk_sgr_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);
```

### 6.2 事件 → 维度映射表

| 触发事件 | source_type | dimension (五育维度) | event_title 示例 | score_change 规则 |
|---------|-------------|---------------------|-----------------|------------------|
| 颁红领巾章（category=moral） | `badge_award` | `moral` (德) | 获得【红领巾基础章】 | +badge.points_awarded |
| 颁校本特色章（category=labor） | `badge_award` | `labor` (劳) | 获得【劳动小能手章】 | +badge.points_awarded |
| 颁校本特色章（category=physical） | `badge_award` | `physical` (体) | 获得【运动达人章】 | +badge.points_awarded |
| 颁校本特色章（category=aesthetic） | `badge_award` | `aesthetic` (美) | 获得【才艺之星章】 | +badge.points_awarded |
| 志愿服务实践审核通过 | `practice_record` | `moral` (德) 或 `labor` (劳) | 【志愿服务】社区清洁 | +50 (可配置) |
| 家务劳动实践审核通过 | `practice_record` | `labor` (劳) | 【家务劳动】洗碗整理 | +50 (可配置) |
| 校外才艺实践审核通过 | `practice_record` | `aesthetic` (美) | 【校外才艺】钢琴演出 | +50 (可配置) |
| 研学活动实践审核通过 | `practice_record` | `intellectual` (智) | 【研学活动】博物馆参观 | +50 (可配置) |
| 社团全勤（学期） | `club_activity` | `physical` (体) 或 `aesthetic` (美) | 【社团全勤】篮球社团 | +30 (可配置) |
| 阅读月榜前10 | `reading_record` | `intellectual` (智) | 【阅读之星】月度第3名 | +20 (可配置) |
| 健康异常连续3天 | `health_check` | `physical` (体) | 【健康关注】连续异常 | 0 (仅记录，不加分) |
| 教师手动加分 | `credit_transaction` | (不写入画像) | — | — |
| 兑换记录 | `redemption_record` | (不写入画像) | — | — |

> **注意**：
> - 志愿服务（volunteer）同时归属德育和劳育 → 写入两条 growth_record（dimension 分别为 moral 和 labor）
> - `score_change = 0` 的事件仅做留痕记录，不贡献画像分数
> - 写入画像的动作在后端 service 层通过**同步调用**完成（与业务操作同事务），保证一致性

### 6.3 写入时机与事务边界

```
业务操作成功提交 →
  [同一事务内]
  1. 写入业务记录（badge_awards / practice_records / etc）
  2. 写入信用流水 credit_transactions（如有积分变动）
  3. 更新积分账户 credit_accounts（如有积分变动）
  4. 写入成长记录 student_growth_records（按事件→维度映射）
```

若任一环节失败，整个事务回滚，保证"业务数据 = 积分数据 = 画像数据"三方一致。

---

## 7. 验收标准

### 7.1 争章颁章

| 编号 | 验收项 | 通过条件 |
|------|--------|---------|
| B-01 | 章定义 CRUD | 管理员可创建/编辑/停用章定义，字段完整保存 |
| B-02 | 单人颁章 | 教师选学生+选章→颁发，积分自动入账，`badge_awards` + `credit_transactions` 双写成功 |
| B-03 | 批量颁章 | 同一枚章一次发给最多 200 人，每人独立成功/失败，互不影响 |
| B-04 | 重复颁章拦截 | 同学生+同章+同日期，第二次请求返回 `duplicate_entry` |
| B-05 | 颁章撤销 | 撤销后积分回滚，`badge_awards` 记录删除 |
| B-06 | 跨班权限 | 非本班教师无法给别班学生颁章 |

### 7.2 学分银行

| 编号 | 验收项 | 通过条件 |
|------|--------|---------|
| C-01 | 积分账户查询 | 按班级/学生查看余额、累计获得、累计消费 |
| C-02 | 积分流水查询 | 支持按类型/日期/学生筛选，分页正确 |
| C-03 | 手动加减分 | 班主任可加减，扣分不允许负余额 |
| C-04 | 流水余额一致性 | `balance_after` 与 `credit_accounts.balance` 始终一致（对账 API 验证） |
| C-05 | 报表准确性 | 班级汇总/类型汇总数据与实际流水 SUM 一致 |

### 7.3 兑换管理

| 编号 | 验收项 | 通过条件 |
|------|--------|---------|
| R-01 | 商品管理 | 管理员可创建/编辑/上下架商品 |
| R-02 | 兑换流程 | 教师代兑换→积分扣减+库存扣减+流水生成，三者在同一事务 |
| R-03 | 库存防超卖 | 并发兑换（用 JMeter/ab 模拟 10 并发），库存不出现负数 |
| R-04 | 积分不足拦截 | 余额 < 所需积分时返回 `insufficient_balance` |
| R-05 | 兑换限制 | 超过 `exchange_limit_per_student` 时返回 `limit_exceeded` |
| R-06 | 退兑流程 | 取消后积分退回+库存恢复，流水可追溯 |
| R-07 | 低库存预警 | 实物商品库存 ≤ stock_warning 时前端显示预警标记 |

### 7.4 校外实践

| 编号 | 验收项 | 通过条件 |
|------|--------|---------|
| P-01 | 实践录入 | 支持四种类型，选填图片，保存成功 |
| P-02 | 图片上传 | 支持 JPG/PNG/HEIC，大小 ≤10MB，自动生成缩略图，返回可访问直链 |
| P-03 | 图片防过量 | 单条记录最多 9 张，超过拒绝 |
| P-04 | 审核流程 | 管理员审核通过/驳回，通过后自动积分入账 |
| P-05 | 实践查询 | 支持按类型/状态/日期/班级筛选 |

### 7.5 校园生活

| 编号 | 验收项 | 通过条件 |
|------|--------|---------|
| CL-01 | 社团 CRUD | 管理员可增删改社团 |
| CL-02 | 社团报名 | 批量录入学生入团，退团可标记 |
| CL-03 | 社团考勤 | 按日期批量录入出勤/缺勤/请假 |
| CL-04 | 图书借阅 | 录入借阅→自动计算应还日期→归还登记→逾期自动标记 |
| CL-05 | 阅读打卡 | 教师录入，榜单按周/月/学期实时计算 |
| CL-06 | 晨午检录入 | 班级全员体温表，支持异常标记 |
| CL-07 | 健康预警 | 体温 ≥37.3 自动预警，连续 3 天异常高亮提醒 |
| CL-08 | 预警处理闭环 | 预警可标记"已处理"并填写处理备注 |

### 7.6 画像联动

| 编号 | 验收项 | 通过条件 |
|------|--------|---------|
| PF-01 | 颁章→画画像 | 颁章成功后 `student_growth_records` 出现对应维度记录 |
| PF-02 | 实践→画画像 | 实践审核通过后出现对应维度记录（志愿服务写两条：德+劳） |
| PF-03 | 事务一致性 | 模拟数据库写入失败，验证业务表+积分表+画像表三者全部回滚 |
| PF-04 | 纯积分操作不写画像 | 手动加减分不产生成长记录 |

### 7.7 性能基线

| 指标 | 目标 |
|------|------|
| 批量颁章（200 人）响应时间 | ≤ 3 秒 |
| 批量晨午检（50 人/班）响应时间 | ≤ 1 秒 |
| 积分流水查询（100 万条数据）分页响应 | ≤ 500ms |
| 阅读榜单（全校 2000 学生，30 天数据） | ≤ 2 秒 |
| 并发兑换（10 并发） | 无超卖，全部成功或合理拒绝 |
| 图片上传（10MB） | ≤ 3 秒（含缩略图生成） |

---

## 8. 实施顺序建议（P0 / P1 / P2）

### P0 — 第一周交付（核心闭环）
1. `badge_definitions` + `badge_awards` 表 + API + 前端颁章页
2. `credit_accounts` + `credit_transactions` 表 + API + 前端积分页
3. 颁章→积分入账 联动逻辑
4. `reward_products` + `redemption_records` 表 + API + 前端兑换页
5. 兑换扣减+库存原子性

### P1 — 第二周交付（扩展功能）
6. `practice_records` 表 + 图片上传 API + 前端实践页
7. 实践审核 + 积分入账联动
8. `health_checks` 表 + API + 前端晨午检页
9. 健康预警逻辑

### P2 — 第三周交付（完善 + 画像联动）
10. `campus_clubs` + `club_enrollments` + `club_attendance` 表 + API + 前端
11. `book_borrows` + `reading_records` 表 + API + 前端（借阅 + 阅读榜单）
12. 全部事件→画像联动写入
13. 积分报表 + 对账 API

---

## A. 附录：Python SQLAlchemy 模型声明示例

> 以下为 `app/models/student_ops.py` 的参考代码骨架（仅贴 `badge_definitions` 一张表做示范，后端工程师按此风格补齐全表）：

```python
"""学生端运营功能模型：争章/学分/实践/校园生活"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, JSON, Date
from sqlalchemy.sql import func
from app.database import Base
from app.models.user import gen_uuid


class BadgeDefinition(Base):
    __tablename__ = "badge_definitions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(128), nullable=False)
    description = Column(String(512), nullable=True)
    badge_type = Column(String(32), nullable=False, default="school_based")
    category = Column(String(32), nullable=False, default="moral")
    icon_url = Column(String(512), nullable=True)
    points_awarded = Column(Integer, nullable=False, default=10)
    min_grade = Column(String(16), nullable=True)
    max_grade = Column(String(16), nullable=True)
    is_active = Column(Integer, nullable=False, default=1)
    sort_order = Column(Integer, nullable=False, default=0)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```
