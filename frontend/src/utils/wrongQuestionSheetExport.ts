/**
 * 错题巩固卷（错题挑题 → 新卷 PDF → 下发打印）导出。
 * 与课堂讲评方案 PDF（classReviewPdfExport）互不干扰：独立离屏排版 + html2canvas/jsPDF。
 * 原题图直接复用讲评已有的错题裁图资产（pre_class.all_wrong_images）。
 * 一体机文印仅留接口 stub，待机型/协议确定后对接。
 */
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import { gradingImageUrl } from "@/services/gradingApi";
import { parseWrongPaperSortKey } from "@/utils/classReviewPdfExport";
import { readGlobalPrintPrefs } from "@/lib/globalPrintPrefs";

const BOOK_FONT =
  '"SimSun", "Songti SC", "STSong", "Times New Roman", "Georgia", "Microsoft YaHei", "PingFang SC", serif';
const BOOK_FONT_COMPAT =
  '"SimSun", "Songti SC", "Noto Serif SC", "SimHei", "Microsoft YaHei", serif';

function getBookFont(): string {
  return readGlobalPrintPrefs().printMode === "compat"
    ? BOOK_FONT_COMPAT
    : BOOK_FONT;
}

const SHEET_WIDTH_PX = 794;
const CANVAS_SCALE = 1.5;
const JPEG_QUALITY = 0.88;
const BLOCK_GAP_MM = 4;
const PDF_MARGIN_X = 18;
const PDF_MARGIN_TOP = 18;
const PDF_MARGIN_BOTTOM = 16;

/** 空选择错误码：UI 侧据此映射 i18n 文案 */
export const WRONG_SHEET_EMPTY_SELECTION = "WRONG_SHEET_EMPTY_SELECTION";

// ── 数据装配（纯函数，供测试） ──

/** 错题卷单题条目 */
export type WrongSheetItem = {
  /** 稳定 ID：question_key 优先 */
  id: string;
  /** 展示题号：real_number / display_title / question_key */
  title: string;
  questionText?: string;
  /** 原题裁图 URL（相对路径，渲染时经 gradingImageUrl 转绝对） */
  imageUrl?: string;
  /** 作答区裁图 URL */
  answerImageUrl?: string;
  wrongCount?: number;
  accuracy?: number;
  /** 典型错因（来自 question_accuracy.top_reasons） */
  topReasons?: Array<{ reason: string; count: number }>;
  /** 错答学生名单 */
  studentNames?: string[];
};

export type WrongSheetMeta = {
  className: string;
  subject: string;
  date: string;
  /** 卷头标题，默认「错题巩固卷」 */
  title?: string;
};

export type WrongSheetPlan = {
  meta: WrongSheetMeta;
  /** 题目分页（每页若干题，按题号排序后切分） */
  pages: WrongSheetItem[][];
  /** 答案与解析（开关关闭时为 null） */
  answerPage: { items: WrongSheetItem[] } | null;
};

const CN_DIGITS: Record<string, number> = {
  零: 0,
  一: 1,
  二: 2,
  两: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
  八: 8,
  九: 9,
};

function cnToNumber(raw: string): number | null {
  const s = (raw || "").trim();
  if (!s) return null;
  if (/^\d+$/.test(s)) return Number(s);
  if (s.includes("十")) {
    // 注意：split("十", 1) 的 limit 是结果数组长度不是分割次数，要用 indexOf 切
    const idx = s.indexOf("十");
    const left = s.slice(0, idx);
    const right = s.slice(idx + 1);
    const tens = left ? (CN_DIGITS[left] ?? null) : 1;
    const ones = right ? (CN_DIGITS[right] ?? null) : 0;
    if (tens === null || ones === null) return null;
    return tens * 10 + ones;
  }
  if (s.length === 1 && s in CN_DIGITS) return CN_DIGITS[s];
  return null;
}

/**
 * 从标题解析题号：「第12题-区3」「第十二题」「3.」「三、2（1）」等。
 * 解析失败排最后（MAX_SAFE_INTEGER）。
 */
