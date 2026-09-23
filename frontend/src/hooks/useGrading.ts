import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  submitGrading,
  getGradingRecords,
  getGradingResult,
  type GradingJobItem,
} from "@/services/api";

/** 查询批改记录（真实端点 GET /grading/home/recent，返回最近 10 条作业） */
export function useGradingRecords() {
  return useQuery({
    queryKey: ["gradingRecords"],
    queryFn: () => getGradingRecords(),
  });
}

/** 提交批改任务：上传单张试卷图片 → POST /grading/home/quick */
export function useSubmitGrading() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (file: File) => submitGrading(file),
    onSuccess: () => {
      // 提交成功后刷新批改记录
      queryClient.invalidateQueries({ queryKey: ["gradingRecords"] });
    },
  });
}

/** 查询单个批改结果（真实端点 GET /grading/home/{job_id}，轮询任务状态） */
export function useGradingResult(taskId: string | null) {
  return useQuery({
    queryKey: ["gradingResult", taskId],
    queryFn: () => getGradingResult(taskId!),
    enabled: !!taskId,
    // 未完成的任务定期轮询（后端状态：queued / running / rendering）
    refetchInterval: (query) => {
      const status = (query.state.data as GradingJobItem | undefined)?.status;
      if (status === "queued" || status === "running" || status === "rendering") {
        return 3000;
      }
      return false;
    },
  });
}
