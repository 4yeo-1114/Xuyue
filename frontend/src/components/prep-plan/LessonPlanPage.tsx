import { Fragment, useEffect, useMemo, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import { useAuth } from "@/hooks/useAuth";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import {
  aiGenerateLessonPlanFull,
  aiGenerateLessonPlanOutline,
  createLessonPlan,
  deleteLessonPlan as deleteLessonPlanApi,
  listLessonPlans,
  listLessonPlanTemplates,
  listResourceFiles,
  listResourceFolders,
  sendLessonPlanEmail as sendLessonPlanEmailApi,
  getAllUsers,
  type AiGenerateOutlineResult,
  type LessonPlanApiRecord,
  type LessonPlanTemplate,
  type ResourceFile,
  type ResourceFolder,
  updateLessonPlan as updateLessonPlanApi,
} from "@/services/api";
import { PREP_LESSON_CONTEXT_KEY } from "./TextbookCatalogPage";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { PdfPreviewDialog } from "@/components/shared/PdfPreviewDialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  ChevronsUpDown,
  ClipboardList,
  Clock3,
  Download,
  Eye,
  FilePlus2,
  FileText,
  Folder,
  Link2,
  Loader2,
  Mail,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  User,
} from "lucide-react";

interface Props {
  selectedSubject: string;
  selectedGrade?: string;
  selectedClass: string;
  selectedClassName?: string;
  onNavChange: (id: string) => void;
}

interface LessonPlanForm {
  title: string;
  schoolYear: string;
  term: string;
  lessonSequence: string;
  teachingContent: string;
  teachingObjectives: string;
  keyPoints: string;
  difficultPoints: string;
  teachingPreparation: string;
  teachingProcess: string;
  collectivePreparationAdvice: string;
  blackboardDesign: string;
  teachingReflection: string;
  deputyAuthor: string;
}

interface LessonPlanMeta {
  mainAuthor: string;
  completedAt: string;
  updatedAt: string;
}

interface LessonPlanRecord {
  id: string;
  subject: string;
  form: LessonPlanForm;
  meta: LessonPlanMeta;
  createdAt?: string;
}

interface LessonPlanBucket {
  plans: LessonPlanRecord[];
  selectedPlanId?: string;
}

const STORAGE_PREFIX = "lesson-plan-editor";
const LESSON_PLAN_PREFS_PREFIX = "lesson-plan-prefs";
const LESSON_PLAN_ALL_SUBJECT = "全部";
const LESSON_PLAN_SUBJECT_OPTIONS = ["语文", "数学", "英语", "科学"] as const;
const LESSON_PLAN_OVERVIEW_SUBJECT_OPTIONS = [
  LESSON_PLAN_ALL_SUBJECT,
  ...LESSON_PLAN_SUBJECT_OPTIONS,
] as const;
const LESSON_PLAN_TERM_OPTIONS = ["上学期", "下学期"] as const;
const LESSON_PLAN_YEAR_OPTIONS = Array.from(
  { length: 100 },
  (_, idx) => `${2000 + idx}年`,
);
const AUTOSAVE_DELAY = 900;

const EMPTY_FORM: LessonPlanForm = {
  title: "",
  schoolYear: "",
  term: "",
  lessonSequence: "",
  teachingContent: "",
  teachingObjectives: "",
  keyPoints: "",
  difficultPoints: "",
  teachingPreparation: "",
  teachingProcess: "",
  collectivePreparationAdvice: "",
  blackboardDesign: "",
  teachingReflection: "",
  deputyAuthor: "",
};

const SECTION_CONFIG: Array<{
  key: keyof LessonPlanForm;
  labelKey: string;
  placeholderKey: string;
  rows?: number;
}> = [
  {
    key: "title",
    labelKey: "prepPlan.lesson.field.title",
    placeholderKey: "prepPlan.lesson.field.titlePlaceholder",
  },
  {
    key: "teachingContent",
    labelKey: "prepPlan.lesson.field.teachingContent",
    placeholderKey: "prepPlan.lesson.field.teachingContentPlaceholder",
    rows: 4,
  },
  {
    key: "teachingObjectives",
    labelKey: "prepPlan.lesson.field.teachingObjectives",
    placeholderKey: "prepPlan.lesson.field.teachingObjectivesPlaceholder",
    rows: 5,
  },
  {
    key: "teachingPreparation",
    labelKey: "prepPlan.lesson.field.teachingPreparation",
    placeholderKey: "prepPlan.lesson.field.teachingPreparationPlaceholder",
    rows: 4,
  },
  {
    key: "teachingProcess",
    labelKey: "prepPlan.lesson.field.teachingProcess",
    placeholderKey: "prepPlan.lesson.field.teachingProcessPlaceholder",
    rows: 14,
  },
  {
    key: "collectivePreparationAdvice",
    labelKey: "prepPlan.lesson.field.collectiveAdvice",
    placeholderKey: "prepPlan.lesson.field.collectiveAdvicePlaceholder",
    rows: 14,
  },
  {
    key: "blackboardDesign",
    labelKey: "prepPlan.lesson.field.blackboardDesign",
    placeholderKey: "prepPlan.lesson.field.blackboardDesignPlaceholder",
    rows: 5,
  },
  {
    key: "teachingReflection",
    labelKey: "prepPlan.lesson.field.teachingReflection",
    placeholderKey: "prepPlan.lesson.field.teachingReflectionPlaceholder",
    rows: 5,
  },
];

const AI_MARKERS: Array<{ marker: string; key: keyof LessonPlanForm }> = [
  { marker: "【课题】", key: "title" },
  { marker: "【教学内容】", key: "teachingContent" },
  { marker: "【教学目标】", key: "teachingObjectives" },
  { marker: "【教学重点】", key: "keyPoints" },
  { marker: "【教学难点】", key: "difficultPoints" },
  { marker: "【教学准备】", key: "teachingPreparation" },
  { marker: "【教学过程】", key: "teachingProcess" },
  { marker: "【集体备课建议】", key: "collectivePreparationAdvice" },
  { marker: "【板书设计】", key: "blackboardDesign" },
  { marker: "【教学反思】", key: "teachingReflection" },
];

function formatDateTime(
  value: string | undefined,
  t: (key: string) => string,
  locale: string,
) {
  if (!value) return t("prepPlan.lesson.notSaved");
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(locale === "en" ? "en-US" : "zh-CN", {
    hour12: false,
  });
}

