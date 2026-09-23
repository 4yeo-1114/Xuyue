import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { toast } from "@/hooks/use-toast";
import type {
  KnowledgePoint,
  Unit,
} from "@/components/settings/subject-config/subjectConfigData";
import { getSubjectConfig } from "@/components/settings/subject-config/subjectConfigData";
import type { KPRow, UnitRow } from "@/services/api";
import {
  createKnowledgePoint,
  deleteKnowledgePoint,
  listKnowledgeData,
  seedKnowledgeData,
  updateKnowledgePoint,
} from "@/services/api";

function rowToKP(r: KPRow): KnowledgePoint {
  return {
    id: r.id,
    code: r.code,
    name: r.name,
    unitId: r.unit_id,
    level: r.level as KnowledgePoint["level"],
    mastery: r.mastery,
    isWeak: r.is_weak,
    prerequisite: r.prerequisite ?? [],
    postrequisite: r.postrequisite ?? [],
    related: r.related ?? [],
    hours: r.hours,
    keyPoint: r.key_point,
    difficulty: r.difficulty,
    commonErrors: r.common_errors,
    resources: (r.resources as any) ?? [],
  };
}

function rowToUnit(r: UnitRow, kps: KnowledgePoint[]): Unit {
  return {
    id: r.id,
    index: r.unit_index,
    name: r.name,
    subtitle: r.subtitle,
    knowledgePoints: kps.filter((k) => k.unitId === r.id),
  };
}

export function useKnowledgeData(subject: string, semester: string) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const SUBJECT = subject;
  const SEMESTER = semester;
  const queryKey = ["knowledge-data", user?.id, subject, semester];

  const query = useQuery({
    queryKey,
    enabled: !!user,
    queryFn: async (): Promise<{ units: Unit[]; isEmpty: boolean }> => {
      const data = await listKnowledgeData(SUBJECT, SEMESTER);
      if (data.isEmpty) {
        return { units: [], isEmpty: true };
      }
      const kps = (data.kps ?? []).map(rowToKP);
      const units = (data.units ?? []).map((u) => rowToUnit(u, kps));
      return { units, isEmpty: false };
    },
  });

  // Seed mock data into DB
  const seedMutation = useMutation({
    mutationFn: async () => {
      if (!user) throw new Error("Not authenticated");
      const mock = getSubjectConfig(SUBJECT);

      // 后端按当前登录用户写入 user_id，这里只组装原始 mock 结构
      await seedKnowledgeData({
        subject: SUBJECT,
        semester: SEMESTER,
        units: mock.units.map((u) => ({
          unit_index: u.index,
          name: u.name,
          subtitle: u.subtitle,
          knowledgePoints: u.knowledgePoints.map((kp) => ({
            code: kp.code,
            name: kp.name,
            level: kp.level,
            mastery: kp.mastery,
            is_weak: kp.isWeak,
            prerequisite: kp.prerequisite,
            postrequisite: kp.postrequisite,
            related: kp.related,
            hours: kp.hours,
            key_point: kp.keyPoint,
            difficulty: kp.difficulty,
            common_errors: kp.commonErrors,
            resources: kp.resources as any,
          })),
        })),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
      toast({ title: "初始化成功", description: "已导入默认知识点数据" });
    },
    onError: (e: any) => {
      toast({
        title: "初始化失败",
        description: e.message,
        variant: "destructive",
      });
    },
  });

  // Create knowledge point
  const createKP = useMutation({
    mutationFn: async (data: {
      unitId: string;
      code: string;
      name: string;
      level: string;
    }) => {
      await createKnowledgePoint({
        unit_id: data.unitId,
        code: data.code,
        name: data.name,
        level: data.level,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
      toast({ title: "知识点已创建" });
    },
    onError: (e: any) =>
      toast({
        title: "创建失败",
        description: e.message,
        variant: "destructive",
      }),
  });

  // Update knowledge point
  const updateKP = useMutation({
    mutationFn: async (data: Partial<KPRow> & { id: string }) => {
      const { id, ...rest } = data;
      await updateKnowledgePoint(id, rest);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
      toast({ title: "知识点已更新" });
    },
    onError: (e: any) =>
      toast({
        title: "更新失败",
        description: e.message,
        variant: "destructive",
      }),
  });

  // Delete knowledge point
  const deleteKP = useMutation({
    mutationFn: async (id: string) => {
      await deleteKnowledgePoint(id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
      toast({ title: "知识点已删除" });
    },
    onError: (e: any) =>
      toast({
        title: "删除失败",
        description: e.message,
        variant: "destructive",
      }),
  });

  return {
    units: query.data?.units ?? [],
    isEmpty: query.data?.isEmpty ?? false,
    isLoading: query.isLoading,
    seed: seedMutation.mutate,
    isSeeding: seedMutation.isPending,
    createKP,
    updateKP,
    deleteKP,
  };
}
