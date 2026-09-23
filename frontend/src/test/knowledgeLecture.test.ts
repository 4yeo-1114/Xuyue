import { describe, expect, it } from "vitest";

import {
  matchKnowledgeLecture,
  resolveNodeNames,
} from "@/services/knowledgeLecture";
import { getKnowledgeGraph } from "@/data/knowledgeGraphData";

const graph = getKnowledgeGraph("primary", "语文");

describe("matchKnowledgeLecture", () => {
  it("matches an exact node name and returns that node", () => {
    const result = matchKnowledgeLecture("拼音", graph);
    expect(result.matched).toBe(true);
    expect(result.nodes.map((n) => n.id)).toEqual(["pinyin"]);
    expect(result.nodes[0].cluster).toBe("字词基础");
    expect(result.nodes[0].prerequisites).toEqual([]);
    expect(result.nodes[0].followups).toContain("literacy");
  });

  it("matches a cluster name and returns all child nodes", () => {
    const result = matchKnowledgeLecture("古诗文", graph);
    expect(result.matched).toBe(true);
    expect(result.nodes.map((n) => n.id).sort()).toEqual(
      ["poetry_recite", "poetry_understand"].sort(),
    );
  });

  it("returns matched=false and empty nodes for an unmatched knowledge point", () => {
    const result = matchKnowledgeLecture("现代文阅读", graph);
    expect(result.matched).toBe(false);
    expect(result.nodes).toEqual([]);
  });

  it("returns matched=false for a null graph", () => {
    expect(matchKnowledgeLecture("拼音", null)).toEqual({
      matched: false,
      nodes: [],
    });
  });

  it("returns matched=false for an empty knowledge point", () => {
    expect(matchKnowledgeLecture("", graph)).toEqual({
      matched: false,
      nodes: [],
    });
  });

  it("matches a knowledge point to the correct subject graph (数学)", () => {
    const mathGraph = getKnowledgeGraph("primary", "数学");
    const result = matchKnowledgeLecture("加减法", mathGraph);
    expect(result.matched).toBe(true);
    expect(result.nodes.map((n) => n.id)).toEqual(["addition"]);
  });
});

describe("resolveNodeNames", () => {
  it("resolves node ids to names preserving input order", () => {
    expect(resolveNodeNames(graph, ["pinyin", "literacy"])).toEqual([
      "拼音",
      "识字写字",
    ]);
  });

  it("returns empty array for unknown ids or null graph", () => {
    expect(resolveNodeNames(graph, ["no_such_id"])).toEqual([]);
    expect(resolveNodeNames(null, ["pinyin"])).toEqual([]);
    expect(resolveNodeNames(graph, [])).toEqual([]);
  });

  it("ignores unknown ids while keeping known ones in order", () => {
    expect(
      resolveNodeNames(graph, ["missing", "vocabulary", "pinyin"]),
    ).toEqual(["词语积累", "拼音"]);
  });
});
