import { describe, expect, it } from "vitest";

import {
  normalize,
  matchKnowledgePoint,
  aggregateRisk,
  buildClassStats,
  enrichGraphData,
  buildEnrichedTree,
} from "@/components/class-detail/knowledge-graph/classStats";
import { getKnowledgeGraph, buildTree } from "@/data/knowledgeGraphData";
import type { ClassAnalysisReport } from "@/services/api";

// Mock 契约样本（验收 §7：语文 · 小学 · 某班）
const mockReport = {
  id: "r1",
  class_id: "c1",
  subject: "语文",
  exam_names: ["期中", "期末"],
  analysis: {
    knowledge_heatmap: [
      {
        knowledge_point: "拼音",
        values: [
          { exam_name: "期中", risk_score: 12, evidence_count: 3 },
          { exam_name: "期末", risk_score: 8, evidence_count: 2 },
        ],
      },
      {
        knowledge_point: "古诗文",
        values: [
          { exam_name: "期中", risk_score: 45, evidence_count: 5 },
          { exam_name: "期末", risk_score: null, evidence_count: 0 },
        ],
      },
      {
        knowledge_point: "现代文阅读",
        values: [{ exam_name: "期中", risk_score: null, evidence_count: 0 }],
      },
    ],
    weak_points: [
      {
        knowledge_point: "古诗文",
        severity: "high",
        affected_student_count: 12,
      },
      {
        knowledge_point: "看图写话",
        severity: "medium",
        affected_student_count: 6,
      },
    ],
  },
} as unknown as ClassAnalysisReport;

const graph = getKnowledgeGraph("primary", "语文");
const stats = buildClassStats(mockReport, graph.nodes);

describe("normalize", () => {
  it("strips whitespace, brackets, and trailing ordinal markers", () => {
    expect(normalize(" 现代文阅读（一） ")).toBe("现代文阅读");
    expect(normalize("古诗文 (2)")).toBe("古诗文");
    expect(normalize("  拼音  ")).toBe("拼音");
  });
});

describe("matchKnowledgePoint", () => {
  it("matches exact node name (100)", () => {
    expect(matchKnowledgePoint("拼音", graph.nodes)).toEqual(["pinyin"]);
  });

  it("matches exact cluster and passes to all child nodes (90)", () => {
    expect(matchKnowledgePoint("古诗文", graph.nodes).sort()).toEqual(
      ["poetry_recite", "poetry_understand"].sort(),
    );
  });

  it("returns empty for unmatched knowledge point", () => {
    expect(matchKnowledgePoint("现代文阅读", graph.nodes)).toEqual([]);
  });
});

describe("aggregateRisk", () => {
  it("averages non-null risks and rounds", () => {
    expect(
      aggregateRisk([
        { risk_score: 12 },
        { risk_score: 8 },
        { risk_score: null },
      ]),
    ).toBe(10);
  });

  it("returns null when all risk scores are null", () => {
    expect(
      aggregateRisk([{ risk_score: null }, { risk_score: null }]),
    ).toBeNull();
    expect(aggregateRisk([])).toBeNull();
  });
});

