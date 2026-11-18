import { beforeEach, describe, expect, it } from "vitest";

import {
  CLASS_REVIEW_EXPORT_PREFS_KEY,
  defaultClassReviewExportPrefs,
  groupWrongPaperImagesByStudent,
  parseWrongPaperSortKey,
  readClassReviewExportPrefs,
  selectHighFrequencyWrongImages,
  writeClassReviewExportPrefs,
} from "@/utils/classReviewPdfExport";

describe("parseWrongPaperSortKey", () => {
  it("parses question number and slot from display titles", () => {
    expect(parseWrongPaperSortKey("第12题-区3")).toEqual({ q: 12, slot: 3 });
    expect(parseWrongPaperSortKey("第7题")).toEqual({ q: 7, slot: 0 });
  });

  it("falls back to leading number and pushes unparseable titles last", () => {
    expect(parseWrongPaperSortKey("3. 选择题")).toEqual({ q: 3, slot: 0 });
    expect(parseWrongPaperSortKey("作文").q).toBe(Number.MAX_SAFE_INTEGER);
  });
});

describe("groupWrongPaperImagesByStudent", () => {
  it("groups by student and sorts each group by question number", () => {
    const groups = groupWrongPaperImagesByStudent([
      { student_name: "张三", title: "第2题-区1", image_url: "/a" },
      { student_name: "李四", title: "第1题", image_url: "/b" },
      { student_name: "张三", title: "第1题-区2", image_url: "/c" },
      { student_name: "张三", title: "第1题-区1", image_url: "/d" },
    ]);

    expect(groups.map((g) => g.student)).toEqual(["张三", "李四"]);
    expect(groups[0].items.map((x) => x.title)).toEqual([
      "第1题-区1",
      "第1题-区2",
      "第2题-区1",
    ]);
    expect(groups[1].items).toHaveLength(1);
  });

  it("returns empty list for missing data", () => {
    expect(groupWrongPaperImagesByStudent(undefined)).toEqual([]);
    expect(groupWrongPaperImagesByStudent([])).toEqual([]);
  });
});

describe("selectHighFrequencyWrongImages", () => {
  const img = (student_name: string, title: string) => ({
    student_name,
    title,
    image_url: "/a",
    answer_url: "/b",
  });

  it("ranks by wrong_count from question_accuracy and keeps top 5", () => {
    const groups = selectHighFrequencyWrongImages(
      [
        img("甲", "第1题-区1"),
        img("甲", "第2题-区1"),
        img("甲", "第3题-区1"),
        img("甲", "第4题-区1"),
        img("甲", "第5题-区1"),
        img("甲", "第6题-区1"),
      ],
      [
        { display_title: "第1题", wrong_count: 30 },
        { display_title: "第2题", wrong_count: 25 },
        { display_title: "第3题", wrong_count: 20 },
        { display_title: "第4题", wrong_count: 5 },
        { display_title: "第5题", wrong_count: 4 },
        { display_title: "第6题", wrong_count: 3 },
      ],
    );
    expect(groups.map((g) => g.q)).toEqual([1, 2, 3, 4, 5]);
    expect(groups[0]).toMatchObject({ title: "第1题", wrongCount: 30 });
    expect(groups[4]).toMatchObject({ title: "第5题", wrongCount: 4 });
  });

  it("caps examples per question and spreads across students", () => {
    const groups = selectHighFrequencyWrongImages(
      [
        img("甲", "第1题-区1"),
        img("甲", "第1题-区2"),
        img("甲", "第1题-区3"),
        img("乙", "第1题-区1"),
        img("丙", "第1题-区1"),
      ],
      [{ display_title: "第1题", wrong_count: 3 }],
    );
    expect(groups).toHaveLength(1);
    expect(groups[0].items).toHaveLength(3);
    expect(new Set(groups[0].items.map((i) => i.student_name)).size).toBe(3);
  });

  it("keeps taking from one student when examples are scarce", () => {
    const groups = selectHighFrequencyWrongImages(
      [
        img("甲", "第1题-区1"),
        img("甲", "第1题-区2"),
        img("甲", "第1题-区3"),
        img("甲", "第1题-区4"),
      ],
      [{ display_title: "第1题", wrong_count: 1 }],
    );
    expect(groups[0].items).toHaveLength(3);
    expect(groups[0].items.every((i) => i.student_name === "甲")).toBe(true);
  });

  it("falls back to student-count ranking when question_accuracy is missing", () => {
    const groups = selectHighFrequencyWrongImages(
      [
        img("甲", "第2题-区1"),
        img("乙", "第2题-区1"),
        img("丙", "第2题-区1"),
        img("甲", "第1题-区1"),
      ],
      undefined,
    );
    expect(groups.map((g) => g.q)).toEqual([2, 1]);
    expect(groups[0].wrongCount).toBe(3);
    expect(groups[1].wrongCount).toBe(1);
  });

  it("skips unparseable titles and handles empty input", () => {
    expect(selectHighFrequencyWrongImages(undefined, undefined)).toEqual([]);
    expect(
      selectHighFrequencyWrongImages([], [{ display_title: "第1题", wrong_count: 9 }]),
    ).toEqual([]);
    const groups = selectHighFrequencyWrongImages(
      [img("甲", "作文"), img("甲", "第1题")],
      [{ display_title: "第1题", wrong_count: 1 }],
    );
    expect(groups).toHaveLength(1);
    expect(groups[0].items).toHaveLength(1);
    expect(groups[0].items[0].title).toBe("第1题");
  });
});

describe("class review export prefs", () => {
  beforeEach(() => {
    localStorage.removeItem(CLASS_REVIEW_EXPORT_PREFS_KEY);
  });

  it("defaults includeWrongPaper to true", () => {
    expect(defaultClassReviewExportPrefs().includeWrongPaper).toBe(true);
    expect(readClassReviewExportPrefs().includeWrongPaper).toBe(true);
  });

  it("persists the includeWrongPaper toggle", () => {
    writeClassReviewExportPrefs({ includeWrongPaper: false });
    expect(readClassReviewExportPrefs().includeWrongPaper).toBe(false);
    writeClassReviewExportPrefs({ includeWrongPaper: true });
    expect(readClassReviewExportPrefs().includeWrongPaper).toBe(true);
  });
});