export function questionNumberFromTitle(title: unknown): number {
  const s = String(title ?? "").trim();
  if (!s) return Number.MAX_SAFE_INTEGER;
  const parsed = parseWrongPaperSortKey(s);
  if (parsed.q !== Number.MAX_SAFE_INTEGER) return parsed.q;
  const cn = s.match(/第\s*([零一二两三四五六七八九十]+)\s*题/);
  if (cn) {
    const n = cnToNumber(cn[1]);
    if (n !== null) return n;
  }
  const lead = s.match(/^([零一二两三四五六七八九十]+|[0-9]+)\s*[、.．]/);
  if (lead) {
    const n = cnToNumber(lead[1]);
    if (n !== null) return n;
  }
  return Number.MAX_SAFE_INTEGER;
}

/** 按题号升序（解析失败排最后，同题号保持相对顺序） */
export function sortWrongSheetItems(items: WrongSheetItem[]): WrongSheetItem[] {
  return [...items].sort(
    (a, b) => questionNumberFromTitle(a.title) - questionNumberFromTitle(b.title),
  );
}

/** 按每页题数切分（perPage < 1 时按 1） */
export function paginateWrongSheetItems(
  items: WrongSheetItem[],
  perPage = 2,
): WrongSheetItem[][] {
  const size = Math.max(1, Math.trunc(perPage) || 1);
  const pages: WrongSheetItem[][] = [];
  for (let i = 0; i < items.length; i += size) {
    pages.push(items.slice(i, i + size));
  }
  return pages;
}

/** 全选 TOP N：列表已按正确率升序（最薄弱在前），取前 n 个 id */
export function selectTopWrongKeys(
  accuracyList: Array<{ question_key?: string; display_title?: string }>,
  n: number,
): string[] {
  const list = Array.isArray(accuracyList) ? accuracyList : [];
  const take = Math.max(0, Math.trunc(n) || 0);
  return list
    .slice(0, take)
    .map((q) => String(q?.question_key || q?.display_title || "").trim())
    .filter(Boolean);
}

type WrongImageLike = {
  student_name?: string;
  title?: string;
  image_url?: string;
  answer_url?: string;
};

/**
 * 为目标题挑一张原题裁图：
 * 1) 题号对齐（兼容中文数字题号）
 * 2) studentFilter 非空时优先这些学生的图
 * 3) 优先带 image_url 的条目
 */
export function matchWrongImageForQuestion(
  images: unknown,
  target: { question_key?: string; display_title?: string; real_number?: string; title?: string },
  studentFilter?: string[],
): WrongImageLike | null {
  const list = (Array.isArray(images) ? images : []) as WrongImageLike[];
  const targetTitles = [
    target.title,
    target.real_number,
    target.display_title,
    target.question_key,
  ]
    .map((x) => String(x ?? "").trim())
    .filter(Boolean);
  const targetNums = new Set(
    targetTitles
      .map((t) => questionNumberFromTitle(t))
      .filter((n) => n !== Number.MAX_SAFE_INTEGER),
  );
  const filter =
    studentFilter && studentFilter.length
      ? new Set(studentFilter.map((s) => String(s).trim()).filter(Boolean))
      : null;

  const scored = list
    .map((img) => {
      const imgNum = questionNumberFromTitle(img?.title);
      const numHit = targetNums.has(imgNum) ? 1 : 0;
      const studentHit = filter && img?.student_name && filter.has(img.student_name) ? 1 : 0;
      const hasImage = img?.image_url ? 1 : 0;
      return { img, numHit, studentHit, hasImage };
    })
    .filter((x) => x.numHit > 0);

  if (!scored.length) return null;
  scored.sort(
    (a, b) =>
      b.studentHit - a.studentHit ||
      b.hasImage - a.hasImage ||
      String(a.img?.student_name || "").localeCompare(String(b.img?.student_name || "")),
  );
  return scored[0].img;
}

function asString(v: unknown): string {
  return String(v ?? "").trim();
}

