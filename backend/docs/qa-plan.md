# 叙阅 QA 验证计划

> 生成日期：2026-08-13
> 覆盖范围：后端 24 路由域 234 端点（`app/routers/*` 180 + `app/grading/router.py` 54）+ 前端 24 页面 + PyInstaller 打包产物
> 验证方法层级：①接口层（curl/HTTP）②UI 层（浏览器）③文件层（磁盘核对）④进程层（端口/日志/任务管理器）
> 外部依赖（百度 OCR/VLM、千问 DashScope、PaddleOCR、SMTP、WIA 扫描仪、pywin32 打印）在降级路径验证时可 mock

---

## 0. 结论速览

### 0.1 已确认缺陷（源码核实，优先处理）

| # | 严重度 | 缺陷 | 位置 | 影响 |
|---|--------|------|------|------|
| C1 | 🔴 致命 | `real_grade_pipeline()` 构建完 `result_text` 后**无 return**，返回 `None` | `app/grading/pipeline.py:774` | `/grading/quick`、`/grading/batch`、`/grading/home/quick` 解包 4 元组必抛 `TypeError`，100% 失败，且先消耗 OCR+Qwen 调用 |
| C2 | 🔴 致命 | 任意文件写入/读取/删除/邮件外带（路径穿越） | `app/routers/resources.py` upload(153)/delete(171)/rename/zip-files/send-email | `file.filename`/`files[]`/`new_name` 未做 resolve/is_relative_to，`p / fname` 直拼，`../../x` 可越界 |
| C3 | 🔴 致命 | IDOR 越权：assessment 会话可被任意登录用户操作 | `app/routers/assessment.py` `start_session`(475)/`submit_answers`(517) | 只查 session 状态，不校验操作者归属；知道 session_id 即可替他人 start/作答并生成结果 |
| C4 | 🟠 高 | `essay-grade/print-pdf` 缺本机管理员校验 | `app/grading/router.py:5803` `api_essay_grade_print_pdf` | 其他打印端点均有 `_require_local_admin`(M5)，此端点函数体无调用、签名无 request → 任意登录用户可远程触发真实打印 |
| C5 | 🟠 高 | 打包产物 `.env` 明文生产凭据 | `dist/叙阅/.env` | 含 RDS 地址/密码/`SMTP_PASSWORD`/`JWT_SECRET_KEY`，分发即泄露生产库 |
| C6 | 🟠 高 | 前端图片鉴权与后端契约错位 | 前端 `services/gradingApi.ts` `gradingImageUrl` + 后端 `app/grading/file_auth.py` | 前端仍拼 `?access_token=`，后端 H2 已改 `?ticket=` 短时下载票 → 图片加载需专项回归 |

### 0.2 高危风险清单（待验证确认）

