# P0/P1 缺陷修复验收记录（2026-08-13）

> 本轮修复 4 个 P0 安全缺陷 + 1 个 P1 同步阻塞问题，均在隔离 worktree 中开发、人工审核后合并回 master，
> 并在测试环境（Docker MySQL `127.0.0.1:13307` + 后端 `http://127.0.0.1:6888`）运行态重放原缺陷用例验证。

## 一、修复总览

| 缺陷 | 等级 | 修复内容 | commit |
|---|---|---|---|
| **P0-3** grading `_safe_folder_name` 路径穿越 | 致命 | `_safe_folder_name` 新增三道拦截（纯 `.`/`..`、`/` `\` 分段 `..`、点开头/结尾），合法含点文件夹名保留 | `45e2438` |
| **P0-1** student_ops 14 列表端点越权 | 高危 | `_list_scope` 统一三档：学生只看本人、教师/班主任看可访问班级、admin/校级全量 | `ab5fc85` |
| **P0-2** `return_book_borrow` 无权限校验 | 高危 | 仅借书学生本人 / 该生所在班级教师（含班主任）/ 管理角色可还，其余 403 | `ab5fc85` |
| **P1** `/grading/quick` 同步阻塞 120s | 中 | `run_ocr` 轮询超时 120s→30s，所有 HTTP 请求加 timeout（post 10s/轮询 5s/下载 10s），OCR 提交失败立即 500 | `bec6420` |
| **P0-4** 四大分析域 IDOR 越权 | 高危 | 26 端点加 `_assert_class_access`（query/body/form 来源 class_id 统一校验）；ct-image 从 path 还原 class_id 拦截越权图片 | `59bac19` / `9a35a8f` |

master 合并：P0-1/2/3 `b22a9e0`、P1 `bec6420`（ff）、P0-4 `26a44a9`（merge），历史保持线性，工作区无残留改动。

## 二、P0-3 路径穿越修复详情

### 缺陷机理
`app/grading/router.py` `_safe_folder_name` 只剔除 `/\:*?"<>|`，放行 `.` 与 `..`。
攻击者可用 URL 编码 `%2E%2E`（解码为 `..`）作为文件夹名拼进 `correct_docs_dir()/safe`
路径，实现对 test_paper 命名空间之外文件的写/读/删/改；多级穿越还会触发 500。

