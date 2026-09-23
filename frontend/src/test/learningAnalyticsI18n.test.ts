import { describe, expect, it } from "vitest";

import {
  learningAnalyticsEn,
  learningAnalyticsZh,
} from "@/i18n/locales/modules/learningAnalytics";

describe("learning analytics translations", () => {
  it("keeps Chinese and English keys aligned", () => {
    expect(Object.keys(learningAnalyticsEn).sort()).toEqual(
      Object.keys(learningAnalyticsZh).sort(),
    );
  });

  it("does not leave Chinese text in English values", () => {
    const untranslated = Object.entries(learningAnalyticsEn).filter(([, value]) =>
      /[\u4e00-\u9fff]/.test(value),
    );

    expect(untranslated).toEqual([]);
  });

  it("contains the four page titles", () => {
    expect(learningAnalyticsEn["studentAnalysis.currentSubject"]).toBe("Current Subject");
    expect(learningAnalyticsEn["classAnalysis.title"]).toBe("Class Analysis");
    expect(learningAnalyticsEn["classReview.title"]).toBe("Class Review");
    expect(learningAnalyticsEn["targeted.title"]).toBe("Targeted Improvement");
  });
});
