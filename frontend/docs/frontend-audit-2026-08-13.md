# 叙阅前端全面审计记录（2026-08-13）

> 用项目级 workflow（`.claude/workflows/frontend-full-audit.js`，commit `e7c50be`）对前端做全面深度审计：
> 15 个 scan agent 覆盖 13 功能域 × 11 维度 + API 契约 + i18n，P0/P1 对抗验证。
> 审计对象为 `grade-buddy-scan-main`（React/Vite SPA，功能聚合于 Index.tsx/Admin.tsx）。

## 一、审计规模与结论

| 指标             | 值                                |
| ---------------- | --------------------------------- |
| scan agent 数    | 15（13 功能域 + API/契约 + i18n） |
| 原始 findings    | 150 条                            |
| 去重后           | 149 条（P0=5, P1=28, P2/P3=116）  |
| 对抗验证         | 15 条 P0/P1 → 14 确认真实, 1 drop |
| 验证后严重度分布 | P1=22, P2=76, P3=50               |

> 注：原始 5 条 P0 经对抗验证全部降级为 P1/P2（详见第三节裁决说明）。前端构建当前通过（vite build 25.6s，exit 0）。

## 二、修复决策（用户拍板 2026-08-13）

| 决策点                          | 结论                                                    |
| ------------------------------- | ------------------------------------------------------- |
| 隔离方案                        | 前端纳入 git（实际已有基线 `f4755c9`），修复走 worktree |
| mock 域（4+1）                  | **接真实 API**                                          |
| i18n 英文半成品（716 键中文值） | **本轮不碰**，产品方向未定                              |
| 修复范围                        | **P1 全量**（含 2 处 XSS）                              |

## 三、发现明细

### 3.1 安全（XSS，P1，必修）

- `FloatingChat.tsx:422`：AI 聊天内容 `dangerouslySetInnerHTML` 原样渲染，`[[跳转:]]` 标签未转义可注入 HTML
- `smart-gen/AIIntegrationPanel.tsx:138`：AI 流式输出未净化直插 DOM，存储型 XSS 向量

### 3.2 纯 mock 假数据冒充真功能（影响教学决策，用户决定接真实 API）

- `class-detail/CompareAnalysisPage.tsx:40`（已验证 high）：对比分析域全 mock，`compareData.ts` hash 伪随机生成排名/指标/经验，不接任何 API
- `class-detail/CompareAnalysisPage.tsx:35`（已验证 high）：对标范围选择器（跨年级/校际联盟/历史同期）仅换随机种子，不改变数据结构与语义
- `class-detail/LayeredPushPage.tsx:19`：分层推送全 mock，所有按钮无 onClick，后端无 layered/dingtalk 路由
- `settings/class-manage/DataSyncPanel.tsx:62`：钉钉集成面板纯 mock，按钮无 onClick、Switch 非受控、日志假数据
- `class-detail/question-analysis/analysisData.ts:71`：试卷分析全本地 hash mock，不调用后端已有 `/class-analysis` 真实接口

### 3.3 不可达功能域（死代码/功能缺失）

- `QuestionAnalysisPage.tsx:23`（已验证 high）：试卷分析 + 知识图谱两页面被 Index.tsx import 但从未进 activeNavId switch，整个域 100% 不可达
- `settings/subject-config/SubjectConfigPage.tsx:36`：科目配置子域无任何导航入口

### 3.4 功能 bug

- `student-panorama/WrongQuestionDetailDialog.tsx:55`（已验证 high）：把后端返回的错题对象当字符串处理，打开永远空态
- `grading/GradingStartPage.tsx:770`：卸载未清理 `essayGradePollTimerRef`，切页后轮询持续后台运行
- `resource-lib/ResourceLibPage.tsx:814`：「发送给其他人」契约漂移，实际不可用
- `resource-lib/ResourceLibPage.tsx:255`：删除激活文件夹后闭包过期，UI 卡「未选择文件夹」
- `settings/account-manage/AccountManagePage.tsx:171`：调已被后端删除的 `view-password` 接口，必然失败
- `settings/class-manage/StudentTable.tsx:130`：批量删除吞失败后无条件 toast 成功；清空失败仅 console.error
- `wuyu-profile/SemesterReportPanel.tsx:73`：冻结失败错误 toast 兜底空字符串，失败静默
- `smart-exam/ExamGenPage.tsx:60`：忽略 `loadResourceId`/`onResourceLoaded`，资源库到组卷跨页跳转死链

### 3.5 i18n（本轮不修，记录备查）

- `classDetail.ts:787`：classDetailEn 781 键中 716 个为中文值，EN 下整个班级详情域显示中文
- chat-cards/class-detail/prep-plan/smart-gen 等 40+ 组件数百处 JSX 硬编码中文未走 t()
- 缺失 key：`studentOps.credits.status`、`studentOps.rewards.insufficientBalance`、`assessment.definition.form.questionsPlaceholder`、`resourceLib.tips.*` 等

### 3.6 已验证 P2 摘录（不在本轮范围）

