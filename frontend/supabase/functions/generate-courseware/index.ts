import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createRedlineStreamTransformer } from "./sse_filter.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
};

const SYSTEM_PROMPT = `你是一位资深的中学语文教学设计专家。你需要根据教师提供的教学需求，生成完整的教学方案。

你的输出应包含以下结构化内容：

## 📋 课件结构总览
列出课件的页数、总时长和核心目标。

## 🎬 课堂流程设计
按时间线设计详细的教学流程，每个环节包括：
- 时间段（如 0-3min）
- 环节类型（导入/探究/精读/拓展/总结）
- 使用的工具
- 具体活动描述
- 互动设计（讨论题/协作任务）

## 📝 分层作业设计
按 A层（拓展）、B层（标准）、C层（基础）设计差异化作业。

## 💡 教学建议
基于学生特点给出 2-3 条针对性教学建议。

## 🎯 预期效果
预测使用此方案后的教学效果提升数据。

请用 Markdown 格式输出，内容要详细、专业、可直接使用。每个环节要具体到可操作的程度。`;

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { content, objective, studentProfile, requirements, genType } =
      await req.json();

    const LOVABLE_API_KEY = Deno.env.get("LOVABLE_API_KEY");
    if (!LOVABLE_API_KEY) {
      throw new Error("LOVABLE_API_KEY is not configured");
    }

    const userPrompt = `请为以下教学需求生成完整的教学方案：

【生成类型】${genType || "互动课件"}
【教学内容】${content || "未指定"}
【教学目标】${objective || "未指定"}
【学生特点】${studentProfile || "未指定"}
【特殊要求】${requirements || "无"}
【推荐工具】古诗文网（文本基础）、ProcessOn（思维可视化）、剪映/必剪（视频创作）

请根据以上信息，结合推荐的开源教学工具，生成一份详细的、可直接使用的教学方案。`;

    const response = await fetch(
      "https://ai.gateway.lovable.dev/v1/chat/completions",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${LOVABLE_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: "google/gemini-3-flash-preview",
          messages: [
            { role: "system", content: SYSTEM_PROMPT },
            { role: "user", content: userPrompt },
          ],
          stream: true,
        }),
      },
    );

    if (!response.ok) {
      if (response.status === 429) {
        return new Response(
          JSON.stringify({ error: "AI服务请求过于频繁，请稍后重试。" }),
          {
            status: 429,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          },
        );
      }
      if (response.status === 402) {
        return new Response(
          JSON.stringify({ error: "AI服务额度不足，请充值后重试。" }),
          {
            status: 402,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          },
        );
      }
      const text = await response.text();
      console.error("AI gateway error:", response.status, text);
      return new Response(JSON.stringify({ error: "AI生成服务暂时不可用" }), {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const upstreamBody = response.body;
    if (!upstreamBody) {
      throw new Error("AI gateway returned empty body");
    }

    // 输出侧红线过滤：透传 SSE 流的同时改写 AI 生成内容（删除/替换红线词）
    const filteredBody = upstreamBody.pipeThrough(
      createRedlineStreamTransformer(),
    );

    return new Response(filteredBody, {
      headers: { ...corsHeaders, "Content-Type": "text/event-stream" },
    });
  } catch (e) {
    console.error("generate-courseware error:", e);
    return new Response(
      JSON.stringify({
        error: e instanceof Error ? e.message : "Unknown error",
      }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }
});