| 优先级 | 风险 | 说明 |
|--------|------|------|
| P0 | 四大分析域 IDOR | `student_analysis`/`class_analysis`/`class_review`/`targeted_improvement` 多数 REST 端点无 class_id 归属校验，任意登录用户可读改写任意班级数据（表无 user_id 列，已知 `get_accessible_class_ids` 未复用）。**✅ 已修复（59bac19 + 9a35a8f）**：26 端点统一 `_assert_class_access`（query/body/form 来源 class_id 校验），ct-image 从 path 还原 class_id 拦截越权图片 |
| P0 | student_ops ~14 个只读列表越权 | badge-awards/credit-transactions/redemptions/practice-records/clubs/attendance/book-borrows/reading-records/leaderboard/health-checks 等 `del user_id` 后直查全表 → 学生账号可遍历全校数据 |
| P0 | `return_book_borrow` 无权限校验 | `student_ops` 还书端点任何登录用户可还任意书。**✅ 已修复（ab5fc85）**：仅借书学生本人 / 该生所在班级教师（含班主任）/ 管理角色可还，其余 403 |
| P1 | PII 外发 | 学生姓名/作答全文/整张试卷图 base64 发千问（class_analysis/class_review/targeted/ai_diagnosis/auto-report），无脱敏无告知。**✅ 脱敏已修复（025039a）**：新增 `app/utils/anonymize.py` 请求级 Anonymizer（真名↔「学生01」稳定映射，RLock 保证并发 batch 共享），5 域发千问前匿名化姓名、AI 返回后还原回真名再入库；`import_exams` 的题目分析 prompt 同批覆盖。告知层（前端发起前隐私提示）待前端处理 |
| P1 | 明文凭据落盘 | `multi_project_settings.json`（含 `Grade123_` 生产密码）、`system_settings` 表 AI key 明文 |
| P1 | 上传弱校验 | grading/upload、students/import、import-scores/excel 无大小/魔数校验，`await file.read()` 全内存 |
| P1 | 开放邮件转发 | `lesson_plans/{id}/send-email` 缺 H4 白名单+限流（contrast exams/resources 已配） |
| P1 | 同步长阻塞 | class-analysis analyze（最长数分钟）、import-exams、post-class AI 失败一律 500 无缓存 |
| P2 | 内存任务状态机 | `_batch_results`/`_ref_grade_results`/`_print_batch_jobs` 等重启即丢、无过期清理、可重复触发计费 |
| P2 | 登录锁进程内 | auth 登录限流内存实现，多进程/重启失效；IP 取 `request.client.host` 代理后全是代理 IP |
| P2 | roles 非白名单 + 默认密码 | admin 建用户 roles 可写任意字符串；批量导入默认密码 `123456` |
| P2 | multi_project 全局切换 | DB 档切换所有用户跟随；文件系统不隔离（跨项目同 user_id 串文件） |

---

## 1. 测试基建

- **DB**：`AUTO_DDL` 默认 false，需手工准备 schema 或用测试库开启；chunfeng v1/v2 迁移已在 `docs/migrations/`。
- **外部 API mock**：百度/千问/PaddleOCR/SMTP 可 mock 以跑降级路径（失败重试 3 次→落盘 failed）。
- **打包版专用**：`/system/exit`、SPA 托管、自动开浏览器、日志重定向需 frozen 环境验证。
- **数据种子**：多角色用户（系统管理员/子系统管理员/校级管理者/年级组长/任课教师/班主任/学生/家长）、班级、学生、批改文件夹、含错题的多场考试。

---

## 2. P0 核心链路验证（grading/auth/students/classes/assessment/portfolio/student_ops/exams）

### 2.1 auth（6 端点）—— 全部主链路入口

| 端点 | 正常 | 边界/异常 | 安全点 |
|------|------|----------|--------|
| POST /auth/login | 正确凭据→200+token+user；登录成功建用户 grading 目录 | 密码错→401；连续 5 次失败（15min 窗口，email+IP 双键）→429；单 IP 20次/min→429 | 登录锁进程内存，重启清空（M4 设计如此）；无注册/无验证码 |
| GET /auth/me | 返回 roles/phone/personal_email | 无效 token→401 | personal_email 敏感字段仅本人可见 |
| GET /auth/users/all | 系统/子系统管理员→用户最小化列表 | 非管理员→403 | 角色硬编码字符串判断 |
| PATCH /auth/me | 本人更新 profile | 无字段长度限制 | personal_email 是邮件白名单判定依据 |
| POST /auth/change-password | 旧密码校验通过→更新哈希 | 旧密码错→400；新密码<6→400 | bcrypt+SHA256 预哈希（>72 字节正确）；无踢下线机制 |

### 2.2 classes（9 端点）

| 端点 | 正常 | 边界/异常 | 安全点 |
|------|------|----------|--------|
| GET /classes | 班主任见自己班+协作班 | 空列表 | 角色判定正确 |
| POST /classes | 任意登录用户可建班（**无角色校验**） | - | 合规面宽 |
| PATCH/DELETE /classes/{id} | owner 操作成功 | 非 owner→403/404 | 级联删除学生/教师需验证（孤儿数据） |
| /classes/{id}/teachers GET/POST/PATCH/DELETE | head 管理班级教师 | 设 head 需全局管理；每班唯一 head | head 变更权限逻辑重点测；head 退班语义需验证 |