- `ClassDashboard.tsx:101`：副班主任前端显示学生管理按钮，后端仅允许 head，操作全 403
- `CompareAnalysisPage.tsx:38`：analytics-compare 未纳入 CLASS_REQUIRED_IDS，缺班级时不兜底
- `ClassPortraitPage.tsx:112`：PDF 导出文件名含斜杠，浏览器截断存成 13.pdf；html2canvas 1.4.1 无法可靠栅格化 recharts SVG，趋势图导出空白
- `GlobalSearchBar.tsx:25`：快捷操作「知识图谱」指向不存在的 navId
- `TopHeader.tsx:316`：「我的」下拉两个入口是死链落占位页
- 大量域内「死按钮」无 onClick（compare-analysis/ExperienceMining、question-analysis/TypicalErrors、layered-push 等）
- `AssessmentConsentTab.tsx:44`：监护人同意总览 N+1 查询
- `student-panorama/StudentPanoramaPage.tsx:47`：localStorage 读写无 try/catch 可能白屏

### 3.7 审计误判纠正（复核后）

- `ClassDetailHeader.tsx:45` 原始 P0「重复 const 声明导致编译失败」**误判**：实测 vite build 通过（该文件零外部引用，是纯死文件，未被打包），esbuild 单文件解析确认存在重复声明。定性应为「死代码 + 潜在构建炸弹」，非 P0。

## 三.5 Batch 3 落地记录（mock 接真实 API，2026-08-13）

| 域                            | 决策                  | 落地                                                                                                                                                                                                                                                                                                                                                               | commit                      |
| ----------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------- |
| 分层推送 LayeredPushPage      | 后端无接口 → 标注演示 | 演示角标 + demoToast，按钮禁用，不冒充真功能                                                                                                                                                                                                                                                                                                                       | `4e85fe1`                   |
| 钉钉同步 DataSyncPanel        | 后端无接口 → 标注演示 | Switch 受控禁用，日志标演示数据                                                                                                                                                                                                                                                                                                                                    | `4e85fe1`                   |
| 试卷分析 QuestionAnalysisPage | 接真实 + 挂导航       | 挂 `analytics-questions` 导航，`useQuery` 接 `getClassReviewReport`+`getErrorBookFolderDetail`，缺口降级 `DegradedMetric`/`DegradedSection`                                                                                                                                                                                                                        | `47449bd`                   |
| 对比分析 CompareAnalysisPage  | 接真实 + 缺口降级     | `useQuery` 接 `getClassAnalysisReport`；新增 `compareAnalysisAdapter.ts` 转换层；RankingDashboard=班内真实 `rankings[]`，MetricsComparison=真实均分/中位/最高/最低/错误率，HistoryTrend=`exam_summaries` 均分折线，ChasingPlan=`weak_points`+教学建议；跨班排名/标杆经验/六维雷达无数据源整卡空态降级；CompareHeader scope 仅年级可用；删 `compareData.ts` 全 mock | `fd10536` + merge `4110cac` |
| 知识图谱                      | 不开放（后端无接口）  | 保持不可达                                                                                                                                                                                                                                                                                                                                                         | —                           |

> 验收：tsc 对比 master 基线 40 条错误零新增；残留 mock 生成器（generateClassRankings/compareData/hash()）全仓 grep 清零。Tour 引导文案「年级排名」→「班内排名」收尾（worktree fix-tour）。

## 三.6 P2 修复落地记录（2026-08-13，两批 38 项）

| 批次            | 范围                       | 关键改动                                                                                                                                                                                                                                                                                                                        | commit    |
| --------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| P2 批1（22 项） | 死按钮死链 + 竞态/静默失败 | 死按钮全部禁用+tooltip（TypicalErrors/联系家长/调整座位/RequirementInput）；死链删或 toast（TopHeader/GlobalSearchBar 知识图谱/KnowledgeCard 查看图谱）；loadStats 竞态守卫、localStorage try/catch、LessonPlanPage Hooks 修复、GenericTour RAF 缓存、GrowthRecordsPanel useInfiniteQuery 分页、ResourceUploadDialog 删模拟预览 | `5ddfd31` |
| P2 批2（16 项） | 契约/越权 + 可访问性       | 副班主任按钮仅 head 可见；TeacherManageDialog 所有者入协作表；ExamGenPage 邮件发送非管理员禁用；AccountManagePage 多角色整体保存；multiProjectAccess 删除硬编码超管邮箱改后端 `multi_project_admin` 字段；**删除死代码 `grading-api.ts`**；gradingApi getToken 对齐 getAuthToken；6 处 aria-label/键盘可达 + 文件网格分页       | `52b1dd7` |

> 验收：tsc 40 基线全程不变，build 通过。P2 剩余未修项为纯 i18n 类（约 15 条，英文半成品方向未定）+ 死代码清理（ResourceLibHeader 13 个 mock 组件、WeekOverview 孤儿组件，删除需单独确认引用）。

## 三.7 死代码清理落地记录（2026-08-13）

| 类别                      | 清理内容                                                                                                                                                                                                                                                         | commit    |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| prep-plan 死组件（10）    | WeekOverview、SemesterTimeline、DailyPrepDetail、AIRecommendation、GradeCollaboration、ToolLibrary、PrepPlanHeader、PrepPlanTour、PrepPlanDailyTips、prepPlanData                                                                                                | `b14296e` |
| resource-lib 死组件（14） | ResourceLibHeader、AdvancedFilterPanel、AIRecommendPanel、ExamPaperZone、MyResourcesPanel、OtherResourcesBar、ResourceDetailPanel、DocumentPreview、MediaPlayer、ResourceListPanel、SharedResourcesPanel、ResourceLibTour、ResourceLibDailyTips、resourceLibData | `b14296e` |
| hooks 死文件（2）         | useResourceSearch、useTeachingResources                                                                                                                                                                                                                          | `b14296e` |
| i18n 孤儿 key（532）      | prepPlan 196 + resourceLib 336（删死组件连带清理，活 key 全保留）                                                                                                                                                                                                | `b14296e` |

