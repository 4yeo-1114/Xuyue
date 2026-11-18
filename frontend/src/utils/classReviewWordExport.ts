/**
 * 课堂讲评 Word（.doc）导出：正文是真文本，老师拿到后可在 Word/WPS 里直接改。
 * 用 Word 兼容 HTML（application/msword + .doc 扩展名），零新依赖；
 * 错题原卷图抓成 base64 内嵌，附录开关与 PDF 版共用（includeWrongPaper）。
 */
import type { ClassReviewReport } from "@/services/api";
import { fetchGradingFileBlob } from "@/services/gradingApi";
import {
  type ClassReviewExportOptions,
  type ClassReviewPdfKind,
  HIGH_FREQ_EXAMPLES_PER_QUESTION,
  HIGH_FREQ_TOP_QUESTIONS,
  readClassReviewExportPrefs,
  selectHighFrequencyWrongImages,
} from "./classReviewPdfExport";

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderList(items: unknown, empty = "暂无内容"): string {
  const list = (Array.isArray(items) ? items : [])
    .map((x) => String(x ?? "").trim())
    .filter(Boolean);
  if (!list.length) return `<p class="muted">${escapeHtml(empty)}</p>`;
  return `<ol>${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>`;
}

/** 图抓成 data URL（Word 里内嵌）；单张失败返回空串，不因一张坏图中断整个导出 */
async function imageToDataUrl(path: string | undefined | null): Promise<string> {
  const raw = String(path ?? "").trim();
  if (!raw) return "";
  if (raw.startsWith("data:")) return raw;
  try {
    const blob = await fetchGradingFileBlob(raw);
    return await new Promise<string>((resolve) => {
      const fr = new FileReader();
      fr.onload = () => resolve(String(fr.result || ""));
      fr.onerror = () => resolve("");
      fr.readAsDataURL(blob);
    });
  } catch {
    return "";
  }
}

/** 并发抓图（上限 6），返回与输入等长的 dataURL 列表 */
async function imagesToDataUrls(paths: Array<string | undefined>): Promise<string[]> {
  const out = new Array<string>(paths.length).fill("");
  let cursor = 0;
  const worker = async () => {
    while (cursor < paths.length) {
      const i = cursor++;
      out[i] = await imageToDataUrl(paths[i]);
    }
  };
  const workers = Math.min(6, Math.max(1, paths.length));
  await Promise.all(Array.from({ length: workers }, worker));
  return out;
}

function wordStyles(): string {
  return `
    @page WordSection1 { size: 21cm 29.7cm; margin: 1.8cm 2.2cm; }
    div.WordSection1 { page: WordSection1; }
    body { font-family: "SimSun", "宋体", "Microsoft YaHei", sans-serif; font-size: 12pt; color: #1c1c1c; line-height: 1.7; }
    h1 { font-size: 20pt; text-align: center; margin: 0 0 6pt; color: #111; }
    .subtitle { text-align: center; color: #5c6678; font-size: 10.5pt; margin: 0 0 14pt; }
    h2 { font-size: 14pt; color: #1a3a5c; border-left: 4px solid #1a3a5c; padding-left: 8pt; margin: 16pt 0 6pt; }
    h3 { font-size: 12pt; color: #1a3a5c; margin: 12pt 0 4pt; }
    p { margin: 4pt 0; }
    .muted { color: #6b7280; font-size: 10.5pt; }
    table { border-collapse: collapse; width: 100%; margin: 6pt 0; }
    td, th { border: 1px solid #d5dae3; padding: 6pt 8pt; vertical-align: top; font-size: 10.5pt; }
    th { background: #f4f6f9; color: #1a3a5c; text-align: left; }
    table.meta td { border: none; padding: 3pt 12pt 3pt 0; font-size: 10.5pt; }
    ol { margin: 4pt 0; padding-left: 22pt; }
    li { margin: 3pt 0; }
    img { max-width: 100%; }
    table.wp-table { table-layout: fixed; }
  `;
}

function wrapWordDocument(bodyHtml: string): string {
  return `<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
<head>
<meta charset="utf-8" />
<title>课堂讲评</title>
<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View><w:Zoom>100</w:Zoom></w:WordDocument></xml><![endif]-->
<style>${wordStyles()}</style>
</head>
<body><div class="WordSection1">${bodyHtml}</div></body>
</html>`;
}

// ── 附录图版面盒：两图并排时总宽恒小于版心 ──
// WPS 兼容模式只认 <img width/height> 属性、忽略 CSS 宽度（11.12「错题原卷看不完整」根因：
// 大裁图按原尺寸撑爆表格，右半栏「作答区域」被裁出页面）。图必须带属性定版，小图不放大。
const WP_IMG_MAX_W = 280;
const WP_IMG_MAX_H = 420;

/** 探 dataURL 原图尺寸；探不出返回 0（调用方按 4:3 兜底） */
function probeImageSize(dataUrl: string): Promise<{ w: number; h: number }> {
  return new Promise((resolve) => {
    const im = new Image();
    im.onload = () =>
      resolve({ w: im.naturalWidth || 0, h: im.naturalHeight || 0 });
    im.onerror = () => resolve({ w: 0, h: 0 });
    im.src = dataUrl;
  });
}

