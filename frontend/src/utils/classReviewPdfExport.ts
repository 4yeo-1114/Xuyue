/**
 * 课堂讲评 PDF 导出：讲评方案/二次巩固文字内容 + 可选「错题原卷」附录。
 * 在离屏 DOM 中单独排版后生成 PDF，与页面上的图片预览区域无关。
 * 错题原卷图 URL 来自 report.pre_class.all_wrong_images。导出前把图源换成同源相对路径
 * （exportImageSrc）：跨域直链 html2canvas 会整张跳过不画（导出全是空白框），同源图无此限制；
 * 同时连续内容块攒批截图（captureBlocksToCanvases），避免上百张错题卡逐块截图把导出拖到几分钟。
 */
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import type { ClassReviewReport } from "@/services/api";
import { readGlobalPrintPrefs } from "@/lib/globalPrintPrefs";

const BOOK_FONT =
  '"SimSun", "Songti SC", "STSong", "Times New Roman", "Georgia", "Microsoft YaHei", "PingFang SC", serif';
/** 兼容模式字体栈：补齐 Noto Serif SC / SimHei，降低 Windows 下作文正文缺字乱码风险 */
const BOOK_FONT_COMPAT =
  '"SimSun", "Songti SC", "Noto Serif SC", "SimHei", "Microsoft YaHei", serif';

function getBookFont(): string {
  return readGlobalPrintPrefs().printMode === "compat"
    ? BOOK_FONT_COMPAT
    : BOOK_FONT;
}

/** 与 A4 @ 96dpi 接近的内容宽度 */
const SHEET_WIDTH_PX = 794;
/** html2canvas 清晰度（1.5 在 A4 正文下足够，比 2 快约一倍） */
const CANVAS_SCALE = 1.5;
const JPEG_QUALITY = 0.88;
const BLOCK_GAP_MM = 4;

/** PDF 页边距（mm） */
const PDF_MARGIN_X = 18;
const PDF_MARGIN_TOP = 22;
const PDF_MARGIN_BOTTOM = 18;

/**
 * 导出截图用图源：把本服务 API 的绝对地址剥成同源相对路径（/api/v1/...），html2canvas 才肯画。
 * 页面在 :6889、API 在 :6888 时，绝对直链属跨域，会被整张跳过（空白框）；
 * 相对路径在开发环境走 Vite 代理、生产本来就同源。data:/blob:/相对路径/外部链接原样返回。
 */
