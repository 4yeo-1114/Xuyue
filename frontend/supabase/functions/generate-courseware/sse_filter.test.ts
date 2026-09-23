import { describe, expect, it } from "vitest";
import { createRedlineStreamTransformer } from "./sse_filter.ts";

const encoder = new TextEncoder();
const decoder = new TextDecoder();

function frame(deltaContent: string): string {
  return `data: ${JSON.stringify({ choices: [{ delta: { content: deltaContent } }] })}`;
}

/** 将 SSE 原始文本按 size 字节切成小块，喂入转换器并回收全部输出。 */
async function runThrough(sse: string, size = 1): Promise<string> {
  const bytes = encoder.encode(sse);
  const chunks: Uint8Array[] = [];
  for (let i = 0; i < bytes.length; i += size)
    chunks.push(bytes.slice(i, i + size));

  const transform = createRedlineStreamTransformer();
  const writer = transform.writable.getWriter();
  const reader = transform.readable.getReader();
  const out: string[] = [];
  const write = (async () => {
    for (const c of chunks) await writer.write(c);
    await writer.close();
  })();
  const read = (async () => {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      out.push(decoder.decode(value));
    }
  })();
  await Promise.all([write, read]);
  return out.join("");
}

interface Parsed {
  contents: string[];
  raw: string[];
  done: boolean;
  badJson: string[];
}

/** 解析输出 SSE，提取每帧 data 的 delta.content，校验结构合法性。 */
function parseOutput(out: string): Parsed {
  const parsed: Parsed = { contents: [], raw: [], done: false, badJson: [] };
  for (const frameText of out.split("\n\n")) {
    for (const line of frameText.split("\n")) {
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (payload === "[DONE]") {
        parsed.done = true;
        continue;
      }
      parsed.raw.push(payload);
      try {
        const obj = JSON.parse(payload) as {
          choices?: { delta?: { content?: unknown } }[];
        };
        const c = obj.choices?.[0]?.delta?.content;
        if (typeof c === "string") parsed.contents.push(c);
      } catch {
        parsed.badJson.push(payload);
      }
    }
  }
  return parsed;
}

describe("createRedlineStreamTransformer（SSE 输出侧过滤）", () => {
  it("替换类：改写 content，帧结构合法，[DONE] 透传", async () => {
    const out = await runThrough(
      `${frame("说莫扎特效应好")}\n\ndata: [DONE]\n\n`,
    );
    const p = parseOutput(out);
    expect(p.badJson).toEqual([]);
    expect(p.contents.join("")).toBe("说音乐欣赏好");
    expect(p.done).toBe(true);
  });

  it("删除类：整帧删除 content 仍保留帧结构（content 为空串）", async () => {
    const out = await runThrough(`${frame("练开天眼功")}\n\ndata: [DONE]\n\n`);
    const p = parseOutput(out);
    expect(p.badJson).toEqual([]);
    expect(p.contents.join("")).toBe("练功");
    expect(p.done).toBe(true);
  });

  it("短语跨多个 SSE 内容帧仍命中（多巴胺 + 成瘾 拆分）", async () => {
    const out = await runThrough(
      `${frame("多巴胺")}\n\n${frame("成瘾害人")}\n\ndata: [DONE]\n\n`,
    );
    const p = parseOutput(out);
    expect(p.badJson).toEqual([]);
    expect(p.contents).toEqual(["", "过度依赖即时刺激害人"]);
    expect(p.done).toBe(true);
  });

  it("网络 chunk 按 1 字节喂入也不破坏帧/JSON", async () => {
    const sse = `${frame("正常文本通过")}\n\n${frame("避免多巴胺成瘾")}\n\ndata: [DONE]\n\n`;
    const out = await runThrough(sse, 1);
    const p = parseOutput(out);
    expect(p.badJson).toEqual([]);
    expect(p.contents.join("")).toBe("正常文本通过避免过度依赖即时刺激");
    expect(p.done).toBe(true);
  });

  it("非内容帧（role delta）与无 content 帧原样透传", async () => {
    const sse =
      `data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n` +
      `${frame("你好")}\n\ndata: [DONE]\n\n`;
    const out = await runThrough(sse);
    const p = parseOutput(out);
    expect(p.badJson).toEqual([]);
    expect(p.raw).toContain('{"choices":[{"delta":{"role":"assistant"}}]}');
    expect(p.contents.join("")).toBe("你好");
    expect(p.done).toBe(true);
  });

  it("非 JSON data 行原样透传（不吞帧）", async () => {
    const out = await runThrough(`data: heartbeat\n\ndata: [DONE]\n\n`);
    expect(out).toContain("data: heartbeat");
    expect(out).toContain("data: [DONE]");
  });

  it("流在 [DONE] 前结束，残留前缀 flush 成内容帧，文本不丢", async () => {
    // “窗口”是“窗口期”的前缀，feed 时被缓冲；[DONE] 到达后先 flush 成内容帧再收尾
    const out = await runThrough(`${frame("窗口")}\n\ndata: [DONE]\n\n`);
    const p = parseOutput(out);
    expect(p.badJson).toEqual([]);
    expect(p.contents).toEqual(["", "窗口"]);
    expect(p.done).toBe(true);
    expect(out.trim().endsWith("data: [DONE]")).toBe(true);
  });

  it("CRLF 行尾（\\r\\n\\r\\n）也可正确解析并保持帧结构", async () => {
    const sse = `${frame("练习右脑开发提升")}\r\n\r\ndata: [DONE]\r\n\r\n`;
    const out = await runThrough(sse);
    const p = parseOutput(out);
    expect(p.badJson).toEqual([]);
    expect(p.contents.join("")).toBe("练习提升");
    expect(p.done).toBe(true);
  });
});
