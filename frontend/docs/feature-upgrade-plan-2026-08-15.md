# 叙阅功能提升实施计划(竞品可学习清单 → 可执行落地方案)

> 生成:2026-08-15 | 方法:workflow `feature-upgrade-audit`(5 audit agent 并行扫描代码库 + 1 合成 agent),6 agent 全绿,231 次工具调用
> 输入:docs/competitive-analysis-2026-08-15.md 第四章「可学习扩展的功能清单」(竞品对比见该文档)
> 产出:17 项可执行实施计划(无 P0,P1×6 / P2×9 / P3×2),含文件级落点、依赖、验收标准

> **实施进度(2026-08-15)**:第一批 3 项已落地(master `6419b35`)——B4 典型错误「查看名单」接线、前端架构 URL 路由化+懒加载、F3 零设备接入指引页。验收:tsc -b 0 / vitest 36 / i18n parity 0 新增。后续批次见各节 owner/依赖标注。
>
> **第二批 2A(五育对齐+AI 素养)已落地(2026-08-15)**:前端 `a698357` / 后端 `b857578`。前端:AI 素养维度全链展示(共享常量/雷达/记录/报告/班级总览/争章分类)+ i18n zh/en,缺省按 0;后端:`indicator_definitions` 三层级(`level`+自引用 `parent_id`+幂等迁移 SQL)+ `ai_literacy` 维度 + `ai_course/ai_project` 来源 + `GET /portfolio/indicators/tree`。验收:前端 tsc -b 0 / vitest 36 全绿;后端本地 Docker 冒烟(远程 RDS 不可达,迁移 SQL 需有库权限环境执行)。格式噪声已清理(Prettier 默认折行回退,仅留功能行)。
>
> **第二批 2B(监护人同意闭环+合规后台)已落地(2026-08-15)**:前端 `697f11a` / 后端 `6b11a38`。前端:管理端「合规后台」页(访问日志查询+年度审计导出+consent 统计)+「个人信息行权」页(教师/管理员代办查/导/改/删)+ i18n zh/en 81×2;后端:`access_logs` 表 + `log_access` 留痕(敏感读取/consent 变更/行权/导出)+ 行权接口 `/admin/rights/data*`(可更正字段白名单+confirm 二次校验+匿名化删除)+ 审计 `/admin/audit/report`+ 幂等迁移 SQL。验收:前端 tsc 0 / vitest 36 / i18n 对称;后端 TestClient 双角色全链路冒烟(行权权限=管理员+班级教师,审计仅管理员)。**决策:行权页承载方=教师/管理员代办(无家长端)**。
>
> **第二批 2C(隐私优先成绩单)已落地(2026-08-15)**:前端 `160c072` / 后端 `8121f2b`。前端:`useExamScores` 去 Supabase 直连改走后端鉴权 API(堵漏,消除 TODO 风险)、`ScoresTab` 等级徽标+「分数⇄等级」切换、`RankingDashboard` 去「最高分+第一名」点名+等级分布+i18n;后端:`exam_scores.grade` 列(幂等迁移 SQL)+ `grade_for_score` 纯函数(≥85/70/60/<60 → excellent/good/pass/needs_work)+ 新增 `GET/POST /student-analysis/exam-scores`(走 `can_view_class`)+ `rankings[].grade` + 家长视图裁剪(去 rank,契约预埋未来家长端)。验收:前端 tsc 0 / vitest 36 / i18n 对称;后端 pytest 9 passed(纯函数边界+TestClient 双角色+迁移幂等)。并行 agent 契约偏差已对齐(前端路径/body 匹配后端 `/student-analysis/exam-scores`+数组 body)。
>
> **第二批 2D(AI 内容统一标识)已落地(2026-08-15)**:前端 `fbacdb5` / 后端 `f86c992`。前端:新增 `AIGeneratedBadge` 统一组件 + `common.aiGenerated` i18n,接入 5 处核心 AI 内容展示(对话气泡/作文批改/课堂讲评/班级学情/靶向诊断);后端:3 张 AI 落库表(`class_analysis_reports`/`class_review_sessions`/`targeted_improvement_reports`)加 `is_ai`+`ai_meta` 列(幂等迁移 SQL,参照已达标的 `assessment_comments`)+ AI 组卷响应每题 `is_ai=true` + AI 诊断 JSON 落盘带 meta。验收:前端 tsc 0 / vitest 36 / i18n 对称;后端 pytest 19 passed(10 新增+9 既有,零回归)。遗留(标注后续批次):SSE 流(`ai_chat`/`ai_auto_report`)、`report_snapshots.payload`、grading 本地 JSON 历史的隐式标识。
>
> **第二批 2E(学校级 AI 管控)已落地(2026-08-15)**:前端 `4fd9697` / 后端 `b7a3732`。后端:`feature_flags` 定为后端 MySQL 唯一事实源(`GET /feature-flags` + `PATCH /feature-flags/{key}` 管理员改 + 9 个默认 flag 幂等种子迁移)+ 新增 `services/ai_policy.py` 统一闸门(`is_feature_enabled` / `require_ai_access` 角色白名单 / `assert_no_sensitive_input` 身份证+手机号+隐私问句)+ 6 个 AI 端点接线(ai_chat/ai_diagnosis/ai_review×3/smart_exam/ai_comment,disabled→403)+ **AI 评语 PII 匿名化补漏**(`build_comment_messages` 拼 prompt 前 Anonymizer 匿名学生真名,消除把真名外发第三方模型缺口);前端:`useFeatureFlags`/`AdminFeatures` 从 Supabase 切后端、Sidebar NAV_ITEMS 加 `featureKey` + Index 路由/FloatingChat 挂载过滤。验收:前端 tsc 0 / vitest 36 / i18n 对称;后端 pytest 31 passed(12 新增+19 既有,零回归)。防直接复制 AI 作答留前端 CSS user-select 后续批次。
>
> **第二批 2F(数据分类分级)已落地(2026-08-15)**:后端 `1e66533`(前端无大改)。交付文档 `docs/contracts/13-data-classification.md`(JY/T 0661-2025 分级 L2-L5,7 表字段级清单+出参映射+脱敏规则库+加密方案设计+合规对齐)+ 统一掩码工具 `field_masking.py`(手机/学籍号/住址/姓名)+ AI 出站 PII 补漏 5 处(`ai_chat_student_roster` 不下发电话/住址、`ai_chat_data_schema` 不广告 PII 列、`ai_chat_mysql_executor` 结果集剥离敏感列防御纵深、`wrong_question_db` 不再写学籍号进 AI prompt)。验收:后端 pytest 45 passed(14 新增+31 既有,零回归)。遗留:加密落库(AES-256-GCM)仅出方案待专项立项;学生列表/行权 CSV 按角色分层脱敏已于收尾批次完成(见下)。
>
> **第二批(2A-2F)六子批全收官(2026-08-15)**:2A 五育对齐+AI 素养(a698357/b857578)、2B 监护人同意闭环+合规后台(697f11a/6b11a38)、2C 隐私优先成绩单(160c072/8121f2b)、2D AI 内容统一标识(fbacdb5/f86c992)、2E 学校级 AI 管控(4fd9697/b7a3732)、2F 数据分类分级(后端 1e66533)。前端 master `4fd9697` / 后端 master `1e66533`。资质项(E06/E07/E17)与卖点运营项(E10-E13/E15/E16)按用户决策未排。
>
> **第二批收尾(2026-08-15)**:① **迁移链式验证+执行手册**:5 份本批迁移(2A-2E)+ 前置 v1/v2 在本地 Docker MySQL 链式执行与幂等二次执行全部通过(scratch 库 36 表),产出 `docs/migration-execution-handbook-2026-08-15.md`(执行顺序/验证 SQL/回滚建议;实测依赖坑:2C/2D 缺表静默跳过、2E 缺表硬报错、v1 纯空库 ERROR 1824——正式库由应用 create_all 建基础表,无碍但需验证 SQL 复查)。正式环境迁移 SQL 仍待有库权限环境按手册第 4 节执行。② **泄露应急预案** `docs/data-breach-response-plan-2026-08-15.md`(PIPL 57 / 数据安全法 22 / 等保 25,三级分级+六步处置+通知义务+演练+快报/联系表模板,衔接 2B access_logs/行权留痕/审计导出)。③ **学生 PII 角色分层脱敏已落地(2026-08-15)**:后端 `72d88b0`。`class_access.can_view_student_pii`(全局管理员+班主任 head 看完整,副班主任/协作教师看掩码);`GET /students` 按角色 `include_pii` 掩码(student_number/phone/parent_phone/parent_name/address → field_masking,birthday → None);行权 CSV 导出一并治理(堵 is_teacher 绕过洞);POST/PATCH 回显保持完整(已被 can_manage_students 限 head)。新增 `tests/test_e10_student_pii.py` 12 例,后端 pytest 57 passed 零回归。跨接口学号不一致(class_analysis 等仍返回完整)记为遗留。

