import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import { normalizeGrade } from "@/i18n";
import {
  listClasses,
  createClass,
  updateClass,
  deleteClass,
} from "@/services/api";
import type { ClassRecord } from "@/types/api";

export type { ClassRecord };

export function useClasses(schoolLevel?: string, grade?: string) {
  const { user } = useAuth();

  return useQuery({
    queryKey: ["classes", user?.id, schoolLevel, grade],
    queryFn: () =>
      listClasses({
        ...(schoolLevel ? { school_level: schoolLevel } : {}),
        // 前端年级值是原始写法（一年级/七年级/高一），存库为规范值（小学一年级/初一/高一），需归一化后再查
        ...(grade ? { grade: normalizeGrade(grade) } : {}),
      }),
    enabled: !!user,
  });
}

export function useCreateClass() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async (params: {
      school_level: string;
      grade: string;
      name: string;
    }) => {
      // 存库用规范年级值（小学一年级/初一/高一），避免与读取时的归一化不一致
      return createClass({ ...params, grade: normalizeGrade(params.grade) });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["classes"] });
      toast.success(t("home.toast.classCreateSuccess"));
    },
    onError: (error: any) => {
      const msg = error?.message ?? "";
      if (msg.includes("该班级已存在")) {
        toast.error(t("home.toast.classCreateExists"));
      } else {
        toast.error(t("home.toast.classCreateFailed"));
      }
    },
  });
}

export function useUpdateClass() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async (params: { id: string; name: string }) => {
      return updateClass(params.id, { name: params.name });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["classes"] });
      toast.success(t("home.toast.classUpdateSuccess"));
    },
    onError: (error: any) => {
      const msg = error?.message ?? "";
      if (msg.includes("该班级名称已存在")) {
        toast.error(t("home.toast.classUpdateNameExists"));
      } else {
        toast.error(t("home.toast.classUpdateFailed"));
      }
    },
  });
}

export function useDeleteClass() {
  const queryClient = useQueryClient();
  const { t } = useLocale();

  return useMutation({
    mutationFn: async (id: string) => {
      await deleteClass(id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["classes"] });
      toast.success(t("home.toast.classDeleteSuccess"));
    },
    onError: () => {
      toast.error(t("home.toast.classDeleteFailed"));
    },
  });
}
