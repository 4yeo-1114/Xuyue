/**
 * 题库标签纯函数层（批量打标 / 徽章 / 本地筛选）。
 * 与后端 question_tags.py 的部分更新语义对齐：只传的字段才改，空串/空列表清空。
 */

/** 标签覆盖层记录（对应后端 question_tags.json 的 value） */
export interface QuestionTag {
  unit?: string | null;
  knowledge_points?: string[] | null;
  difficulty?: string | null;
  question_type?: string | null;
  source?: string | null;
  updated_at?: string | null;
}

/** 批量/单行打标补丁：字段缺省 = 本次不改 */
export interface QuestionTagPatch {
  unit?: string;
  knowledge_points?: string[];
  difficulty?: string;
  question_type?: string;
  source?: string;
}

/** 标签本地筛选条件（空串 = 不过滤） */
export interface QuestionTagFilter {
  unit?: string;
  knowledge_point?: string;
  difficulty?: string;
  question_type?: string;
}

/** 难度下拉固定三档（客户口径：易/中/难） */
export const TAG_DIFFICULTY_OPTIONS = ["易", "中", "难"] as const;

type KeyCarrier = {
  fingerprint?: string | null;
  unique_key?: string | null;
  raw_id?: string | null;
  id?: string | null;
};

/**
 * 解析题目稳定键。
 * 优先 school_question_banks.fingerprint（fp_+64hex），
 * 其次 PG 资产 unique_key，再回退 raw_id / id。
 */
export function questionTagKey(q: KeyCarrier): string {
  const candidates = [q.fingerprint, q.unique_key, q.raw_id, q.id];
  for (const c of candidates) {
    const token = String(c ?? "").trim();
    if (token) return token;
  }
  return "";
}

/** 题目来源标记：有 fingerprint 视为校本题库，否则按 PG 资产题 */
export function questionTagSource(q: KeyCarrier): string {
  return String(q.fingerprint ?? "").trim() ? "school" : "pg";
}

/** 解析多值知识点输入：支持中英文逗号 / 顿号 / 分号 / 换行分隔，去重去空 */
export function parseKnowledgePointsInput(input: string): string[] {
  const parts = String(input ?? "")
    .split(/[,，、;；\n\r]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const p of parts) {
    if (seen.has(p)) continue;
    seen.add(p);
    out.push(p);
  }
  return out;
}

/** 知识点数组 → 展示串 */
export function formatKnowledgePoints(list: string[] | null | undefined): string {
  return (list ?? []).filter(Boolean).join("、");
}

/**
 * 部分更新合并：patch 里出现的字段覆盖 existing，未出现的保留。
 * 空串 unit/difficulty/question_type 清空为 null；空数组知识点清空为 []。
 */
export function mergeQuestionTag(
  existing: QuestionTag | null | undefined,
  patch: QuestionTagPatch,
): QuestionTag {
  const base: QuestionTag = {
    unit: existing?.unit ?? null,
    knowledge_points: [...(existing?.knowledge_points ?? [])],
    difficulty: existing?.difficulty ?? null,
    question_type: existing?.question_type ?? null,
    source: existing?.source ?? null,
    updated_at: existing?.updated_at ?? null,
  };
  if (patch.unit !== undefined) {
    const v = patch.unit.trim();
    base.unit = v || null;
  }
  if (patch.knowledge_points !== undefined) {
    base.knowledge_points = patch.knowledge_points.map((s) => s.trim()).filter(Boolean);
  }
  if (patch.difficulty !== undefined) {
    const v = patch.difficulty.trim();
    base.difficulty = v || null;
  }
  if (patch.question_type !== undefined) {
    const v = patch.question_type.trim();
    base.question_type = v || null;
  }
  if (patch.source !== undefined) {
    const v = patch.source.trim();
    base.source = v || null;
  }
  return base;
}

/** 该题是否已有任一标签（决定徽章区是否占位） */
export function hasVisibleTags(tag: QuestionTag | null | undefined): boolean {
  if (!tag) return false;
  if (tag.unit) return true;
  if (tag.difficulty) return true;
  if (tag.question_type) return true;
  if ((tag.knowledge_points ?? []).length > 0) return true;
  return false;
}

/** 单条标签是否命中筛选（空条件 = 命中） */
export function tagMatchesFilter(
  tag: QuestionTag | null | undefined,
  filter: QuestionTagFilter | null | undefined,
): boolean {
  const f = filter ?? {};
  const unit = (f.unit ?? "").trim();
  const kp = (f.knowledge_point ?? "").trim();
  const difficulty = (f.difficulty ?? "").trim();
  const qtype = (f.question_type ?? "").trim();
  if (!unit && !kp && !difficulty && !qtype) return true;
  const t = tag ?? {};
  if (unit && !String(t.unit ?? "").includes(unit)) return false;
  if (difficulty && String(t.difficulty ?? "") !== difficulty) return false;
  if (qtype && !String(t.question_type ?? "").includes(qtype)) return false;
  if (kp) {
    const list = t.knowledge_points ?? [];
    if (!list.some((item) => String(item).includes(kp))) return false;
  }
  return true;
}

/**
 * 按标签筛选题目列表（本地过滤，供当前页/已加载列表使用）。
 * items 通过 getKey 取稳定键，再查 tagMap。
 */
export function filterQuestionsByTags<T>(
  items: T[],
  tagMap: Record<string, QuestionTag>,
  filter: QuestionTagFilter | null | undefined,
  getKey: (item: T) => string,
): T[] {
  const f = filter ?? {};
  const unit = (f.unit ?? "").trim();
  const kp = (f.knowledge_point ?? "").trim();
  const difficulty = (f.difficulty ?? "").trim();
  const qtype = (f.question_type ?? "").trim();
  if (!unit && !kp && !difficulty && !qtype) return items;
  return items.filter((item) => {
    const tag = tagMap[getKey(item)];
    return tagMatchesFilter(tag, f);
  });
}

/**
 * 从批量打标表单收集补丁：空字段不进补丁（= 本次不改），与部分更新语义一致。
 */
export function collectPatchFromForm(form: {
  unit: string;
  knowledge_points: string;
  difficulty: string;
  question_type: string;
}): QuestionTagPatch {
  const patch: QuestionTagPatch = {};
  const unit = form.unit.trim();
  const kps = parseKnowledgePointsInput(form.knowledge_points);
  const difficulty = form.difficulty.trim();
  const qtype = form.question_type.trim();
  // 知识点输入非空才写（空输入 = 不改，避免误清）；单独提供 clearKnowledgePoints 语义时再传空数组
  if (unit) patch.unit = unit;
  if (kps.length > 0) patch.knowledge_points = kps;
  if (difficulty) patch.difficulty = difficulty;
  if (qtype) patch.question_type = qtype;
  return patch;
}