---

## 一、核心判断(先读这个)

**17 项里只有 4 项是纯前端、本周可落地**(B4 / F3 / 架构路由化 / D5 诊断趋势);**三项战略级 P1(区域级学情、开放 API、校本题库)全部卡后端数据层/契约**,前端只能做骨架无法独立验收。

**后端缺口的共性根因(3 条)**:

1. **多租户 = 每校一个 MySQL 库**(multi_project.py 为 DB 级隔离),跨校聚合需跨库聚合服务或共享库+school_id 重构
2. **Class 模型无 school_id**(app/models/class_model.py L8-18 仅 user_id/school_level/grade/name/student_count),全 models 目录无 school/org 表
3. **题目 ID 为前端本地随机生成**(`q_时间戳_随机`),每卷独立,无跨卷聚合锚点(校本题库 C2 的前置硬依赖)

**护城河域(growth)关键发现**:五育画像/综评档案/成长印记/学分银行/动态评估**前后端已高度成型**(后端 5 类事件自动写成长记录、动态评估标签已进 AI 评语 prompt)。真正的差距不是"没有闭环",而是**闭环最后一公里**:

- 成长册(照片+记录+评语合成可打印册)——前后端均无
- 学分银行余额/兑换**不进学期报告**(ReportResponse 无 credit 字段)
- 综评档案无"报告快照+相册+奖章"一体化内容查看
- AI 对话交互**不落库**,无法做交互级薄弱点趋势

