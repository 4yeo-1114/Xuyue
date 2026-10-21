import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import {
  autoTier,
  batchMoveTiers,
  getLayeredPushSettings,
  getLayeredRoster,
  getLayeredStats,
  listLayeredRounds,
  patchLayeredTaskStatus,
  saveLayeredPushSettings,
  sendLayeredReport,
  startPush,
  syncLayeredRoster,
  testPush,
  urgePush,
} from "@/services/api";
import type { LayeredPushSettings, LayeredStats } from "@/services/api";

function getErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "message" in error) {
    return String((error as { message?: unknown }).message ?? "");
  }
  return "";
}

/** 分层名单（学生 + 平均分 + 分层 + 钉钉同步状态） */
export function useLayeredRoster(classId?: string, subject?: string) {
  return useQuery({
    queryKey: ["layered-roster", classId, subject],
    queryFn: () => getLayeredRoster(classId!, subject),
    enabled: !!classId,
  });
}

/** 分层推送设置（未存过为 null，本地再合默认值） */
export function useLayeredSettings(classId?: string, subject?: string) {
  return useQuery({
    queryKey: ["layered-settings", classId, subject],
    queryFn: () => getLayeredPushSettings(classId!, subject),
    enabled: !!classId,
    staleTime: 0,
  });
}

/** 最近一轮统计（推送后台发送中时轮询由页面传 refetchInterval） */
export function useLayeredStats(classId?: string, subject?: string, refetchInterval?: number) {
  return useQuery({
    queryKey: ["layered-stats", classId, subject],
    queryFn: () => getLayeredStats(classId!, subject),
    enabled: !!classId,
    refetchInterval,
  });
}

/** 历史推送轮次 */
export function useLayeredRounds(classId?: string, subject?: string) {
  return useQuery({
    queryKey: ["layered-rounds", classId, subject],
    queryFn: () => listLayeredRounds(classId!, subject),
    enabled: !!classId,
  });
}

function invalidateAfterMove(
  qc: ReturnType<typeof useQueryClient>,
  classId: string,
  subject?: string,
) {
  qc.invalidateQueries({ queryKey: ["layered-roster", classId, subject] });
  qc.invalidateQueries({ queryKey: ["layered-roster", classId] });
  qc.invalidateQueries({ queryKey: ["students", classId] });
}

/** 拖拽/批量调整分层（乐观更新由页面做，这里负责请求 + 缓存失效） */
export function useMoveTiers() {
  const qc = useQueryClient();
  const { t } = useLocale();
  return useMutation({
    mutationFn: (params: {
      class_id: string;
      subject?: string;
      moves: { student_id: string; tier: "A" | "B" | "C" }[];
    }) => batchMoveTiers({ class_id: params.class_id, moves: params.moves }),
    onSuccess: (_, variables) => {
      invalidateAfterMove(qc, variables.class_id, variables.subject);
    },
    onError: (error) => {
      toast.error(getErrorMessage(error) || t("layeredPush.toast.moveFailed"));
    },
  });
}

/** 按平均分自动分层 */
export function useAutoTier() {
  const qc = useQueryClient();
  const { t } = useLocale();
  return useMutation({
    mutationFn: (params: {
      class_id: string;
      subject?: string;
      thresholds?: { a?: number; b?: number };
    }) => autoTier(params),
    onSuccess: (data, variables) => {
      invalidateAfterMove(qc, variables.class_id, variables.subject);
      toast.success(
        t("layeredPush.toast.tiersUpdated", {
          updated: data.updated,
          noScore: data.no_score,
        }),
      );
    },
    onError: (error) => {
      toast.error(getErrorMessage(error) || t("layeredPush.toast.moveFailed"));
    },
  });
}

/** 保存设置（成功后写回缓存，避免 refetch 覆盖本地编辑） */
export function useSaveLayeredSettings() {
  const qc = useQueryClient();
  const { t } = useLocale();
  return useMutation({
    mutationFn: (params: {
      class_id: string;
      subject?: string;
      settings: LayeredPushSettings;
    }) => saveLayeredPushSettings(params),
    onSuccess: (_, variables) => {
      qc.setQueryData(
        ["layered-settings", variables.class_id, variables.subject],
        variables.settings,
      );
      // 预览与实际消息同一拼装函数，设置变了要重新拉
      qc.invalidateQueries({ queryKey: ["layered-preview"] });
    },
    onError: (error) => {
      toast.error(getErrorMessage(error) || t("layeredPush.toast.settingsSaveFailed"));
    },
  });
}

