import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { importStudents, globalImportStudents } from "@/services/api";
import { useLocale } from "@/contexts/LocaleContext";

export function useImportStudents() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async ({ classId, file }: { classId: string; file: File }) => {
      return importStudents(classId, file);
    },
    onSuccess: (count, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["students", variables.classId],
      });
      queryClient.invalidateQueries({ queryKey: ["classes"] });
      toast.success(t("account.toast.studentImportSuccess", { count }));
    },
    onError: (error: any) => {
      toast.error(error.message || t("account.toast.studentImportFailed"));
    },
  });
}

export function useGlobalImportStudents() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async ({
      file,
      classId,
    }: {
      file: File;
      classId?: string;
    }) => {
      return globalImportStudents(file, classId);
    },
    onSuccess: (count) => {
      queryClient.invalidateQueries({ queryKey: ["students"] });
      queryClient.invalidateQueries({ queryKey: ["classes"] });
      toast.success(t("account.toast.studentImportSuccess", { count }));
    },
    onError: (error: any) => {
      toast.error(error.message || t("account.toast.studentImportFailed"));
    },
  });
}