### 修复内容（`45e2438`）
`_safe_folder_name` 返回空串（沿用既有错误处理路径，不抛异常）当且仅当：
1. 值恰好为 `.` 或 `..`；
2. 任何被 `/` 或 `\` 分隔出的路径段恰好为 `.` 或 `..`；
3. 名称以 `.` 开头或以 `.` 结尾（Windows 隐藏/歧义名）。

合法含点文件夹名（如 `数学期中.卷`、`math.v3`）内嵌点不受影响。

### 运行态验证（student1 token）
| 攻击/用例 | 结果 |
|---|---|
| GET `/grading/folders/.. /files`（`%2E%2E`） | 404（拦截） |
| GET `/grading/folders/..%2F../files`（分段穿越） | 200 + `无效文件夹名` + 空列表 |
| POST `/grading/folders` `{"name":".."}` | 400 文件夹名称无效 |
| POST `/grading/folders` `{"name":"..%2F.."}` | 400 文件夹名称无效 |
| POST `/grading/folders/delete` `{"folder_names":[".."]}` | 400 请选择要删除的文件夹 |
| POST `/grading/folders` `{"name":"数学期中.卷"}` | 200 创建成功（合法名称不误伤） |
| POST `/grading/folders` `{"name":"期中测试"}` / `{"name":"math.v3"}` | 200 创建成功 |

> 注：Git Bash curl 传输中文 body 会编码损坏导致假 400，改用 Python requests 验证，均 200。

## 三、P0-1/P0-2 student_ops 越权修复详情

### 缺陷机理
`app/routers/student_ops.py` 约 14 个只读列表端点 `del user_id` 后直查全表，
学生账号可遍历全校数据（含健康检查记录）；`return_book_borrow`（~1877）无任何归属校验。

### 修复内容（`ab5fc85`）
新增 helper：
- `_list_scope(db, user_id)` → `(own_student_ids, visible_class_ids)`：
  - `(None, None)` → 全校可见（系统管理员/子系统管理员/校级管理者/年级组长，经 `_is_global_admin`）
  - 学生 → `({me.id}, {me.class_id})`，仅可见自己的记录
  - 教师/班主任 → `(None, set(get_accessible_class_ids(...)))`，仅可见所管班级
- `_can_return_borrow(db, user_id, borrow)` → 借书学生本人 / 借书所在班级教师（`can_view_class`）/ 管理角色。

改动端点（12 个列表 + 1 个还书）：
`badge-awards` / `credit-transactions` / `redemptions` / `practice-records` /
`club-enrollments` / `club-attendance` / `book-borrows` / `book-borrows/overdue` /
`reading-records` / `reading-leaderboard`（特殊语义：学生看本班、教师看可访问班级、admin 全量）/
`health-checks` / `health-alerts` + `book-borrows/{id}/return`。

保留 3 个 `del user_id` 端点未动（非学生数据泄露）：`badge-definitions`、`reward-products`、`clubs`（全局目录型数据）。

### 运行态验证（student1 vs admin）
| 端点 | student1 total | admin total | 结论 |
|---|---|---|---|
| health-checks | 0 | 1 | 学生被过滤 |
| credit-transactions | 0 | 1 | 学生被过滤 |
| practice-records | 0 | 1 | 学生被过滤 |
| reading-records | 0 | 1 | 学生被过滤 |
| book-borrows | 2（仅本人） | 3 | 学生只见自己记录 |

越权兜底：学生传他人 `studentId` / 其他 `classId` → 200 空集（无泄露）。

### P0-2 还书越权验证
| 用例 | 结果 |
|---|---|
| student1 PATCH 还 QA学生二的书（`e4671467...`） | **403** `仅借书学生本人/本班教师/管理员可归还` |
| teacher1 PATCH 还本班学生（初一1班）的书 | **200** 归还成功，status→returned |

### P1 /grading/quick 阻塞收敛验证
| 用例 | 结果 |
|---|---|
| 上传空白图（OCR 外部服务拒绝 token） | **0.3s 快速失败**，HTTP 500 + 明确错误，不再阻塞 120s |
| 上传非图片（text/plain） | 400 `请上传图片文件（如 jpg、png）`（图片校验未破坏） |
| 同步契约 | 未变：`{ok, result, image_original, image_annotated, image_marks_only}`，前端异常路径兼容 |

### P0-4 四大分析域 IDOR 越权验证
| 场景 | 结果 |
|---|---|
| student1 读初一1班学情（GET list） | **403** `无该班级访问权限` |
| student1 写（POST upsert） | **403** |
| student1 删（DELETE score-history/exam） | **403** |
| student1 ct-image 越权图片（path 内嵌 `cls_{class_id}`） | **403** |
| teacher1 读本班学情 | **200** 放行 |
| teacher1 读不存在的班级 | **403** |
| teacher1 class-review report / targeted-improvement recommendations | **200** 放行 |

## 四、遗留事项（不在本轮范围）

1. **凭据轮换**（用户侧）：RDS DB_PASSWORD、QQ SMTP 账号+授权码、JWT_SECRET_KEY、
   multi_project_settings.json 密码 → 轮换后跑 `scripts/build_exe.sh` 重打包干净 dist。

## 五、相关文档

- `docs/qa-plan.md`：缺陷清单及状态标注（本轮已更新 3 处 P0 + 1 处 P1 ✅）
- `docs/DEPLOY.md`：部署与凭据注入说明