/** 测试推送（给当前老师本人发配置摘要，验证钉钉通道） */
export function useTestPush() {
  const { t } = useLocale();
  return useMutation({
    mutationFn: (params: { class_id: string; subject?: string }) => testPush(params),
    onSuccess: (data) => {
      if (data.ok) toast.success(data.message || t("layeredPush.toast.testPushOk"));
      else toast.error(data.message || t("layeredPush.toast.testPushFail"));
    },
    onError: (error) => {
      toast.error(getErrorMessage(error) || t("layeredPush.toast.testPushFail"));
    },
  });
}

/** 确认推送（发起新一轮，后台发送） */
export function useStartPush() {
  const qc = useQueryClient();
  const { t } = useLocale();
  return useMutation({
    mutationFn: (params: {
      class_id: string;
      subject?: string;
      notice_only?: boolean;
      notice_text?: string;
    }) => startPush(params),
    onSuccess: (data, variables) => {
      if (data.notice_only) {
        toast.success(t("layeredPush.toast.noticeSent", { total: data.total }));
      } else {
        toast.success(t("layeredPush.toast.pushStarted", { total: data.total }));
        qc.invalidateQueries({ queryKey: ["layered-stats", variables.class_id, variables.subject] });
        qc.invalidateQueries({ queryKey: ["layered-rounds", variables.class_id, variables.subject] });
      }
    },
    onError: (error) => {
      toast.error(getErrorMessage(error) || t("layeredPush.toast.pushFailed"));
    },
  });
}

/** 催交 */
export function useUrgePush() {
  const qc = useQueryClient();
  const { t } = useLocale();
  return useMutation({
    mutationFn: (params: { class_id: string; subject?: string; tier?: "A" | "B" | "C" }) =>
      urgePush(params),
    onSuccess: (data, variables) => {
      qc.invalidateQueries({ queryKey: ["layered-stats", variables.class_id, variables.subject] });
      toast.success(t("layeredPush.toast.urgeResult", { sent: data.sent, failed: data.failed }));
    },
    onError: (error) => {
      toast.error(getErrorMessage(error) || t("layeredPush.toast.urgeFailed"));
    },
  });
}

/** 教师标记完成/未完成（乐观更新 stats.unfinished） */
export function usePatchTaskStatus(classId?: string, subject?: string) {
  const qc = useQueryClient();
  const { t } = useLocale();
  return useMutation({
    mutationFn: (params: { task_id: string; status: "pending" | "completed" }) =>
      patchLayeredTaskStatus(params.task_id, params.status),
    onMutate: async (params) => {
      const key = ["layered-stats", classId, subject];
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<LayeredStats>(key);
      if (prev && params.task_id) {
        qc.setQueryData<LayeredStats>(key, {
          ...prev,
          tiers: Object.fromEntries(
            Object.entries(prev.tiers).map(([tier, bucket]) => [
              tier,
              {
                ...bucket,
                unfinished: bucket.unfinished.filter((u) => u.task_id !== params.task_id),
                completed:
                  params.status === "completed"
                    ? bucket.completed + 1
                    : Math.max(0, bucket.completed - 1),
              },
            ]),
          ),
        });
      }
      return { prev };
    },
    onError: (error, _params, ctx) => {
      if (ctx?.prev) qc.setQueryData(["layered-stats", classId, subject], ctx.prev);
      toast.error(getErrorMessage(error) || t("layeredPush.toast.markFailed"));
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["layered-stats", classId, subject] });
    },
  });
}

/** 生成报告（weekly/round × self/head） */
export function useSendReport() {
  const { t } = useLocale();
  return useMutation({
    mutationFn: (params: {
      class_id: string;
      subject?: string;
      kind?: "weekly" | "round";
      recipient?: "self" | "head";
    }) => sendLayeredReport(params),
    onSuccess: (data) => {
      if (data.ok) toast.success(data.message || t("layeredPush.toast.reportOk"));
      else toast.error(data.message || t("layeredPush.toast.reportFail"));
    },
    onError: (error) => {
      toast.error(getErrorMessage(error) || t("layeredPush.toast.reportFail"));
    },
  });
}

/** 按绑定的钉钉部门整班刷新名单 */
export function useSyncRoster() {
  const qc = useQueryClient();
  const { t } = useLocale();
  return useMutation({
    mutationFn: (params: { class_id: string }) => syncLayeredRoster(params),
    onSuccess: (data, variables) => {
      invalidateAfterMove(qc, variables.class_id);
      toast.success(
        t("layeredPush.toast.syncRosterDone", {
          created: data.created,
          updated: data.updated,
          total: data.total,
        }),
      );
    },
    onError: (error) => {
      toast.error(getErrorMessage(error) || t("layeredPush.toast.syncRosterFailed"));
    },
  });
}
