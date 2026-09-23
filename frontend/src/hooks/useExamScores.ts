import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getExamScores, upsertExamScores } from "@/services/api";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";

/** 成绩记录（来自后端 GET /exam-scores，含后端计算的等级代码） */
export interface ExamScoreRecord {
  student_id: string;
  score: number | null;
  grade: "excellent" | "good" | "pass" | "needs_work" | null;
}

export function useExamScores(examId?: string) {
  return useQuery({
    queryKey: ["exam_scores", examId],
    queryFn: () => getExamScores(examId!),
    enabled: !!examId,
  });
}

export function useUpsertExamScores() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async (params: {
      exam_id: string;
      scores: { student_id: string; score: number | null }[];
    }) => {
      await upsertExamScores(params.exam_id, params.scores);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["exam_scores", variables.exam_id],
      });
      toast.success(t("home.toast.scoreSaveSuccess"));
    },
    onError: () => toast.error(t("home.toast.scoreSaveFailed")),
  });
}
