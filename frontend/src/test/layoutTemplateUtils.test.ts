import { describe, expect, it } from "vitest";

import {
  applyTemplateToPages,
  packLayoutForTemplate,
  scaleBbox,
  templateLayoutPages,
  type LayoutTemplateDetail,
} from "@/components/grading/layoutTemplateUtils";
import type { ReferenceLayoutPage } from "@/services/gradingApi";

const page1: ReferenceLayoutPage = {
  page_no: 1,
  filename: "std_1.jpg",
  image_url: "a/std_1.jpg",
  image_size: [1000, 1400],
  questions: [
    {
      question_id: "q-cur",
      display_no: 1,
      regions: [
        {
          region_id: "r1",
          label: "1-A",
          role: "question",
          order: 1,
          bbox: [10, 10, 100, 50],
        },
      ],
      answer_slots: [
        {
          slot_id: "s1",
          label: "1_1",
          order: 1,
          bbox: [10, 60, 80, 100],
          regions: [{ bbox: [10, 60, 80, 100] }],
        },
      ],
    },
  ],
};

const templatePage1: ReferenceLayoutPage = {
  page_no: 1,
  filename: "old_1.jpg",
  image_url: "old/old_1.jpg",
  image_size: [1000, 1400],
  questions: [
    {
      question_id: "q-tpl",
      display_no: 1,
      regions: [
        {
          region_id: "tr1",
          label: "1-A",
          role: "question",
          order: 1,
          bbox: [100, 200, 500, 300],
        },
      ],
      answer_slots: [
        {
          slot_id: "ts1",
          label: "1_1",
          order: 1,
          bbox: [100, 320, 480, 400],
          regions: [{ bbox: [100, 320, 480, 400] }],
          has_handwriting_location: true,
        },
      ],
    },
  ],
};

describe("scaleBbox", () => {
  it("returns the same box when sizes match", () => {
    expect(scaleBbox([1, 2, 3, 4], [100, 100], [100, 100])).toEqual([
      1, 2, 3, 4,
    ]);
  });

  it("scales proportionally when image size differs", () => {
    // 2 倍宽、1 倍高
    expect(scaleBbox([10, 20, 30, 40], [100, 100], [200, 100])).toEqual([
      20, 20, 60, 40,
    ]);
  });

  it("keeps box when a size is missing", () => {
    expect(scaleBbox([1, 2, 3, 4], [0, 0], [100, 100])).toEqual([1, 2, 3, 4]);
  });
});

describe("applyTemplateToPages", () => {
  it("replaces questions by page_no and keeps current page chrome", () => {
    const result = applyTemplateToPages([page1], [templatePage1]);
    expect(result).toHaveLength(1);
    expect(result[0].filename).toBe("std_1.jpg");
    expect(result[0].image_url).toBe("a/std_1.jpg");
    expect(result[0].image_size).toEqual([1000, 1400]);
    expect(result[0].questions[0].question_id).toBe("q-tpl");
    expect(result[0].questions[0].answer_slots[0].bbox).toEqual([
      100, 320, 480, 400,
    ]);
  });

  it("scales template boxes when image sizes differ", () => {
    const target: ReferenceLayoutPage = {
      ...page1,
      image_size: [2000, 2800], // 2x
    };
    const result = applyTemplateToPages([target], [templatePage1]);
    expect(result[0].questions[0].regions[0].bbox).toEqual([
      200, 400, 1000, 600,
    ]);
    expect(result[0].questions[0].answer_slots[0].bbox).toEqual([
      200, 640, 960, 800,
    ]);
  });

  it("keeps unmatched current pages untouched", () => {
    const page2: ReferenceLayoutPage = {
      ...page1,
      page_no: 2,
      filename: "std_2.jpg",
    };
    const result = applyTemplateToPages([page1, page2], [templatePage1]);
    expect(result[0].questions[0].question_id).toBe("q-tpl");
    expect(result[1].questions[0].question_id).toBe("q-cur");
    expect(result[1].filename).toBe("std_2.jpg");
  });

  it("ignores extra template pages and empty inputs", () => {
    expect(applyTemplateToPages([], [templatePage1])).toEqual([]);
    const result = applyTemplateToPages([page1], [
      templatePage1,
      { ...templatePage1, page_no: 9 },
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].questions[0].question_id).toBe("q-tpl");
  });

  it("keeps current questions when template page has none", () => {
    const emptyTpl = { ...templatePage1, questions: [] };
    const result = applyTemplateToPages([page1], [emptyTpl]);
    expect(result[0].questions[0].question_id).toBe("q-cur");
  });
});

describe("packLayoutForTemplate / templateLayoutPages", () => {
  it("round-trips pages through layout JSON shape", () => {
    const packed = packLayoutForTemplate([page1]);
    expect(packed.version).toBe(1);
    expect(packed.pages).toHaveLength(1);

    const detail = {
      id: "lt_1",
      name: "t",
      layout: packed,
    } as LayoutTemplateDetail;
    const pages = templateLayoutPages(detail);
    expect(pages[0].page_no).toBe(1);
    expect(pages[0].questions[0].question_id).toBe("q-cur");
  });

  it("returns empty array for missing layout", () => {
    expect(templateLayoutPages(null)).toEqual([]);
    expect(
      templateLayoutPages({ id: "x", name: "y", layout: {} }),
    ).toEqual([]);
  });
});
