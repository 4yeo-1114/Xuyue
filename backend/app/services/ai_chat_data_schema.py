# -*- coding: utf-8 -*-
"""AI 助教：MySQL 表与本地批改目录的结构说明（供大模型生成查询语句）。"""

from __future__ import annotations

from app.grading.user_paths import user_grading_dir_name

# 与 app/models 中 __tablename__ 一致，共 28 张表（其中 system_settings 禁止 AI 查询）
MYSQL_TABLE_COUNT = 28
# 与 app/grading/user_paths.py UserGradingPaths 子目录数量一致
LOCAL_DIR_COUNT = 12

_MODULE_QUERY_GUIDE = """
## 【必读】语义意图 → 查哪张表（用户不必说模块名）

用户**不会**总说「班级管理」「智能组卷」等界面名称。请根据问句**含义**选表：

| 用户可能问法（举例） | 应查的表 / 工具 |
|---------------------|----------------|
| 五年级有几个班、班级概况 | `classes` |
| 某班有哪些学生、花名册 | `students` JOIN `classes` |
| 张三在哪个班 | `students` JOIN `classes` |
| 我有哪些教案、数学教案 | `lesson_plans`（当前账号） |
| 组卷库、我的试卷有几份 | `smart_exam_papers`（当前账号） |
| 靶向诊断、提升方案 | `targeted_improvement_reports` |
| 推荐关注的学生 | `targeted_recommendations` |
| 课堂讲评、巩固方案 | `class_review_sessions` |
| 学情、成绩趋势 | `student_analysis` / `student_score_history` |
| 薄弱知识点 | `knowledge_points` |
| 张三期中考试多少分、某次考试得分 | `execute_local_data_query` → `local_grading_scores`（**批改详细/批改档案**） |
| 批改得分、排名、最高分 | `execute_local_data_query` → `local_grading_scores` |
| 批改了哪些考试 | `local_exam_list` |
| 错题 | `local_ct_wrong_questions` |
| 班主任是谁 | `class_teachers` JOIN `classes` |
| 待办事项 | `todo_items` |

## 前端功能模块 → 查询哪张表

用户问下列界面里的内容时，**必须**用 `execute_mysql_query` 查对应表。

| 前端模块 | 用户可能的说法 | 主表 | 辅助表 | 账号隔离 |
|---------|---------------|------|--------|---------|
| **班级管理** | 班级、年级、多少个班、有哪些班、花名册 | `classes` | `students`、`class_teachers` | 教师按可访问班级 |
| **智能组卷** | 组卷、试卷库、我的试卷、题目 | `smart_exam_papers` | `exam_question_templates` | **仅当前登录账号**（user_id，后台强制） |
| **教案生成** | 教案、备课、教学过程、教学目标 | `lesson_plans` | `classes`（JOIN 查班号） | **仅当前登录账号**（user_id，后台强制） |
| **靶向提升** | 靶向、诊断、提升方案、推荐名单 | `targeted_improvement_reports` | `targeted_recommendations` | 按可访问班级 class_id |
| **课堂讲评** | 讲评、课前、巩固、二次巩固、课后反馈 | `class_review_sessions` | `classes` | 按可访问班级 class_id |

**账号隔离（教案 + 智能组卷，极其重要）**：
- `lesson_plans`、`smart_exam_papers`、`exam_question_templates` 与前端一致：**每个登录账号只能看到自己的教案和试卷**。
- 后台执行 SQL 时会**强制**追加 `表名.user_id = 当前用户`，管理员也不能查到其他教师的教案/组卷。
- 编写 SQL 时**不要**写 user_id 条件，也不要尝试查其他账号；只查业务字段（title、subject、class_id 等）。
- 回答用户时用「您保存的教案」「您的组卷库」，不要说成全校或其他老师的。

**其他说明**：
- `class_review_sessions` = **课堂讲评**；每班每学科一条。
- `smart_exam_papers.questions` 为 JSON 题目数组；元数据用 title/subject/updated_at，必要时 SELECT questions。

### 四大模块 SQL 示例

**智能组卷 — 当前账号的试卷（勿写 user_id）：**
```sql
SELECT id, title, subject, updated_at
FROM smart_exam_papers
ORDER BY updated_at DESC
LIMIT 20
```

**教案生成 — 当前账号某学科教案（勿写 user_id）：**
```sql
SELECT lp.title, lp.subject, lp.teaching_objectives, lp.updated_at, c.grade, c.name AS class_no
FROM lesson_plans lp
JOIN classes c ON lp.class_id = c.id
WHERE lp.subject LIKE '%数学%'
ORDER BY lp.updated_at DESC
LIMIT 20
```

**靶向提升 — 某学生诊断与方案：**
```sql
SELECT student_name, subject, diagnosis_text, plan_text, generated_at
FROM targeted_improvement_reports
WHERE student_name = '龙锐涵'
LIMIT 10
```

**靶向提升 — 某班推荐关注学生：**
```sql
SELECT subject, student_names_json, updated_at
FROM targeted_recommendations
WHERE subject LIKE '%数学%'
LIMIT 10
```

**课堂讲评 — 某班某科讲评方案：**
```sql
SELECT title, subject, pre_class_json, consolidation_json, post_feedback_json, generated_at
FROM class_review_sessions
WHERE subject LIKE '%数学%'
LIMIT 5
```

**班级管理 — 某年级有多少班（用户不必说「班级管理」）：**
```sql
SELECT grade, name, student_count
FROM classes
WHERE grade LIKE '%五年级%'
ORDER BY name
LIMIT 100
```

**班级管理 — 某班学生名单：**
```sql
SELECT s.name AS student_name, c.grade, c.name AS class_no
FROM students s
JOIN classes c ON s.class_id = c.id
WHERE c.name = '2101'
ORDER BY s.name
LIMIT 200
```
"""

