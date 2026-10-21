import { describe, expect, it } from "vitest";

import {
  WRONG_SHEET_EMPTY_SELECTION,
  assembleWrongSheetItems,
  buildWrongSheetPlan,
  matchWrongImageForQuestion,
  paginateWrongSheetItems,
  questionNumberFromTitle,
  selectTopWrongKeys,
  sortWrongSheetItems,
  wrongSheetFileName,
  type WrongSheetItem,
} from "@/utils/wrongQuestionSheetExport";

function item(partial: Partial<WrongSheetItem> & { id: string }): WrongSheetItem {
  return {
    title: partial.id,
    ...partial,
  };
}

describe("questionNumberFromTitle", () => {
  it("parses arabic and chinese question numbers", () => {
    expect(questionNumberFromTitle("第12题-区3")).toBe(12);
    expect(questionNumberFromTitle("第3题")).toBe(3);
    expect(questionNumberFromTitle("第十二题")).toBe(12);
    expect(questionNumberFromTitle("3. 选择题")).toBe(3);
    expect(questionNumberFromTitle("作文")).toBe(Number.MAX_SAFE_INTEGER);
  });
});

describe("sortWrongSheetItems", () => {
  it("sorts by question number ascending and keeps unknown last", () => {
    const sorted = sortWrongSheetItems([
      item({ id: "c", title: "第10题" }),
      item({ id: "a", title: "第2题" }),
      item({ id: "d", title: "附加题" }),
      item({ id: "b", title: "第七题" }),
    ]);
    expect(sorted.map((x) => x.id)).toEqual(["a", "b", "c", "d"]);
  });
});

describe("paginateWrongSheetItems", () => {
  it("splits items into pages of given size", () => {
    const items = [
      item({ id: "1", title: "第1题" }),
      item({ id: "2", title: "第2题" }),
      item({ id: "3", title: "第3题" }),
      item({ id: "4", title: "第4题" }),
      item({ id: "5", title: "第5题" }),
    ];
    const pages = paginateWrongSheetItems(items, 2);
    expect(pages).toHaveLength(3);
    expect(pages[0].map((x) => x.id)).toEqual(["1", "2"]);
    expect(pages[2].map((x) => x.id)).toEqual(["5"]);
  });

  it("clamps invalid perPage to 1", () => {
    const items = [item({ id: "1" }), item({ id: "2" })];
    expect(paginateWrongSheetItems(items, 0).every((p) => p.length === 1)).toBe(true);
    expect(paginateWrongSheetItems(items, -3)).toHaveLength(2);
  });
});

describe("selectTopWrongKeys", () => {
  it("takes first N keys from accuracy list (weakest first)", () => {
    const list = [
      { question_key: "q1", display_title: "第1题" },
      { question_key: "q2", display_title: "第2题" },
      { question_key: "q3", display_title: "第3题" },
    ];
    expect(selectTopWrongKeys(list, 2)).toEqual(["q1", "q2"]);
    expect(selectTopWrongKeys(list, 0)).toEqual([]);
    expect(selectTopWrongKeys([], 5)).toEqual([]);
  });
});

describe("matchWrongImageForQuestion", () => {
  const images = [
    { student_name: "张三", title: "第5题-区1", image_url: "/a" },
    { student_name: "李四", title: "第5题-区1", image_url: "/b" },
    { student_name: "王五", title: "第6题", image_url: "/c" },
  ];

  it("matches by question number", () => {
    const hit = matchWrongImageForQuestion(images, { display_title: "第6题" });
    expect(hit?.image_url).toBe("/c");
  });

  it("prefers students in studentFilter", () => {
    const hit = matchWrongImageForQuestion(
      images,
      { display_title: "第5题" },
      ["李四"],
    );
    expect(hit?.student_name).toBe("李四");
  });

  it("returns null when no number matches", () => {
    expect(matchWrongImageForQuestion(images, { display_title: "第99题" })).toBeNull();
  });
});

