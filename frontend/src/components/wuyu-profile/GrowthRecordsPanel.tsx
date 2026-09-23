import { useState } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
  useInfiniteQuery,
} from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { toast } from "sonner";
import {
  Plus,
  Trash2,
  Loader2,
  ClipboardList,
  ChevronDown,
  Mic,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import {
  listGrowthRecords,
  listIndicators,
  createGrowthRecord,
  deleteGrowthRecord,
  type GrowthRecord,
  type WuyuDimension,
} from "@/services/wuyuApi";
import { useVoiceInput } from "@/hooks/useVoiceInput";
import {
  DIMENSIONS,
  DIMENSION_LABEL_KEY,
  DIMENSION_COLORS,
  formatDateTime,
} from "./portfolioShared";

interface GrowthRecordsPanelProps {
  studentId: string;
}

/** 录音秒数格式化为 mm:ss */
const formatVoiceSeconds = (s: number): string => {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
};

export function GrowthRecordsPanel({ studentId }: GrowthRecordsPanelProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const voice = useVoiceInput();

  // 录入表单状态
  const [dimension, setDimension] = useState<WuyuDimension>("moral");
  const [points, setPoints] = useState<string>("");
  const [note, setNote] = useState<string>("");
  const [indicatorId, setIndicatorId] = useState<string>("");

  // 删除确认
  const [deleteTarget, setDeleteTarget] = useState<GrowthRecord | null>(null);

  const {
    data,
    isLoading,
    isError,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["wuyu-growth", studentId],
    queryFn: ({ pageParam = 1 }) =>
      listGrowthRecords(studentId, { page: pageParam, pageSize: 100 }),
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce(
        (sum, p) => sum + (p?.rows?.length || 0),
        0,
      );
      const total = lastPage?.total ?? 0;
      return loaded < total ? allPages.length + 1 : undefined;
    },
    enabled: !!studentId,
  });

  const { data: indicators } = useQuery({
    queryKey: ["wuyu-indicators", dimension],
    queryFn: () => listIndicators(dimension),
    enabled: !!studentId,
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["wuyu-growth", studentId] });
    queryClient.invalidateQueries({ queryKey: ["wuyu-portfolio", studentId] });
    queryClient.invalidateQueries({ queryKey: ["wuyu-report", studentId] });
  };

  const createMut = useMutation({
    mutationFn: () =>
      createGrowthRecord(studentId, {
        dimension,
        growth_point: Number(points),
        note: note.trim() || null,
        evidence: null,
        indicator_id: indicatorId || null,
      }),
    onSuccess: () => {
      toast.success(t("wuyu.growth.success"));
      setPoints("");
      setNote("");
      setIndicatorId("");
      invalidateAll();
    },
    onError: (err: any) => {
      toast.error(t("wuyu.growth.failed"), { description: err?.message });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (record: GrowthRecord) =>
      deleteGrowthRecord(studentId, record.id),
    onSuccess: () => {
      toast.success(t("wuyu.growth.deleteSuccess"));
      setDeleteTarget(null);
      invalidateAll();
    },
    onError: (err: any) => {
      toast.error(t("wuyu.growth.deleteFailed"), { description: err?.message });
      setDeleteTarget(null);
    },
  });

  const handleSubmit = () => {
    const num = Number(points);
    if (
      points.trim() === "" ||
      !Number.isFinite(num) ||
      num < -10 ||
      num > 10
    ) {
      toast.error(t("wuyu.growth.pointsRequired"));
      return;
    }
    createMut.mutate();
  };

  const handleVoiceClick = async () => {
    if (voice.state === "recording") {
      const text = await voice.stopAndTranscribe();
      if (text) {
        // 已有内容则追加（用空格分隔），否则直接替换
        setNote((prev) =>
          prev && prev.trim() ? `${prev.trim()} ${text}` : text,
        );
        toast.success(t("voice.success"));
      } else {
        toast.error(t("voice.fail"));
      }
      return;
    }
    const err = await voice.start();
    if (err === "denied") {
      toast.error(t("voice.denied"));
    } else if (err === "error") {
      toast.error(t("voice.unsupported"));
    }
  };

  const rows = data?.pages.flatMap((p) => p?.rows ?? []) ?? [];
  const total = data?.pages?.[0]?.total ?? 0;

  return (
    <Card>
      <CardHeader className="pb-3 flex-row items-start justify-between space-y-0">
        <div>
          <div className="flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">
              {t("wuyu.growth.title")}
            </CardTitle>
          </div>
          <CardDescription>{t("wuyu.growth.subtitle")}</CardDescription>
        </div>
        <Badge variant="secondary" className="shrink-0">
          {t("wuyu.growth.total", { count: total })}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 手动录入 */}
        <div className="rounded-lg border border-border/50 p-4 space-y-3 bg-muted/30">
          <p className="text-sm font-medium text-foreground">
            {t("wuyu.growth.manualAdd")}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("wuyu.growth.dimension")}</Label>
              <Select
                value={dimension}
                onValueChange={(v) => {
                  setDimension(v as WuyuDimension);
                  setIndicatorId("");
                }}
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DIMENSIONS.map((d) => (
                    <SelectItem key={d} value={d}>
                      {t(DIMENSION_LABEL_KEY[d])}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t("wuyu.growth.points")}</Label>
              <Input
                className="h-9"
                type="number"
                step={1}
                min={-10}
                max={10}
                value={points}
                onChange={(e) => setPoints(e.target.value)}
                placeholder={t("wuyu.growth.pointsPlaceholder")}
              />
            </div>
            <div className="space-y-1.5 sm:col-span-1">
              <Label className="text-xs">{t("wuyu.growth.note")}</Label>
              <div className="flex gap-2">
                <Input
                  className="h-9 flex-1 min-w-0"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder={t("wuyu.growth.notePlaceholder")}
                />
                {voice.supported && (
                  <Button
                    type="button"
                    size="sm"
                    variant={
                      voice.state === "recording" ? "destructive" : "outline"
                    }
                    className="h-9 shrink-0 gap-1 px-2.5 text-xs"
                    title={t(
                      voice.state === "recording"
                        ? "voice.stop"
                        : voice.state === "recognizing"
                          ? "voice.recognizing"
                          : "voice.start",
                    )}
                    onClick={handleVoiceClick}
                    disabled={voice.state === "recognizing"}
                  >
                    {voice.state === "recognizing" ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : voice.state === "recording" ? (
                      <>
                        <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                        <span className="tabular-nums">
                          {formatVoiceSeconds(voice.seconds)}
                        </span>
                      </>
                    ) : (
                      <>
                        <Mic className="w-3.5 h-3.5" />
                        <span>{t("voice.button")}</span>
                      </>
                    )}
                  </Button>
                )}
              </div>
            </div>
            <div className="space-y-1.5 sm:col-span-3">
              <Label className="text-xs">{t("wuyu.growth.indicator")}</Label>
              <Select value={indicatorId} onValueChange={setIndicatorId}>
                <SelectTrigger className="h-9">
                  <SelectValue
                    placeholder={t("wuyu.growth.indicatorPlaceholder")}
                  />
                </SelectTrigger>
                <SelectContent>
                  {indicators && indicators.length > 0 ? (
                    indicators.map((ind) => (
                      <SelectItem key={ind.id} value={ind.id}>
                        {ind.name}
                      </SelectItem>
                    ))
                  ) : (
                    <div className="px-2 py-1.5 text-sm text-muted-foreground">
                      {t("wuyu.growth.noIndicator")}
                    </div>
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={createMut.isPending}
            >
              {createMut.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
              ) : (
                <Plus className="w-3.5 h-3.5 mr-1" />
              )}
              {createMut.isPending
                ? t("wuyu.growth.submitting")
                : t("wuyu.growth.submit")}
            </Button>
          </div>
        </div>

        {/* 列表 */}
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mb-2" />
            <p className="text-sm">{t("wuyu.loading")}</p>
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center py-12 border border-dashed rounded-lg text-muted-foreground">
            <p className="text-sm mb-2">{t("wuyu.loadFailed")}</p>
            <Button size="sm" variant="outline" onClick={() => refetch()}>
              {t("wuyu.retry")}
            </Button>
          </div>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 border border-dashed rounded-lg text-muted-foreground">
            <ClipboardList className="w-8 h-8 opacity-30 mb-2" />
            <p className="text-sm">{t("wuyu.growth.empty")}</p>
            <p className="text-xs mt-1">{t("wuyu.growth.emptyHint")}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {rows.map((r) => {
              const color = DIMENSION_COLORS[r.dimension] ?? "#94a3b8";
              const isManual = r.source_type === "manual";
              return (
                <div
                  key={r.id}
                  className="flex items-center gap-3 rounded-lg border border-border/50 px-3 py-2.5"
                >
                  <span
                    className="w-1.5 h-8 rounded-full shrink-0"
                    style={{ backgroundColor: color }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">
                        {t(DIMENSION_LABEL_KEY[r.dimension])}
                      </span>
                      <Badge variant="secondary" className="text-[10px]">
                        {t(
                          `wuyu.growth.source.${r.source_type}`,
                          undefined,
                          r.source_type,
                        )}
                      </Badge>
                      {r.indicator_name && (
                        <Badge variant="outline" className="text-[10px]">
                          {r.indicator_name}
                        </Badge>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {formatDateTime(r.occurred_at)}
                      </span>
                    </div>
                    {r.note && (
                      <p className="text-xs text-muted-foreground truncate mt-0.5">
                        {r.note}
                      </p>
                    )}
                  </div>
                  <span
                    className={`text-sm font-bold shrink-0 ${
                      (r.growth_point ?? 0) >= 0
                        ? "text-emerald-600"
                        : "text-destructive"
                    }`}
                  >
                    {(r.growth_point ?? 0) >= 0 ? "+" : ""}
                    {r.growth_point}
                  </span>
                  {isManual && (
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive shrink-0"
                      title={t("wuyu.growth.delete")}
                      onClick={() => setDeleteTarget(r)}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  )}
                </div>
              );
            })}
            {hasNextPage && (
              <div className="flex justify-center pt-1">
                <Button
                  size="sm"
                  variant="outline"
                  className="text-xs h-8 gap-1"
                  onClick={() => fetchNextPage()}
                  disabled={isFetchingNextPage}
                >
                  {isFetchingNextPage ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <ChevronDown className="w-3.5 h-3.5" />
                  )}
                  {isFetchingNextPage
                    ? t("wuyu.loading")
                    : t("wuyu.growth.loadMore")}
                </Button>
              </div>
            )}
          </div>
        )}
      </CardContent>

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("wuyu.growth.deleteConfirm")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("wuyu.growth.delete")} ·{" "}
              {deleteTarget
                ? t(DIMENSION_LABEL_KEY[deleteTarget.dimension])
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                if (deleteTarget) deleteMut.mutate(deleteTarget);
              }}
              disabled={deleteMut.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteMut.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
              ) : (
                <Trash2 className="w-3.5 h-3.5 mr-1" />
              )}
              {t("wuyu.growth.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
