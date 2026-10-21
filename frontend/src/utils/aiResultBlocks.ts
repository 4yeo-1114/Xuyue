/**
 * AI 批改结果解析块的共享实现。
 *
 * 历史背景:grading 域(GradingStartPage)与 home 域(GradingEntrySection)各有一份重复的
 * parseAiResultBlocks / inferAiBlockStatus / normalizeEssayResultForDisplay 实现,因
 * home 域在 i18n 批6 复制整坨逻辑导致分叉。本模块收敛为唯一实现:
 * - 行为取 grading 域完整版(含 normalizeChatMathText 预处理 + <essay_score> 过滤)
 * - 题目标题统一走 i18n(grading.ai.questionTitle,参数 { n })
 */

import { normalizeChatMathText } from "./chatMathFormat";

export type AiBlockStatus = "correct" | "wrong" | "blank" | "partial" | "unknown";
export type SubItem = {
  content: string;
  status: AiBlockStatus;
  partial_ratio?: number;
  /** 题号 key（与后端 wrong_annotations / question_notes 的键一致） */
  key?: string;
};
export type AiResultBlock = {
  title: string;
  content: string;
  status: AiBlockStatus;
  partial_ratio?: number;
  /** 大题块对应的题号 key（取首个子项） */
  key?: string;
  subItems?: SubItem[];
};

type TranslateFn = (
  key: string,
  params?: Record<string, string | number>,
  fallback?: string,
) => string;

export function inferAiBlockStatus(content: string): AiBlockStatus {
  const t = (content || "").trim();
  if (!t) return "unknown";

  // 1. 提取最前面的判定结果（最准确，避免被后面的解析文字干扰）
  // 匹配：第X题-作答区Y：状态 或者 第X题：状态
  const statusMatch = t.match(
    /^第[0-9A-Za-z\(\)（）一二三四五六七八九十百千两]+题(?:[-—]作答区[0-9]+)?[:：]\s*(对|错|正确|错误|半对|待确认|未答|未作答|空白)/,
  );
  if (statusMatch) {
    const s = statusMatch[1];
    if (s === "对" || s === "正确") return "correct";
    if (s === "错" || s === "错误") return "wrong";
    if (s === "半对") return "partial";
    // 待确认 = AI 读不清手写、未判对错，交老师确认（不能落进 wrong/blank 统计）
    if (s === "待确认") return "unknown";
    if (s === "未答" || s === "未作答" || s === "空白") return "blank";
  }

  // 2. 兜底精确匹配冒号后的状态
  if (
    t.includes("：对") ||
    t.includes(": 对") ||
    t.includes("：正确") ||
    t.includes(": 正确")
  )
    return "correct";
  if (
    t.includes("：错") ||
    t.includes(": 错") ||
    t.includes("：错误") ||
    t.includes(": 错误")
  )
    return "wrong";
  if (t.includes("：半对") || t.includes(": 半对")) return "partial";
  if (t.includes("：待确认") || t.includes(": 待确认")) return "unknown";
  if (t.includes("：未作答") || t.includes(": 未作答") || t.includes("：空白"))
    return "blank";

  // 3. 最后的模糊兜底（如果前面都匹配不到，只能靠猜）
  const hasPartial = /半对/.test(t);
  const hasWrong = /错误|不正确|有误|incorrect|wrong/.test(t);
  const hasBlank = /未作答|未答|空白|未填写|blank/.test(t);
  const hasCorrect = /正确|匹配|无明显错误|correct/.test(t);

  if (hasPartial) return "partial";
  if (hasBlank) return "blank";
  if (hasWrong) return "wrong";
  if (hasCorrect) return "correct";
  return "unknown";
}

/** 从结果文本里提取半对比例（如 半对（0.6）→ 0.6）；没有则返回 undefined。 */
export function extractPartialRatio(content: string): number | undefined {
  const m = (content || "").match(/半对[（(]\s*([0-9]+(?:\.[0-9]+)?)\s*[)）]/);
  if (!m) return undefined;
  const ratio = parseFloat(m[1]);
  if (Number.isNaN(ratio)) return undefined;
  return Math.min(1, Math.max(0, ratio));
}