> 验收：26 死文件删除后 prep-plan 剩 2 活文件（LessonPlanPage/PrepPlanPage）、resource-lib 剩 3 活文件（ExamDetectionConfirmDialog/ResourceLibPage/ResourceUploadDialog），5 活文件对死组件零引用已 grep 复核；i18n 结构闭合正确（prepPlan 352 键 / resourceLib 164 键）；tsc 40 基线零新增、build 通过。
> **连带收益**：删死代码后 resourceLibEn 已全英文（原 7 键中文值在被清的孤儿 key 里），i18n 翻译工作量收敛为 **classDetailEn 716 键**（原 classDetail 716 + resourceLib 7）。
> **遗留**：`ClassDetailHeader.tsx`（根目录零散死文件，零引用 + 重复 const 声明）不在死代码批内，交由 i18n 批1 删除。

## 三.8 i18n 字典翻译落地（2026-08-13）

- **classDetailEn 716 键中文值 → 英文**（`c13aa94`）：只动 En 段 value，Zh 逐字节不变；键集合严格对齐（781 键 × 2 段）；占位符/emoji/数字/HTML 实体全保留；人名拼音转写（张三→Zhang San）、年级 Grade 1-12 美式、A/B/C 层 Level A/B/C 统一。验收：残留中文值 0、占位符对齐 0 不一致、tsc 40、build 通过。
- 连带：删死代码后 resourceLibEn 已全英文，字典翻译实际只做了 classDetail 一个文件。

## 三.9 i18n 组件接入（进行中，批1 后持续更新）

**试点**（WrongQuestionsTab，`27e442b`）：10 处 JSX 中文 → `t()`，复用 3 已有 key（common.cancel/delete/classDetail.未知）+ 新增 6 key（英文驼峰，Zh/En 双段同步）。

**方法论（已确立，后续批沿用）**：

- 只改 UI 文案（JSX 文本节点 + title/placeholder/aria-label/label/toast），不动数据字符串（API 返回、传给后端的参数、console/注释）
- key 复用优先（全模块字典找语义匹配，含中文 key 名直接复用），无匹配才新增；新增 key 英文小写驼峰、Zh/En 双段同步
- 「标签：值」模式冒号+占位符整个进 key（中文全角：/英文半角:）
- 占位符/emoji/数字原样保留；JSX 变量插值拆占位符重组，渲染结果与原文逐字一致
- 已知局限：科目下拉值传给后端保持中文，英文版仍显中文（后续 `translateSubjectName()` 显示层翻译增强，不在本轮）

**批规划**（顺序执行，每批基于最新 master 避免字典冲突）：b1 顶层大文件(112处+删ClassDetailHeader) → b2 顶层小文件(103处) → b3 class-portrait(150处) → b4 student-panorama+targeted-improve(200处) → b5 其余子目录(150处) → b6 settings/smart-exam/grading/home/共享(150处)

**批6 落地（2026-08-14）**：

- **b6a grading**（`b6cff87` 合入）：GradingStartPage 9 处接入 t()（8 处复用既有 grading.* key + 下载文件名复用孤儿 key `grading.essay.reportSuffix`）；ErrorBookPage aria-label；ErrorBookDetail 剩 2 处中文为后端/OCR 槽位数据字符串（`第X题-作答区Y`）按方法论保留。新增 key 1（grading.errorBook.openErrorBook）。
- **b6b settings**（`d4ca39c` 合入）：TextbookMappingPanel/DataSyncPanel/StudentTable/ClassOverviewCards/SystemSettingsPage 接入；多数 settings 文件已由前序批转完；SystemSettingsPage `request` 模块级辅助函数经新增可选参数 `statusErrorFallback` 透传 t()。新增 key 19（settingsSubject 8 + settingsClass 10 + settings 1）。
- **b6c smart-exam/home/共享**（`9bf7036` 合入）：ExamGenPage/PhotoGradingDialog/TodoAndQuickActions/PrivacyNoticeDialog/GenericTour 接入；GradingEntrySection/Index/Admin/Auth 已由前批转完或属数据/注释。新增 key 8（examGen 1 + home 2 + common 5）。
- 验收：三批合并后 tsc 37 基线持平零新增、`npm run build` 通过。
- **b6d 科目显示层翻译补漏**（`82e1291` 合入）：修复 12 文件 38+/-24。直接渲染科目中文名接入 `translateSubjectName(locale, subject)`：WrongQuestionsCard/ExamHistoryTab/TargetedHeader/WrongQuestionsTab/RecentGrading/SubjectConfigHeader + 补充发现 ExamDetectionConfirmDialog/TeacherManageDialog/ReviewContentEditor/ReviewHeader/AnalysisHeader/ClassDashboard（t() 参数内嵌 subject 的也包）。LessonPlanPage/PrepPlanPage 确认已走 displaySubject/translateSubjectName 无需改；排除 subjectLabel 已接、数据文件、prop/Select value/localStorage key 等非渲染点。复查：全 src 无未包 translateSubjectName 的直接 subject 渲染点。
- 验收：四批（b6a/b6b/b6c/b6d）合并后 tsc 37 基线持平零新增、`npm run build` 通过。i18n 组件接入 + 科目显示层翻译至此全量收口。
- **遗留修复**（`9ed64b4` 合入）：`parseAiResultBlocks` 兜底中文（`解析结果`/`总览`）接入 t()——GradingStartPage 4 处 useMemo 调用补传 `t`（依赖数组同步），GradingEntrySection 版函数加 inline `t` 参数 + 3 处兜底走 `grading.ai.parseResult`/`grading.ai.overview`。tsc 37 持平、build 通过。