_MYSQL_TEACHER_ACCESS_NOTE = """
**普通教师 MySQL 权限**：可查教案/组卷/靶向/讲评等表；靶向与讲评按可访问班级过滤。
**教案与组卷**与其他模块不同：无论角色，**仅返回当前登录账号**的数据（与前端账号隔离一致）。
批改得分、错题请用 `execute_local_data_query`。

"""

_MYSQL_ADMIN_ACCOUNT_NOTE = """
**管理员说明**：查全校 students/exams 等教务表不受限，但 **lesson_plans / smart_exam_papers / exam_question_templates 仍仅当前登录账号**，不能查其他教师的教案或试卷。

"""

_MYSQL_SCHEMA_BODY = """
## 系统教务 MySQL 库（只读 SELECT）

**规则**：仅可使用 `execute_mysql_query` 执行 **SELECT**；禁止 INSERT/UPDATE/DELETE/DROP 等。
未写 LIMIT 时系统自动追加 `LIMIT 100`。查不到数据时如实告知，禁止编造。
**禁止查询的表**：
- `system_settings`（含 API 密钥等敏感配置，不在白名单内）
- **`users`、`profiles`、`user_roles`**（系统登录账号与个人资料，AI 助教一律不可查，即使用户明确要求）

---

### 一、教务核心

#### classes（班级）
| 字段 | 含义 |
|------|------|
| id | 班级 UUID |
| user_id | 创建者用户 ID |
| school_level | 学段 primary/junior/senior |
| grade | 年级，如「四年级」「初一年级」 |
| name | 班号，如 2101（查询用 name='2101'，不带「班」字） |
| student_count | 登记学生人数 |

**可查**：某年级有多少班、班级列表、按班号找班。

#### students（学生花名册）
| 字段 | 含义 |
|------|------|
| id, class_id, user_id | 主键与关联 |
| name | 姓名 |
| student_number | 学号 |
| gender, tier, status | 性别、分层、状态 |
| seat_row, seat_col, cadre_role | 座位与班干部 |
| enroll_date | 入学时间 |

**可查**：学生在哪个班（JOIN classes）、某班全部学生、按姓名/学号查找。

**⚠️ E09 敏感字段（禁止查询/返回）**：`phone`（手机）、`parent_name`（家长姓名）、
`parent_phone`（家长电话）、`address`（家庭住址）、`birthday`（生日）、`notes`（备注）属
L3-L5 级敏感数据，AI 助教一律不得查询或带出。即使用户询问「家长电话/住址/生日」，也应
礼貌说明属于学生敏感信息，请教师本人通过「学生管理」查看。

#### class_teachers（班级任课教师）
| 字段 | 含义 |
|------|------|
| class_id, user_id | 班级与教师 |
| role | head=班主任 / deputy=副班主任 / teacher=任课教师 |
| subject | 任教学科 |

**可查**：某班班主任是谁、某教师带哪些班（查 `class_teachers` JOIN `classes`；**禁止 JOIN users**，教师姓名由系统自动关联返回）。

#### exams（系统登记的考试）
| 字段 | 含义 |
|------|------|
| id, class_id, user_id | 主键与关联 |
| subject, title | 学科、考试名称 |
| total_score | 满分 |
| exam_date | 考试日期 |

#### exam_scores（系统登记的成绩）
| 字段 | 含义 |
|------|------|
| exam_id, student_id, user_id | 关联 |
| score | 得分 |

**可查**：排名、最高/最低/平均分（JOIN exams、students）。

#### wrong_questions（系统错题库）
| 字段 | 含义 |
|------|------|
| student_id, class_id, exam_id, user_id | 关联 |
| subject, question_content | 学科、题干 |
| correct_answer, student_answer | 正确答案与学生作答 |
| error_type, analysis | 错因类型与分析 |

---

### 二、学情与分析

#### student_analysis（学生学情目标）
| 字段 | 含义 |
|------|------|
| class_id, student_name, subject | 班级、姓名、学科 |
| target_score, current_score | 目标分、当前分 |

#### student_score_history（学生成绩历史）
| 字段 | 含义 |
|------|------|
| class_id, student_name, subject | 班级、姓名、学科 |
| exam_name, score | 考试名、得分 |
| class_avg | 该场班级平均分 |

**可查**：某学生某科成绩趋势、历次考试分数。

#### student_wrong_questions（学情模块错题）
| 字段 | 含义 |
|------|------|
| class_id, student_name, subject | 班级、姓名、学科 |
| exam_name, question_title | 考试、题目标题 |
| image_url, answer_url | 题目与答案图片 |

#### class_review_sessions（课堂讲评 — 对应前端「课堂讲评/智能复习」模块）
| 字段 | 含义 |
|------|------|
| class_id, subject, title | 班级、学科、讲评标题 |
| exam_names_json, imported_folder_names_json | 关联的考试名称、导入的批改文件夹 |
| source_summary_json | 数据来源摘要（错题/得分概况） |
| pre_class_json | 课前讲评/导入概览 |
| tracking_json | 跟踪数据 |
| consolidation_json | **二次巩固方案**（讲评核心内容之一） |
| post_feedback_json | 课后反馈 |
| ai_raw_json | AI 原始输出 |
| generated_at | 生成时间 |

**可查**：某班某学科是否已生成讲评、巩固方案摘要、关联了哪些考试。

#### targeted_improvement_reports（靶向提升 — 学生诊断报告）
| 字段 | 含义 |
|------|------|
| class_id, student_id, student_name, student_number, subject | 班级与学生、学科 |
| diagnosis_text, plan_text | 诊断与提升计划（纯文本） |
| diagnosis_json, plan_json, source_summary_json | 结构化诊断/方案 |
| exam_names_json, imported_folder_names_json | 依据的考试与批改文件夹 |
| generated_at | 生成时间 |

#### targeted_recommendations（靶向提升 — 班级推荐名单）
| 字段 | 含义 |
|------|------|
| class_id, subject | 班级、学科 |
| student_names_json | JSON 数组，推荐关注的学生姓名 |

---

### 三、知识点与组卷

#### subject_units（学科单元/章节）
| 字段 | 含义 |
|------|------|
| user_id, subject, semester | 用户、学科、学期 |
| unit_index, name, subtitle | 单元序号与名称 |

#### knowledge_points（知识点）
| 字段 | 含义 |
|------|------|
| user_id, unit_id, code, name | 归属与编码 |
| mastery | 掌握度 0~1 |
| is_weak | 是否薄弱点 |
| level, difficulty, common_errors, key_point | 层级、难度、常见错误 |
| prerequisite, postrequisite, related | JSON 关联知识点 |
| hours, resources | 课时与资源 |

#### smart_exam_papers（智能组卷 — 试卷库，**按 user_id 账号隔离**）
| 字段 | 含义 |
|------|------|
| user_id | **所属登录账号**（AI 查询时后台强制 = 当前用户，不可查他人） |
| title, subject | 试卷标题、学科 |
| questions | JSON 题目数组 |
| created_at, updated_at | 时间 |

#### exam_question_templates（智能组卷 — 题型模板，**按 user_id 账号隔离**）
| 字段 | 含义 |
|------|------|
| user_id, subject, type_name | 用户、学科、题型名 |
| default_count, default_score_each, sort_order | 默认题量、分值、排序 |

---

### 四、教案与资源

#### lesson_plans（教案生成 — 教案库，**按 user_id 账号隔离**）
| 字段 | 含义 |
|------|------|
| user_id | **所属登录账号**（AI 查询时后台强制 = 当前用户，不可查他人） |
| class_id, subject, title | 班级、学科、教案标题 |
| school_year, term, grade | 学年、学期、年级 |
| teaching_content, teaching_objectives, key_points, difficult_points | 内容与目标 |
| teaching_preparation, teaching_process, blackboard_design | 教学过程 |
| collective_preparation_advice, teaching_reflection | 集体备课与反思 |
| main_author, deputy_author, lesson_sequence, completed_at | 作者与完成时间 |
| created_at, updated_at | 时间 |

**可查**：某班有哪些教案、某教案的教学目标/过程全文。

#### prep_plans（备课计划）
| 字段 | 含义 |
|------|------|
| user_id, date, subject | 用户、日期 YYYY-MM-DD、学科 |
| content, completed | 计划内容、是否完成 |

#### teaching_resources（教学资源）
| 字段 | 含义 |
|------|------|
| user_id, title, description, type | 基本信息 |
| file_url, file_name, file_size, mime_type | 文件元数据 |
| tags, is_shared, uses, rating | 标签、共享、使用次数 |
| detected_grade, detected_class, detected_subject, detected_unit | AI 识别元数据 |
| question_count, knowledge_point_count, difficulty | 题目与难度统计 |

#### essay_rubrics（作文评分标准）
| 字段 | 含义 |
|------|------|
| user_id, name, content | 用户、名称、标准正文 |
| summary_prompt, comment_prompt, scoring_prompt 等 | 各环节 Prompt |
| topic_text, topic_image_base64 | 作文题目 |

---

### 五、用户与权限（AI 助教不可查）

以下表含**系统登录账号与个人隐私**，`execute_mysql_query` **一律禁止**访问（后端硬拦截）：

#### users / profiles / user_roles — **禁止 AI 查询**
含账号、密码、邮箱、手机号、角色等登录用户信息。即使用户要求「查 users 表」「查某老师密码」也必须拒绝。

---

### 六、系统统计与配置

#### grading_daily_stats（批改日统计）
| 字段 | 含义 |
|------|------|
| user_id, folder_safe, stat_date | 用户、考试文件夹、日期 |
| upload_count, grade_count | 当日上传份数、批改份数 |

**可查**：某教师某天批改量、统计趋势。

#### todo_items（待办事项）
| 字段 | 含义 |
|------|------|
| user_id, title, content | 用户、标题、内容 |
| remind_at, notified_at, is_done | 提醒时间与完成状态 |

#### system_config（系统配置项）
| 字段 | 含义 |
|------|------|
| key, value, label, category, description | 配置键值（value 为 JSON） |

#### feature_flags（功能开关）
| 字段 | 含义 |
|------|------|
| key, label, enabled | 开关键与是否启用 |
| scope, scope_id | 作用域 |

#### system_settings（系统密钥设置）— **禁止 AI 查询**
含 dashscope_api_key、baidu_access_token 等，不在 execute_mysql_query 白名单内。

---

### 常用 SQL 示例

**学生在哪个班：**
```sql
SELECT s.name, c.grade, c.name AS class_no
FROM students s
JOIN classes c ON s.class_id = c.id
WHERE s.name = '龙锐涵'
LIMIT 10
```

**某班花名册：**
```sql
SELECT s.name, s.student_number FROM students s
JOIN classes c ON s.class_id = c.id
WHERE c.name = '2101'
ORDER BY s.name
LIMIT 200
```

**系统登记成绩排名：**
```sql
SELECT st.name, es.score, e.title
FROM exam_scores es
JOIN exams e ON es.exam_id = e.id
JOIN students st ON es.student_id = st.id
WHERE e.title LIKE '%期中%'
ORDER BY es.score DESC
LIMIT 30
```

**学生成绩历史：**
```sql
SELECT student_name, exam_name, score, class_avg
FROM student_score_history
WHERE student_name = '龙锐涵' AND subject = '数学'
ORDER BY created_at DESC
LIMIT 20
```
"""


