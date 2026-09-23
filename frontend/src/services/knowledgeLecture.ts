import type {
  KnowledgeGraphData,
  KnowledgeNode,
} from "@/data/knowledgeGraphData";
import { matchKnowledgePoint } from "@/components/class-detail/knowledge-graph/classStats";

/**
 * 错题知识点串讲 — 纯函数层。
 *
 * 职责：把错题详情接口返回的单个 `knowledge_point` 字符串，映射到静态知识图谱
 * （knowledgeGraphData.ts）中的节点，供串讲卡片消费。
 * 不修改任何源数据，不引入副作用，便于 Vitest 单测。
 */

export interface KnowledgeLectureMatch {
  /** 是否命中至少一个图节点 */
  matched: boolean;
  /** 命中的节点（保持图谱顺序）；未命中为空数组 */
  nodes: KnowledgeNode[];
}

/**
 * 匹配单个知识点到图谱节点。
 * 依赖 classStats.matchKnowledgePoint 的打分逻辑（精确/集群/子串等）。
 * graph 为空或知识点为空 → matched=false。
 */
export function matchKnowledgeLecture(
  kp: string,
  graph: KnowledgeGraphData | null,
): KnowledgeLectureMatch {
  if (
    !kp ||
    !graph ||
    !Array.isArray(graph.nodes) ||
    graph.nodes.length === 0
  ) {
    return { matched: false, nodes: [] };
  }
  const ids = matchKnowledgePoint(kp, graph.nodes);
  if (ids.length === 0) return { matched: false, nodes: [] };
  const idSet = new Set(ids);
  return {
    matched: true,
    nodes: graph.nodes.filter((node) => idSet.has(node.id)),
  };
}

/**
 * 把图节点 id 解析回名称（保持入参顺序；未知 id 忽略）。
 * 用于前置 prerequisites / 后续 followups 数组的展示。
 */
export function resolveNodeNames(
  graph: KnowledgeGraphData | null,
  ids: string[],
): string[] {
  if (!graph || !Array.isArray(ids) || ids.length === 0) return [];
  const byId = new Map(graph.nodes.map((node) => [node.id, node.name]));
  return ids.map((id) => byId.get(id)).filter((name): name is string => !!name);
}
