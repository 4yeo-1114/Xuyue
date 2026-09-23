import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { toast } from "sonner";
import {
  CheckSquare,
  Eye,
  Loader2,
  Megaphone,
  RefreshCw,
  Undo2,
  Archive,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getClassOverview, type ClassPortfolioStudent } from "@/services/wuyuApi";
import {
  listArchive,
  selectArchive,
  publishArchive,
  withdrawArchive,
  archiveToFile,
  type EvaluationArchive,
} from "@/services/archiveApi";
import { TERM_PATTERN, tierVariant, toNum } from "./portfolioShared";
import { cn } from "@/lib/utils";

interface SelectionPanelProps {
  classId: string;
}

type BadgeKind =
  | "none"
  | "draft"
  | "selected"
  | "publicity"
  | "ended"
  | "archived";

function statusBadge(
  rec: EvaluationArchive | undefined
): { kind: BadgeKind; labelKey: string } {
  if (!rec) return { kind: "none", labelKey: "archive.status.none" };
  switch (rec.status) {
    case "archived":
      return { kind: "archived", labelKey: "archive.status.archived" };
    case "publicity":
      return rec.publicity_expired
        ? { kind: "ended", labelKey: "archive.status.ended" }
        : { kind: "publicity", labelKey: "archive.status.publicity" };
    case "selected":
      return { kind: "selected", labelKey: "archive.status.selected" };
    default:
      return { kind: "draft", labelKey: "archive.status.draft" };
  }
}