/** 去掉字面量 \\u3000，并为【习作提升】补上真实段首缩进（两个全角空格） */
export function normalizeEssayResultForDisplay(text: string): string {
  let raw = (text || "").replace(/\\u3000+/g, "");
  const marker = "【习作提升】";
  const idx = raw.indexOf(marker);
  if (idx === -1) return raw;

  const before = raw.slice(0, idx + marker.length);
  let after = raw.slice(idx + marker.length);
  const nextIdx = after.indexOf("【");
  const rewrite = nextIdx === -1 ? after : after.slice(0, nextIdx);
  const rest = nextIdx === -1 ? "" : after.slice(nextIdx);
  const indent = "　　";

  const rewritten = rewrite
    .split("\n")
    .map((line) => {
      const stripped = line.replace(/^[　 \t]+/, "");
      return stripped ? indent + stripped : "";
    })
    .join("\n");

  return before + rewritten + rest;
}

export function parseAiResultBlocks(
  text: string,
  t?: TranslateFn,
): AiResultBlock[] {
  let raw = normalizeChatMathText(
    normalizeEssayResultForDisplay((text || "").trim()),
  );
  // 去除隐式的评分标签，不在前端界面的AI解析块中作为独立内容显示
  raw = raw.replace(/<essay_score>[\s\S]*?<\/essay_score>/g, "").trim();
  const parseResultTitle = t ? t("grading.ai.parseResult") : "解析结果";
  const overviewTitle = t ? t("grading.ai.overview") : "总览";

  if (!raw)
    return [
      { title: parseResultTitle, content: "", status: "unknown", subItems: [] },
    ];
  const lines = raw.split(/\r?\n/);
  // 匹配 "第x题" 或者 "第x题-作答区y"
  // 注意：这里的正则不仅支持数字，还支持汉字，以及如 "1(1)" 这种复杂的题号
  const qStart = /^第([0-9A-Za-z\(\)（）一二三四五六七八九十百千两]+)题/;
  const blocks: AiResultBlock[] = [];
  let currentTitle = "";
  let currentKey = "";
  let buffer: string[] = [];
  let summary: string[] = [];

  const flush = () => {
    if (currentTitle) {
      const content = buffer.join("\n").trim();
      const itemStatus = inferAiBlockStatus(content);
      const itemPartialRatio = extractPartialRatio(content);

      // 检查之前是否已经有这个大题了
      const existingBlock = blocks.find((b) => b.title === currentTitle);
      if (existingBlock) {
        // 如果已经有这个大题，作为子项追加进去
        if (!existingBlock.subItems) existingBlock.subItems = [];
        existingBlock.subItems.push({
          content,
          status: itemStatus,
          partial_ratio: itemPartialRatio,
          key: currentKey,
        });
        // 为了兼容旧字段
        existingBlock.content += "\n\n" + content;
        if (itemStatus === "wrong" || itemStatus === "blank") {
          existingBlock.status = "wrong";
        } else if (itemStatus === "partial" && existingBlock.status !== "wrong") {
          existingBlock.status = "partial";
          existingBlock.partial_ratio = itemPartialRatio;
        }
      } else {
        blocks.push({
          title: currentTitle,
          content,
          status: itemStatus,
          partial_ratio: itemPartialRatio,
          key: currentKey,
          subItems: [
            { content, status: itemStatus, partial_ratio: itemPartialRatio, key: currentKey },
          ],
        });
      }
    }
    currentTitle = "";
    currentKey = "";
    buffer = [];
  };

  for (const ln of lines) {
    const line = ln.trimEnd();
    if (!line.trim()) continue;
    const m = line.match(qStart);
    if (m) {
      flush();
      currentTitle = t
        ? t("grading.ai.questionTitle", { n: m[1] })
        : `第${m[1]}题`;
      currentKey = m[1];
      buffer.push(line);
    } else if (currentTitle) {
      buffer.push(line);
    } else {
      summary.push(line);
    }
  }
  flush();
  if (summary.length) {
    const content = summary.join("\n");
    blocks.unshift({
      title: overviewTitle,
      content,
      status: inferAiBlockStatus(content),
    });
  }
  return blocks.length
    ? blocks
    : [
        {
          title: parseResultTitle,
          content: raw,
          status: inferAiBlockStatus(raw),
        },
      ];
}