export function exportImageSrc(path: string | undefined | null): string {
  const raw = String(path ?? "").trim();
  if (!raw) return "";
  if (!/^https?:\/\//i.test(raw)) return raw;
  try {
    const url = new URL(raw);
    return url.pathname.startsWith("/api/")
      ? `${url.pathname}${url.search}${url.hash}`
      : raw;
  } catch {
    return raw;
  }
}

// ── 课堂讲评导出偏好（localStorage，惯例对齐 globalPrintPrefs / printWrongNotes）──
export const CLASS_REVIEW_EXPORT_PREFS_KEY = "class_review_export_prefs_v1";

export type ClassReviewExportPrefs = {
  /** 导出讲评方案 PDF 时是否附上「错题原卷」附录（默认开） */
  includeWrongPaper: boolean;
};

export type ClassReviewExportOptions = {
  /** 覆盖本地偏好；不传则读 localStorage */
  includeWrongPaper?: boolean;
};

export function defaultClassReviewExportPrefs(): ClassReviewExportPrefs {
  return { includeWrongPaper: true };
}

export function readClassReviewExportPrefs(): ClassReviewExportPrefs {
  const defaults = defaultClassReviewExportPrefs();
  try {
    const raw = localStorage.getItem(CLASS_REVIEW_EXPORT_PREFS_KEY);
    if (!raw) return defaults;
    const j = JSON.parse(raw);
    return {
      includeWrongPaper:
        typeof j?.includeWrongPaper === "boolean"
          ? j.includeWrongPaper
          : defaults.includeWrongPaper,
    };
  } catch {
    return defaults;
  }
}

export function writeClassReviewExportPrefs(
  prefs: ClassReviewExportPrefs,
): void {
  try {
    localStorage.setItem(
      CLASS_REVIEW_EXPORT_PREFS_KEY,
      JSON.stringify({
        includeWrongPaper: prefs.includeWrongPaper,
      }),
    );
  } catch {
    // ignore quota / private mode
  }
}

/** 错题原卷条目结构：与 classReview 报告 pre_class.all_wrong_images / 网页预览一致 */
export type WrongPaperImage = {
  student_name?: string;
  title?: string;
  image_url?: string;
  answer_url?: string;
};

/**
 * 从标题解析排序键：「第12题-区3」「第12题」「12.」等。
 * 题号优先，同题再按作答区号；解析失败排最后。
 */
export function parseWrongPaperSortKey(title: unknown): {
  q: number;
  slot: number;
} {
  const s = String(title ?? "");
  const qm = s.match(/(\d+)\s*题/) || s.match(/(\d+)/);
  const sm = s.match(/区\s*(\d+)/) || s.match(/[-_]\s*s(\d+)/i);
  return {
    q: qm ? Number(qm[1]) : Number.MAX_SAFE_INTEGER,
    slot: sm ? Number(sm[1]) : 0,
  };
}

/** 按学生分节，节内按题号/作答区排序（与网页预览分组一致） */
export function groupWrongPaperImagesByStudent(
  images: unknown,
): Array<{ student: string; items: WrongPaperImage[] }> {
  const list = Array.isArray(images) ? images : [];
  const map = new Map<string, WrongPaperImage[]>();
  for (const raw of list) {
    const img = (raw || {}) as WrongPaperImage;
    const student = String(img.student_name || "").trim() || "未命名学生";
    const bucket = map.get(student);
    if (bucket) bucket.push(img);
    else map.set(student, [img]);
  }
  return Array.from(map.entries()).map(([student, items]) => ({
    student,
    items: [...items].sort((a, b) => {
      const ka = parseWrongPaperSortKey(a.title);
      const kb = parseWrongPaperSortKey(b.title);
      return ka.q - kb.q || ka.slot - kb.slot;
    }),
  }));
}

interface PdfLayout {
  marginX: number;
  marginTop: number;
  marginBottom: number;
  contentWidth: number;
  contentHeight: number;
  pageWidth: number;
  pageHeight: number;
}

function getPdfLayout(pdf: jsPDF): PdfLayout {
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  return {
    marginX: PDF_MARGIN_X,
    marginTop: PDF_MARGIN_TOP,
    marginBottom: PDF_MARGIN_BOTTOM,
    contentWidth: pageWidth - PDF_MARGIN_X * 2,
    contentHeight: pageHeight - PDF_MARGIN_TOP - PDF_MARGIN_BOTTOM,
    pageWidth,
    pageHeight,
  };
}

function drawPageFooters(pdf: jsPDF, layout: PdfLayout, docTitle: string) {
  const total = pdf.getNumberOfPages();
  const footerY = layout.pageHeight - 10;
  for (let i = 1; i <= total; i++) {
    pdf.setPage(i);
    pdf.setDrawColor(200, 205, 212);
    pdf.setLineWidth(0.2);
    pdf.line(layout.marginX, footerY - 4, layout.pageWidth - layout.marginX, footerY - 4);
    pdf.setFont("helvetica", "normal");
    pdf.setFontSize(8);
    pdf.setTextColor(130, 135, 145);
    pdf.text(docTitle, layout.marginX, footerY);
    pdf.text(`${i} / ${total}`, layout.pageWidth - layout.marginX, footerY, { align: "right" });
  }
}

const TRACKING_PLACEHOLDER = "课后填写课堂效果后，AI会评估本堂讲评质量与优缺点。";
const CONSOLIDATION_PLACEHOLDER = "课后填写课堂效果后，AI会生成二次讲解与巩固方案。";

function asArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((x) => String(x ?? "").trim()).filter(Boolean);
}

function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderList(items: unknown, empty = "暂无内容") {
  const list = asArray(items);
  if (!list.length) return `<p class="muted">${escapeHtml(empty)}</p>`;
  return `<ol>${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>`;
}

function exportBlock(inner: string) {
  return `<div class="export-block" data-export-block>${inner}</div>`;
}

