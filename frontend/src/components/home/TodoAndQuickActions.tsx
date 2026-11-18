import { useEffect, useMemo, useState } from "react";
import {
  FileText,
  BarChart3,
  Presentation,
  BookOpen,
  Plus,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { request } from "@/services/api";
import { useLocale } from "@/contexts/LocaleContext";

interface TodoAndQuickActionsProps {
  selectedSubject: string;
  selectedClass: string;
  onNavChange: (id: string) => void;
  onScrollToGrading?: () => void;
}

type TodoPriority = "urgent" | "priority" | "normal";

const quickActionDefs = [
  {
    icon: FileText,
    labelKey: "home.quickActions.grade",
    // 跳「开始批改」页（1026：原来 __scroll_grading 只在首页滚到拍照区，
    // 看着像没反应；「去批改」就该进开始批改页）
    navId: "grading-start",
  },
  {
    icon: BarChart3,
    labelKey: "home.quickActions.analyze",
    navId: "analytics-portrait",
  },
  {
    icon: Presentation,
    labelKey: "home.quickActions.teach",
    navId: "ai-review",
  },
  { icon: BookOpen, labelKey: "home.quickActions.prep", navId: "prep-compose" },
];

export function TodoAndQuickActions({
  selectedSubject,
  selectedClass,
  onNavChange,
  onScrollToGrading,
}: TodoAndQuickActionsProps) {
  const { t, locale } = useLocale();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<
    Array<{
      id: string;
      title: string;
      content?: string | null;
      remind_at?: string | null;
      created_at: string;
    }>
  >([]);
  const [addOpen, setAddOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newRemindAt, setNewRemindAt] = useState("");
  const [detailOpen, setDetailOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [editRemindAt, setEditRemindAt] = useState("");

  const priorityStyles = useMemo(
    () => ({
      urgent: {
        dot: "bg-destructive",
        label: t("home.todo.priority.urgent"),
        labelColor: "text-destructive",
      },
      priority: {
        dot: "bg-orange-500",
        label: t("home.todo.priority.priority"),
        labelColor: "text-orange-600",
      },
      normal: {
        dot: "bg-primary",
        label: t("home.todo.priority.normal"),
        labelColor: "text-primary",
      },
    }),
    [t, locale],
  );

  const quickActions = useMemo(
    () => quickActionDefs.map((qa) => ({ ...qa, label: t(qa.labelKey) })),
    [t, locale],
  );

  const toDatetimeLocalValue = (iso?: string | null): string => {
    const s = (iso || "").trim();
    if (!s) return "";
    const hasTz = /([zZ]|[+-]\d{2}:\d{2})$/.test(s);
    const d = new Date(hasTz ? s : `${s}Z`);
    if (!Number.isFinite(d.getTime())) return "";
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const toLocaleDisplay = (iso?: string | null): string => {
    const s = (iso || "").trim();
    if (!s) return "";
    const hasTz = /([zZ]|[+-]\d{2}:\d{2})$/.test(s);
    const d = new Date(hasTz ? s : `${s}Z`);
    if (!Number.isFinite(d.getTime())) return "";
    return d.toLocaleString();
  };

  const loadTodos = async () => {
    setLoading(true);
    try {
      const data = await request<Array<any>>("/todos");
      setItems(
        (data || []).map((d) => ({
          id: String(d.id),
          title: String(d.title || ""),
          content: d.content ?? null,
          remind_at: d.remind_at ?? null,
          created_at: String(d.created_at || ""),
        })),
      );
    } catch (e: any) {
      toast.error(e?.message ? String(e.message) : t("home.todo.loadFailed"));
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadTodos();
  }, []);

  const createTodo = async () => {
    const title = (newTitle || "").trim();
    if (!title) {
      toast.error(t("home.todo.nameRequired"));
      return;
    }
    let remind_at: string | null = null;
    if ((newRemindAt || "").trim()) {
      const dt = new Date(newRemindAt);
      if (!Number.isFinite(dt.getTime())) {
        toast.error(t("home.todo.invalidRemindTime"));
        return;
      }
      remind_at = dt.toISOString();
    }
    setLoading(true);
    try {
      await request<any>("/todos", {
        method: "POST",
        body: JSON.stringify({
          title,
          content: (newContent || "").trim() || null,
          remind_at,
        }),
      });
      toast.success(t("home.todo.created"));
      setAddOpen(false);
      setNewTitle("");
      setNewContent("");
      setNewRemindAt("");
      await loadTodos();
    } catch (e: any) {
      toast.error(e?.message ? String(e.message) : t("home.todo.createFailed"));
    } finally {
      setLoading(false);
    }
  };

  const topTodos = useMemo(() => items.slice(0, 6), [items]);

  const openDetail = (todo: {
    id: string;
    title: string;
    content?: string | null;
    remind_at?: string | null;
    created_at: string;
  }) => {
    setActiveId(todo.id);
    setEditTitle(todo.title || "");
    setEditContent((todo.content ?? "") as string);
    setEditRemindAt(toDatetimeLocalValue(todo.remind_at ?? null));
    setDetailOpen(true);
  };

  const saveTodo = async () => {
    if (!activeId) return;
    const title = (editTitle || "").trim();
    if (!title) {
      toast.error(t("home.todo.nameRequired"));
      return;
    }
    let remind_at: string | null = null;
    if ((editRemindAt || "").trim()) {
      const dt = new Date(editRemindAt);
      if (!Number.isFinite(dt.getTime())) {
        toast.error(t("home.todo.invalidRemindTime"));
        return;
      }
      remind_at = dt.toISOString();
    }
    setLoading(true);
    try {
      await request<any>(`/todos/${activeId}`, {
        method: "PATCH",
        body: JSON.stringify({
          title,
          content: (editContent || "").trim() || null,
          remind_at,
        }),
      });
      toast.success(t("home.todo.saved"));
      setDetailOpen(false);
      setActiveId(null);
      await loadTodos();
    } catch (e: any) {
      toast.error(e?.message ? String(e.message) : t("home.todo.saveFailed"));
    } finally {
      setLoading(false);
    }
  };

  const deleteTodo = async (id: string) => {
    if (!id) return;
    if (!window.confirm(t("home.todo.deleteConfirm"))) return;
    setLoading(true);
    try {
      await request<any>(`/todos/${id}`, { method: "DELETE" });
      toast.success(t("home.todo.deleted"));
      if (activeId === id) {
        setDetailOpen(false);
        setActiveId(null);
      }
      await loadTodos();
    } catch (e: any) {
      toast.error(e?.message ? String(e.message) : t("home.todo.deleteFailed"));
    } finally {
      setLoading(false);
    }
  };

  const handleAction = (navId?: string) => {
    if (!navId) return;
    if (navId === "__scroll_grading") {
      onScrollToGrading?.();
    } else {
      onNavChange(navId);
    }
  };

  return (
    <div className="grid grid-cols-5 gap-4 animate-fade-in">
      <div className="col-span-3 rounded-xl bg-card border border-border/50 p-5 card-elevated">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-foreground">
            {t("home.todo.title")}
          </h3>
          <Button
            size="sm"
            variant="outline"
            className="h-8 text-xs gap-1"
            onClick={() => setAddOpen(true)}
          >
            <Plus className="w-3.5 h-3.5" /> {t("home.todo.add")}
          </Button>
        </div>
        <div className="space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-10 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              {t("common.loading")}
            </div>
          ) : topTodos.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">
              {t("home.todo.empty")}
            </div>
          ) : (
            topTodos.map((todo) => {
              const priority: TodoPriority = todo.remind_at
                ? "priority"
                : "normal";
              const ps = priorityStyles[priority];
              return (
                <div key={todo.id} className="flex items-start gap-3">
                  <span
                    className={cn(
                      "mt-1.5 w-2 h-2 rounded-full shrink-0",
                      ps.dot,
                    )}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span
                        className={cn("text-xs font-medium", ps.labelColor)}
                      >
                        {ps.label}
                      </span>
                    </div>
                    <p className="text-sm font-medium text-foreground">
                      {todo.title}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {todo.remind_at
                        ? t("home.todo.remindAt", {
                            time: toLocaleDisplay(todo.remind_at),
                          })
                        : t("home.todo.createdAt", {
                            time: todo.created_at
                              ? toLocaleDisplay(todo.created_at)
                              : "",
                          })}
                    </p>
                    <div className="flex gap-2 mt-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => openDetail(todo)}
                      >
                        {t("home.todo.view")}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs text-destructive hover:text-destructive"
                        onClick={() => void deleteTodo(todo.id)}
                      >
                        {t("home.todo.delete")}
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
        <Button variant="link" size="sm" className="mt-4 p-0 h-auto text-xs">
          {t("home.todo.viewAll")}
        </Button>
      </div>

      <div className="col-span-2 rounded-xl bg-card border border-border/50 p-5 card-elevated">
        <h3 className="text-base font-semibold text-foreground mb-4">
          {t("home.quickActions.title")}
        </h3>
        <div className="grid grid-cols-2 gap-3">
          {quickActions.map((qa) => (
            <button
              key={qa.labelKey}
              className="flex flex-col items-center gap-2 p-4 rounded-xl border border-border/50 hover:border-primary/30 hover:bg-primary/5 transition-all duration-200 hover-scale cursor-pointer"
              onClick={() => handleAction(qa.navId)}
            >
              <qa.icon className="w-6 h-6 text-primary" />
              <span className="text-sm font-medium text-foreground">
                {qa.label}
              </span>
            </button>
          ))}
        </div>
      </div>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("home.todo.addTitle")}</DialogTitle>
            <DialogDescription>{t("home.todo.addDesc")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-sm">{t("home.todo.nameLabel")}</Label>
              <Input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder={t("home.todo.namePlaceholder")}
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm">{t("home.todo.contentLabel")}</Label>
              <Textarea
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder={t("home.todo.contentPlaceholder")}
                className="min-h-[96px]"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm">{t("home.todo.remindLabel")}</Label>
              <Input
                type="datetime-local"
                value={newRemindAt}
                onChange={(e) => setNewRemindAt(e.target.value)}
              />
            </div>
            <div className="text-xs text-muted-foreground">
              {t("home.todo.createdAtLabel", {
                time: new Date().toLocaleString(),
              })}
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setAddOpen(false)}
              disabled={loading}
            >
              {t("common.cancel")}
            </Button>
            <Button onClick={() => void createTodo()} disabled={loading}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={detailOpen}
        onOpenChange={(o) => {
          setDetailOpen(o);
          if (!o) setActiveId(null);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("home.todo.detailTitle")}</DialogTitle>
            <DialogDescription>{t("home.todo.detailDesc")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label className="text-sm">{t("home.todo.nameLabel")}</Label>
              <Input
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                placeholder={t("home.todo.nameEditPlaceholder")}
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm">{t("home.todo.contentLabel")}</Label>
              <Textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                placeholder={t("home.todo.contentPlaceholder")}
                className="min-h-[96px]"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm">{t("home.todo.remindLabel")}</Label>
              <Input
                type="datetime-local"
                value={editRemindAt}
                onChange={(e) => setEditRemindAt(e.target.value)}
              />
            </div>
            <div className="text-xs text-muted-foreground">
              {t("home.todo.createdAtLabel", {
                time: activeId
                  ? items.find((x) => x.id === activeId)?.created_at
                    ? new Date(
                        items.find((x) => x.id === activeId)!.created_at,
                      ).toLocaleString()
                    : ""
                  : "",
              })}
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                if (activeId) void deleteTodo(activeId);
              }}
              disabled={loading || !activeId}
              className="text-destructive hover:text-destructive"
            >
              {t("home.todo.delete")}
            </Button>
            <Button
              variant="outline"
              onClick={() => setDetailOpen(false)}
              disabled={loading}
            >
              {t("home.todo.close")}
            </Button>
            <Button
              onClick={() => void saveTodo()}
              disabled={loading || !activeId}
            >
              {t("home.todo.saveChanges")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
