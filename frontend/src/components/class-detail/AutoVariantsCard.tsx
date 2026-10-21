import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import {
  generateAutoVariants,
  getAutoVariants,
  flattenAutoVariantDisplay,
  resolveAutoVariantsState,
} from "@/services/banditApi";
import type { AutoVariantItem, QuestionSource } from "@/services/banditApi";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sparkles,
  Loader2,
  RefreshCw,
  ChevronDown,
  AlertCircle,
  BookX,
  Settings2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { QUESTION_TYPE_OPTIONS, splitTopics } from "@/lib/aiQuestionTypes";

interface AutoVariantsCardProps {
  /** 批改场次 folder_safe（cls_{class_id}__{exam_name}）；空则显示未生成 */
  folder: string;
}

/**
 * 本场自动配套练习卡片（客户清单#2 全自动）：
 * 批改完成后后端自动产出变式题；此处只读展示 + 「重新生成」force 重跑。
 * 样式对齐 VariantRecommendPanel。
 */
export function AutoVariantsCard({ folder }: AutoVariantsCardProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  // 题源：ai=AI 生成（可选题型/知识点）；bank=题库
  const [source, setSource] = useState<QuestionSource>("ai");
  const [showOpts, setShowOpts] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [topicText, setTopicText] = useState("");

  const enabled = !!folder;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["auto-variants", folder],
    queryFn: () => getAutoVariants(folder),
    enabled,
    retry: 1,
  });

  const genMutation = useMutation({
    mutationFn: () =>
      generateAutoVariants(folder, true, {
        source,
        types: selectedTypes,
        topics: splitTopics(topicText),
      }),
    onSuccess: (result) => {
      queryClient.setQueryData(["auto-variants", folder], result);
      queryClient.invalidateQueries({ queryKey: ["auto-variants", folder] });
      if (result.status === "ready") {
        toast.success(t("grading.autoVariants.regenerateSuccess"));
      } else if (result.status === "failed") {
        toast.error(t("grading.autoVariants.regenerateFailed"));
      } else {
        toast.success(t("grading.autoVariants.regenerateSuccess"));
      }
    },
    onError: () => toast.error(t("grading.autoVariants.regenerateFailed")),
  });

  const state = resolveAutoVariantsState({
    data,
    isFetching: isLoading,
    isGenerating: genMutation.isPending,
  });
  const rows = useMemo(() => flattenAutoVariantDisplay(data), [data]);

  const toggleExpand = (key: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const statusLabel =
    state === "generating"
      ? t("grading.autoVariants.generating")
      : state === "failed"
        ? t("grading.autoVariants.failed")
        : state === "empty"
          ? t("grading.autoVariants.empty")
          : state === "none"
            ? t("grading.autoVariants.none")
            : t("grading.autoVariants.ready");

  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
          <Sparkles className="w-4 h-4 text-amber-500" />
          {t("grading.autoVariants.title")}
          <Badge variant="outline" className="text-[10px]">
            {statusLabel}
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={source}
            onValueChange={(v) => setSource(v as QuestionSource)}
          >
            <SelectTrigger className="h-8 w-[110px] text-xs">
              <SelectValue placeholder={t("smartGen.aiSource.label")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ai">{t("smartGen.aiSource.ai")}</SelectItem>
              <SelectItem value="bank">{t("smartGen.aiSource.bank")}</SelectItem>
            </SelectContent>
          </Select>
          {source === "ai" && (
            <Button
              size="sm"
              variant="outline"
              className="h-8 gap-1 text-xs"
              onClick={() => setShowOpts((v) => !v)}
            >
              <Settings2 className="w-3.5 h-3.5" />
              {t("smartGen.aiSource.settings")}
            </Button>
          )}
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5"
          disabled={!folder || genMutation.isPending || source === "bank"}
          onClick={() => genMutation.mutate()}
        >
          {genMutation.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5" />
          )}
          {t("grading.autoVariants.regenerate")}
        </Button>
        </div>
      </div>

      {source === "ai" && showOpts && (
        <div className="rounded-lg border border-border/50 bg-muted/20 p-3 space-y-2">
          <div className="flex items-center gap-2">
            <span className="w-14 shrink-0 text-xs font-medium">
              {t("smartGen.aiSource.topicsLabel")}
            </span>
            <Input
              className="h-8 text-xs"
              placeholder={t("smartGen.aiSource.topicsPlaceholder")}
              value={topicText}
              onChange={(e) => setTopicText(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="w-14 shrink-0 text-xs font-medium">
              {t("smartGen.aiSource.typesLabel")}
            </span>
            {QUESTION_TYPE_OPTIONS.map((o) => {
              const active = selectedTypes.includes(o.value);
              return (
                <Button
                  key={o.value}
                  size="sm"
                  variant={active ? "default" : "outline"}
                  className="h-7 px-2 text-xs"
                  onClick={() =>
                    setSelectedTypes((prev) =>
                      active
                        ? prev.filter((v) => v !== o.value)
                        : [...prev, o.value],
                    )
                  }
                >
                  {o.label}
                </Button>
              );
            })}
          </div>
          <p className="text-xs text-muted-foreground">
            {t("smartGen.aiSource.aiHint")}
          </p>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        {t("grading.autoVariants.subtitle")}
        {data?.generated_at ? (
          <span className="ml-2">
            {t("grading.autoVariants.generatedAt", {
              time: new Date(data.generated_at).toLocaleString(),
            })}
          </span>
        ) : null}
      </p>

      {source === "bank" ? (
        <div className="rounded-lg border border-dashed border-amber-500/50 bg-amber-500/5 px-4 py-6 text-center text-xs text-amber-600">
          {t("smartGen.aiSource.bankUnavailable")}
          <div className="mt-1 text-muted-foreground">
            {t("smartGen.aiSource.bankHint")}
          </div>
        </div>
      ) : !folder ? (
        <p className="py-4 text-center text-sm text-muted-foreground">
          {t("grading.autoVariants.noFolder")}
        </p>
      ) : state === "generating" || (state === "loading" && !data) ? (
        <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin text-primary/60" />
          {state === "generating"
            ? t("grading.autoVariants.generating")
            : t("grading.autoVariants.loading")}
        </div>
      ) : isError && !data ? (
        <div className="flex flex-col items-center gap-2 py-4 text-center">
          <AlertCircle className="w-8 h-8 text-destructive/60" />
          <p className="text-sm text-muted-foreground">
            {t("grading.autoVariants.loadFailed")}
          </p>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => refetch()}>
            <RefreshCw className="w-3.5 h-3.5" />
            {t("grading.autoVariants.regenerate")}
          </Button>
        </div>
      ) : state === "failed" ? (
        <div className="flex flex-col items-center gap-2 py-4 text-center">
          <AlertCircle className="w-8 h-8 text-destructive/60" />
          <p className="text-sm text-muted-foreground">
            {t("grading.autoVariants.failedHint")}
          </p>
        </div>
      ) : state === "none" ? (
        <div className="flex flex-col items-center gap-2 py-4 text-center">
          <BookX className="w-8 h-8 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">
            {t("grading.autoVariants.noneHint")}
          </p>
        </div>
      ) : state === "empty" || rows.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-4 text-center">
          <BookX className="w-8 h-8 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">
            {t("grading.autoVariants.emptyHint")}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {rows.map((item, idx) => {
            const key = `${item.id ?? idx}-${item.kp_name}-${idx}`;
            const isOpen = expandedIds.has(key);
            return (
              <div
                key={key}
                className="rounded-md border border-border/50 bg-muted/20 p-2.5 space-y-1.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm leading-relaxed whitespace-pre-line">{item.question}</p>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 shrink-0 gap-1 text-xs"
                    onClick={() => toggleExpand(key)}
                  >
                    {isOpen
                      ? t("grading.autoVariants.hideAnswer")
                      : t("grading.autoVariants.showAnswer")}
                    <ChevronDown
                      className={cn(
                        "w-3.5 h-3.5 transition-transform",
                        isOpen && "rotate-180",
                      )}
                    />
                  </Button>
                </div>
                <div className="flex items-center gap-2 flex-wrap text-xs text-muted-foreground">
                  <Badge variant="secondary" className="text-[10px]">
                    {t("grading.autoVariants.weakPoint")}: {item.kp_name}
                  </Badge>
                  {typeof item.wrong_count === "number" && item.wrong_count > 0 && (
                    <span>
                      {t("grading.autoVariants.wrongCount", { count: item.wrong_count })}
                    </span>
                  )}
                  {typeof item.student_count === "number" && item.student_count > 0 && (
                    <span>
                      {t("grading.autoVariants.studentCount", { count: item.student_count })}
                    </span>
                  )}
                </div>
                {isOpen && (
                  <div className="mt-1 rounded-md border border-primary/20 bg-primary/5 p-2 space-y-1">
                    <p className="text-xs">
                      <span className="font-medium text-primary">
                        {t("grading.autoVariants.answerLabel")}：
                      </span>
                      <span className="text-muted-foreground">
                        {item.answer || "—"}
                      </span>
                    </p>
                    {item.analysis ? (
                      <p className="text-xs">
                        <span className="font-medium text-primary">
                          {t("grading.autoVariants.analysisLabel")}：
                        </span>
                        <span className="text-muted-foreground">{item.analysis}</span>
                      </p>
                    ) : null}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default AutoVariantsCard;