/** 等比缩进版面盒：大图压到盒内、小图原尺寸 */
function fitImageBox(w: number, h: number): { w: number; h: number } {
  if (!w || !h) return { w: WP_IMG_MAX_W, h: Math.round(WP_IMG_MAX_W * 0.75) };
  const s = Math.min(1, WP_IMG_MAX_W / w, WP_IMG_MAX_H / h);
  return { w: Math.max(1, Math.round(w * s)), h: Math.max(1, Math.round(h * s)) };
}

function wordImgTag(
  dataUrl: string,
  size: { w: number; h: number },
  alt: string,
): string {
  const { w, h } = fitImageBox(size.w, size.h);
  return `<img src="${dataUrl}" alt="${alt}" width="${w}" height="${h}" style="width: ${w}px; height: ${h}px" />`;
}

/**
 * 「错题原卷」附录：按高频错题分节（错误人数最多的前 N 题，每题至多 M 名学生示例）。
 * 客户 11.12 反馈「导出 151 页太多了，只需要展示几个高频错题就可以了」。
 * 图用 width/height 属性定版（WPS 兼容模式不认 CSS 宽度），表格两栏恒 50%。
 * 无图时返回空串。
 */
async function buildWrongPaperSection(
  images: unknown,
  questionAccuracy: unknown,
): Promise<string> {
  const groups = selectHighFrequencyWrongImages(images, questionAccuracy);
  if (!groups.length) return "";
  const paths: Array<string | undefined> = [];
  for (const group of groups) {
    for (const item of group.items) {
      paths.push(item.image_url);
      paths.push(item.answer_url);
    }
  }
  const dataUrls = await imagesToDataUrls(paths);
  const sizes = await Promise.all(
    dataUrls.map((u) => (u ? probeImageSize(u) : Promise.resolve({ w: 0, h: 0 }))),
  );
  let k = 0;
  const parts: string[] = [
    `<h2>错题原卷</h2><p class="muted">高频错题：错误人数最多的前 ${HIGH_FREQ_TOP_QUESTIONS} 题，每题展示至多 ${HIGH_FREQ_EXAMPLES_PER_QUESTION} 名学生示例，供课堂讲评对照使用。</p>`,
  ];
  for (const group of groups) {
    parts.push(`<h3>${escapeHtml(group.title)}（错 ${group.wrongCount} 人）</h3>`);
    for (const item of group.items) {
      const qUrl = dataUrls[k];
      const qSize = sizes[k];
      k += 1;
      const aUrl = dataUrls[k];
      const aSize = sizes[k];
      k += 1;
      const title = escapeHtml(item.title || "错题");
      const student = escapeHtml(
        String(item.student_name || "").trim() || "未命名学生",
      );
      const qImg = qUrl
        ? wordImgTag(qUrl, qSize, title)
        : `<span class="muted">暂无图片</span>`;
      const aImg = aUrl
        ? wordImgTag(aUrl, aSize, `${title} 作答`)
        : `<span class="muted">暂无图片</span>`;
      parts.push(`
        <p><b>学生：${student} · ${title}</b></p>
        <table class="wp-table">
          <tr><th width="50%">错题原卷</th><th width="50%">作答区域</th></tr>
          <tr><td style="text-align:center">${qImg}</td><td style="text-align:center">${aImg}</td></tr>
        </table>
      `);
    }
  }
  return parts.join("");
}

function metaTable(report: ClassReviewReport, subject: string): string {
  const summary = report.source_summary || {};
  const generatedAt = report.generated_at
    ? new Date(report.generated_at).toLocaleString("zh-CN")
    : new Date().toLocaleString("zh-CN");
  const examNames = (report.exam_names || []).map((n) => escapeHtml(n));
  return `
    <table class="meta">
      <tr>
        <td><b>学科：</b>${escapeHtml(subject)}</td>
        <td><b>生成时间：</b>${escapeHtml(generatedAt)}</td>
      </tr>
      <tr>
        <td><b>导入考试：</b>${escapeHtml(String(examNames.length))} 场</td>
        <td><b>有效学生：</b>${escapeHtml(String(summary.valid_student_count ?? 0))} 人</td>
      </tr>
    </table>
  `;
}

