import type {
  KnowledgeNode,
  KnowledgeGraphData,
  TreeNode,
} from "@/data/knowledgeGraphData";
import type { ClassAnalysisReport } from "@/services/api";

/**
 * 知识图谱 × 班级分析报告 的纯函数层。
 *
 * 职责：把后端 `GET /class-analysis/report` 的真实班级数据（knowledge_heatmap /
 * weak_points）叠加到静态图拓扑（knowledgeGraphData.ts）之上，并派生只读的
 * Enriched 对象。绝不修改 `getKnowledgeGraph()` 的源输出，绝不使用 hash 伪随机回填。
 */

export type NodeDataSource = "heatmap" | "cluster" | "weak";

export interface NodeClassStats {
  /** 掌握率 0-100；null = 暂无掌握率数据（证据不足，不得用 0 冒充） */
  mastery: number | null;
  /** 跨考试聚合的薄弱风险 0-100；null = 无 heatmap 证据 */
  riskScore: number | null;
  /** Σ evidence_count（涉及题目数） */
  evidenceCount: number;
  /** weak_points.affected_student_count；null = 无 weak_points 记录 */
  weakCount: number | null;
  weakSeverity?: "high" | "medium" | "low";
  /** 数据来源：heatmap=节点级命中；cluster=集群整体数据下发；weak=仅薄弱点命中 */
  dataSource: NodeDataSource;
}

export interface EnrichedNode extends Omit<KnowledgeNode, "mastery"> {
  mastery: number | null;
  hasData: boolean;
  evidenceCount: number;
  weakCount: number | null;
  weakSeverity?: "high" | "medium" | "low";
  riskScore: number | null;
  dataSource: NodeDataSource;
}

export type EnrichedGraphData = Omit<KnowledgeGraphData, "nodes"> & {
  nodes: EnrichedNode[];
};

export interface EnrichedTreeNode extends Omit<
  TreeNode,
  "mastery" | "children"
> {
  mastery: number | null;
  hasData: boolean;
  children: EnrichedTreeNode[];
}

/* ── 预留人工别名表（命中率不足时再补，禁止 hash 兜底） ── */
const ALIASES: Record<string, string[]> = {};

const MIN_LEN = 2;

/** trim → 去空白 → 小写 → 去尾部“（一）”序号 → 去剩余括号 */
export function normalize(s: string): string {
  return s
    .trim()
    .replace(/\s+/g, "")
    .toLowerCase()
    .replace(/[（(]\s*[一二三四五六七八九十\d]+\s*[)）]\s*$/g, "")
    .replace(/[()（）]/g, "");
}

/** 单条 knowledge_point → 单个图节点的打分（-1 = 不匹配） */
function matchScore(kp: string, node: KnowledgeNode): number {
  const k = normalize(kp);
  const n = normalize(node.name);
  const c = normalize(node.cluster);
  if (!k) return -1;
  if (n === k) return 100; // ① 精确：节点名 = 知识点
  if (c === k) return 90; // ② 精确：集群名 = 知识点（下发子节点）
  if (k.includes(n) && n.length >= MIN_LEN) return 70; // ③ 节点名是知识点的子串（别名/上位）
  if (n.includes(k) && k.length >= MIN_LEN) return 60; // ④ 知识点是节点名的子串
  if (c.includes(k) && k.length >= MIN_LEN) return 50; // ⑤ 知识点是集群名的子串
  return -1;
}

interface MatchHit {
  id: string;
  score: number;
}

/** 返回打分最高的全部命中节点 id（同分并列）；全不中 → [] */
export function matchKnowledgePoint(
  kp: string,
  nodes: KnowledgeNode[],
): string[] {
  return matchHits(kp, nodes).map((h) => h.id);
}

function matchHits(kp: string, nodes: KnowledgeNode[]): MatchHit[] {
  // 别名优先（人工维护）
  const aliased = ALIASES[kp];
  if (aliased && aliased.length > 0) {
    const set = new Set(aliased);
    return nodes
      .filter((n) => set.has(n.id))
      .map((n) => ({ id: n.id, score: 200 }));
  }
  let best = -1;
  const hits: MatchHit[] = [];
  for (const node of nodes) {
    const s = matchScore(kp, node);
    if (s > best) {
      best = s;
      hits.length = 0;
      hits.push({ id: node.id, score: s });
    } else if (s === best && s >= 0) {
      hits.push({ id: node.id, score: s });
    }
  }
  return best >= 0 ? hits : [];
}