/** 多个章节合并为一块截图，减少 html2canvas 调用次数 */
function exportSectionsStack(...parts: string[]) {
  return exportBlock(`<div class="section-stack">${parts.join("")}</div>`);
}

function sectionPart(title: string, inner: string) {
  return `
    <section class="section-part">
      <h2>${escapeHtml(title)}</h2>
      ${inner}
    </section>
  `;
}

function exportSection(title: string, inner: string) {
  return exportBlock(sectionPart(title, inner));
}

function renderFlow(flow: unknown) {
  const steps = Array.isArray(flow) ? flow : [];
  if (!steps.length) {
    return exportBlock(`${sectionPart("讲评流程时间轴", `<p class="muted">暂无讲评流程</p>`)}`);
  }
  return steps
    .map((step: any, index: number) => {
      const title = escapeHtml(step?.step || `环节${index + 1}`);
      const minutes = escapeHtml(step?.minutes || "-");
      const teacher = escapeHtml(step?.teacher_action || "暂无");
      const student = escapeHtml(step?.student_action || "暂无");
      const flowHeader =
        index === 0
          ? `<section class="section-part flow-section-head"><h2>讲评流程时间轴</h2></section>`
          : "";
      return exportBlock(`
        ${flowHeader}
        <div class="flow-item">
          <div class="flow-head"><strong>${index + 1}. ${title}</strong><span class="flow-time">${minutes} 分钟</span></div>
          <div class="flow-grid">
            <div><span class="flow-label">教师动作</span>${teacher}</div>
            <div><span class="flow-label">学生活动</span>${student}</div>
          </div>
        </div>
      `);
    })
    .join("");
}

function renderInsightBoxes(title: string, items: unknown, empty: string) {
  return exportBlock(`
    <div class="box">
      <h3>${escapeHtml(title)}</h3>
      ${renderList(items, empty)}
    </div>
  `);
}

function renderTiered(groups: unknown) {
  const list = Array.isArray(groups) ? groups : [];
  if (!list.length) return exportBlock(`<p class="muted">暂无分层任务</p>`);
  return list
    .map((group: any, index: number) => {
      const level = escapeHtml(group?.level || `层级${index + 1}`);
      return exportBlock(`
        <div class="box">
          <h3>${level}</h3>
          ${renderList(group?.tasks, "暂无任务")}
        </div>
      `);
    })
    .join("");
}

