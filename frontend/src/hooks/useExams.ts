import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import { listExams, createExam, deleteExam } from "@/services/api";
import type { ExamRecord } from "@/services/api";

export type { ExamRecord };

export function useExams(classId?: string, subject?: string) {
  const { user } = useAuth();

  return useQuery({
    queryKey: ["exams", classId, subject],
    queryFn: () => listExams(classId!, subject),
    // enabled 条件保持：依赖登录态与 classId（鉴权由后端 can_view_class 完成）
    enabled: !!user && !!classId,
  });
}

export function useCreateExam() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: (params: {
      class_id: string;
      subject: string;
      title: string;
      total_score: number;
      exam_date: string;
    }) => createExam(params),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["exams", variables.class_id],
      });
      toast.success(t("home.toast.examCreateSuccess"));
    },
    onError: () => toast.error(t("home.toast.examCreateFailed")),
  });
}

export function useDeleteExam() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async (params: { id: string; class_id: string }) => {
      await deleteExam(params.id);
      return params;
    },
    onSuccess: (params) => {
      queryClient.invalidateQueries({ queryKey: ["exams", params.class_id] });
      toast.success(t("home.toast.examDeleteSuccess"));
    },
    onError: () => toast.error(t("home.toast.examDeleteFailed")),
  });
}