**重点**：班级无 `school_id`/`project_id` 列 → 校级管理者跨校全局 head 权限。

### 2.3 students（8 端点）

| 端点 | 正常 | 边界/异常 | 安全点 |
|------|------|----------|--------|
| GET /students?class_id= | 本班 head/deputy/teacher 可见 | 无权限→403 | 只读/写权限分级 |
| POST /students | head 创建 | 非 head→403 | student_number 唯一性 |
| POST /students/batch | 批量成功 | 含重复学号自动跳过，返回成功数 | 批量事务原子性 |
| POST /students/import | Excel 解析（姓名/学号等列模糊映射）；已存在按姓名更新 | 无"姓名"列→400；非 xlsx→400；`nan` 清洗 | **无文件大小/魔数校验** |
| POST /students/import/global | 全年级导入；仅写已存在班级 | 缺列→400；未匹配班级静默跳过 | **无管理员门禁**；静默跳过非管理班级（数据半导入无感知） |
| PATCH/DELETE /students/{id} | head 操作 | 非 head→403 | 可改 class_id 换班不校验目标班权限；删除后遗留历史/错题引用 |
| DELETE /students/clear/{class_id} | 清空全班 | **无服务端二次确认** | 高危误删；无级联清理 |

### 2.4 grading（54 端点）—— 全站最复杂域