function baseStyles() {
  const font = getBookFont();
  return `
    .cr-sheet { box-sizing: border-box; width: ${SHEET_WIDTH_PX}px; padding: 52px 58px; color: #1c1c1c; font-family: ${font}; font-size: 14px; line-height: 1.72; background: #fff; }
    .cr-sheet * { box-sizing: border-box; }
    .export-block { width: 100%; }
    .export-divider .divider { margin: 0; }
    .cr-doc .top { text-align: center; border-bottom: 2px solid #1a3a5c; padding-bottom: 18px; margin-bottom: 20px; }
    .cr-doc .report-label { margin: 0 0 10px; font-size: 11px; letter-spacing: 0.18em; color: #1a3a5c; font-weight: 600; }
    .cr-doc h1 { margin: 0; font-size: 24px; font-weight: 700; line-height: 1.35; color: #111; font-family: ${font}; letter-spacing: 0.04em; }
    .cr-doc .subtitle { margin-top: 8px; color: #5c6678; font-size: 12px; letter-spacing: 0.02em; }
    .cr-doc .meta { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 20px; margin: 0; padding: 14px 16px; border: 1px solid #d5dae3; border-radius: 2px; background: linear-gradient(180deg, #fafbfd 0%, #f4f6f9 100%); }
    .cr-doc .meta div { font-size: 12.5px; color: #333; line-height: 1.5; }
    .cr-doc .meta b { color: #1a3a5c; margin-right: 8px; font-weight: 700; }
    .cr-doc section { margin: 0; }
    .cr-doc .section-stack .section-part + .section-part { margin-top: 16px; padding-top: 16px; border-top: 1px solid #e8ebf0; }
    .cr-doc .flow-section-head { margin-bottom: 12px; }
    .cr-doc .flow-section-head h2 { margin-bottom: 0; border-bottom: none; padding-bottom: 0; }
    .cr-doc section h2:only-child { margin-bottom: 0; }
    .cr-doc h2 { margin: 0 0 12px; font-size: 15.5px; font-weight: 700; color: #1a3a5c; border-left: 4px solid #1a3a5c; border-bottom: 1px solid #e8ebf0; padding: 0 0 7px 12px; font-family: ${font}; }
    .cr-doc h3 { margin: 0 0 10px; font-size: 14px; font-weight: 700; color: #243b53; }
    .cr-doc .summary { border: 1px solid #d5dae3; border-left: 4px solid #1a3a5c; background: #f7f9fc; padding: 14px 16px; font-size: 14px; line-height: 1.8; color: #222; text-align: justify; }
    .cr-doc .box { border: 1px solid #d5dae3; border-radius: 2px; padding: 12px 14px; background: #fff; }
    .cr-doc ol { margin: 0; padding-left: 24px; }
    .cr-doc li { margin: 6px 0; font-size: 13px; line-height: 1.68; color: #2a2a2a; }
    .cr-doc .muted { margin: 0; color: #6b7280; font-size: 12.5px; }
    .cr-doc .pill { display: inline-block; border: 1px solid #c5ccd8; border-radius: 2px; padding: 4px 10px; margin: 4px 8px 4px 0; font-size: 12px; background: #f4f6f9; color: #334155; }
    .cr-doc .flow-item { border: 1px solid #d5dae3; border-radius: 2px; padding: 12px 14px; background: #fff; }
    .cr-doc .flow-head { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 10px; font-size: 14px; padding-bottom: 8px; border-bottom: 1px dashed #e2e6ed; }
    .cr-doc .flow-time { color: #5c6678; font-size: 12px; white-space: nowrap; }
    .cr-doc .flow-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; font-size: 13px; }
    .cr-doc .flow-label { display: block; font-weight: 700; margin-bottom: 5px; color: #1a3a5c; font-size: 12px; }
    .cr-doc .score { display: inline-block; margin-top: 10px; padding: 4px 12px; border: 1px solid #c5ccd8; font-size: 12px; background: #eef2f7; color: #1a3a5c; border-radius: 2px; }
    .cr-doc .duration-note { margin-top: 10px; padding-top: 8px; border-top: 1px solid #e8ebf0; font-size: 12.5px; color: #5c6678; }
    .cr-doc .wrong-student-name { margin: 0 0 10px; font-size: 14.5px; font-weight: 700; color: #1a3a5c; }
    .cr-doc .wrong-card { border: 1px solid #d5dae3; border-radius: 2px; background: #fff; overflow: hidden; }
    .cr-doc .wrong-card-title { margin: 0; padding: 8px 12px; font-size: 12.5px; font-weight: 700; color: #243b53; background: #f4f6f9; border-bottom: 1px solid #e8ebf0; }
    .cr-doc .wrong-card-body { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; padding: 10px 12px; }
    .cr-doc .wrong-img-block { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
    .cr-doc .wrong-img-label { font-size: 11px; color: #5c6678; }
    .cr-doc .wrong-img-frame { border: 1px solid #e2e6ed; border-radius: 2px; background: #fff; padding: 6px; display: flex; align-items: center; justify-content: center; min-height: 72px; }
    .cr-doc .wrong-img { display: block; max-width: 100%; max-height: 220px; height: auto; object-fit: contain; }
    .cr-doc .wrong-img-block.answer .wrong-img { max-height: 120px; }
    .cr-doc .wrong-empty { color: #6b7280; font-size: 11px; }
  `;
}

function metaBlock(report: ClassReviewReport, subject: string) {
  const summary = report.source_summary || {};
  const generatedAt = report.generated_at
    ? new Date(report.generated_at).toLocaleString("zh-CN")
    : new Date().toLocaleString("zh-CN");
  const examNames = report.exam_names || [];
  return `
    <div class="meta">
      <div><b>学科</b>${escapeHtml(subject)}</div>
      <div><b>生成时间</b>${escapeHtml(generatedAt)}</div>
      <div><b>导入考试</b>${escapeHtml(String(examNames.length))} 场</div>
      <div><b>有效学生</b>${escapeHtml(String(summary.valid_student_count ?? 0))} 人</div>
    </div>
  `;
}

