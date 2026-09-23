import {
  useState,
  useRef,
  useEffect,
  useLayoutEffect,
  useCallback,
  useMemo,
  type ReactNode,
} from "react";
import { X, Send, Sparkles, Trash2, History, ArrowLeft } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import DOMPurify from "dompurify";
import { normalizeChatMathText } from "@/utils/chatMathFormat";
import { useProjectBranding } from "@/contexts/ProjectBrandingContext";
import { BrandLogo } from "@/components/BrandLogo";
import { API_PREFIX } from "@/config/api";
import { getAuthToken } from "@/services/api";
import { useLocale } from "@/contexts/LocaleContext";
import { getDictionary } from "@/i18n";
import { CHAT_NAV_IDS, CHAT_QUICK_COUNTS } from "@/i18n/locales/modules/chat";
import {
  AI_AUTO_REPORT_CHECK_EVENT,
  consumeAutoReport,
  fetchPendingAutoReports,
  streamAutoReport,
  type AutoReportPending,
} from "@/services/aiAutoReportApi";
import {
  listAiChatHistory,
  getAiChatHistoryDetail,
  deleteAiChatHistory,
} from "@/services/aiChatHistoryApi";

import {
  type DataCard,
  type StudentCardData,
  type KnowledgeCardData,
  type ClassOverviewData,
  type WrongQuestionData,
  type QuestionListData,
  StudentCard,
  StudentListCard,
  KnowledgeCard,
  KnowledgeListCard,
  ClassOverviewCard,
  WrongQuestionsCard,
  QuestionListCard,
  ToolCallingSkeleton,
} from "@/components/chat-cards";
import { AIGeneratedBadge } from "@/components/common/AIGeneratedBadge";

type Msg = { role: "user" | "assistant"; content: string };

/** 兼容旧版 AI 跳转名与别名（后端/历史消息可能仍为中文） */
const NAV_ALIASES: Record<string, string> = {
  班级仪表盘: "class-dashboard",
  学生名单: "class-students",
  班级画像: "analytics-portrait",
  智能复习: "ai-review",
  历史批改: "grading-errors",
  智能生成: "prep-compose",
  知识图谱: "class-knowledge",
  试题分析: "analytics-questions",
  对比分析: "analytics-compare",
};

function buildLabelToNavId(): Record<string, string> {
  const map: Record<string, string> = {};
  const zhDict = getDictionary("zh");
  const enDict = getDictionary("en");
  for (const navId of CHAT_NAV_IDS) {
    const zhLabel = zhDict[`nav.${navId}`];
    const enLabel = enDict[`nav.${navId}`];
    if (zhLabel) map[zhLabel] = navId;
    if (enLabel) map[enLabel] = navId;
  }
  Object.entries(NAV_ALIASES).forEach(([label, id]) => {
    map[label] = id;
  });
  return map;
}

const LABEL_TO_NAV_ID = buildLabelToNavId();

const AUTO_REPORT_HEADER_ZH = "【自动生成】";

const CHAT_URL = `${API_PREFIX}/ai-chat`;

function getQuickQuestionKeys(navId: string): string[] {
  const id = navId in CHAT_QUICK_COUNTS ? navId : "home";
  const count = CHAT_QUICK_COUNTS[id];
  return Array.from({ length: count }, (_, i) => `chat.quick.${id}.${i}`);
}