export type AssembleWrongSheetParams = {
  selectedKeys: string[];
  /** report.source_summary.question_accuracy */
  questionAccuracy: unknown[];
  /** report.pre_class.all_wrong_images */
  allWrongImages: unknown[];
  /** 可选：report.source_summary.question_students（错答名单） */
  questionStudents?: Record<string, unknown>;
  /** 可选：只纳入这些学生的错题/图 */
  studentFilter?: string[];
};

/**
 * 把勾选的 question_key / display_title 装配成错题卷条目（按题号排序）。
 * studentFilter 非空时，仅保留错答学生与筛选有交集、或能匹配到筛选学生裁图的题。
 */
export function assembleWrongSheetItems(
  params: AssembleWrongSheetParams,
): WrongSheetItem[] {
  const selected = new Set(
    (params.selectedKeys || []).map((k) => String(k ?? "").trim()).filter(Boolean),
  );
  if (!selected.size) return [];
  const accuracyList = (Array.isArray(params.questionAccuracy)
    ? params.questionAccuracy
    : []) as Array<Record<string, any>>;
  const filter =
    params.studentFilter && params.studentFilter.length
      ? new Set(params.studentFilter.map((s) => String(s).trim()).filter(Boolean))
      : null;
  const studentsMap = (params.questionStudents || {}) as Record<string, any>;

  const items: WrongSheetItem[] = [];
  for (const q of accuracyList) {
    const key = asString(q?.question_key || q?.display_title);
    const title = asString(q?.real_number || q?.display_title || q?.question_key);
    const id = key || title;
    if (!id || !selected.has(id) || items.some((it) => it.id === id)) continue;

    const fromQ = Array.isArray(q?.wrong_students) ? q.wrong_students : [];
    const fromMap = Array.isArray(
      studentsMap[asString(q?.question_key)]?.wrong_students,
    )
      ? studentsMap[asString(q?.question_key)].wrong_students
      : Array.isArray(studentsMap[asString(q?.display_title)]?.wrong_students)
        ? studentsMap[asString(q?.display_title)].wrong_students
        : [];
    const wrongStudents = [...fromQ, ...fromMap]
      .map((s: unknown) => asString(s))
      .filter(Boolean);
    const img = matchWrongImageForQuestion(
      params.allWrongImages,
      {
        question_key: asString(q?.question_key),
        display_title: asString(q?.display_title),
        real_number: asString(q?.real_number),
        title,
      },
      filter ? [...filter] : undefined,
    );

    if (filter) {
      const studentHit =
        wrongStudents.some((s) => filter.has(s)) ||
        (img?.student_name ? filter.has(img.student_name) : false);
      if (!studentHit) continue;
    }

    const topReasons = Array.isArray(q?.top_reasons)
      ? q.top_reasons
          .map((r: any) => ({
            reason: asString(r?.reason),
            count: Number(r?.count) || 0,
          }))
          .filter((r: { reason: string }) => r.reason)
      : [];

    items.push({
      id,
      title: title || id,
      questionText: asString(q?.question_text) || undefined,
      imageUrl: asString(img?.image_url) || undefined,
      answerImageUrl: asString(img?.answer_url) || undefined,
      wrongCount: Number(q?.wrong_count) || 0,
      accuracy: typeof q?.accuracy === "number" ? q.accuracy : undefined,
      topReasons,
      studentNames: wrongStudents,
    });
  }
  return sortWrongSheetItems(items);
}

export type BuildWrongSheetPlanParams = {
  items: WrongSheetItem[];
  className: string;
  subject: string;
  date?: string;
  /** 是否附「答案与解析」页，默认 true */
  includeAnswers?: boolean;
  /** 每页题数，默认 2（图 + 作答空白区） */
  perPage?: number;
};