export function hasReviewPlanContent(report: ClassReviewReport | null | undefined): boolean {
  if (!report?.pre_class) return false;
  const overview = report.pre_class.overview || {};
  const plan = report.pre_class.review_plan || {};
  return Boolean(
    String(overview.summary || "").trim() ||
      asArray(plan.key_points).length ||
      asArray(plan.objectives).length ||
      asArray(overview.weak_points).length ||
      (Array.isArray(plan.teaching_flow) && plan.teaching_flow.length > 0)
  );
}

export function hasConsolidationContent(report: ClassReviewReport | null | undefined): boolean {
  if (!report) return false;
  const tracking = report.tracking || {};
  const consolidation = report.consolidation || {};
  const trackingSummary = String(tracking.summary || "").trim();
  const consolidationSummary = String(consolidation.summary || "").trim();

  if (tracking.quality_score !== undefined && tracking.quality_score !== null) return true;
  if (trackingSummary && !trackingSummary.includes("课后填写课堂效果后")) return true;
  if (consolidationSummary && !consolidationSummary.includes("课后填写课堂效果后")) return true;
  if (asArray(tracking.strengths).length || asArray(tracking.problems).length) return true;
  if (asArray(consolidation.reteaching_points).length || asArray(consolidation.lesson_adjustments).length) return true;
  if (Array.isArray(consolidation.tiered_practice) && consolidation.tiered_practice.length > 0) return true;
  return false;
}

/** 错题原卷单题卡片：原卷图 + 作答区域图（URL 经 exportImageSrc 转同源，html2canvas 才画） */
function renderWrongPaperCard(img: WrongPaperImage) {
  const title = escapeHtml(img.title || "错题");
  const questionUrl = img.image_url ? exportImageSrc(img.image_url) : "";
  const answerUrl = img.answer_url ? exportImageSrc(img.answer_url) : "";
  const questionHtml = questionUrl
    ? `<img class="wrong-img" src="${escapeHtml(questionUrl)}" alt="${title}" />`
    : `<p class="wrong-empty">暂无图片</p>`;
  const answerHtml = answerUrl
    ? `<div class="wrong-img-block answer">
         <div class="wrong-img-label">作答区域</div>
         <div class="wrong-img-frame">
           <img class="wrong-img" src="${escapeHtml(answerUrl)}" alt="${title} 作答" />
         </div>
       </div>`
    : "";
  return exportBlock(`
    <div class="wrong-card">
      <p class="wrong-card-title">${title}</p>
      <div class="wrong-card-body">
        <div class="wrong-img-block">
          <div class="wrong-img-label">错题原卷</div>
          <div class="wrong-img-frame">${questionHtml}</div>
        </div>
        ${answerHtml}
      </div>
    </div>
  `);
}

/**
 * 「错题原卷」附录：按学生分节，节内按题号/作答区排序。
 * 无图时返回空串，不占导出篇幅。
 */
function renderWrongPaperSection(images: unknown) {
  const groups = groupWrongPaperImagesByStudent(images);
  if (!groups.length) return "";
  const parts: string[] = [
    exportBlock(
      sectionPart(
        "错题原卷",
        `<p class="muted">按学生汇总的错题原卷与作答区域，供课堂讲评对照使用。</p>`
      )
    ),
  ];
  for (const group of groups) {
    parts.push(
      exportBlock(
        `<p class="wrong-student-name">学生：${escapeHtml(group.student)}</p>`
      )
    );
    for (const img of group.items) {
      parts.push(renderWrongPaperCard(img));
    }
  }
  return parts.join("");
}

/** 等离屏 DOM 内图片加载完成再截图，避免 html2canvas 拍到空白图框；字体就绪再量高度，防文字排版漂移 */
async function waitForImages(root: HTMLElement) {
  try {
    await document.fonts.ready;
  } catch {
    // 个别浏览器无 fonts API，忽略
  }
  const imgs = Array.from(root.querySelectorAll("img"));
  await Promise.all(
    imgs.map(
      (img) =>
        new Promise<void>((resolve) => {
          if (img.complete) {
            resolve();
            return;
          }
          const done = () => resolve();
          img.addEventListener("load", done, { once: true });
          img.addEventListener("error", done, { once: true });
        })
    )
  );
}