→ 战略上:护城河已建成,缺的是让它"可交付/可验收/可讲给局端听"的收口能力。

---

## 二、本周可落地(纯前端,无后端依赖)

### 1. B4 班级共性错题「查看名单」接线 — effort S / frontend

- **落点**:`src/components/class-detail/question-analysis/TypicalErrors.tsx`
- **改动**:启用 L52-57 现 disabled 的「查看名单」按钮,弹窗展示已有 wrongStudents 名单(数据已在前端模型);校验 QuestionDetail.tsx/types.ts 数据贯通、讲评页按共性错误分组视图正确渲染
- **验收**:按钮可点击弹名单;讲评页按共性错误分组正确渲染;`tsc -b --force` 通过
- **依赖**:现有 /class-review/report + /grading/error-book 契约,无新后端

### 2. F3 零设备改造/拍照即用进校入口 — effort M / frontend

- **落点**:`src/pages/Index.tsx:424-431`(「多端管理」PlaceholderPage)+ i18n settings.ts/zh.ts/en.ts(+ 可选 OnboardingTour.tsx)
- **改动**:占位页改为「接入方式」指引页,手机拍照/文件上传/扫描仪 3 种接入卡片,各自触发现有能力(相机→PhotoGradingDialog、上传→UploadZone、扫描→ScanQueue);补 i18n zh/en 对等
- **验收**:导航进入新接入指引页,≥3 种接入卡片且各触发现有能力;tsc 0 错误;i18n 对等
- **依赖**:复用现有拍照/上传端点,无强后端依赖

### 3. 前端架构 URL 路由化 + 懒加载 — effort M / frontend

- **落点**:`src/pages/Index.tsx:138-147,197-443` + `src/App.tsx:87` + `src/components/Sidebar.tsx NAV_ITEMS`
- **改动**:BrowserRouter 替换单页 state 式 activeNavId 路由;React.lazy 懒加载大型功能域;迁移 localStorage 持久化 activeNavId 并兼容旧 URL;新功能域标准落点 = Sidebar 增 nav + Index 增 case + services 增模块 + i18n 增 module
- **验收**:新增演示功能域全链路可见(nav+页面+双语 i18n);tsc 0 错误;vitest 现有用例全绿
- **依赖**:纯前端重构(为区域视图/开放平台等大功能域铺路)

### 4. D5 实时诊断趋势视图(纯前端子集)— effort M / frontend

- **落点**:`src/components/assessment/AssessmentPage.tsx` + AssessmentResultsTab.tsx
- **改动**:加「诊断」模式/页签;复用 listStudentResults 全历史结果(dimension_percents+created_at)画维度趋势曲线 + 上次 vs 本次修正提示 + 薄弱维度标记
- **验收**:同一题组完成 ≥2 次施测后,诊断页签按维度渲染 dimension_percents 随时间折线图,展示上次 vs 本次变化与薄弱维度标记;tsc 通过
- **依赖**:现有 AssessmentResult 历史累积已够,后端可不动