describe("assembleWrongSheetItems", () => {
  const accuracy = [
    {
      question_key: "q2",
      display_title: "第2题",
      real_number: "一、2",
      question_text: "题干2",
      wrong_count: 8,
      accuracy: 30,
      top_reasons: [{ reason: "计算粗心", count: 3 }],
    },
    {
      question_key: "q1",
      display_title: "第1题",
      question_text: "题干1",
      wrong_count: 5,
      accuracy: 50,
      top_reasons: [],
    },
    {
      question_key: "q3",
      display_title: "第3题",
      wrong_count: 1,
      accuracy: 90,
    },
  ];
  const images = [
    { student_name: "张三", title: "第1题-区1", image_url: "/img1" },
    { student_name: "李四", title: "第2题-区1", image_url: "/img2" },
  ];

  it("assembles selected questions sorted by number with images", () => {
    const items = assembleWrongSheetItems({
      selectedKeys: ["q2", "q1"],
      questionAccuracy: accuracy,
      allWrongImages: images,
    });
    expect(items.map((x) => x.id)).toEqual(["q1", "q2"]);
    expect(items[0].imageUrl).toBe("/img1");
    expect(items[1].title).toBe("一、2");
    expect(items[1].topReasons?.[0]?.reason).toBe("计算粗心");
  });

  it("returns empty list for empty selection", () => {
    expect(
      assembleWrongSheetItems({
        selectedKeys: [],
        questionAccuracy: accuracy,
        allWrongImages: images,
      }),
    ).toEqual([]);
  });

  it("filters by student when studentFilter is set", () => {
    const items = assembleWrongSheetItems({
      selectedKeys: ["q1", "q2"],
      questionAccuracy: accuracy,
      allWrongImages: images,
      studentFilter: ["张三"],
    });
    // q2 的图来自李四，且 wrong_students 未给，过滤后只留张三能命中的 q1
    expect(items.map((x) => x.id)).toEqual(["q1"]);
  });

  it("keeps questions whose wrong_students intersect the filter", () => {
    const items = assembleWrongSheetItems({
      selectedKeys: ["q1", "q2"],
      questionAccuracy: accuracy,
      allWrongImages: images,
      questionStudents: {
        q1: { wrong_students: ["王五"] },
        q2: { wrong_students: ["张三", "李四"] },
      },
      studentFilter: ["王五"],
    });
    // 王五只在 q1 的错答名单里；q2 的错答/裁图都不含王五
    expect(items.map((x) => x.id)).toEqual(["q1"]);
  });
});

describe("buildWrongSheetPlan", () => {
  const items = [
    item({ id: "a", title: "第1题" }),
    item({ id: "b", title: "第2题" }),
    item({ id: "c", title: "第3题" }),
  ];

  it("throws on empty selection", () => {
    expect(() =>
      buildWrongSheetPlan({
        items: [],
        className: "三(1)",
        subject: "数学",
      }),
    ).toThrow(WRONG_SHEET_EMPTY_SELECTION);
  });

  it("includes answer page by default and omits when disabled", () => {
    const withAnswers = buildWrongSheetPlan({
      items,
      className: "三(1)",
      subject: "数学",
      date: "2026-10-16",
      perPage: 2,
    });
    expect(withAnswers.answerPage?.items).toHaveLength(3);
    expect(withAnswers.pages).toHaveLength(2);
    expect(withAnswers.meta.title).toBe("错题巩固卷");

    const noAnswers = buildWrongSheetPlan({
      items,
      className: "三(1)",
      subject: "数学",
      date: "2026-10-16",
      includeAnswers: false,
    });
    expect(noAnswers.answerPage).toBeNull();
    expect(noAnswers.meta.date).toBe("2026-10-16");
  });
});

describe("wrongSheetFileName", () => {
  it("builds a pdf file name from meta", () => {
    expect(
      wrongSheetFileName({
        className: "三(1)",
        subject: "数学",
        date: "2026-10-16",
      }),
    ).toBe("数学_错题巩固卷_2026-10-16.pdf");
  });
});
