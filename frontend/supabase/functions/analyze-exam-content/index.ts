import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version",
};

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const { fileName, mimeType, fileSize, title, currentContext } = await req.json();

    if (!fileName) {
      return new Response(JSON.stringify({ detection: null, confidence: 0 }), {
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
        model: "google/gemini-2.5-flash",
        messages: [
          {
            role: "system",
            content: `你是一个试卷内容识别引擎。根据文件名、标题和相关信息，提取试卷的归属信息。

规则：
1. 从文件名和标题中提取：学段、年级、班级、科目、单元/章节信息
2. 常见模式：
   - "高二3班数学第三单元检测卷" → 学段:高中, 年级:高二, 班级:3班, 科目:数学, 单元:第三单元
   - "七年级语文期中试卷" → 学段:初中, 年级:七年级, 科目:语文
   - "八下物理第二章测试" → 学段:初中, 年级:八年级, 科目:物理, 单元:第二章
3. 学段映射：一-六年级→小学，七-九年级→初中，高一-高三→高中
4. 给出识别置信度(0-1)，信息越完整置信度越高
5. 同时生成相关标签和推断题目数量、知识点等
6. 如果无法识别某个字段，设为null`,
          },
          {
            role: "user",
            content: `文件名：${fileName}\n标题：${title || fileName}\nMIME类型：${mimeType || "未知"}\n文件大小：${fileSize || "未知"}\n当前上下文：${currentContext ? JSON.stringify(currentContext) : "无"}`,
          },
        ],
        tools: [
          {
            type: "function",
            function: {
              name: "extract_exam_info",
              description: "Extract exam/paper attribution info from file metadata",
              parameters: {
                type: "object",
                properties: {
                  detected_school_level: {
                    type: "string",
                    description: "学段: 小学/初中/高中, or null",
                  },
                  detected_grade: {
                    type: "string",
                    description: "年级: e.g. 七年级/高二, or null",
                  },
                  detected_class: {
                    type: "string",
                    description: "班级: e.g. 3班/七班, or null",
                  },
                  detected_subject: {
                    type: "string",
                    description: "科目: e.g. 数学/语文/英语, or null",
                  },
                  detected_unit: {
                    type: "string",
                    description: "单元: e.g. 第三单元, or null",
                  },
                  detected_chapter: {
                    type: "string",
                    description: "章节: e.g. 整式的加减, or null",
                  },
                  confidence: {
                    type: "number",
                    description: "识别置信度 0-1",
                  },
                  tags: {
                    type: "array",
                    items: { type: "string" },
                    description: "Generated tags starting with #",
                  },
                  estimated_question_count: {
                    type: "number",
                    description: "推测的题目数量",
                  },
                  estimated_knowledge_points: {
                    type: "array",
                    items: { type: "string" },
                    description: "推测的知识点列表",
                  },
                  estimated_difficulty: {
                    type: "number",
                    description: "推测的难度 0-1",
                  },
                  source_label: {
                    type: "string",
                    description: "来源标签: 手动上传/校本题库/AI生成/年级共享",
                  },
                },
                required: ["confidence"],
                additionalProperties: false,
              },
            },
          },
        ],
        tool_choice: { type: "function", function: { name: "extract_exam_info" } },
      }),
    });

    if (!response.ok) {
      if (response.status === 429) {
        return new Response(JSON.stringify({ error: "AI请求过于频繁" }), {
          status: 429,
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

    return new Response(JSON.stringify({ confidence: 0 }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (e) {
    console.error("analyze-exam-content error:", e);
    return new Response(JSON.stringify({ error: e instanceof Error ? e.message : "Unknown error" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