---

## 三、完整实施计划(17 项)

| ref   | 阶段 | 功能                             | 落点                                                | effort | owner    | 可执行性                    |
| ----- | ---- | -------------------------------- | --------------------------------------------------- | ------ | -------- | --------------------------- |
| B4    | P1   | 共性错题「查看名单」接线         | TypicalErrors.tsx                                   | S      | frontend | ✅ 本周可做                 |
| F3    | P1   | 零设备改造/拍照即用入口          | Index.tsx + i18n                                    | M      | frontend | ✅ 本周可做                 |
| 架构  | P2   | URL 路由化+懒加载                | Index/App/Sidebar                                   | M      | frontend | ✅ 本周可做                 |
| D5    | P3   | 诊断趋势视图(纯前端)             | AssessmentPage                                      | M      | frontend | ✅ 本周可做                 |
| A7    | P1   | 潦草手写 OCR 增强                | 后端 ocr.py + pipeline.py                           | L      | backend  | ⚠ 需 PaddleOCR 模型升级     |
| D1+F1 | P1   | 区域级学情/局端多校视图          | 后端 school/region 数据层 + 前端区域视图            | XL     | both     | ⛔ 卡数据层(无 school 表)   |
| C1    | P1   | 开放 API/开发者平台              | 后端 openapi.py + api_keys + 前端 OpenPlatform.tsx  | XL     | both     | ⛔ 卡密钥体系(无 api_keys)  |
| C2    | P1   | 校本题库带正答率                 | 后端 school_question_bank + 题目指纹 + 前端组卷面板 | XL     | both     | ⛔ 卡题目稳定 ID 指纹       |
| A1    | P2   | 答案聚类批量批改                 | GradingStartPage + 后端 cluster 端点                | L      | both     | ⚠ 需后端逐题聚合契约        |
| A2    | P2   | 动态 Rubric(结构化维度+改分重批) | GradingStartPage + 批改 prompt                      | M      | both     | ⚠ 需结构化维度设计          |
| A3    | P2   | 匿名批改                         | GradingStartPage + 姓名区 bbox                      | M      | both     | ⚠ 需后端姓名定位            |
| A6    | P2   | 主客观题分流                     | 后端 pipeline + 结果区复核清单                      | XL     | both     | ⚠ 主链路改造,回归风险高     |
| B1    | P2   | 讲知识升维(错题→知识点串讲)      | ErrorBookDetail + KnowledgeDetailPanel              | M      | frontend | ✅ 复用现有契约             |
| C3    | P2   | AI 出题多源输入+高质量干扰项     | ExamGenPage + /exams/ai-generate                    | L      | both     | ⚠ 需后端扩展请求模型+prompt |
| D2    | P2   | 异常预警(旷课/健康)              | 后端 student_ops 聚合端点 + CampusSection Tab       | L      | both     | ⚠ 跨表规则判定,需造数验证   |
| E1    | P2   | 智能体可编排                     | 智能体广场 + FloatingChat + agent 定义表            | XL     | both     | ⚠ 需后端 agent 装配 API     |
| A4    | P3   | 步骤级纠错                       | 后端 prompt + 错题本契约扩展                        | L      | both     | ⚠ 需 prompt 升级+契约扩展   |

---

## 四、护城河「最后一公里」专项(战略价值最高)

growth 域审核确认护城河已成型,收口差距 4 处(均对"可交付给局端/家长"有直接影响):

| #   | 缺口                                         | 现状证据                      | 价值                                   |
| --- | -------------------------------------------- | ----------------------------- | -------------------------------------- |
| G1  | **成长册**(照片+记录+评语合成可打印册)       | 前后端均无此模块              | 综评材料实体化交付,局端/家长可直接带走 |
| G2  | 学分银行余额/兑换**不进学期报告**            | ReportResponse 无 credit 字段 | 报告完整性,激励闭环可视化              |
| G3  | 综评档案无"报告快照+相册+奖章"**一体化查看** | 各模块独立                    | 成长档案叙事化,竞品展示面              |
| G4  | AI 对话交互**不落库** → 无交互级薄弱点趋势   | 后端无 chat 记录表            | 学情数据资产化(E2)前置                 |

建议:G1 优先(可打印成长册是"成长数据闭环"对外可交付的载体,能直接给局端演示)。

---

## 五、政策驱动功能完善(第二批,2026-08-15)

