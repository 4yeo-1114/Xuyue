# 种春风功能复刻对照清单

> 项目:叙阅(job2,学校端)+ 种春风复刻
> 生成:2026-08-14 | 基准:复刻审计 Workflow(`wf_4a197dbe-956`,4-agent) + 两轮实现(P0 缺口 + 合同内 🟡 风险项)
> 范围口径(用户拍板):叙阅 = 学校端升级版;**家长端属独立「灵犀家长」项目**(`F:\grade-buddy-parent家长端`),不作为本清单扣分项,单列扩展。

## 一、复刻矩阵(34 项)

| 类别 | 种春风功能 | 状态 | 复刻依据(前后端) | 缺口/说明 |
|---|---|---|---|---|
| **叙阅七大模块** | 智能批改 | ✅ | 后端 `app/grading/router.py`(快速/批量/参照批改、扫描导入、打印标记);前端 GradingStartPage/ManualPaperGradingDialog/批改历史 | — |
| | 学情分析 | ✅ | 后端 班级学情分析/课堂回顾/学生学情/成绩导入/AI诊断+CT图/靶向提升;前端 学生/班级/年级/题目/对比分析、知识图谱 | 知识图谱由 ai-diagnosis 支撑 |
| | 智能备课 | ✅ | 后端 备课计划/教案/资源;前端 备课计划/教案生成/智能生成工具 | — |
| | 错题管理 | ✅ | 后端 error-book stats/detail + `GET /wrong-questions/due|review|variants`(遗忘曲线 SM-2 + 变式推荐,本轮补);前端 错题本+错题详情+遗忘曲线卡+变式卡 | 变式题源=同知识点历史错题(未引 AI 生成) |
| | 智能组卷 | ✅ | 后端 exams/papers CRUD+ai-generate;前端 ExamGenPage(题型编辑/导出) | — |
| | 课堂讲评 | ✅ | 后端 class-review(post-class 报告);前端 ClassReviewPage(AI讲评/效果追踪) | — |
| | 数据看板 | ✅ | 后端 `GET /admin/dashboard/overview|daily|weekly|monthly`(全校驾驶舱聚合,本轮补)+ grading-stats;前端 SchoolDashboardPage(日/周/月切换)+ 年级/班级看板 + 首页 StatsOverview(接真实数据) | 驾驶舱仅全局管理员 |
| **五育成长画像** | 五育画像引擎 | ✅ | 后端 GET /portfolio/students/{id}(trend)+ assessment_engine 双轨制评分;前端 WuyuProfile overview(雷达图/五维指标卡/智育事件明细) | — |
| | 德智体美劳五维成长记录 | ✅ | 后端 growth-records 增删查;前端 GrowthRecordsPanel(手动录入±10/来源着色) | — |
| | 教师语音录入 | ✅ | 后端 `POST /audio/asr`(qwen3-asr-flash);前端 GrowthRecordsPanel 🎤(MediaRecorder)(P0 补) | — |
| | 成长流水 | ✅ | 后端 growth-records POST/GET/DELETE(evidence/indicator_id/source_type);前端 录入/删除/分页 | — |
| | 五育指标库 | ✅ | 后端 GET /portfolio/indicators(维度/停用过滤);前端 listIndicators 选择器 | — |
| | 班级总览 | ✅ | 后端 GET /portfolio/classes/{id}(sort total/name/tier/percentile/composite);前端 ClassOverviewPanel(WuyuProfilePage 班级侧,本轮补) | 数据源审计时已就绪,纯前端补 UI |
| | 学生评价(教师端) | ✅ | 画像引擎 + AI评语(generate/confirm 有数据支撑) | — |
| **证据链** | 证据链可追溯 | ✅ | 后端 event_catalog 智育事件目录 + 成长记录 evidence + upload-evidence 图片鉴权;前端成长记录展示 source_type/来源 | — |
| **学期/学年成长报告** | 学期/学年报告自动生成 | ✅ | 后端 GET /report?term(快照优先→实时聚合);前端 SemesterReportPanel | — |
| | 报告冻结快照(成档) | ✅ | 后端 POST /report/freeze(多版本回溯);前端 freezeReport 版本号 | — |
| | AI评语生成+教师确认 | ✅ | 后端 comment generate/confirm(禁词/人格归因校验);前端 AiCommentPanel 状态机 | — |
| | 报告PDF出口 | ✅ | 后端 GET /report/pdf(UTF-8 文件名);前端 downloadReportPdf+saveBlob | — |
| | 五育报告(月度/期末) | ✅ | 月度:`GET /portfolio/students/{id}/monthly-report?month=`(本轮补,复用报告引擎);期末=学期报告已覆盖 | 月度口径=自然月 |
| | 成长数据可视化 | ✅ | 后端 trend=true 按月趋势;前端雷达图+月度趋势柱图 | — |
| **综评档案** | 综合素质评价档案 | ✅ | 后端 学期报告+冻结快照(成档)+ `portfolio/archive` 遴选→公示→成档状态流(本轮补);前端 SemesterReportPanel + SelectionPanel(ClassPortraitPage 综评遴选 Tab) | 状态流 draft→selected→publicity(7天)→archived,可撤回 |
| | 综合素质评价一键导出 | ✅ | 后端 PDF 下载(升学合规出口) | — |
| **学生端** | 学生成长印记(动态相册) | ✅ | 后端 `portfolio/students/{id}/memories` CRUD(上传/列表/删除,ticket 鉴权);前端 WuyuProfilePage memory Tab + StudentMemoryPanel(P0 补) | — |
| | 争章颁章与学分银行 | ✅ | 后端 badge-definitions/awards + credit-accounts/对账;前端 激励中心 Tab1/Tab2 + 五育画像激励 Tab | — |
| | 校外实践 | ✅ | 后端 practice-records 四类+review(volunteer 归德+劳);前端 激励中心 Tab4(含证据上传) | — |
| | 校园生活配套 | ✅ | 后端 社团/考勤/图书借阅/阅读排行榜/健康预警 + 晨午检请假/出勤统计(`/student-ops/attendance`+`stats`,本轮补);前端 CampusSection 全部 Tab(含请假/出勤) | 阅读榜/健康预警前端已单列 |
| | 激励终端联动 | ✅ | 后端 reward-products + redemptions(状态机) + 库存/兑换报表(`stock-stats`/`redemptions/report`,本轮补);前端 RewardSection(含报表 Tab) | 报表对齐 credit-report 模式 |
| **动态评估/延伸** | 动态评估系统 | ✅ | 后端 题组/施测会话/锚点计分/监护人同意全套;前端 多元评价 Tab1-4 | 双轨制+三层由 assessment_engine 覆盖 |
| | 学情驱动内容推荐 | ✅ | 后端 `GET /targeted-improvement/recommendations/content`(弱项→知识点→教学资源)+ `POST /re-evaluate`(AI 诊断前后对比,本轮补);前端 TargetedImprovePage 内容推荐+复测 | 推荐源=资源库复用 |
| **家长端(扩展)** | 家长端成长档案 | 🟡 | 后端 parent-students 绑定 + 监护人同意三态;前端 ParentBindingDialog(教师侧) | **归「灵犀家长」项目**(合同未点名);本清单不扣分 |
| | 安全守护·家长端推送 | 🟡 | 后端 health-alerts 健康预警有;推送/订阅机制缺 | 归「灵犀家长」项目 |
| | 学情透明与科学辅导 | ❌ | 无家长端学情查询 | 归「灵犀家长」项目(已有日报/周报/错题) |
| | 家校互动 | ❌ | 无 | 归「灵犀家长」项目 |