/** values[].risk_score 非空均值 → 0-100；全 null → null */
export function aggregateRisk(
  values: Array<{ risk_score: number | null }>,
): number | null {
  const risks = (values ?? [])
    .map((v) => v.risk_score)
    .filter((v): v is number => typeof v === "number" && v != null);
  if (risks.length === 0) return null;
  return Math.round(risks.reduce((s, v) => s + v, 0) / risks.length);
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/** 掌握度聚合单行（BE-1 /class-analysis/mastery-distribution 的 data 元素） */
export interface MasteryEntry {
  name: string;
  mastery: number; // 0-1，错题分布派生相对口径
  wrong_count?: number;
  total?: number;
}

/**
 * 错题分布派生掌握度 → Map<nodeId, 掌握度 0-100>。
 * 锚点是 name（kp_id 多为 NULL，仅按 name 归一化匹配图节点）；命中多个节点（集群下发）全下发。
 */
export function buildMasteryMap(
  items: MasteryEntry[],
  nodes: KnowledgeNode[],
): Map<string, number> {
  const map = new Map<string, number>();
  for (const item of items ?? []) {
    if (!item?.name) continue;
    const v = clamp(Math.round((item.mastery ?? 0) * 100), 0, 100);
    for (const hit of matchHits(item.name, nodes)) {
      map.set(hit.id, v);
    }
  }
  return map;
}

/**
 * 聚合班级分析报告 → Map<nodeId, NodeClassStats>。
 * heatmap 先行（提供 mastery/risk/evidence），weak_points 后行（补 weakCount/severity）。
 * masteryByNode 为错题分布派生掌握度（真实口径）；命中时优先取真实值，
 * 未命中回退 heatmap 的 100-risk 反推（兼容旧数据与既有测试）。
 */
export function buildClassStats(
  report: ClassAnalysisReport | null,
  nodes: KnowledgeNode[],
  masteryByNode?: Map<string, number>,
): Map<string, NodeClassStats> {
  const map = new Map<string, NodeClassStats>();
  if (!report?.analysis) return map;

  for (const row of report.analysis.knowledge_heatmap ?? []) {
    const risk = aggregateRisk(row.values);
    const evidence = (row.values ?? []).reduce(
      (s, v) => s + (v.evidence_count || 0),
      0,
    );
    for (const hit of matchHits(row.knowledge_point, nodes)) {
      // 集群级命中（② 精确集群 90 / ⑤ 集群名子串 50）→ 数据为集群整体，下发子节点
      const clusterSource = hit.score === 90 || hit.score === 50;
      const prev = map.get(hit.id);
      const real = masteryByNode?.get(hit.id);
      map.set(hit.id, {
        mastery:
          real != null ? real : risk == null ? null : clamp(100 - risk, 0, 100),
        riskScore: risk,
        evidenceCount: evidence,
        weakCount: prev?.weakCount ?? null,
        weakSeverity: prev?.weakSeverity,
        dataSource: clusterSource ? "cluster" : "heatmap",
      });
    }
  }

  for (const wp of report.analysis.weak_points ?? []) {
    for (const hit of matchHits(wp.knowledge_point, nodes)) {
      const prev = map.get(hit.id);
      map.set(hit.id, {
        mastery: prev?.mastery ?? null,
        riskScore: prev?.riskScore ?? null,
        evidenceCount: prev?.evidenceCount ?? 0,
        weakCount: wp.affected_student_count,
        weakSeverity: wp.severity,
        dataSource: prev?.dataSource ?? "weak",
      });
    }
  }

  return map;
}

/** 派生新 EnrichedGraphData（不改源 graphData）。无数据的节点 mastery=null、hasData=false。 */
export function enrichGraphData(
  graphData: KnowledgeGraphData,
  statsMap: Map<string, NodeClassStats>,
): EnrichedGraphData {
  return {
    ...graphData,
    nodes: graphData.nodes.map((n) => {
      const stat = statsMap.get(n.id);
      const mastery = stat?.mastery != null ? stat.mastery : null;
      return {
        ...n,
        mastery,
        hasData: mastery != null,
        evidenceCount: stat?.evidenceCount ?? 0,
        weakCount: stat?.weakCount ?? null,
        weakSeverity: stat?.weakSeverity,
        riskScore: stat?.riskScore ?? null,
        dataSource: stat?.dataSource ?? "heatmap",
      };
    }),
  };
}

/** 派生 EnrichedTreeNode：cluster 均值只统计 hasData 子节点；全无数据 → null。 */
export function buildEnrichedTree(
  tree: TreeNode[],
  statsMap: Map<string, NodeClassStats>,
): EnrichedTreeNode[] {
  return tree.map((cluster) => {
    const children: EnrichedTreeNode[] = cluster.children.map((child) => {
      const stat = statsMap.get(child.id);
      const mastery = stat?.mastery != null ? stat.mastery : null;
      return {
        ...child,
        mastery,
        hasData: mastery != null,
        children: [],
      };
    });
    const dataChildren = children.filter(
      (c): c is EnrichedTreeNode & { mastery: number } =>
        c.hasData && c.mastery != null,
    );
    const clusterMastery =
      dataChildren.length > 0
        ? Math.round(
            dataChildren.reduce((s, c) => s + c.mastery, 0) /
              dataChildren.length,
          )
        : null;
    return {
      ...cluster,
      mastery: clusterMastery,
      hasData: dataChildren.length > 0,
      children,
    };
  });
}