/** 装配错题卷排版计划；空选择抛 WRONG_SHEET_EMPTY_SELECTION */
export function buildWrongSheetPlan(params: BuildWrongSheetPlanParams): WrongSheetPlan {
  const items = sortWrongSheetItems(params.items || []);
  if (!items.length) {
    throw new Error(WRONG_SHEET_EMPTY_SELECTION);
  }
  const includeAnswers = params.includeAnswers !== false;
  const date =
    params.date || new Date().toLocaleDateString("zh-CN").replace(/\//g, "-");
  return {
    meta: {
      className: asString(params.className),
      subject: asString(params.subject),
      date,
      title: asString(params.title) || "错题巩固卷",
    },
    pages: paginateWrongSheetItems(items, params.perPage ?? 2),
    answerPage: includeAnswers ? { items } : null,
  };
}

// ── 一体机文印 stub（协议未定，不瞎写） ──

export type OneClickPrinterPayload = {
  pdfBlob: Blob;
  fileName: string;
  meta: WrongSheetMeta;
  /** 份数 */
  copies?: number;
};

/**
 * 一体机文印下发接口预留。
 * TODO: 待机型/协议确定后对接（抓取打印协议 / 厂商 SDK / 局域网 HTTP）。
 * 当前一律拒绝并抛出友好错误，由 UI 提示「一体机对接未配置」。
 */
export async function sendToOneClickPrinter(
  _payload: OneClickPrinterPayload,
): Promise<{ ok: false; reason: string }> {
  // TODO: 待机型/协议确定后对接一体机文印。
  throw new Error("一体机对接未配置");
}

// ── PDF 排版 + 渲染 ──

function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function exportBlock(inner: string) {
  return `<div class="export-block" data-export-block>${inner}</div>`;
}

function sheetStyles() {
  const font = getBookFont();
  return `
    .wq-sheet { box-sizing: border-box; width: ${SHEET_WIDTH_PX}px; padding: 42px 52px; color: #1c1c1c; font-family: ${font}; font-size: 14px; line-height: 1.7; background: #fff; }
    .wq-sheet * { box-sizing: border-box; }
    .export-block { width: 100%; }
    .wq-cover { text-align: center; border-bottom: 2px solid #1a3a5c; padding-bottom: 16px; margin-bottom: 8px; }
    .wq-cover .label { margin: 0 0 8px; font-size: 11px; letter-spacing: 0.2em; color: #1a3a5c; font-weight: 600; }
    .wq-cover h1 { margin: 0; font-size: 26px; font-weight: 700; letter-spacing: 0.12em; color: #111; font-family: ${font}; }
    .wq-cover .meta { display: flex; justify-content: center; gap: 18px; margin-top: 12px; font-size: 12.5px; color: #333; flex-wrap: wrap; }
    .wq-cover .meta b { color: #1a3a5c; margin-right: 6px; }
    .wq-name-row { display: flex; gap: 28px; margin-top: 14px; font-size: 13.5px; color: #222; }
    .wq-name-row .line { flex: 1; border-bottom: 1px solid #444; padding-bottom: 4px; text-align: left; }
    .wq-q { border: 1px solid #d5dae3; border-radius: 2px; background: #fff; overflow: hidden; }
    .wq-q-title { margin: 0; padding: 8px 12px; font-size: 13.5px; font-weight: 700; color: #243b53; background: #f4f6f9; border-bottom: 1px solid #e8ebf0; }
    .wq-q-body { padding: 10px 12px 12px; }
    .wq-q-stem { margin: 0 0 8px; font-size: 13px; color: #222; line-height: 1.7; white-space: pre-wrap; }
    .wq-q-image-frame { border: 1px solid #e2e6ed; border-radius: 2px; background: #fff; padding: 8px; display: flex; align-items: center; justify-content: center; min-height: 80px; }
    .wq-q-image { display: block; max-width: 100%; max-height: 260px; height: auto; object-fit: contain; }
    .wq-q-empty { color: #6b7280; font-size: 11px; }
    .wq-q-answer { margin-top: 10px; min-height: 72px; border: 1px dashed #c5ccd8; border-radius: 2px; background: repeating-linear-gradient(180deg, #fff 0, #fff 22px, #f3f5f8 22px, #f3f5f8 23px); }
    .wq-q-answer-label { margin: 8px 0 0; font-size: 11px; color: #5c6678; }
    .wq-answers h2 { margin: 0 0 12px; font-size: 16px; font-weight: 700; color: #1a3a5c; border-left: 4px solid #1a3a5c; padding-left: 10px; border-bottom: 1px solid #e8ebf0; padding-bottom: 6px; font-family: ${font}; }
    .wq-a-item { border: 1px solid #d5dae3; border-radius: 2px; padding: 10px 12px; margin-bottom: 10px; background: #fff; }
    .wq-a-title { margin: 0 0 6px; font-size: 13px; font-weight: 700; color: #243b53; }
    .wq-a-line { margin: 4px 0; font-size: 12.5px; color: #2a2a2a; line-height: 1.65; }
    .wq-a-line b { color: #1a3a5c; margin-right: 6px; }
    .wq-a-reasons { margin: 4px 0 0; padding-left: 18px; }
    .wq-a-reasons li { margin: 3px 0; font-size: 12px; color: #333; }
  `;
}

function renderCover(plan: WrongSheetPlan) {
  const { meta } = plan;
  return exportBlock(`
    <div class="wq-cover">
      <p class="label">WRONG QUESTION PRACTICE SHEET</p>
      <h1>${escapeHtml(meta.title || "错题巩固卷")}</h1>
      <div class="meta">
        <span><b>班级</b>${escapeHtml(meta.className || "—")}</span>
        <span><b>学科</b>${escapeHtml(meta.subject || "—")}</span>
        <span><b>日期</b>${escapeHtml(meta.date)}</span>
        <span><b>题数</b>${plan.pages.reduce((n, p) => n + p.length, 0)}</span>
      </div>
      <div class="wq-name-row">
        <div class="line">姓名：____________________</div>
        <div class="line">得分：________</div>
      </div>
    </div>
  `);
}

function renderQuestionBlock(item: WrongSheetItem, index: number) {
  const title = escapeHtml(item.title || `第${index + 1}题`);
  const stem = item.questionText
    ? `<p class="wq-q-stem">${escapeHtml(item.questionText)}</p>`
    : "";
  const imgUrl = item.imageUrl ? gradingImageUrl(item.imageUrl) : "";
  const imageHtml = imgUrl
    ? `<img class="wq-q-image" src="${escapeHtml(imgUrl)}" alt="${title}" />`
    : `<p class="wq-q-empty">暂无原题图，请结合题干作答</p>`;
  return exportBlock(`
    <div class="wq-q">
      <p class="wq-q-title">${index + 1}. ${title}${item.wrongCount ? `（错 ${item.wrongCount} 人）` : ""}</p>
      <div class="wq-q-body">
        ${stem}
        <div class="wq-q-image-frame">${imageHtml}</div>
        <p class="wq-q-answer-label">作答区：</p>
        <div class="wq-q-answer"></div>
      </div>
    </div>
  `);
}

function renderAnswerPage(items: WrongSheetItem[]) {
  const parts = items.map((item, index) => {
    const reasons = (item.topReasons || []).slice(0, 5);
    const reasonHtml = reasons.length
      ? `<ul class="wq-a-reasons">${reasons
          .map(
            (r) =>
              `<li>${escapeHtml(r.reason)}${r.count ? `（${r.count}人）` : ""}</li>`,
          )
          .join("")}</ul>`
      : `<p class="wq-a-line">—</p>`;
    return `
      <div class="wq-a-item">
        <p class="wq-a-title">${index + 1}. ${escapeHtml(item.title || "")}</p>
        <p class="wq-a-line"><b>参考答案</b>____________________</p>
        <p class="wq-a-line"><b>典型错因</b></p>
        ${reasonHtml}
      </div>
    `;
  });
  return exportBlock(`
    <div class="wq-answers">
      <h2>答案与解析</h2>
      ${parts.join("")}
    </div>
  `);
}

function buildWrongSheetHtml(plan: WrongSheetPlan): string {
  const questionBlocks = plan.pages
    .map((page, pageIdx) =>
      page
        .map((item, i) =>
          renderQuestionBlock(item, pageIdx * 100 + i),
        )
        .join(""),
    )
    .join("");
  const answerHtml = plan.answerPage ? renderAnswerPage(plan.answerPage.items) : "";
  return `
    <div class="wq-sheet" data-export-sheet>
      ${renderCover(plan)}
      ${questionBlocks}
      ${answerHtml}
    </div>
  `;
}

function mountExportRoot(innerHtml: string) {
  const el = document.createElement("div");
  el.style.position = "fixed";
  el.style.left = "-10000px";
  el.style.top = "0";
  el.style.width = `${SHEET_WIDTH_PX}px`;
  el.style.background = "#fff";
  el.innerHTML = `<style>${sheetStyles()}</style>${innerHtml}`;
  document.body.appendChild(el);
  return el;
}

async function waitForImages(root: HTMLElement) {
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
        }),
    ),
  );
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
    pdf.line(
      layout.marginX,
      footerY - 4,
      layout.pageWidth - layout.marginX,
      footerY - 4,
    );
    pdf.setFont("helvetica", "normal");
    pdf.setFontSize(8);
    pdf.setTextColor(130, 135, 145);
    pdf.text(docTitle, layout.marginX, footerY);
    pdf.text(`${i} / ${total}`, layout.pageWidth - layout.marginX, footerY, {
      align: "right",
    });
  }
}

