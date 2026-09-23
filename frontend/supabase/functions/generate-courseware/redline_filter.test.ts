import { describe, expect, it } from "vitest";
import { RedlineFilter, filterText } from "./redline_filter.ts";

describe("filterText（整段过滤，纯函数）", () => {
  it("删除类：直接移除词条", () => {
    expect(filterText("要教松果体激活课程")).toBe("要教课程");
    expect(filterText("练照相记忆提升成绩")).toBe("练提升成绩");
  });

  it("删除类：合并相邻空白，不留双空格残渣", () => {
    expect(filterText("孩子 开天眼 训练")).toBe("孩子 训练");
    expect(filterText("a 右脑开发 b")).toBe("a b");
  });

  it("替换类：替换为改写语", () => {
    expect(filterText("注意莫扎特效应")).toBe("注意音乐欣赏");
    expect(filterText("避免游戏上瘾")).toBe("避免过度游戏");
    expect(filterText("谨防短视频上瘾")).toBe("谨防过度刷短视频");
  });

  it("最长短语优先：不被短前缀误伤", () => {
    expect(filterText("低级的快乐靠多巴胺")).toBe("不同活动带来不同成长价值");
    expect(filterText("低级快乐")).toBe("即时快乐");
    // 长短语在前，不会被"低级快乐"先拆后再匹配
    expect(filterText("谈低级快乐前")).toBe("谈即时快乐前");
    expect(filterText("高级快乐")).toBe("长期成长");
  });

  it("裸词不误伤：多巴胺 / 上瘾 / 戒断 单独出现不拦", () => {
    expect(filterText("多巴胺")).toBe("多巴胺");
    expect(filterText("上瘾")).toBe("上瘾");
    expect(filterText("戒断")).toBe("戒断");
    // 不误伤「低级错误」等正常表达
    expect(filterText("低级错误")).toBe("低级错误");
  });

  it("无命中文本原样保留", () => {
    const text = "正常教学：语文阅读，目标提升学生核心素养。";
    expect(filterText(text)).toBe(text);
  });
});

describe("RedlineFilter（流式，feed/flush）", () => {
  it("替换短语被切分到多个 chunk 仍命中", () => {
    const f = new RedlineFilter();
    expect(f.feed("多巴胺")).toBe("");
    expect(f.feed("成瘾")).toBe("过度依赖即时刺激");
    expect(f.flush()).toBe("");
  });

  it("删除短语跨 chunk 拆分 + 删除点空白合并", () => {
    const f = new RedlineFilter();
    const out = f.feed("a 开") + f.feed("天眼 b") + f.flush();
    expect(out).toBe("a b");
  });

  it("chunk 落在短语中间时缓冲不释放，等完整命中再替换", () => {
    const f = new RedlineFilter();
    const a = f.feed("21");
    const b = f.feed("天养成习惯要坚持");
    const c = f.flush();
    expect(a + b + c).toBe("习惯养成需要时间要坚持");
  });

  it("flush 释放残留缓冲（残留不可能构成完整命中，原样放行）", () => {
    const f = new RedlineFilter();
    expect(f.feed("窗口")).toBe(""); // “窗口”是“窗口期”的前缀，先保持
    expect(f.flush()).toBe("窗口");
  });

  it("流式结果与整段 filterText 等价", () => {
    const text = "学生通过左右脑开发提高专注力训练效果，避免多巴胺成瘾。";
    expect(filterText(text)).toBe(
      "学生通过提高专注习惯培养效果，避免过度依赖即时刺激。",
    );
    const f = new RedlineFilter();
    const parts = [
      f.feed("学生通过"),
      f.feed("左右脑开发提高"),
      f.feed("专注力训练效果，"),
      f.feed("避免多巴胺成瘾。"),
      f.flush(),
    ];
    expect(parts.join("")).toBe(filterText(text));
  });
});