## 三.11 复刻 🟡 风险项落地（2026-08-14）

复刻审计矩阵 34 项（✅20/🟡10/❌4）基础上,本轮补齐合同内 8 项 🟡。用户澄清:叙阅=学校端升级版,**家长端（成长档案/安全守护推送）属独立「灵犀家长」项目**（`F:\grade-buddy-parent家长端`,含 parent-service/h5/android）,本轮排除。

**6 个实现 Agent 并行**（worktree 隔离,文件边界独立,零冲突）,后端合并 `9ebb359`(6 分支 merge),前端 6 commit:

| Agent | 风险项                         | 后端新增端点                                                                                                                                        | 前端 commit |
| ----- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| A     | 班级五育总览 + 月度报告        | `GET /portfolio/students/{id}/monthly-report?month=`;classes sort 扩展 tier/percentile/composite                                                    | `ee20725`   |
| B     | 激励终端报表 + 晨午检请假/出勤 | `GET /reward-products/stock-stats`、`GET /redemptions/report`、`POST/GET /student-ops/attendance`、`GET /attendance/stats` + `attendance_record` 表 | `3b6c8fb`   |
| C     | 错题遗忘曲线 + 变式推荐        | `GET /wrong-questions/due`、`POST /wrong-questions/{id}/review`(SM-2 简易)、`GET /wrong-questions/{id}/variants` + `wrong_question_review` 表       | `02823c9`   |
| D     | 全校数据驾驶舱 + 日/周/月      | `GET /admin/dashboard/overview`、`/daily                                                                                                            | weekly      | monthly`(批改量/预警/兑换/五育均分聚合)                                                            | `6b2c917` |
| E     | 综评遴选→公示                  | `POST /portfolio/classes/{id}/archive/select`、`POST /archive/{id}/publicity                                                                        | withdraw    | archive`、`GET /portfolio/archive`+`evaluation_archive` 表(draft→selected→publicity(7天)→archived) | `8f8e195` |
| F     | 学情内容推荐闭环               | `GET /targeted-improvement/recommendations/content`(弱项→知识点→教学资源)、`POST /targeted-improvement/re-evaluate`(AI 诊断前后对比)                | `5a42b79`   |

**默认口径**（无产品决策,按审计缺口最小落地）:变式题=同知识点历史错题(不引入 AI 生成);出勤=教师直接登记(简化审批);驾驶舱 KPI=班级/学生/批改量/预警/兑换/五育均分,仅全局管理员;遴选公示状态流可撤回。

**验收**:后端 `from app.main import app` 21 个新端点全注册;前端全量 `npx tsc -b --force` = 14 条**全部既有错误**(GradingStartPage/AccountManagePage/examExport 等非本次改动文件),零新增且比基线 37 降 23 条(Agent 顺带修复 gradingFetch 签名等);`npm run build` ✓(24.6s)。i18n 新增 key 全走 t()、Zh/En 双段同步。

**复刻度**:✅30 / 🟡2 / ❌2 ≈ 88%(剩余 🟡=家长端成长档案、安全守护推送;❌=家长端学情透明/家校互动,均归「灵犀家长」扩展项,合同未点名)。

## 四、原始 P0 验证裁决

| 原始 P0                        | 验证后 | 裁决说明                      |
| ------------------------------ | ------ | ----------------------------- |
| G5 域 100% 不可达              | P1     | 属实，功能缺失非崩溃          |
| ClassDetailHeader 编译失败     | P2     | 误判（见 3.7），实际死文件    |
| assessment 占位 key 缺失       | P2     | 属实，显示原始 key 但功能可用 |
| studentOps.credits.status 缺失 | P2     | 属实，同上                    |
| studentOps.rewards 缺失        | P2     | 属实，同上                    |

## 三.10 P0 合同缺口落地（2026-08-14）

种春风功能复刻审计（约 75%：20✅/10🟡/4❌）确认两项 P0 合同缺口，经用户拍板「先补 2 项 P0」，并行 worktree 实现并合并。