async function buildReviewPlanBody(
  report: ClassReviewReport,
  subject: string,
  includeWrongPaper: boolean,
): Promise<string> {
  const preClass = report.pre_class || {};
  const overview = preClass.overview || {};
  const plan = preClass.review_plan || {};
  const examNames = report.exam_names || [];
  const flow = Array.isArray(plan.teaching_flow) ? plan.teaching_flow : [];

  const flowHtml = flow.length
    ? flow
        .map((step: any, index: number) => {
          const title = escapeHtml(step?.step || `环节${index + 1}`);
          const minutes = escapeHtml(step?.minutes || "-");
          return `
            <p><b>${index + 1}. ${title}</b>（${minutes} 分钟）</p>
            <table>
              <tr><th style="width:50%">教师动作</th><th>学生活动</th></tr>
              <tr>
                <td>${escapeHtml(step?.teacher_action || "暂无")}</td>
                <td>${escapeHtml(step?.student_action || "暂无")}</td>
              </tr>
            </table>
          `;
        })
        .join("")
    : `<p class="muted">暂无讲评流程</p>`;

  const wrongPaperHtml = includeWrongPaper
    ? await buildWrongPaperSection(
        preClass.all_wrong_images,
        report.source_summary?.question_accuracy,
      )
    : "";

  return `
    <h1>${escapeHtml(subject)}课堂讲评方案</h1>
    <p class="subtitle">课前分析报告 · AI 智能生成（Word 可编辑版）</p>
    ${metaTable(report, subject)}
    <h2>数据根据</h2>
    ${examNames.length ? `<p>${examNames.map(escapeHtml).join("、")}</p>` : `<p class="muted">暂无导入考试</p>`}
    <h2>讲评概要</h2>
    <p>${escapeHtml(overview.summary || "已生成课堂讲评方案")}</p>
    <p class="muted">建议讲评时长：${escapeHtml(plan.duration || "待定")}</p>
    <h2>课堂重点知识点</h2>
    ${renderList(plan.key_points, "暂无重点知识点")}
    <h2>本班整体薄弱点</h2>
    ${renderList(overview.weak_points, "暂无")}
    <h2>班级优势表现</h2>
    ${renderList(overview.strengths, "暂无")}
    <h2>数据证据</h2>
    ${renderList(overview.data_basis, "暂无")}
    <h2>讲评目标</h2>
    ${renderList(plan.objectives)}
    <h2>板书设计</h2>
    ${renderList(plan.blackboard_design)}
    <h2>课堂互动问题</h2>
    ${renderList(plan.interaction_questions)}
    <h2>讲评流程时间轴</h2>
    ${flowHtml}
    ${wrongPaperHtml}
  `;
}

function buildConsolidationBody(report: ClassReviewReport, subject: string): string {
  const tracking = report.tracking || {};
  const consolidation = report.consolidation || {};
  const qualityScore =
    tracking.quality_score !== undefined && tracking.quality_score !== null
      ? `<p class="muted">讲评质量评分：${escapeHtml(tracking.quality_score)}</p>`
      : "";
  const tiers = Array.isArray(consolidation.tiered_practice)
    ? consolidation.tiered_practice
    : [];
  const tieredHtml = tiers.length
    ? tiers
        .map((group: any, index: number) => {
          const level = escapeHtml(group?.level || `层级${index + 1}`);
          return `<h3>${level}</h3>${renderList(group?.tasks, "暂无任务")}`;
        })
        .join("")
    : `<p class="muted">暂无分层任务</p>`;

  return `
    <h1>课后讲评复盘与二次巩固</h1>
    <p class="subtitle">${escapeHtml(subject)} · 课后跟踪报告（Word 可编辑版）</p>
    ${metaTable(report, subject)}
    <h2>本次讲课分析</h2>
    <p>${escapeHtml(tracking.summary || "课后填写课堂效果后，AI会评估本堂讲评质量与优缺点。")}</p>
    ${qualityScore}
    <h2>讲课亮点</h2>
    ${renderList(tracking.strengths, "暂无讲课优点分析")}
    <h2>待优化问题</h2>
    ${renderList(tracking.problems, "暂无讲课不足分析")}
    <h2>下次改进建议</h2>
    ${renderList(tracking.improvement_suggestions, "暂无改进建议")}
    <h2>二次讲评建议</h2>
    <p>${escapeHtml(consolidation.summary || "课后填写课堂效果后，AI会生成二次讲解与巩固方案。")}</p>
    <h2>二次讲解重点</h2>
    ${renderList(consolidation.reteaching_points, "暂无二次讲解点")}
    <h2>课堂调整策略</h2>
    ${renderList(consolidation.lesson_adjustments, "暂无二次讲课调整策略")}
    <h2>分层巩固任务</h2>
    ${tieredHtml}
  `;
}

function downloadDoc(html: string, filename: string): void {
  // 带 BOM，Word/WPS 打开中文不乱码
  const blob = new Blob(["\ufeff", html], { type: "application/msword" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** 导出讲评方案/二次巩固 Word（.doc）。错题原卷只进「讲评方案」，与 PDF 版口径一致 */
export async function exportClassReviewWord(
  kind: ClassReviewPdfKind,
  report: ClassReviewReport,
  subject: string,
  options?: ClassReviewExportOptions,
): Promise<void> {
  const includeWrongPaper =
    kind === "review_plan" &&
    (options?.includeWrongPaper ??
      readClassReviewExportPrefs().includeWrongPaper);
  const date = new Date().toLocaleDateString("zh-CN").replace(/\//g, "-");
  const body =
    kind === "review_plan"
      ? await buildReviewPlanBody(report, subject, includeWrongPaper)
      : buildConsolidationBody(report, subject);
  const filename =
    kind === "review_plan"
      ? `${subject}_课堂讲评方案_${date}.doc`
      : `${subject}_二次巩固方案_${date}.doc`;
  downloadDoc(wrapWordDocument(body), filename);
}
