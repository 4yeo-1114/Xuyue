# 数据层契约 · C2 校本题库回填器 + 唯一键语义

> 版本: 1.0 | 日期: 2026-08-20 | 归属专项: 数据层专项 DL4b（C2 校本题库第二刀：回填器 + 契约）
> 前置: DL1 学校/区域锚表、DL2 默认学校回填、DL3 指纹函数（`app/utils/question_fingerprint.py`）、DL4a 表 `school_question_banks`（commit db38e71）均已合入 master。
> 边界: 本契约只描述**纯新增逻辑单元**（回填器），不接 HTTP 层、不改任何既有端点/服务/表结构。

---

## 目录

1. [范围与边界](#1-范围与边界)
2. [输入数据源](#2-输入数据源)
3. [指纹语义（DL3 引用）](#3-指纹语义dl3-引用)
4. [软删恢复规则（三态 upsert）](#4-软删恢复规则三态-upsert)
5. [幂等与并发约定](#5-幂等与并发约定)
6. [验收口径](#6-验收口径)

---

## 1. 范围与边界

**本契约管辖**：

- `app/utils/question_bank_backfill.py` 的 `upsert_question_to_bank(db, record, *, school_id=None)` 回填器。
- 回填器把一条错题记录（dict）写入 `school_question_banks`，动作语义为三态 upsert（新建 / 更新 / 软删恢复）。
- 返回动作描述（`created` / `updated` / `restored`）及命中行 `id` / `school_id` / `fingerprint`。

**明确不做（边界）**：

- 不接任何 HTTP 端点 / 路由 / 批改服务——回填器是纯逻辑单元，由后续接线方调用。
- 不改 `school_question_banks` 表结构、DL3 `question_fingerprint()`、schools/regions 锚表。
- 不回填 `knowledge_point_id` / `difficulty`（知识点锚表未定，`knowledge_points` 是列表语义，映射留给后续 DL）。
- 不做近似去重 / 同义归一（那是 P1 simhash 范畴，见 DL3 文档）。

---

## 2. 输入数据源

`record` 字段与 `app/grading/wrong_question_db.py` 的错题记录对齐：

| record 字段                | 来源                                         | 说明                                                 |
| -------------------------- | -------------------------------------------- | ---------------------------------------------------- |
| `paper_subject`            | 错题记录 `paper_subject`                     | 科目，指纹四字段之一，可空                           |
| `question_type`            | 错题记录 `question_type`                     | 题型，指纹四字段之一，可空                           |
| `question_text`            | 错题分析 `analysis.question_text`            | 题干，**NOT NULL 且为指纹来源**，空则抛 `ValueError` |
| `estimated_correct_answer` | 错题分析 `analysis.estimated_correct_answer` | 参考答案，指纹四字段之一，可空                       |
| `school_id`（可选）        | 调用方显式传入 / record 内                   | 未给时用 DL2 默认学校 `DEFAULT_SCHOOL_ID` 兜底       |

`school_id` 解析优先级：`record["school_id"]` → 函数参数 `school_id` → `DEFAULT_SCHOOL_ID`
（`11111111-1111-4111-8111-111111111111`，与 `docs/migrations/2026-08-20-school-backfill.sql` 的 seed 一致）。

---

## 3. 指纹语义（DL3 引用）

- 指纹 = `question_fingerprint(paper_subject, question_type, question_text, estimated_correct_answer)`，
  输出 `fp_` + 64 位小写 hex，总长 67（列 `VARCHAR(67)`）。
- 实质内容变化（改科目 / 改题型 / 改题干 / 改答案）⇒ 指纹变化 ⇒ 视为新题；
  仅排版级差异（空白、全半角、冗余首尾标点）⇒ 指纹不变 ⇒ 同一题。
- 因此回填器对同一道题跨卷收敛到 `school_question_banks` 同一条记录，叠加后续统计。

---

## 4. 软删恢复规则（三态 upsert）

`school_question_banks` 唯一键 = `UNIQUE(school_id, fingerprint)`（`uq_sqb_school_fp`），且含 `deleted_at` 软删列。
回填器**按 `(school_id, fingerprint)` 查询、不区分 `deleted_at`**，命中即复用，三态如下：

| 现状                                    | 动作     | 操作                                                                                      |
| --------------------------------------- | -------- | ----------------------------------------------------------------------------------------- |
| 同指纹行不存在                          | created  | 新建一行，`deleted_at = NULL`                                                             |
| 同指纹行存在且 `deleted_at IS NULL`     | updated  | 幂等重写四个内容字段（同指纹下内容归一化一致）、刷新 `updated_at`，`deleted_at` 保持 NULL |
| 同指纹行存在且 `deleted_at IS NOT NULL` | restored | **恢复该行**：清 `deleted_at` 为 NULL，并幂等重写四个内容字段                             |

**硬性约束**：软删行仍占着 `UNIQUE(school_id, fingerprint)`，因此**绝不允许**"只查未删行、查不到就 INSERT"——
那样软删行同指纹的第二次回填会撞唯一键抛 DuplicateEntry。回填器必须命中软删行并走恢复分支。
本契约将 DuplicateEntry 场景的处理收敛为查询口径（命中软删行），写侧单写者串行，见 §5。

---

## 5. 幂等与并发约定

- **幂等**：同一 record 连续回填 N 次，库中始终只有 1 行（同指纹收敛），动作依次为 `created → updated/updated…`；软删后再次回填为 `restored`。
- **事务边界**：`upsert_question_to_bank` 只 `flush` 不 `commit`，事务由调用方收口（便于与周边写入组合成同一事务）。
- **并发**：写侧约定**单写者（每校串行）**调用（回填为异步落库任务，天然串行）。若未来出现并发同指纹双 INSERT，
  由调用方以 `IntegrityError` 捕获重试为更新；回填器本身不处理该竞态。
- **数据安全**：回填器是纯新增单元，不改既有表、不级联影响其他域，失败仅影响单条回填。

---

## 6. 验收口径

- `python -m pytest tests/test_question_bank_backfill.py -q` 全绿（in-memory SQLite，不依赖真实 MySQL）。
- 覆盖三态：新建（created）、更新（updated）、软删恢复（restored）各一用例。
- **软删恢复用例**必须证明：软删行同指纹回填后 `len(rows) == 1` 且 `deleted_at IS NULL`——即未新建导致 DuplicateEntry。
- 空题干（`question_text` 全空白）抛 `ValueError`。
- `school_id` 显式覆盖与默认学校兜底各覆盖一次；同指纹排版级差异收敛为单行、实质差异产生新行。
- 全量门禁 `python -m pytest tests/ -q` 零回归（既有 270 passed + 环境性 error 不变）。