| P0 缺口                      | 后端（已合入 master）                                                                                                                                                                                       | 前端（已提交）                                                                                                                                            |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 教师语音录入（成长记录 ASR） | `f189286`：POST /api/v1/audio/asr（qwen3-asr-flash 同步模型，DashScope multimodal-generation；paraformer 仅支持公开 URL/WebSocket 故弃用，带错误 fallback）+ `app/routers/audio.py` + `app/services/asr.py` | `ba0693c`：GrowthRecordsPanel 🎤 语音按钮 + `useVoiceInput.ts`（MediaRecorder）+ `asrApi.ts` + `wuyuVoice.ts` 字典（zh/en 注册）                          |
| 学生成长印记动态相册         | `aaad05c`：`student_memory.py` model + `app/routers/portfolio.py` memories CRUD（复用 upload-evidence/save_evidence_image 上传模式 + ticket 鉴权）                                                          | `416713d`：WuyuProfilePage 新增 memory Tab + `StudentMemoryPanel.tsx`（时间倒序、caption、删除）+ `wuyuApi.ts` list/upload/delete + `wuyu.ts` memory keys |

> 验收：前端 `npx tsc -b` 37 基线持平零新增、`npm run build` 通过；后端 `from app.main import app` 路由注册 OK（audio/asr + 4 条 memories 路由）。
> 遗留：家长端为 contract-scope 记忆标记的扩展项（合同未点名），本轮未做。

## 四、全面复检审计与 P0/P1 修复（2026-08-14）

前端全面深度复检（`frontend-full-audit` workflow，Run `wf_9760f0ea-e66`），15 扫描 agent → 165 原始 → 去重 163 → 15 条 P0/P1 对抗验证**全数确认真实**。

**最终严重度分布**：P0=1 / P1=10 / P2=64 / P3=88

### 4.1 本次修复（6 并行 agent，worktree 隔离，workflow `wf_a913b6cd-c95`）

| 修复                                                                                                       | 级别    | 后端                             | 前端 commit |
| ---------------------------------------------------------------------------------------------------------- | ------- | -------------------------------- | ----------- |
| ExamGenPage 分页 effect 无限重渲染循环（typeOrder 模块级常量 + setState 内容判等 + loadResourceId 竞态）   | P0      | —                                | `9bd1e9c`   |
| 知识图谱整页接线（死代码→可达：Index switch case + Sidebar 菜单 + i18n key）                               | P1 ×2   | —                                | `91766c7`   |
| 教案发送邮件安全：后端白名单+限流+鉴权、前端管理员门控                                                     | P1 安全 | `512424d`（lesson_plans.py +57） | `364ad57`   |
| 资源下载 JWT 从 URL query → Authorization header（后端已支持）                                             | P1 安全 | —                                | `13f0e30`   |
| 智能生成模块 9 组件全量接 i18n（smartGen 221 对 key，Zh/En 同步）                                          | P1      | —                                | `70e5ca0`   |
| grading 批改端点对齐后端真实路由（submitGrading/records/result → `/grading/home/quick\|recent\|{job_id}`） | P1 契约 | —                                | `0ce634f`   |

> 前端 master：`2ab53d9` → `0ce634f`（6 commit）。后端 master：`9ebb359` → `512424d`。
> 验收：`npx tsc -b --force` 14 条全为既有错误零新增（分布 ReviewContentEditor/StudentProfilePanel/GradingStartPage/ReferenceLayoutCorrectionDialog/Header/AccountManagePage/BadgeSection/examExport）；`npm run build` ✓（24.75s）；后端 `from app.main import app` + py_compile ✓。

### 4.2 遗留（未在本轮范围）

- **P2 ×64 / P3 ×88**：死代码/不可达页、Supabase-FastAPI 契约分源、死按钮、a11y

## 四.5 i18n 集群清理（2026-08-14）

复检审计遗留的 i18n 硬编码集群全量清理。首轮 workflow（`wf_a7abe88f-5ab`）中 3 个 agent 因前端仓库 worktree 创建失败未执行，改用普通 Agent 直接写主 checkout 补跑，全部收口。

| i18n 域                              | 前端 commit | 说明                                                                                           |
| ------------------------------------ | ----------- | ---------------------------------------------------------------------------------------------- |
| chat-cards 6 组件                    | `1684ba3`   | 新建 `chatCards.ts` 41 key，Agent 独占注册 zh/en.ts                                            |
| compare-analysis 9 组件              | `785c767`   | `classDetail.compare` 66 key                                                                   |
| knowledge-graph 3 组件               | `c0266fa`   | `learningAnalytics.knowledge` 36 key                                                           |
| settings/account + useStudents toast | `b840ec3`   | `account` 21 key；顺手修 3 处基线 tsc（AccountManagePage radix onCloseAutoFocus/autoComplete） |
| student-ops                          | `09dc255`   | 3 key；分页中性化（不再绑定「积分流水」语义）、还书确认文案修正、修复 BadgeSection 基线 tsc    |
| resource-lib                         | `8861bf9`   | 11 key；拖拽区 aria-label                                                                      |

> 前端 master：`9eaa6f7` → `8861bf9`（6 commit）。`npx tsc -b` 从 14 降到 **10 条**（agent 顺带修复 4 条基线错误），全部在未改动文件；`npm run build` ✓（27.42s）。

## 四.6 P2 批次清理（2026-08-14）

复检审计的 P2×64 第一批次（6 agent 并行，普通 Agent 直接写主 checkout，file boundary 零冲突）。workflow `wf_1c737586-25a`。