function mountExportRoot(innerHtml: string) {
  const el = document.createElement("div");
  el.style.position = "fixed";
  el.style.left = "-10000px";
  el.style.top = "0";
  el.style.width = `${SHEET_WIDTH_PX}px`;
  el.style.background = "#fff";
  el.innerHTML = `<style>${baseStyles()}</style><div class="cr-doc">${innerHtml}</div>`;
  document.body.appendChild(el);
  return el;
}

function createReviewPlanElement(
  report: ClassReviewReport,
  subject: string,
  includeWrongPaper: boolean
) {
  const preClass = report.pre_class || {};
  const overview = preClass.overview || {};
  const plan = preClass.review_plan || {};
  const examNames = report.exam_names || [];

  const examPills =
    examNames.length
      ? examNames.map((n) => `<span class="pill">${escapeHtml(n)}</span>`).join("")
      : `<p class="muted">暂无导入考试</p>`;

  const wrongPaperHtml = includeWrongPaper
    ? renderWrongPaperSection(preClass.all_wrong_images)
    : "";

  const innerHtml = `
    <div class="cr-sheet" data-export-sheet>
      ${exportBlock(`
        <div class="top">
          <p class="report-label">CLASS REVIEW REPORT</p>
          <h1>${escapeHtml(subject)}课堂讲评方案</h1>
          <div class="subtitle">课前分析报告 · AI 智能生成</div>
        </div>
        ${metaBlock(report, subject)}
      `)}
      ${exportSectionsStack(
        sectionPart("数据根据", `<div class="box">${examPills}</div>`),
        sectionPart(
          "讲评概要",
          `<div class="summary">${escapeHtml(overview.summary || "已生成课堂讲评方案")}</div>
           <p class="duration-note">建议讲评时长：${escapeHtml(plan.duration || "待定")}</p>`
        )
      )}
      ${exportSection("课堂重点知识点", renderList(plan.key_points, "暂无重点知识点"))}
      ${renderInsightBoxes("本班整体薄弱点", overview.weak_points, "暂无")}
      ${renderInsightBoxes("班级优势表现", overview.strengths, "暂无")}
      ${renderInsightBoxes("数据证据", overview.data_basis, "暂无")}
      ${exportSectionsStack(
        sectionPart("讲评目标", renderList(plan.objectives)),
        sectionPart("板书设计", renderList(plan.blackboard_design)),
        sectionPart("课堂互动问题", renderList(plan.interaction_questions))
      )}
      ${renderFlow(plan.teaching_flow)}
      ${wrongPaperHtml}
    </div>
  `;
  return mountExportRoot(innerHtml);
}

function createConsolidationElement(report: ClassReviewReport, subject: string) {
  const tracking = report.tracking || {};
  const consolidation = report.consolidation || {};

  const qualityScore =
    tracking.quality_score !== undefined && tracking.quality_score !== null
      ? `<span class="score">讲评质量评分：${escapeHtml(tracking.quality_score)}</span>`
      : "";

  const innerHtml = `
    <div class="cr-sheet" data-export-sheet>
      ${exportBlock(`
        <div class="top">
          <p class="report-label">POST-CLASS REVIEW</p>
          <h1>课后讲评复盘与二次巩固</h1>
          <div class="subtitle">${escapeHtml(subject)} · 课后跟踪报告</div>
        </div>
        ${metaBlock(report, subject)}
      `)}
      ${exportBlock(sectionPart(
        "本次讲课分析",
        `<div class="summary">${escapeHtml(tracking.summary || TRACKING_PLACEHOLDER)}${qualityScore}</div>`
      ))}
      ${exportSectionsStack(
        sectionPart("讲课亮点", renderList(tracking.strengths, "暂无讲课优点分析")),
        sectionPart("待优化问题", renderList(tracking.problems, "暂无讲课不足分析")),
        sectionPart("下次改进建议", renderList(tracking.improvement_suggestions, "暂无改进建议"))
      )}
      ${exportBlock(sectionPart(
        "二次讲评建议",
        `<div class="summary">${escapeHtml(consolidation.summary || CONSOLIDATION_PLACEHOLDER)}</div>`
      ))}
      ${exportSectionsStack(
        sectionPart("二次讲解重点", renderList(consolidation.reteaching_points, "暂无二次讲解点")),
        sectionPart("课堂调整策略", renderList(consolidation.lesson_adjustments, "暂无二次讲课调整策略"))
      )}
      ${exportBlock(sectionPart("分层巩固任务", ""))}
      ${renderTiered(consolidation.tiered_practice)}
    </div>
  `;
  return mountExportRoot(innerHtml);
}