> 来源:docs/policy-ai-education-2026-08-15.md 完善建议 E01-E17;剔除**资质项**(E06 双备案/E07 AI 备案路径/E17 国家平台入驻)与**卖点/运营项**(E10/E11/E12/E13/E15/E16),保留 8 项代码可排期功能
> 落点由 Explore agent 定位(2026-08-15)。**护城河模块前后端均已成型,本批 = 「对齐国家框架 + 合规能力补强」,零架构重构**

### 5.1 E01 五育指标对齐国家五维度(前后端 / M)

- **落点**:前端 `wuyu-profile/WuyuProfilePage.tsx` + `PortfolioDetailPanel/GrowthRecordsPanel/SemesterReportPanel`;后端 `models/student_portfolio.py`、`student_growth_record.py`、`indicator_definition.py`
- **现状**:`student_portfolios.dimensions` 已是五维度 JSON(`moral/intellectual/physical/aesthetic/labor`),`growth_records` 已有 `dimension`+`indicator_id`
- **改动**:`indicator_definition` 支持层级(维度→方面→观测点,对齐教基〔2021〕3号五方面);可观测点级采集项;展示层对齐
- **验收**:五育指标结构对齐国家五维度;层级化可配置;tsc -b / 后端路由 / 现有 vitest 回归

### 5.2 E02 综评/成长印记新增「AI 素养」维度(前后端 / M)

- **落点**:同 E01(`dimensions` JSON + `dimension` 枚举 + 成长印记采集);后端 `models/student_portfolio.py`、`student_growth_record.py`
- **现状**:`dimension` 枚举 = `moral|intellectual|physical|aesthetic|labor`,无 ai
- **改动**:维度枚举 + JSON 扩展 `ai_literacy`;支持记录 AI 课程过程性成果(成果/作品/素养表现);综评档案含 AI 素养
- **验收**:新增维度全链可见;可记录 AI 课程成果;与 E01 同一批

### 5.3 E03 监护人同意闭环(前后端 / M)

- **落点**:前端 `assessment/AssessmentConsentTab.tsx` + `ParentBindingDialog`;后端 `routers/assessment.py` + `services/assessment/consent.py` + **新增 access_log 表**
- **现状**:grant/withdraw/restore 状态机已有(`guardian_consent.status/version/granted_at/withdrawn_at`,撤回即冻结不删数据);**缺独立行权页面与访问日志**
- **改动**:①`access_log` 表 + 访问留痕写入(谁何时看了哪些学生数据)②学生/家长**一键行权页**(查询/导出/更正/删除,删除触发匿名化或物理删)
- **验收**:访问日志留痕产品内可见;行权页可用;撤回同意冻结与行权联动

### 5.4 E04 隐私优先成绩单(前后端 / M)

- **落点**:前端 `class-detail/ScoresTab.tsx` + `compare-analysis/RankingDashboard.tsx` + `CompareOverviewCard.tsx` + `GradeAnalysisPage.tsx`;后端 `models/exam_score.py` + `routers/student_analysis.py`
- **现状**:成绩/排名教师端**公开渲染,无 visibility 字段,无结构化等级制**(仅展示层 优秀/及格/不及格 与 tier A/B/C 配色)
- **改动**:①`exam_scores` 加等级字段(4-5 级)或派生等级 ②成绩单等级制渲染 ③排名可见范围控制(家长只见自家、教师按班最小授权、禁年级公开排名)
- **验收**:等级制成绩单;排名一对一可见;无年级公开排名;现有对比分析回归通过
- **风险**:RankingDashboard 是既有功能,可见范围改造需回归排名榜与对比分析

### 5.5 E05 AI 内容显式+隐式标识(前后端 / M)

- **落点**:统一标识组件 + 后端 **6 个 AI 产出点**(`portfolio/llm.py`、`ai_auto_report/generator.py`、`class_review.py`、`targeted_improvement.py`、`student_analysis.py` ai-diagnosis、grading 域)+ 前端展示(FloatingChat 流式、AiCommentPanel、讲评/靶向/组卷)
- **现状**:smart-gen 有「AI 生成」标签、CommentSection 有 `ai_model`;**无全局统一标识体系**
- **改动**:统一「AI 生成」标识组件/工具;所有 AI 产出加显式徽标;导出文件埋隐式元数据
- **验收**:全部 AI 产出统一标识;导出含元数据

### 5.6 E08 学校级 AI 管控(后端为主 / M)