**全局共性（每个子表验证通用）**：
- `bind_grading_user_context` 强制 Bearer 并绑定 `grading_data_{user_id}` 目录。
- **`_safe_folder_name` 只删 `/\:*?"<>|`，不删 `.`** → `folder_name=".."` 可穿越（不跨用户但影响所有 `/folders/{folder:path}` 端点）。**✅ 已修复（45e2438）**：新增三道拦截——纯 `.`/`..`、`/` `\` 分段 `..`、点开头/结尾；合法含点文件夹名（`数学期中.卷`）保留。
- 后台任务状态全存进程内存 dict，重启即丢。
- 并发：ThreadPoolExecutor（快速 16、作文 OCR 3/Qwen 2、参照 aliyun 4/baidu 4/smart_ref 6）。
- 外部失败→单任务重试 3 次→落盘 failed，无全链路熔断。

**扫描仪（4）**：scan-import start/stop/status 仅本机管理员（`_require_local_admin`：127.0.0.1 + 管理/校级角色）；`/scanners` 枚举 WIA，非 Windows→ok:false。

**快速批改 + 首页（6）**：
- ⚠️ **C1**：`/grading/quick`、`/grading/batch`、`/grading/home/quick` 全挂（先修 C1 再验）。
- `/grading/home/quick` 返回 job_id（百度 correct_edu 盲批，后台线程）；`home/recent` 最近 10 条重启后仍可读；`home/{job_id}` GET/DELETE 需验证归属（防 IDOR）。
- ✅ **P1**：`/grading/quick` 同步阻塞收敛（`bec6420`）——`run_ocr` 轮询超时 120s→30s，所有 HTTP 请求加 timeout（post 10s/轮询 5s/下载 10s），OCR 提交失败立即 500 不轮询；同步契约不变，实测 0.3s 快速失败。

**文件夹管理（7）**：upload 无文件大小上限（全内存读）、content_type 仅宽松 `image/*` 无魔数、同名单覆盖无锁、标准答案 `standard_page_no` 1-20 越界→400、`folder_name` 穿越面贯穿全部。

**参照批改 reference-layout（3）**：prepare 调百度 paper_cut_edu_vlm 同步阻塞；confirm 校验 prepare_id 一致否则 400；缺页/源变更→409。

**人工阅卷 manual-layout（3）**：prepare 调百度 paper_cut_edu；confirm 需全部模板页 + 每作答区 `max_score>0` 且 ≤2 位小数 + 至少一题一作答区，不满足→400；模板签名（size+mtime_ns）变更→"请重新切题"。

**批改历史（2）**：grading-history/essay-grading-history 读用户目录 JSON，杀进程重启后仍可读。

**打印（6）**：print-marks/print-marks-batch 同步阻塞无超时；print-marks-batch/start 后台 job（重复启动同批=并行打印无互斥）；`_safe_marks_only_filename` 防穿越；双面模式自动两两配对+背面旋转；**除 C4 的 print-pdf 外全部有 M5 校验**。

**作文批改 essay-grade（5）**：start（百度 handwriting_composition→千问，多页拼长图，timeout 180/OCR 240s）；`<essay_score>` 提取分数；全页无文字→"所有页面均未识别到有效文字"；pdf 生成 items 字段缺失→500 而非 400；**C4**：print-pdf 越权。

**rubrics（4）**：`topic_image_base64` 可致 DB 膨胀；ids 元素类型未校验可 500。

**错题本（2）**：纯本地正则解析历史文本，受 AI 文本格式影响；`scoring_config` 原样返回。

**评分配置（2）**：apply 按对/错/未答/半对算分写历史+触发 `schedule_smart_scoring_auto_report`；`scoring_config` 无结构校验（float 失败按 0）；读写历史非事务。

**人工批改（2）**：manual-grade 校验 decisions slot/分数上下限；`scores` 路径校验弱（无上下限）；读改写 TOCTOU；clear 删除 modify 图。

**参照批改 grade-by-reference（3）**：aliyun/baidu/smart_ref/manual 四分支；aliyun 需已确认切题否则 409；**先清空旧历史再跑（同 folder 并发互相覆盖）**；engine 未拒绝未知值走 else。

### 2.5 assessment（15 端点）

| 端点 | 正常 | 边界/异常 | 安全点 |
|------|------|----------|--------|
| /assessment/definitions CRUD | 仅 super/org admin 写 | questions 空/缺字段/option<2→400；PUT 与 POST 校验不对称 | 任何登录用户可读题面；物理删除→已引用会话/结果悬挂 |
| /assessment/sessions POST | self 校验 me.id==student_id；class_batch 逐个本班校验 | test_mode 非法→400 | - |
| /assessment/sessions GET/单查 | 学生只见自己/教师本班/admin 全量 | - | admin 无 school 隔离 |
| **sessions/{id}/start** | pending→in_progress | - | ⚠️ **C3**：无权限校验 |
| **sessions/{id}/answers** | 提交答案+计分+写结果 | 已提交→400 | ⚠️ **C3**：无权限校验 |
| results/{rid} grant/withdraw/restore | 状态机 not_required→granted→withdrawn，restore version+1 | withdrawn 重复→400 | 仅 super/school admin/本班教师代操作 |

**计分确定性**：等权累加+维度归一化+LABEL_MAP 白名单闸门（无 AI）。**consent 状态机**是核心验证点。

### 2.6 portfolio（12 端点）

| 端点 | 正常 | 边界/异常 | 安全点 |
|------|------|----------|--------|
| /portfolio/students/{id} | 五育画像+月度趋势 | 不存在/跨班→404（防泄露） | 跨班隔离 `_get_student_or_404` |
| growth-records CRUD | dimension 五值枚举否则 422；indicator 与 dimension 一致 | 写需本班角色否则 403 | - |
| /report?term= | 快照优先→实时聚合 | term 格式校验否则 422；version 不存在→404 | 非法 term 如 `2025-2026-3`→422 |
| /report/freeze | 生成 vN 快照；再次 GET 走快照 from_snapshot:true | - | 冻结后改成长记录报告不变 |
| comment/generate+confirm | 千问生成写 assessment_comment；网关失败→ai_failed 兜底 | **含禁词（人格归因）→422**；ai_failed 不可确认→400 | LLM 输出+人工输入都过 `sanitize_comment` 禁词闸门 |
| /report/pdf | 中文文件名 `filename*=UTF-8''学期成长报告_{姓名}_{term}.pdf` | - | 跨班 404 |

**数据来源双轨**：成长流水 + 智育事件轨（raw SQL 直查 wrong_questions/exam_scores/targeted 报告）；德体美劳未接源表返回 `data_sources_missing` 占位不造假。

### 2.7 student_ops（48 端点）—— 最大越权面

- **14 个只读列表端点越权**（P0）：badge-awards/credit-transactions/redemptions/practice-records/clubs/club-attendance/book-borrows/reading-records/reading-leaderboard/health-checks/health-alerts 等 `del user_id` 后直查全表 → **学生账号可遍历全校敏感数据**。**✅ 已修复（ab5fc85）**：`_list_scope` 统一三档——学生只看本人、教师/班主任看可访问班级（`get_accessible_class_ids`）、admin/校级全量；reading-leaderboard 学生看本班。
- **`return_book_borrow` 完全无权限校验**（P0）：任何登录用户可还任意书。
- `update_practice_record` 改 student_id 不校验目标班级权限。
- `redemptions` 并发超卖需实测（锁账户+锁商品防超卖）；批量端点靠 `begin_nested()` 局部回滚（部分成功计数需验证）。
- `overdue` GET 带写副作用（自动标记逾期）。
- `reading-leaderboard` 字符串列名 `order_by(desc("total_pages"))` 可能 SQL 报错需实测。
- upload-evidence/get-file-url/files 图片校验+下载票+归属需确认。

### 2.8 exams（6 端点）

| 端点 | 正常 | 边界/异常 | 安全点 |
|------|------|----------|--------|
| /exams/papers CRUD | 数学/理科自动规范化符号 | questions 非 list 转空；无题型/分数/结构校验 | 无幂等防重复 |
| /exams/send-email | 发本人/同域名 | 限流 429；非同域名 403；base64 非法→400 | 有 H4 白名单+20/日限流；**实为通用 PDF 发信器不绑定试卷实体** |
| /exams/ai-generate | 千问生成题目 | 无 Key→500；AI 非 JSON→500 | `requirements.count/score` 无范围校验（-1/1000 均可）；AI 结果不落库 |

---

## 3. P1 分析/AI 验证

**共性**：四大分析域（student_analysis 11 / class_analysis 4 / class_review 5 / targeted_improvement 6）+ ai_chat 1 + ai_auto_report 3。**P0 共性问题：无 class_id 归属校验 = IDOR**。同步阻塞端点 AI 失败一律 500 无缓存。

| 域 | 关键验证点 |
|----|-----------|
| student_analysis | list/单查/upsert/score-history/import-scores/delete-exam 全部 IDOR 待确认；ai-diagnosis 无错题→400；ct-image 仅拦 `..` 未做用户目录归属校验 |
| class_analysis | analyze 需 ≤160 图否则 400；无 Key→500；整张试卷图 base64 发千问（PII）；同步最长数分钟 |
| class_review | import-exams 非本班考试→400；post-class 需先有 session 否则 400；全班姓名+作答发千问 |
| targeted_improvement | recommendations 过滤非法名/去重/截断 5；import-exams 逐生并发 5 worker，失败不回滚已成功 |
| ai_chat | 隐私拒答→教程→数据查询→闲聊四路分流；SQL 防护（SELECT-only 正则+黑名单+表白名单+行级 class_id/user_id 注入+隐私表拦截+默认 LIMIT 100）；SSE 流式；无服务端会话（前端每次回传完整 messages） |
| ai_auto_report | pending→stream/consume；跨用户 report_id→404；>6h 过期；内存队列重启即丢；**无生成幂等锁（可重复触发千问计费）** |

---

## 4. P2 管理/系统验证

| 域 | 关键验证点 |
|----|-----------|
| admin（6） | roles 未白名单可写任意字符串；`caller_password` 明文进请求体（日志泄漏面）；批量导入默认密码 `123456`、随机邮箱 `xxxxx@pgj.com`、上限验证；子系统管理员改/删系统管理员→403 |
| admin_grading_stats（1） | start/end+user_id 必填；start>end 自动交换不报错 |
| system_settings（4） | AI key 明文存 DB（掩码展示）；baidu-credentials 换 token 失败→400 |
| todos（6） | notify-due 无每日限流（contrast exams）；notify-due-system 本机+`x-cron-key` 匹配才批量发 |
| lesson_plans（5） | **send-email 缺 H4 白名单+限流 → 开放邮件转发（P1）** |
| resources（11） | ⚠️ **C2 路径穿越**；download 用 `?ticket=` 下载票 10min 过期 |
| prep_plans（4） | 日期非法按字符串比较不报错；`exclude_unset` setattr |
| system（2） | cleanup-grading-data 仅本人目录；/system/exit 本机+frozen only |
| multi_project（8） | DB 档切换全局生效；明文密码落盘；删最后一项→400；apply 缺 users 表→400 |
| parent（2） | **不校验学生班级归属（A 班教师可绑 B 班学生）**；不校验 parent_id 是否有家长身份；家长走 JWT 登录无专属手机号流程 |

---

## 5. 前端页面验证

前端为侧边栏 SPA：react-router 仅 4 条真实路由（`/`、`/auth`、`/admin`、`/class/:classId`），页面切换由 `activeNavId` 驱动（localStorage `sidebar-active-nav` 持久化）。API 走 `gradingApi.ts`（Bearer）+ `api.ts`（30s 超时、2 次重试、AbortController）。

| 页面 | 验证点 |
|------|--------|
| 登录 /auth | zod 邮箱格式+密码≥6；429→15min 提示；密码错误统一文案"账号或密码错误"；提交中按钮禁用 |
| 管理 /admin | 非管理员→toast+重定向；批量导入管理员需 caller_password 复核 |
| 作业批改 grading-start（6126 行核心） | 上传类型白名单；标准答案页码 1-20；manual 槽位状态/分数范围；paper_box 容量 1~20；`GradingErrorBoundary` 兜底；任务轮询 2s；job_id 存 localStorage 重启续轮询 |
| 对比分析/分层推送 | ⚠️ **部分数据为静态 mock**（compareData.ts/layeredData.ts），需标注非真实接口 |
| 个人设置 | 改密需旧密码；原密码错→400；语言切换 |

**前端-后端契约风险（专项回归）**：
1. ⚠️ **C6**：`gradingImageUrl` 对 `/api/v1/grading/`、`/ct`、`/zyk_data`、`/student-analysis/ct-image` 自动拼 `?access_token=`，后端 H2 已改 `?ticket=` 短时下载票 → 图片加载回归。
2. `api.ts` 期望 `{data:...}` 包裹 vs `gradingApi.ts` 裸 JSON（`/auth/*` 用 authRequest 裸响应）——两套契约并存，混用易解析错位。
3. `request` 对 POST 也重试 2 次 → 批改类接口可能重复提交任务（需确认是否只对 GET 重试）。

---

## 6. 打包产物专项验证（frozen 环境）

| # | 验证点 | 方法 | 预期 | 前置 |
|---|--------|------|------|------|
| P1 | exe 冷启动 | 双击 `dist/叙阅/叙阅.exe` | socket 探测 6888 失败→起 uvicorn；lifespan `init_db()`+`migrate_legacy_grading_dirs_if_needed()`+1.5s 后自动开浏览器 | 端口空闲 |
| P2 | 前端内嵌挂载 | 访问 `http://127.0.0.1:6888/` | `_MEIPASS/frontend` 命中；SPA catch-all 返回 index.html；assets 可加载 | - |
| P3 | .env 缺失 fail-fast | 移走 `dist/叙阅/.env` 再启动 | `config._get_env_file()` 回退 `_MEIPASS/.env`；缺 DB/JWT→ValueError 启动即退 | - |
| P4 | 重复启动 | 服务运行中再双击 exe | 探测 6888 成功→只 `webbrowser.open`+`sys.exit(0)`，不重复起服务 | 首实例已监听 |
| P5 | 端口冲突 | 先用其他程序占 6888 再启动 | **误判为"服务在跑"只开浏览器，页面实际 502**（需回归） | 非本服务占用 |
| P6 | 日志重定向 | 冷启动后看 `dist/叙阅/logs/app.log` | frozen 且 stdout/stderr 为 None→重定向到 logs（append/utf-8/buffering=1） | 首次启动 |
| P7 | 杀进程后重开、数据持久化 | 完成任务后 taskkill，重启 | `grading_data_all/` 在 exe 同目录持久化；history/错题库恢复 | 有历史数据 |
| P8 | /system/exit | 前端"退出叙阅"按钮 | 仅 127.0.0.1/::1/localhost、仅 frozen→0.25s 后 `os._exit(0)`；非本机→403；开发→400 | frozen |
| P9 | 扫描/打印降级 | 无 pywin32 环境 | `/grading/scanners`→`{ok:false,msg:'请安装 pywin32...'}`；`/printers` 同；不崩 | 无 pywin32 |
| P10 | 下载票鉴权 | 访问留痕图 `?ticket=` | 票绑 user+resource、10min 过期；过期/换 resource→401；无票→401；`../`→403 | 已生成留痕图 |
| P11 | 中文路径/文件名 | 复制 dist 到含中文/空格路径；上传中文名 | `_get_env_file` 用 `sys.executable` 定位支持中文；上传清洗落盘 | Windows |
| P12 | 依赖缺失 fail-fast（非 frozen） | 清掉 sqlalchemy 后 `python run.py` | 提示"缺少后端依赖…pip install"+exit(1) | 非 frozen |
| P13 | 临时目录规避 C 盘 | 启动后查 `temp/` | `tempfile.tempdir` 指向项目根 temp | - |
| P14 | AUTO_DDL 与生产库 | 查 `.env` AUTO_DDL | 默认 false→init_db/sync 直接返回不自动建表；显式 true 才建 | 生产 RDS |
| P15 | 登录限流在打包环境 | 连续输错 5 次 | 429"15 分钟后再试"；日志审计；重启 exe 锁清空 | frozen |

---

## 7. 安全专项汇总（跨域集中验证）

| 类别 | 验证点 |
|------|--------|
| 路径穿越 | resources 上传/删除/重命名/打包/邮件；grading `_safe_folder_name` 的 `.` 允许；ct-image `..` 拦截；download 票 |
| IDOR/越权 | assessment start/answers；四大分析域；student_ops 列表；return_book_borrow；print-pdf |
| 上传安全 | 无大小/魔数/文件名清洗（grading/students/resources）；Excel 公式注入风险 |
| 凭据泄露 | dist `.env` 明文；multi_project_settings.json 明文；system_settings AI key 明文 |
| PII 外发 | class_analysis/class_review/targeted/ai_diagnosis 学生姓名+作答+试卷图发第三方 |
| 邮件滥用 | lesson_plans send-email 开放转发；todos notify-due 无限流 |
| 认证 | 登录锁内存实现；JWT 7 天无 revocation；无验证码/注册 |

---

## 8. 执行顺序建议

1. **先修 C1**（real_grade_pipeline 缺 return）——挡着 grading P0 主链路，不修快速批改全测不了。
2. **修复 C2/C3/C4**（路径穿越、assessment 越权、print-pdf 越权）——三个高危安全洞。
3. 处理 C5/C6（凭据外泄 + 图片鉴权契约）。
4. 跑 P0 主链路功能验证（grading 全流程 → auth/classes/students → assessment → portfolio → student_ops → exams）。
5. 跑 P1 分析/AI（含 mock 降级路径）。
6. 跑 P2 管理/系统 + 打包产物专项（需 frozen 环境）。
7. 回归修复项 + 前端契约风险点。