def build_mysql_schema_doc(*, mysql_admin: bool) -> str:
    head = _MODULE_QUERY_GUIDE
    if mysql_admin:
        head += _MYSQL_ADMIN_ACCOUNT_NOTE
    else:
        head += _MYSQL_TEACHER_ACCESS_NOTE
    return head + _MYSQL_SCHEMA_BODY


def build_local_schema_doc(user_id: str) -> str:
    dir_name = user_grading_dir_name(user_id)
    return f"""
## 个人批改本地档案（`grading_data_all/{dir_name}/`，仅当前登录用户）

**规则**：查询必须用 `execute_local_data_query` + `local_*` 虚拟表；**禁止**在 SQL 中写绝对路径或其它用户目录。
未写 LIMIT 时自动 `LIMIT 100`。无结果时必须说「未查询到」，禁止编造。

---

### 根目录下全部子文件夹（共 12 项，与系统 `UserGradingPaths` 一致）

| 路径（相对根目录） | 作用 | 主要内容 | AI 是否可查 |
|-------------------|------|----------|------------|
| `correct_documents/test_paper/` | **考试归档根目录** | 每场考试一个子文件夹，文件夹名即 exam_key（如 `cls_{{uuid}}__考试名`），内存原始试卷 PDF/图片 | 间接查：virtual `local_exam_list` |
| `correct_documents/test_paper_img/` | **试卷预览图** | 与 test_paper 同结构的子文件夹；PDF/Word 转成的 `*_img.jpg` 或原图副本，供 OCR/批改预览 | 暂无虚拟表（仅 OCR 中间产物） |
| `grading_history/` | **批改结果与得分** | 每场考试对应 JSON：`{{exam_key}}.json`（智能批改）、`{{exam_key}}__manual.json`（答题卡（自主阅卷））、`{{exam_key}}__essay.json`（作文）；内含 completed/failed 各学生批改详情与分数 | **可查**：`local_grading_scores`、`local_exam_list` |
| `ct/cls_{{class_id}}/records/` | **按班级的批改记录** | 每场考试一个 JSON，结构含 class、papers（每生一卷）、wrong_questions、summary | **可查**：`local_ct_students`、`local_ct_wrong_questions` |
| `ct/cls_{{class_id}}/analysis/` | **按班级的错题分析** | 与 records 类似，侧重错题聚合分析 | **可查**：同上虚拟表 |
| `scan/` | **扫描仪导入缓存** | 从扫描仪批量导入的临时图片/批次文件，导入后会进入正式批改流程 | 暂无虚拟表 |
| `home_img/` | **首页快速批改** | 首页「拍一张批改」的单张作业：原图、留痕图、空白留痕、`{{job_id}}.json` 记录状态与结果 | 暂无虚拟表（非班级考试档案） |
| `ai_diagnosis/` | **AI 学情诊断** | `{{class_id}}_{{student}}_{{subject}}` 编码文件名的 JSON，存某生某科 AI 诊断结论 | 暂无虚拟表（可后续扩展） |
| `history/` | **旧版历史兼容目录** | 早期版本遗留的归档，新项目数据主要在 grading_history | 暂无虚拟表 |
| `zyk_data/` | **个人资源库** | 用户自建文件夹，存放上传的教学资源文件（课件、试卷等），按文件夹组织 | 暂无虚拟表（元数据在 MySQL teaching_resources） |
| `temp/` | **临时文件** | 上传/转换过程中的临时缓存，可清理 | 不查 |
| `test/` | **快速批改测试** | 快速批改流程的临时上传与输出 | 不查 |
| `modify/` | **批改留痕输出** | 批改过程中生成的留痕图、标注图、作文 OCR 合并图等中间/结果文件 | 不查 |

---

### 关键 JSON 结构说明

**grading_history/{{exam_key}}.json**
- `completed`: 字典，键为试卷文件名，值为单卷批改结果（含 score/result/student/group_name 等）
- `failed`: 批改失败的试卷及原因
- `scoring_config`: 评分配置

**ct/cls_{{class_id}}/records/{{exam_name}}.json**
- `class`: 班级元信息（name、grade 等）
- `papers`: 字典，键试卷名，值含 student、wrong_questions、summary、subject 等

---

### 虚拟表（execute_local_data_query 唯一入口）

#### local_exam_list
来源：`correct_documents/test_paper/` + `grading_history/` 汇总。
| 字段 | exam_key, exam_title, student_count, max_score, avg_score |

#### local_grading_scores
来源：`grading_history/*.json` → `completed`。
| 字段 | exam_key, exam_title, student_name, score, grading_type（智能/人工/作文） |

#### local_ct_students
来源：`ct/cls_*/records|analysis/*.json` → `papers`。
| 字段 | class_id, class_name, student_name, exam_name, wrong_question_count |

#### local_ct_wrong_questions
来源：同上 → `papers[].wrong_questions`。
| 字段 | class_name, student_name, exam_name, subject, content, error_type |

---

### 查询示例

```sql
SELECT exam_title, student_count, max_score FROM local_exam_list LIMIT 20
```
```sql
SELECT student_name, score, exam_title, grading_type
FROM local_grading_scores
WHERE student_name = '龙锐涵'
LIMIT 20
```
```sql
SELECT student_name, score FROM local_grading_scores
WHERE exam_title LIKE '%单元测%'
ORDER BY score DESC LIMIT 30
```
```sql
SELECT DISTINCT student_name FROM local_ct_students
WHERE class_name LIKE '%2101%' LIMIT 200
```
```sql
SELECT student_name, content, error_type FROM local_ct_wrong_questions
WHERE student_name = '张三' LIMIT 20
```

**说明**：scan、home_img、ai_diagnosis、zyk_data、test_paper_img 等目录目前无虚拟表，若用户询问其中内容且 virtual 表查不到，应说明「批改档案查询范围内暂无该数据」，不可编造。
"""