| 域                   | 前端 commit | 修复要点                                                                                                                                                                                                                                      |
| -------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| class-dashboard 接线 | `c359634`   | G2 成绩子页面（ScoresTab/ExamHistoryTab/StudentTab/WrongQuestionsTab）接入 Tab 可达；班级切换重置 page；Zone-1 核心指标接 `listStudentAnalysis`；ClassReview 按班存科目偏好；ExamHistory/StudentTab i18n                                      |
| 导航接线+死代码清理  | `1f6db46`   | 4 隐藏路由接 Sidebar 入口（compare/grading-history/subject-config/prep-compose）+nav.* key+面包屑；Admin 4 子页面（dashboard/users/config/features）可达；**删除 Header.tsx + 7 个 class-portrait 死代码**（含伪造成绩 `generateExamScores`） |
| ExamGen 逻辑         | `51d855d`   | AI 生成改合并策略（保留用户手题目）；试卷库 loading 态；794px 编辑器响应式预览；AIIntegrationPanel 死按钮接线（确认生成/保存草稿/接受建议）                                                                                                   |
| 资源库+admin         | `a148cb3`   | 文件/文件夹竞态保护（请求序号）；「发送给他人」普通教师权限降级（隐藏+toast，`/auth/users/all` 仅管理员）；上传统一 FastAPI 存储；拖拽区键盘可达；admin 教师列表错误态                                                                        |
| 契约分源             | `b206d8b`   | `getAuthToken()` 统一（supabase 回退）；错题本类型去幽灵 `ok`；StatsOverview 随年级/班级筛选；TopHeader 改接 FastAPI；TargetedImprove `before` dict 解析；StudentPanorama loading/error                                                       |
| perf+i18n 遗留       | `8d6be31`   | FloatingChat 轮询仅面板打开时；layered-push 整域 t() 接入（~120 key）；GrowthRecords source_type 兜底；QuestionAnalysis 错题名单卡；Tour 修正失效步骤；useState lazy init                                                                     |

> 前端 master：`8861bf9` → `8d6be31`（6 commit）。`npx tsc -b` **10 → 9 条**：删除 Header.tsx 消除 1 条基线错误，其余 9 条全在未改动文件（GradingStartPage×4/examExport×2/ReviewContentEditor/StudentProfilePanel/ReferenceLayoutCorrectionDialog），**P2 批次零新增 tsc 错误**；`npm run build` ✓（62s，仅既有 chunk-size warning）。
>
> **保留项（如实记录）**：AssessmentConsentTab N+1（`wf_1c737586-25a` Agent F 确认后端无批量同意状态接口，不自行造接口）；ExamHistoryTab supabase 数据源保留（后端无等价成绩/考试 CRUD）；Zone-1 作业完成率为 score-coverage 近似推导。

## 四.7 P2 剩余尾巴（2026-08-14）

复检审计 P2×64 第二批（workflow `wf_f7afb351-9da`，1 后端 + 4 前端并行，前后端共享契约）。前端 master `8d6be31` → `9831036`（4 commit），后端 master `512424d` → `81a641e`（1 commit）。

| 域                                | 前端 commit / 后端 commit       | 修复要点                                                                                                                                                                                                              |
| --------------------------------- | ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **批量 consent 接口（跨前后端）** | 前端 `1e75dd8` + 后端 `81a641e` | 后端新增 `GET /assessment/classes/{class_id}/consents`（单次 IN 查询取最新 result，权限：管理/班级教师，契约 `ConsentsListData`）；前端 AssessmentConsentTab 的 N+1（50 人班级 50 请求）改单请求。**审计 P2 #8 闭环** |
| 死按钮×2                          | `38275d3`                       | ChasingPlan 追赶计划 3 按钮（启动/邀请督导/申请资源）+ TopHeader 通知面板（全部已读/查看全部），局部状态 + toast，home.ts 15 key                                                                                      |
| prep-plan                         | `b5cbe03`                       | LessonPlanPage 学科静默回退「语文」bug（非法学科中止创建 + 保留用户选择）；PrepPlanPage 8 处 aria-label i18n + 月视图日格子键盘可达，prepPlan.ts 9 key                                                                |
| settings/student-ops              | `9831036`                       | 批量删除 toast 聚合单条；表格全选/行点击键盘可达；BadgeSection 2 处 window.confirm → AlertDialog；账号卡按钮 aria-label 常显，account.ts 3 key                                                                        |

> 前端 `npx tsc -b` **9 条零新增**（与本批前完全一致，全在未改动文件）；`npm run build` ✓（31.87s）。后端 `py_compile` + import ✓（assessment.py +107）。
>
> **审计口径修正**：Agent E 确认 BadgeSection 的 window.confirm 实为 2 处（非审计「7 处」——统计口径含整个 student-ops 域），已全改 AlertDialog；边界外 CampusSection/RewardSection 的 5 处原生 confirm（退团/还书/上下架/状态流转/积分兑换）已补清（`4e1350e`），student-ops 域确认弹窗模式全部统一为 AlertDialog。
>
> **保留项**：KnowledgeGraphPage 全 mock 数据（审计 P2 #32）——后端 class_analysis.py 无知识图谱接口（仅 subjects/report/importable-exams/analyze），同 ExamHistoryTab 口径保留；ExamHistoryTab supabase 保留。

## 四.8 知识图谱接真实班级数据（2026-08-14，审计 P2 #32）

