import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { REDLINE_PHRASES, REDLINE_PHRASE_COUNT } from "./redline_phrases.ts";

/**
 * C 端权威父本路径。可用环境变量 REDLINE_PARENT_PATH 覆盖。
 * 机器上无父本时跳过逐条 diff（其余守卫测试仍全量执行）。
 */
const PARENT_PATH =
  process.env.REDLINE_PARENT_PATH ??
  "F:/grade-buddy-parent家长端/parent-service/app/services/redline_filter.py";
const hasParent = existsSync(PARENT_PATH);

/** 从 Python 父本源码中解析出 REDLINE_PHRASES dict（键/值均为双引号字符串或 null）。 */
function parseParentPhrases(py: string): Record<string, string | null> {
  const block = py.match(/REDLINE_PHRASES[^{]*\{([\s\S]*?)\n\}/);
  if (!block) throw new Error("REDLINE_PHRASES block not found in parent");
  const entries: Record<string, string | null> = {};
  // Python 删除类值写 None，替换类值写 "..."；两者分别映射到 TS 的 null / string
  const pairRe = /"((?:[^"\\]|\\.)*)"\s*:\s*((?:null|None|"(?:[^"\\]|\\.)*"))/g;
  let m: RegExpExecArray | null;
  while ((m = pairRe.exec(block[1])) !== null) {
    entries[m[1]] =
      m[2] === "null" || m[2] === "None" ? null : (JSON.parse(m[2]) as string);
  }
  return entries;
}

describe("redline_phrases 词表守卫", () => {
  it("词表总条数 ≥ 26", () => {
    expect(REDLINE_PHRASE_COUNT).toBeGreaterThanOrEqual(26);
  });

  it("结构 = 8 条删除类（null）+ 18 条替换类（string）", () => {
    const entries = Object.entries(REDLINE_PHRASES);
    const deletes = entries.filter(([, v]) => v === null).length;
    const replaces = entries.filter(([, v]) => v !== null).length;
    expect(deletes).toBe(8);
    expect(replaces).toBe(18);
    expect(deletes + replaces).toBe(26);
  });

  it("删除类关键条抽查（伪科学名目必须为 null）", () => {
    for (const k of [
      "松果体激活",
      "照相记忆",
      "左右脑开发",
      "全脑开发",
      "感统失调",
      "开天眼",
      "蒙眼识字",
      "右脑开发",
    ]) {
      expect(REDLINE_PHRASES[k]).toBeNull();
    }
  });

  it("替换类关键条抽查（话术换语言，保留行为内核）", () => {
    const spot: Record<string, string> = {
      多巴胺戒断: "减少即时刺激",
      "21天养成习惯": "习惯养成需要时间",
      "21 天养成习惯": "习惯养成需要时间",
      逆商AQ: "抗挫能力",
      "逆商 AQ": "抗挫能力",
      莫扎特效应: "音乐欣赏",
      脑波音乐: "音乐放松",
      游戏上瘾: "过度游戏",
      短视频上瘾: "过度刷短视频",
      潜能翻倍: "能力提升",
      决定一生: "影响深远",
      窗口期: "关键阶段",
      低级的快乐靠多巴胺: "不同活动带来不同成长价值",
      低级快乐: "即时快乐",
      高级快乐: "长期成长",
      多巴胺成瘾: "过度依赖即时刺激",
      专注力训练: "专注习惯培养",
      意志力是肌肉: "循序渐进培养自控",
    };
    for (const [k, v] of Object.entries(spot)) {
      expect(REDLINE_PHRASES[k], `key=${k}`).toBe(v);
    }
  });

  it.runIf(hasParent)(
    "与 C 端父本 REDLINE_PHRASES 逐条完全一致（26/26）",
    () => {
      const py = readFileSync(PARENT_PATH, "utf8");
      const parent = parseParentPhrases(py);

      const parentKeys = Object.keys(parent).sort();
      const tsKeys = Object.keys(REDLINE_PHRASES).sort();
      expect(parentKeys.length).toBe(26);
      expect(tsKeys.length).toBe(26);
      expect(tsKeys).toEqual(parentKeys);
      expect(REDLINE_PHRASES).toEqual(parent);
    },
  );

  it.runIf(!hasParent)(
    "（跳过父本 diff：机器上无 C 端父本，路径可经 REDLINE_PARENT_PATH 指定）",
    () => {
      expect(true).toBe(true);
    },
  );
});
