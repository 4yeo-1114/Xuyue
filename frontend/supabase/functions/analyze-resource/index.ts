import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
};

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const { fileName, mimeType, fileSize, title } = await req.json();

    if (!fileName) {
      return new Response(JSON.stringify({ tags: [], type: "其他" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const LOVABLE_API_KEY = Deno.env.get("LOVABLE_API_KEY");
    if (!LOVABLE_API_KEY) throw new Error("LOVABLE_API_KEY is not configured");

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
            content: `你是一个教学资源标签提取引擎。根据文件名和类型信息，推断该资源可能的内容，生成相关标签。

规则：
1. 标签以#开头，如 #鲁迅、#阿长与山海经、#朗读
2. 推断可能关联的课文、作者、知识点
3. 生成3-6个标签
4. 同时推断最合适的资源分类
5. 推断可能关联的课文名称（如有）
6. 推断适用年级（如有线索）`,
          },
          {
            role: "user",
            content: `文件名：${fileName}\nMIME类型：${mimeType || "未知"}\n文件大小：${fileSize || "未知"}\n标题：${title || fileName}`,
          },
        ],
        tools: [
          {
            type: "function",
            function: {
              name: "extract_tags",
              description: "Extract tags and metadata from resource file info",
              parameters: {
                type: "object",
                properties: {
                  tags: {
                    type: "array",
                    items: { type: "string" },
                    description: "Generated tags starting with #, e.g. ['#鲁迅', '#朗读']",
                  },
                  resourceType: {
                    type: "string",
                    description: "Resource type: 课件教案/试题试卷/微课视频/音频/图片素材/模板/学案/其他",
                  },
                  relatedLesson: {
                    type: "string",
                    description: "Related lesson name if identifiable, e.g. '阿长与山海经'",
                  },
                  suggestedGrade: {
                    type: "string",
                    description: "Suggested grade if identifiable, e.g. '七年级'",
                  },
                },
                required: ["tags", "resourceType"],
                additionalProperties: false,
              },
            },
          },
        ],
        tool_choice: { type: "function", function: { name: "extract_tags" } },
      }),
    });

    if (!response.ok) {
      if (response.status === 429) {
        return new Response(JSON.stringify({ error: "AI请求过于频繁，请稍后再试" }), {
          status: 429,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
      if (response.status === 402) {
        return new Response(JSON.stringify({ error: "AI额度已用完" }), {
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
      return new Response(JSON.stringify(parsed), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    return new Response(JSON.stringify({ tags: [], resourceType: "其他" }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("analyze-resource error:", e);
    return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "Unknown error" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
