import { useCallback, useEffect, useState } from "react";
import { Loader2, Save, Trash2, Wand2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import { gradingFetch } from "@/services/gradingApi";
import {
  type LayoutTemplateDetail,
  type LayoutTemplateMeta,
} from "./layoutTemplateUtils";

type Mode = "save" | "apply";

type Props = {
  open: boolean;
  mode: Mode;
  saving?: boolean;
  onOpenChange: (open: boolean) => void;
  /** 保存：由父级把当前布局页发给后端（走 layout-templates POST） */
  onSave: (payload: {
    name: string;
    subject: string;
    class_id: string;
  }) => Promise<void> | void;
  /** 套用：由父级把模板套到当前考试并走 confirm_reference_layout 确认流 */
  onApply: (template: LayoutTemplateDetail) => Promise<void> | void;
};

async function listLayoutTemplates(): Promise<LayoutTemplateMeta[]> {
  const result = await gradingFetch<{ data: LayoutTemplateMeta[] }>(
    "/layout-templates",
  );
  return (result?.data || []) as LayoutTemplateMeta[];
}

/** 保存命名布局模板（POST /layout-templates） */
export async function saveLayoutTemplate(payload: {
  name: string;
  layout: unknown;
  source_folder?: string;
  class_id?: string;
  subject?: string;
}): Promise<LayoutTemplateMeta> {
  const result = await gradingFetch<{ data: LayoutTemplateMeta }>(
    "/layout-templates",
    {
      method: "POST",
      body: {
        name: payload.name,
        layout: payload.layout,
        source_folder: payload.source_folder || "",
        class_id: payload.class_id || "",
        subject: payload.subject || "",
      },
    },
  );
  return result.data;
}

async function getLayoutTemplate(id: string): Promise<LayoutTemplateDetail> {
  const result = await gradingFetch<{ data: LayoutTemplateDetail }>(
    `/layout-templates/${encodeURIComponent(id)}`,
  );
  return result.data;
}

async function deleteLayoutTemplate(id: string): Promise<void> {
  await gradingFetch(`/layout-templates/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

function formatTime(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

/** 布局模板入口：存为模板 / 从模板应用（跨考试复用框选） */
export function LayoutTemplateDialog({
  open,
  mode,
  saving = false,
  onOpenChange,
  onSave,
  onApply,
}: Props) {
  const { t } = useLocale();
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [classId, setClassId] = useState("");
  const [rows, setRows] = useState<LayoutTemplateMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const refreshList = useCallback(async () => {
    setLoading(true);
    setListError("");
    try {
      const list = await listLayoutTemplates();
      setRows(list);
      if (list.length && !selectedId) {
        setSelectedId(list[0].id);
      }
    } catch (error: unknown) {
      setListError(
        error instanceof Error
          ? error.message
          : t("layoutTemplate.loadFailed"),
      );
    } finally {
      setLoading(false);
    }
  }, [selectedId, t]);

  useEffect(() => {
    if (!open) return;
    if (mode === "apply") {
      void refreshList();
    }
  }, [open, mode, refreshList]);

  useEffect(() => {
    if (!open) {
      setName("");
      setListError("");
      setApplyingId(null);
      setDeletingId(null);
    }
  }, [open]);

  const handleSave = async () => {
    const trimmed = name.trim();
    if (!trimmed || saving) return;
    await onSave({
      name: trimmed,
      subject: subject.trim(),
      class_id: classId.trim(),
    });
  };

  const handleApply = async (row: LayoutTemplateMeta) => {
    if (applyingId) return;
    setApplyingId(row.id);
    try {
      const detail = await getLayoutTemplate(row.id);
      await onApply(detail);
    } finally {
      setApplyingId(null);
    }
  };

  const handleDelete = async (row: LayoutTemplateMeta) => {
    if (deletingId) return;
    setDeletingId(row.id);
    try {
      await deleteLayoutTemplate(row.id);
      setRows((prev) => prev.filter((item) => item.id !== row.id));
      if (selectedId === row.id) setSelectedId(null);
    } catch (error: unknown) {
      setListError(
        error instanceof Error
          ? error.message
          : t("layoutTemplate.deleteFailed"),
      );
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {mode === "save"
              ? t("layoutTemplate.saveTitle")
              : t("layoutTemplate.applyTitle")}
          </DialogTitle>
          <DialogDescription>
            {mode === "save"
              ? t("layoutTemplate.saveDesc")
              : t("layoutTemplate.applyDesc")}
          </DialogDescription>
        </DialogHeader>

        {mode === "save" ? (
          <div className="grid gap-3 py-2">
            <div className="grid gap-1.5">
              <Label htmlFor="layout-template-name">
                {t("layoutTemplate.name")}
              </Label>
              <Input
                id="layout-template-name"
                value={name}
                maxLength={80}
                placeholder={t("layoutTemplate.namePlaceholder")}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleSave();
                }}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor="layout-template-subject">
                  {t("layoutTemplate.subject")}
                </Label>
                <Input
                  id="layout-template-subject"
                  value={subject}
                  maxLength={40}
                  placeholder={t("layoutTemplate.optional")}
                  onChange={(e) => setSubject(e.target.value)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="layout-template-class">
                  {t("layoutTemplate.classId")}
                </Label>
                <Input
                  id="layout-template-class"
                  value={classId}
                  maxLength={64}
                  placeholder={t("layoutTemplate.optional")}
                  onChange={(e) => setClassId(e.target.value)}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="grid gap-2 py-2">
            {loading ? (
              <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("layoutTemplate.loading")}
              </div>
            ) : rows.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                {t("layoutTemplate.listEmpty")}
              </div>
            ) : (
              <ScrollArea className="h-64 rounded-md border">
                <ul className="divide-y">
                  {rows.map((row) => (
                    <li
                      key={row.id}
                      className={cn(
                        "flex items-start gap-2 px-3 py-2.5",
                        selectedId === row.id && "bg-primary/5",
                      )}
                    >
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        onClick={() => setSelectedId(row.id)}
                        onDoubleClick={() => void handleApply(row)}
                      >
                        <div className="truncate text-sm font-medium">
                          {row.name}
                        </div>
                        <div className="mt-0.5 truncate text-xs text-muted-foreground">
                          {[
                            row.subject || "",
                            row.class_id || "",
                            row.source_folder || "",
                            formatTime(row.updated_at || row.created_at),
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </div>
                      </button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                        title={t("layoutTemplate.delete")}
                        disabled={Boolean(deletingId)}
                        onClick={() => void handleDelete(row)}
                      >
                        {deletingId === row.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </Button>
                    </li>
                  ))}
                </ul>
              </ScrollArea>
            )}
            {listError ? (
              <div className="text-xs text-destructive">{listError}</div>
            ) : null}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={saving || Boolean(applyingId)}
          >
            {t("common.cancel")}
          </Button>
          {mode === "save" ? (
            <Button
              onClick={() => void handleSave()}
              disabled={saving || !name.trim()}
              className="gap-2"
            >
              {saving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              {saving ? t("layoutTemplate.saving") : t("layoutTemplate.save")}
            </Button>
          ) : (
            <Button
              onClick={() => {
                const row = rows.find((item) => item.id === selectedId);
                if (row) void handleApply(row);
              }}
              disabled={!selectedId || Boolean(applyingId)}
              className="gap-2"
            >
              {applyingId ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Wand2 className="h-4 w-4" />
              )}
              {applyingId
                ? t("layoutTemplate.applying")
                : t("layoutTemplate.apply")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export type { LayoutTemplateDetail, LayoutTemplateMeta };