- **落点**:后端 `services/ai_chat_guard.py`/`ai_chat_privacy.py`/`ai_chat_access.py` + `models/feature_flag.py`;前端 `settings/SystemSettingsPage.tsx` + `smart-gen/AIIntegrationPanel.tsx` 开关
- **现状**:禁词闸门(comment.py `FORBIDDEN_WORDS` fail-closed)、隐私表拦截(PRIVACY_BLOCKED_MYSQL_TABLES)、账号隔离、feature_flag 已有;**无全局统一管控框架**
- **改动**:统一 AI 管控:白名单开关、按学段限制学生端 AI 入口、敏感输入拦截(试题/个人身份信息)、防直接复制 AI 作答
- **验收**:开关可配生效;敏感输入拦截;学生端入口限制

### 5.7 E09 数据分类分级+脱敏加密(后端为主 / M)

- **落点**:后端各模型/路由(学生字段出参层)+ 交付文档;前端无大改
- **现状**:`ai_auto_report` 有 PII 匿名化(anonymize.py);**无统一分类分级**
- **改动**:按 JY/T 0661-2025 对学生字段逐一定级(L3-L5),输出「教育数据分类分级清单」交付文档;敏感字段脱敏/加密落地
- **验收**:清单交付;敏感字段脱敏或加密(学籍号/成绩/健康信息)

### 5.8 E14 合规后台(后端为主 / M)

- **落点**:`access_log` 表(与 E03 复用)+ 审计导出路由 + 前端设置页
- **现状**:无审计导出,访问日志缺失
- **改动**:年度合规审计报告导出;访问日志查询页;泄露应急预案文档与报告告知流程
- **验收**:审计报告可导出;与 E03 同一批

### 批次划分建议(按依赖合并)

| 批次 | 内容                      | 依赖               | 前后端   |
| ---- | ------------------------- | ------------------ | -------- |
| 2A   | E01+E02 五育对齐+AI 素养  | 动五育模块同批改   | 前后端   |
| 2B   | E03+E14 同意闭环+合规后台 | 共用 access_log 表 | 前后端   |
| 2C   | E04 隐私成绩单            | 独立               | 前后端   |
| 2D   | E05 AI 统一标识           | 独立               | 前后端   |
| 2E   | E08 AI 管控               | 独立               | 后端为主 |
| 2F   | E09 分类分级              | 独立               | 后端为主 |

---

## 六、建议执行顺序

1. **第一批已落地(master `6419b35`)**:B4 错题名单接线 + 架构 URL 路由化 + F3 零设备入口;D5 诊断趋势视图(纯前端)待排
2. **第二批·政策功能完善(本批)**:按依赖分 6 子批——**2A 五育对齐+AI 素养 → 2B 同意闭环+合规后台 → 2C 隐私成绩单 → 2D AI 统一标识 → 2E AI 管控 → 2F 分类分级**;2A/2B 优先(直接强化护城河主卖点,资质项 E06/E07/E17 已剔除不排)
3. **后端专项立项(一次排 3 个架构缺口)**:school/region 数据层 + 题目稳定 ID 指纹 + api_keys 密钥体系 → 解锁 D1/F1、C1、C2 三项战略 P1
4. **护城河收口**:G1 成长册(可打印)→ G2 学分进报告 → G3 一体化查看 → G4 AI 交互落库
5. **批改增效**:A7 OCR 增强(后端独立可做)→ A2 Rubric / A3 匿名(挂现有批改链)

## 七、主要风险

- 区域多校视图是架构级缺口:多租户每校一库 + 无 school 表,跨校聚合需跨库服务或共享库重构,数据层未立项前不可验收
- 开放 API / 校本题库依赖后端新契约,前端无法独立落地
- A1/A3 依赖后端逐题聚合与姓名区 bbox 契约;现有 completed[].result 字符串脆弱,前端硬解析有回归风险
- A7 效果提升不可控,需记录前后样本做对比验收
- A6 主客观分流是主链路改造,回归风险高
- C3 PDF/URL 解析依赖现有试卷切题脚本,不可复用则需额外投入
- D2 替课类预警数据源缺失(现有数据不足支撑替课识别),先做旷课/健康规则
- **第二批(2026-08-15)**:2C 隐私成绩单改动 RankingDashboard 排名榜需回归对比分析;2A/2B 动五育模块维度结构与 consent 状态机,需跑现有 portfolio/assessment 测试与造数验证

---

_相关:[competitive-analysis-2026-08-15.md](competitive-analysis-2026-08-15.md)(竞品对比矩阵+可学习清单) | [zhong-chun-feng-replica-checklist.md](zhong-chun-feng-replica-checklist.md)(种春风复刻清单)_