/** 综评遴选面板：班级候选列表 → 勾选遴选 → 开启公示 → 成档归档 */
export function SelectionPanel({ classId }: SelectionPanelProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [term, setTerm] = useState("2025-2026-1");
  const [queryTerm, setQueryTerm] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const termValid = TERM_PATTERN.test(term.trim());

  // 候选列表：班级学生画像总览，默认按综合成长分排序
  const {
    data: overview,
    isLoading: loadingOverview,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["portfolio-class-overview", classId],
    queryFn: () => getClassOverview(classId, "total"),
    enabled: !!classId,
  });

  // 综评档案列表（当前学期）
  const { data: archives = [], isLoading: loadingArchives } = useQuery({
    queryKey: ["portfolio-archive", classId, queryTerm],
    queryFn: () => listArchive({ class_id: classId, term: queryTerm as string }),
    enabled: !!classId && !!queryTerm,
  });

  const archiveByStudent = useMemo(() => {
    const m: Record<string, EvaluationArchive> = {};
    for (const a of archives) m[a.student_id] = a;
    return m;
  }, [archives]);

  const candidates: ClassPortfolioStudent[] = overview?.students || [];

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["portfolio-archive", classId] });
  };

  // ── 遴选 ─────────────────────────────────────────
  const selectMut = useMutation({
    mutationFn: (ids: string[]) =>
      selectArchive(classId, { student_ids: ids, term: queryTerm as string }),
    onSuccess: (data) => {
      toast.success(t("archive.selection.success", { count: data.length }));
      setSelectedIds(new Set());
      invalidate();
    },
    onError: (err: any) => {
      toast.error(t("archive.selection.failed"), { description: err?.message });
    },
  });

  // ── 开启公示 ─────────────────────────────────────
  const publishMut = useMutation({
    mutationFn: (id: string) => publishArchive(id),
    onSuccess: (rec) => {
      toast.success(t("archive.publish.success"));
      invalidate();
    },
    onError: (err: any) => {
      toast.error(t("archive.publish.failed"), { description: err?.message });
    },
  });

  // ── 撤回公示 ─────────────────────────────────────
  const withdrawMut = useMutation({
    mutationFn: (id: string) => withdrawArchive(id),
    onSuccess: (rec) => {
      toast.success(t("archive.withdraw.success"));
      invalidate();
    },
    onError: (err: any) => {
      toast.error(t("archive.withdraw.failed"), { description: err?.message });
    },
  });

  // ── 成档归档 ─────────────────────────────────────
  const archiveMut = useMutation({
    mutationFn: (id: string) => archiveToFile(id),
    onSuccess: (rec) => {
      toast.success(t("archive.archive.success"));
      invalidate();
    },
    onError: (err: any) => {
      toast.error(t("archive.archive.failed"), { description: err?.message });
    },
  });

  // 可勾选的学生：未成档、未处于公示中
  const isCheckable = (studentId: string) => {
    const rec = archiveByStudent[studentId];
    if (!rec) return true;
    return rec.status === "draft" || rec.status === "selected";
  };

  const toggle = (studentId: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(studentId);
      else next.delete(studentId);
      return next;
    });
  };

  const toggleAll = () => {
    const checkable = candidates.filter((c) => isCheckable(c.student_id)).map((c) => c.student_id);
    const allChecked = checkable.length > 0 && checkable.every((id) => selectedIds.has(id));
    setSelectedIds(allChecked ? new Set() : new Set(checkable));
  };

  const handleSelect = () => {
    if (selectedIds.size === 0) {
      toast.error(t("archive.selection.empty"));
      return;
    }
    selectMut.mutate(Array.from(selectedIds));
  };

  const handleLoad = () => {
    if (!termValid) {
      toast.error(t("archive.termInvalid"));
      return;
    }
    setQueryTerm(term.trim());
  };

  const isLoading = loadingOverview || loadingArchives;

  const candidateTier = (c: ClassPortfolioStudent) => c.tier?.total || null;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* 控制区：学期 + 遴选 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">{t("archive.title")}</CardTitle>
          </div>
          <CardDescription>{t("archive.subtitle")}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
            <div className="space-y-1.5 flex-1 max-w-xs">
              <Label className="text-xs">{t("archive.term")}</Label>
              <Input
                className="h-9"
                value={term}
                onChange={(e) => setTerm(e.target.value)}
                placeholder={t("archive.termPlaceholder")}
              />
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <Button size="sm" variant="outline" onClick={handleLoad} disabled={!termValid}>
                <Eye className="w-3.5 h-3.5 mr-1" />
                {t("archive.load")}
              </Button>
              <Button size="sm" variant="outline" onClick={() => refetch()} disabled={isLoading}>
                <RefreshCw className={`w-3.5 h-3.5 mr-1 ${isLoading ? "animate-spin" : ""}`} />
                {t("archive.refresh")}
              </Button>
              <Button
                size="sm"
                onClick={handleSelect}
                disabled={!queryTerm || selectMut.isPending}
              >
                {selectMut.isPending ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
                ) : (
                  <CheckSquare className="w-3.5 h-3.5 mr-1" />
                )}
                {selectMut.isPending ? t("archive.selection.selecting") : t("archive.selection.select")}
              </Button>
            </div>
          </div>
          <div className="mt-2 text-xs text-muted-foreground">
            {t("archive.selection.hint", { count: selectedIds.size })}
          </div>
        </CardContent>
      </Card>

      {/* 候选列表 */}
      {!queryTerm ? (
        <div className="flex flex-col items-center justify-center py-16 border border-dashed rounded-lg text-muted-foreground">
          <Megaphone className="w-8 h-8 opacity-30 mb-2" />
          <p className="text-sm">{t("archive.termRequired")}</p>
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center justify-center py-16 border border-dashed rounded-lg text-muted-foreground">
          <p className="text-sm mb-2">{t("archive.loadFailed")}</p>
          <Button size="sm" variant="outline" onClick={() => refetch()}>
            {t("archive.retry")}
          </Button>
        </div>
      ) : isLoading ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin mb-2" />
          <p className="text-sm">{t("archive.loading")}</p>
        </div>
      ) : candidates.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 border border-dashed rounded-lg text-muted-foreground">
          <Users className="w-8 h-8 opacity-30 mb-2" />
          <p className="text-sm">{t("archive.candidates.empty")}</p>
        </div>
      ) : (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold">
                {t("archive.candidates.title", { count: candidates.length })}
              </CardTitle>
              <Button size="sm" variant="ghost" onClick={toggleAll}>
                {t("archive.candidates.toggleAll")}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-border/60">
              {candidates.map((c) => {
                const rec = archiveByStudent[c.student_id];
                const { kind, labelKey } = statusBadge(rec);
                const checkable = isCheckable(c.student_id);
                const checked = selectedIds.has(c.student_id);
                const tier = candidateTier(c);
                const busy = publishMut.isPending || withdrawMut.isPending || archiveMut.isPending;
                return (
                  <div
                    key={c.student_id}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3 text-sm",
                      !checkable && "opacity-80"
                    )}
                  >
                    <Checkbox
                      id={`archive-cb-${c.student_id}`}
                      checked={checkable && checked}
                      disabled={!checkable}
                      onCheckedChange={(v) => toggle(c.student_id, v === true)}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground truncate">
                          {c.name}
                        </span>
                        {tier && (
                          <Badge variant={tierVariant(tier)} className="text-[10px] px-1.5">
                            {tier}
                          </Badge>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        {c.student_number || "—"} · {t("archive.growthPoint")} {toNum(c.total_growth_point)}
                      </div>
                    </div>
                    <Badge
                      variant={
                        kind === "publicity"
                          ? "default"
                          : kind === "ended" || kind === "archived"
                            ? "secondary"
                            : kind === "selected"
                              ? "outline"
                              : "secondary"
                      }
                    >
                      {t(labelKey)}
                    </Badge>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {rec && (kind === "draft" || kind === "selected") && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => publishMut.mutate(rec.id)}
                          disabled={busy}
                        >
                          <Megaphone className="w-3.5 h-3.5 mr-1" />
                          {t("archive.publish.label")}
                        </Button>
                      )}
                      {rec && kind === "publicity" && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => withdrawMut.mutate(rec.id)}
                            disabled={busy}
                          >
                            <Undo2 className="w-3.5 h-3.5 mr-1" />
                            {t("archive.withdraw.label")}
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => archiveMut.mutate(rec.id)}
                            disabled={busy}
                          >
                            <Archive className="w-3.5 h-3.5 mr-1" />
                            {t("archive.archive.label")}
                          </Button>
                        </>
                      )}
                      {rec && kind === "ended" && (
                        <Button
                          size="sm"
                          onClick={() => archiveMut.mutate(rec.id)}
                          disabled={busy}
                        >
                          <Archive className="w-3.5 h-3.5 mr-1" />
                          {t("archive.archive.label")}
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
