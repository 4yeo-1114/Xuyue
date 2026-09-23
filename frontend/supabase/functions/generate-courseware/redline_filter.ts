/**
 * 流式红线词过滤器 —— Python 父本 RedlineFilter 的 TypeScript 忠实移植。
 *
 * 父本：F:/grade-buddy-parent家长端/parent-service/app/services/redline_filter.py
 *
 * 设计要点（与父本一致）：
 *   - 最长短语优先匹配：先匹配长短语，避免短前缀误伤
 *   - 滑动窗口缓冲：当缓冲尾是某短语的前缀时保持不释放——
 *     LLM 会把中文短语拆到多个 token，逐 token 硬删会拆字出错
 *   - 删除类命中后合并相邻空白，不留双空格残渣；替换类直接替换
 *   - flush()：流结束时释放残留缓冲（残留不可能构成完整命中）
 *
 * 纯函数式：无 IO、无外部依赖、无网络，可单测（Deno / Node / 浏览器均可用）。
 */
import { REDLINE_PHRASES } from "./redline_phrases.ts";

type PhraseMap = Readonly<Record<string, string | null>>;

const isSpace = (ch: string): boolean => /\s/.test(ch);

export class RedlineFilter {
  private readonly phrases: PhraseMap;
  private readonly sorted: string[];
  private readonly prefixes: Set<string>;
  private buf = "";
  private pendingMerge = false;
  private mergeHasLeftWs = false;

  constructor(phrases?: PhraseMap) {
    this.phrases = phrases ?? REDLINE_PHRASES;
    this.sorted = Object.keys(this.phrases).sort((a, b) => b.length - a.length);
    this.prefixes = new Set<string>();
    for (const phrase of Object.keys(this.phrases)) {
      for (let i = 1; i <= phrase.length; i++) {
        this.prefixes.add(phrase.slice(0, i));
      }
    }
  }

  /** 输入 LLM 分片 token，返回此刻可安全释放的片段（可为空串）。 */
  feed(chunk: string): string {
    this.buf += chunk;
    const out: string[] = [];
    while (true) {
      const match = this.findMatch(this.buf);
      if (match !== null) {
        const [start, end, phrase] = match;
        const safe = this.buf.slice(0, start);
        const stripped = safe.trimEnd();
        const heldWs = safe.slice(stripped.length);
        if (stripped) {
          out.push(stripped);
          this.pendingMerge = false;
        }
        const repl = this.phrases[phrase];
        if (repl !== null) {
          // 替换类：保留删除/替换前已有的空白，直接替换短语
          if (heldWs) out.push(heldWs);
          out.push(repl);
          this.pendingMerge = false;
        } else {
          // 删除类：丢掉前面的空白，等下一次释放时合并为单个空格
          this.pendingMerge = true;
          this.mergeHasLeftWs = heldWs.length > 0;
        }
        this.buf = this.buf.slice(end);
        continue;
      }
      // 无完整命中：释放除"可能是短语前缀"的尾部以外的内容
      const hold = this.holdLen();
      let safeChunk: string;
      if (hold > 0) {
        safeChunk = this.buf.slice(0, this.buf.length - hold);
        this.buf = this.buf.slice(this.buf.length - hold);
      } else {
        safeChunk = this.buf;
        this.buf = "";
      }
      if (safeChunk) out.push(this.emit(safeChunk));
      break;
    }
    return out.join("");
  }

  /** 流结束时释放残留缓冲。残留不可能构成完整命中，直接原样放行。 */
  flush(): string {
    const tail = this.emit(this.buf);
    this.buf = "";
    this.pendingMerge = false;
    this.mergeHasLeftWs = false;
    return tail;
  }

  /** 返回 text 中最靠左的完整命中 [start, end, phrase]；无命中返回 null。 */
  private findMatch(text: string): [number, number, string] | null {
    const n = text.length;
    for (let i = 0; i < n; i++) {
      for (const phrase of this.sorted) {
        const pLen = phrase.length;
        if (i + pLen <= n && text.slice(i, i + pLen) === phrase) {
          return [i, i + pLen, phrase];
        }
      }
    }
    return null;
  }

  /**
   * 缓冲尾需要保持不释放的长度（最长前缀优先）。
   * 除"能成为某短语前缀"的尾部外，还要把前缀前面的空白一起保持，
   * 这样短语在后续 feed 里被删除时，前面的空白仍在缓冲内，可被合并。
   */
  private holdLen(): number {
    const n = this.buf.length;
    let hold = 0;
    for (let i = n; i > 0; i--) {
      if (this.prefixes.has(this.buf.slice(n - i))) {
        hold = i;
        break;
      }
    }
    let j = n - hold - 1;
    while (j >= 0 && isSpace(this.buf[j])) {
      hold += 1;
      j -= 1;
    }
    return hold;
  }

  /** 释放片段时应用删除后的空白合并：把删除点两侧空白并为单个空格。 */
  private emit(safe: string): string {
    if (this.pendingMerge) {
      this.pendingMerge = false;
      const left = this.mergeHasLeftWs;
      this.mergeHasLeftWs = false;
      if (left || (safe.length > 0 && isSpace(safe[0]))) {
        return " " + safe.trimStart();
      }
      return safe;
    }
    return safe;
  }
}

/** 整段文本红线过滤，语义与流式 RedlineFilter 等价。 */
export function filterText(text: string): string {
  const filt = new RedlineFilter();
  return filt.feed(text) + filt.flush();
}
