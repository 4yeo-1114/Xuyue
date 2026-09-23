import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { toast } from "sonner";
import {
  Sparkles,
  Check,
  ShieldCheck,
  ShieldAlert,
  Loader2,
  MessageSquareText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  getComment,
  generateComment,
  confirmComment,
  type CommentSection,
} from "@/services/wuyuApi";
import { ApiError } from "@/services/api";
import { TERM_PATTERN, formatDateTime } from "./portfolioShared";

interface AiCommentPanelProps {
  studentId: string;
}

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "outline" | "destructive"
> = {
  absent: "outline",
  pending: "secondary",
  confirmed: "default",
  ai_failed: "destructive",
};

export function AiCommentPanel({ studentId }: AiCommentPanelProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();

  const [term, setTerm] = useState("2025-2026-1");
  const [draft, setDraft] = useState("");

  const termValid = TERM_PATTERN.test(term.trim());

  const {
    data: comment,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["wuyu-comment", studentId, term.trim()],
    queryFn: () => getComment(studentId, term.trim()),
    enabled: !!studentId && termValid,
  });

  // 拉取到评语后同步到草稿
  useEffect(() => {
    if (comment) setDraft(comment.content ?? "");
  }, [comment]);

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["wuyu-comment", studentId] });
    queryClient.invalidateQueries({ queryKey: ["wuyu-report", studentId] });
  };

  const genMut = useMutation({
    mutationFn: () => generateComment(studentId, term.trim()),
    onSuccess: (section) => {
      if (section.status === "ai_failed") {
        toast.error(t("wuyu.comment.generateFailed"), {
          description: section.content ?? "",
        });
      } else {
        toast.success(t("wuyu.comment.generateSuccess"));
      }
      setDraft(section.content ?? "");
      invalidateAll();
    },
    onError: (err: any) => {
      toast.error(t("wuyu.comment.generateFailed"), {
        description: err?.message,
      });
    },
  });

  const confirmMut = useMutation({
    mutationFn: () => confirmComment(studentId, term.trim(), draft),
    onSuccess: (section) => {
      toast.success(t("wuyu.comment.confirmSuccess"));
      setDraft(section.content ?? "");
      invalidateAll();
    },
    onError: (err: unknown) => {
      // 禁词闸门拒绝是后端 422 契约(见 wuyuApi.confirmComment 注释),按错误码判断;
      // 其余错误统一走 i18n 提示,不依赖后端文案做子串匹配,避免文案变更导致分支失效。
      if (err instanceof ApiError && err.status === 422) {
        toast.error(t("wuyu.comment.confirmBlocked"));
      } else {
        toast.error(t("wuyu.comment.confirmFailed"));
      }
    },
  });

  const status = comment?.status ?? "absent";
  const canConfirm = status === "pending" || status === "confirmed";
  const statusLabel = t(`wuyu.comment.status.${status}`);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <MessageSquareText className="w-4 h-4 text-primary" />
          <CardTitle className="text-sm font-semibold">
            {t("wuyu.comment.title")}
          </CardTitle>
        </div>
        <CardDescription>{t("wuyu.comment.subtitle")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 学期 + 生成 */}
        <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
          <div className="space-y-1.5 flex-1 max-w-xs">
            <Label className="text-xs">{t("wuyu.report.term")}</Label>
            <Input
              className="h-9"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder={t("wuyu.report.termPlaceholder")}
            />
          </div>
          <Button
            size="sm"
            onClick={() => genMut.mutate()}
            disabled={!termValid || genMut.isPending}
          >
            {genMut.isPending ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
            ) : (
              <Sparkles className="w-3.5 h-3.5 mr-1" />
            )}
            {genMut.isPending
              ? t("wuyu.comment.generating")
              : t("wuyu.comment.generate")}
          </Button>
        </div>

        {/* 状态徽标 */}
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={STATUS_VARIANT[status] ?? "outline"}>
            {statusLabel}
          </Badge>
          {isLoading && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" /> {t("wuyu.loading")}
            </span>
          )}
          {!isLoading && status === "absent" && (
            <span className="text-xs text-muted-foreground">
              {t("wuyu.comment.generateFirst")}
            </span>
          )}
          {!isLoading && comment?.gate_flagged === true && (
            <Badge variant="outline" className="text-amber-600">
              <ShieldAlert className="w-3 h-3 mr-1" />{" "}
              {t("wuyu.comment.gateFlagged")}
            </Badge>
          )}
          {!isLoading &&
            status === "confirmed" &&
            comment?.gate_flagged === false && (
              <Badge variant="outline" className="text-emerald-600">
                <ShieldCheck className="w-3 h-3 mr-1" />{" "}
                {t("wuyu.comment.gatePassed")}
              </Badge>
            )}
          {comment?.ai_model && (
            <Badge variant="secondary" className="text-[10px]">
              {t("wuyu.comment.aiModel")}: {comment.ai_model}
            </Badge>
          )}
          {status === "confirmed" && comment?.confirmed_at && (
            <span className="text-xs text-muted-foreground">
              {t("wuyu.comment.confirmedAt")}:{" "}
              {formatDateTime(comment.confirmed_at)}
            </span>
          )}
        </div>

        {/* 内容编辑区 */}
        <Textarea
          className="min-h-[140px]"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t("wuyu.comment.contentPlaceholder")}
          disabled={status === "absent"}
        />

        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] text-muted-foreground">
            {t("wuyu.comment.aiAuxiliary")}
          </p>
          <Button
            size="sm"
            onClick={() => confirmMut.mutate()}
            disabled={!canConfirm || !draft.trim() || confirmMut.isPending}
          >
            {confirmMut.isPending ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
            ) : (
              <Check className="w-3.5 h-3.5 mr-1" />
            )}
            {status === "confirmed"
              ? t("wuyu.comment.confirmWithEdit")
              : t("wuyu.comment.confirm")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export type { CommentSection };