function formatHeaderDate(value: string | undefined, locale: string) {
  const source = value || new Date().toISOString();
  const d = new Date(source);
  if (Number.isNaN(d.getTime())) return source;
  if (locale === "en") {
    return d.toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

function buildLessonPlanFileBaseName(
  title: string | undefined,
  t: (key: string) => string,
) {
  return (title || t("prepPlan.lesson.unnamed")).replace(/[\\/:*?"<>|]/g, "_");
}

interface LessonPlanDocxBlock {
  heading?: string;
  text: string;
}

interface LessonPlanDocxSection {
  label: string;
  blocks: LessonPlanDocxBlock[];
}

interface LessonPlanDocxPayload {
  fileNameBase: string;
  headerLine: string;
  mainAuthor: string;
  dateLine: string;
  title: string;
  sections: LessonPlanDocxSection[];
  footerLine: string;
}

// 生成 Word(.docx) 教案：正文统一宋体小四(12pt)，标题三号加粗居中，用表格呈现各栏目。
async function renderLessonPlanDocxBlob(payload: LessonPlanDocxPayload) {
  const {
    AlignmentType,
    BorderStyle,
    Document,
    Packer,
    Paragraph,
    Table,
    TableCell,
    TableRow,
    TabStopType,
    TextRun,
    VerticalAlign,
    WidthType,
  } = await import("docx");

  const BODY_SIZE = 24; // 小四 = 12pt = 24 半磅
  const TITLE_SIZE = 32; // 三号 = 16pt
  const bodyFont = {
    ascii: "Times New Roman",
    eastAsia: "宋体",
    hAnsi: "Times New Roman",
  };
  const border = { style: BorderStyle.SINGLE, size: 4, color: "000000" };

  const paragraphsForBlocks = (blocks: LessonPlanDocxBlock[]) => {
    const paras: Paragraph[] = [];
    blocks.forEach((block, bi) => {
      if (bi > 0) {
        paras.push(new Paragraph({ children: [], spacing: { after: 40 } }));
      }
      if (block.heading) {
        paras.push(
          new Paragraph({
            children: [
              new TextRun({
                text: block.heading,
                font: bodyFont,
                size: BODY_SIZE,
                bold: true,
              }),
            ],
            spacing: { after: 20 },
          }),
        );
      }
      const lines = (block.text || "").split("\n");
      for (const line of lines) {
        paras.push(
          new Paragraph({
            children: [new TextRun({ text: line, font: bodyFont, size: BODY_SIZE })],
          }),
        );
      }
    });
    return paras;
  };

  const tableRows = payload.sections.map(
    (section) =>
      new TableRow({
        children: [
          new TableCell({
            children: [
              new Paragraph({
                children: [
                  new TextRun({
                    text: section.label,
                    font: bodyFont,
                    size: BODY_SIZE,
                    bold: true,
                  }),
                ],
              }),
            ],
            width: { size: 1400, type: WidthType.DXA },
            verticalAlign: VerticalAlign.TOP,
            margins: { top: 60, bottom: 60, left: 100, right: 100 },
          }),
          new TableCell({
            children: paragraphsForBlocks(section.blocks),
            verticalAlign: VerticalAlign.TOP,
            margins: { top: 60, bottom: 60, left: 100, right: 100 },
          }),
        ],
      }),
  );

  const doc = new Document({
    creator: "叙阅",
    sections: [
      {
        properties: {
          page: {
            size: { width: 11906, height: 16838 },
            margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 },
          },
        },
        children: [
          new Paragraph({
            children: [
              new TextRun({ text: payload.headerLine, font: bodyFont, size: BODY_SIZE }),
              new TextRun({ text: "\t", font: bodyFont, size: BODY_SIZE }),
              new TextRun({ text: payload.mainAuthor, font: bodyFont, size: BODY_SIZE }),
              new TextRun({ text: "\t", font: bodyFont, size: BODY_SIZE }),
              new TextRun({ text: payload.dateLine, font: bodyFont, size: BODY_SIZE }),
            ],
            tabStops: [
              { type: TabStopType.CENTER, position: 4513 },
              { type: TabStopType.RIGHT, position: 9026 },
            ],
            spacing: { after: 120 },
          }),
          new Paragraph({
            children: [
              new TextRun({
                text: payload.title,
                font: bodyFont,
                size: TITLE_SIZE,
                bold: true,
              }),
            ],
            alignment: AlignmentType.CENTER,
            spacing: { after: 120 },
          }),
          new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            borders: {
              top: border,
              bottom: border,
              left: border,
              right: border,
              insideHorizontal: border,
              insideVertical: border,
            },
            rows: tableRows,
          }),
          new Paragraph({
            children: [
              new TextRun({
                text: payload.footerLine,
                font: bodyFont,
                size: BODY_SIZE,
                bold: true,
              }),
            ],
            alignment: AlignmentType.CENTER,
            spacing: { before: 120 },
          }),
        ],
      },
    ],
  });

  const blob = await Packer.toBlob(doc);
  const filename = `${payload.fileNameBase}_${new Date().toLocaleDateString("zh-CN").replace(/\//g, "-")}.docx`;
  return { blob, filename };
}

function buildStorageKey(
  userId: string,
  selectedSubject: string,
  selectedClass: string,
) {
  return `${STORAGE_PREFIX}::${userId || "anonymous"}::${selectedSubject || "未选学科"}::${selectedClass || "未选班级"}`;
}

function buildLessonPlanPrefsKey(userId: string) {
  return `${LESSON_PLAN_PREFS_PREFIX}::${userId || "anonymous"}`;
}

function readLessonPlanPrefs(userId: string): {
  schoolYear?: string;
  term?: string;
} {
  try {
    const raw = localStorage.getItem(buildLessonPlanPrefsKey(userId));
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return {
      schoolYear:
        typeof parsed?.schoolYear === "string" ? parsed.schoolYear : undefined,
      term: typeof parsed?.term === "string" ? parsed.term : undefined,
    };
  } catch {
    return {};
  }
}

function writeLessonPlanPrefs(
  userId: string,
  prefs: { schoolYear?: string; term?: string },
) {
  try {
    localStorage.setItem(
      buildLessonPlanPrefsKey(userId),
      JSON.stringify(prefs),
    );
  } catch {
    //
  }
}

// —— 教案 PDF（Word 版式）：离屏 DOM 固定宽度 + 逐块截图 + 块级分页 + 四周留白 ——
const LP_SHEET_WIDTH = 794;
const LP_CANVAS_SCALE = 1.5;
const LP_JPEG_QUALITY = 0.88;
// PDF 页边距（mm）：四周留白，贴近 Word 版式
const LP_MARGIN_X = 18;
const LP_MARGIN_TOP = 22;
const LP_MARGIN_BOTTOM = 18;
const LP_FONT =
  '"SimSun", "宋体", "Songti SC", "STSong", "Times New Roman", serif';

function lpEscape(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function lpPreserveSpaces(value: string): string {
  return value.replace(/ {2,}/g, (sp) => "&nbsp;".repeat(sp.length));
}

function lpCellInner(blocks: LessonPlanDocxBlock[]): string {
  return blocks
    .map((block) => {
      const heading = block.heading
        ? `<div class="lp-heading">${lpEscape(block.heading)}</div>`
        : "";
      const lines = (block.text || "")
        .split("\n")
        .map((ln) => `<div>${lpEscape(ln) || "&nbsp;"}</div>`)
        .join("");
      return `<div class="lp-subblock">${heading}${lines}</div>`;
    })
    .join("");
}

function lpPdfStyles(): string {
  return `
    .lp-sheet { box-sizing: border-box; width: ${LP_SHEET_WIDTH}px; background: #fff; color: #000; font-family: ${LP_FONT}; font-size: 12pt; line-height: 1.8; }
    .lp-sheet * { box-sizing: border-box; }
    .lp-header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
    .lp-title { text-align: center; font-size: 16pt; font-weight: 700; margin: 20px 0; }
    .lp-row { display: grid; grid-template-columns: 150px 1fr; }
    .lp-label { padding: 8px 12px; font-weight: 600; border-left: 1px solid #000; border-right: 1px solid #000; border-bottom: 1px solid #000; }
    .lp-cell { padding: 8px 12px; white-space: pre-wrap; border-right: 1px solid #000; border-bottom: 1px solid #000; }
    .lp-row.lp-first .lp-label { border-top: 1px solid #000; }
    .lp-row.lp-first .lp-cell { border-top: 1px solid #000; }
    .lp-heading { font-weight: 600; margin-bottom: 4px; }
    .lp-subblock + .lp-subblock { margin-top: 12px; }
    .lp-footer { text-align: center; font-weight: 600; margin-top: 24px; }
  `;
}

function mountLessonPlanPdfElement(payload: LessonPlanDocxPayload): HTMLElement {
  const rows = payload.sections
    .map(
      (section, i) => `
      <div class="lp-row${i === 0 ? " lp-first" : ""}" data-export-block>
        <div class="lp-label">${lpEscape(section.label)}</div>
        <div class="lp-cell">${lpCellInner(section.blocks)}</div>
      </div>`,
    )
    .join("");

  const html = `
    <div class="lp-sheet" data-export-sheet>
      <div class="lp-head-block" data-export-block>
        <div class="lp-header">
          <span>${lpEscape(payload.headerLine)}</span>
          <span>${lpEscape(payload.mainAuthor)}</span>
          <span>${lpEscape(payload.dateLine)}</span>
        </div>
        <div class="lp-title">${lpEscape(payload.title)}</div>
      </div>
      ${rows}
      <div class="lp-foot-block" data-export-block>
        <div class="lp-footer">${lpPreserveSpaces(lpEscape(payload.footerLine))}</div>
      </div>
    </div>`;

  const el = document.createElement("div");
  el.style.position = "fixed";
  el.style.left = "-10000px";
  el.style.top = "0";
  el.style.width = `${LP_SHEET_WIDTH}px`;
  el.style.background = "#fff";
  el.innerHTML = `<style>${lpPdfStyles()}</style>${html}`;
  document.body.appendChild(el);
  return el;
}

async function renderLessonPlanPdfBlob(payload: LessonPlanDocxPayload) {
  const html2canvas = (await import("html2canvas")).default;
  const { jsPDF } = await import("jspdf");

  const el = mountLessonPlanPdfElement(payload);
  try {
    const pdf = new jsPDF("p", "mm", "a4");
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const contentWidth = pageWidth - LP_MARGIN_X * 2;
    const contentHeight = pageHeight - LP_MARGIN_TOP - LP_MARGIN_BOTTOM;

    const blocks = Array.from(
      el.querySelectorAll<HTMLElement>("[data-export-block]"),
    );

    let y = 0;
    let hasPage = false;

    for (const block of blocks) {
      const canvas = await html2canvas(block, {
        scale: LP_CANVAS_SCALE,
        useCORS: false,
        logging: false,
        backgroundColor: "#ffffff",
      });
      const imgData = canvas.toDataURL("image/jpeg", LP_JPEG_QUALITY);
      const blockH = (canvas.height * contentWidth) / canvas.width;

      // 单块超高（极长的教学过程等）：按比例切片兜底，避免整块溢出页面。
      if (blockH >= contentHeight - 0.5) {
        let topPx = 0;
        let first = true;
        while (topPx < canvas.height) {
          if (!first || hasPage) pdf.addPage();
          first = false;
          const remainPx = canvas.height - topPx;
          const slicePx = Math.min(
            remainPx,
            Math.floor((contentHeight / blockH) * canvas.height),
          );
          const slice = document.createElement("canvas");
          slice.width = canvas.width;
          slice.height = Math.max(1, slicePx);
          const ctx = slice.getContext("2d")!;
          ctx.drawImage(
            canvas,
            0,
            topPx,
            canvas.width,
            slicePx,
            0,
            0,
            canvas.width,
            slicePx,
          );
          const sliceH = (slicePx * contentWidth) / canvas.width;
          pdf.addImage(
            slice.toDataURL("image/jpeg", LP_JPEG_QUALITY),
            "JPEG",
            LP_MARGIN_X,
            LP_MARGIN_TOP,
            contentWidth,
            sliceH,
          );
          topPx += slicePx;
          hasPage = true;
        }
        y = 0;
        continue;
      }

      // 当前页放不下整块 → 整块换到下一页，避免把表格行/文字拦腰切断。
      if (hasPage && y + blockH > contentHeight) {
        pdf.addPage();
        y = 0;
      }

      pdf.addImage(
        imgData,
        "JPEG",
        LP_MARGIN_X,
        LP_MARGIN_TOP + y,
        contentWidth,
        blockH,
      );
      y += blockH;
      hasPage = true;
    }

    const blob = pdf.output("blob");
    const filename = `${payload.fileNameBase}_${new Date().toLocaleDateString("zh-CN").replace(/\//g, "-")}.pdf`;
    return { blob, filename, pdf };
  } finally {
    if (el.parentNode) el.parentNode.removeChild(el);
  }
}

function buildPlanSummary(plan: LessonPlanRecord, t: (key: string) => string) {
  const title = plan.form.title?.trim() || t("prepPlan.lesson.unnamed");
  const summary =
    plan.form.teachingContent?.trim() ||
    plan.form.teachingObjectives?.trim() ||
    plan.form.teachingProcess?.trim() ||
    t("prepPlan.lesson.noContent");
  return {
    title,
    summary,
  };
}

function parseAiLessonPlan(raw: string): Partial<LessonPlanForm> {
  const normalized = String(raw || "")
    .replace(/\r/g, "")
    .trim();
  const parsed: Partial<LessonPlanForm> = {};

  AI_MARKERS.forEach((current, idx) => {
    const start = normalized.indexOf(current.marker);
    if (start < 0) return;
    const contentStart = start + current.marker.length;
    let contentEnd = normalized.length;

    for (let j = idx + 1; j < AI_MARKERS.length; j += 1) {
      const nextIndex = normalized.indexOf(AI_MARKERS[j].marker, contentStart);
      if (nextIndex >= 0) {
        contentEnd = nextIndex;
        break;
      }
    }

    const value = normalized
      .slice(contentStart, contentEnd)
      .trim()
      .replace(/^[:：]/, "")
      .trim();

    if (value) parsed[current.key] = value;
  });

  return parsed;
}

/** 目录上下文（#48b：由 TextbookCatalogPage 写入 sessionStorage） */
interface CatalogLessonContext {
  subject: string;
  grade: string;
  edition: string;
  nodeId: number | string;
  nodeName: string;
  level: string;
}

/** 把模板 structure（环节数组）格式化为教学过程文本 */
function structureToTeachingProcess(structure: Record<string, unknown>): string {
  if (!Array.isArray(structure) || structure.length === 0) return "";
  const numbered = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
  return structure
    .map((item, idx) => {
      const step = typeof item?.step === "string" ? item.step : "";
      const prompt = typeof item?.prompt === "string" ? item.prompt : "";
      const label = numbered[idx] ? `${numbered[idx]}、${step}` : step;
      return label && prompt ? `${label}\n${prompt}` : label || prompt;
    })
    .filter(Boolean)
    .join("\n\n");
}

/** 把 AI 大纲对象序列化为确认后传给 full 接口的 outline 文本 */
function formatOutlineForPrompt(outline: AiGenerateOutlineResult): string {
  const parts: string[] = [];
  if (outline?.title) parts.push(`课题：${outline.title}`);
  if (outline?.objectives) parts.push(`教学目标：\n${outline.objectives}`);
  if (outline?.key_points) parts.push(`教学重点：${outline.key_points}`);
  if (outline?.difficult_points) parts.push(`教学难点：${outline.difficult_points}`);
  if (Array.isArray(outline?.process_summary) && outline.process_summary.length > 0) {
    const steps = outline.process_summary
      .map((s, i) => `${i + 1}. ${s?.step || ""}：${s?.point || ""}`)
      .join("\n");
    parts.push(`教学过程概要：\n${steps}`);
  }
  return parts.join("\n\n");
}

function mapApiRecordToPlan(record: LessonPlanApiRecord): LessonPlanRecord {
  return {
    id: record.id,
    subject: record.subject || "",
    form: {
      title: record.title || "",
      schoolYear: record.school_year || "",
      term: record.term || "",
      lessonSequence: record.lesson_sequence || "",
      teachingContent: record.teaching_content || "",
      teachingObjectives: record.teaching_objectives || "",
      keyPoints: record.key_points || "",
      difficultPoints: record.difficult_points || "",
      teachingPreparation: record.teaching_preparation || "",
      teachingProcess: record.teaching_process || "",
      collectivePreparationAdvice: record.collective_preparation_advice || "",
      blackboardDesign: record.blackboard_design || "",
      teachingReflection: record.teaching_reflection || "",
      deputyAuthor: record.deputy_author || "",
    },
    meta: {
      mainAuthor: record.main_author || "",
      completedAt: record.completed_at || "",
      updatedAt: record.updated_at || "",
    },
    createdAt: record.created_at || "",
  };
}

function normalizeCompletedAt(value?: string | null): string | null {
  const raw = (value ?? "").trim();
  return raw || null;
}

function buildLessonPlanPayload(
  form: LessonPlanForm,
  meta: LessonPlanMeta,
  currentAuthor: string,
  classId: string,
  grade: string,
  subject: string,
  completedAt?: string | null,
) {
  return {
    class_id: classId,
    school_year: form.schoolYear,
    term: form.term,
    grade,
    subject,
    title: form.title,
    lesson_sequence: form.lessonSequence,
    teaching_content: form.teachingContent,
    teaching_objectives: form.teachingObjectives,
    key_points: form.keyPoints,
    difficult_points: form.difficultPoints,
    teaching_preparation: form.teachingPreparation,
    teaching_process: form.teachingProcess,
    collective_preparation_advice: form.collectivePreparationAdvice,
    blackboard_design: form.blackboardDesign,
    teaching_reflection: form.teachingReflection,
    main_author: meta.mainAuthor || currentAuthor,
    deputy_author: form.deputyAuthor,
    completed_at: normalizeCompletedAt(completedAt ?? meta.completedAt),
  };
}

function readLegacyBucket(
  storageKey: string,
  currentAuthor: string,
): LessonPlanBucket {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return { plans: [], selectedPlanId: "" };
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed?.plans)) {
      return {
        plans: parsed.plans
          .map((item: any) => ({
            id: String(
              item?.id ||
                `legacy_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
            ),
            subject: "",
            form: {
              ...EMPTY_FORM,
              ...(item?.form && typeof item.form === "object" ? item.form : {}),
            },
            meta: {
              mainAuthor: item?.meta?.mainAuthor || currentAuthor,
              completedAt: item?.meta?.completedAt || "",
              updatedAt: item?.meta?.updatedAt || "",
            },
          }))
          .filter((item: LessonPlanRecord) => !!item.id),
        selectedPlanId:
          typeof parsed?.selectedPlanId === "string"
            ? parsed.selectedPlanId
            : "",
      };
    }
    if (parsed?.form && typeof parsed.form === "object") {
      const migratedPlan: LessonPlanRecord = {
        id: `legacy_${Date.now()}`,
        subject: "",
        form: {
          ...EMPTY_FORM,
          ...parsed.form,
        },
        meta: {
          mainAuthor: parsed?.meta?.mainAuthor || currentAuthor,
          completedAt: parsed?.meta?.completedAt || "",
          updatedAt: parsed?.meta?.updatedAt || "",
        },
      };
      return { plans: [migratedPlan], selectedPlanId: migratedPlan.id };
    }
  } catch {
    return { plans: [], selectedPlanId: "" };
  }
  return { plans: [], selectedPlanId: "" };
}

export function LessonPlanPage(props: Props) {
  const { selectedSubject, selectedGrade, selectedClass, selectedClassName } =
    props;
  const { user } = useAuth();
  const { t, locale } = useLocale();

  // 「发送给他人」仅管理员可用：后端 /auth/users/all 白名单只有 系统管理员/子系统管理员 两种角色，
  // 校级管理者/年级组长即使前端放行也会 403，故与后端保持一致的两种角色判定（同 smart-exam 页面模式）。
  const isGlobalAdmin = useMemo(() => {
    if (!user || !user.roles) return false;
    return user.roles.some((r) => ["系统管理员", "子系统管理员"].includes(r));
  }, [user]);
  const previewRef = useRef<HTMLDivElement>(null);
  const hasLoadedRef = useRef(false);
  const saveTimerRef = useRef<number | null>(null);
  const suppressAutosaveRef = useRef(false);
  // 防抖定时器 pending 时的最新待落盘载荷：切换/离开/卸载前据此 flush，避免 <900ms 内编辑丢失
  const pendingAutosaveRef = useRef<{
    planId: string;
    payload: ReturnType<typeof buildLessonPlanPayload>;
  } | null>(null);

  const isSupportedSubject = (subject: string) =>
    LESSON_PLAN_SUBJECT_OPTIONS.some((item) => item === subject);

  // 父级传入的学科不在教案支持列表时，保留用户显式选择值，禁止静默回退为「语文」误标新教案。
  // 仅当父级未传具体学科（空值/「全部」）时才回退到第一个支持学科作为展示默认。
  const initialSubject =
    LESSON_PLAN_SUBJECT_OPTIONS.find((item) => item === selectedSubject) ||
    (selectedSubject && selectedSubject !== LESSON_PLAN_ALL_SUBJECT
      ? selectedSubject
      : LESSON_PLAN_SUBJECT_OPTIONS[0]);
  const currentAuthor =
    user?.display_name?.trim() ||
    user?.email ||
    t("prepPlan.lesson.notLoggedIn");
  const gradeDisplayName =
    selectedGrade || t("prepPlan.lesson.notSelectedGrade");
  const classDisplayName =
    selectedClassName || selectedClass || t("prepPlan.lesson.notSelectedGrade");

  const displaySubject = useCallback(
    (subject: string) =>
      subject === LESSON_PLAN_ALL_SUBJECT
        ? t("prepPlan.calendar.subjectAll")
        : translateSubjectName(locale, subject),
    [locale, t],
  );

  const displayTerm = useCallback(
    (term: string) => {
      if (term === "上学期") return t("prepPlan.lesson.term.first");
      if (term === "下学期") return t("prepPlan.lesson.term.second");
      return term;
    },
    [t],
  );
  const lessonPlanPrefs = useMemo(
    () => readLessonPlanPrefs(user?.id || "anonymous"),
    [user?.id],
  );
  // 总览过滤器必须是合法选项（「全部」+支持学科）：父级学科不支持教案时回退到「全部」，
  // 避免把非法值带入过滤下拉。
  const [overviewSubject, setOverviewSubject] = useState<string>(() =>
    LESSON_PLAN_OVERVIEW_SUBJECT_OPTIONS.some((item) => item === initialSubject)
      ? initialSubject
      : LESSON_PLAN_ALL_SUBJECT,
  );
  const [editorSubject, setEditorSubject] = useState<string>(initialSubject);
  const legacyStorageKey = useMemo(
    () =>
      overviewSubject === LESSON_PLAN_ALL_SUBJECT
        ? ""
        : buildStorageKey(
            user?.id || "anonymous",
            overviewSubject,
            selectedClass,
          ),
    [overviewSubject, selectedClass, user?.id],
  );

  const [view, setView] = useState<"overview" | "editor">("overview");
  const [plans, setPlans] = useState<LessonPlanRecord[]>([]);
  const [activePlanId, setActivePlanId] = useState<string>("");
  const [form, setForm] = useState<LessonPlanForm>(EMPTY_FORM);
  const [meta, setMeta] = useState<LessonPlanMeta>({
    mainAuthor: currentAuthor,
    completedAt: "",
    updatedAt: "",
  });
  const [draftSavedAt, setDraftSavedAt] = useState("");
  const [plansLoading, setPlansLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deletingPlanId, setDeletingPlanId] = useState("");
  // 删除前 AlertDialog 确认的待删教案（null=未弹出）
  const [deleteTarget, setDeleteTarget] = useState<LessonPlanRecord | null>(
    null,
  );

  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailTargetType, setEmailTargetType] = useState<"self" | "others">(
    "self",
  );
  const [emailUserComboboxOpen, setEmailUserComboboxOpen] = useState(false);
  const [targetEmailInput, setTargetEmailInput] = useState("");
  // /auth/users/all 返回最小字段（不含 personal_email），故用户选择器只展示姓名，不承载收件人邮箱
  const [selectedUserObj, setSelectedUserObj] = useState<{
    id: string;
    email: string;
    display_name?: string | null;
  } | null>(null);
  const [usersList, setUsersList] = useState<
    {
      id: string;
      email: string;
      display_name?: string | null;
    }[]
  >([]);
  const [loadingUsers, setLoadingUsers] = useState(false);

  // PDF 弹窗预览（复用 renderLessonPlanPdfBlob，预览关闭时 revoke blob URL）
  const [previewBlobUrl, setPreviewBlobUrl] = useState("");
  const [previewFilename, setPreviewFilename] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);

  // #48b：教材目录上下文（挂载时读 sessionStorage 预填，读后即清）
  const [catalogContext, setCatalogContext] =
    useState<CatalogLessonContext | null>(null);
  const catalogPrefillRef = useRef(false);
  const [loadReady, setLoadReady] = useState(false);
  // 教案模板导航
  const [templates, setTemplates] = useState<LessonPlanTemplate[]>([]);
  const [templateSheetOpen, setTemplateSheetOpen] = useState(false);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  // AI 生成（分步确认式：大纲 → 确认 → 完整教案落库）
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiFilling, setAiFilling] = useState(false);
  const [outline, setOutline] = useState<AiGenerateOutlineResult | null>(null);
  const [outlineDialogOpen, setOutlineDialogOpen] = useState(false);
  // 资源插入（多级下钻：年级 → 学科 → 知识点 → 文件，复用资源库的全局共享目录）
  const [resourceDialogOpen, setResourceDialogOpen] = useState(false);
  const [resourcePath, setResourcePath] = useState<string[]>([]);
  const [resourceFolders, setResourceFolders] = useState<ResourceFolder[]>([]);
  const [resourceFolderLoading, setResourceFolderLoading] = useState(false);
  const [resourceFiles, setResourceFiles] = useState<ResourceFile[]>([]);
  const [resourceFilesLoading, setResourceFilesLoading] = useState(false);

  const fetchUsersList = async () => {
    setLoadingUsers(true);
    try {
      const users = await getAllUsers();
      setUsersList(users);
    } catch (err) {
      toast.error(t("prepPlan.lesson.toast.usersFailed"));
    } finally {
      setLoadingUsers(false);
    }
  };

  useEffect(() => {
    if (
      emailModalOpen &&
      emailTargetType === "others" &&
      usersList.length === 0
    ) {
      fetchUsersList();
    }
  }, [emailModalOpen, emailTargetType]);

  const hydrateActivePlan = (target?: LessonPlanRecord | null) => {
    suppressAutosaveRef.current = true;
    if (target) {
      setActivePlanId(target.id);
      setForm({
        ...EMPTY_FORM,
        ...target.form,
      });
      setMeta({
        mainAuthor: target.meta.mainAuthor || currentAuthor,
        completedAt: target.meta.completedAt || "",
        updatedAt: target.meta.updatedAt || "",
      });
      setDraftSavedAt(target.meta.updatedAt || "");
      return;
    }
    setActivePlanId("");
    setForm({
      ...EMPTY_FORM,
      schoolYear: lessonPlanPrefs.schoolYear || "",
      term: lessonPlanPrefs.term || "",
    });
    setMeta({
      mainAuthor: currentAuthor,
      completedAt: "",
      updatedAt: "",
    });
    setDraftSavedAt("");
  };

  useEffect(() => {
    if (!selectedClass) return;
    let cancelled = false;

    const loadPlans = async () => {
      hasLoadedRef.current = false;
      setPlansLoading(true);
      try {
        const rows = await listLessonPlans({
          class_id: selectedClass,
          subject:
            overviewSubject === LESSON_PLAN_ALL_SUBJECT
              ? undefined
              : overviewSubject,
        });
        let nextPlans = rows.map(mapApiRecordToPlan);

        if (nextPlans.length === 0 && legacyStorageKey) {
          const legacyBucket = readLegacyBucket(
            legacyStorageKey,
            currentAuthor,
          );
          if (legacyBucket.plans.length > 0) {
            const migrated: LessonPlanRecord[] = [];
            for (const legacyPlan of legacyBucket.plans) {
              const created = await createLessonPlan(
                buildLessonPlanPayload(
                  legacyPlan.form,
                  legacyPlan.meta,
                  currentAuthor,
                  selectedClass,
                  gradeDisplayName,
                  overviewSubject,
                  legacyPlan.meta.completedAt || null,
                ),
              );
              migrated.push(mapApiRecordToPlan(created));
            }
            nextPlans = migrated;
            localStorage.removeItem(legacyStorageKey);
            toast.success(t("prepPlan.lesson.toast.migrated"), {
              description: t("prepPlan.lesson.toast.migratedDesc"),
            });
          }
        }

        if (cancelled) return;
        setPlans(nextPlans);
        // 学科/班级过滤变化会重载并可能切换 activePlanId，先落盘 pending 防抖内容
        void flushPendingAutosave();
        const keepActive = nextPlans.find((item) => item.id === activePlanId);
        hydrateActivePlan(keepActive || nextPlans[0]);
        if (view !== "editor") {
          setView("overview");
        }
      } catch (error: any) {
        if (cancelled) return;
        setPlans([]);
        // 清空并可能切换 activePlanId，先落盘 pending 防抖内容
        void flushPendingAutosave();
        hydrateActivePlan(null);
        toast.error(t("prepPlan.lesson.toast.loadFailed"), {
          description:
            error?.message || t("prepPlan.lesson.toast.loadFailedDesc"),
        });
      } finally {
        if (!cancelled) {
          setPlansLoading(false);
          hasLoadedRef.current = true;
          setLoadReady(true);
        }
      }
    };

    loadPlans();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    currentAuthor,
    overviewSubject,
    gradeDisplayName,
    legacyStorageKey,
    selectedClass,
  ]);

  useEffect(() => {
    if (!hasLoadedRef.current) return;
    if (!activePlanId) return;
    if (suppressAutosaveRef.current) {
      suppressAutosaveRef.current = false;
      return;
    }
    const updatedAt = new Date().toISOString();
    const nextMeta = {
      ...meta,
      mainAuthor: meta.mainAuthor || currentAuthor,
      updatedAt,
    };
    const payload = buildLessonPlanPayload(
      form,
      nextMeta,
      currentAuthor,
      selectedClass,
      gradeDisplayName,
      editorSubject,
    );
    setPlans((prev) =>
      prev.map((item) =>
        item.id === activePlanId
          ? {
              ...item,
              subject: editorSubject,
              form,
              meta: nextMeta,
            }
          : item,
      ),
    );
    setDraftSavedAt(updatedAt);
    setMeta(nextMeta);

    // 记录最新待落盘载荷：切走/卸载时 flushPendingAutosave 依据它立即写入后端
    pendingAutosaveRef.current = { planId: activePlanId, payload };

    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(async () => {
      try {
        const updated = await updateLessonPlanApi(activePlanId, payload);
        const mapped = mapApiRecordToPlan(updated);
        setPlans((prev) =>
          prev.map((item) => (item.id === mapped.id ? mapped : item)),
        );
        if (activePlanId === mapped.id) {
          setMeta(mapped.meta);
          setDraftSavedAt(mapped.meta.updatedAt || updatedAt);
        }
      } catch (error: any) {
        toast.error(t("prepPlan.lesson.toast.autosaveFailed"), {
          description:
            error?.message || t("prepPlan.lesson.toast.autosaveFailedDesc"),
        });
      } finally {
        // 定时器已触发（无论成败）即清空 pending，避免切走时对已落盘内容重复写入
        pendingAutosaveRef.current = null;
      }
    }, AUTOSAVE_DELAY);

    return () => {
      if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    };
  }, [
    activePlanId,
    currentAuthor,
    editorSubject,
    form,
    gradeDisplayName,
    selectedClass,
  ]);

  // 主动落盘：切走/离开前立即写入 pending 防抖内容，防止 effect cleanup 清 timer 后 <900ms 编辑丢失
  const flushPendingAutosave = useCallback(async () => {
    const pending = pendingAutosaveRef.current;
    if (!pending) return;
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    pendingAutosaveRef.current = null;
    try {
      const updated = await updateLessonPlanApi(
        pending.planId,
        pending.payload,
      );
      const mapped = mapApiRecordToPlan(updated);
      setPlans((prev) =>
        prev.map((item) => (item.id === mapped.id ? mapped : item)),
      );
    } catch {
      // 静默：本地 plans/meta 已在 effect 同步更新，后续「完成保存」或下次自动保存会重试
    }
  }, []);

  // 组件卸载（离开备课域）时兜底落盘，防止 pending 防抖写入随卸载被丢弃
  useEffect(() => {
    return () => {
      const pending = pendingAutosaveRef.current;
      if (!pending) return;
      void updateLessonPlanApi(pending.planId, pending.payload).catch(() => {});
    };
  }, []);

  // #48b：挂载时读取教材目录上下文，读后立即清空（只生效一次）
  useEffect(() => {
    let parsed: CatalogLessonContext | null = null;
    try {
      const raw = sessionStorage.getItem(PREP_LESSON_CONTEXT_KEY);
      if (raw) {
        const value = JSON.parse(raw) as CatalogLessonContext;
        if (value && value.subject && value.nodeName) parsed = value;
      }
    } catch {
      // 解析失败静默
    } finally {
      try {
        sessionStorage.removeItem(PREP_LESSON_CONTEXT_KEY);
      } catch {
        // ignore
      }
    }
    if (parsed) setCatalogContext(parsed);
  }, []);

  // #48b：加载教案模板列表（失败静默，不阻塞编辑）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setTemplatesLoading(true);
      try {
        const rows = await listLessonPlanTemplates();
        if (!cancelled) setTemplates(rows || []);
      } catch {
        // 模板加载失败静默
      } finally {
        if (!cancelled) setTemplatesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // #48b：目录上下文到达后预填表单（仅一次）；无活动教案则自动新建并进入编辑器
  useEffect(() => {
    if (!loadReady || !catalogContext || catalogPrefillRef.current) return;
    catalogPrefillRef.current = true;
    const ctx = catalogContext;
    if (LESSON_PLAN_SUBJECT_OPTIONS.some((s) => s === ctx.subject)) {
      setEditorSubject(ctx.subject);
    }
    setForm((prev) => {
      const next = { ...prev };
      if (!next.title?.trim()) next.title = ctx.nodeName;
      if (!next.teachingContent?.trim()) {
        const lines = [
          ctx.grade ? `年级：${ctx.grade}` : "",
          ctx.edition ? `教材版本：${ctx.edition}` : "",
          ctx.level === "unit" ? `单元：${ctx.nodeName}` : "",
        ].filter(Boolean);
        if (lines.length > 0) next.teachingContent = lines.join("\n");
      }
      return next;
    });
    if (activePlanId) {
      setView("editor");
      return;
    }
    if (!selectedClass) return;
    void (async () => {
      try {
        const created = await createLessonPlan({
          class_id: selectedClass,
          grade: ctx.grade || gradeDisplayName,
          subject: ctx.subject,
          title: ctx.nodeName,
          main_author: currentAuthor,
        });
        const newPlan = mapApiRecordToPlan(created);
        setPlans((prev) => [newPlan, ...prev]);
        setActivePlanId(newPlan.id);
        setForm(newPlan.form);
        setMeta(newPlan.meta);
        setDraftSavedAt(newPlan.meta.updatedAt || "");
        setView("editor");
        toast.success(t("prepPlan.lesson.toast.createdFromCatalog"), {
          description: t("prepPlan.lesson.toast.createdFromCatalogDesc"),
        });
      } catch {
        // 自动新建失败不阻塞：仍进入编辑器，字段已预填
        setView("editor");
      }
    })();
  }, [
    loadReady,
    catalogContext,
    activePlanId,
    selectedClass,
    gradeDisplayName,
    currentAuthor,
    t,
  ]);

  const updateField = (key: keyof LessonPlanForm, value: string) => {
    if (key === "schoolYear" || key === "term") {
      const nextPrefs = {
        schoolYear: key === "schoolYear" ? value : form.schoolYear,
        term: key === "term" ? value : form.term,
      };
      writeLessonPlanPrefs(user?.id || "anonymous", nextPrefs);
    }
    setForm((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const handleOpenPlan = (planId: string) => {
    // 切换 activePlanId 前先落盘当前教案的 pending 防抖内容，避免被 effect cleanup 丢弃
    void flushPendingAutosave();
    const target = plans.find((item) => item.id === planId);
    if (!target) return;
    setEditorSubject(target.subject || initialSubject);
    hydrateActivePlan(target);
    setView("editor");
  };

  const handleCreatePlan = async () => {
    // 新建教案会切换 activePlanId，先落盘当前教案的 pending 防抖内容
    void flushPendingAutosave();
    // 学科来源：总览过滤器已选择具体学科时用该学科；否则沿用父级导航学科。
    // 父级学科不在教案支持列表（语文/数学/英语/科学）时，禁止静默回退为「语文」误标新教案，
    // 改为明确提示用户先在学科下拉中选择支持范围内的学科。
    const createSubject =
      overviewSubject !== LESSON_PLAN_ALL_SUBJECT
        ? overviewSubject
        : isSupportedSubject(selectedSubject)
          ? selectedSubject
          : null;

    if (!createSubject) {
      toast.error(t("prepPlan.lesson.toast.selectSubjectFirst"), {
        description: t("prepPlan.lesson.toast.selectSubjectFirstDesc"),
      });
      return;
    }
    try {
      setCreating(true);
      const created = await createLessonPlan({
        class_id: selectedClass,
        school_year: lessonPlanPrefs.schoolYear || "",
        term: lessonPlanPrefs.term || "",
        grade: gradeDisplayName,
        subject: createSubject,
        main_author: currentAuthor,
      });
      const newPlan = mapApiRecordToPlan(created);
      const nextPlans = [newPlan, ...plans];
      setPlans(nextPlans);
      setEditorSubject(newPlan.subject || createSubject);
      hydrateActivePlan(newPlan);
      setView("editor");
      toast.success(t("prepPlan.lesson.toast.created"));
    } catch (error: any) {
      toast.error(t("prepPlan.lesson.toast.createFailed"), {
        description:
          error?.message || t("prepPlan.lesson.toast.loadFailedDesc"),
      });
    } finally {
      setCreating(false);
    }
  };

  const handleDeletePlan = async (planId: string) => {
    const target = plans.find((item) => item.id === planId);
    if (!target) return;
    // 待删教案若有 pending 防抖写入，删除后该写入无意义，直接清空避免卸载时重复更新已删记录
    if (pendingAutosaveRef.current?.planId === planId) {
      pendingAutosaveRef.current = null;
    }
    try {
      setDeletingPlanId(planId);
      await deleteLessonPlanApi(planId);
      const nextPlans = plans.filter((item) => item.id !== planId);
      setPlans(nextPlans);
      if (activePlanId === planId) {
        hydrateActivePlan(nextPlans[0]);
      }
      toast.success(
        t("prepPlan.lesson.toast.deleted", {
          title: buildPlanSummary(target, t).title,
        }),
      );
    } catch (error: any) {
      toast.error(t("prepPlan.lesson.toast.deleteFailed"), {
        description:
          error?.message || t("prepPlan.lesson.toast.loadFailedDesc"),
      });
    } finally {
      setDeletingPlanId("");
    }
  };

  const handleCompleteSave = async () => {
    if (!activePlanId) return;
    const timestamp = new Date().toISOString();
    const nextMeta = {
      ...meta,
      mainAuthor: currentAuthor,
      completedAt: timestamp,
      updatedAt: timestamp,
    };

    try {
      setSaving(true);
      if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
      // 「完成保存」自己做了完整落盘，清掉 pending 避免后续 flush/卸载重复写入旧载荷
      pendingAutosaveRef.current = null;
      const updated = await updateLessonPlanApi(
        activePlanId,
        buildLessonPlanPayload(
          form,
          nextMeta,
          currentAuthor,
          selectedClass,
          gradeDisplayName,
          editorSubject,
          timestamp,
        ),
      );
      const mapped = mapApiRecordToPlan(updated);
      setPlans((prev) =>
        prev.map((item) => (item.id === mapped.id ? mapped : item)),
      );
      setMeta(mapped.meta);
      setDraftSavedAt(mapped.meta.updatedAt || timestamp);
      toast.success(t("prepPlan.lesson.toast.saved"), {
        description: t("prepPlan.lesson.toast.savedDesc"),
      });
    } catch (error: any) {
      toast.error(t("prepPlan.lesson.toast.saveFailed"), {
        description:
          error?.message || t("prepPlan.lesson.toast.autosaveFailedDesc"),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleGeneratePlan = async () => {
    const lessonTitle = form.title?.trim();
    if (!lessonTitle) {
      toast.error(t("prepPlan.lesson.toast.topicRequired"), {
        description: t("prepPlan.lesson.toast.topicRequiredDesc"),
      });
      return;
    }
    setAiGenerating(true);
    try {
      const outlineResult = await aiGenerateLessonPlanOutline({
        subject: editorSubject,
        grade: catalogContext?.grade || gradeDisplayName,
        edition: catalogContext?.edition || undefined,
        unit_name:
          catalogContext?.level === "unit" ? catalogContext.nodeName : undefined,
        lesson_title: lessonTitle,
        lesson_sequence: form.lessonSequence?.trim() || undefined,
      });
      setOutline(outlineResult);
      setOutlineDialogOpen(true);
    } catch (error: any) {
      toast.error(t("prepPlan.lesson.toast.aiOutlineFailed"), {
        description:
          error?.message || t("prepPlan.lesson.toast.aiServiceUnavailable"),
      });
    } finally {
      setAiGenerating(false);
    }
  };

  const handleRegenerateOutline = async () => {
    setOutlineDialogOpen(false);
    await handleGeneratePlan();
  };

  const handleConfirmOutline = async () => {
    if (!outline) return;
    const lessonTitle = form.title?.trim();
    if (!lessonTitle) return;
    setAiFilling(true);
    try {
      const record = await aiGenerateLessonPlanFull({
        class_id: selectedClass,
        outline: formatOutlineForPrompt(outline),
        subject: editorSubject,
        grade: catalogContext?.grade || gradeDisplayName,
        edition: catalogContext?.edition || undefined,
        unit_name:
          catalogContext?.level === "unit" ? catalogContext.nodeName : undefined,
        lesson_title: lessonTitle,
        lesson_sequence: form.lessonSequence?.trim() || undefined,
      });
      const mapped = mapApiRecordToPlan(record);
      setPlans((prev) => [mapped, ...prev.filter((p) => p.id !== mapped.id)]);
      setActivePlanId(mapped.id);
      setForm(mapped.form);
      setMeta(mapped.meta);
      setDraftSavedAt(mapped.meta.updatedAt || "");
      setOutlineDialogOpen(false);
      toast.success(t("prepPlan.lesson.toast.aiGeneratedAndSaved"), {
        description: t("prepPlan.lesson.toast.aiGeneratedAndSavedDesc"),
      });
    } catch (error: any) {
      toast.error(t("prepPlan.lesson.toast.aiFullFailed"), {
        description:
          error?.message || t("prepPlan.lesson.toast.aiServiceUnavailable"),
      });
    } finally {
      setAiFilling(false);
    }
  };

  const handleApplyTemplate = (tpl: LessonPlanTemplate) => {
    const process = structureToTeachingProcess(tpl.structure);
    if (!process) {
      toast.info(t("prepPlan.lesson.templateEmpty"));
      return;
    }
    setForm((prev) => ({
      ...prev,
      teachingProcess: process,
    }));
    setTemplateSheetOpen(false);
    toast.success(t("prepPlan.lesson.templateApplied"), {
      description: t("prepPlan.lesson.templateAppliedDesc", { name: tpl.name }),
    });
  };

  const activeResourcePath = resourcePath.join("/");

  const openResourceDialog = () => {
    setResourceDialogOpen(true);
    setResourcePath([]);
  };

  const enterResourceFolder = (name: string) => {
    setResourcePath((prev) => [...prev, name]);
  };

  // 打开弹窗 / 下钻路径变化时，加载当前层的子文件夹与文件
  useEffect(() => {
    if (!resourceDialogOpen) return;
    const path = resourcePath.join("/");
    let cancelled = false;

    setResourceFolderLoading(true);
    setResourceFilesLoading(true);
    void (async () => {
      try {
        const folders = await listResourceFolders(path || undefined);
        if (!cancelled) setResourceFolders(folders || []);
      } catch {
        if (!cancelled)
          toast.error(t("prepPlan.lesson.resource.loadFoldersFailed"));
      } finally {
        if (!cancelled) setResourceFolderLoading(false);
      }
    })();
    // 根目录只有年级文件夹，进入层级后才拉取文件
    if (path) {
      void (async () => {
        try {
          const files = await listResourceFiles(path);
          if (!cancelled) setResourceFiles(files || []);
        } catch {
          if (!cancelled)
            toast.error(t("prepPlan.lesson.resource.loadFilesFailed"));
        } finally {
          if (!cancelled) setResourceFilesLoading(false);
        }
      })();
    } else {
      setResourceFiles([]);
      setResourceFilesLoading(false);
    }

    return () => {
      cancelled = true;
    };
  }, [resourceDialogOpen, resourcePath, t]);

  const insertResource = (file: ResourceFile) => {
    const link = file.url ? `[${file.name}](${file.url})` : file.name;
    const line = `- 资源：${link}（${activeResourcePath}）`;
    setForm((prev) => ({
      ...prev,
      teachingContent: prev.teachingContent?.trim()
        ? `${prev.teachingContent}\n${line}`
        : line,
    }));
    setResourceDialogOpen(false);
    toast.success(t("prepPlan.lesson.resource.inserted"));
  };

  // 教案内容统一封装为 payload，供 Word 导出与 PDF 预览共用（版式一致）。
  const buildLessonPlanPayload = (): LessonPlanDocxPayload => {
    const noContent = t("prepPlan.lesson.noContent");
    const headerLine = t("prepPlan.lesson.previewHeader", {
      year: form.schoolYear || "____",
      term: form.term ? displayTerm(form.term) : "____",
      subject: translateSubjectName(locale, editorSubject),
    });
    const mainAuthor = t("prepPlan.lesson.previewMainAuthor", {
      name: meta.mainAuthor || currentAuthor,
    });
    const dateLine = formatHeaderDate(
      meta.completedAt || draftSavedAt,
      locale,
    );
    const sections: LessonPlanDocxSection[] = [
      {
        label: t("prepPlan.lesson.previewLabel.content"),
        blocks: [{ text: form.teachingContent || noContent }],
      },
      {
        label: t("prepPlan.lesson.previewLabel.objectives"),
        blocks: [{ text: form.teachingObjectives || noContent }],
      },
      {
        label: t("prepPlan.lesson.previewLabel.keyDifficult"),
        blocks: [
          {
            heading: t("prepPlan.lesson.previewLabel.key"),
            text: form.keyPoints || noContent,
          },
          {
            heading: t("prepPlan.lesson.previewLabel.difficult"),
            text: form.difficultPoints || noContent,
          },
        ],
      },
      {
        label: t("prepPlan.lesson.previewLabel.preparation"),
        blocks: [{ text: form.teachingPreparation || noContent }],
      },
      {
        label: t("prepPlan.lesson.previewLabel.process"),
        blocks: [
          { text: form.teachingProcess || noContent },
          ...(form.collectivePreparationAdvice?.trim()
            ? [
                {
                  heading: t("prepPlan.lesson.previewLabel.collective"),
                  text: form.collectivePreparationAdvice,
                },
              ]
            : []),
        ],
      },
      {
        label: t("prepPlan.lesson.previewLabel.blackboard"),
        blocks: [{ text: form.blackboardDesign || noContent }],
      },
      {
        label: t("prepPlan.lesson.previewLabel.reflection"),
        blocks: [{ text: form.teachingReflection || noContent }],
      },
    ];
    const footerLine = [
      t("prepPlan.lesson.previewFooter.sequence", {
        seq: form.lessonSequence || "    ",
      }),
      t("prepPlan.lesson.previewFooter.deputy", {
        name: form.deputyAuthor || "",
      }),
    ].join("        ");

    return {
      fileNameBase: buildLessonPlanFileBaseName(form.title, t),
      headerLine,
      mainAuthor,
      dateLine,
      title: form.title || t("prepPlan.lesson.unnamed"),
      sections,
      footerLine,
    };
  };

  const handleDownloadPdf = async () => {
    try {
      const { blob, filename } = await renderLessonPlanDocxBlob(
        buildLessonPlanPayload(),
      );

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(t("prepPlan.lesson.toast.pdfDownloaded"));
    } catch (error: any) {
      toast.error(t("prepPlan.lesson.toast.downloadFailed"), {
        description:
          error?.message || t("prepPlan.lesson.toast.downloadFailedDesc"),
      });
    }
  };

  const handlePreviewPdf = async () => {
    if (!previewRef.current) return;

    try {
      const { blob, filename } = await renderLessonPlanPdfBlob(
        buildLessonPlanPayload(),
      );
      const url = URL.createObjectURL(blob);
      setPreviewBlobUrl(url);
      setPreviewFilename(filename);
      setPreviewOpen(true);
    } catch (error: any) {
      toast.error(t("prepPlan.lesson.toast.downloadFailed"), {
        description:
          error?.message || t("prepPlan.lesson.toast.downloadFailedDesc"),
      });
    }
  };

  const handlePreviewClose = () => {
    setPreviewOpen(false);
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl("");
      setPreviewFilename("");
    }
  };

  const handleSendEmailClick = () => {
    if (!activePlanId) {
      toast.error(t("prepPlan.lesson.toast.openFirst"));
      return;
    }
    setTargetEmailInput("");
    setSelectedUserObj(null);
    setEmailTargetType("self");
    setEmailModalOpen(true);
  };

  const executeSendEmail = async () => {
    if (!activePlanId) return;
    if (!previewRef.current) return;
    if (emailTargetType === "others" && !isGlobalAdmin) {
      toast.error(t("prepPlan.lesson.email.adminOnly"));
      return;
    }

    try {
      setSendingEmail(true);
      const { blob, filename } = await renderLessonPlanPdfBlob(
        buildLessonPlanPayload(),
      );
      const buffer = await blob.arrayBuffer();
      let binary = "";
      const bytes = new Uint8Array(buffer);
      for (let i = 0; i < bytes.length; i += 1) {
        binary += String.fromCharCode(bytes[i]);
      }
      const pdfBase64 = btoa(binary);
      const targetEmail =
        emailTargetType === "others" ? targetEmailInput : undefined;
      const res = await sendLessonPlanEmailApi(activePlanId, {
        pdf_base64: pdfBase64,
        filename,
        to_email: targetEmail,
      });
      toast.success(t("prepPlan.lesson.toast.emailSent"), {
        description: res.to_email
          ? t("prepPlan.lesson.toast.emailSentTo", { email: res.to_email })
          : t("prepPlan.lesson.toast.emailSentSelf"),
      });
      setEmailModalOpen(false);
      setSelectedUserObj(null);
    } catch (error: any) {
      toast.error(t("prepPlan.lesson.toast.emailFailed"), {
        description:
          error?.message || t("prepPlan.lesson.toast.emailFailedDesc"),
      });
    } finally {
      setSendingEmail(false);
    }
  };

  const activePlanSummary = useMemo(
    () => plans.find((item) => item.id === activePlanId),
    [activePlanId, plans],
  );

  const activePlanSummaryData = activePlanSummary
    ? buildPlanSummary(activePlanSummary, t)
    : null;

  if (!selectedClass) {
    return (
      <Card className="border-dashed">
        <CardContent className="flex min-h-[360px] flex-col items-center justify-center gap-4 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <FileText className="h-8 w-8" />
          </div>
          <div className="space-y-1">
            <div className="text-lg font-semibold text-foreground">
              {t("common.selectClassFirst")}
            </div>
            <div className="max-w-lg text-sm text-muted-foreground">
              {t("common.selectClassHint")}
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (view === "overview") {
    return (
      <div className="space-y-6">
        <Card className="border-primary/15 bg-gradient-to-r from-primary/[0.06] via-background to-background">
          <CardHeader className="pb-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <FileText className="h-5 w-5" />
                  </div>
                  <div>
                    <CardTitle className="text-xl">
                      {t("prepPlan.lesson.overviewTitle")}
                    </CardTitle>
                    <CardDescription>
                      {t("prepPlan.lesson.overviewDesc")}
                    </CardDescription>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <Badge variant="secondary">
                    {t("prepPlan.lesson.currentGrade", {
                      value: gradeDisplayName,
                    })}
                  </Badge>
                  <Badge variant="secondary">
                    {t("prepPlan.lesson.currentSubject", {
                      value: displaySubject(overviewSubject),
                    })}
                  </Badge>
                  <Badge variant="secondary">
                    {t("prepPlan.lesson.currentClass", {
                      value: classDisplayName,
                    })}
                  </Badge>
                  <Badge variant="secondary">
                    {t("prepPlan.lesson.mainAuthor", { value: currentAuthor })}
                  </Badge>
                  <Badge variant="secondary">
                    {t("prepPlan.lesson.planCount", { count: plans.length })}
                  </Badge>
                </div>
              </div>

              <Button
                className="gap-2"
                onClick={handleCreatePlan}
                disabled={creating || plansLoading}
              >
                {creating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <FilePlus2 className="h-4 w-4" />
                )}
                {t("prepPlan.lesson.createPlan")}
              </Button>
            </div>
            <div className="max-w-[220px]">
              <div className="mb-2 text-xs font-medium text-muted-foreground">
                {t("prepPlan.lesson.currentSubjectLabel")}
              </div>
              <Select
                value={overviewSubject}
                onValueChange={(value) => setOverviewSubject(value)}
              >
                <SelectTrigger className="h-9 bg-background">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LESSON_PLAN_OVERVIEW_SUBJECT_OPTIONS.map((subject) => (
                    <SelectItem key={subject} value={subject}>
                      {displaySubject(subject)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardHeader>
        </Card>

        {plansLoading ? (
          <Card className="border-dashed">
            <CardContent className="flex min-h-[240px] items-center justify-center gap-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("prepPlan.lesson.loading")}
            </CardContent>
          </Card>
        ) : plans.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="flex min-h-[360px] flex-col items-center justify-center gap-4 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <FileText className="h-8 w-8" />
              </div>
              <div className="space-y-1">
                <div className="text-lg font-semibold text-foreground">
                  {t("prepPlan.lesson.emptyTitle")}
                </div>
                <div className="max-w-lg text-sm text-muted-foreground">
                  {t("prepPlan.lesson.emptyDesc")}
                </div>
              </div>
              <Button
                className="gap-2"
                onClick={handleCreatePlan}
                disabled={creating}
              >
                {creating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <FilePlus2 className="h-4 w-4" />
                )}
                {t("prepPlan.lesson.createNow")}
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
            {plans.map((plan) => {
              const { title, summary } = buildPlanSummary(plan, t);
              const isCompleted = !!plan.meta.completedAt;
              const isCurrent = plan.id === activePlanId;
              return (
                <Card
                  key={plan.id}
                  className={`overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-md ${isCurrent ? "border-primary/40 shadow-sm" : ""}`}
                >
                  <CardHeader className="space-y-3 pb-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge
                            variant={isCompleted ? "default" : "secondary"}
                          >
                            {isCompleted
                              ? t("prepPlan.lesson.statusCompleted")
                              : t("prepPlan.lesson.statusDraft")}
                          </Badge>
                          {isCurrent && (
                            <Badge variant="outline">
                              {t("prepPlan.lesson.recentEdit")}
                            </Badge>
                          )}
                          <Badge variant="outline">
                            {plan.subject
                              ? translateSubjectName(locale, plan.subject)
                              : t("prepPlan.lesson.uncategorizedSubject")}
                          </Badge>
                        </div>
                        <CardTitle className="text-lg leading-snug">
                          {title}
                        </CardTitle>
                        <CardDescription className="text-xs">
                          {t("prepPlan.lesson.recentUpdate", {
                            author: plan.meta.mainAuthor || currentAuthor,
                            time: formatDateTime(
                              plan.meta.updatedAt,
                              t,
                              locale,
                            ),
                          })}
                        </CardDescription>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="shrink-0 text-muted-foreground hover:text-destructive"
                        onClick={() => setDeleteTarget(plan)}
                        title={t("prepPlan.lesson.deletePlan")}
                        disabled={deletingPlanId === plan.id}
                      >
                        {deletingPlanId === plan.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="rounded-xl border bg-muted/15 p-4">
                      <div className="line-clamp-5 whitespace-pre-wrap text-sm leading-6 text-foreground/85">
                        {summary}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground">
                      <div className="rounded-lg bg-muted/30 p-3">
                        <div className="font-medium text-foreground">
                          {t("prepPlan.lesson.completedAt")}
                        </div>
                        <div className="mt-1">
                          {formatDateTime(plan.meta.completedAt, t, locale)}
                        </div>
                      </div>
                      <div className="rounded-lg bg-muted/30 p-3">
                        <div className="font-medium text-foreground">
                          {t("prepPlan.lesson.scope")}
                        </div>
                        <div className="mt-1">
                          {gradeDisplayName} /{" "}
                          {plan.subject
                            ? translateSubjectName(locale, plan.subject)
                            : t("prepPlan.lesson.uncategorizedSubject")}{" "}
                          / {classDisplayName}
                        </div>
                      </div>
                    </div>
                    <Button
                      className="w-full gap-2"
                      onClick={() => handleOpenPlan(plan.id)}
                    >
                      <FileText className="h-4 w-4" />
                      {t("prepPlan.lesson.openEditor")}
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="border-primary/15 bg-gradient-to-r from-primary/[0.06] via-background to-background">
        <CardHeader className="pb-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2"
                  onClick={() => setView("overview")}
                >
                  <ArrowLeft className="h-4 w-4" />
                  {t("prepPlan.lesson.backToOverview")}
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <FileText className="h-5 w-5" />
                </div>
                <div>
                  <CardTitle className="text-xl">
                    {t("prepPlan.lesson.editorTitle")}
                  </CardTitle>
                  <CardDescription>
                    {t("prepPlan.lesson.editorDesc")}
                  </CardDescription>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                <Badge variant="secondary">
                  {t("prepPlan.lesson.currentGrade", {
                    value: gradeDisplayName,
                  })}
                </Badge>
                <Badge variant="secondary">
                  {t("prepPlan.lesson.currentSubject", {
                    value: translateSubjectName(locale, editorSubject),
                  })}
                </Badge>
                <Badge variant="secondary">
                  {t("prepPlan.lesson.currentClass", {
                    value: classDisplayName,
                  })}
                </Badge>
                <Badge variant="secondary">
                  {t("prepPlan.lesson.mainAuthor", { value: currentAuthor })}
                </Badge>
                <Badge variant="secondary">
                  {t("prepPlan.lesson.currentPlan", {
                    title:
                      activePlanSummaryData?.title ||
                      t("prepPlan.lesson.notSelected"),
                  })}
                </Badge>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Select
                value={editorSubject}
                onValueChange={(value) => setEditorSubject(value)}
              >
                <SelectTrigger className="h-10 w-[130px] bg-background">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LESSON_PLAN_SUBJECT_OPTIONS.map((subject) => (
                    <SelectItem key={subject} value={subject}>
                      {translateSubjectName(locale, subject)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                className="gap-2"
                onClick={() => setTemplateSheetOpen(true)}
                disabled={templatesLoading}
                title={t("prepPlan.lesson.templateTitle")}
              >
                <ClipboardList className="h-4 w-4" />
                {t("prepPlan.lesson.templateButton")}
              </Button>
              <Button
                variant="outline"
                className="gap-2"
                onClick={handleGeneratePlan}
                disabled={aiGenerating || aiFilling}
              >
                {aiGenerating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                {aiGenerating
                  ? t("prepPlan.lesson.aiOutlining")
                  : t("prepPlan.lesson.aiGenerate")}
              </Button>
              <Button
                variant="outline"
                className="gap-2"
                onClick={handlePreviewPdf}
              >
                <Eye className="h-4 w-4" />
                {t("prepPlan.lesson.previewPdf")}
              </Button>
              <Button
                variant="outline"
                className="gap-2"
                onClick={handleDownloadPdf}
              >
                <Download className="h-4 w-4" />
                {t("prepPlan.lesson.downloadPlan")}
              </Button>
              <Button
                variant="outline"
                className="gap-2"
                onClick={handleSendEmailClick}
                disabled={sendingEmail}
              >
                {sendingEmail ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Mail className="h-4 w-4" />
                )}
                {t("prepPlan.lesson.sendEmail")}
              </Button>
              <Button
                className="gap-2"
                onClick={handleCompleteSave}
                disabled={saving}
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                {t("prepPlan.lesson.completeSave")}
              </Button>
            </div>
          </div>

          <div className="mt-2 flex flex-col gap-2 text-xs text-muted-foreground md:flex-row md:items-center md:justify-between">
            <div className="flex flex-wrap items-center gap-4">
              <span className="inline-flex items-center gap-1">
                <User className="h-3.5 w-3.5" />
                {t("prepPlan.lesson.mainAuthor", {
                  value: meta.mainAuthor || currentAuthor,
                })}
              </span>
              <span className="inline-flex items-center gap-1">
                <Clock3 className="h-3.5 w-3.5" />
                {t("prepPlan.lesson.completedAtLabel", {
                  time: formatDateTime(meta.completedAt, t, locale),
                })}
              </span>
            </div>
            <span>
              {t("prepPlan.lesson.autoSync", {
                time: formatDateTime(draftSavedAt, t, locale),
              })}
            </span>
          </div>

          {(aiGenerating || aiFilling) && (
            <div className="mt-2 rounded-lg border border-primary/20 bg-background/80 p-3">
              <div className="flex items-center gap-2 text-xs">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span className="font-medium text-foreground">
                  {aiGenerating
                    ? t("prepPlan.lesson.aiOutlining")
                    : t("prepPlan.lesson.aiGeneratingFull")}
                </span>
              </div>
            </div>
          )}
        </CardHeader>
      </Card>

      <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border/60 pb-4">
            <div className="flex items-center justify-between gap-3">
              <div className="space-y-1">
                <CardTitle className="text-lg">
                  {t("prepPlan.lesson.editArea")}
                </CardTitle>
                <CardDescription>
                  {t("prepPlan.lesson.editAreaDesc")}
                </CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={openResourceDialog}
              >
                <Link2 className="h-4 w-4" />
                {t("prepPlan.lesson.resource.insertButton")}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[calc(100vh-17rem)]">
              <div className="space-y-6 p-6">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">
                    {t("prepPlan.lesson.field.title")}
                  </label>
                  <Input
                    value={form.title}
                    onChange={(e) => updateField("title", e.target.value)}
                    placeholder={t("prepPlan.lesson.field.titlePlaceholder")}
                  />
                </div>

                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">
                      {t("prepPlan.lesson.field.year")}
                    </label>
                    <Select
                      value={form.schoolYear}
                      onValueChange={(value) =>
                        updateField("schoolYear", value)
                      }
                    >
                      <SelectTrigger className="h-10 bg-background">
                        <SelectValue
                          placeholder={t("prepPlan.lesson.field.selectYear")}
                        />
                      </SelectTrigger>
                      <SelectContent className="max-h-72">
                        {LESSON_PLAN_YEAR_OPTIONS.map((year) => (
                          <SelectItem key={year} value={year}>
                            {locale === "en" ? year.replace("年", "") : year}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">
                      {t("prepPlan.lesson.field.term")}
                    </label>
                    <Select
                      value={form.term}
                      onValueChange={(value) => updateField("term", value)}
                    >
                      <SelectTrigger className="h-10 bg-background">
                        <SelectValue
                          placeholder={t("prepPlan.lesson.field.selectTerm")}
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {LESSON_PLAN_TERM_OPTIONS.map((term) => (
                          <SelectItem key={term} value={term}>
                            {displayTerm(term)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">
                      {t("prepPlan.lesson.field.lessonSequence")}
                    </label>
                    <Input
                      value={form.lessonSequence}
                      onChange={(e) =>
                        updateField("lessonSequence", e.target.value)
                      }
                      placeholder={t(
                        "prepPlan.lesson.field.lessonSequencePlaceholder",
                      )}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">
                      {t("prepPlan.lesson.field.deputyAuthor")}
                    </label>
                    <Input
                      value={form.deputyAuthor}
                      onChange={(e) =>
                        updateField("deputyAuthor", e.target.value)
                      }
                      placeholder={t(
                        "prepPlan.lesson.field.deputyAuthorPlaceholder",
                      )}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">
                      {t("prepPlan.lesson.field.keyPoints")}
                    </label>
                    <Textarea
                      value={form.keyPoints}
                      onChange={(e) => updateField("keyPoints", e.target.value)}
                      placeholder={t(
                        "prepPlan.lesson.field.keyPointsPlaceholder",
                      )}
                      className="min-h-[140px]"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">
                      {t("prepPlan.lesson.field.difficultPoints")}
                    </label>
                    <Textarea
                      value={form.difficultPoints}
                      onChange={(e) =>
                        updateField("difficultPoints", e.target.value)
                      }
                      placeholder={t(
                        "prepPlan.lesson.field.difficultPointsPlaceholder",
                      )}
                      className="min-h-[140px]"
                    />
                  </div>
                </div>

                <Separator />

                {SECTION_CONFIG.filter(
                  (item) =>
                    item.key !== "title" &&
                    item.key !== "teachingProcess" &&
                    item.key !== "collectivePreparationAdvice",
                ).map((section) => (
                  <div key={section.key} className="space-y-2">
                    <label className="text-sm font-medium text-foreground">
                      {t(section.labelKey)}
                    </label>
                    <Textarea
                      value={form[section.key]}
                      onChange={(e) => updateField(section.key, e.target.value)}
                      placeholder={t(section.placeholderKey)}
                      className={
                        section.rows && section.rows >= 10
                          ? "min-h-[320px]"
                          : "min-h-[120px]"
                      }
                      rows={section.rows}
                    />
                  </div>
                ))}

                <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,7fr)_minmax(260px,3fr)]">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">
                      {t("prepPlan.lesson.field.teachingProcess")}
                    </label>
                    <Textarea
                      value={form.teachingProcess}
                      onChange={(e) =>
                        updateField("teachingProcess", e.target.value)
                      }
                      placeholder={t(
                        "prepPlan.lesson.field.teachingProcessPlaceholder",
                      )}
                      className="min-h-[320px]"
                      rows={14}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-foreground">
                      {t("prepPlan.lesson.field.collectiveAdvice")}
                    </label>
                    <Textarea
                      value={form.collectivePreparationAdvice}
                      onChange={(e) =>
                        updateField(
                          "collectivePreparationAdvice",
                          e.target.value,
                        )
                      }
                      placeholder={t(
                        "prepPlan.lesson.field.collectiveAdvicePlaceholder",
                      )}
                      className="min-h-[320px]"
                      rows={14}
                    />
                  </div>
                </div>
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border/60 pb-4">
            <CardTitle className="text-lg">
              {t("prepPlan.lesson.preview")}
            </CardTitle>
            <CardDescription>
              {t("prepPlan.lesson.previewDesc")}
            </CardDescription>
          </CardHeader>
          <CardContent className="bg-muted/20 p-4">
            <div className="flex justify-center px-2 pb-6">
                <div
                  ref={previewRef}
                  className="w-full max-w-[820px] bg-white px-8 pt-8 pb-6 text-[14px] leading-7 text-black shadow-[0_10px_30px_rgba(15,23,42,0.10)]"
                >
                  <div className="flex min-h-[32px] items-center justify-between gap-4 overflow-hidden text-[16px] font-semibold leading-8 tracking-[0.01em] whitespace-nowrap">
                    <span className="min-w-0 shrink truncate">
                      {t("prepPlan.lesson.previewHeader", {
                        year: form.schoolYear || "____",
                        term: form.term ? displayTerm(form.term) : "____",
                        subject: translateSubjectName(locale, editorSubject),
                      })}
                    </span>
                    <span className="shrink-0">
                      {t("prepPlan.lesson.previewMainAuthor", {
                        name: meta.mainAuthor || currentAuthor,
                      })}
                    </span>
                    <span className="shrink-0">
                      {formatHeaderDate(
                        meta.completedAt || draftSavedAt,
                        locale,
                      )}
                    </span>
                  </div>

                  <div className="mt-4 border border-black">
                    <div className="border-b border-black px-4 py-3 text-center text-[24px] font-bold tracking-wide">
                      {form.title || t("prepPlan.lesson.unnamed")}
                    </div>
                    <table className="w-full border-collapse text-[14px]">
                      <tbody>
                        <tr className="align-top">
                          <td className="w-28 border-r border-b border-black px-3 py-2 font-semibold">
                            {t("prepPlan.lesson.previewLabel.content")}
                          </td>
                          <td className="border-b border-black px-3 py-2 whitespace-pre-wrap">
                            {form.teachingContent ||
                              t("prepPlan.lesson.noContent")}
                          </td>
                        </tr>
                        <tr className="align-top">
                          <td className="w-28 border-r border-b border-black px-3 py-2 font-semibold">
                            {t("prepPlan.lesson.previewLabel.objectives")}
                          </td>
                          <td className="border-b border-black px-3 py-2 whitespace-pre-wrap">
                            {form.teachingObjectives ||
                              t("prepPlan.lesson.noContent")}
                          </td>
                        </tr>
                        <tr className="align-top">
                          <td className="w-28 border-r border-b border-black px-3 py-2 font-semibold">
                            {t("prepPlan.lesson.previewLabel.keyDifficult")}
                          </td>
                          <td className="border-b border-black px-3 py-2">
                            <div className="space-y-3">
                              <div>
                                <div className="font-semibold">
                                  {t("prepPlan.lesson.previewLabel.key")}
                                </div>
                                <div className="whitespace-pre-wrap">
                                  {form.keyPoints ||
                                    t("prepPlan.lesson.noContent")}
                                </div>
                              </div>
                              <div>
                                <div className="font-semibold">
                                  {t("prepPlan.lesson.previewLabel.difficult")}
                                </div>
                                <div className="whitespace-pre-wrap">
                                  {form.difficultPoints ||
                                    t("prepPlan.lesson.noContent")}
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                        <tr className="align-top">
                          <td className="w-28 border-r border-b border-black px-3 py-2 font-semibold">
                            {t("prepPlan.lesson.previewLabel.preparation")}
                          </td>
                          <td className="border-b border-black px-3 py-2 whitespace-pre-wrap">
                            {form.teachingPreparation ||
                              t("prepPlan.lesson.noContent")}
                          </td>
                        </tr>
                        <tr className="align-top">
                          <td className="w-28 border-r border-b border-black px-3 py-2 font-semibold">
                            {t("prepPlan.lesson.previewLabel.process")}
                          </td>
                          <td className="border-b border-black p-0">
                            <div className="grid min-h-[320px] grid-cols-[7fr_3fr]">
                              <div className="px-3 py-2 whitespace-pre-wrap">
                                {form.teachingProcess ||
                                  t("prepPlan.lesson.noContent")}
                              </div>
                              <div className="border-l border-black px-3 py-2">
                                <div className="mb-2 font-semibold">
                                  {t("prepPlan.lesson.previewLabel.collective")}
                                </div>
                                <div className="whitespace-pre-wrap">
                                  {form.collectivePreparationAdvice ||
                                    t("prepPlan.lesson.noContent")}
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                        <tr className="align-top">
                          <td className="w-28 border-r border-b border-black px-3 py-2 font-semibold">
                            {t("prepPlan.lesson.previewLabel.blackboard")}
                          </td>
                          <td className="border-b border-black px-3 py-2 whitespace-pre-wrap">
                            {form.blackboardDesign ||
                              t("prepPlan.lesson.noContent")}
                          </td>
                        </tr>
                        <tr className="align-top">
                          <td className="w-28 border-r border-black px-3 py-2 font-semibold">
                            {t("prepPlan.lesson.previewLabel.reflection")}
                          </td>
                          <td className="px-3 py-2 whitespace-pre-wrap">
                            {form.teachingReflection ||
                              t("prepPlan.lesson.noContent")}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div className="mt-4 flex items-center justify-center gap-12 text-[16px] font-semibold leading-7">
                    <span>
                      {t("prepPlan.lesson.previewFooter.sequence", {
                        seq: form.lessonSequence || "    ",
                      })}
                    </span>
                    <span>
                      {t("prepPlan.lesson.previewFooter.deputy", {
                        name: form.deputyAuthor || "",
                      })}
                    </span>
                  </div>
                </div>
              </div>
          </CardContent>
        </Card>
      </div>

      <Dialog open={emailModalOpen} onOpenChange={setEmailModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("prepPlan.lesson.email.title")}</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Tabs
              value={emailTargetType}
              onValueChange={(v) => setEmailTargetType(v as "self" | "others")}
              className="w-full"
            >
              <TabsList className="grid w-full grid-cols-2 mb-4">
                <TabsTrigger value="self">
                  {t("prepPlan.lesson.email.self")}
                </TabsTrigger>
                <TabsTrigger
                  value="others"
                  disabled={!isGlobalAdmin}
                  title={
                    !isGlobalAdmin
                      ? t("prepPlan.lesson.email.adminOnly")
                      : undefined
                  }
                >
                  {t("prepPlan.lesson.email.others")}
                </TabsTrigger>
              </TabsList>

              <TabsContent value="self" className="mt-0">
                <div className="text-sm text-muted-foreground p-4 bg-muted/30 rounded-md">
                  <p>{t("prepPlan.lesson.email.selfHint")}</p>
                </div>
              </TabsContent>

              <TabsContent value="others" className="mt-0 space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">
                    {t("prepPlan.lesson.email.searchUser")}
                  </label>
                  <Popover
                    open={emailUserComboboxOpen}
                    onOpenChange={setEmailUserComboboxOpen}
                  >
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        role="combobox"
                        aria-expanded={emailUserComboboxOpen}
                        className="w-full justify-between font-normal"
                        disabled={loadingUsers}
                      >
                        {selectedUserObj
                          ? `${selectedUserObj.display_name || selectedUserObj.email.split("@")[0]}`
                          : loadingUsers
                            ? t("prepPlan.lesson.email.loadingUsers")
                            : t("prepPlan.lesson.email.searchPlaceholder")}
                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[380px] p-0" align="start">
                      <Command>
                        <CommandInput
                          placeholder={t("prepPlan.lesson.email.searchInput")}
                        />
                        <CommandList>
                          <CommandEmpty>
                            {t("prepPlan.lesson.email.userNotFound")}
                          </CommandEmpty>
                          <CommandGroup>
                            {usersList.map((u) => (
                              <CommandItem
                                key={u.id}
                                value={u.display_name || u.email.split("@")[0]}
                                onSelect={() => {
                                  // 后端 /users/all 不含 personal_email，选择用户只作展示，不自动填收件人邮箱
                                  setSelectedUserObj(u);
                                  setEmailUserComboboxOpen(false);
                                }}
                              >
                                <Check
                                  className={cn(
                                    "mr-2 h-4 w-4",
                                    selectedUserObj?.id === u.id
                                      ? "opacity-100"
                                      : "opacity-0",
                                  )}
                                />
                                {u.display_name || u.email.split("@")[0]}
                              </CommandItem>
                            ))}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">
                    {t("prepPlan.lesson.email.emailAddress")}
                  </label>
                  <Input
                    type="email"
                    placeholder={t(
                      "prepPlan.lesson.email.recipientPlaceholder",
                    )}
                    value={targetEmailInput}
                    onChange={(e) => {
                      setTargetEmailInput(e.target.value);
                    }}
                  />
                </div>
              </TabsContent>
            </Tabs>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEmailModalOpen(false)}
              disabled={sendingEmail}
            >
              {t("common.cancel")}
            </Button>
            <Button
              onClick={executeSendEmail}
              disabled={
                sendingEmail ||
                (emailTargetType === "others" && !targetEmailInput.trim())
              }
            >
              {sendingEmail ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Mail className="h-4 w-4 mr-2" />
              )}
              {sendingEmail
                ? t("prepPlan.lesson.email.sending")
                : t("prepPlan.lesson.email.confirmSend")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("prepPlan.lesson.deletePlan")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget
                ? t("prepPlan.lesson.deleteConfirm", {
                    title: buildPlanSummary(deleteTarget, t).title,
                  })
                : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-white hover:bg-destructive/90"
              disabled={deletingPlanId === deleteTarget?.id}
              onClick={() => {
                if (deleteTarget) {
                  void handleDeletePlan(deleteTarget.id);
                  setDeleteTarget(null);
                }
              }}
            >
              {deletingPlanId === deleteTarget?.id && (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              )}
              {t("prepPlan.lesson.deletePlan")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <PdfPreviewDialog
        open={previewOpen}
        onClose={handlePreviewClose}
        blobUrl={previewBlobUrl}
        filename={previewFilename}
      />

      <Sheet open={templateSheetOpen} onOpenChange={setTemplateSheetOpen}>
        <SheetContent className="w-[360px] overflow-y-auto sm:max-w-[420px]">
          <SheetHeader>
            <SheetTitle>{t("prepPlan.lesson.templateTitle")}</SheetTitle>
          </SheetHeader>
          <div className="space-y-3 py-4">
            {templatesLoading ? (
              <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("prepPlan.lesson.templateLoading")}
              </div>
            ) : templates.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                {t("prepPlan.lesson.templateEmpty")}
              </div>
            ) : (
              templates.map((tpl) => (
                <Card key={String(tpl.id)} className="p-4">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-foreground">
                      {tpl.name}
                    </span>
                    <Badge variant="secondary">{tpl.category}</Badge>
                  </div>
                  {tpl.description ? (
                    <p className="mb-3 text-xs leading-5 text-muted-foreground">
                      {tpl.description}
                    </p>
                  ) : null}
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full gap-1.5"
                    onClick={() => handleApplyTemplate(tpl)}
                  >
                    <Check className="h-4 w-4" />
                    {t("prepPlan.lesson.templateApply")}
                  </Button>
                </Card>
              ))
            )}
          </div>
        </SheetContent>
      </Sheet>

      <Dialog open={outlineDialogOpen} onOpenChange={setOutlineDialogOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t("prepPlan.lesson.outline.title")}</DialogTitle>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh]">
            <div className="space-y-4 py-2">
              {outline?.title ? (
                <div>
                  <div className="mb-1 text-sm font-semibold text-foreground">
                    {t("prepPlan.lesson.outline.titleLabel")}
                  </div>
                  <div className="whitespace-pre-wrap text-sm text-foreground/85">
                    {outline.title}
                  </div>
                </div>
              ) : null}
              {outline?.objectives ? (
                <div>
                  <div className="mb-1 text-sm font-semibold text-foreground">
                    {t("prepPlan.lesson.outline.objectivesLabel")}
                  </div>
                  <div className="whitespace-pre-wrap text-sm text-foreground/85">
                    {outline.objectives}
                  </div>
                </div>
              ) : null}
              {outline?.key_points ? (
                <div>
                  <div className="mb-1 text-sm font-semibold text-foreground">
                    {t("prepPlan.lesson.outline.keyPointsLabel")}
                  </div>
                  <div className="whitespace-pre-wrap text-sm text-foreground/85">
                    {outline.key_points}
                  </div>
                </div>
              ) : null}
              {outline?.difficult_points ? (
                <div>
                  <div className="mb-1 text-sm font-semibold text-foreground">
                    {t("prepPlan.lesson.outline.difficultPointsLabel")}
                  </div>
                  <div className="whitespace-pre-wrap text-sm text-foreground/85">
                    {outline.difficult_points}
                  </div>
                </div>
              ) : null}
              {Array.isArray(outline?.process_summary) &&
              outline.process_summary.length > 0 ? (
                <div>
                  <div className="mb-1 text-sm font-semibold text-foreground">
                    {t("prepPlan.lesson.outline.processLabel")}
                  </div>
                  <ol className="list-decimal space-y-1 pl-5 text-sm text-foreground/85">
                    {outline.process_summary.map((item, idx) => (
                      <li key={idx}>
                        {item?.step || ""}
                        {item?.point ? `：${item.point}` : ""}
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}
            </div>
          </ScrollArea>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setOutlineDialogOpen(false)}
              disabled={aiFilling}
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="outline"
              className="gap-2"
              onClick={handleRegenerateOutline}
              disabled={aiFilling}
            >
              <RefreshCw className="h-4 w-4" />
              {t("prepPlan.lesson.outline.regenerate")}
            </Button>
            <Button onClick={handleConfirmOutline} disabled={aiFilling}>
              {aiFilling ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : null}
              {aiFilling
                ? t("prepPlan.lesson.outline.generatingFull")
                : t("prepPlan.lesson.outline.confirmAndGenerate")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={resourceDialogOpen} onOpenChange={setResourceDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("prepPlan.lesson.resource.title")}</DialogTitle>
          </DialogHeader>
          <div className="py-2">
            {/* 面包屑：根目录 / 年级 / 学科 / 知识点，点击任意段跳转 */}
            <nav className="mb-2 flex flex-wrap items-center gap-0.5 text-sm">
              <button
                type="button"
                onClick={() => setResourcePath([])}
                className={`rounded px-1.5 py-0.5 transition-colors ${
                  resourcePath.length === 0
                    ? "font-semibold text-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                {t("prepPlan.lesson.resource.root")}
              </button>
              {resourcePath.map((seg, i) => (
                <Fragment key={`${seg}-${i}`}>
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <button
                    type="button"
                    onClick={() => setResourcePath(resourcePath.slice(0, i + 1))}
                    className={`max-w-[8rem] truncate rounded px-1.5 py-0.5 transition-colors ${
                      i === resourcePath.length - 1
                        ? "font-semibold text-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    }`}
                  >
                    {seg}
                  </button>
                </Fragment>
              ))}
            </nav>

            {resourceFolderLoading ? (
              <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("prepPlan.lesson.resource.loading")}
              </div>
            ) : resourceFolders.length === 0 &&
              resourceFiles.length === 0 &&
              !resourceFilesLoading ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                {t("prepPlan.lesson.resource.empty")}
              </div>
            ) : (
              <div className="space-y-2">
                {resourceFolders.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {resourceFolders.map((folder) => (
                      <Button
                        key={folder.name}
                        variant="outline"
                        size="sm"
                        onClick={() => enterResourceFolder(folder.name)}
                      >
                        <Folder className="h-3.5 w-3.5 shrink-0" />
                        {folder.name}
                      </Button>
                    ))}
                  </div>
                ) : null}
                {resourceFilesLoading ? (
                  <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t("prepPlan.lesson.resource.loading")}
                  </div>
                ) : resourceFiles.length > 0 ? (
                  <div className="mt-3 max-h-[280px] overflow-y-auto rounded-md border bg-muted/15 p-2">
                    {resourceFiles.map((file) => (
                      <button
                        key={file.name}
                        type="button"
                        className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted/60"
                        onClick={() => insertResource(file)}
                      >
                        <span className="min-w-0 flex-1 truncate">
                          {file.name}
                        </span>
                        <Link2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
