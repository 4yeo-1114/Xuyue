import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import {
  listStudentsByClass,
  createStudent,
  updateStudent,
  deleteStudent,
  clearStudents
} from "@/services/api";
import type { StudentInfo } from "@/types/api";

export type StudentRecord = StudentInfo;

function getErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "message" in error) {
    return String((error as { message?: unknown }).message ?? "");
  }
  return "";
}

export function useStudents(classId?: string) {
  const { user } = useAuth();

  return useQuery({
    queryKey: ["students", classId],
    queryFn: () => listStudentsByClass(classId!),
    enabled: !!user && !!classId,
  });
}

export function useCreateStudent() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async (params: { class_id: string; name: string; student_number?: string; gender?: string }) => {
      return createStudent(params);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["students", data.class_id] });
      queryClient.invalidateQueries({ queryKey: ["classes"] });
      toast.success(t("account.toast.studentCreateSuccess"));
    },
    onError: (error: unknown) => {
      const msg = getErrorMessage(error);
      if (msg.includes("该学号在本班已存在") || msg.includes("学号已存在")) toast.error(t("account.toast.studentDuplicate"));
      else toast.error(t("account.toast.studentCreateFailed"));
    },
  });
}

export function useUpdateStudent() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async (params: { id: string; class_id: string; patch: Partial<StudentRecord> }) => {
      return updateStudent(params.id, params.patch);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["students", variables.class_id] });
      toast.success(t("account.toast.studentUpdateSuccess"));
    },
    onError: (error: unknown) => {
      const msg = getErrorMessage(error);
      if (msg.includes("该学号在本班已存在") || msg.includes("学号已存在")) toast.error(t("account.toast.studentDuplicate"));
      else toast.error(t("account.toast.studentUpdateFailed"));
    },
  });
}

export function useDeleteStudent() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async (params: { id: string; class_id: string }) => {
      await deleteStudent(params.id);
      return params;
    },
    onSuccess: (params) => {
      queryClient.invalidateQueries({ queryKey: ["students", params.class_id] });
      queryClient.invalidateQueries({ queryKey: ["classes"] });
      toast.success(t("account.toast.studentDeleteSuccess"));
    },
    onError: () => {
      toast.error(t("account.toast.studentDeleteFailed"));
    },
  });
}

export function useClearStudents() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async (class_id: string) => {
      await clearStudents(class_id);
      return class_id;
    },
    onSuccess: (class_id) => {
      queryClient.invalidateQueries({ queryKey: ["students", class_id] });
      queryClient.invalidateQueries({ queryKey: ["classes"] });
      toast.success(t("account.toast.studentClearSuccess"));
    },
    onError: (error: any) => {
      toast.error(error.message || t("account.toast.studentClearFailed"));
    },
  });
}