## 二、叙阅七大模块 vs 种春风

| 模块 | 状态 | 判定依据 |
|---|---|---|
| 智能批改 | ✅ 完整 | grading/router.py 批改核心+打印标记+扫描导入;前端拍照/手动作卷全流程 |
| 学情分析 | ✅ 完整 | 班级/学生双粒度 + AI诊断+CT图+成绩导入+靶向提升,前后端齐全 |
| 智能备课 | ✅ 完整 | 备课计划/教案生成/资源库,前后端齐全 |
| 错题管理 | ✅ 完整 | 错题本/归档/统计 + 遗忘曲线推送 + 变式推荐(本轮补) |
| 智能组卷 | ✅ 完整 | exams/papers+ai-generate+前端题型编辑 |
| 课堂讲评 | ✅ 完整 | class-review 报告 + 前端 AI 讲评/效果追踪 |
| 数据看板 | ✅ 完整 | 全校驾驶舱(日/周/月)+ 年级/班级看板(本轮补全校级) |

**结论:七大模块 7/7 完整。**

## 三、修复历程

1. **审计**(2026-08-14):4-agent 复刻审计,34 项 = ✅20 / 🟡10 / ❌4,复刻度约 74%(含部分实现)
2. **P0 合同缺口**(2026-08-14,`p0-gaps-implement` workflow):教师语音录入 + 学生成长印记动态相册(2 个 ❌ → ✅)。后端 `f189286`/`aaad05c`,前端 `416713d`/`ba0693c`
3. **合同内 🟡 风险项**(2026-08-14,`risk-items-implement` workflow):8 项 🟡 → ✅。后端 6 分支合并 `9ebb359`(21 新端点),前端 6 commit(`ee20725`/`3b6c8fb`/`02823c9`/`6b2c917`/`8f8e195`/`5a42b79`)

## 四、复刻度结论

- **当前**:✅30 / 🟡2 / ❌2 ≈ **88%**(学校端合同内 30/30 = **100% 覆盖**)
- **剩余 4 项**:全为家长端扩展项,归独立「灵犀家长」项目,合同未点名,不作为扣分项
- **验收口径**:后端 `from app.main import app` 全路由注册;前端全量 `npx tsc -b --force` 14 条全为既有错误零新增(基线 37 已降至 14);`npm run build` ✓

## 五、相关文档

- 前端全面审计记录:`docs/frontend-audit-2026-08-13.md`(含三.10 P0 落地、三.11 风险项落地)
- 后端验收记录:`../grade-buddy-scan-back_end/docs/acceptance-2026-08-13-p0-fixes.md`
- 后端缺陷清单:`../grade-buddy-scan-back_end/docs/qa-plan.md`
- 契约:`../grade-buddy-scan-back_end/docs/contracts/`(00-data-layer-baseline / 10-portfolio / 11-assessment / 12-student-ops / 99-reconciliation)
