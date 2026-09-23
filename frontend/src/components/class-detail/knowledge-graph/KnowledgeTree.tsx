import { useState, useMemo, useEffect } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { ChevronRight, ChevronDown, Search, Filter } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { EnrichedTreeNode } from "./classStats";

function getMasteryColor(m: number) {
  if (m >= 80) return "text-emerald-600";
  if (m >= 60) return "text-amber-500";
  if (m >= 50) return "text-orange-500";
  return "text-red-500";
}

function getMasteryDot(m: number) {
  if (m >= 80) return "bg-emerald-500";
  if (m >= 60) return "bg-amber-500";
  if (m >= 50) return "bg-orange-500";
  return "bg-red-500";
}

interface KnowledgeTreeProps {
  tree: EnrichedTreeNode[];
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  filterWeak: boolean;
  onFilterWeakChange: (v: boolean) => void;
  searchQuery: string;
  onSearchChange: (v: string) => void;
  hasAnyData: boolean;
}

export function KnowledgeTree({
  tree,
  selectedNodeId,
  onSelectNode,
  filterWeak,
  onFilterWeakChange,
  searchQuery,
  onSearchChange,
  hasAnyData,
}: KnowledgeTreeProps) {
  const { t } = useLocale();

  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(
    () => new Set(tree.map((t) => t.id)),
  );

  // 切换科目/班级后 tree 变化 → 重置为全部默认展开；
  // 同科目数据刷新（ids 未变）则保留用户的折叠状态
  useEffect(() => {
    setExpandedClusters((prev) => {
      const ids = new Set(tree.map((t) => t.id));
      if (ids.size === prev.size && tree.every((c) => prev.has(c.id))) {
        return prev;
      }
      return ids;
    });
  }, [tree]);

  const toggleCluster = (id: string) => {
    setExpandedClusters((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const filteredTree = useMemo(() => {
    return tree
      .map((cluster) => {
        let children = cluster.children;
        if (filterWeak)
          children = children.filter(
            (c) => c.hasData && c.mastery != null && c.mastery < 60,
          );
        if (searchQuery) {
          const q = searchQuery.toLowerCase();
          children = children.filter((c) => c.name.toLowerCase().includes(q));
        }
        return { ...cluster, children };
      })
      .filter((c) => c.children.length > 0 || (!filterWeak && !searchQuery));
  }, [tree, filterWeak, searchQuery]);

  return (
    <>
      {/* Header */}
      <div className="p-3 border-b border-border space-y-2">
        <h3 className="text-sm font-semibold text-foreground">
          {t("classDetail.知识点目录")}
        </h3>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            placeholder={t("classDetail.搜索知识点")}
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-7 h-8 text-xs"
          />
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Filter className="w-3 h-3" />
            {t("knowledge.tree.weakOnly")}
          </span>
          <Switch
            checked={filterWeak}
            onCheckedChange={onFilterWeakChange}
            disabled={!hasAnyData}
            className="scale-75"
          />
        </div>
      </div>

      {/* Tree */}
      <div className="p-2 space-y-0.5">
        {filteredTree.map((cluster) => (
          <div key={cluster.id}>
            {/* Cluster header */}
            <button
              onClick={() => toggleCluster(cluster.id)}
              className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md hover:bg-muted/60 text-left transition-colors"
            >
              {expandedClusters.has(cluster.id) ? (
                <ChevronDown className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
              )}
              <span className="text-xs font-medium text-foreground truncate flex-1">
                {cluster.name}
              </span>
              <span
                className={cn(
                  "text-xs font-mono",
                  cluster.mastery == null
                    ? "text-muted-foreground"
                    : getMasteryColor(cluster.mastery),
                )}
              >
                {cluster.mastery == null ? "—" : `${cluster.mastery}%`}
              </span>
            </button>

            {/* Children */}
            {expandedClusters.has(cluster.id) && (
              <div className="ml-3 pl-2 border-l border-border/50 space-y-0.5">
                {cluster.children.map((child) => (
                  <button
                    key={child.id}
                    onClick={() => onSelectNode(child.id)}
                    className={cn(
                      "w-full flex items-center gap-1.5 px-2 py-1 rounded-md text-left text-xs transition-all",
                      selectedNodeId === child.id
                        ? "bg-primary/10 text-primary font-medium"
                        : "hover:bg-muted/60 text-foreground/80",
                    )}
                  >
                    <span
                      className={cn(
                        "w-2 h-2 rounded-full flex-shrink-0",
                        child.hasData
                          ? getMasteryDot(child.mastery!)
                          : "bg-muted-foreground/40",
                      )}
                    />
                    <span className="truncate flex-1">{child.name}</span>
                    <span
                      className={cn(
                        "font-mono",
                        child.mastery == null
                          ? "text-muted-foreground"
                          : getMasteryColor(child.mastery),
                      )}
                    >
                      {child.mastery == null ? "—" : `${child.mastery}%`}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="p-2 border-t border-border flex flex-wrap gap-2 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          ≥80%
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-amber-500" />
          60-80%
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-orange-500" />
          50-60%
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-red-500" />
          &lt;50%
        </span>
      </div>
    </>
  );
}