_ASSET_SCHEMA_BODY = """
## 家长端 PG 资产库（只读 SELECT · execute_asset_query）

**来源**：家长端 PG 资产库（只读镜像）。AI 助教**仅可查 5 张资产表**：`questions`、`knowledge_points`、
`question_kp`、`subject_units`、`difficulty_gold`。
**规则**：必须用 `execute_asset_query` + **SELECT**；禁止写操作。查题库/出题/知识点树/相似题时使用。
未写 LIMIT 时系统自动追加 `LIMIT 100`；结果会剥离家长端个人学习状态与家长 PII 列（user_id/mastery/is_weak/phone 等）。

#### questions（统一题库 — 资产抽题主数据源）
| 字段 | 含义 |
|------|------|
| id, subject, grade | 主键、学科、学段（小学/初中/高中/大学） |
| question_type, question, options | 题型、题干、选项（JSON） |
| answer, analysis, knowledge_point | 答案、解析、知识点名 |
| difficulty, source, quality_flag | 难度、来源、质量（ok/filled/NULL 可入池） |

#### knowledge_points（知识点）
| 字段 | 含义 |
|------|------|
| id, code, name, level | 主键、编码、名称、层级 |
| unit_id, knowledge_nature | 所属单元、知识本质（fact/rule/procedure/symbol） |
| key_point, difficulty, common_errors | 重点、难度、常见错误 |

#### question_kp（题→知识点多对多桥接）
| 字段 | 含义 |
|------|------|
| question_id, kp_id, matched_via | 题、知识点、匹配方式（exact） |

#### subject_units（学科单元/章节）
| 字段 | 含义 |
|------|------|
| id, subject, grade, semester | 主键、学科、学段、学期 |
| unit_index, name, subtitle | 单元序号与名称 |

#### difficulty_gold（题目难度评测集）
| 字段 | 含义 |
|------|------|
| question_id, subject, gold_difficulty | 题、学科、金标准难度 |
| gold_verdict, confidence, status | 判级、置信度、状态 |

**查题示例：**
```sql
SELECT id, subject, grade, question FROM questions WHERE subject LIKE '%数学%' AND grade = '初中' LIMIT 10
```

**知识点树示例（knowledge_points JOIN subject_units 按学科）：**
```sql
SELECT kp.code, kp.name, kp.level, su.name AS unit_name
FROM knowledge_points kp JOIN subject_units su ON kp.unit_id = su.id
WHERE su.subject = '数学' ORDER BY kp.level, kp.code LIMIT 100
```
"""


def build_asset_schema_doc() -> str:
    """家长端 PG 资产库（5 张只读资产表）文档。"""
    return _ASSET_SCHEMA_BODY


def build_full_data_schema(*, user_id: str, mysql_admin: bool) -> str:
    header = (
        f"# 数据字典（MySQL 共 {MYSQL_TABLE_COUNT} 张表，其中 system_settings 禁止 AI 查询；"
        "生成 SELECT 时必须严格遵守）\n"
    )
    return (
        header
        + build_mysql_schema_doc(mysql_admin=mysql_admin)
        + build_local_schema_doc(user_id)
        + build_asset_schema_doc()
    )
