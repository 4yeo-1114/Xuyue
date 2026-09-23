import { useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import {
  Presentation,
  Target,
  FileText,
  Sparkles,
  ArrowLeft,
  ArrowRight,
  Link2,
  Video,
  FileStack,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { EnrichedNode, EnrichedGraphData } from "./classStats";
import {
  KGInlineTip,
  KGTipChart,
  KGTipUsers,
  KGTipBook,
} from "./KnowledgeGraphTour";

interface KnowledgeDetailPanelProps {
  node: EnrichedNode | null;
  graphData: EnrichedGraphData;
  onNavChange: (id: string) => void;
  onSelectNode: (id: string | null) => void;
}

function getMasteryColor(m: number) {
  if (m >= 80) return "text-emerald-600";
  if (m >= 60) return "text-amber-500";
  if (m >= 50) return "text-orange-500";
  return "text-red-500";
}

export function KnowledgeDetailPanel({
  node,
  graphData,
  onNavChange,
  onSelectNode,
}: KnowledgeDetailPanelProps) {
  const { t } = useLocale();

  const prereqs = useMemo(() => {
    if (!node) return [];
    return node.prerequisites
      .map((id) => graphData.nodes.find((n) => n.id === id))
      .filter(Boolean) as EnrichedNode[];
  }, [node, graphData]);

  const followups = useMemo(() => {
    if (!node) return [];
    return node.followups
      .map((id) => graphData.nodes.find((n) => n.id === id))
      .filter(Boolean) as EnrichedNode[];
  }, [node, graphData]);

  const related = useMemo(() => {
    if (!node) return [];
    return graphData.links
      .filter(
        (l) =>
          l.type === "parallel" &&
          (l.source === node.id || l.target === node.id),
      )
      .map((l) => {
        const otherId = l.source === node.id ? l.target : l.source;
        return graphData.nodes.find((n) => n.id === otherId);
      })
      .filter(Boolean) as EnrichedNode[];
  }, [node, graphData]);

  if (!node) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-6">
        <BookOpen className="w-10 h-10 mb-3 opacity-30" />
        <p className="text-sm text-center">
          {t("knowledge.detail.hintLine1")}
          <br />
          {t("knowledge.detail.hintLine2")}
        </p>
      </div>
    );
  }

  const hasMastery = node.hasData && node.mastery != null;

  return (
    <div className="p-4 space-y-4">
      {/* Mastery tip */}
      {hasMastery ? (
        <KGInlineTip
          id={`kg-mastery-${node.id}`}
          icon={KGTipChart}
          text={t("knowledge.detail.masteryTip", {
            name: node.name,
            mastery: node.mastery,
          })}
          type={node.mastery! < 60 ? "warning" : "hint"}
          show={true}
        />
      ) : (
        <KGInlineTip
          id={`kg-mastery-none-${node.id}`}
          icon={KGTipChart}
          text={t("knowledge.detail.needReportHint")}
          type="info"
          show={true}
        />
      )}

      {/* Header */}
      <div>
        <div className="text-xs text-muted-foreground">{node.cluster}</div>
        <h3 className="text-base font-semibold text-foreground">{node.name}</h3>
      </div>

      {/* Core metrics */}
      <div className="space-y-2 p-3 rounded-lg bg-muted/50">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            {t("knowledge.detail.mastery")}
          </span>
          {hasMastery ? (
            <span
              className={cn(
                "text-lg font-bold",
                getMasteryColor(node.mastery!),
              )}
            >
              {node.mastery}%
            </span>
          ) : (
            <span className="text-lg font-bold text-muted-foreground">
              {t("knowledge.noMastery")}
            </span>
          )}
        </div>
        {hasMastery && <Progress value={node.mastery!} className="h-2" />}
        {hasMastery ? (
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {node.dataSource === "cluster"
                ? t("knowledge.detail.masteryFromCluster", {
                    cluster: node.cluster,
                  })
                : t("knowledge.detail.dataFromReport")}
            </span>
            <span>{t("knowledge.detail.hours", { hours: node.hours })}</span>
          </div>
        ) : (
          <div className="flex items-center justify-end text-xs text-muted-foreground">
            <span>{t("knowledge.detail.hours", { hours: node.hours })}</span>
          </div>
        )}
      </div>

      {/* Question stats */}
      <div className="space-y-1.5 p-3 rounded-lg border border-border">
        <h4 className="text-xs font-medium text-foreground">
          {t("knowledge.detail.questions")}
        </h4>
        <div className="text-xs text-muted-foreground">
          {node.evidenceCount > 0
            ? t("knowledge.detail.questionsCount", {
                count: node.evidenceCount,
              })
            : t("knowledge.detail.noQuestions")}
        </div>
      </div>

      {/* Weak students */}
      <div
        data-tour="kg-students"
        className="space-y-1.5 p-3 rounded-lg border border-border"
      >
        {node.weakCount != null && node.weakCount >= 5 && (
          <KGInlineTip
            id={`kg-students-${node.id}`}
            icon={KGTipUsers}
            text={t("knowledge.detail.weakStudentsTip", {
              count: node.weakCount,
            })}
            type="amber"
            show={true}
          />
        )}
        <h4 className="text-xs font-medium text-foreground">
          {t("classDetail.学生分布")}
        </h4>
        <div className="text-xs text-muted-foreground">
          {node.weakCount != null
            ? t("knowledge.detail.weakStudentsCount", { count: node.weakCount })
            : t("knowledge.detail.noWeakData")}
        </div>
        {node.weakSeverity && (
          <div className="text-xs text-muted-foreground">
            {t("knowledge.detail.weakSeverity", {
              level: t(`classAnalysis.severity.${node.weakSeverity}`),
            })}
          </div>
        )}
        {node.weakCount != null && node.weakCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full mt-1 text-xs text-primary h-7"
            onClick={() => onNavChange("class-students")}
          >
            {t("knowledge.detail.viewWeakList")}
          </Button>
        )}
      </div>

      {/* Prerequisites & followups */}
      {(prereqs.length > 0 || followups.length > 0) && (
        <div className="space-y-1.5 p-3 rounded-lg border border-border">
          {prereqs.length > 0 && (
            <>
              <h4 className="text-xs font-medium text-foreground">
                {t("knowledge.detail.prereq")}
              </h4>
              {prereqs[0].hasData && prereqs[0].mastery != null && (
                <KGInlineTip
                  id={`kg-prereq-${node.id}`}
                  icon={KGTipBook}
                  text={t("knowledge.detail.prereqTip", {
                    name: prereqs[0].name,
                    mastery: prereqs[0].mastery,
                    status:
                      prereqs[0].mastery >= 70
                        ? t("knowledge.detail.baselineOk")
                        : t("classDetail.需要补强"),
                  })}
                  type={prereqs[0].mastery >= 70 ? "hint" : "amber"}
                  show={true}
                />
              )}
              {prereqs.map((n) => (
                <button
                  key={n.id}
                  onClick={() => onSelectNode(n.id)}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary transition-colors w-full text-left"
                >
                  <ArrowLeft className="w-3 h-3" />
                  <span className="flex-1">{n.name}</span>
                  {n.hasData && n.mastery != null ? (
                    <span
                      className={cn("font-mono", getMasteryColor(n.mastery))}
                    >
                      {n.mastery}%
                    </span>
                  ) : (
                    <span className="font-mono">—</span>
                  )}
                </button>
              ))}
            </>
          )}
          {followups.length > 0 && (
            <>
              <h4 className="text-xs font-medium text-foreground mt-2">
                {t("knowledge.detail.followup")}
              </h4>
              {followups.map((n) => (
                <button
                  key={n.id}
                  onClick={() => onSelectNode(n.id)}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary transition-colors w-full text-left"
                >
                  <ArrowRight className="w-3 h-3" />
                  <span className="flex-1">{n.name}</span>
                  {n.hasData && n.mastery != null ? (
                    <span
                      className={cn("font-mono", getMasteryColor(n.mastery))}
                    >
                      {n.mastery}%
                    </span>
                  ) : (
                    <span className="font-mono">—</span>
                  )}
                </button>
              ))}
            </>
          )}
        </div>
      )}

      {/* Related knowledge */}
      {related.length > 0 && (
        <div className="space-y-1.5 p-3 rounded-lg border border-border">
          <h4 className="text-xs font-medium text-foreground">
            {t("knowledge.detail.related")}
          </h4>
          {related.map((n) => (
            <button
              key={n.id}
              onClick={() => onSelectNode(n.id)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary transition-colors w-full text-left"
            >
              <Link2 className="w-3 h-3" />
              <span className="flex-1">{n.name}</span>
              {n.hasData && n.mastery != null ? (
                <span className={cn("font-mono", getMasteryColor(n.mastery))}>
                  {n.mastery}%
                </span>
              ) : (
                <span className="font-mono">—</span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Resources */}
      <div
        data-tour="kg-resources"
        className="space-y-1.5 p-3 rounded-lg border border-border"
      >
        <h4 className="text-xs font-medium text-foreground">
          {t("classDetail.推荐资源")}
        </h4>
        <div className="space-y-1 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <Video className="w-3 h-3" />
            {t("knowledge.detail.resourceMicro", { name: node.name })}
          </div>
          <div className="flex items-center gap-1.5">
            <FileStack className="w-3 h-3" />
            {node.evidenceCount > 0
              ? t("knowledge.detail.resourcePractice", {
                  count: node.evidenceCount,
                })
              : t("knowledge.detail.resourcePracticeNone")}
          </div>
          <div className="flex items-center gap-1.5">
            <FileText className="w-3 h-3" />
            {t("knowledge.detail.resourceLesson")}
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div data-tour="kg-actions" className="grid grid-cols-2 gap-2">
        <Button
          size="sm"
          variant="outline"
          className="text-xs h-8"
          onClick={() => onNavChange("ai-review")}
        >
          <Presentation className="w-3 h-3 mr-1" />{" "}
          {t("knowledge.detail.addToReview")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="text-xs h-8"
          onClick={() => onNavChange("ai-targeted")}
        >
          <Target className="w-3 h-3 mr-1" />{" "}
          {t("knowledge.detail.pushPractice")}
        </Button>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex cursor-not-allowed">
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-8"
                disabled
              >
                <FileText className="w-3 h-3 mr-1" />{" "}
                {t("knowledge.detail.viewOriginal")}
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <p>{t("knowledge.detail.viewOriginalTip")}</p>
          </TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex cursor-not-allowed">
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-8"
                disabled
              >
                <Sparkles className="w-3 h-3 mr-1" />{" "}
                {t("knowledge.detail.variants")}
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <p>{t("knowledge.detail.variantsTip")}</p>
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
