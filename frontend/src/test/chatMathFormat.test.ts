import { describe, expect, it } from "vitest";

import { normalizeChatMathText } from "@/utils/chatMathFormat";

describe("normalizeChatMathText", () => {
  it("formats grading analysis math as readable Unicode", () => {
    const analysis =
      "根据定义，$5^3 = 5 \\times 5 \\times 5 = 125$；" +
      "$\\frac{3}{8} = 3 \\div 8$，且 $x_1^2 \\leq \\sqrt{9}$。";

    expect(normalizeChatMathText(analysis)).toBe(
      "根据定义，5³ = 5 × 5 × 5 = 125；3⁄8 = 3 ÷ 8，且 x₁² ≤ √(9)。",
    );
  });
});