/* ── Parse content into segments (text + cards) ── */
function parseContent(
  text: string,
): Array<{ kind: "text"; value: string } | { kind: "card"; card: DataCard }> {
  const segments: Array<
    { kind: "text"; value: string } | { kind: "card"; card: DataCard }
  > = [];
  const regex = /```datacard\s*\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        kind: "text",
        value: text.slice(lastIndex, match.index),
      });
    }
    try {
      const card = JSON.parse(match[1].trim()) as DataCard;
      segments.push({ kind: "card", card });
    } catch {
      segments.push({ kind: "text", value: match[0] });
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    segments.push({ kind: "text", value: text.slice(lastIndex) });
  }
  return segments;
}

/* ── Render a data card ── */
function DataCardRenderer({
  card,
  onNavigate,
}: {
  card: DataCard;
  onNavigate?: (id: string) => void;
}) {
  switch (card.type) {
    case "student":
      return (
        <StudentCard
          data={card.data as StudentCardData}
          onNavigate={onNavigate}
        />
      );
    case "knowledge":
      return (
        <KnowledgeCard
          data={card.data as KnowledgeCardData}
          onNavigate={onNavigate}
        />
      );
    case "class_overview":
      return (
        <ClassOverviewCard
          data={card.data as ClassOverviewData}
          onNavigate={onNavigate}
        />
      );
    case "wrong_questions":
      return (
        <WrongQuestionsCard
          data={card.data as { questions: WrongQuestionData[] }}
          onNavigate={onNavigate}
        />
      );
    case "question_list":
      return (
        <QuestionListCard
          data={card.data as QuestionListData}
          onNavigate={onNavigate}
        />
      );
    default:
      return null;
  }
}

/* ── simple markdown renderer（含数学符号规范化） ── */
function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (ch) =>
    ch === "&"
      ? "&amp;"
      : ch === "<"
        ? "&lt;"
        : ch === ">"
          ? "&gt;"
          : ch === '"'
            ? "&quot;"
            : "&#39;",
  );
}

function renderMarkdown(text: string) {
  const normalized = normalizeChatMathText(text);
  const html = normalized
    .replace(/\[\[跳转:(.*?)\]\]/g, (_match, label: string) => {
      const safe = escapeHtml(label);
      return `<button class="nav-jump-btn" data-nav-label="${safe}">${safe} →</button>`;
    })
    .replace(/^####\s*(.+)$/gm, '<div class="font-semibold mt-2 mb-1">$1</div>')
    .replace(/^###\s*(.+)$/gm, '<div class="font-semibold mt-2 mb-1">$1</div>')
    .replace(
      /^##\s*(.+)$/gm,
      '<div class="font-semibold mt-2.5 mb-1 text-[15px]">$1</div>',
    )
    .replace(/^#\s*(.+)$/gm, '<div class="font-bold mt-2.5 mb-1">$1</div>')
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/^\- (.+)$/gm, "<li>$1</li>")
    .replace(/^(\d+)\. (.+)$/gm, "<li>$2</li>")
    .replace(
      /(<li>.*<\/li>\n?)+/g,
      (m) => `<ul class="list-disc pl-4 space-y-0.5">${m}</ul>`,
    )
    .replace(/\n/g, "<br/>");
  // 白名单净化：仅保留 markdown 渲染用到的安全标签与 [[跳转:]] 所需元素，杜绝任意 HTML / 事件属性注入
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ["button", "div", "strong", "li", "ul", "br"],
    ALLOWED_ATTR: ["class", "data-nav-label"],
  });
}

const CHAT_PANEL_CLOSE_MS = 280;

/** 与项目 Header / Sidebar 一致的品牌头像 */
function BrandAvatar({ className }: { className?: string }) {
  return (
    <BrandLogo
      className={cn("rounded-lg", className)}
      alt=""
    />
  );
}

/** 历史时间格式化：YYYY-MM-DD HH:mm */
function formatHistoryTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return iso;
  }
}

/** AI 助教历史对话面板（只读浏览 + 删除；与当前 localStorage 会话完全独立） */
function AiChatHistoryPanel({
  renderContent,
}: {
  renderContent: (content: string) => ReactNode;
}) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["ai-chat-history", "list"],
    queryFn: () => listAiChatHistory(1, 20),
    enabled: selectedId === null,
    retry: false,
    staleTime: 30_000,
  });

  const detailQuery = useQuery({
    queryKey: ["ai-chat-history", "detail", selectedId],
    queryFn: () => getAiChatHistoryDetail(selectedId as string),
    enabled: selectedId !== null,
    retry: false,
  });

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await deleteAiChatHistory(id);
        toast.success(t("chat.history.deleteSuccess"));
        if (selectedId === id) setSelectedId(null);
        queryClient.invalidateQueries({
          queryKey: ["ai-chat-history", "list"],
        });
      } catch {
        toast.error(t("chat.requestFailed"));
      }
    },
    [queryClient, selectedId, t],
  );

  const renderList = () => {
    if (listQuery.isLoading) {
      return (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("chat.history.loading")}
        </div>
      );
    }
    if (listQuery.isError) {
      return (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("chat.history.error")}
        </div>
      );
    }
    const items = listQuery.data?.items ?? [];
    if (items.length === 0) {
      return (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("chat.history.empty")}
        </div>
      );
    }
    return (
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.id}
            className="group flex items-center gap-1 rounded-lg border border-border px-2 py-2 hover:bg-secondary/40"
          >
            <button
              type="button"
              className="min-w-0 flex-1 px-1 text-left"
              onClick={() => setSelectedId(item.id)}
            >
              <p className="truncate text-sm font-medium text-foreground">
                {item.title || t("chat.title")}
              </p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {t("chat.history.messageCount", { count: item.message_count })}{" "}
                · {formatHistoryTime(item.updated_at)}
              </p>
            </button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                  aria-label={t("chat.history.deleteTitle")}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    {t("chat.history.deleteTitle")}
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    {t("chat.history.deleteDesc")}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
                  <AlertDialogAction onClick={() => void handleDelete(item.id)}>
                    {t("chat.history.deleteConfirm")}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        ))}
      </div>
    );
  };

  const renderDetail = () => {
    if (detailQuery.isLoading) {
      return (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("chat.history.loading")}
        </div>
      );
    }
    if (detailQuery.isError || !detailQuery.data) {
      return (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("chat.history.error")}
        </div>
      );
    }
    const detail = detailQuery.data;
    if (detail.messages.length === 0) {
      return (
        <div className="py-8 text-center text-sm text-muted-foreground">
          {t("chat.history.empty")}
        </div>
      );
    }
    return (
      <div className="space-y-3.5">
        {detail.messages.map((m) => (
          <div
            key={m.id}
            className={cn(
              "flex gap-2.5",
              m.role === "user" ? "justify-end" : "justify-start",
            )}
          >
            {m.role === "assistant" && (
              <BrandAvatar className="w-7 h-7 text-[10px] mt-0.5" />
            )}
            <div
              className={cn(
                "rounded-lg px-3.5 py-2.5 text-sm leading-relaxed",
                m.role === "user"
                  ? "ai-chat-user-bubble text-primary-foreground rounded-tr-sm max-w-[82%]"
                  : "ai-chat-assistant-bubble rounded-tl-sm max-w-[calc(100%-2.25rem)]",
              )}
            >
              {m.role === "assistant" && (
                <div className="mb-1.5">
                  <AIGeneratedBadge />
                </div>
              )}
              {m.role === "assistant" ? renderContent(m.content) : m.content}
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col" data-testid="ai-chat-history-panel">
      <div className="flex shrink-0 items-center gap-1 border-b border-border px-2 py-2">
        {selectedId !== null ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1 rounded-md px-2 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setSelectedId(null)}
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            {t("chat.history.backToList")}
          </Button>
        ) : (
          <span className="px-1 text-sm font-semibold text-foreground">
            {t("chat.history.title")}
          </span>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 py-3">
        {selectedId === null ? renderList() : renderDetail()}
      </div>
    </div>
  );
}

export function FloatingChat({
  activeNavId = "home",
  onNavigate,
}: {
  activeNavId?: string;
  onNavigate?: (navId: string) => void;
}) {
  const { projectName } = useProjectBranding();
  const { t } = useLocale();
  const zhDict = useMemo(() => getDictionary("zh"), []);
  const apiModuleContext = zhDict[`nav.${activeNavId}`] || zhDict["nav.home"];
  const autoReportHeader = t("chat.autoReportHeader");
  const STORAGE_KEY = "ai-tutor-messages";
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const [messages, setMessages] = useState<Msg[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [contentReady, setContentReady] = useState(false);
  const processedReportIdsRef = useRef<Set<string>>(new Set());
  const autoReportBusyRef = useRef(false);

  const scrollToBottomInstant = useCallback(() => {
    const container = scrollContainerRef.current;
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
    messagesEndRef.current?.scrollIntoView({ block: "end", behavior: "auto" });
  }, []);

  const openPanel = useCallback(() => {
    setClosing(false);
    setContentReady(false);
    setShowHistory(false);
    setOpen(true);
  }, []);

  const closePanel = useCallback(() => {
    setClosing(true);
    setContentReady(false);
    setShowHistory(false);
    window.setTimeout(() => {
      setOpen(false);
      setClosing(false);
    }, CHAT_PANEL_CLOSE_MS);
  }, []);

  useEffect(() => {
    if (open && !closing) {
      const t = window.setTimeout(() => inputRef.current?.focus(), 360);
      return () => window.clearTimeout(t);
    }
  }, [open, closing]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch {}
  }, [messages]);

  // 打开时立即定位到底部，避免从顶部滑到底部的闪动
  useLayoutEffect(() => {
    if (!open || closing) {
      setContentReady(false);
      return;
    }
    const snap = () => scrollToBottomInstant();
    snap();
    requestAnimationFrame(() => {
      snap();
      requestAnimationFrame(() => {
        snap();
        setContentReady(true);
      });
    });
  }, [open, closing, messages, isLoading, scrollToBottomInstant]);

  // 流式输出过程中保持贴底
  useEffect(() => {
    if (!open || closing || !contentReady) return;
    scrollToBottomInstant();
  }, [open, closing, contentReady, messages, isLoading, scrollToBottomInstant]);

  const handleCardNavigate = useCallback(
    (navId: string) => {
      if (onNavigate) {
        onNavigate(navId);
        const label = t(`nav.${navId}`);
        toast.success(t("chat.navSuccess", { label }));
      }
    },
    [onNavigate, t],
  );

  const handleAutoReport = useCallback(
    async (report: AutoReportPending) => {
      if (
        processedReportIdsRef.current.has(report.id) ||
        autoReportBusyRef.current
      )
        return;
      processedReportIdsRef.current.add(report.id);
      autoReportBusyRef.current = true;
      openPanel();
      setIsLoading(true);
      let assistantSoFar = `${autoReportHeader}\n\n`;
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: assistantSoFar },
      ]);
      try {
        await streamAutoReport(report.id, (chunk) => {
          assistantSoFar += chunk;
          const snap = assistantSoFar;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "assistant") {
              return prev.map((m, i) =>
                i === prev.length - 1 ? { ...m, content: snap } : m,
              );
            }
            return [...prev, { role: "assistant", content: snap }];
          });
        });
        await consumeAutoReport(report.id);
      } catch (e: unknown) {
        processedReportIdsRef.current.delete(report.id);
        const msg = e instanceof Error ? e.message : t("chat.autoReportFailed");
        toast.error(msg);
      } finally {
        setIsLoading(false);
        autoReportBusyRef.current = false;
      }
    },
    [openPanel, autoReportHeader, t],
  );

  const pollPendingAutoReports = useCallback(async () => {
    if (autoReportBusyRef.current) return;
    try {
      const token = await getAuthToken();
      if (!token) return;
      const reports = await fetchPendingAutoReports();
      for (const report of reports) {
        if (processedReportIdsRef.current.has(report.id)) continue;
        await handleAutoReport(report);
        break;
      }
    } catch (e) {
      console.warn("[ai_auto_report] poll failed", e);
    }
  }, [handleAutoReport]);

  useEffect(() => {
    if (!open) return;
    pollPendingAutoReports();
    const timer = window.setInterval(pollPendingAutoReports, 3000);
    const onCheck = () => {
      void pollPendingAutoReports();
    };
    window.addEventListener(AI_AUTO_REPORT_CHECK_EVENT, onCheck);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(AI_AUTO_REPORT_CHECK_EVENT, onCheck);
    };
  }, [open, pollPendingAutoReports]);

  const streamChat = useCallback(
    async (allMessages: Msg[], moduleContext: string) => {
      const token = await getAuthToken();
      if (!token) throw new Error(t("chat.loginRequired"));

      const resp = await fetch(CHAT_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          messages: allMessages,
          currentModule: moduleContext,
        }),
      });

      if (!resp.ok) {
        const err = await resp
          .json()
          .catch(() => ({ detail: t("chat.requestFailed") }));
        throw new Error(err.detail || err.error || `HTTP ${resp.status}`);
      }
      if (!resp.body) throw new Error("No stream body");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assistantSoFar = "";

      const upsert = (chunk: string) => {
        assistantSoFar += chunk;
        const snap = assistantSoFar;
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant") {
            return prev.map((m, i) =>
              i === prev.length - 1 ? { ...m, content: snap } : m,
            );
          }
          return [...prev, { role: "assistant", content: snap }];
        });
      };

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
            if (c) upsert(c);
          } catch {
            buffer = line + "\n" + buffer;
            break;
          }
        }
      }
    },
    [t],
  );

  const send = async (text: string) => {
    if (!text.trim() || isLoading) return;
    const userMsg: Msg = { role: "user", content: text.trim() };
    const updated = [...messages, userMsg];
    setMessages(updated);
    setInput("");
    setIsLoading(true);
    try {
      await streamChat(updated, apiModuleContext);
    } catch (e: any) {
      toast.error(e.message || t("chat.replyFailed"));
    } finally {
      setIsLoading(false);
    }
  };

  const quickQuestionKeys = getQuickQuestionKeys(activeNavId);
  const quickQuestions = quickQuestionKeys.map((key) => t(key));
  const showQuick = messages.length === 0 && !isLoading;

  const assistantProseClass =
    "prose prose-sm max-w-none text-foreground/90 [&_strong]:text-foreground [&_ul]:my-1.5 [&_li]:my-0.5 [&_.nav-jump-btn]:inline-flex [&_.nav-jump-btn]:items-center [&_.nav-jump-btn]:gap-1 [&_.nav-jump-btn]:text-[11px] [&_.nav-jump-btn]:font-medium [&_.nav-jump-btn]:text-primary [&_.nav-jump-btn]:bg-primary/10 [&_.nav-jump-btn]:px-2.5 [&_.nav-jump-btn]:py-1 [&_.nav-jump-btn]:rounded-md [&_.nav-jump-btn]:border [&_.nav-jump-btn]:border-primary/20 [&_.nav-jump-btn]:cursor-pointer [&_.nav-jump-btn]:transition-colors hover:[&_.nav-jump-btn]:bg-primary/15 [&_.nav-jump-btn]:mx-0.5";

  /* ── Render assistant message with cards ── */
  const renderAssistantContent = (content: string) => {
    let body = content;
    let showAutoHeader = false;
    if (
      body.startsWith(AUTO_REPORT_HEADER_ZH) ||
      body.startsWith(autoReportHeader)
    ) {
      showAutoHeader = true;
      const headerLen = body.startsWith(AUTO_REPORT_HEADER_ZH)
        ? AUTO_REPORT_HEADER_ZH.length
        : autoReportHeader.length;
      body = body.slice(headerLen).replace(/^\s*\n?/, "");
    }
    const segments = parseContent(body);
    return (
      <>
        {showAutoHeader && (
          <p className="font-semibold text-primary text-[13px] mb-2 leading-snug">
            {autoReportHeader}
          </p>
        )}
        {segments.map((seg, i) => {
          if (seg.kind === "card") {
            return (
              <DataCardRenderer
                key={i}
                card={seg.card}
                onNavigate={handleCardNavigate}
              />
            );
          }
          const html = renderMarkdown(seg.value);
          if (!html.replace(/<br\s*\/?>/gi, "").trim()) return null;
          return (
            <div
              key={i}
              className={assistantProseClass}
              dangerouslySetInnerHTML={{ __html: html }}
              onClick={(e) => {
                const target = e.target as HTMLElement;
                if (target.classList.contains("nav-jump-btn")) {
                  const label = target.getAttribute("data-nav-label");
                  if (label) {
                    const navId = LABEL_TO_NAV_ID[label];
                    if (navId && onNavigate) {
                      onNavigate(navId);
                      toast.success(t("chat.navSuccess", { label }));
                    } else {
                      toast.error(t("chat.navNotFound", { label }));
                    }
                  }
                }
              }}
            />
          );
        })}
      </>
    );
  };

  const panelVisible = open || closing;

  return (
    <>
      {/* 悬浮入口 */}
      {!panelVisible && (
        <button
          onClick={openPanel}
          className="ai-chat-fab fixed bottom-6 right-6 z-50 w-[3.75rem] h-[3.75rem] rounded-2xl text-primary-foreground flex flex-col items-center justify-center gap-0.5 hover:scale-105 active:scale-95 transition-transform duration-200 group"
          aria-label={t("chat.fab.aria")}
        >
          <Sparkles className="w-5 h-5 drop-shadow-sm group-hover:rotate-12 transition-transform duration-300" />
          <span className="text-[9px] font-semibold tracking-wide opacity-90">
            AI
          </span>
        </button>
      )}

      {panelVisible && (
        <div
          className={cn(
            "ai-chat-surface fixed bottom-6 right-6 z-50 w-[min(100vw-2rem,400px)] h-[min(100vh-5rem,600px)] rounded-xl border border-border bg-card flex flex-col overflow-hidden pointer-events-auto shadow-card",
            closing ? "ai-chat-panel-exit" : "ai-chat-panel-enter",
          )}
          role="dialog"
          aria-label={t("chat.dialog.aria")}
          aria-modal="false"
        >
          {/* Header */}
          <div className="shrink-0 border-b border-border bg-secondary/60 px-4 py-3.5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <BrandAvatar className="w-9 h-9 rounded-xl text-sm" />
                <div className="min-w-0">
                  <h2 className="font-bold text-[15px] leading-tight text-foreground">
                    {t("chat.title")}
                  </h2>
                  <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
                    {t("app.tagline")}
                  </p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className={cn(
                  "h-8 w-8 shrink-0 rounded-lg text-muted-foreground hover:text-foreground hover:bg-background",
                  showHistory && "bg-secondary text-foreground",
                )}
                onClick={() => setShowHistory((v) => !v)}
                aria-label={t("chat.history.entry")}
              >
                <History className="w-4 h-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 rounded-lg text-muted-foreground hover:text-foreground hover:bg-background"
                onClick={closePanel}
                aria-label={t("chat.close")}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
          </div>

          {/* Messages */}
          {showHistory ? (
            <div className="flex-1 min-h-0 bg-background">
              <AiChatHistoryPanel renderContent={renderAssistantContent} />
            </div>
          ) : (
            <div
              ref={scrollContainerRef}
              className={cn(
                "flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 py-4 bg-background",
                !contentReady && "opacity-0",
              )}
            >
              <div className="space-y-3.5">
                {showQuick && (
                  <div className="space-y-3">
                    <div className="flex gap-2.5 items-start">
                      <BrandAvatar className="w-7 h-7 text-[10px] mt-0.5" />
                      <div className="ai-chat-assistant-bubble rounded-lg rounded-tl-sm px-3.5 py-2.5 text-sm leading-relaxed max-w-[88%]">
                        <p className="text-foreground">
                          {t("chat.greeting", { projectName })}
                        </p>
                        <p className="text-muted-foreground text-[13px] mt-1.5">
                          {t("chat.greetingHint")}
                        </p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2 pl-9">
                      {quickQuestions.map((q) => (
                        <button
                          key={q}
                          onClick={() => send(q)}
                          className="ai-chat-quick-chip text-xs px-3 py-1.5 rounded-md text-foreground/85"
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {messages.map((m, i) => (
                  <div
                    key={i}
                    className={cn(
                      "flex gap-2.5",
                      m.role === "user" ? "justify-end" : "justify-start",
                    )}
                  >
                    {m.role === "assistant" && (
                      <BrandAvatar className="w-7 h-7 text-[10px] mt-0.5" />
                    )}
                    <div
                      className={cn(
                        "rounded-lg px-3.5 py-2.5 text-sm leading-relaxed",
                        m.role === "user"
                          ? "ai-chat-user-bubble text-primary-foreground rounded-tr-sm max-w-[82%]"
                          : "ai-chat-assistant-bubble rounded-tl-sm max-w-[calc(100%-2.25rem)]",
                      )}
                    >
                      {m.role === "assistant" && (
                        <div className="mb-1.5">
                          <AIGeneratedBadge />
                        </div>
                      )}
                      {m.role === "assistant"
                        ? renderAssistantContent(m.content)
                        : m.content}
                    </div>
                  </div>
                ))}

                {isLoading &&
                  messages[messages.length - 1]?.role !== "assistant" && (
                    <div className="flex gap-2.5 justify-start">
                      <BrandAvatar className="w-7 h-7 text-[10px] mt-0.5" />
                      <div className="ai-chat-assistant-bubble rounded-lg rounded-tl-sm px-3.5 py-2.5 text-sm max-w-[calc(100%-2.25rem)]">
                        <ToolCallingSkeleton />
                      </div>
                    </div>
                  )}
                <div
                  ref={messagesEndRef}
                  className="h-px shrink-0"
                  aria-hidden
                />
              </div>
            </div>
          )}

          {/* Input */}
          {showHistory ? (
            <div className="shrink-0 border-t border-border bg-card px-3 py-3">
              <Button
                variant="ghost"
                size="sm"
                className="h-9 w-full rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary"
                onClick={() => setShowHistory(false)}
              >
                <ArrowLeft className="w-4 h-4 mr-1" />
                {t("chat.history.back")}
              </Button>
            </div>
          ) : (
            <div className="shrink-0 border-t border-border bg-card px-3 py-3">
              <div className="ai-chat-input-shell flex items-center gap-1.5 rounded-lg px-2 py-1">
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                      disabled={messages.length === 0}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>
                        {t("chat.clearTitle")}
                      </AlertDialogTitle>
                      <AlertDialogDescription>
                        {t("chat.clearDesc")}
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>
                        {t("common.cancel")}
                      </AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => {
                          setMessages([]);
                          localStorage.removeItem(STORAGE_KEY);
                        }}
                      >
                        {t("chat.clearConfirm")}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
                <input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) =>
                    e.key === "Enter" &&
                    !e.shiftKey &&
                    !isLoading &&
                    send(input)
                  }
                  placeholder={
                    isLoading
                      ? t("chat.inputLoading")
                      : t("chat.inputPlaceholder")
                  }
                  className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground px-1 py-2"
                />
                <Button
                  size="icon"
                  className={cn(
                    "h-8 w-8 shrink-0 rounded-md transition-colors",
                    input.trim() && !isLoading
                      ? "bg-primary text-primary-foreground hover:bg-primary/90"
                      : "bg-muted text-muted-foreground",
                  )}
                  disabled={!input.trim() || isLoading}
                  onClick={() => send(input)}
                >
                  <Send className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