function appendTallCanvasToPdf(
  pdf: jsPDF,
  canvas: HTMLCanvasElement,
  pageBreakBefore: boolean,
  layout: PdfLayout,
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
    pdf.addImage(
      imgData,
      "JPEG",
      layout.marginX,
      layout.marginTop + position,
      imgWidth,
      imgHeight,
    );
    heightLeft -= layout.contentHeight;
    position -= layout.contentHeight;
  }
}

async function captureBlockCanvas(block: HTMLElement) {
  return html2canvas(block, {
    scale: CANVAS_SCALE,
    useCORS: false,
    logging: false,
    backgroundColor: "#ffffff",
  });
}

async function renderElementToPdfBlob(
  element: HTMLElement,
  docTitle: string,
): Promise<Blob> {
  const pdf = new jsPDF("p", "mm", "a4");
  const layout = getPdfLayout(pdf);
  const sheet = element.querySelector<HTMLElement>("[data-export-sheet]") || element;
  const blocks = Array.from(sheet.querySelectorAll<HTMLElement>("[data-export-block]"));
  await waitForImages(sheet);

  let y = 0;
  let hasPage = false;
  for (const block of blocks) {
    const canvas = await captureBlockCanvas(block);
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
  return pdf.output("blob");
}

export function wrongSheetFileName(meta: WrongSheetMeta): string {
  const date = meta.date || new Date().toLocaleDateString("zh-CN").replace(/\//g, "-");
  const subject = meta.subject || "错题";
  return `${subject}_错题巩固卷_${date}.pdf`;
}

export type ExportWrongQuestionSheetParams = BuildWrongSheetPlanParams;

/**
 * 生成错题巩固卷 PDF（返回 Blob，供下载/浏览器打印/一体机）。
 * 空选择会抛 WRONG_SHEET_EMPTY_SELECTION。
 */
export async function buildWrongSheetPdfBlob(
  params: ExportWrongQuestionSheetParams,
): Promise<{ blob: Blob; plan: WrongSheetPlan; fileName: string }> {
  const plan = buildWrongSheetPlan(params);
  const el = mountExportRoot(buildWrongSheetHtml(plan));
  try {
    const blob = await renderElementToPdfBlob(el, plan.meta.title || "Wrong Sheet");
    return { blob, plan, fileName: wrongSheetFileName(plan.meta) };
  } finally {
    el.parentNode?.removeChild(el);
  }
}

/** 生成并下载错题巩固卷 PDF */
export async function exportWrongQuestionSheetPdf(
  params: ExportWrongQuestionSheetParams,
): Promise<{ fileName: string; plan: WrongSheetPlan }> {
  const { blob, plan, fileName } = await buildWrongSheetPdfBlob(params);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return { fileName, plan };
}

/** 生成并在新标签页打开 PDF（浏览器打印对话框） */
export async function printWrongQuestionSheet(
  params: ExportWrongQuestionSheetParams,
): Promise<void> {
  const { blob } = await buildWrongSheetPdfBlob(params);
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  if (!win) {
    URL.revokeObjectURL(url);
    throw new Error("浏览器拦截了弹窗，请允许本站弹窗后重试");
  }
}
