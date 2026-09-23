import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";
import { getLatestWrongQuestions } from "@/services/api";
import type { ClassWrongQuestionItem } from "@/services/api";

export type { ClassWrongQuestionItem } from "@/services/api";

export interface WrongQuestionQueryPair {
  studentId: string;
  studentName: string;
  subject: string;
}

/**
 * 聚合班级各学生最近一场考试的错题（GET /student-analysis/wrong-questions/latest）。
 *
 * /latest 为按（学生, 科目）返回最近一场考试错题，班级视角需逐对查询后合并；
 * 单对失败跳过（403 越权 / 500 异常不拖垮整班）。数据源为权威表 student_wrong_questions。
 */
export function useClassLatestWrongQuestions(
  classId: string | undefined,
  pairs: WrongQuestionQueryPair[],
) {
  const { user } = useAuth();

  const scopeKey = JSON.stringify(pairs.map((p) => [p.studentId, p.subject]));

  return useQuery({
    queryKey: ["class-latest-wrong-questions", classId, scopeKey],
    queryFn: async () => {
      let failed = 0;
      const results = await Promise.all(
        pairs.map(async (p) => {
          try {
            const res = await getLatestWrongQuestions(
              classId!,
              p.studentName,
              p.subject,
            );
            return (res.questions || []).map<ClassWrongQuestionItem>((q) => ({
              ...q,
              student_id: p.studentId,
              student_name: p.studentName,
              subject: p.subject,
              exam_name: res.exam_name,
              created_at: res.created_at,
            }));
          } catch {
            failed += 1;
            return [] as ClassWrongQuestionItem[];
          }
        }),
      );
      // 全部查询失败才抛错（如越权/服务异常），让 UI 走错误态；部分失败则返回已有结果
      if (pairs.length > 0 && failed === pairs.length) {
        throw new Error("错题查询失败");
      }
      return results.flat();
    },
    enabled: !!user && !!classId && pairs.length > 0,
  });
}