describe("buildClassStats", () => {
  it("maps heatmap risk to mastery = 100 - risk", () => {
    const pinyin = stats.get("pinyin");
    expect(pinyin?.mastery).toBe(90);
    expect(pinyin?.riskScore).toBe(10);
    expect(pinyin?.evidenceCount).toBe(5);
    expect(pinyin?.dataSource).toBe("heatmap");
    expect(pinyin?.weakCount).toBeNull(); // 无 weak_points 行
  });

  it("marks cluster-level match with dataSource=cluster and weak data", () => {
    const recite = stats.get("poetry_recite");
    const understand = stats.get("poetry_understand");
    expect(recite?.mastery).toBe(55); // 45 → 55
    expect(recite?.dataSource).toBe("cluster");
    expect(recite?.weakCount).toBe(12);
    expect(recite?.weakSeverity).toBe("high");
    expect(understand?.mastery).toBe(55);
    expect(understand?.weakCount).toBe(12);
  });

  it("weak-only node gets weakCount but no mastery", () => {
    const pw = stats.get("picture_writing");
    expect(pw?.mastery).toBeNull();
    expect(pw?.weakCount).toBe(6);
    expect(pw?.weakSeverity).toBe("medium");
    expect(pw?.dataSource).toBe("weak");
  });

  it("leaves unmatched nodes unmarked", () => {
    expect(stats.get("oral_comm")).toBeUndefined();
    expect(stats.get("diary")).toBeUndefined();
  });

  it("all-null risk yields null mastery (no zero impersonation)", () => {
    const report = {
      ...mockReport,
      analysis: {
        knowledge_heatmap: [
          {
            knowledge_point: "拼音",
            values: [
              { exam_name: "期中", risk_score: null, evidence_count: 1 },
              { exam_name: "期末", risk_score: null, evidence_count: 2 },
            ],
          },
        ],
        weak_points: [],
      },
    } as unknown as ClassAnalysisReport;
    const s = buildClassStats(report, graph.nodes);
    expect(s.get("pinyin")?.mastery).toBeNull();
    expect(s.get("pinyin")?.riskScore).toBeNull();
    expect(s.get("pinyin")?.evidenceCount).toBe(3);
  });

  it("returns empty map for null report", () => {
    expect(buildClassStats(null, graph.nodes).size).toBe(0);
  });
});

describe("enrichGraphData", () => {
  it("returns a new object without mutating the source graph", () => {
    const source = getKnowledgeGraph("primary", "语文");
    const before = source.nodes[0].mastery;
    const enriched = enrichGraphData(source, stats);
    expect(enriched).not.toBe(source);
    expect(enriched.nodes).not.toBe(source.nodes);
    expect(source.nodes[0].mastery).toBe(before); // 源不被改
    expect(source.nodes[0]).not.toHaveProperty("hasData");
  });

  it("attaches hasData / nullable mastery / evidence / weak fields", () => {
    const enriched = enrichGraphData(graph, stats);
    const pinyin = enriched.nodes.find((n) => n.id === "pinyin");
    expect(pinyin?.hasData).toBe(true);
    expect(pinyin?.mastery).toBe(90);
    expect(pinyin?.evidenceCount).toBe(5);

    const oral = enriched.nodes.find((n) => n.id === "oral_comm");
    expect(oral?.hasData).toBe(false);
    expect(oral?.mastery).toBeNull();
    expect(oral?.evidenceCount).toBe(0);

    const pw = enriched.nodes.find((n) => n.id === "picture_writing");
    expect(pw?.hasData).toBe(false); // weak-only → 无掌握率
    expect(pw?.weakCount).toBe(6);
  });
});

describe("buildEnrichedTree", () => {
  it("averages cluster mastery over data children only", () => {
    const tree = buildTree(graph);
    const enrichedTree = buildEnrichedTree(tree, stats);

    const poetry = enrichedTree.find((c) => c.name === "古诗文");
    expect(poetry?.hasData).toBe(true);
    expect(poetry?.mastery).toBe(55); // 55+55 → 55

    const base = enrichedTree.find((c) => c.name === "字词基础");
    expect(base?.hasData).toBe(true);
    expect(base?.mastery).toBe(90); // 仅 拼音 有数据

    const writing = enrichedTree.find((c) => c.name === "写话习作");
    expect(writing?.hasData).toBe(false); // 看图写话 weak-only 无掌握率，其余无数据
    expect(writing?.mastery).toBeNull();

    const oral = enrichedTree.find((c) => c.name === "口语交际");
    expect(oral?.hasData).toBe(false);
    expect(oral?.mastery).toBeNull();
  });

  it("does not mutate the input tree", () => {
    const tree = buildTree(graph);
    const snapshot = JSON.stringify(tree);
    buildEnrichedTree(tree, stats);
    expect(JSON.stringify(tree)).toBe(snapshot);
  });
});
