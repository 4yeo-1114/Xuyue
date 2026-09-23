import { request } from "@/services/api";

/** 历史会话列表项（GET /ai-chat/history 的 items 元素） */
export interface AiChatHistoryItem {
  id: string;
  title: string;
  summary?: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

/** 历史会话消息（GET /ai-chat/history/{id} 的 messages 元素，seq 升序） */
export interface AiChatHistoryMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  model?: string | null;
  seq: number;
  created_at: string;
}

/** 历史会话详情 */
export interface AiChatHistoryDetail extends AiChatHistoryItem {
  messages: AiChatHistoryMessage[];
}

/** 历史会话分页列表（GET /ai-chat/history 的 data） */
export interface AiChatHistoryList {
  items: AiChatHistoryItem[];
  total: number;
  page: number;
  pageSize: number;
}

/** 拉取历史会话分页列表（updated_at 倒序，仅当前用户 active 会话） */
export async function listAiChatHistory(
  page = 1,
  pageSize = 20,
): Promise<AiChatHistoryList> {
  const params = new URLSearchParams({
    page: String(page),
    pageSize: String(pageSize),
  });
  return request<AiChatHistoryList>(`/ai-chat/history?${params.toString()}`);
}

/** 拉取单个历史会话详情（含全部消息，seq 升序） */
export async function getAiChatHistoryDetail(
  id: string,
): Promise<AiChatHistoryDetail> {
  return request<AiChatHistoryDetail>(
    `/ai-chat/history/${encodeURIComponent(id)}`,
  );
}

/** 删除单个历史会话 */
export async function deleteAiChatHistory(id: string): Promise<{ id: string }> {
  return request<{ id: string }>(`/ai-chat/history/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}
