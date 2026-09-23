import { useMemo } from "react";
import { BookOpen } from "lucide-react";
import type { KnowledgeGraphData } from "@/data/knowledgeGraphData";
import {
  matchKnowledgeLecture,
  resolveNodeNames,
} from "@/services/knowledgeLecture";
import { Card, CardContent } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { cn } from "@/lib/utils";

interface KnowledgeLectureCardProps {
  /** 单个知识点（来自错题详情的 knowledge_points） */
  kp: string;
  /** 静态知识图谱；schoolLevel/subject 缺失时为 null，则只展示知识点名 */
  graph: KnowledgeGraphData | null;
  className?: string;
}

/**
 * 错题知识点串讲卡片。
 *
 * 三种状态：
 * 1. graph 为空（未拿到 schoolLevel/subject）→ 仅展示知识点原始名 + 提示
 * 2. 匹配到图节点 → 展示每个命中节点的串讲信息（cluster / level / mastery / 前置 / 后续）
 * 3. 未匹配 → 展示知识点原始名 + 「暂未映射到知识图谱」提示
 */
export function KnowledgeLectureCard({
  kp,
  graph,
  className,
}: KnowledgeLectureCardProps) {
  const { t } = useLocale();
  const match = useMemo(() => matchKnowledgeLecture(kp, graph), [kp, graph]);

  if (!graph) {
    return (
      <Card className={cn("border-border/50 shadow-sm bg-muted/20", className)}>
        <CardContent className="p-3 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{kp}</span>
          <span className="ml-2">
            {t("grading.errorBook.knowledge.noGraph")}
          </span>
        </CardContent>
      </Card>
    );
  }

  if (!match.matched) {
    return (
      <Card className={cn("border-border/50 shadow-sm bg-muted/20", className)}>
        <CardContent className="p-3 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{kp}</span>
          <span className="ml-2">
            {t("grading.errorBook.knowledge.notMapped")}
          </span>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <BookOpen className="h-4 w-4 text-primary" />
        {t("grading.errorBook.knowledge.lectureTitle")}
        <span className="font-normal text-muted-foreground">· {kp}</span>
      </div>
      {match.nodes.map((node) => {
        const prereqNames = resolveNodeNames(graph, node.prerequisites);
        const followupNames = resolveNodeNames(graph, node.followups);
        return (
          <Card key={node.id} className="border-border/50 shadow-sm">
            <CardContent className="space-y-2 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-foreground">
                    {node.name}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {t("grading.errorBook.knowledge.cluster")}: {node.cluster}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-3 text-xs">
                  <span className="text-muted-foreground">
                    {t("grading.errorBook.knowledge.level")} {node.level}
                  </span>
                  <span className="rounded bg-primary/10 px-2 py-0.5 font-semibold text-primary">
                    {t("grading.errorBook.knowledge.mastery")} {node.mastery}%
                  </span>
                </div>
              </div>

              <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-xs">
                <div className="flex items-start gap-1.5">
                  <span className="shrink-0 text-muted-foreground">
                    {t("grading.errorBook.knowledge.prereq")}:
                  </span>
                  {prereqNames.length > 0 ? (
                    <span className="flex flex-wrap gap-1">
                      {prereqNames.map((name) => (
                        <span
                          key={name}
                          className="rounded bg-muted/60 px-1.5 py-0.5 text-foreground/80"
                        >
                          {name}
                        </span>
                      ))}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">
                      {t("grading.errorBook.knowledge.nonePrereq")}
                    </span>
                  )}
                </div>
                <div className="flex items-start gap-1.5">
                  <span className="shrink-0 text-muted-foreground">
                    {t("grading.errorBook.knowledge.followup")}:
                  </span>
                  {followupNames.length > 0 ? (
                    <span className="flex flex-wrap gap-1">
                      {followupNames.map((name) => (
                        <span
                          key={name}
                          className="rounded bg-muted/60 px-1.5 py-0.5 text-foreground/80"
                        >
                          {name}
                        </span>
                      ))}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">
                      {t("grading.errorBook.knowledge.noneFollowup")}
                    </span>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
