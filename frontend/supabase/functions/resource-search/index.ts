import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
};

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const { query, resources } = await req.json();

    if (!query || !resources?.length) {
      return new Response(JSON.stringify({ rankedIds: resources?.map((r: any) => r.id) ?? [] }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const LOVABLE_API_KEY = Deno.env.get("LOVABLE_API_KEY");
    if (!LOVABLE_API_KEY) throw new Error("LOVABLE_API_KEY is not configured");

    // Build a compact resource summary for the AI
    const resourceSummary = resources.map((r: any) =>
      `[${r.id}] ${r.title} | 类型:${r.type} | 标签:${r.tags.join(",")} | 描述:${r.description || ""}`
    ).join("\n");

    const response = await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${LOVABLE_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "google/gemini-2.5-flash-lite",
        messages: [
          {
            role: "system",
            content: `你是一个教学资源智能匹配引擎。你需要深度理解用户的搜索意图，进行语义理解而非简单关键词匹配。

语义理解规则：
- "鲁迅导入音频" → 理解为：需要与鲁迅相关的、适合课堂导入的音频资源（如朗读、朗诵）
- "山海经图片" → 理解为：与《山海经》相关的图片素材
- "期中复习" → 理解为：适合期中阶段的复习资料（试卷、知识梳理等）
- 要考虑作者、作品、课文之间的关联（如"鲁迅"关联"阿长与山海经"、"藤野先生"等）

返回规则：
1. score 是 0-100 的匹配度分数
2. reason 是一句话解释为什么匹配（需说明语义关联）
3. highlights 是需要在标题和标签中高亮的关键词数组
4. 只返回 score >= 20 的资源
5. 按 score 降序排列`,
          },
          {
            role: "user",
            content: `用户搜索：${query}\n\n可选资源列表：\n${resourceSummary}`,
          },
        ],
        tools: [
          {
            type: "function",
            function: {
              name: "rank_resources",
              description: "Return ranked resources by relevance with highlight keywords",
              parameters: {
                type: "object",
                properties: {
                  rankings: {
                    type: "array",
                    items: {
                      type: "object",
                      properties: {
                        id: { type: "string", description: "Resource ID" },
                        score: { type: "number", description: "Match score 0-100" },
                        reason: { type: "string", description: "Brief reason for match in Chinese" },
                        highlights: {
                          type: "array",
                          items: { type: "string" },
                          description: "Keywords to highlight in the title/tags, e.g. ['鲁迅','朗读','阿长']",
                        },
                      },
                      required: ["id", "score", "reason", "highlights"],
                      additionalProperties: false,
                    },
                  },
                },
                required: ["rankings"],
                additionalProperties: false,
              },
            },
          },
        ],
        tool_choice: { type: "function", function: { name: "rank_resources" } },
      }),
    });

    if (!response.ok) {
      if (response.status === 429) {
        return new Response(JSON.stringify({ error: "AI 请求过于频繁，请稍后再试" }), {
          status: 429,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
      if (response.status === 402) {
        return new Response(JSON.stringify({ error: "AI 额度已用完，请充值" }), {
          status: 402,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
      const t = await response.text();
      console.error("AI gateway error:", response.status, t);
      throw new Error("AI gateway error");
    }

    const data = await response.json();
    const toolCall = data.choices?.[0]?.message?.tool_calls?.[0];

    if (toolCall?.function?.arguments) {
      const parsed = JSON.parse(toolCall.function.arguments);
      return new Response(JSON.stringify({ rankings: parsed.rankings || [] }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Fallback: return all resources
    return new Response(JSON.stringify({ rankings: resources.map((r: any) => ({ id: r.id, score: 50, reason: "默认匹配" })) }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("resource-search error:", e);
    return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "Unknown error" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
