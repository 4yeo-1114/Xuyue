import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { batchCreateStudents } from "@/services/api";
import { useLocale } from "@/contexts/LocaleContext";

function getErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "message" in error) {
    return String((error as { message?: unknown }).message ?? "");
  }
  return "";
}

export function useBatchCreateStudents() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async (params: {
      class_id: string;
      students: { name: string; student_number: string; gender?: string }[];
    }) => {
      return batchCreateStudents(params);
    },
    onSuccess: (count, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["students", variables.class_id],
      });
      queryClient.invalidateQueries({ queryKey: ["classes"] });
      toast.success(t("home.toast.batchCreateSuccess", { count }));
    },
    onError: (error: unknown) => {
      const msg = getErrorMessage(error);
      if (msg.includes("部分") || msg.includes("已存在"))
        toast.error(t("home.toast.batchCreatePartialError"));
      else toast.error(t("home.toast.batchCreateFailed"));
    },
  });
}