/** 单块超高时仍按比例分页切片（极少出现） */
function appendTallCanvasToPdf(
  pdf: jsPDF,
  canvas: HTMLCanvasElement,
  pageBreakBefore: boolean,
  layout: PdfLayout
) {
  const imgData = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
  const imgWidth = layout.contentWidth;
  const imgHeight = (canvas.height * imgWidth) / canvas.width;

  let heightLeft = imgHeight;
  let position = 0;
  let firstSlice = true;

  if (pageBreakBefore) {
    pdf.addPage();
    firstSlice = false;
  }

  while (heightLeft > 0) {
    if (!firstSlice) pdf.addPage();
    else firstSlice = false;
    pdf.addImage(imgData, "JPEG", layout.marginX, layout.marginTop + position, imgWidth, imgHeight);
    heightLeft -= layout.contentHeight;
    position -= layout.contentHeight;
  }
}

/** 攒批截图：单次 html2canvas 最多覆盖的 CSS 高度（约 8~10 张错题卡），把调用次数压一个量级 */
const CAPTURE_BATCH_MAX_PX = 2800;

/**
 * 切点吸附：在 y 附近找最近的一整行空白像素。html2canvas 克隆排版与实测有细小漂移，
 * 硬按块边界切会把「建议讲评时长」这类贴边文字行拦腰切成两块（各带半个字）；
 * 吸附到空白行后两边文字都完整。找不到空白行（如错题卡相邻的描边）就按原位切。
 */
function snapCutToBlankRow(canvas: HTMLCanvasElement, y: number, search = 40): number {
  const h = canvas.height;
  const target = Math.max(1, Math.min(h - 1, Math.round(y)));
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return target;
  const top = Math.max(1, target - search);
  const bottom = Math.min(h - 1, target + search);
  const win = ctx.getImageData(0, top, canvas.width, bottom - top + 1).data;
  const w = canvas.width;
  const blankAt = (row: number) => {
    const base = (row - top) * w * 4;
    for (let i = 0; i < w * 4; i += 4) {
      if (win[base + i] < 245 || win[base + i + 1] < 245 || win[base + i + 2] < 245) {
        return false;
      }
    }
    return true;
  };
  if (blankAt(target)) return target;
  for (let d = 1; d <= search; d++) {
    if (target - d >= top && blankAt(target - d)) return target - d;
    if (target + d <= bottom && blankAt(target + d)) return target + d;
  }
  return target;
}

/**
 * 连续内容块攒批截图：每批对 sheet 裁一条横带一次成图，再按块切出与逐块截图等价的画布。
 * 逐块调用 html2canvas 时每次都要克隆整棵 DOM 并把全部图片重解一遍，上百张错题卡会拖到几分钟。
 * 截完的块顺手移出离屏 DOM，越往后克隆越小；克隆树只留导出根（页面本体的大图预览不进克隆）。
 * 切点用 snapCutToBlankRow 吸附空白行，宁可少切一截留白，也不把文字行切成两半。
 */
