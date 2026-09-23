/**
 * AI 助教消息中的数学/理化符号规范化（无 KaTeX 时将 LaTeX/^ 写法转为 Unicode 可读形式）
 */

const SUPERSCRIPT: Record<string, string> = {
  "0": "⁰",
  "1": "¹",
  "2": "²",
  "3": "³",
  "4": "⁴",
  "5": "⁵",
  "6": "⁶",
  "7": "⁷",
  "8": "⁸",
  "9": "⁹",
  "+": "⁺",
  "-": "⁻",
  n: "ⁿ",
  x: "ˣ",
  y: "ʸ",
};

const SUBSCRIPT: Record<string, string> = {
  "0": "₀",
  "1": "₁",
  "2": "₂",
  "3": "₃",
  "4": "₄",
  "5": "₅",
  "6": "₆",
  "7": "₇",
  "8": "₈",
  "9": "₉",
  "+": "₊",
  "-": "₋",
  n: "ₙ",
};

function toSuperscript(text: string): string {
  return [...text].map((c) => SUPERSCRIPT[c] ?? c).join("");
}

function toSubscript(text: string): string {
  return [...text].map((c) => SUBSCRIPT[c] ?? c).join("");
}

function formatFraction(numerator: string, denominator: string): string {
  const wrap = (value: string) => {
    const normalized = value.trim();
    return /[\s+\-*/=]/.test(normalized) ? "(" + normalized + ")" : normalized;
  };
  return wrap(numerator) + "⁄" + wrap(denominator);
}

/** 将 LaTeX/^ 片段转为 Unicode 可读文本 */
export function formatMathExpression(raw: string): string {
  let s = (raw || "").trim();
  if (!s) return s;

  s = s.replace(
    /\\(?:dfrac|tfrac|frac)\{([^}]+)\}\{([^}]+)\}/g,
    (_, numerator, denominator) => formatFraction(numerator, denominator),
  );
  s = s.replace(/\\sqrt\{([^}]+)\}/g, "√($1)");
  s = s.replace(/\\sqrt\[(\d+)\]\{([^}]+)\}/g, "$1√($2)");

  const latexSymbols: [RegExp, string][] = [
    [/\\times/g, "×"],
    [/\\div/g, "÷"],
    [/\\cdot/g, "·"],
    [/\\pm/g, "±"],
    [/\\mp/g, "∓"],
    [/\\leq/g, "≤"],
    [/\\le/g, "≤"],
    [/\\geq/g, "≥"],
    [/\\ge/g, "≥"],
    [/\\neq/g, "≠"],
    [/\\ne/g, "≠"],
    [/\\approx/g, "≈"],
    [/\\infty/g, "∞"],
    [/\\pi/g, "π"],
    [/\\alpha/g, "α"],
    [/\\beta/g, "β"],
    [/\\gamma/g, "γ"],
    [/\\theta/g, "θ"],
    [/\\Delta/g, "Δ"],
    [/\\degree/g, "°"],
    [/\\circ/g, "°"],
    [/\\text\{([^}]*)\}/g, "$1"],
    [/\\mathrm\{([^}]*)\}/g, "$1"],
    [/\\left/g, ""],
    [/\\right/g, ""],
    [/\\,/g, " "],
    [/\\;/g, " "],
    [/\\quad/g, " "],
    [/\\qquad/g, "  "],
  ];
  for (const [pat, rep] of latexSymbols) {
    s = s.replace(pat, rep);
  }

  s = s.replace(/\^\{([^}]+)\}/g, (_, exp) => toSuperscript(exp));
  s = s.replace(/\^(\d+)/g, (_, exp) => toSuperscript(exp));
  s = s.replace(/\^([a-zA-Z])/g, (_, c) => toSuperscript(c));

  s = s.replace(/_\{([^}]+)\}/g, (_, sub) => toSubscript(sub));
  s = s.replace(/_(\d+)/g, (_, sub) => toSubscript(sub));

  s = s.replace(/\\([a-zA-Z]+)/g, "$1");
  s = s.replace(/\s+/g, " ").trim();
  return s;
}

/** 处理全文：$...$、$$...$$，以及未包裹的 cm^3 等常见写法 */
export function normalizeChatMathText(text: string): string {
  if (!text) return text;

  let out = text.replace(/\$\$([\s\S]+?)\$\$/g, (_, math) => formatMathExpression(math));
  out = out.replace(/\$([^$\n]+?)\$/g, (_, math) => formatMathExpression(math));

  // 未用 $ 包裹的常见单位幂次（避免误伤 URL）
  out = out.replace(
    /\b([a-zA-Z]{1,4})\^(\d+)\b/g,
    (_, base: string, exp: string) => base + toSuperscript(exp),
  );

  return out;
}
