import { API_PREFIX } from "@/config/api";
import { getAuthToken } from "@/services/api";

export type AutoReportPending = {
  id: string;
  folder_safe: string;
  folder_display: string;
  report_type: "smart_scoring" | "essay";
  title: string;
  user_message: string;
  created_at: number;
};

export async function fetchPendingAutoReports(): Promise<AutoReportPending[]> {
  const token = await getAuthToken();
  if (!token) return [];
  const resp = await fetch(`${API_PREFIX}/ai-chat/auto-reports/pending`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) return [];
  const data = await resp.json().catch(() => ({}));
  return (data.reports || []) as AutoReportPending[];
}

export async function consumeAutoReport(reportId: string): Promise<void> {
  const token = await getAuthToken();
  if (!token) return;
  const resp = await fetch(
    `${API_PREFIX}/ai-chat/auto-reports/${encodeURIComponent(reportId)}/consume`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  if (!resp.ok) {
    // 不吞 404/401：让调用方 catch，避免服务端未真正消费却当作成功、
    // 或凭据失效导致 FloatingChat 反复拉取同一报告
    throw new Error(`HTTP ${resp.status}`);
  }
}

export async function streamAutoReport(
  reportId: string,
  onChunk: (chunk: string) => void,
): Promise<void> {
  const token = await getAuthToken();
  if (!token) throw new Error("请先登录后再使用 AI 助教");

  const resp = await fetch(
    `${API_PREFIX}/ai-chat/auto-reports/${encodeURIComponent(reportId)}/stream`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    },
  );

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(err.detail || err.error || `HTTP ${resp.status}`);
  }
  if (!resp.body) throw new Error("No stream body");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done = false;

  while (!done) {
    const { done: rd, value } = await reader.read();
    if (rd) break;
    buffer += decoder.decode(value, { stream: true });

    let nl: number;
    while ((nl = buffer.indexOf("\n")) !== -1) {
      let line = buffer.slice(0, nl);
      buffer = buffer.slice(nl + 1);
      if (line.endsWith("\r")) line = line.slice(0, -1);
      if (line.startsWith(":") || !line.trim()) continue;
      if (!line.startsWith("data: ")) continue;
      const json = line.slice(6).trim();
      if (json === "[DONE]") {
        done = true;
        break;
      }
      try {
        const p = JSON.parse(json);
        const c = p.choices?.[0]?.delta?.content;
        if (c) onChunk(c);
      } catch {
        buffer = line + "\n" + buffer;
        break;
      }
    }
  }
}

/** 批改页统分/作文完成后可主动触发一次检查 */
export const AI_AUTO_REPORT_CHECK_EVENT = "ai-auto-report-check";

export function notifyAutoReportCheck(): void {
  window.dispatchEvent(new CustomEvent(AI_AUTO_REPORT_CHECK_EVENT));
}