async function captureBlocksCanvases(
  sheet: HTMLElement,
  blocks: HTMLElement[],
  exportRoot: HTMLElement,
): Promise<HTMLCanvasElement[]> {
  const out: HTMLCanvasElement[] = [];
  const queue = [...blocks];
  while (queue.length) {
    const batch: HTMLElement[] = [];
    let batchH = 0;
    while (queue.length) {
      const h = queue[0].getBoundingClientRect().height;
      if (batch.length && batchH + h > CAPTURE_BATCH_MAX_PX) break;
      batchH += h;
      batch.push(queue.shift()!);
    }
    const sheetRect = sheet.getBoundingClientRect();
    const rects = batch.map((el) => el.getBoundingClientRect());
    const canvas = await html2canvas(sheet, {
      scale: CANVAS_SCALE,
      useCORS: false,
      logging: false,
      backgroundColor: "#ffffff",
      x: rects[0].left - sheetRect.left,
      y: rects[0].top - sheetRect.top,
      width: rects[0].width,
      height: rects[rects.length - 1].bottom - rects[0].top,
      ignoreElements: (el) => el.parentElement === document.body && el !== exportRoot,
    });
    const cuts: number[] = [0];
    for (let i = 1; i < rects.length; i++) {
      const y = Math.round((rects[i].top - rects[0].top) * CANVAS_SCALE);
      cuts.push(Math.max(cuts[i - 1], snapCutToBlankRow(canvas, y)));
    }
    cuts.push(canvas.height);
    for (let i = 0; i < rects.length; i++) {
      const y0 = cuts[i];
      const y1 = Math.max(y0 + 1, cuts[i + 1]);
      const slice = document.createElement("canvas");
      slice.width = canvas.width;
      slice.height = y1 - y0;
      slice
        .getContext("2d")
        ?.drawImage(canvas, 0, y0, canvas.width, slice.height, 0, 0, canvas.width, slice.height);
      out.push(slice);
    }
    for (const el of batch) el.remove();
  }
  return out;
}

/**
 * 按不可分割块逐块写入 PDF：当前页剩余空间不足时整块移到下一页，避免文本框被拦腰切断。
 */
async function renderElementToPdf(element: HTMLElement, filename: string, docTitle: string) {
  const pdf = new jsPDF("p", "mm", "a4");
  const layout = getPdfLayout(pdf);
  const sheet = element.querySelector<HTMLElement>("[data-export-sheet]") || element;
  const blocks = Array.from(sheet.querySelectorAll<HTMLElement>("[data-export-block]"));

  // 错题原卷附录带 <img>，先等图加载再攒批截图
  await waitForImages(sheet);
  const canvases = await captureBlocksCanvases(sheet, blocks, element);

  let y = 0;
  let hasPage = false;

  for (const canvas of canvases) {
    const imgWidth = layout.contentWidth;
    const blockHeightMm = (canvas.height * imgWidth) / canvas.width;
    const imgData = canvas.toDataURL("image/jpeg", JPEG_QUALITY);

    if (blockHeightMm >= layout.contentHeight - 0.5) {
      appendTallCanvasToPdf(pdf, canvas, hasPage, layout);
      hasPage = true;
      y = 0;
      continue;
    }

    const gap = y > 0 ? BLOCK_GAP_MM : 0;
    if (hasPage && y + gap + blockHeightMm > layout.contentHeight) {
      pdf.addPage();
      y = 0;
    }

    const drawY = layout.marginTop + y + (y > 0 ? BLOCK_GAP_MM : 0);
    if (y > 0) y += BLOCK_GAP_MM;
    pdf.addImage(imgData, "JPEG", layout.marginX, drawY, imgWidth, blockHeightMm);
    y += blockHeightMm;
    hasPage = true;
  }

  drawPageFooters(pdf, layout, docTitle);
  pdf.save(filename);
}

export type ClassReviewPdfKind = "review_plan" | "consolidation";

export async function exportClassReviewPdf(
  kind: ClassReviewPdfKind,
  report: ClassReviewReport,
  subject: string,
  options?: ClassReviewExportOptions
) {
  // 错题原卷只进「讲评方案」PDF；二次巩固是课后文档不附图
  const includeWrongPaper =
    kind === "review_plan" &&
    (options?.includeWrongPaper ??
      readClassReviewExportPrefs().includeWrongPaper);
  const date = new Date().toLocaleDateString("zh-CN").replace(/\//g, "-");
  const element =
    kind === "review_plan"
      ? createReviewPlanElement(report, subject, includeWrongPaper)
      : createConsolidationElement(report, subject);
  const filename =
    kind === "review_plan"
      ? `${subject}_课堂讲评方案_${date}.pdf`
      : `${subject}_二次巩固方案_${date}.pdf`;
  const docTitle =
    kind === "review_plan" ? "Class Review Report" : "Post-Class Review";
  try {
    await renderElementToPdf(element, filename, docTitle);
  } finally {
    if (element.parentNode) element.parentNode.removeChild(element);
  }
}
