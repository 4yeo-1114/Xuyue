/**
 * SSE 流式转发过滤器 —— 透传 OpenAI 兼容 SSE 帧的同时对内容做红线过滤。
 *
 * 只改「内容」，绝不破坏流结构。策略：
 *   1. 以 `\n\n` 为帧分隔符在流层缓冲，绝不半帧转发；UTF-8 多字节字符
 *      跨网络 chunk 截断由 TextDecoder({ stream: true }) 兜底。
 *   2. 逐行处理帧内行：仅改写 `data:` 行里 choices[0].delta.content，
 *      其余字段（id/model/created/usage/role/finish_reason 等）原样保留；
 *      `event:` / `id:` / 注释行 等非 data 行原样透传。
 *   3. JSON 解析失败 / 非内容 data 行 → 原样透传，绝不吞帧。
 *   4. 跨帧短语截断：RedlineFilter 内置滑动窗口缓冲（feed/flush），
 *      上一帧尾部被截断的短语前缀会保留到下一帧再匹配，中文多 token 拆分不漏。
 *   5. 删除类命中使某帧 content 为空时仍保留帧结构（content: ""），客户端可安全忽略；
 *      流结束（[DONE] 或 EOF）时 flush 残留缓冲，保证文本不丢失。
 */
import { RedlineFilter } from "./redline_filter.ts";

interface Delta {
  content?: string;
}
interface Choice {
  delta?: Delta;
}
interface ChunkFrame {
  choices?: Choice[];
}

const encoder = new TextEncoder();

/** 构造一个携带纯文本内容的 SSE 内容帧（用于 flush 残留文本时兜底）。 */
function frameForContent(text: string): string {
  const frame: ChunkFrame = { choices: [{ delta: { content: text } }] };
  return "data: " + JSON.stringify(frame);
}

export function createRedlineStreamTransformer(): TransformStream<
  Uint8Array,
  Uint8Array
> {
  const decoder = new TextDecoder();
  const filter = new RedlineFilter();
  let frameBuf = "";

  const emitFrame = (
    frameText: string,
    controller: { enqueue: (chunk: Uint8Array) => void },
  ) => {
    const lines = frameText.split("\n");
    const out: string[] = [];
    for (const rawLine of lines) {
      if (rawLine.startsWith("data:")) {
        const payload = rawLine.slice(5).trim();
        if (payload === "[DONE]") {
          // 收尾帧：先把过滤缓冲里残留的文本作为内容帧释放，再透传 [DONE]
          const tail = filter.flush();
          if (tail)
            controller.enqueue(encoder.encode(frameForContent(tail) + "\n\n"));
          out.push(rawLine);
          continue;
        }
        let parsed: ChunkFrame;
        try {
          parsed = JSON.parse(payload) as ChunkFrame;
        } catch {
          out.push(rawLine);
          continue;
        }
        const delta = parsed.choices?.[0]?.delta;
        if (delta && typeof delta.content === "string") {
          delta.content = filter.feed(delta.content);
          out.push("data: " + JSON.stringify(parsed));
        } else {
          out.push(rawLine);
        }
      } else {
        out.push(rawLine);
      }
    }
    if (out.length > 0) {
      controller.enqueue(encoder.encode(out.join("\n") + "\n\n"));
    }
  };

  return new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      frameBuf += decoder.decode(chunk, { stream: true });
      let idx: number;
      while ((idx = frameBuf.indexOf("\n\n")) !== -1) {
        const frame = frameBuf.slice(0, idx);
        frameBuf = frameBuf.slice(idx + 2);
        emitFrame(frame, controller);
      }
    },
    flush(controller) {
      if (frameBuf) {
        emitFrame(frameBuf, controller);
        frameBuf = "";
      }
      // EOF 未遇 [DONE] 时兜底释放过滤残留
      const tail = filter.flush();
      if (tail)
        controller.enqueue(encoder.encode(frameForContent(tail) + "\n\n"));
    },
  });
}
