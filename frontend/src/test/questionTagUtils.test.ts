import { describe, expect, it } from "vitest";

import {
  collectPatchFromForm,
  filterQuestionsByTags,
  formatKnowledgePoints,
  hasVisibleTags,
  mergeQuestionTag,
  parseKnowledgePointsInput,
  questionTagKey,
  questionTagSource,
  tagMatchesFilter,
  type QuestionTag,
} from "@/components/question-bank/questionTagUtils";

describe("questionTagKey", () => {
  it("prefers fingerprint, then unique_key, then raw_id, then id", () => {
    expect(
      questionTagKey({ fingerprint: "fp_aaa", unique_key: "uk", raw_id: "r", id: "i" }),
    ).toBe("fp_aaa");
    expect(questionTagKey({ unique_key: "uk_1", raw_id: "r", id: "i" })).toBe("uk_1");
    expect(questionTagKey({ raw_id: "raw_9", id: "i" })).toBe("raw_9");
    expect(questionTagKey({ id: "id_9" })).toBe("id_9");
  });

  it("returns empty string when no stable key", () => {
    expect(questionTagKey({})).toBe("");
    expect(questionTagKey({ fingerprint: "  ", unique_key: null })).toBe("");
  });

  it("marks source school only when fingerprint present", () => {
    expect(questionTagSource({ fingerprint: "fp_x" })).toBe("school");
    expect(questionTagSource({ unique_key: "uk_x" })).toBe("pg");
  });
});

describe("parseKnowledgePointsInput", () => {
  it("splits on mixed separators and dedupes", () => {
    expect(parseKnowledgePointsInput("分数, 小数、百分数；ratio\nrate")).toEqual([
      "分数",
      "小数",
      "百分数",
      "ratio",
      "rate",
    ]);
  });

  it("returns empty list for blank input", () => {
    expect(parseKnowledgePointsInput("")).toEqual([]);
    expect(parseKnowledgePointsInput("  ,，  ")).toEqual([]);
  });

  it("formatKnowledgePoints joins with 、", () => {
    expect(formatKnowledgePoints(["a", "b"])).toBe("a、b");
    expect(formatKnowledgePoints(null)).toBe("");
  });
});

describe("mergeQuestionTag (partial update)", () => {
  it("only overwrites fields present in patch", () => {
    const existing: QuestionTag = {
      unit: "U1",
      knowledge_points: ["kp-a"],
      difficulty: "中",
      question_type: "选择题",
      source: "pg",
      updated_at: "t1",
    };
    const next = mergeQuestionTag(existing, { unit: "U2" });
    expect(next.unit).toBe("U2");
    expect(next.knowledge_points).toEqual(["kp-a"]);
    expect(next.difficulty).toBe("中");
    expect(next.question_type).toBe("选择题");
  });

  it("clears a field when empty string / empty list is passed", () => {
    const existing: QuestionTag = { unit: "U1", knowledge_points: ["kp"], difficulty: "难" };
    const next = mergeQuestionTag(existing, {
      unit: "  ",
      knowledge_points: [],
      difficulty: "",
    });
    expect(next.unit).toBeNull();
    expect(next.knowledge_points).toEqual([]);
    expect(next.difficulty).toBeNull();
    expect(next.question_type).toBeNull();
  });

  it("creates a record from empty base", () => {
    const next = mergeQuestionTag(null, {
      unit: "U9",
      knowledge_points: ["x"],
      difficulty: "易",
    });
    expect(next.unit).toBe("U9");
    expect(next.knowledge_points).toEqual(["x"]);
    expect(next.difficulty).toBe("易");
    expect(next.source).toBeNull();
  });
});

describe("hasVisibleTags", () => {
  it("is false for empty / missing tags", () => {
    expect(hasVisibleTags(null)).toBe(false);
    expect(hasVisibleTags(undefined)).toBe(false);
    expect(hasVisibleTags({})).toBe(false);
    expect(hasVisibleTags({ unit: null, knowledge_points: [] })).toBe(false);
  });

  it("is true when any dimension is set", () => {
    expect(hasVisibleTags({ unit: "U" })).toBe(true);
    expect(hasVisibleTags({ knowledge_points: ["k"] })).toBe(true);
    expect(hasVisibleTags({ difficulty: "中" })).toBe(true);
    expect(hasVisibleTags({ question_type: "填空" })).toBe(true);
  });
});

describe("tagMatchesFilter / filterQuestionsByTags", () => {
  const tagA: QuestionTag = {
    unit: "第一单元",
    knowledge_points: ["分数加减"],
    difficulty: "中",
    question_type: "选择题",
  };
  const tagB: QuestionTag = {
    unit: "第二单元",
    knowledge_points: ["几何"],
    difficulty: "难",
    question_type: "证明题",
  };

  it("empty filter matches everything", () => {
    expect(tagMatchesFilter(tagA, {})).toBe(true);
    expect(tagMatchesFilter(null, { unit: "第一" })).toBe(false);
  });

  it("matches unit / knowledge_point with substring, difficulty exact", () => {
    expect(tagMatchesFilter(tagA, { unit: "第一" })).toBe(true);
    expect(tagMatchesFilter(tagA, { unit: "第三" })).toBe(false);
    expect(tagMatchesFilter(tagA, { knowledge_point: "加减" })).toBe(true);
    expect(tagMatchesFilter(tagA, { knowledge_point: "几何" })).toBe(false);
    expect(tagMatchesFilter(tagA, { difficulty: "中" })).toBe(true);
    expect(tagMatchesFilter(tagA, { difficulty: "难" })).toBe(false);
    expect(tagMatchesFilter(tagB, { question_type: "证明" })).toBe(true);
  });

  it("filters question list by tag map keys", () => {
    const items = [
      { id: "q1", unique_key: "uk1" },
      { id: "q2", unique_key: "uk2" },
      { id: "q3", unique_key: "uk3" },
    ];
    const tagMap: Record<string, QuestionTag> = {
      uk1: tagA,
      uk2: tagB,
    };
    const getKey = (q: { unique_key: string }) => q.unique_key;

    // 只保留第一单元
    const onlyUnit1 = filterQuestionsByTags(items, tagMap, { unit: "第一" }, getKey);
    expect(onlyUnit1.map((q) => q.id)).toEqual(["q1"]);

    // 难度难 → 只有 uk2
    const hard = filterQuestionsByTags(items, tagMap, { difficulty: "难" }, getKey);
    expect(hard.map((q) => q.id)).toEqual(["q2"]);

    // 无筛选 → 全量
    expect(filterQuestionsByTags(items, tagMap, {}, getKey)).toHaveLength(3);

    // 未打标的 q3 在「有标签」筛选下不出现
    const typed = filterQuestionsByTags(items, tagMap, { question_type: "选择" }, getKey);
    expect(typed.map((q) => q.id)).toEqual(["q1"]);
  });
});

describe("collectPatchFromForm", () => {
  it("omits empty fields so batch apply is partial", () => {
    const patch = collectPatchFromForm({
      unit: "  ",
      knowledge_points: "",
      difficulty: "中",
      question_type: "",
    });
    expect(patch).toEqual({ difficulty: "中" });
  });

  it("includes parsed knowledge points", () => {
    const patch = collectPatchFromForm({
      unit: "U1",
      knowledge_points: "a, b、a",
      difficulty: "",
      question_type: "填空",
    });
    expect(patch.unit).toBe("U1");
    expect(patch.knowledge_points).toEqual(["a", "b"]);
    expect(patch.question_type).toBe("填空");
    expect(patch.difficulty).toBeUndefined();
  });
});
