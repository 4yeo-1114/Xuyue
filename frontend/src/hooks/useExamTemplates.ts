import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "./useAuth";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import {
  listExamTemplates,
  createExamTemplate,
  updateExamTemplate,
  deleteExamTemplate,
  reorderExamTemplates,
  seedExamTemplates,
} from "@/services/api";
import type { ExamTemplate } from "@/services/api";

export type { ExamTemplate };

// Temporary fallback default question types
function getDefaultQuestionTypes(subject: string) {
  if (subject === "语文" || subject === "英语") {
    return [
      { type: "选择题", count: 10, scoreEach: 2 },
      { type: "填空题", count: 10, scoreEach: 2 },
      { type: "简答题", count: 5, scoreEach: 6 },
      { type: "作文", count: 1, scoreEach: 30 },
    ];
  }
  return [
    { type: "选择题", count: 15, scoreEach: 3 },
    { type: "填空题", count: 10, scoreEach: 2 },
    { type: "判断题", count: 10, scoreEach: 1 },
    { type: "简答题", count: 5, scoreEach: 5 },
  ];
}

export function useExamTemplates(subject: string) {
  const { user } = useAuth();
  const { t } = useLocale();
  const qc = useQueryClient();
  const key = ["exam_templates", subject];

  const {
    data: templates = [],
    isLoading,
    refetch,
  } = useQuery({
    queryKey: key,
    // enabled 条件保持：依赖登录态与学科（user_id 由后端从 token 取）
    enabled: !!user && !!subject,
    queryFn: () => listExamTemplates(subject),
  });

  const isEmpty = !isLoading && templates.length === 0;

  const create = useMutation({
    mutationFn: async (t: {
      type_name: string;
      default_count: number;
      default_score_each: number;
      sort_order: number;
    }) => {
      await createExamTemplate({ subject, ...t });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: key });
      toast.success(t("home.toast.templateCreateSuccess"));
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const update = useMutation({
    mutationFn: async (t: {
      id: string;
      type_name: string;
      default_count: number;
      default_score_each: number;
    }) => {
      await updateExamTemplate(t.id, {
        type_name: t.type_name,
        default_count: t.default_count,
        default_score_each: t.default_score_each,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: key });
      toast.success(t("home.toast.templateUpdateSuccess"));
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: async (id: string) => {
      await deleteExamTemplate(id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: key });
      toast.success(t("home.toast.templateDeleteSuccess"));
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const reorder = useMutation({
    mutationFn: async (orderedIds: string[]) => {
      await reorderExamTemplates(orderedIds);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: key });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const seedDefaults = useMutation({
    mutationFn: async (rawSubject: string) => {
      const defaults = getDefaultQuestionTypes(rawSubject);
      const rows = defaults.map((d, i) => ({
        type_name: d.type,
        default_count: d.count,
        default_score_each: d.scoreEach,
        sort_order: i,
      }));
      await seedExamTemplates(subject, rows);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: key });
      toast.success(t("home.toast.templateImportSuccess"));
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return {
    templates,
    isLoading,
    isEmpty,
    create,
    update,
    remove,
    reorder,
    seedDefaults,
    refetch,
  };
}
