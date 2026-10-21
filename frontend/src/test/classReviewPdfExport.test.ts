import { beforeEach, describe, expect, it } from "vitest";

import {
  CLASS_REVIEW_EXPORT_PREFS_KEY,
  defaultClassReviewExportPrefs,
  groupWrongPaperImagesByStudent,
  parseWrongPaperSortKey,
  readClassReviewExportPrefs,
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
