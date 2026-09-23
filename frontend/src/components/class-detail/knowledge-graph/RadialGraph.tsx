import { useMemo, useState, useRef, useCallback, useEffect } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { cn } from "@/lib/utils";
import type { EnrichedGraphData, EnrichedNode } from "./classStats";

interface RadialGraphProps {
  data: EnrichedGraphData;
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  overallMastery: number | null;
  filterWeak: boolean;
  searchQuery: string;
  schoolLevel: string;
  selectedSubject: string;
}

const RING_RADII = { 1: 120, 2: 210, 3: 290 };
const CX = 400;
const CY = 400;
const SVG_SIZE = 800;

function getMasteryFill(m: number) {
  if (m >= 80) return "#22c55e";
  if (m >= 60) return "#eab308";
  if (m >= 50) return "#f97316";
  return "#ef4444";
}

function getMasteryStroke(m: number) {
  if (m >= 80) return "#16a34a";
  if (m >= 60) return "#ca8a04";
  if (m >= 50) return "#ea580c";
  return "#dc2626";
}

export function RadialGraph({
  data,
  selectedNodeId,
  onSelectNode,
  overallMastery,
  filterWeak,
  searchQuery,
  schoolLevel,
  selectedSubject,
}: RadialGraphProps) {
  const { t } = useLocale();

  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [transform, setTransform] = useState({ scale: 1, rotation: 0 });
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<{ startX: number; startRotation: number } | null>(
    null,
  );
  // 拖拽旋转每帧 setTransform 会触发全图约 100 节点重渲染；用 rAF 合帧到每动画帧一次
  const rafRef = useRef<number | null>(null);
  const pendingRotationRef = useRef<number | null>(null);
  // React 的 onWheel 在根节点以 passive 方式注册，preventDefault 无效；
  // 改用原生非 passive 监听（addEventListener { passive:false }），保证缩放不带动页面滚动
  const wheelRef = useRef<HTMLDivElement>(null);

  // Position nodes in radial layout
  const nodePositions = useMemo(() => {
    const positions = new Map<
      string,
      { x: number; y: number; node: EnrichedNode }
    >();
    const ringGroups: Record<number, EnrichedNode[]> = { 1: [], 2: [], 3: [] };

    for (const node of data.nodes) {
      ringGroups[node.ring].push(node);
    }

    for (const ring of [1, 2, 3] as const) {
      const nodes = ringGroups[ring];
      const radius = RING_RADII[ring];
      nodes.forEach((node, i) => {
        const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
        positions.set(node.id, {
          x: CX + radius * Math.cos(angle),
          y: CY + radius * Math.sin(angle),
          node,
        });
      });
    }

    return positions;
  }, [data]);

  // Filter dimming
  const isDimmed = useCallback(
    (node: EnrichedNode) => {
      // 无数据节点在“只看薄弱点”时一律暗（排除在薄弱之外）
      if (filterWeak && (!node.hasData || node.mastery == null)) return true;
      if (filterWeak && node.mastery != null && node.mastery >= 60) return true;
      if (
        searchQuery &&
        !node.name.toLowerCase().includes(searchQuery.toLowerCase())
      )
        return true;
      return false;
    },
    [filterWeak, searchQuery],
  );

  // Mouse handlers for rotation
  const handleMouseDown = (e: React.MouseEvent) => {
    if (
      e.target instanceof SVGCircleElement ||
      e.target instanceof SVGTextElement
    )
      return;
    dragRef.current = { startX: e.clientX, startRotation: transform.rotation };
  };

  const flushRotation = useCallback(() => {
    rafRef.current = null;
    const target = pendingRotationRef.current;
    if (target == null) return;
    pendingRotationRef.current = null;
    setTransform((prev) =>
      Math.abs(prev.rotation - target) < 0.01
        ? prev
        : { ...prev, rotation: target },
    );
  }, []);

  const scheduleRotation = useCallback(
    (rotation: number) => {
      pendingRotationRef.current = rotation;
      if (rafRef.current == null) {
        rafRef.current = requestAnimationFrame(flushRotation);
      }
    },
    [flushRotation],
  );

  const handleMouseMove = (e: React.MouseEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    const delta = (e.clientX - drag.startX) * 0.3;
    scheduleRotation(drag.startRotation + delta);
  };

  const handleMouseUp = () => {
    dragRef.current = null;
  };

  useEffect(() => {
    const el = wheelRef.current;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      setTransform((prev) => ({
        ...prev,
        scale: Math.max(0.5, Math.min(2, prev.scale - e.deltaY * 0.001)),
      }));
    };
    if (el) el.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      if (el) el.removeEventListener("wheel", onWheel);
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const nodeRadius = (node: EnrichedNode) => 12 + (node.weight / 15) * 8;

  return (
    <div className="w-full h-full flex flex-col">
      {/* Top bar with legend */}
      <div className="flex flex-col gap-0.5 px-4 py-2.5 border-b border-border/50 bg-card/50 backdrop-blur-sm">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold text-foreground">
            {t("knowledge.radial.title")} · {schoolLevel}
            {selectedSubject}
          </div>
          <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <span className="w-6 h-[2px] bg-foreground/40" />{" "}
              {t("knowledge.radial.prereq")}
            </span>
            <span className="flex items-center gap-1">
              <span
                className="w-6 h-[2px] bg-foreground/20 border-t border-dashed border-foreground/40"
                style={{ borderStyle: "dashed" }}
              />{" "}
              {t("knowledge.radial.followup")}
            </span>
            <span className="flex items-center gap-1">
              <svg width="20" height="8">
                <path
                  d="M0 4 Q10 0 20 4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1"
                  opacity="0.4"
                />
              </svg>
              {t("knowledge.radial.parallel")}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>
            {t("knowledge.radial.nodeCount", { count: data.totalNodes })}
          </span>
          <span>·</span>
          {overallMastery == null ? (
            <span>{t("knowledge.radial.classMasteryNone")}</span>
          ) : (
            <span>
              {t("knowledge.radial.classMastery", { value: overallMastery })}
            </span>
          )}
          <span className="ml-auto text-[10px] opacity-60">
            {t("knowledge.radial.navHint")}
          </span>
        </div>
      </div>

      {/* SVG Canvas */}
      <div
        ref={wheelRef}
        className="flex-1 overflow-hidden cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${SVG_SIZE} ${SVG_SIZE}`}
          className="w-full h-full"
          style={{
            transform: `scale(${transform.scale})`,
            transformOrigin: "center",
          }}
        >
          <defs>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          <g transform={`rotate(${transform.rotation}, ${CX}, ${CY})`}>
            {/* Ring guides */}
            {([1, 2, 3] as const).map((ring) => (
              <circle
                key={ring}
                cx={CX}
                cy={CY}
                r={RING_RADII[ring]}
                fill="none"
                stroke="hsl(var(--border))"
                strokeWidth="1"
                strokeDasharray="4 4"
                opacity="0.3"
              />
            ))}

            {/* Ring labels */}
            <text
              x={CX + RING_RADII[1] + 5}
              y={CY - 5}
              fontSize="10"
              fill="hsl(var(--muted-foreground))"
              opacity="0.5"
            >
              {t("classDetail.基础")}
            </text>
            <text
              x={CX + RING_RADII[2] + 5}
              y={CY - 5}
              fontSize="10"
              fill="hsl(var(--muted-foreground))"
              opacity="0.5"
            >
              {t("knowledge.radial.core")}
            </text>
            <text
              x={CX + RING_RADII[3] + 5}
              y={CY - 5}
              fontSize="10"
              fill="hsl(var(--muted-foreground))"
              opacity="0.5"
            >
              {t("classDetail.拓展")}
            </text>

            {/* Links */}
            {data.links.map((link, i) => {
              const source = nodePositions.get(link.source);
              const target = nodePositions.get(link.target);
              if (!source || !target) return null;

              const isRelated =
                hoveredId === link.source ||
                hoveredId === link.target ||
                selectedNodeId === link.source ||
                selectedNodeId === link.target;

              if (link.type === "parallel") {
                const midX = (source.x + target.x) / 2;
                const midY = (source.y + target.y) / 2 - 30;
                return (
                  <path
                    key={i}
                    d={`M${source.x} ${source.y} Q${midX} ${midY} ${target.x} ${target.y}`}
                    fill="none"
                    stroke={
                      isRelated
                        ? "hsl(var(--primary))"
                        : "hsl(var(--muted-foreground))"
                    }
                    strokeWidth={isRelated ? 2 : 1}
                    opacity={isRelated ? 0.6 : 0.15}
                    strokeDasharray=""
                  />
                );
              }

              return (
                <line
                  key={i}
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  stroke={
                    isRelated
                      ? "hsl(var(--primary))"
                      : "hsl(var(--muted-foreground))"
                  }
                  strokeWidth={isRelated ? 2 : 1}
                  opacity={isRelated ? 0.6 : 0.15}
                  strokeDasharray={link.type === "followup" ? "4 3" : ""}
                  markerEnd=""
                />
              );
            })}

            {/* Nodes */}
            {Array.from(nodePositions.entries()).map(([id, pos]) => {
              const node = pos.node;
              const r = nodeRadius(node);
              const isSelected = selectedNodeId === id;
              const isHovered = hoveredId === id;
              const dim = isDimmed(node);
              const noData = !node.hasData || node.mastery == null;

              return (
                <g
                  key={id}
                  transform={`rotate(${-transform.rotation}, ${pos.x}, ${pos.y})`}
                  style={{ cursor: "pointer", transition: "opacity 0.2s" }}
                  opacity={dim ? 0.2 : 1}
                  role="button"
                  tabIndex={0}
                  aria-label={node.name}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectNode(id);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      onSelectNode(id);
                    }
                  }}
                  onMouseEnter={() => setHoveredId(id)}
                  onMouseLeave={() => setHoveredId(null)}
                >
                  {/* Glow for selected */}
                  {isSelected && (
                    <circle
                      cx={pos.x}
                      cy={pos.y}
                      r={r + 6}
                      fill="none"
                      stroke="hsl(var(--primary))"
                      strokeWidth="2"
                      opacity="0.5"
                      filter="url(#glow)"
                    />
                  )}

                  {/* Node circle */}
                  <circle
                    cx={pos.x}
                    cy={pos.y}
                    r={isHovered ? r + 3 : r}
                    fill={
                      noData
                        ? "hsl(var(--muted-foreground)/0.25)"
                        : getMasteryFill(node.mastery ?? 0)
                    }
                    stroke={
                      isSelected
                        ? "hsl(var(--primary))"
                        : noData
                          ? "hsl(var(--muted-foreground)/0.5)"
                          : getMasteryStroke(node.mastery ?? 0)
                    }
                    strokeWidth={isSelected ? 3 : 1.5}
                    strokeDasharray={noData ? "3 2" : undefined}
                    style={{ transition: "r 0.15s, stroke-width 0.15s" }}
                  />

                  {/* Mastery text inside */}
                  <text
                    x={pos.x}
                    y={pos.y + 1}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize="9"
                    fontWeight="600"
                    fill={noData ? "hsl(var(--muted-foreground))" : "white"}
                  >
                    {noData ? "—" : `${node.mastery}%`}
                  </text>

                  {/* Label */}
                  <text
                    x={pos.x}
                    y={pos.y + r + 12}
                    textAnchor="middle"
                    fontSize="10"
                    fill="hsl(var(--foreground))"
                    fontWeight={isSelected ? "600" : "400"}
                    opacity={isHovered || isSelected ? 1 : 0.7}
                  >
                    {node.name.length > 6
                      ? node.name.slice(0, 6) + "…"
                      : node.name}
                  </text>

                  {/* Tooltip on hover */}
                  {isHovered && !dim && (
                    <foreignObject
                      x={pos.x - 70}
                      y={pos.y - r - 70}
                      width="140"
                      height="60"
                    >
                      <div className="bg-popover border border-border rounded-lg px-2.5 py-1.5 shadow-lg text-[10px] text-popover-foreground">
                        <div className="font-medium truncate">{node.name}</div>
                        {noData ? (
                          <div className="text-muted-foreground">
                            {t("knowledge.noMasteryData")}
                          </div>
                        ) : (
                          <>
                            <div className="text-muted-foreground">
                              {t("knowledge.radial.masteryLabel", {
                                value: node.mastery,
                              })}
                            </div>
                            <div className="text-muted-foreground">
                              {t("knowledge.radial.hoursWeight", {
                                hours: node.hours,
                                weight: node.weight,
                              })}
                            </div>
                          </>
                        )}
                      </div>
                    </foreignObject>
                  )}
                </g>
              );
            })}

            {/* Center circle */}
            <g data-tour="kg-center">
              <circle
                cx={CX}
                cy={CY}
                r={50}
                fill="hsl(var(--card))"
                stroke="hsl(var(--border))"
                strokeWidth="2"
              />
              <text
                x={CX}
                y={CY - 8}
                textAnchor="middle"
                fontSize="22"
                fontWeight="700"
                fill="hsl(var(--foreground))"
              >
                {overallMastery == null ? "—" : `${overallMastery}%`}
              </text>
              <text
                x={CX}
                y={CY + 12}
                textAnchor="middle"
                fontSize="10"
                fill="hsl(var(--muted-foreground))"
              >
                {overallMastery == null
                  ? t("knowledge.radial.classMasteryNone")
                  : t("knowledge.radial.overallMastery")}
              </text>
            </g>
          </g>
        </svg>
      </div>
    </div>
  );
}
