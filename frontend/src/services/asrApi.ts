/**
 * 语音转文字（ASR）API 封装 — 教师语音录入 P0。
 *
 * 上传浏览器录音 Blob → 后端 POST /api/v1/audio/asr → 返回识别文字。
 * 走 multipart/form-data，不复用 request()（其默认 Content-Type: application/json
 * 不适合文件上传），手动带 Authorization Bearer token 并解包 {data:{text}}。
 */
import { getAuthToken } from "@/services/api";
import { API_PREFIX } from "@/config/api";

/** POST /api/v1/audio/asr 响应 data 段 */
export interface AsrResult {
  text: string;
}

/**
 * 上传音频 Blob，返回识别出的中文文字。
 * @param blob  浏览器 MediaRecorder 采集的音频
 * @param fallbackFilename 无可用扩展名时的兜底文件名
 */
export async function asrTranscribe(
  blob: Blob,
  fallbackFilename = "voice.webm"
): Promise<string> {
  const token = await getAuthToken();
  const ext = mimeToExt(blob.type);
  const name = ext ? `voice.${ext}` : fallbackFilename;
  const file = new File([blob], name, { type: blob.type || "audio/webm" });

  const formData = new FormData();
  formData.append("file", file);

  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_PREFIX}/audio/asr`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!res.ok) {
    let message = `语音转写失败(${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (body?.message) message = String(body.message);
    } catch {
      // 非 JSON 错误体，保留默认文案
    }
    throw new Error(message);
  }

  const json = (await res.json()) as { data?: AsrResult };
  return (json?.data?.text ?? "").trim();
}

/** MIME type → 文件扩展名（用于后端判定容器类型）；未知返回 null */
function mimeToExt(mime: string): string | null {
  if (!mime) return null;
  const m = mime.toLowerCase();
  if (m.includes("webm")) return "webm";
  if (m.includes("ogg") || m.includes("opus")) return "ogg";
  if (m.includes("mp4") || m.includes("m4a") || m.includes("aac")) return "m4a";
  if (m.includes("mp3") || m.includes("mpeg")) return "mp3";
  if (m.includes("wav") || m.includes("wave")) return "wav";
  return null;
}