调研确认 mock 比审计更实：`knowledgeGraphData.ts` 的 `mastery()` 是 `hashStr` 确定性伪随机；`KnowledgeDetailPanel` 的 gradeRank/totalQuestions/学生四档分布全是哈希伪随机。后端无知识点级真实掌握度聚合（records 逐题 status_code 存在但错题才带 AI 知识点标签、对题无标签、命名非标准化），唯一可复用的班级级知识点数据是 `class-analysis/report` 的 `knowledge_heatmap`/`weak_points`。

**方案（后端零新增，纯前端 `bda0dfb`）**：

- 新增 `classStats.ts` 纯函数层：`buildClassStats`（normalize+打分匹配：精确节点名 100>集群 90>别名子串 70/60/50，MIN_LEN=2，ALIASES 预留）→ `Map<nodeId,{mastery|null,evidenceCount,weakCount,severity,dataSource}>`；`enrichGraphData`/`buildEnrichedTree` 派生新对象不改源
- `KnowledgeGraphPage` 接 `getClassAnalysisReport(classId, subject)`（useQuery），三态：loading（静态拓扑+info 条）/error（重试条）/empty（report==null→CTA 去生成分析）；`overallMastery` 只对 hasData 节点求均值，空则 null
- 掌握度真实化：`mastery = 100 - risk_score`（risk null→「暂无掌握率」，**禁 0 冒充**）；未匹配节点诚实「暂无掌握率数据」，**禁 hash 回填**
- 去伪随机：KnowledgeDetailPanel 删 hashStr/gradeRank/questionSummary/学生分布，涉及题目→evidence_count、薄弱人数→weak_count；RadialGraph 无数据节点灰+「—」；KnowledgeTree filterWeak 无数据禁用
- i18n：learningAnalytics.ts knowledge.* 增删改（Zh/En 成对，删 gradeRank/questionSummary/scoreDistribution，masteryTip 去 rank）；classDetail.ts Tour 假数字改中性

**验收**：tsc **9 零新增**（与本批前一致）；`classStats.test.ts` **16 passed**（匹配/聚合/全 null→null/unmatched/enrich 不改源）；`learningAnalyticsI18n.test.ts` 3 passed（Zh/En parity）；`grep hashStr|gradeRank` 在 knowledge-graph/ 零残留；`npm run build` ✓（31.43s）。

**保留**：知识图谱无数据节点诚实空态（匹配率低是预期内兜底）；ExamHistoryTab supabase 保留（后端无等价成绩/考试 CRUD）。

## 四.9 P3 批次全面审计（2026-08-14）

P2×64 全清后开 P3 批次，跑全面审计 workflow `p3-audit`（Run `wf_ff2dd6a8-f47`）：13 功能域×11 维度 + i18n + API 契约，**15 扫描 agent + 10 对抗验证**，160 原始 → **158 条去重**，10 条 P0/P1 对抗验证**全数确认真实**（5 条保持 P1、5 条降级 P2）。

**最终严重度分布**：P1=15 / P2=50 / P3=93

**分类**：i18n **41**（最大头）、logic 20、api 18、types 17、state 16、a11y 15、render 9、perf 8、style 6、contract 5、navigation 3。

**旧 P3×87 基线核对**（每个功能域 agent 内联旧基线逐条 Read 源文件核对）：62 条回填 → **still_exists 59 / fixed 2 / moved 1**。fixed：G6-9（TargetedImprove PDF 正文科目名已 `translateSubjectName` 本地化）、G7-8（错题关联图片容器已加 `h-32 md:h-40` 固定高度）；moved：G13-5（固定侧栏已移入 `AdminLayout.tsx:52`，问题仍存）。G2/G4/G5/G9/G12 的 25 条未回填（agent 疏漏），但新 findings 已覆盖同类问题。

**P1 明细（15 条）**：

| 问题                                                           | 文件                                                                                                      | 级别       |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ---------- |
| 保存成绩未等 scores 加载即提交全空，可覆盖真实成绩（数据丢失） | ScoresTab.tsx:34                                                                                          | P1 api ✓   |
| 追赶计划三按钮只弹虚假成功 toast，无后端调用                   | compare-analysis/ChasingPlan.tsx:56                                                                       | P1 logic ✓ |
| 「重新生成」忽略用户输入，硬编码《阿长与山海经》演示内容       | smart-gen/SmartGenPage.tsx:36                                                                             | P1 logic ✓ |
| 年级分析整页硬编码中文，英文模式整页中文                       | GradeAnalysisPage.tsx                                                                                     | P1 i18n ✓  |
| 学生管理弹窗整窗硬编码中文                                     | StudentManageDialog.tsx                                                                                   | P1 i18n ✓  |
| 性别下拉硬编码「男/女」（2 处）                                | ClassDashboard.tsx:891 / StudentTab.tsx:160                                                               | P1 i18n    |
| 6+1 个 hooks 的 toast 硬编码中文                               | useClasses/useExams/useExamScores/useExamTemplates/useWrongQuestions/useBatchCreateStudents/useAIGenerate | P1 i18n    |

**批次安排**：Batch 1 = P1×15（3 agent 并行，`p3-batch1`，workflow `wf_880d253e-367`）；Batch 2 = P2×50；Batch 3 = P3×93。均普通 agent 直写主 checkout + 主 CC 统一验收（tsc 9 零新增）与提交。

