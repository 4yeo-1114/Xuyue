export interface NormalizableExamQuestion {
  id?: string;
  type?: string;
  stem?: string;
  content?: string;
  options?: string[];
  subQuestions?: string[];
  score?: number;
}

const MATH_RELATED_SUBJECT_KEYWORDS = ["数学", "物理", "化学"];

const FRAC_PATTERN = /\\frac\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}/g;

export function isMathRelatedSubject(subject: string): boolean {
  const s = (subject || "").trim();
  return MATH_RELATED_SUBJECT_KEYWORDS.some((k) => s.includes(k));
}

function formatFrac(num: string, den: string): string {
  const n = num.trim();
  const d = den.trim();
  const numPart = /[+\- ]/.test(n) ? `(${n})` : n;
  const denPart = /[+\- ]/.test(d) ? `(${d})` : d;
  return `${numPart}/${denPart}`;
}

export function normalizeExamMathNotation(text: string): string {
  if (!text || typeof text !== "string") return (text || "").trim();
  let s = text.trim();
  if (!s) return s;

  s = s.replace(/\$\$([^$]+)\$\$/g, "$1");
  s = s.replace(/\$([^$]+)\$/g, "$1");

  let prev = "";
  while (prev !== s) {
    prev = s;
    s = s.replace(FRAC_PATTERN, (_, num: string, den: string) => formatFrac(num, den));
  }

  const replacements: [RegExp, string][] = [
    [/\\times/g, "×"],
    [/\\div/g, "÷"],
    [/\\cdot/g, "·"],
    [/\\leq/g, "≤"],
    [/\\geq/g, "≥"],
    [/\\neq/g, "≠"],
    [/\\approx/g, "≈"],
    [/\\pi/g, "π"],
    [/\\infty/g, "∞"],
    [/\\pm/g, "±"],
    [/\\left\s*/g, ""],
    [/\\right\s*/g, ""],
    [/\\sqrt\{([^{}]+)\}/g, "√($1)"],
    [/\\text\{([^{}]+)\}/g, "$1"],
    [/\\,/g, ""],
    [/\\;/g, " "],
    [/\\!/g, ""],
  ];
  for (const [pattern, repl] of replacements) {
    s = s.replace(pattern, repl);
  }

  s = s.replace(/([a-zA-Z0-9])\^2\b/g, "$1²");
  s = s.replace(/([a-zA-Z0-9])\^3\b/g, "$1³");
  s = s.replace(/\\([a-zA-Z]+)/g, "$1");
  s = s.replace(/\(\s*\)\s*\(\s*\)/g, "（ ）");
  s = s.replace(/\(\s{2,}\)/g, "（ ）");
  s = s.replace(/[（(]\s*\d+\s*分\s*[）)]\s*$/g, "");
  s = s.replace(/[ \t]+/g, " ");
  return s.trim();
}

export function normalizeExamQuestionFields<T extends NormalizableExamQuestion>(question: T): T {
  const q = { ...question };
  if (q.stem) q.stem = normalizeExamMathNotation(String(q.stem));
  if (q.content) q.content = normalizeExamMathNotation(String(q.content));
  if (Array.isArray(q.options)) {
    q.options = q.options.map((opt) => normalizeExamMathNotation(String(opt)));
  }
  if (Array.isArray(q.subQuestions)) {
    q.subQuestions = q.subQuestions.map((sub) => normalizeExamMathNotation(String(sub)));
  }
  return q;
}

export function normalizeExamQuestions<T extends NormalizableExamQuestion>(
  questions: T[],
  subject: string
): T[] {
  if (!isMathRelatedSubject(subject)) return questions;
  return questions.map((q) => normalizeExamQuestionFields({ ...q }));
}
