import { useState, useMemo, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { useAdminAuth } from "@/hooks/useAdminAuth";
import { getKnowledgeGraph, buildTree } from "@/data/knowledgeGraphData";
import { getClassAnalysisReport } from "@/services/api";
import { getMasteryDistribution } from "@/services/dashboardApi";
import {
  buildClassStats,
  buildMasteryMap,
  enrichGraphData,
  buildEnrichedTree,
} from "./knowledge-graph/classStats";
import { KnowledgeTree } from "./knowledge-graph/KnowledgeTree";
import { RadialGraph } from "./knowledge-graph/RadialGraph";
import { KnowledgeDetailPanel } from "./knowledge-graph/KnowledgeDetailPanel";
import {
  KnowledgeGraphTour,
  KGTipProvider,
  KGInlineTip,
  KGTipAlert,
  KGTipLightbulb,
  KGTipChart,
} from "./knowledge-graph/KnowledgeGraphTour";
import { Button } from "@/components/ui/button";

interface KnowledgeGraphPageProps {
  selectedSubject: string;
  selectedClass: string;
  schoolLevel: string;
  onNavChange: (id: string) => void;
}

export function KnowledgeGraphPage({
  selectedSubject,
  selectedClass,
  schoolLevel,
  onNavChange,
}: KnowledgeGraphPageProps) {
  const { t } = useLocale();
  const { schoolId } = useAdminAuth();

  // 真实班级分析报告（audit #32：替换伪随机 mock）
  const reportQuery = useQuery({
    queryKey: ["class-knowledge", selectedClass, selectedSubject],
    queryFn: () => getClassAnalysisReport(selectedClass, selectedSubject),
    enabled: !!selectedClass && !!selectedSubject,
  });
  const report = reportQuery.data?.report ?? null;

  // 掌握度真实化（BE-1）：错题分布派生口径，班级维度（school_id 必填）
  const masteryDistQuery = useQuery({
    queryKey: ["mastery-distribution", schoolId, "class", selectedClass],
    queryFn: () =>
      getMasteryDistribution(schoolId!, { class_id: selectedClass }),
    enabled: !!schoolId && !!selectedClass,
  });

  const graphData = useMemo(
    () => getKnowledgeGraph(schoolLevel, selectedSubject),
    [schoolLevel, selectedSubject],
  );

  const classStats = useMemo(() => {
    const masteryByNode = buildMasteryMap(
      masteryDistQuery.data ?? [],
      graphData.nodes,
    );
    return buildClassStats(report, graphData.nodes, masteryByNode);
  }, [report, graphData, masteryDistQuery.data]);

  const enrichedData = useMemo(
    () => enrichGraphData(graphData, classStats),
    [graphData, classStats],
  );

  const tree = useMemo(() => buildTree(graphData), [graphData]);
  const enrichedTree = useMemo(
    () => buildEnrichedTree(tree, classStats),
    [tree, classStats],
  );

  const hasAnyData = useMemo(
    () => Array.from(classStats.values()).some((s) => s.mastery != null),
    [classStats],
  );

  const overallMastery = useMemo(() => {
    const withData = enrichedData.nodes.filter(
      (n) => n.hasData && n.mastery != null,
    );
    if (withData.length === 0) return null;
    return Math.round(
      withData.reduce((s, n) => s + (n.mastery as number), 0) / withData.length,
    );
  }, [enrichedData]);

  const weakCount = useMemo(
    () =>
      enrichedData.nodes.filter(
        (n) => n.hasData && n.mastery != null && n.mastery < 60,
      ).length,
    [enrichedData],
  );

  const initialNodeId = useMemo(() => {
    for (const cluster of enrichedTree) {
      if (cluster.children.length > 0) return cluster.children[0].id;
    }
    return null;
  }, [enrichedTree]);

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    initialNodeId,
  );

  useEffect(() => {
    setSelectedNodeId(initialNodeId);
  }, [initialNodeId]);

  const [filterWeak, setFilterWeak] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const selectedNode = useMemo(
    () => enrichedData.nodes.find((n) => n.id === selectedNodeId) ?? null,
    [enrichedData, selectedNodeId],
  );

  const handleSelectNode = useCallback((id: string | null) => {
    setSelectedNodeId(id);
  }, []);

  const isLoading = reportQuery.isLoading && !reportQuery.data;
  const isError = reportQuery.isError;
  const isEmpty = !selectedClass || report == null || !hasAnyData;

  return (
    <KGTipProvider>
      <KnowledgeGraphTour />

      {/* 顶部状态条：loading / error / empty */}
      <div className="mb-2 space-y-2">
        {isLoading && (
          <KGInlineTip
            id="kg-loading"
            icon={KGTipChart}
            text={`${t("knowledge.loading.title")} · ${t("knowledge.loading.hint")}`}
            type="info"
            show={true}
          />
        )}
        {isError && (
          <div className="flex items-center gap-3 px-4 py-2 rounded-xl text-sm bg-red-50 border-l-4 border-l-red-500 text-red-900">
            <KGTipAlert className="w-4 h-4 shrink-0 opacity-70" />
            <span className="flex-1">{t("knowledge.error.title")}</span>
            <Button
              size="sm"
              variant="outline"
              className="text-xs h-7 shrink-0"
              onClick={() => reportQuery.refetch()}
            >
              {t("knowledge.error.retry")}
            </Button>
          </div>
        )}
        {!isLoading && !isError && isEmpty && (
          <div className="flex items-center gap-3 px-4 py-2 rounded-xl text-sm bg-amber-50 border-l-4 border-l-amber-500 text-amber-900">
            <KGTipAlert className="w-4 h-4 shrink-0 opacity-70" />
            <div className="flex-1">
              <div className="font-medium">{t("knowledge.empty.title")}</div>
              <div className="text-xs opacity-80">
                {t("knowledge.empty.description", { subject: selectedSubject })}
              </div>
            </div>
            <Button
              size="sm"
              variant="outline"
              className="text-xs h-7 shrink-0"
              onClick={() => onNavChange("analytics-portrait")}
            >
              {t("knowledge.empty.action")}
            </Button>
          </div>
        )}
        {/* 薄弱点概览 */}
        {!isLoading && !isError && !isEmpty && (
          <KGInlineTip
            id="kg-weak-overview"
            icon={KGTipAlert}
            text={t("classDetail.kgWeakPointsTip", { count: weakCount })}
            type="warning"
            show={weakCount > 0}
          />
        )}
      </div>

      <div className="flex flex-col gap-0 rounded-xl border border-border bg-card shadow-sm lg:flex-row">
        {/* Left: Knowledge Tree */}
        <div
          data-tour="kg-tree"
          className="w-full lg:w-[20%] lg:min-w-[220px] border-b lg:border-b-0 lg:border-r border-border bg-card flex flex-col"
        >
          {/* Filter tip */}
          {filterWeak && (
            <KGInlineTip
              id="kg-filter-active"
              icon={KGTipLightbulb}
              text={t("classDetail.已筛选薄弱点 点击节点查看建议")}
              type="info"
              show={true}
            />
          )}
          <KnowledgeTree
            tree={enrichedTree}
            selectedNodeId={selectedNodeId}
            onSelectNode={handleSelectNode}
            filterWeak={filterWeak}
            onFilterWeakChange={setFilterWeak}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            hasAnyData={hasAnyData}
          />
        </div>

        {/* Center: Radial Graph */}
        <div
          data-tour="kg-radial"
          className="w-full h-[600px] lg:h-auto lg:flex-1 lg:min-w-0 bg-[hsl(var(--muted)/0.3)] relative min-h-[600px]"
        >
          <RadialGraph
            data={enrichedData}
            selectedNodeId={selectedNodeId}
            onSelectNode={handleSelectNode}
            overallMastery={overallMastery}
            filterWeak={filterWeak}
            searchQuery={searchQuery}
            schoolLevel={schoolLevel}
            selectedSubject={selectedSubject}
          />
        </div>

        {/* Right: Detail Panel */}
        <div
          data-tour="kg-detail"
          className="w-full lg:w-[25%] lg:min-w-[260px] border-t lg:border-t-0 lg:border-l border-border bg-card flex flex-col"
        >
          <KnowledgeDetailPanel
            node={selectedNode}
            graphData={enrichedData}
            onNavChange={onNavChange}
            onSelectNode={handleSelectNode}
          />
        </div>
      </div>
    </KGTipProvider>
  );
}