### 落地记录

**Batch 1（P1×15，2026-08-14）**：`p3-batch1` workflow（`wf_880d253e-367`），3 agent 并行 → 4 commit（数据正确性 / 6 hooks toast i18n / 整页+性别 i18n / docs+workflows）。tsc 9 零新增、vitest 36 passed、build ✓。master 至 `c954ef6`。

**Batch 2（P2×50−2，2026-08-14）**：`p3-batch2` workflow（`wf_d28f0ddc-3fa`），6 agent 并行（admin / 成绩试卷知识图谱 / 学生画像回顾 / grading顶层 / prep+exam / resource+settings+尾巴），排除被 Batch 1 覆盖的 2 条 → 7 commit。tsc **9→8**（StudentProfilePanel score 类型被顺手修掉）、vitest 36、i18n parity 全对等、build ✓。重点：ErrorBookPage 保留空文件夹+失败标记、loadFolderFiles 竞态守卫（reqId ref）、作文打印留痕死菜单移除、ExamGenPage personal_email 诚实降级（后端 /users/all 无该字段）、isGlobalAdmin 收紧后端白名单、LessonPlanPage 删除 AlertDialog。

**Batch 3a（P3 机械小修 ~50 条，2026-08-14）**：`p3-batch3a` workflow（`wf_e8afd7d3-ff9`），9 agent 并行（ClassDashboard / compare-analysis / student-panorama+ScoresTab / top-level 孤儿组件 / home+hooks / grading / smart-exam+prep / wuyu / chat-cards+reward+assessment）→ 11 commit。tsc **8→4**（GradingStartPage 4 条 TS2367 死代码比较被顺手修掉）、vitest 36、i18n parity 全对等、build ✓。Agent C 删死 prop 漏同步 2 个调用方（StudentPanoramaPage totalStudents / Index schoolLevel+onNavChange），主 CC dispatch 修复 agent 补齐。

**Batch 3b（P3 需判断 ~43 条，2026-08-14）**：`p3-batch3b` workflow（`wf_72d9e0f2-7fa`），8 agent 并行（知识图谱 / resource-lib / class-portrait+question-analysis / targeted+grade+tour / smart-gen / settings / admin+pages / services 契约）。主 CC 侦查已确认：ReviewContentEditor 6 个中文 key 全单文件引用（3 个模块无条目）、DashboardTour/AnalysisDailyTips/SubjectSettingsPage 零引用可直接删、api.ts 已导出 request。结构性大重构 CampusSection 2690 行拆分**不属本批次**，单独标注待专项。→ 9 commit，tsc **4→3**、vitest 36、i18n parity 全对等、build ✓ 18.5s，master 至 `14e477c`。

**晚班收尾（2026-08-15，审计遗留专项 5 commit，`5b707a0`→`76a7a3a`）**：

- **scripts 清理**（`5b707a0`）：删 16 个一次性 i18n 流水线工具（extract/scan/apply/fix/generate/build + 中间产物，全项目零引用），留 `check-i18n-parity.cjs` 正式验收工具
- **types/api.ts 死类型×3**（`b35c9a5`）：`PaginatedResponse`/`GradingRecordFilters`/`GradingRecord` 零引用删除。调研确认真实分页契约前后端已自洽（C 域 `items` / A、B 域 `rows` + `pageSize` camelCase），无"对不齐"，问题只是死契约残留
- **parseAiResultBlocks 收敛**（`1fee461`）：新建 `src/utils/aiResultBlocks.ts` 共享模块（完整行为 + `<essay_score>` 过滤），GradingStartPage/GradingEntrySection 删本地重复定义，`grading.ai.questionTitle` i18n 成对
- **CampusSection 2690 行拆分**（`61e019b`）：按 6 Tab 子域垂直切 9 文件（壳 75 行 + 6 Tab + campusCommon/campusUtils），纯移动零逻辑改动，Tab 间零共享 state，对外契约不变
- **tsc 真实基线×3 清零**（`76a7a3a`）：ReferenceLayoutCorrectionDialog DrawKind 补成员 / examExport 死代码删

> ⚠ **验收命令坑（重要）**：root `tsc --noEmit` 是 **空转**（root tsconfig 为 solution-style `files:[]` + references，不检查任何文件）。真实类型检查必须用 `node node_modules/typescript/bin/tsc -b --force` 或 `tsc -p tsconfig.app.json --noEmit`。P3 全部批次实际用 `tsc -b`（40→37→14→10→9→8→4→3 可信），但某窗口误用 root `tsc --noEmit` 造成"0 错误"假象，现已纠正——当前 `tsc -b` / `tsc -p tsconfig.app.json` 均为 **0 错误**。

## 五、相关文档

- 后端验收记录：`grade-buddy-scan-back_end/docs/acceptance-2026-08-13-p0-fixes.md`
- 后端缺陷清单：`grade-buddy-scan-back_end/docs/qa-plan.md`
- 审计 workflow：`.claude/workflows/frontend-full-audit.js`
- P3 审计 workflow：`.claude/workflows/p3-audit.js`；P3 批次：`.claude/workflows/p3-batch1.js` / `p3-batch2.js` / `p3-batch3a.js` / `p3-batch3b.js`
