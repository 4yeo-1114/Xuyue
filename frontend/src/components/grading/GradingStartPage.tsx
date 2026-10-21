import {
  useState,
  useRef,
  useCallback,
  useEffect,
  useMemo,
  Fragment,
} from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  PenTool,
  FolderOpen,
  Upload,
  Loader2,
  ArrowLeft,
  ArrowRight,
  Search,
  Trash2,
  Edit2,
  Printer,
  StopCircle,
  Check,
  X,
  Settings,
  BarChart3,
  Save,
  Download,
  Eraser,
  Camera,
  Split,
  Eye,
  AlertCircle,
  RefreshCw,
  Sparkles,
  RotateCcw,
  RotateCw,
  ClipboardList,
  ImagePlus,
  Minus,
  Plus,
  Maximize2,
  ExternalLink,
  Send,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  listFolders,
  exportClassData,
  createFolder,
  importClassData,
  renameFolder,
  renameFolderFile,
  deleteFolders,
  listFolderFiles,
  fetchGradingHistory,
  fetchEssayGradingHistory,
  uploadToFolder,
  startReferenceGrade,
  backfillBlocks,
  referenceGradeStatus,
  cancelReferenceGrade,
  pushDingtalkNotify,
  saveAnswerKey,
  getAnswerKey,
  uploadOriginalPaper,
  uploadAnswerSheet,
  getAnswerSheetRows,
  saveAnswerSheetRows,
  recognizePaperScores,
  applyPaperScores,
  gradeByAnswerKey,
  answerKeyGradeStatus,
  cancelAnswerKeyGrade,
  startEssayGrade,
  essayGradeStatus,
  cancelEssayGrade,
  deleteFolderFile,
  printMarks,
  printTestMarksGrade,
  printMarksBatch,
  startPrintMarksBatch,
  printMarksBatchStatus,
  cancelPrintMarksBatch,
  startScanImport,
  stopScanImport,
  getScanImportStatus,
  gradingImageUrl,
  downloadEssayGradePdf,
  downloadMarksPdf,
  browserPrintMarksPdf,
  exportMarksPdf,
  rotateImage,
  exportEssayGradePdf,
  browserPrintEssayGradePdf,
  printEssayGradePdf,
  saveScoringConfig,
  applyScoringConfig,
  autoScoringConfig,
  saveManualGrade,
  clearManualGrade,
  getEssayRubrics,
  createEssayRubric,
  updateEssayRubric,
  deleteEssayRubrics,
  prepareReferenceLayout,
  getReferenceLayout,
  confirmReferenceLayout,
  getReferenceAnswerTable,
  saveReferenceAnswerTable,
  rebuildReferenceAnswerTable,
  type ReferenceAnswerTablePage,
  prepareManualLayout,
  manualHistoryEngine,
  getManualLayout,
  confirmManualLayout,
  saveManualSlotDecisions,
  saveEssayScore,
  saveEssayResult,
  correctAiBlocks,
  aiPaperSummary,
  saveEssayNote,
  generateWrongAnnotation,
  saveWrongAnnotations,
  type WrongAnnotationsMap,
  type DeductionItemsMap,
  type EssayRubric,
  type EssayDimension,
  type EssayScorePayload,
  type EssayPdfItem,
  type GradingEngine,
  type QuestionStructure,
  type PrintPaperSize,
  type CustomPaperMm,
  type ReferenceLayoutPage,
  type ReferenceLayoutStatus,
  type ManualSlotDecision,
  type ClassDataImportResult,
  type AnswerSheetRow,
} from "@/services/gradingApi";
import { saveBlob } from "@/services/complianceApi";
import { notifyAutoReportCheck } from "@/services/aiAutoReportApi";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PdfPreview } from "./PdfPreview";
import { GradingErrorBoundary } from "./GradingErrorBoundary";
import { PrivacyNoticeDialog } from "@/components/common/PrivacyNoticeDialog";
import { AIGeneratedBadge } from "@/components/common/AIGeneratedBadge";
import { importClassReviewExams, listStudentsByClass } from "@/services/api";
import type { StudentInfo } from "@/types/api";
import { useGlobalPrintPrefs } from "@/hooks/useGlobalPrintPrefs";
import { useGlobalFilters } from "@/hooks/useGlobalFilters";
import { getSubjectsBySchoolLevel } from "@/components/SubjectTabs";
import { usePrinters } from "@/hooks/usePrinters";
import { useLocale } from "@/contexts/LocaleContext";
import { PrinterSettingsPanel } from "@/components/shared/PrinterSettingsPanel";
import { PRINTER_DEFAULT, printerOutputMode } from "@/lib/globalPrintPrefs";
import {
  parseAiResultBlocks,
  type AiResultBlock,
} from "@/utils/aiResultBlocks";
import { ReferenceLayoutCorrectionDialog } from "./ReferenceLayoutCorrectionDialog";
import {
  LayoutTemplateDialog,
  saveLayoutTemplate,
  type LayoutTemplateDetail,
} from "./LayoutTemplateDialog";
import {
  applyTemplateToPages,
  packLayoutForTemplate,
  templateLayoutPages,
} from "./layoutTemplateUtils";
import {
  StandardAnswerTableDialog,
  type AnswerTableEdit,
} from "./StandardAnswerTableDialog";
import { AnswerSheetDialog } from "./AnswerSheetDialog";
import { PaperScoreConfirmDialog, type PaperScoreItem } from "./PaperScoreConfirmDialog";
import { ManualPaperGradingDialog, type ManualAnnotations, type ManualPaperDirection } from "./ManualPaperGradingDialog";
import { WrongAnnotationCard } from "./WrongAnnotationCard";
import {
  EssayDimensionConfigEditor,
  EssayDimensionScoreCard,
  parseEssayDimensions,
} from "./EssayDimensionPanels";

interface GradingStartPageProps {
  selectedClass: string;
}

const POLL_INTERVAL = 2000;
const REF_JOB_STORAGE_PREFIX = "grade_buddy_ref_job_id__";
const ESSAY_JOB_STORAGE_PREFIX = "grade_buddy_essay_job_id__";
const FOLDER_PREFS_STORAGE_PREFIX = "grade_buddy_folder_prefs__";
const CLASS_REVIEW_PUSH_PREFIX = "grade_buddy_class_review_pushed__";
const CLASS_REVIEW_AUTO_PUSH_KEY = "grade_buddy_auto_push_class_review";
const DEFAULT_PAPER_BOX_CAPACITY = 1;
const MAX_PAPER_BOX_CAPACITY = 20;

type OrchestrationStatus =
  | { phase: "idle" }
  | { phase: "scanning" }
  | { phase: "grading"; jobId?: string | null }
  | { phase: "printing"; jobId?: string | null }
  | { phase: "done" }
  | { phase: "error"; step: "scan" | "grade" | "print"; message: string };

const ORCHESTRATE_STEPS = ["scan", "grade", "print"] as const;
type OrchestrateStep = (typeof ORCHESTRATE_STEPS)[number];

type FolderFileItem = { name: string; url: string; type?: string };

type StandardAnswerItem = FolderFileItem & {
  filename: string;
  page_no: number;
};

type PaperBox = {
  student: StudentInfo;
  files: FolderFileItem[];
  slots: Array<FolderFileItem | null>;
};

type AiBlock = {
  index: number;
  sub_index?: number | null;
  result: "对" | "错" | "未作答" | "半对";
  comment?: string;
  manual_note?: string;
  score?: number | null;
  partial_ratio?: number | null;
  baidu_is_slot?: boolean;
  baidu_real_name?: string;
  [key: string]: unknown;
};

type RefCompleted = {
  name: string;
  result: string;
  image_annotated?: string;
  image_marks_only?: string;
  image_marks_with_wrong_notes?: string;
  image_annotated_with_wrong_notes?: string;
  image_original?: string;
  marks_only_filename?: string;
  marks_with_wrong_notes_filename?: string;
  annotated_with_wrong_notes_filename?: string;
  ocr_title?: string;
  ocr_content?: string;
  score_total?: number | null;
  essay_grade?: string | null;
  dimension_scores?: Record<string, number> | null;
  question_scores?: Record<string, number> | null;
  group_name?: string;
  group_pages?: string[];
  blocks?: AiBlock[];
  question_notes?: Record<string, string>;
  paper_note?: string;
  wrong_annotations?: WrongAnnotationsMap;
  deduction_items?: DeductionItemsMap;
};

/** 智能批改 block → 统分键（与后端 _ai_block_score_key 口径一致） */
function aiBlockScoreKey(b: AiBlock): string {
  return b.baidu_is_slot && b.sub_index
    ? `第${b.index}题-作答区${b.sub_index}`
    : `第${b.index}题`;
}

/** 汇总一道题各作答区的 AI 评语，作为「AI批注」预填文本 */
function aiNoteTextForQuestion(blocks: AiBlock[]): string {
  const parts: string[] = [];
  for (const b of blocks) {
    const c = (b.comment ?? "").trim();
    if (!c) continue;
    if (blocks.length > 1 && b.sub_index != null) {
      parts.push(`作答区${b.sub_index}：${c}`);
    } else {
      parts.push(c);
    }
  }
  return parts.join("；");
}

function classReviewPushKey(folder: string, subject: string): string {
  return `${CLASS_REVIEW_PUSH_PREFIX}${folder}__${subject}`;
}

function hasPushedClassReview(folder: string, subject: string): boolean {
  try {
    return localStorage.getItem(classReviewPushKey(folder, subject)) === "1";
  } catch {
    return false;
  }
}

function markClassReviewPushed(folder: string, subject: string): void {
  try {
    localStorage.setItem(classReviewPushKey(folder, subject), "1");
  } catch {
    // 隐私模式/存储满时静默降级
  }
}

/** 自主阅卷（答题卡）与自主阅卷（试卷）共用同一套作答区切题与留痕管线，
 * 只是框线来源不同（答题卡框线检测 vs 标准答题区）；参照批改同管线、按标准答案判分。 */
function isManualEngine(engine: GradingEngine): boolean {
  return (
    engine === "manual" ||
    engine === "manual_reference" ||
    engine === "manual_paper"
  );
}

function readAutoPushPreference(): boolean {
  try {
    return localStorage.getItem(CLASS_REVIEW_AUTO_PUSH_KEY) === "1";
  } catch {
    return false;
  }
}

function writeAutoPushPreference(enabled: boolean): void {
  try {
    localStorage.setItem(CLASS_REVIEW_AUTO_PUSH_KEY, enabled ? "1" : "0");
  } catch {
    // 隐私模式/存储满时静默降级
  }
}

/** 钉钉推送模式：auto=批改完自动推 / manual=手动点按钮推（默认自动） */
const DINGTALK_PUSH_MODE_KEY = "grade_buddy_dingtalk_push_mode";

function readDingtalkPushMode(): "auto" | "manual" {
  try {
    return localStorage.getItem(DINGTALK_PUSH_MODE_KEY) === "manual"
      ? "manual"
      : "auto";
  } catch {
    return "auto";
  }
}

function writeDingtalkPushMode(mode: "auto" | "manual"): void {
  try {
    localStorage.setItem(DINGTALK_PUSH_MODE_KEY, mode);
  } catch {
    // 隐私模式/存储满时静默降级
  }
}

function getEssayGroupBaseName(filename?: string | null): string {
  const name = String(filename || "").trim();
  const stem = name.replace(/\.[^.]+$/, "");
  const m = stem.match(/^(.*?)_\d+$/);
  return m?.[1] || stem;
}

function getManualResultScore(item: RefCompleted | null | undefined): number {
  if (!item) return 0;
  try {
    const parsed = JSON.parse(item.result || "{}");
    const value = Number(parsed.score_total ?? item.score_total ?? 0);
    return Number.isFinite(value) ? value : 0;
  } catch {
    const value = Number(item.score_total || 0);
    return Number.isFinite(value) ? value : 0;
  }
}

/** 有卷面题号结构时按原卷题号展示（如「1 读拼音，写词语」「（1） 加点字读音」「二 观察与梳理」），
 *  否则回退「第N题」。题号必须按原卷来：是 1 就是 1，是（1）就是（1），不再用「第N题/第一大题」重排。 */
function structureDisplayFor(
  structure: QuestionStructure | null | undefined,
  title: string,
): string {
  const s = structure?.[title];
  const num = s?.sub || s?.major || "";
  const qt = s?.question_text || "";
  if (num) return qt ? `${num} ${qt}` : num;
  return title;
}

/** 统分界面里只显示题号（不显示题干），如「1」「（1）」「二」；无卷面题号时回退「第N题」的 N。 */
function structureNumberOnly(
  structure: QuestionStructure | null | undefined,
  title: string,
): string {
  const s = structure?.[title];
  // 印刷题号（标准答题区路径带回）优先——那就是老师卷面上认得的题号
  const num = (s?.printed_no || s?.sub || s?.major || "").trim();
  if (num) return num;
  const m = (title || "").match(/^第(.+?)题$/);
  return m ? m[1] : title;
}

/** 从首个小标题号推断格式，生成第 index 个小标题号（index 从 1 开始）。
 *  例：首题号「(1)」→「(3)」；「①」→「③」；「1」→「3」。 */
function subLabelAt(firstSub: string | undefined, index: number): string {
  const s = (firstSub || "").trim();
  if (!s) return String(index);
  const paren = s.match(/^[（(]\s*(\d+)\s*[)）]$/);
  if (paren) return `(${index})`;
  const circled = "①②③④⑤⑥⑦⑧⑨⑩";
  if (circled.includes(s)) return circled[index - 1] ?? String(index);
  return String(index);
}

/** 把「第N题-作答区M：对；…」子项文本替换成「M：对；…」（M 按卷面小题号格式生成）。 */
function renderSubItemContent(
  blockTitle: string,
  content: string,
  structure: QuestionStructure | null | undefined,
): string {
  const text = content || "";
  const m = text.match(/^第.+?题-作答区(\d+)[:：]\s*/);
  if (!m) return text;
  const zone = parseInt(m[1], 10);
  const s = structure?.[blockTitle];
  const label = subLabelAt(s?.sub, zone);
  return text.replace(/^第.+?题-作答区\d+[:：]\s*/, `${label}：`);
}

/** 统分界面里，把「第N题-作答区M」标题转成小题号标签（如「1」「(1)」）。 */
function subTitleDisplay(
  fullTitle: string,
  structure: QuestionStructure | null | undefined,
): string {
  const m = (fullTitle || "").match(/^第(.+?)题-作答区(\d+)$/);
  if (!m) return fullTitle;
  const blockTitle = `第${m[1]}题`;
  const zone = parseInt(m[2], 10);
  const s = structure?.[blockTitle];
  return subLabelAt(s?.sub, zone);
}

/** 单张试卷是否已批改（与后端统计、界面「已批改」徽章一致） */
function isPaperGraded(
  item: RefCompleted | undefined,
  engine: GradingEngine,
): boolean {
  if (!item?.name) return false;
  if (engine === "essay") {
    return Boolean(String(item.result || "").trim());
  }
  if (isManualEngine(engine)) {
    if (!item.result) return false;
    try {
      const parsed = JSON.parse(item.result);
      return (
        parsed?.type === "manual_analyze" && parsed?.manual_status === "graded"
      );
    } catch {
      return false;
    }
  }
  return Boolean(
    String(item.result || "").trim() ||
    item.image_marks_only ||
    item.marks_only_filename ||
    item.image_annotated,
  );
}

type PaperBoxStatus = "graded" | "full" | "incomplete";

/** 试卷框展示状态：已批改优先于已满/未满 */
function getPaperBoxStatus(
  filledCount: number,
  capacity: number,
  allGraded: boolean,
): PaperBoxStatus {
  if (allGraded && filledCount > 0) return "graded";
  if (filledCount >= capacity) return "full";
  return "incomplete";
}

type TranslateFn = (
  key: string,
  params?: Record<string, string | number>,
  fallback?: string,
) => string;

function getPaperBoxStatusLabel(
  status: PaperBoxStatus,
  engine: GradingEngine,
  t: TranslateFn,
): string {
  if (isManualEngine(engine))
    return status === "graded"
      ? t("grading.status.graded")
      : t("grading.status.ungraded");
  if (status === "graded") return t("grading.status.graded");
  if (status === "full") return t("grading.status.full");
  return t("grading.status.incomplete");
}

function getPaperBoxStatusBadgeClass(
  status: PaperBoxStatus,
  engine: GradingEngine,
): string {
  if (isManualEngine(engine) && status !== "graded")
    return "bg-red-100 text-red-700 border border-red-200";
  if (status === "graded") {
    return "bg-green-100 text-green-700";
  }
  if (status === "full")
    return "bg-orange-100 text-orange-800 border border-orange-200";
  return "bg-red-100 text-red-700 border border-red-200";
}

function getCompletedItemRichness(item?: Partial<RefCompleted> | null): number {
  if (!item) return -1;
  let score = 0;
  if (item.result) score += 2;
  if (item.image_annotated) score += 2;
  if (item.image_original) score += 1;
  if (item.image_marks_only) score += 1;
  if (item.marks_only_filename) score += 1;
  return score;
}

function mergeCompletedLists(
  ...lists: Array<Array<RefCompleted | undefined> | null | undefined>
): RefCompleted[] {
  const map: Record<string, RefCompleted> = {};
  for (const list of lists) {
    for (const item of list || []) {
      if (!item?.name) continue;
      const existing = map[item.name];
      if (
        !existing ||
        getCompletedItemRichness(item) >= getCompletedItemRichness(existing)
      ) {
        map[item.name] = item;
      }
    }
  }
  return Object.values(map);
}

/** 从文件名取试卷框页码（`名_2.jpg` → 2）；无 `_\d+` 后缀视为第 1 页。 */
function paperBoxPageNumberOfName(filename?: string | null): number {
  const stem = String(filename || "").trim().replace(/\.[^.]+$/, "");
  const m = stem.match(/_(\d+)$/);
  return m ? Math.max(1, parseInt(m[1], 10)) : 1;
}

/** 同 base 分组里，completed 条目 entryName 是否覆盖 fileName 这一页。
 *  作文批改是整卷语义（多页重复同一总分）→ 同 base 即覆盖；
 *  智能/参照/自主阅卷每页独立计分 → 只有同页条目才覆盖，不能拿别的页的结果顶替。 */
function completedEntryCoversFile(
  entryName: string,
  fileName: string,
  engine: GradingEngine,
): boolean {
  if (engine === "essay") return true;
  return (
    paperBoxPageNumberOfName(entryName) === paperBoxPageNumberOfName(fileName)
  );
}

function findCompletedEntryForFile(
  filename: string,
  merged: Record<string, RefCompleted>,
  engine: GradingEngine,
): RefCompleted | undefined {
  const direct = merged[filename];
  if (isPaperGraded(direct, engine)) return direct;
  const base = getEssayGroupBaseName(filename);
  let best: RefCompleted | undefined;
  let bestScore = -1;
  for (const item of Object.values(merged)) {
    if (!item?.name) continue;
    if (getEssayGroupBaseName(item.name) !== base) continue;
    if (!completedEntryCoversFile(item.name, filename, engine)) continue;
    if (!isPaperGraded(item, engine)) continue;
    const score = getCompletedItemRichness(item);
    if (score > bestScore) {
      bestScore = score;
      best = item;
    }
  }
  return best;
}

function isFileMarkedGraded(
  filename: string,
  merged: Record<string, RefCompleted>,
  engine: GradingEngine,
): boolean {
  return !!findCompletedEntryForFile(filename, merged, engine);
}

/** 汇总一个学生试卷框的「分数 + 等级」。
 *  作文批改：score_total 是整卷总分，多页会重复写同一总分 → 取最大值，不累加。
 *  智能/参照/自主阅卷：每页独立计分 → 累加各页 score_total。 */
function computeBoxScoreGrade(
  box: PaperBox,
  merged: Record<string, RefCompleted>,
  engine: GradingEngine,
): { score: number | null; grade: string } {
  let score: number | null = null;
  let grade = "";
  const seen = new Set<string>();
  const isEssay = engine === "essay";
  for (const f of box.files) {
    const item = findCompletedEntryForFile(f.name, merged, engine);
    if (!item || !item.name || seen.has(item.name)) continue;
    seen.add(item.name);
    const v =
      typeof item.score_total === "number" && Number.isFinite(item.score_total)
        ? item.score_total
        : null;
    if (v != null) {
      if (isEssay) {
        score = score == null ? v : Math.max(score, v);
      } else {
        score = (score ?? 0) + v;
      }
    }
    if (!grade && item.essay_grade) grade = item.essay_grade;
  }
  if (score != null) score = Math.round(score * 100) / 100;
  return { score, grade };
}

/** 正反面合并拆分展示：多页且各页有分时返回「正40+反60=100分」（第1页=正面、第2页=反面、3起=页N）。
 *  作文整卷计分不拆分（多页重复同一总分）；单页不展示拆分。 */
function computeBoxPageBreakdown(
  box: PaperBox,
  merged: Record<string, RefCompleted>,
  engine: GradingEngine,
): string {
  if (engine === "essay") return "";
  const parts: string[] = [];
  let sum = 0;
  const seen = new Set<string>();
  for (const f of box.files) {
    const item = findCompletedEntryForFile(f.name, merged, engine);
    if (!item || !item.name || seen.has(item.name)) continue;
    seen.add(item.name);
    const v =
      typeof item.score_total === "number" && Number.isFinite(item.score_total)
        ? item.score_total
        : null;
    if (v == null) continue;
    sum += v;
    const m = String(f.name).replace(/\.[^.]+$/, "").match(/_(\d+)$/);
    const page = m ? Math.max(1, parseInt(m[1], 10)) : 1;
    const label = page <= 1 ? "正" : page === 2 ? "反" : `页${page}`;
    const vs = Math.round(v * 100) / 100;
    parts.push(`${label}${vs}`);
  }
  if (parts.length < 2) return "";
  const total = Math.round(sum * 100) / 100;
  return `${parts.join("+")}=${total}分`;
}

function extractAiScoringTitlesFromBlocks(blocks: AiResultBlock[]): string[] {
  const titles: string[] = [];
  const seen = new Set<string>();
  blocks.forEach((block) => {
    if (
      !/^第([0-9A-Za-z\(\)（）一二三四五六七八九十百千两]+)题/.test(block.title)
    )
      return;
    // 题级：一道题一个分值，不再拆到作答区（避免 3 分 6 空=0.5 分这类小数）
    if (!seen.has(block.title)) {
      titles.push(block.title);
      seen.add(block.title);
    }
  });
  return titles;
}

function normalizeManualText(value: unknown): string {
  if (typeof value !== "string") return "";
  return value
    .replace(/\r\n?/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function getManualQuestionTypeLabel(type: unknown, t: TranslateFn): string {
  switch (String(type || "")) {
    case "0":
      return t("grading.questionType.choice");
    case "1":
      return t("grading.questionType.judge");
    case "2":
      return t("grading.questionType.blank");
    case "3":
      return t("grading.questionType.essay");
    default:
      return t("grading.questionType.other");
  }
}

function serializeManualScores(scores: Record<string, string>) {
  return JSON.stringify(
    Object.keys(scores)
      .sort((a, b) =>
        a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }),
      )
      .reduce<Record<string, string>>((acc, key) => {
        acc[key] = scores[key] ?? "";
        return acc;
      }, {}),
  );
}

function normalizeManualScoreInput(raw: string): string {
  const cleaned = raw.replace(/[^\d.]/g, "");
  if (!cleaned) return "";
  const firstDot = cleaned.indexOf(".");
  if (firstDot === -1) return cleaned;
  const integerPart = cleaned.slice(0, firstDot + 1);
  const decimalPart = cleaned.slice(firstDot + 1).replace(/\./g, "");
  return `${integerPart}${decimalPart.slice(0, 1)}`;
}

// R2 作业采集：作业类型可选项（值直接落库，与学科「语文」等中文值保持一致）
const HOMEWORK_TYPES = [
  "课后作业",
  "随堂练习",
  "单元测试",
  "周测",
  "月考",
  "期中考试",
  "期末考试",
  "模拟考试",
  "作文",
];

// 试卷框预览内嵌缩放：右上角按钮或 Ctrl+滚轮 放大/缩小，「适合窗口」还原，可新标签页打开原图。
function ZoomableImage({ src, alt }: { src: string; alt: string }) {
  const { t } = useLocale();
  const viewportRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [viewport, setViewport] = useState<{ w: number; h: number }>({
    w: 0,
    h: 0,
  });

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const update = () => setViewport({ w: el.clientWidth, h: el.clientHeight });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 切换图片（换学生/换试卷）时还原缩放，并用独立 Image 探测自然尺寸（比依赖 <img onLoad> 更可靠）
  useEffect(() => {
    setNatural(null);
    setZoom(1);
    setRotation(0);
    let alive = true;
    const probe = new Image();
    probe.onload = () => {
      if (alive && probe.naturalWidth && probe.naturalHeight) {
        setNatural({ w: probe.naturalWidth, h: probe.naturalHeight });
      }
    };
    probe.src = src;
    return () => {
      alive = false;
    };
  }, [src]);

  const clamp = (v: number, min: number, max: number) =>
    Math.min(max, Math.max(min, v));

  // viewport 已扣除外层 p-3，这里再预留内层 p-3（两侧共 24px）让「适合窗口」留边
  const PAD = 24;
  const rotated = rotation % 180 !== 0;
  // 旋转 90/270 时按交换后的宽高计算「适合窗口」
  const fitW = natural ? (rotated ? natural.h : natural.w) : 0;
  const fitH = natural ? (rotated ? natural.w : natural.h) : 0;
  const fitScale =
    natural && viewport.w > 0 && viewport.h > 0
      ? Math.min(
          Math.max(viewport.w - PAD, 0) / fitW,
          Math.max(viewport.h - PAD, 0) / fitH,
        )
      : 1;
  const scale = fitScale * zoom;
  const w = natural ? Math.round(natural.w * scale) : undefined;
  const h = natural ? Math.round(natural.h * scale) : undefined;

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden">
      <div className="absolute right-2 top-2 z-10 flex items-center gap-0.5 rounded-lg border border-border/70 bg-background/90 p-0.5 shadow-sm backdrop-blur">
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          onClick={() => setZoom((z) => clamp(z * 0.8, 0.2, 6))}
          title={t("grading.layout.zoomOut")}
        >
          <Minus className="h-4 w-4" />
        </Button>
        <span className="w-12 select-none text-center text-xs font-semibold text-muted-foreground">
          {Math.round(zoom * 100)}%
        </span>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          onClick={() => setZoom((z) => clamp(z * 1.25, 0.2, 6))}
          title={t("grading.layout.zoomIn")}
        >
          <Plus className="h-4 w-4" />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          onClick={() => setZoom(1)}
          title={t("grading.layout.resetZoom")}
        >
          <Maximize2 className="h-4 w-4" />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          onClick={() => setRotation((r) => (r + 90) % 360)}
          title={t("grading.preview.rotate", undefined, "旋转")}
        >
          <RotateCw className="h-4 w-4" />
        </Button>
        <a
          href={src}
          target="_blank"
          rel="noopener noreferrer"
          title={t("grading.preview.openOriginal", undefined, "打开原图")}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <ExternalLink className="h-4 w-4" />
        </a>
      </div>
      <div
        ref={viewportRef}
        className="min-h-0 flex-1 overflow-auto"
        onWheel={(e) => {
          if (!e.ctrlKey && !e.metaKey) return;
          e.preventDefault();
          setZoom((z) => clamp(z * (e.deltaY < 0 ? 1.1 : 0.9), 0.2, 6));
        }}
      >
        <div className="flex min-h-full min-w-full p-3">
          {w && h ? (
            <div
              className="relative m-auto shrink-0 bg-white shadow-sm"
              style={{ width: rotated ? h : w, height: rotated ? w : h }}
            >
              <img
                key={src}
                src={src}
                alt={alt}
                draggable={false}
                className="absolute left-1/2 top-1/2 block select-none"
                style={{
                  width: w,
                  height: h,
                  transform: `translate(-50%, -50%) rotate(${rotation}deg)`,
                  transition: "transform 0.2s ease",
                }}
              />
            </div>
          ) : (
            <div className="m-auto flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("grading.preview.loading", undefined, "加载中…")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function GradingStartPage({ selectedClass }: GradingStartPageProps) {
  const { t } = useLocale();
  const { selectedSubject, grade, schoolLevel } = useGlobalFilters();
  const navigate = useNavigate();
  const displayFolderName = useCallback((name: string) => {
    const s = String(name || "");
    if (s.startsWith("cls_")) {
      const i = s.indexOf("__");
      if (i > 4 && i + 2 < s.length) return s.slice(i + 2);
    }
    return s;
  }, []);

  const [view, setView] = useState<"list" | "folder">("list");
  const [folders, setFolders] = useState<string[]>([]);
  const [folderMeta, setFolderMeta] = useState<
    Record<string, { subject?: string; grade?: string; homework_type?: string }>
  >({});
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);

  // 钉钉报告链接深链：?folder=cls_<class_id>__<exam> 直接打开对应文件夹
  const [searchParams] = useSearchParams();
  useEffect(() => {
    const folderFromUrl = (searchParams.get("folder") || "").trim();
    if (!folderFromUrl) return;
    if (!/^cls_[A-Za-z0-9\-_]+__/.test(folderFromUrl)) return;
    setSelectedFolder(folderFromUrl);
    setView("folder");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  /** 批改完成自动推送到「课堂讲评」的开关（默认关，手动开启，持久化到本地） */
  const [autoPushClassReview, setAutoPushClassReview] = useState(
    readAutoPushPreference,
  );
  useEffect(() => {
    writeAutoPushPreference(autoPushClassReview);
  }, [autoPushClassReview]);

  /** 钉钉推送模式：auto=批改完自动推 / manual=手动推（持久化到本地） */
  const [dingtalkPushMode, setDingtalkPushMode] = useState(
    readDingtalkPushMode,
  );
  useEffect(() => {
    writeDingtalkPushMode(dingtalkPushMode);
  }, [dingtalkPushMode]);
  /** 手动推送进行中标记，避免连点并发 */
  const [dingtalkPushing, setDingtalkPushing] = useState(false);

  /** 批改完成自动推送到「课堂讲评」的弹窗状态 */
  const [classReviewPushOpen, setClassReviewPushOpen] = useState(false);
  const [classReviewPushState, setClassReviewPushState] = useState<{
    status: "pushing" | "success" | "error";
    message?: string;
    subject?: string;
  }>({ status: "success" });
  /** 推送进行中标记，避免并发 */
  const classReviewPushingRef = useRef(false);
  const [folderFiles, setFolderFiles] = useState<FolderFileItem[]>([]);
  const [standardAnswers, setStandardAnswers] = useState<StandardAnswerItem[]>(
    [],
  );
  const [referenceLayoutStatus, setReferenceLayoutStatus] =
    useState<ReferenceLayoutStatus>({
      confirmed: false,
      reviewed_pages: [],
      stale_pages: [],
    });
  const [referenceLayoutPages, setReferenceLayoutPages] = useState<
    ReferenceLayoutPage[]
  >([]);
  const [referenceLayoutPrepareId, setReferenceLayoutPrepareId] = useState<
    string | null
  >(null);
  const [referenceLayoutOpen, setReferenceLayoutOpen] = useState(false);
  const [referenceLayoutPreparing, setReferenceLayoutPreparing] =
    useState(false);
  const [referenceLayoutOpening, setReferenceLayoutOpening] = useState(false);
  const [referenceLayoutSaving, setReferenceLayoutSaving] = useState(false);
  // 布局模板（跨考试复用框选）：存为模板 / 从模板应用
  const [layoutTemplateOpen, setLayoutTemplateOpen] = useState(false);
  const [layoutTemplateMode, setLayoutTemplateMode] = useState<"save" | "apply">(
    "save",
  );
  const [layoutTemplateSaving, setLayoutTemplateSaving] = useState(false);
  const [answerTableOpen, setAnswerTableOpen] = useState(false);
  const [answerTableLoading, setAnswerTableLoading] = useState(false);
  const [answerTableSaving, setAnswerTableSaving] = useState(false);
  const [answerTablePages, setAnswerTablePages] = useState<
    ReferenceAnswerTablePage[]
  >([]);
  // 答案纸专窗：只看「题号+答案」，确认后与答题区按题号合并
  const [answerSheetOpen, setAnswerSheetOpen] = useState(false);
  const [answerSheetLoading, setAnswerSheetLoading] = useState(false);
  const [answerSheetSaving, setAnswerSheetSaving] = useState(false);
  const [answerSheetRows, setAnswerSheetRows] = useState<AnswerSheetRow[]>([]);
  const [answerSheetError, setAnswerSheetError] = useState("");
  // 识别列表「答题区框」→切题审查同款框编辑器：标记来源（确认保存后自动回识别列表）+ 落点页
  const boxEditReturnRef = useRef(false);
  const [boxEditTargetPage, setBoxEditTargetPage] = useState(0);
  const [manualLayoutStatus, setManualLayoutStatus] =
    useState<ReferenceLayoutStatus>({
      confirmed: false,
      reviewed_pages: [],
      stale_pages: [],
    });
  const [manualLayoutPages, setManualLayoutPages] = useState<
    ReferenceLayoutPage[]
  >([]);
  const [manualLayoutPrepareId, setManualLayoutPrepareId] = useState<
    string | null
  >(null);
  const [manualLayoutOpen, setManualLayoutOpen] = useState(false);
  const [manualLayoutPreparing, setManualLayoutPreparing] = useState(false);
  const [manualLayoutSaving, setManualLayoutSaving] = useState(false);
  // 答题卡（参照批改）：标准答案输入
  const [answerKeyText, setAnswerKeyText] = useState("");
  const [answerKeyImageFile, setAnswerKeyImageFile] = useState<File | null>(null);
  const [answerKeyImageName, setAnswerKeyImageName] = useState("");
  const [answerKeyLoaded, setAnswerKeyLoaded] = useState<
    Record<string, string> | null
  >(null);
  const [answerKeyDialogOpen, setAnswerKeyDialogOpen] = useState(false);
  const [answerKeySaving, setAnswerKeySaving] = useState(false);
  const answerKeyImageInputRef = useRef<HTMLInputElement>(null);
  // 原始试卷（含每题分值）：上传 → AI 识别分值 → 确认页逐题核对 → 回填切题计分规则
  const [originalPaperOpen, setOriginalPaperOpen] = useState(false);
  const [originalPaperUploading, setOriginalPaperUploading] = useState(false);
  const [originalPaperRecognizing, setOriginalPaperRecognizing] = useState(false);
  const [originalPaperName, setOriginalPaperName] = useState("");
  const [originalPaperScoreCount, setOriginalPaperScoreCount] = useState(0);
  const [originalPaperScoreItems, setOriginalPaperScoreItems] = useState<
    PaperScoreItem[]
  >([]);
  const [originalPaperScoreOpen, setOriginalPaperScoreOpen] = useState(false);
  const [originalPaperApplying, setOriginalPaperApplying] = useState(false);
  const originalPaperInputRef = useRef<HTMLInputElement>(null);
  const [gradingEngine, setGradingEngine] = useState<GradingEngine>("aliyun");
  // 进入答题卡（自主阅卷/参照批改）时自动回显已保存的标准答案，供判分时作参考答案
  useEffect(() => {
    if (!isManualEngine(gradingEngine) || !selectedFolder || answerKeyLoaded) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await getAnswerKey(selectedFolder);
        if (!cancelled && res?.ok && Object.keys(res.answers || {}).length > 0) {
          setAnswerKeyLoaded(res.answers);
          setAnswerKeyText(res.raw || "");
        }
      } catch {
        // 忽略回显失败
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [gradingEngine, selectedFolder, answerKeyLoaded]);
  const standardAnswer = useMemo(
    () =>
      standardAnswers.find((item) => item.page_no === 1) ??
      standardAnswers[0] ??
      null,
    [standardAnswers],
  );
  const [classStudents, setClassStudents] = useState<StudentInfo[]>([]);
  const [studentsLoading, setStudentsLoading] = useState(false);
  const [paperBoxCapacity, setPaperBoxCapacity] = useState(
    DEFAULT_PAPER_BOX_CAPACITY,
  );
  const [paperBoxSettingsOpen, setPaperBoxSettingsOpen] = useState(false);
  const [paperBoxCapacityDraft, setPaperBoxCapacityDraft] = useState(
    String(DEFAULT_PAPER_BOX_CAPACITY),
  );
  const [scanImportRunning, setScanImportRunning] = useState(false);
  /** 扫描导入错误状态（来自 getScanImportStatus 轮询） */
  const [scanError, setScanError] = useState(false);
  const [scanErrorMessage, setScanErrorMessage] = useState<string | null>(null);
  const [scanImportedCount, setScanImportedCount] = useState(0);
  /** 错误 toast 去重：只在 error 从无到有时弹一次 */
  const scanErrorToastShownRef = useRef(false);
  const [refLoading, setRefLoading] = useState(false);
  /** 当前一键批改任务 id，用于停止批改 */
  const [activeGradingJobId, setActiveGradingJobId] = useState<string | null>(
    null,
  );
  const [refProgress, setRefProgress] = useState<{
    total: number;
    completed: RefCompleted[];
    failed: Array<{ name: string; msg: string }>;
    currentName?: string | null;
  } | null>(null);
  /** 磁盘持久化的批改结果，与当前任务内存合并后用于「已批改」与详情 */
  const [gradingsPersisted, setGradingsPersisted] = useState<{
    completed: RefCompleted[];
    failed: Array<{ name: string; msg: string }>;
  } | null>(null);

  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [newFolderSubject, setNewFolderSubject] = useState("");
  const [newFolderHomeworkType, setNewFolderHomeworkType] = useState(
    HOMEWORK_TYPES[0],
  );
  const [createLoading, setCreateLoading] = useState(false);
  const [folderDeleteMode, setFolderDeleteMode] = useState(false);
  const [deletingFolderIds, setDeletingFolderIds] = useState<Set<string>>(
    new Set(),
  );
  const [deleteFolderDialogOpen, setDeleteFolderDialogOpen] = useState(false);
  const [deleteFolderPassword, setDeleteFolderPassword] = useState("");
  const [deleteFolderExecuting, setDeleteFolderExecuting] = useState(false);
  const [renameFolderDialogOpen, setRenameFolderDialogOpen] = useState(false);
  const [renameFolderTarget, setRenameFolderTarget] = useState<string | null>(
    null,
  );
  const [renameFolderNewName, setRenameFolderNewName] = useState("");
  const [renameFolderHomeworkType, setRenameFolderHomeworkType] = useState(
    HOMEWORK_TYPES[0],
  );
  const [renameFolderLoading, setRenameFolderLoading] = useState(false);
  const [renameFileDialogOpen, setRenameFileDialogOpen] = useState(false);
  const [renameFileTarget, setRenameFileTarget] = useState<{
    name: string;
  } | null>(null);
  const [renameFileNewName, setRenameFileNewName] = useState("");
  const [renameFileLoading, setRenameFileLoading] = useState(false);

  // ── 数据漫游：班级数据导出 / 导入 ──
  const [dataExporting, setDataExporting] = useState(false);
  const [dataImporting, setDataImporting] = useState(false);
  const [importResult, setImportResult] =
    useState<ClassDataImportResult | null>(null);
  const [importResultOpen, setImportResultOpen] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);
  const testPrintInputRef = useRef<HTMLInputElement>(null);

  const [zoomImageUrl, setZoomImageUrl] = useState<string | null>(null);
  /** 预览弹窗为学生试卷时记录文件名，用于单张批改；{t("grading.preview.altStdAnswer")}预览为 null */
  const [zoomStudentFilename, setZoomStudentFilename] = useState<string | null>(
    null,
  );
  const [zoomPreviewError, setZoomPreviewError] = useState(false);
  const [detailItem, setDetailItem] = useState<RefCompleted | null>(null);
  const [manualGradingItem, setManualGradingItem] =
    useState<RefCompleted | null>(null);
  const [manualPaperSaving, setManualPaperSaving] = useState(false);
  const [manualPaperPrinting, setManualPaperPrinting] = useState(false);
  const [detailShowOriginal, setDetailShowOriginal] = useState(false);
  // 屏幕预览「显示批注」开关（默认开）：开时优先显示带错因批注的卷面变体图
  const [previewWrongNotes, setPreviewWrongNotes] = useState(true);
  const [aiCorrectOpen, setAiCorrectOpen] = useState(false);
  const [aiCorrectSaving, setAiCorrectSaving] = useState(false);
  const [aiCorrections, setAiCorrections] = useState<
    Record<string, "对" | "错" | "未作答" | "半对">
  >({});
  const [aiQuestionNotes, setAiQuestionNotes] = useState<Record<string, string>>({});
  const [aiNoteSource, setAiNoteSource] = useState<Record<string, "ai" | "manual">>({});
  const [aiScores, setAiScores] = useState<Record<string, string>>({});
  const [aiPaperNote, setAiPaperNote] = useState("");
  const [aiPaperNoteSource, setAiPaperNoteSource] = useState<"ai" | "manual">("manual");
  const [aiSummaryLoading, setAiSummaryLoading] = useState(false);
  // 判错批注：questionKey → 批注；随 detailItem 同步，编辑/重生成走 wrong-annotation 接口
  const [wrongAnnotations, setWrongAnnotations] = useState<WrongAnnotationsMap>({});
  // 结构化扣分项：随 detailItem 同步；清分联动时本地清掉并在下次保存整体覆盖回写
  const [manualDeductions, setManualDeductions] = useState<DeductionItemsMap>({});
  const manualDeductionsRef = useRef<DeductionItemsMap>({});
  const manualDeductionsDirtyRef = useRef(false);
  const [wrongAnnoRegenerating, setWrongAnnoRegenerating] = useState<string | null>(null);
  const [essayResultEditOpen, setEssayResultEditOpen] = useState(false);
  const [essayResultDraft, setEssayResultDraft] = useState("");
  const [essayResultSaving, setEssayResultSaving] = useState(false);
  const [essayNoteOpen, setEssayNoteOpen] = useState(false);
  const [essayNoteDraft, setEssayNoteDraft] = useState("");
  const [essayNoteSaving, setEssayNoteSaving] = useState(false);

  const [manualGradeScores, setManualGradeScores] = useState<
    Record<string, string>
  >({});
  const [manualGradeSaving, setManualGradeSaving] = useState(false);
  const [manualEditingName, setManualEditingName] = useState<string | null>(
    null,
  );
  const [manualSwitching, setManualSwitching] = useState(false);
  const [manualClearConfirmOpen, setManualClearConfirmOpen] = useState(false);
  const [manualClearing, setManualClearing] = useState(false);

  const [deleteMode, setDeleteMode] = useState(false);
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteExecuting, setDeleteExecuting] = useState(false);
  const [printConfirmOpen, setPrintConfirmOpen] = useState(false);
  const [printSettingsOpen, setPrintSettingsOpen] = useState(false);
  const [selectGradeMode, setSelectGradeMode] = useState(false);
  const [selectedGradeIds, setSelectedGradeIds] = useState<Set<string>>(
    new Set(),
  );
  const [printBatchLoading, setPrintBatchLoading] = useState(false);
  const [exportPdfLoading, setExportPdfLoading] = useState(false);
  const [exportPdfOneLoading, setExportPdfOneLoading] = useState(false);
  const [browserPrintLoading, setBrowserPrintLoading] = useState(false);
  const [browserPrintOneLoading, setBrowserPrintOneLoading] = useState(false);
  const [rotatingFileName, setRotatingFileName] = useState<string | null>(null);
  const [testPrintLoading, setTestPrintLoading] = useState(false);
  const [testPrintOpen, setTestPrintOpen] = useState(false);
  const [testPrintPhase, setTestPrintPhase] = useState<
    "grading" | "printing" | "done" | "error"
  >("grading");
  const [testPrintResult, setTestPrintResult] = useState<string>("");
  const [testPrintError, setTestPrintError] = useState<string>("");
  const [activePrintJobId, setActivePrintJobId] = useState<string | null>(null);
  const [previewPaperBoxStudentId, setPreviewPaperBoxStudentId] = useState<
    string | null
  >(null);
  const [previewPaperBoxPageNo, setPreviewPaperBoxPageNo] = useState(1);
  const [previewPaperBoxShowOriginal, setPreviewPaperBoxShowOriginal] =
    useState(false);
  const [previewPaperBoxUploading, setPreviewPaperBoxUploading] =
    useState(false);
  const [previewPaperBoxDeleteOpen, setPreviewPaperBoxDeleteOpen] =
    useState(false);
  const [previewPaperBoxDeleting, setPreviewPaperBoxDeleting] = useState(false);
  const [paperBoxSlideDirection, setPaperBoxSlideDirection] = useState(0);
  const paperBoxUploadTargetPageRef = useRef(1);
  const [standardBoxOpen, setStandardBoxOpen] = useState(false);
  const [standardBoxPageNo, setStandardBoxPageNo] = useState(1);
  const [standardBoxUploading, setStandardBoxUploading] = useState(false);
  // 「上传学生试卷」批量上传进度（此前无任何进行中提示，多张大图时像没反应）
  const [studentUploading, setStudentUploading] = useState(false);
  const [studentUploadProgress, setStudentUploadProgress] = useState<{
    done: number;
    total: number;
  } | null>(null);
  const [standardBoxDeleteOpen, setStandardBoxDeleteOpen] = useState(false);
  const [standardBoxDeleting, setStandardBoxDeleting] = useState(false);
  const standardBoxUploadTargetPageRef = useRef(1);
  const [printOneLoading, setPrintOneLoading] = useState(false);
  const {
    selectedPrinter,
    setSelectedPrinter,
    printPaperSize,
    setPrintPaperSize,
    customPaperWidthMm,
    setCustomPaperWidthMm,
    customPaperHeightMm,
    setCustomPaperHeightMm,
    paperSourceId,
    setPaperSourceId,
    printMode,
    setPrintMode,
    printWrongNotes,
    setPrintWrongNotes,
    resolvePrinterName,
    getCustomPaperSetting,
  } = useGlobalPrintPrefs();
  const {
    printers,
    loading: printersLoading,
    refresh: refreshPrinters,
  } = usePrinters();

  const stdInputRef = useRef<HTMLInputElement>(null);
  const answerSheetInputRef = useRef<HTMLInputElement>(null);
  const standardBoxUploadInputRef = useRef<HTMLInputElement>(null);
  const studentInputRef = useRef<HTMLInputElement>(null);
  const paperBoxUploadInputRef = useRef<HTMLInputElement>(null);
  const manualAutosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const lastManualAutosaveKeyRef = useRef<string>("");
  const refGradePollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  // 自动补全「编辑批改」缺 blocks 的旧记录：job 防重 + 轮询计时器
  const autoBackfillJobRef = useRef<string | null>(null);
  const autoBackfillPollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const printBatchPollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  // loadFolderFiles 竞态守卫：每次调用自增，晚返回的慢请求发现序号过期即丢弃，避免覆盖新文件夹/引擎的数据
  const loadFolderFilesReqIdRef = useRef(0);
  const scanImportKnownFilesRef = useRef<Set<string>>(new Set());
  const scanAutoAssigningRef = useRef(false);
  const refGradeCancelledRef = useRef(false);
  const essayGradePollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const essayGradeCancelledRef = useRef(false);
  const [essayRubricOpen, setEssayRubricOpen] = useState(false);
  const [essayRubrics, setEssayRubrics] = useState<EssayRubric[]>([]);
  const [activeRubricId, setActiveRubricId] = useState<string | null>(null);
  const [dimensionDraft, setDimensionDraft] = useState<EssayDimension[] | null>(
    null,
  );
  const [dimensionSaving, setDimensionSaving] = useState(false);
  const [newRubricDialogOpen, setNewRubricDialogOpen] = useState(false);
  const [newRubricName, setNewRubricName] = useState("");
  const [newRubricLoading, setNewRubricLoading] = useState(false);
  const [rubricDeleteMode, setRubricDeleteMode] = useState(false);
  const [deletingRubricIds, setDeletingRubricIds] = useState<Set<string>>(
    new Set(),
  );
  const [deleteRubricConfirmOpen, setDeleteRubricConfirmOpen] = useState(false);
  const [deleteRubricExecuting, setDeleteRubricExecuting] = useState(false);

  // {t("grading.action.scoringSettings")}弹窗
  const [scoringDialogOpen, setScoringDialogOpen] = useState(false);
  const [scoringConfig, setScoringConfig] = useState<Record<string, number>>(
    {},
  );
  const [scoringSaving, setScoringSaving] = useState(false);
  const [scoringApplying, setScoringApplying] = useState(false);
  const [scoringAutoLoading, setScoringAutoLoading] = useState(false);
  // AI 识别出的整卷满分（卷面满分），用于统分界面展示与 X/满分 口径
  const [fullScore, setFullScore] = useState<number | null>(null);
  const [questionStructure, setQuestionStructure] =
    useState<QuestionStructure | null>(null);
  // AI 识别出的大题总分（一/二/三/四…）与题序，用于统分界面按「大题+小题」分组展示
  const [majorScores, setMajorScores] = useState<Record<string, number>>({});
  const [majorOrder, setMajorOrder] = useState<string[]>([]);
  const [majorTitles, setMajorTitles] = useState<Record<string, string>>({});
  // 大题 → 小题（题号 + 分值）清单，供统分界面「大题 + 小题分数框」展示（不放题干）
  const [paperSubs, setPaperSubs] = useState<
    Record<string, { num: string; score: number }[]>
  >({});
  // 打开统分设置面板时自动触发一次 AI 分配分值的防重入标记
  const autoScoringTriggeredRef = useRef(false);
  // 发起第三方 AI 分析前的隐私告知
  const [noticePending, setNoticePending] = useState<(() => void) | null>(null);

  // ---- 一键编排（扫描→批阅→打印串行，步骤可开关）----
  const [enabledSteps, setEnabledSteps] = useState<
    Record<OrchestrateStep, boolean>
  >({ scan: true, grade: true, print: true });
  const [orchestration, setOrchestration] = useState<OrchestrationStatus>({
    phase: "idle",
  });
  /** 批阅前快照的勾选文件名（null=全量），批阅会清空勾选，故提前快照 */
  const orchestrationFilenamesRef = useRef<string[] | null>(null);
  /** 编排是否在运行（非终态），用于 onDone 防误推进 */
  const orchestrationActiveRef = useRef(false);
  /** 批阅步是否已真正启动（用于隐私弹窗被取消时中止编排） */
  const orchestrationGradeStartedRef = useRef(false);
  /** 编排代际令牌：每次启动新编排自增，旧编排的轮询 onDone 据此丢弃，避免游离回调推进新状态机 */
  const orchestrationGradeGenRef = useRef(0);
  const orchestrationPrintGenRef = useRef(0);
  /** 供编排异步流程调用最新闭包的 handleBatchPrint（避免闭包陈旧读旧勾选） */
  const latestHandleBatchPrintRef = useRef<
    (opts?: { onDone?: (st: any) => void }) => void
  >(() => {});
  /** 供编排打印步读取最新可打印性（避免闭包陈旧） */
  const checkOrchestrPrintableRef = useRef<() => boolean>(() => false);
  /** 编排中止守卫：记录 view/selectedFolder/gradingEngine，变化时中止编排 */
  const orchestrationAbortGuardRef = useRef({
    view,
    selectedFolder,
    gradingEngine,
  });

  const getStoredJobId = (folder: string): string | null => {
    try {
      return localStorage.getItem(`${REF_JOB_STORAGE_PREFIX}${folder}`) || null;
    } catch {
      return null;
    }
  };

  const getStoredEssayJobId = (folder: string): string | null => {
    try {
      return (
        localStorage.getItem(`${ESSAY_JOB_STORAGE_PREFIX}${folder}`) || null
      );
    } catch {
      return null;
    }
  };

  const setStoredJobId = (folder: string, jobId: string | null) => {
    try {
      const key = `${REF_JOB_STORAGE_PREFIX}${folder}`;
      if (jobId) localStorage.setItem(key, jobId);
      else localStorage.removeItem(key);
    } catch {
      //
    }
  };

  const setStoredEssayJobId = (folder: string, jobId: string | null) => {
    try {
      const key = `${ESSAY_JOB_STORAGE_PREFIX}${folder}`;
      if (jobId) localStorage.setItem(key, jobId);
      else localStorage.removeItem(key);
    } catch {
      //
    }
  };
  const getStoredFolderPrefs = (
    folder: string,
  ): {
    engine?: GradingEngine;
    active_rubric_id?: string;
    scoring_config?: Record<string, number>;
    paper_box_capacity?: number;
  } => {
    try {
      const raw = localStorage.getItem(
        `${FOLDER_PREFS_STORAGE_PREFIX}${folder}`,
      );
      if (!raw) return {};
      const j = JSON.parse(raw);
      const engine =
        j?.engine === "aliyun" ||
        j?.engine === "baidu" ||
        j?.engine === "essay" ||
        j?.engine === "smart_ref" ||
        j?.engine === "manual" ||
        j?.engine === "manual_reference" ||
        j?.engine === "manual_paper"
          ? (j.engine as GradingEngine)
          : undefined;
      const active_rubric_id =
        typeof j?.active_rubric_id === "string"
          ? j.active_rubric_id
          : undefined;
      const scoring_config =
        j?.scoring_config &&
        typeof j.scoring_config === "object" &&
        !Array.isArray(j.scoring_config)
          ? Object.entries(j.scoring_config).reduce<Record<string, number>>(
              (acc, [key, value]) => {
                const num =
                  typeof value === "number"
                    ? value
                    : parseFloat(String(value ?? ""));
                acc[key] = Number.isFinite(num) ? num : 0;
                return acc;
              },
              {},
            )
          : undefined;
      const rawCapacity = Number(j?.paper_box_capacity);
      const paper_box_capacity = Number.isFinite(rawCapacity)
        ? Math.min(MAX_PAPER_BOX_CAPACITY, Math.max(1, Math.floor(rawCapacity)))
        : undefined;
      return {
        engine,
        active_rubric_id,
        scoring_config,
        paper_box_capacity,
      };
    } catch {
      return {};
    }
  };

  const setStoredFolderPrefs = (
    folder: string,
    prefs: {
      engine?: GradingEngine;
      active_rubric_id?: string;
      scoring_config?: Record<string, number>;
      paper_box_capacity?: number;
    },
  ) => {
    try {
      const key = `${FOLDER_PREFS_STORAGE_PREFIX}${folder}`;
      localStorage.setItem(key, JSON.stringify(prefs));
    } catch {
      //
    }
  };

  const clearRefGradePollTimer = useCallback(() => {
    if (refGradePollTimerRef.current) {
      clearTimeout(refGradePollTimerRef.current);
      refGradePollTimerRef.current = null;
    }
  }, []);

  const clearEssayGradePollTimer = useCallback(() => {
    if (essayGradePollTimerRef.current) {
      clearTimeout(essayGradePollTimerRef.current);
      essayGradePollTimerRef.current = null;
    }
  }, []);

  const clearPrintBatchPollTimer = useCallback(() => {
    if (printBatchPollTimerRef.current) {
      clearTimeout(printBatchPollTimerRef.current);
      printBatchPollTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      if (refGradePollTimerRef.current)
        clearTimeout(refGradePollTimerRef.current);
      if (essayGradePollTimerRef.current)
        clearTimeout(essayGradePollTimerRef.current);
      if (printBatchPollTimerRef.current)
        clearTimeout(printBatchPollTimerRef.current);
      if (manualAutosaveTimerRef.current)
        clearTimeout(manualAutosaveTimerRef.current);
      if (autoBackfillPollTimerRef.current)
        clearTimeout(autoBackfillPollTimerRef.current);
    };
  }, []);

  const startRefGradePolling = useCallback(
    (
      folderName: string,
      jobId: string,
      opts?: { singleFilename?: string },
      onDone?: (st: any) => void,
    ) => {
      refGradeCancelledRef.current = false;
      clearRefGradePollTimer();
      setActiveGradingJobId(jobId);
      setRefLoading(true);
      // total<=0 连续无进展次数兜底（避免状态机卡死）
      let refZeroTotalCount = 0;

      const poll = async () => {
        if (refGradeCancelledRef.current) return;
        try {
          const st = await referenceGradeStatus(folderName, jobId);
          if (st.ok) {
            setRefProgress({
              total: st.total,
              completed: st.completed || [],
              failed: st.failed || [],
              currentName: st.current_name || null,
            });
            const done =
              !!st.done ||
              (st.total > 0 &&
                (st.completed?.length || 0) + (st.failed?.length || 0) >=
                  st.total);
            if (done) {
              setRefLoading(false);
              setActiveGradingJobId(null);
              setStoredJobId(folderName, null);
              refGradePollTimerRef.current = null;
              const lastCompleted = (st.completed || []) as RefCompleted[];
              const lastFailed = st.failed || [];
              fetchGradingHistory(folderName, gradingEngine)
                .then((h) => {
                  if (h.ok) {
                    setGradingsPersisted({
                      completed: mergeCompletedLists(
                        h.completed as RefCompleted[],
                        lastCompleted,
                      ),
                      failed: h.failed?.length ? h.failed : lastFailed,
                    });
                  } else if (lastCompleted.length) {
                    setGradingsPersisted({
                      completed: mergeCompletedLists(lastCompleted),
                      failed: lastFailed,
                    });
                  }
                })
                .catch(() => {});
              setRefProgress((prev) =>
                prev
                  ? {
                      ...prev,
                      total: st.total,
                      completed: mergeCompletedLists(
                        prev.completed,
                        lastCompleted,
                      ),
                      failed: lastFailed.length ? lastFailed : prev.failed,
                      currentName: null,
                    }
                  : {
                      total: st.total,
                      completed: mergeCompletedLists(lastCompleted),
                      failed: lastFailed,
                      currentName: null,
                    },
              );
              if (opts?.singleFilename) {
                setZoomImageUrl(null);
                setZoomStudentFilename(null);
                const ok = (st.completed || []).find(
                  (c) => c.name === opts.singleFilename,
                );
                const fail = (st.failed || []).find(
                  (f) => f.name === opts.singleFilename,
                );
                if (ok) setDetailItem(ok as RefCompleted);
                else if (fail)
                  toast.error(fail.msg || t("grading.toast.gradeFailed"));
              } else if (lastFailed.length) {
                toast.error(
                  lastFailed[0]?.msg || t("grading.toast.gradeFailed"),
                );
              } else if (
                (st.total || 0) <= 0 &&
                !lastCompleted.length &&
                !lastFailed.length
              ) {
                toast.error(t("grading.toast.noPapersToRegrade"));
              }
              try {
                onDone?.(st);
              } catch {
                // 回调异常不影响原收尾逻辑
              }
              return;
            }
            // total<=0 兜底：连续 5 次无任何进展视为终态，避免状态机卡死
            if ((st.total || 0) > 0) {
              refZeroTotalCount = 0;
            }
            if (
              (st.total || 0) <= 0 &&
              (st.completed?.length || 0) === 0 &&
              (st.failed?.length || 0) === 0
            ) {
              refZeroTotalCount += 1;
              if (refZeroTotalCount >= 5) {
                setRefLoading(false);
                setActiveGradingJobId(null);
                setStoredJobId(folderName, null);
                refGradePollTimerRef.current = null;
                toast.error(t("grading.toast.noPapersToRegrade"));
                fetchGradingHistory(folderName, gradingEngine)
                  .then((h) => {
                    if (h.ok) {
                      setGradingsPersisted({
                        completed: mergeCompletedLists(
                          h.completed as RefCompleted[],
                          [],
                        ),
                        failed: h.failed || [],
                      });
                    }
                  })
                  .catch(() => {});
                try {
                  onDone?.(st);
                } catch {
                  // 回调异常不影响原收尾逻辑
                }
                return;
              }
            }
          }
        } catch (e: any) {
          const msg = String(e?.message || "");
          if (msg.includes("任务不存在") || msg.includes("404")) {
            setRefLoading(false);
            setActiveGradingJobId(null);
            setStoredJobId(folderName, null);
            refGradePollTimerRef.current = null;
            return;
          }
        }
        if (refGradeCancelledRef.current) return;
        refGradePollTimerRef.current = setTimeout(poll, POLL_INTERVAL);
      };
      poll();
    },
    [clearRefGradePollTimer, gradingEngine, t],
  );

  const startEssayGradePolling = useCallback(
    (
      folderName: string,
      jobId: string,
      opts?: { singleFilename?: string },
      onDone?: (st: any) => void,
    ) => {
      essayGradeCancelledRef.current = false;
      clearEssayGradePollTimer();
      setActiveGradingJobId(jobId);
      setRefLoading(true);

      const poll = async () => {
        if (essayGradeCancelledRef.current) return;
        try {
          const st = await essayGradeStatus(folderName, jobId);
          if (st.ok) {
            // 复用 refProgress 的展示结构（completed/failed/total/currentName）
            setRefProgress({
              total: st.total,
              completed: (st.completed || []) as any,
              failed: st.failed || [],
              currentName: st.current_name || null,
            });
            if (
              (st.total || 0) <= 0 &&
              (st.completed?.length || 0) === 0 &&
              (st.failed?.length || 0) === 0
            ) {
              setRefLoading(false);
              setActiveGradingJobId(null);
              setStoredEssayJobId(folderName, null);
              essayGradePollTimerRef.current = null;
              toast.error(t("grading.toast.noPapersToRegrade"));
              fetchEssayGradingHistory(folderName)
                .then((h) => {
                  if (h.ok) {
                    setGradingsPersisted({
                      completed: (h.completed || []) as any,
                      failed: h.failed || [],
                    });
                  }
                })
                .catch(() => {});
              try {
                onDone?.(st);
              } catch {
                // 回调异常不影响原收尾逻辑
              }
              return;
            }
            const done =
              !!st.done ||
              (st.completed?.length || 0) + (st.failed?.length || 0) >=
                st.total;
            if (done) {
              setRefLoading(false);
              setActiveGradingJobId(null);
              setStoredEssayJobId(folderName, null);
              essayGradePollTimerRef.current = null;
              fetchEssayGradingHistory(folderName)
                .then((h) => {
                  if (h.ok) {
                    setGradingsPersisted({
                      completed: (h.completed || []) as any,
                      failed: h.failed || [],
                    });
                  }
                })
                .catch(() => {});
              notifyAutoReportCheck();
              if (opts?.singleFilename) {
                setZoomImageUrl(null);
                setZoomStudentFilename(null);
                const ok = (st.completed || []).find(
                  (c: any) => c.name === opts.singleFilename,
                );
                const fail = (st.failed || []).find(
                  (f) => f.name === opts.singleFilename,
                );
                if (ok) setDetailItem(ok as any);
                else if (fail)
                  toast.error(fail.msg || t("grading.toast.gradeFailed"));
              }
              try {
                onDone?.(st);
              } catch {
                // 回调异常不影响原收尾逻辑
              }
              return;
            }
          }
        } catch (e: any) {
          const msg = String(e?.message || "");
          if (msg.includes("任务不存在") || msg.includes("404")) {
            setRefLoading(false);
            setActiveGradingJobId(null);
            setStoredEssayJobId(folderName, null);
            return;
          }
        }
        essayGradePollTimerRef.current = setTimeout(poll, 1200);
      };
      poll();
    },
    [clearEssayGradePollTimer],
  );

  useEffect(() => {
    setDetailShowOriginal(false);
    if (manualAutosaveTimerRef.current) {
      clearTimeout(manualAutosaveTimerRef.current);
      manualAutosaveTimerRef.current = null;
    }
    if (detailItem && isManualEngine(gradingEngine)) {
      try {
        const res = JSON.parse(detailItem.result || "{}");
        const existingScores = res.scores || {};
        setManualGradeScores(existingScores);
        lastManualAutosaveKeyRef.current = `${detailItem.name}::${serializeManualScores(existingScores)}`;
      } catch (e) {
        setManualGradeScores({});
        lastManualAutosaveKeyRef.current = `${detailItem.name}::{}`;
      }
    } else {
      setManualGradeScores({});
      lastManualAutosaveKeyRef.current = "";
    }
  }, [detailItem?.name, detailItem?.result, gradingEngine]);

  useEffect(() => {
    setZoomPreviewError(false);
  }, [zoomImageUrl]);

  const loadFolders = useCallback(async () => {
    if (!selectedClass) {
      setFolders([]);
      setFolderMeta({});
      return;
    }
    try {
      const res = await listFolders(selectedClass || undefined);
      if (res.ok) {
        setFolders(res.folders || []);
        setFolderMeta(res.meta || {});
      }
    } catch (e) {
      toast.error(t("grading.start.loadFoldersFailed"));
    }
  }, [selectedClass]);

  // 自动补全：检测到缺逐题数据(blocks)的智能/参照批改记录时，静默重批补齐，让「编辑批改」可用。
  // 只补缺 blocks 的那几张，不清空、不重批已有逐题数据的记录。
  const autoBackfillIfNeeded = useCallback(
    (folderName: string, engine: GradingEngine, completed: RefCompleted[]) => {
      if (
        engine !== "baidu" &&
        engine !== "smart_ref" &&
        engine !== "aliyun"
      )
        return;
      const missing = completed.filter((it) => !it?.blocks?.length);
      if (!missing.length) return;
      if (autoBackfillJobRef.current) return; // 已在补全中，防重
      backfillBlocks(folderName, engine)
        .then((res) => {
          if (!res.ok || !res.job_id) return;
          autoBackfillJobRef.current = res.job_id;
          const poll = async () => {
            try {
              const st = await referenceGradeStatus(folderName, res.job_id!);
              const done =
                !!st.done ||
                (st.total > 0 &&
                  (st.completed?.length || 0) + (st.failed?.length || 0) >=
                    st.total);
              if (done) {
                autoBackfillJobRef.current = null;
                autoBackfillPollTimerRef.current = null;
                // 补完刷新历史（此时缺 blocks 的记录已被重批补齐）
                fetchGradingHistory(folderName, engine)
                  .then((h) => {
                    if (h.ok) {
                      setGradingsPersisted({
                        completed: (h.completed || []) as RefCompleted[],
                        failed: h.failed || [],
                      });
                    }
                  })
                  .catch(() => {});
                return;
              }
            } catch (e: any) {
              const msg = String(e?.message || "");
              if (msg.includes("任务不存在") || msg.includes("404")) {
                autoBackfillJobRef.current = null;
                autoBackfillPollTimerRef.current = null;
                return;
              }
            }
            autoBackfillPollTimerRef.current = setTimeout(poll, POLL_INTERVAL);
          };
          poll();
        })
        .catch(() => {});
    },
    [],
  );

  const loadFolderFiles = useCallback(
    async (name: string, engine?: GradingEngine) => {
      const requestId = ++loadFolderFilesReqIdRef.current;
      try {
        const currentEngine = engine || gradingEngine;
        const historyEngine = manualHistoryEngine(currentEngine);
        const [res, hist] = await Promise.all([
          listFolderFiles(name),
          currentEngine === "essay"
            ? fetchEssayGradingHistory(name)
            : fetchGradingHistory(name, historyEngine),
        ]);
        // 竞态守卫：快速切换文件夹/引擎时，晚返回的慢请求序号已过期，直接丢弃，避免覆盖新数据
        if (requestId !== loadFolderFilesReqIdRef.current) return;
        if (res.ok) {
          setFolderFiles(res.files || []);
          setStandardAnswers(
            (res.standard_answers?.length
              ? res.standard_answers
              : res.standard_answer
                ? [res.standard_answer]
                : []) as StandardAnswerItem[],
          );
          setReferenceLayoutStatus(
            res.reference_layout || {
              confirmed: false,
              reviewed_pages: [],
              stale_pages: [],
            },
          );
          setManualLayoutStatus(
            res.manual_layout || {
              confirmed: false,
              reviewed_pages: [],
              stale_pages: [],
            },
          );
        }
        if (hist.ok) {
          setGradingsPersisted({
            completed: (hist.completed || []) as RefCompleted[],
            failed: hist.failed || [],
          });
          const localPrefs = getStoredFolderPrefs(name);
          const localScoring = localPrefs.scoring_config;
          setScoringConfig(
            (currentEngine === "baidu" || currentEngine === "aliyun")
              ? localScoring || (hist as any).scoring_config || {}
              : {},
          );
          const histFullScore = (hist as any).full_score;
          setFullScore(
            typeof histFullScore === "number" ? histFullScore : null,
          );
          setQuestionStructure(
            (hist as any).question_structure || null,
          );
          const histMajorScores = (hist as any).major_scores;
          setMajorScores(
            histMajorScores && typeof histMajorScores === "object"
              ? histMajorScores
              : {},
          );
          const histMajorOrder = (hist as any).major_order;
          setMajorOrder(Array.isArray(histMajorOrder) ? histMajorOrder : []);
          const histMajorTitles = (hist as any).major_titles;
          setMajorTitles(
            histMajorTitles && typeof histMajorTitles === "object"
              ? histMajorTitles
              : {},
          );
          const histPaperSubs = (hist as any).paper_subs;
          setPaperSubs(
            histPaperSubs && typeof histPaperSubs === "object"
              ? histPaperSubs
              : {},
          );
          // 自动补全：缺逐题数据(blocks)的智能/参照批改记录，静默重批补齐，让「编辑批改」按钮出现
          autoBackfillIfNeeded(
            name,
            currentEngine,
            (hist.completed || []) as RefCompleted[],
          );
        } else {
          setGradingsPersisted({ completed: [], failed: [] });
          const localPrefs = getStoredFolderPrefs(name);
          setScoringConfig(
            (currentEngine === "baidu" || currentEngine === "aliyun") ? localPrefs.scoring_config || {} : {},
          );
          setFullScore(null);
          setQuestionStructure(null);
          setMajorScores({});
          setMajorOrder([]);
          setMajorTitles({});
        }
      } catch (e) {
        if (requestId !== loadFolderFilesReqIdRef.current) return;
        toast.error(t("grading.start.loadFilesFailed"));
      }
    },
    [gradingEngine, autoBackfillIfNeeded],
  );

  // 切到作文批改或其他模式时，重新加载对应的持久化记录（与其他模式隔离）
  useEffect(() => {
    if (view !== "folder" || !selectedFolder) {
      // 离开文件夹视图：作废所有在途加载，防止慢请求晚返回污染下次进入时的状态
      loadFolderFilesReqIdRef.current += 1;
      return;
    }
    setRefProgress(null);
    setDetailItem(null);
    loadFolderFiles(selectedFolder, gradingEngine);
  }, [view, selectedFolder, gradingEngine, loadFolderFiles]);

  useEffect(() => {
    loadFolders();
  }, [loadFolders]);

  useEffect(() => {
    if (!selectedClass) {
      setClassStudents([]);
      return;
    }
    let cancelled = false;
    setStudentsLoading(true);
    listStudentsByClass(selectedClass)
      .then((rows) => {
        if (!cancelled) setClassStudents(rows || []);
      })
      .catch(() => {
        if (!cancelled) {
          setClassStudents([]);
          toast.error(t("grading.start.loadStudentsFailed"));
        }
      })
      .finally(() => {
        if (!cancelled) setStudentsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedClass]);

  useEffect(() => {
    if (view !== "folder" || (gradingEngine !== "baidu" && gradingEngine !== "aliyun")) {
      setScoringDialogOpen(false);
    }
  }, [gradingEngine, view, selectedFolder]);

  // 仅当用户真正「切换」班级时才退出文件夹视图回到列表；
  // 首次挂载不重置，避免盖掉 ?folder= 深链（从批改历史点进来）打开的文件夹。
  const prevSelectedClassRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    const prev = prevSelectedClassRef.current;
    prevSelectedClassRef.current = selectedClass;
    if (prev === undefined) return; // 首次挂载：跳过，保留深链文件夹
    setView("list");
    setSelectedFolder(null);
    setFolderFiles([]);
    setStandardAnswers([]);
    setReferenceLayoutStatus({
      confirmed: false,
      reviewed_pages: [],
      stale_pages: [],
    });
    setReferenceLayoutPages([]);
    setReferenceLayoutPrepareId(null);
    setReferenceLayoutOpen(false);
    setGradingsPersisted(null);
    setRefProgress(null);
    setRefLoading(false);
    setActiveGradingJobId(null);
    setDetailItem(null);
    setZoomImageUrl(null);
    setZoomStudentFilename(null);
  }, [selectedClass]);

  useEffect(() => {
    if (view === "folder") void refreshPrinters();
  }, [view, refreshPrinters]);

  const openPrintSettings = async () => {
    setPrintSettingsOpen(true);
    await refreshPrinters();
  };
  useEffect(() => {
    if (view !== "folder" || !selectedFolder) return;
    const prefs = getStoredFolderPrefs(selectedFolder);
    // 匿名批改（baidu 智能模型批改）已下线：历史偏好若为 baidu，回退到参照答案批改
    if (prefs.engine) setGradingEngine(prefs.engine === "baidu" ? "aliyun" : prefs.engine);
    if (typeof prefs.active_rubric_id === "string")
      setActiveRubricId(prefs.active_rubric_id);
    else setActiveRubricId(null);
    const capacity = prefs.paper_box_capacity || DEFAULT_PAPER_BOX_CAPACITY;
    setPaperBoxCapacity(capacity);
    setPaperBoxCapacityDraft(String(capacity));
  }, [view, selectedFolder]);

  // 在文件夹内切换选项时持久化（依赖不含 selectedFolder，避免切换文件夹瞬间用旧值覆盖新文件夹的存储）
  useEffect(() => {
    if (view !== "folder" || !selectedFolder) return;
    setStoredFolderPrefs(selectedFolder, {
      engine: gradingEngine,
      active_rubric_id: activeRubricId || undefined,
      scoring_config: getStoredFolderPrefs(selectedFolder).scoring_config,
      paper_box_capacity:
        getStoredFolderPrefs(selectedFolder).paper_box_capacity,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- selectedFolder 仅作写入目标，切换文件夹由恢复 effect 更新状态后再因状态变化落盘
  }, [view, gradingEngine, activeRubricId]);

  useEffect(() => {
    if (view !== "folder" || !selectedFolder || (gradingEngine !== "baidu" && gradingEngine !== "aliyun"))
      return;
    const existing = getStoredFolderPrefs(selectedFolder);
    setStoredFolderPrefs(selectedFolder, {
      engine: existing.engine ?? gradingEngine,
      active_rubric_id: existing.active_rubric_id,
      scoring_config: scoringConfig,
      paper_box_capacity: existing.paper_box_capacity,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, selectedFolder, gradingEngine, scoringConfig]);

  // 返回/切换界面后，任务仍在后端继续；重新进入文件夹时自动恢复轮询与进度展示
  useEffect(() => {
    if (view !== "folder" || !selectedFolder) return;
    if (refLoading) return;
    if (activeGradingJobId) return;
    const jid = getStoredJobId(selectedFolder);
    if (jid) startRefGradePolling(selectedFolder, jid);
  }, [
    view,
    selectedFolder,
    refLoading,
    activeGradingJobId,
    startRefGradePolling,
  ]);

  // 加载作文批改规则
  const loadEssayRubrics = useCallback(async () => {
    try {
      const list = await getEssayRubrics();
      setEssayRubrics(list);
      // 如果没有选中的规则，但列表有数据，默认选中第一个
      if (list.length > 0 && !activeRubricId) {
        setActiveRubricId(list[0].id);
      }
    } catch (e) {
      toast.error(t("grading.toast.loadRubricsFailed"));
    }
  }, [activeRubricId]);

  useEffect(() => {
    if (gradingEngine === "essay") {
      loadEssayRubrics();
    }
  }, [gradingEngine, loadEssayRubrics]);

  const activeRubricForDraft = useMemo(
    () =>
      activeRubricId ? essayRubrics.find((r) => r.id === activeRubricId) : null,
    [activeRubricId, essayRubrics],
  );

  /** 评分维度展示用：以规则已保存的 dimensions_json 为准 */
  const rubricDimensions = useMemo<EssayDimension[]>(
    () => parseEssayDimensions(activeRubricForDraft?.dimensions_json),
    [activeRubricForDraft],
  );

  /** 维度编辑草稿：弹窗打开/切换规则时从规则解析（兜底默认五维） */
  const currentDimensions = useMemo<EssayDimension[]>(
    () =>
      dimensionDraft ??
      parseEssayDimensions(activeRubricForDraft?.dimensions_json),
    [dimensionDraft, activeRubricForDraft],
  );

  // 打开 rubric 弹窗 / 切换规则时，把 dimensions_json 解析进编辑草稿
  useEffect(() => {
    if (!essayRubricOpen) return;
    setDimensionDraft(
      parseEssayDimensions(activeRubricForDraft?.dimensions_json),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅在弹窗打开/切换规则时同步草稿
  }, [essayRubricOpen, activeRubricId]);

  const handleDimensionsChange = useCallback(
    (dims: EssayDimension[]) => {
      setDimensionDraft(dims);
      // 同步写入 essayRubrics 状态的 dimensions_json，保证任何字段 blur 持久化时一并带上
      setEssayRubrics((prev) =>
        prev.map((r) =>
          r.id === activeRubricId
            ? {
                ...r,
                dimensions_json: dims.length > 0 ? JSON.stringify(dims) : null,
              }
            : r,
        ),
      );
    },
    [activeRubricId],
  );

  const handleSaveDimensions = useCallback(async () => {
    if (!activeRubricId) return;
    const dims =
      dimensionDraft ??
      parseEssayDimensions(activeRubricForDraft?.dimensions_json);
    const nextRubric = {
      ...(activeRubricForDraft || {}),
      dimensions_json: dims.length > 0 ? JSON.stringify(dims) : null,
    };
    setDimensionSaving(true);
    try {
      await updateEssayRubric(
        activeRubricId,
        activeRubricForDraft?.content || "",
        undefined,
        nextRubric,
      );
      await loadEssayRubrics();
      toast.success(t("grading.dimension.saved"));
    } catch (e: any) {
      toast.error(e?.message || t("grading.dimension.saveFailed"));
    } finally {
      setDimensionSaving(false);
    }
  }, [
    activeRubricId,
    dimensionDraft,
    activeRubricForDraft,
    loadEssayRubrics,
    t,
  ]);

  const handleSaveEssayScore = useCallback(
    async (payload: EssayScorePayload) => {
      if (!selectedFolder) return;
      const res = await saveEssayScore(selectedFolder, payload);
      if (!res.ok) {
        throw new Error(res.msg || t("grading.dimension.saveFailed"));
      }
      const updated = res.completed;
      if (updated) {
        setGradingsPersisted((prev) =>
          prev
            ? {
                ...prev,
                completed: (prev.completed || []).map((c) =>
                  c.name === updated.name ? { ...c, ...updated } : c,
                ),
              }
            : prev,
        );
        setRefProgress((prev) =>
          prev
            ? {
                ...prev,
                completed: (prev.completed || []).map((c) =>
                  c.name === updated.name ? { ...c, ...updated } : c,
                ),
              }
            : prev,
        );
        setDetailItem((prev) =>
          prev?.name === updated.name ? { ...prev, ...updated } : prev,
        );
      }
      toast.success(t("grading.dimension.saved"));
    },
    [selectedFolder, t],
  );

  const openEssayResultEdit = useCallback(() => {
    if (!detailItem?.name) return;
    // 隐藏标签只用于程序识别分数，编辑框里不展示给老师
    const clean = (detailItem.result || "")
      .replace(/<essay_score>[\s\S]*?<\/essay_score>/g, "")
      .replace(/<essay_dimensions>[\s\S]*?<\/essay_dimensions>/g, "")
      .trim();
    setEssayResultDraft(clean);
    setEssayResultEditOpen(true);
  }, [detailItem?.name, detailItem?.result]);

  const handleSaveEssayResult = useCallback(async () => {
    if (!selectedFolder || !detailItem?.name) return;
    const text = (essayResultDraft || "").trim();
    if (!text) {
      toast.error(t("grading.essay.resultEmpty", undefined, "批改文案不能为空"));
      return;
    }
    setEssayResultSaving(true);
    try {
      const res = await saveEssayResult(selectedFolder, {
        filename: detailItem.name,
        result: text,
      });
      if (!res.ok) {
        throw new Error(res.msg || t("grading.dimension.saveFailed"));
      }
      const updated = res.completed;
      if (updated) {
        setGradingsPersisted((prev) =>
          prev
            ? {
                ...prev,
                completed: (prev.completed || []).map((c) =>
                  c.name === updated.name ? { ...c, ...updated } : c,
                ),
              }
            : prev,
        );
        setRefProgress((prev) =>
          prev
            ? {
                ...prev,
                completed: (prev.completed || []).map((c) =>
                  c.name === updated.name ? { ...c, ...updated } : c,
                ),
              }
            : prev,
        );
        setDetailItem((prev) =>
          prev?.name === updated.name ? { ...prev, ...updated } : prev,
        );
      }
      setEssayResultEditOpen(false);
      toast.success(t("grading.essay.resultSaved", undefined, "批改文案已保存"));
    } catch (e: any) {
      toast.error(e?.message || t("grading.dimension.saveFailed"));
    } finally {
      setEssayResultSaving(false);
    }
  }, [selectedFolder, detailItem?.name, essayResultDraft, t]);

  const openEssayNoteEdit = useCallback(() => {
    if (!detailItem?.name) return;
    setEssayNoteDraft(detailItem.paper_note ?? "");
    setEssayNoteOpen(true);
  }, [detailItem?.name, detailItem?.paper_note]);

  const handleSaveEssayNote = useCallback(async () => {
    if (!selectedFolder || !detailItem?.name) return;
    setEssayNoteSaving(true);
    try {
      const res = await saveEssayNote(
        selectedFolder,
        detailItem.name,
        (essayNoteDraft || "").trim(),
      );
      if (!res.ok || !res.item) {
        throw new Error(res.message || "保存失败");
      }
      const bust = (url?: string) =>
        url ? `${url}${url.includes("?") ? "&" : "?"}v=${Date.now()}` : url;
      const updated = {
        ...res.item,
        image_annotated: bust(res.item.image_annotated),
        image_marks_only: bust(res.item.image_marks_only),
        image_original: bust(res.item.image_original),
      };
      setDetailItem((prev) =>
        prev?.name === updated.name ? { ...prev, ...updated } : prev,
      );
      setEssayNoteOpen(false);
      toast.success("老师总评已保存");
    } catch (e: any) {
      toast.error(e?.message || "保存失败");
    } finally {
      setEssayNoteSaving(false);
    }
  }, [selectedFolder, detailItem?.name, essayNoteDraft]);

  // 作文批改：重新进入文件夹时恢复轮询
  useEffect(() => {
    if (view !== "folder" || !selectedFolder) return;
    if (refLoading) return;
    if (activeGradingJobId) return;
    if (gradingEngine !== "essay") return;
    const jid = getStoredEssayJobId(selectedFolder);
    if (jid) startEssayGradePolling(selectedFolder, jid);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- startEssayGradePolling 定义在下方，同 startRefGradePolling 结构一致
  }, [view, selectedFolder, refLoading, activeGradingJobId, gradingEngine]);

  useEffect(() => {
    if (view !== "folder" || !selectedFolder) return;
    const applyStatus = (
      res: Awaited<ReturnType<typeof getScanImportStatus>>,
    ) => {
      if (res.ok && res.running && res.folder_name === selectedFolder)
        setScanImportRunning(true);
      else setScanImportRunning(false);
      if (res.ok && res.folder_name === selectedFolder && res.error) {
        const msg = res.error_message || t("grading.scan.error");
        setScanError(true);
        setScanErrorMessage(msg);
        if (!scanErrorToastShownRef.current) {
          scanErrorToastShownRef.current = true;
          toast.error(msg);
        }
      } else {
        setScanError(false);
        setScanErrorMessage(null);
        scanErrorToastShownRef.current = false;
      }
      if (
        res.ok &&
        res.folder_name === selectedFolder &&
        typeof res.imported_count === "number"
      ) {
        setScanImportedCount(res.imported_count);
      }
    };
    const pollOnce = () =>
      getScanImportStatus()
        .then(applyStatus)
        .catch(() => setScanImportRunning(false));
    pollOnce();
    // 正在扫描时要秒级响应；空闲时降频——否则空轮询会把后端日志刷满，
    // 排查真问题时反而看不清有用信息。
    const intervalMs = scanImportRunning ? 2000 : 10000;
    const timer = setInterval(pollOnce, intervalMs);
    return () => clearInterval(timer);
  }, [view, selectedFolder, t, scanImportRunning]);

  useEffect(() => {
    if (!scanImportRunning || !selectedFolder) return;
    const t = setInterval(() => loadFolderFiles(selectedFolder), 3000);
    return () => clearInterval(t);
  }, [scanImportRunning, selectedFolder, loadFolderFiles]);

  const studentFiles = folderFiles;

  const sortedClassStudents = useMemo(() => {
    const scoreNumber = (value?: string | null) => {
      const s = String(value || "").trim();
      const n = Number(s);
      return Number.isFinite(n) ? n : null;
    };
    return [...classStudents].sort((a, b) => {
      const an = scoreNumber(a.student_number);
      const bn = scoreNumber(b.student_number);
      if (an !== null && bn !== null && an !== bn) return an - bn;
      if (an !== null && bn === null) return -1;
      if (an === null && bn !== null) return 1;
      return String(a.student_number || a.name).localeCompare(
        String(b.student_number || b.name),
        "zh-Hans-CN",
        {
          numeric: true,
          sensitivity: "base",
        },
      );
    });
  }, [classStudents]);

  const sanitizePaperBoxName = useCallback((name: string) => {
    const s = String(name || "")
      .trim()
      .replace(/[\\/:*?"<>|]/g, "_");
    return s || t("grading.unnamed");
  }, []);

  const splitFilename = useCallback((filename: string) => {
    const dot = filename.lastIndexOf(".");
    if (dot <= 0) return { stem: filename, ext: "" };
    return { stem: filename.slice(0, dot), ext: filename.slice(dot) };
  }, []);

  const getFilenamePageNo = useCallback(
    (filename: string) => {
      const { stem } = splitFilename(filename);
      const match = stem.match(/_(\d+)$/);
      const pageNo = match ? Number(match[1]) : 1;
      return Number.isInteger(pageNo) && pageNo > 0 ? pageNo : 1;
    },
    [splitFilename],
  );

  const getPaperBoxPageInfo = useCallback(
    (filename: string): { studentId: string; pageNo: number } | null => {
      const { stem } = splitFilename(filename);
      for (const student of sortedClassStudents) {
        const base = sanitizePaperBoxName(student.name);
        if (stem === base) return { studentId: student.id, pageNo: 1 };
        if (!stem.startsWith(`${base}_`)) continue;
        const pageNo = Number(stem.slice(base.length + 1));
        if (Number.isInteger(pageNo) && pageNo > 0)
          return { studentId: student.id, pageNo };
      }
      return null;
    },
    [sanitizePaperBoxName, sortedClassStudents, splitFilename],
  );

  /** 从上传文件名解析试卷框槽位：张三_2_img.jpg / 张三_2.pdf / 张三_2.docx → 张三 P2 */
  const parseUploadPaperBoxSlot = useCallback(
    (filename: string): { boxName: string; pageNo: number } | null => {
      const { stem } = splitFilename(filename);
      const imgPageMatch = stem.match(/^(.+)_(\d+)_img$/);
      if (imgPageMatch) {
        const pageNo = Number(imgPageMatch[2]);
        if (Number.isInteger(pageNo) && pageNo > 0) {
          return { boxName: imgPageMatch[1], pageNo };
        }
      }
      const pageMatch = stem.match(/^(.+)_(\d+)$/);
      if (pageMatch) {
        const pageNo = Number(pageMatch[2]);
        if (Number.isInteger(pageNo) && pageNo > 0) {
          return { boxName: pageMatch[1], pageNo };
        }
      }
      return null;
    },
    [splitFilename],
  );

  const findStudentForPaperBoxName = useCallback(
    (boxName: string) => {
      const target = sanitizePaperBoxName(boxName);
      return (
        sortedClassStudents.find(
          (s) => sanitizePaperBoxName(s.name) === target,
        ) ?? null
      );
    },
    [sanitizePaperBoxName, sortedClassStudents],
  );

  const standardAnswerSlots = useMemo<Array<StandardAnswerItem | null>>(() => {
    const capacity = Math.max(
      1,
      paperBoxCapacity || DEFAULT_PAPER_BOX_CAPACITY,
    );
    const slots = Array.from(
      { length: capacity },
      () => null as StandardAnswerItem | null,
    );
    for (const item of standardAnswers) {
      const pageNo = Number(item.page_no || 1);
      if (
        Number.isInteger(pageNo) &&
        pageNo >= 1 &&
        pageNo <= capacity &&
        !slots[pageNo - 1]
      ) {
        slots[pageNo - 1] = item;
      }
    }
    return slots;
  }, [paperBoxCapacity, standardAnswers]);

  const standardBoxCurrentSlot =
    standardAnswerSlots[standardBoxPageNo - 1] ?? null;
  const standardAnswerPageSet = useMemo(
    () => new Set(standardAnswers.map((item) => Number(item.page_no || 1))),
    [standardAnswers],
  );

  const paperBoxes = useMemo<PaperBox[]>(() => {
    const capacity = Math.max(
      1,
      paperBoxCapacity || DEFAULT_PAPER_BOX_CAPACITY,
    );
    const boxes = sortedClassStudents.map((student) => ({
      student,
      files: [] as FolderFileItem[],
      slots: Array.from(
        { length: capacity },
        () => null as FolderFileItem | null,
      ),
    }));
    const byId = new Map(boxes.map((box) => [box.student.id, box]));
    for (const file of studentFiles) {
      const info = getPaperBoxPageInfo(file.name);
      if (!info) continue;
      const box = byId.get(info.studentId);
      if (!box) continue;
      box.files.push(file);
      if (
        info.pageNo >= 1 &&
        info.pageNo <= capacity &&
        !box.slots[info.pageNo - 1]
      ) {
        box.slots[info.pageNo - 1] = file;
      }
    }
    return boxes;
  }, [
    getPaperBoxPageInfo,
    paperBoxCapacity,
    sortedClassStudents,
    studentFiles,
  ]);

  /** 学生框内按页码 1、2、3… 排序，供打印/导出使用（box.files 仅为上传顺序） */
  const filesInPageOrder = useCallback(
    (box: PaperBox): FolderFileItem[] => {
      const fromSlots: FolderFileItem[] = [];
      for (const slot of box.slots) {
        if (slot) fromSlots.push(slot);
      }
      if (fromSlots.length > 0) return fromSlots;
      return [...box.files].sort((a, b) => {
        const pa = getPaperBoxPageInfo(a.name)?.pageNo ?? 999;
        const pb = getPaperBoxPageInfo(b.name)?.pageNo ?? 999;
        if (pa !== pb) return pa - pb;
        return a.name.localeCompare(b.name, "zh-Hans-CN", {
          numeric: true,
          sensitivity: "base",
        });
      });
    },
    [getPaperBoxPageInfo],
  );

  /** 打印留痕：保持学生顺序，同一学生内按页码 1→2→3 排序 */
  const sortFilesForPrint = useCallback(
    (files: FolderFileItem[]): FolderFileItem[] => {
      const pageNoOf = (name: string) => {
        const fromBox = getPaperBoxPageInfo(name)?.pageNo;
        if (fromBox != null) return fromBox;
        const { stem } = splitFilename(name);
        const m = stem.match(/_(\d+)$/);
        return m ? Number(m[1]) : 1;
      };
      const baseOf = (name: string) => {
        const { stem } = splitFilename(name);
        const m = stem.match(/^(.*?)_\d+$/);
        return m?.[1] || stem;
      };
      const result: FolderFileItem[] = [];
      let i = 0;
      while (i < files.length) {
        const base = baseOf(files[i].name);
        const block: FolderFileItem[] = [];
        while (i < files.length && baseOf(files[i].name) === base) {
          block.push(files[i]);
          i += 1;
        }
        block.sort((a, b) => {
          const pa = pageNoOf(a.name);
          const pb = pageNoOf(b.name);
          if (pa !== pb) return pa - pb;
          return a.name.localeCompare(b.name, "zh-Hans-CN", {
            numeric: true,
            sensitivity: "base",
          });
        });
        result.push(...block);
      }
      return result;
    },
    [getPaperBoxPageInfo, splitFilename],
  );

  const unboxedStudentFiles = useMemo(
    () => studentFiles.filter((file) => !getPaperBoxPageInfo(file.name)),
    [getPaperBoxPageInfo, studentFiles],
  );

  const activePaperBox = useMemo(
    () =>
      paperBoxes.find((b) => b.student.id === previewPaperBoxStudentId) ?? null,
    [paperBoxes, previewPaperBoxStudentId],
  );

  const paperBoxCurrentSlot =
    activePaperBox?.slots[previewPaperBoxPageNo - 1] ?? null;

  const syncPaperBoxDetailItem = useCallback(
    (studentId: string, pageNo: number) => {
      const box = paperBoxes.find((b) => b.student.id === studentId);
      if (!box) return;
      const slot = box.slots[pageNo - 1];
      const allCompleted = [
        ...(gradingsPersisted?.completed || []),
        ...(refProgress?.completed || []),
      ] as RefCompleted[];
      const targetName =
        slot?.name || `${sanitizePaperBoxName(box.student.name)}_${pageNo}.jpg`;
      const currentBase = getEssayGroupBaseName(targetName);
      const currentCompleted = slot
        ? allCompleted.find((c) => c.name === slot.name)
        : undefined;
      // 借整卷/同页结果兜底时必须先确认该条目覆盖当前页：
      // 作文整卷语义可跨页借（多页重复同一总分）；参照/智能/自主每页独立，
      // 不能把 P1 的批改结果顶到 P2 头上（未批改就显示未批改）。
      const groupCompleted = allCompleted
        .filter((c) => getEssayGroupBaseName(c.name) === currentBase)
        .filter((c) =>
          completedEntryCoversFile(c.name, targetName, gradingEngine),
        )
        .sort(
          (a, b) => getCompletedItemRichness(b) - getCompletedItemRichness(a),
        )[0];
      if (!slot) {
        const stem = `${sanitizePaperBoxName(box.student.name)}_${pageNo}`;
        setDetailItem(
          groupCompleted
            ? {
                ...groupCompleted,
                name: `${stem}.jpg`,
                image_annotated: undefined,
                image_original: undefined,
                image_marks_only: undefined,
                marks_only_filename: undefined,
              }
            : { name: `${stem}.jpg`, result: "" },
        );
      } else {
        setDetailItem(
          currentCompleted
            ? (currentCompleted as RefCompleted)
            : groupCompleted
              ? {
                  ...groupCompleted,
                  name: slot.name,
                  image_annotated: undefined,
                  image_original: undefined,
                  image_marks_only: undefined,
                  marks_only_filename: undefined,
                }
              : { name: slot.name, result: "" },
        );
      }
      setDetailShowOriginal(false);
    },
    [paperBoxes, gradingsPersisted, refProgress, sanitizePaperBoxName, gradingEngine],
  );

  const openManualPaper = useCallback(
    (filename: string) => {
      if (!manualLayoutStatus.confirmed) {
        toast.info(t("grading.action.cutAnalysis"));
        return;
      }
      const item =
        gradingsPersisted?.completed.find((entry) => entry.name === filename) ||
        refProgress?.completed.find((entry) => entry.name === filename) ||
        null;
      if (!item?.result) {
        toast.info(t("grading.manual.noAnalysisData"));
        return;
      }
      setDetailItem(null);
      setManualGradingItem({ ...item, name: filename });
    },
    [
      gradingsPersisted?.completed,
      manualLayoutStatus.confirmed,
      refProgress?.completed,
      t,
    ],
  );

  const openPaperBoxDialog = useCallback(
    (studentId: string, options?: { previewOnly?: boolean }) => {
      const box = paperBoxes.find((b) => b.student.id === studentId);
      if (!box) return;
      const firstIdx = box.slots.findIndex(Boolean);
      const page = firstIdx >= 0 ? firstIdx + 1 : 1;
      const firstFile = box.slots[firstIdx >= 0 ? firstIdx : 0];
      // 卡片点按：手动系进打分弹窗；放大镜（previewOnly）：统分/批改详情
      if (!options?.previewOnly && isManualEngine(gradingEngine) && firstFile) {
        openManualPaper(firstFile.name);
        return;
      }
      setPaperBoxSlideDirection(0);
      setPreviewPaperBoxStudentId(studentId);
      setPreviewPaperBoxPageNo(page);
      setPreviewPaperBoxShowOriginal(false);
      syncPaperBoxDetailItem(studentId, page);
    },
    [gradingEngine, openManualPaper, paperBoxes, syncPaperBoxDetailItem],
  );

  const switchPaperBoxPage = useCallback((page: number) => {
    setPreviewPaperBoxPageNo((prev) => {
      if (page === prev) return prev;
      setPaperBoxSlideDirection(page > prev ? 1 : -1);
      setPreviewPaperBoxShowOriginal(false);
      return page;
    });
  }, []);

  const closeGradingPreviewDialog = useCallback(() => {
    setDetailItem(null);
    setPreviewPaperBoxStudentId(null);
    setPreviewPaperBoxShowOriginal(false);
    setPaperBoxSlideDirection(0);
  }, []);

  const triggerPaperBoxUpload = useCallback((pageNo: number) => {
    paperBoxUploadTargetPageRef.current = pageNo;
    paperBoxUploadInputRef.current?.click();
  }, []);

  const handlePaperBoxSlotUpload = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !selectedFolder || !activePaperBox) return;
    const pageNo = paperBoxUploadTargetPageRef.current;
    setPreviewPaperBoxUploading(true);
    try {
      const stem = `${sanitizePaperBoxName(activePaperBox.student.name)}_${pageNo}`;
      const existing = activePaperBox.slots[pageNo - 1];
      if (existing?.name) {
        try {
          await deleteFolderFile(selectedFolder, existing.name);
        } catch {
          //
        }
      }
      const { ext } = splitFilename(file.name);
      const targetName = `${stem}${ext || ".jpg"}`;
      const uploadFile = new File([file], targetName, {
        type: file.type || "application/octet-stream",
      });
      await uploadToFolder(selectedFolder, uploadFile, false);
      toast.success(t("grading.toast.pageUploaded", { page: pageNo }));
      await loadFolderFiles(selectedFolder, gradingEngine);
      setPreviewPaperBoxPageNo(pageNo);
      setPaperBoxSlideDirection(0);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg || t("grading.uploadFailed"));
    } finally {
      setPreviewPaperBoxUploading(false);
    }
  };

  const handleConfirmPaperBoxDelete = async () => {
    if (!selectedFolder || !activePaperBox || !paperBoxCurrentSlot?.name) {
      setPreviewPaperBoxDeleteOpen(false);
      return;
    }
    const filename = paperBoxCurrentSlot.name;
    const pageNo = previewPaperBoxPageNo;
    setPreviewPaperBoxDeleting(true);
    try {
      await deleteFolderFile(selectedFolder, filename);
      setRefProgress((prev) =>
        prev
          ? {
              ...prev,
              completed: (prev.completed || []).filter(
                (item) => item.name !== filename,
              ),
              failed: (prev.failed || []).filter(
                (item) => item.name !== filename,
              ),
            }
          : prev,
      );
      setGradingsPersisted((prev) =>
        prev
          ? {
              completed: (prev.completed || []).filter(
                (item) => item.name !== filename,
              ),
              failed: (prev.failed || []).filter(
                (item) => item.name !== filename,
              ),
            }
          : prev,
      );
      const stem = `${sanitizePaperBoxName(activePaperBox.student.name)}_${pageNo}`;
      setDetailItem({ name: `${stem}.jpg`, result: "" });
      setPreviewPaperBoxShowOriginal(false);
      setPreviewPaperBoxDeleteOpen(false);
      toast.success(t("grading.toast.pageDeleted"));
      await loadFolderFiles(selectedFolder, gradingEngine);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg || t("grading.toast.deleteFailed"));
    } finally {
      setPreviewPaperBoxDeleting(false);
    }
  };

  const findNextPaperBoxSlot = useCallback(
    (occupiedNames?: Set<string>) => {
      const occupied =
        occupiedNames || new Set(studentFiles.map((f) => f.name));
      const byStem = new Set(
        Array.from(occupied).map((name) => splitFilename(name).stem),
      );
      for (const student of sortedClassStudents) {
        const base = sanitizePaperBoxName(student.name);
        for (let pageNo = 1; pageNo <= paperBoxCapacity; pageNo += 1) {
          const stem = `${base}_${pageNo}`;
          if (!byStem.has(stem)) return { student, pageNo, stem };
        }
      }
      return null;
    },
    [
      paperBoxCapacity,
      sanitizePaperBoxName,
      sortedClassStudents,
      splitFilename,
      studentFiles,
    ],
  );

  const applyPaperBoxCapacity = () => {
    const next = Math.min(
      MAX_PAPER_BOX_CAPACITY,
      Math.max(
        1,
        Math.floor(Number(paperBoxCapacityDraft) || DEFAULT_PAPER_BOX_CAPACITY),
      ),
    );
    setPaperBoxCapacity(next);
    setPaperBoxCapacityDraft(String(next));
    if (selectedFolder) {
      const existing = getStoredFolderPrefs(selectedFolder);
      setStoredFolderPrefs(selectedFolder, {
        ...existing,
        paper_box_capacity: next,
      });
    }
    setPaperBoxSettingsOpen(false);
    toast.success(t("grading.toast.paperBoxCapacitySet", { count: next }));
  };

  useEffect(() => {
    if (!scanImportRunning || !selectedFolder || scanAutoAssigningRef.current)
      return;
    if (!sortedClassStudents.length || !studentFiles.length) return;
    const known = scanImportKnownFilesRef.current;
    const candidates = studentFiles.filter(
      (file) => !known.has(file.name) && !getPaperBoxPageInfo(file.name),
    );
    if (!candidates.length) return;
    scanAutoAssigningRef.current = true;
    (async () => {
      const occupied = new Set(studentFiles.map((f) => f.name));
      let renamed = 0;
      for (const file of candidates) {
        const slot = findNextPaperBoxSlot(occupied);
        if (!slot) break;
        const { ext } = splitFilename(file.name);
        const newName = `${slot.stem}${ext || ".jpg"}`;
        try {
          await renameFolderFile(selectedFolder, file.name, newName);
          occupied.delete(file.name);
          occupied.add(newName);
          known.add(newName);
          renamed += 1;
        } catch {
          known.add(file.name);
        }
      }
      if (renamed > 0) {
        toast.success(t("grading.toast.scanAutoAssigned", { count: renamed }));
        await loadFolderFiles(selectedFolder);
      }
    })().finally(() => {
      scanAutoAssigningRef.current = false;
    });
  }, [
    findNextPaperBoxSlot,
    getPaperBoxPageInfo,
    loadFolderFiles,
    scanImportRunning,
    selectedFolder,
    sortedClassStudents.length,
    splitFilename,
    studentFiles,
  ]);

  const toggleFolderDeleteSelection = (name: string) => {
    setDeletingFolderIds((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const handleConfirmDeleteFolders = async () => {
    if (deletingFolderIds.size === 0 || !deleteFolderPassword.trim()) {
      toast.error(t("grading.start.selectClassAndPassword"));
      return;
    }
    setDeleteFolderExecuting(true);
    try {
      const res = await deleteFolders(
        Array.from(deletingFolderIds),
        deleteFolderPassword.trim(),
      );
      if (res.ok) {
        toast.success(res.msg || t("grading.start.deleted"));
        setDeleteFolderDialogOpen(false);
        setDeleteFolderPassword("");
        setDeletingFolderIds(new Set());
        setFolderDeleteMode(false);
        loadFolders();
      } else {
        toast.error(res.msg || t("grading.start.deleteFailed"));
      }
    } catch (e: any) {
      toast.error(e?.message || t("grading.start.deleteFailed"));
    } finally {
      setDeleteFolderExecuting(false);
    }
  };

  // ----- 作文批改规则相关 -----
  const handleCreateRubric = async () => {
    const name = newRubricName.trim();
    if (!name) {
      toast.error(t("grading.toast.ruleNameRequired"));
      return;
    }
    setNewRubricLoading(true);
    try {
      const res = await createEssayRubric(name, "");
      toast.success(t("grading.toast.ruleCreated"));
      setNewRubricDialogOpen(false);
      setNewRubricName("");
      await loadEssayRubrics();
      setActiveRubricId(res.id);
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.ruleCreateFailed"));
    } finally {
      setNewRubricLoading(false);
    }
  };

  // handleUpdateRubricContent 已经移除，因为主输入框被删除，现在采用失焦自动保存

  const handleConfirmDeleteRubrics = async () => {
    if (deletingRubricIds.size === 0) return;
    setDeleteRubricExecuting(true);
    try {
      await deleteEssayRubrics(Array.from(deletingRubricIds));
      toast.success(t("grading.toast.ruleDeleted"));
      setDeleteRubricConfirmOpen(false);
      setDeletingRubricIds(new Set());
      setRubricDeleteMode(false);
      await loadEssayRubrics();
      // 如果删除的是当前选中的，重置选中状态
      if (activeRubricId && deletingRubricIds.has(activeRubricId)) {
        setActiveRubricId(null);
      }
    } catch (e: any) {
      toast.error(e?.message || t("grading.start.deleteFailed"));
    } finally {
      setDeleteRubricExecuting(false);
    }
  };

  const toggleRubricDeleteSelection = (id: string) => {
    setDeletingRubricIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  // -------------------------

  const handleCreateFolder = async () => {
    if (!selectedClass) {
      toast.error(t("grading.toast.selectClassFirst"));
      return;
    }
    const name = newFolderName.trim();
    if (!name) {
      toast.error(t("grading.start.enterFolderName"));
      return;
    }
    setCreateLoading(true);
    try {
      const res = await createFolder(name, selectedClass || undefined, {
        subject: newFolderSubject || selectedSubject || undefined,
        grade: grade || undefined,
        homeworkType: newFolderHomeworkType || undefined,
      });
      if (res.ok) {
        toast.success(t("grading.start.folderCreated"));
        setNewFolderName("");
        setCreateDialogOpen(false);
        loadFolders();
      } else {
        toast.error(t("grading.start.createFailed"));
      }
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.ruleCreateFailed"));
    } finally {
      setCreateLoading(false);
    }
  };

  const handleRenameFolder = async () => {
    if (!renameFolderTarget) return;
    const newName = renameFolderNewName.trim();
    if (!newName) {
      toast.error(t("grading.start.enterNewName"));
      return;
    }
    setRenameFolderLoading(true);
    try {
      const res = await renameFolder(renameFolderTarget, newName, {
        homeworkType: renameFolderHomeworkType || undefined,
      });
      if (res.ok) {
        toast.success(t("grading.start.folderRenamed"));
        setRenameFolderDialogOpen(false);
        loadFolders();
      } else {
        toast.error(res.msg || t("grading.start.renameFailed"));
      }
    } catch (e: any) {
      toast.error(e?.message || t("grading.start.renameFailed"));
    } finally {
      setRenameFolderLoading(false);
    }
  };

  // ----- 数据漫游：班级数据导出 / 导入 -----
  const handleExportClassData = useCallback(async () => {
    if (!selectedClass) {
      toast.error(t("grading.toast.selectClassFirst"));
      return;
    }
    setDataExporting(true);
    try {
      const blob = await exportClassData(selectedClass);
      const now = new Date();
      const dateStamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}`;
      const safeClassId = String(selectedClass).replace(/[\\/:*?"<>|]/g, "_");
      saveBlob(blob, `grade_buddy_export_${safeClassId}_${dateStamp}.zip`);
      toast.success(t("grading.dataExport.exportSuccess"));
    } catch (e: any) {
      toast.error(t("grading.dataExport.exportFailed"), {
        description: e?.message || t("grading.dataExport.exportFailed"),
      });
    } finally {
      setDataExporting(false);
    }
  }, [selectedClass, t]);

  const handleImportClassData = useCallback(
    async (file: File) => {
      if (!selectedClass) {
        toast.error(t("grading.toast.selectClassFirst"));
        return;
      }
      setDataImporting(true);
      try {
        const res = await importClassData(file, selectedClass);
        setImportResult(res);
        const importedCount = res.imported?.length ?? 0;
        const skippedCount = res.skipped?.length ?? 0;
        const failedCount = res.errors?.length ?? 0;
        toast.success(
          t("grading.dataExport.importSummary", {
            imported: importedCount,
            skipped: skippedCount,
            failed: failedCount,
          }),
        );
        if (skippedCount > 0 || failedCount > 0) {
          setImportResultOpen(true);
        }
      } catch (e: any) {
        toast.error(t("grading.dataExport.importFailed"), {
          description: e?.message || t("grading.dataExport.importFailed"),
        });
      } finally {
        setDataImporting(false);
      }
    },
    [selectedClass, t],
  );

  const handleImportFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) void handleImportClassData(file);
      e.target.value = "";
    },
    [handleImportClassData],
  );

  const openRenameFileDialog = (filename: string) => {
    if (refLoading) return;
    setRenameFileTarget({ name: filename });
    setRenameFileNewName(filename);
    setRenameFileDialogOpen(true);
  };

  const handleRenameFile = async () => {
    if (!selectedFolder || !renameFileTarget) return;
    const oldName = renameFileTarget.name;
    const newName = renameFileNewName.trim();
    if (!newName) {
      toast.error(t("grading.toast.renamePaperRequired"));
      return;
    }
    if (newName === oldName) {
      setRenameFileDialogOpen(false);
      return;
    }
    setRenameFileLoading(true);
    try {
      const res = await renameFolderFile(selectedFolder, oldName, newName);
      if (res.ok) {
        const nextName = res.filename || res.name || newName;
        toast.success(t("grading.toast.paperRenamed"));
        setRenameFileDialogOpen(false);
        setRenameFileTarget(null);
        setRenameFileNewName("");
        setSelectedGradeIds((prev) => {
          if (!prev.has(oldName)) return prev;
          const next = new Set(prev);
          next.delete(oldName);
          next.add(nextName);
          return next;
        });
        setDeletingIds((prev) => {
          if (!prev.has(oldName)) return prev;
          const next = new Set(prev);
          next.delete(oldName);
          next.add(nextName);
          return next;
        });
        setRefProgress((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            completed: prev.completed.map((item) =>
              item.name === oldName ? { ...item, name: nextName } : item,
            ),
            failed: prev.failed.map((item) =>
              item.name === oldName ? { ...item, name: nextName } : item,
            ),
            currentName:
              prev.currentName === oldName ? nextName : prev.currentName,
          };
        });
        if (zoomStudentFilename === oldName) {
          setZoomImageUrl(null);
          setZoomStudentFilename(null);
        }
        if (detailItem?.name === oldName) {
          setDetailItem(null);
        }
        await loadFolderFiles(selectedFolder, gradingEngine);
      } else {
        toast.error(res.msg || t("grading.start.renameFailed"));
      }
    } catch (e: any) {
      toast.error(e?.message || t("grading.start.renameFailed"));
    } finally {
      setRenameFileLoading(false);
    }
  };

  const handleSelectFolder = (name: string) => {
    refGradeCancelledRef.current = true;
    clearRefGradePollTimer();
    // 不停止任务：仅停止当前页面轮询；job_id 已写入本地，回到该{t("grading.start.folders")}会自动恢复
    setSelectedFolder(name);
    setRefProgress(null);
    setGradingsPersisted(null);
    setDeleteMode(false);
    setDeletingIds(new Set());
    setSelectGradeMode(false);
    setSelectedGradeIds(new Set());
    setManualLayoutOpen(false);
    setManualGradingItem(null);
    setAnswerKeyLoaded(null);
    setAnswerKeyText("");
    setAnswerKeyImageFile(null);
    setAnswerKeyImageName("");
    setView("folder");
  };

  const handleBackToList = () => {
    refGradeCancelledRef.current = true;
    clearRefGradePollTimer();
    // 不停止任务：仅停止当前页面轮询；回到{t("grading.start.folders")}详情会自动恢复
    setView("list");
    setSelectedFolder(null);
    setRefProgress(null);
    setGradingsPersisted(null);
    setDeleteMode(false);
    setDeletingIds(new Set());
    setSelectGradeMode(false);
    setSelectedGradeIds(new Set());
    setManualLayoutOpen(false);
    setManualGradingItem(null);
  };

  const updateManualCompletedItem = useCallback((item: RefCompleted) => {
    setGradingsPersisted((prev) => {
      if (!prev) return prev;
      const nextCompleted = prev.completed.filter((c) => c.name !== item.name);
      nextCompleted.push(item);
      return { ...prev, completed: nextCompleted };
    });
    setDetailItem(item);
  }, []);

  // 判错批注地图随详情卷同步（换卷/批注落盘后刷新）
  useEffect(() => {
    setWrongAnnotations(detailItem?.wrong_annotations ?? {});
  }, [detailItem?.name, detailItem?.wrong_annotations]);

  // 扣分项地图随详情卷同步（换卷/落盘后刷新）
  useEffect(() => {
    const next = detailItem?.deduction_items ?? {};
    manualDeductionsRef.current = next;
    manualDeductionsDirtyRef.current = false;
    setManualDeductions(next);
  }, [detailItem?.name, detailItem?.deduction_items]);

  /** 批注存储引擎：manual/manual_reference → manual；作文不参与批注 */
  const wrongAnnoEngine = useMemo(() => {
    if (isManualEngine(gradingEngine)) return "manual" as const;
    if (
      gradingEngine === "baidu" ||
      gradingEngine === "smart_ref" ||
      gradingEngine === "aliyun"
    )
      return gradingEngine;
    return null;
  }, [gradingEngine]);

  /** 整体覆盖保存批注（轻量端点，不重画留痕，变体图后端自刷） */
  const persistWrongAnnotations = useCallback(
    async (next: WrongAnnotationsMap): Promise<boolean> => {
      if (!selectedFolder || !detailItem?.name || !wrongAnnoEngine) return false;
      try {
        const res = await saveWrongAnnotations(
          selectedFolder,
          detailItem.name,
          wrongAnnoEngine,
          next,
        );
        if (!res.ok) return false;
        const saved = res.wrong_annotations ?? next;
        setWrongAnnotations(saved);
        const bust = (url?: string | null) =>
          url ? `${url}${url.includes("?") ? "&" : "?"}v=${Date.now()}` : url;
        setDetailItem((prev) =>
          prev && prev.name === detailItem.name
            ? {
                ...prev,
                wrong_annotations: saved,
                image_annotated_with_wrong_notes: bust(
                  res.image_annotated_with_wrong_notes,
                ),
                annotated_with_wrong_notes_filename:
                  res.annotated_with_wrong_notes_filename,
                image_marks_with_wrong_notes: bust(res.image_marks_with_wrong_notes),
                marks_with_wrong_notes_filename: res.marks_with_wrong_notes_filename,
              }
            : prev,
        );
        return true;
      } catch (e: any) {
        toast.error(e?.message || "批注保存失败");
        return false;
      }
    },
    [selectedFolder, detailItem?.name, wrongAnnoEngine],
  );

  /** 编辑/手写批注（空文本 = 删除）；AI 稿被改后标 edited，不再被自动覆盖 */
  const handleWrongAnnoEdit = useCallback(
    (questionKey: string, text: string) => {
      const before = wrongAnnotations[questionKey];
      const trimmed = (text || "").trim();
      let next: WrongAnnotationsMap;
      if (!trimmed) {
        const { [questionKey]: _removed, ...rest } = wrongAnnotations;
        next = rest;
      } else {
        next = {
          ...wrongAnnotations,
          [questionKey]: {
            text: trimmed,
            source: before?.source === "ai" ? "ai" : "manual",
            edited: true,
            ...(before?.generated_at
              ? { generated_at: before.generated_at }
              : {}),
          },
        };
      }
      setWrongAnnotations(next);
      void persistWrongAnnotations(next);
    },
    [wrongAnnotations, persistWrongAnnotations],
  );

  /** 重新生成单题 AI 批注（老师明确要求，覆盖旧稿） */
  const handleWrongAnnoRegenerate = useCallback(
    async (questionKey: string) => {
      if (
        !selectedFolder ||
        !detailItem?.name ||
        !wrongAnnoEngine ||
        wrongAnnoRegenerating
      )
        return;
      setWrongAnnoRegenerating(questionKey);
      try {
        const res = await generateWrongAnnotation(
          selectedFolder,
          detailItem.name,
          wrongAnnoEngine,
          questionKey,
        );
        if (res.ok) {
          const saved = res.wrong_annotations ?? wrongAnnotations;
          setWrongAnnotations(saved);
          const bust = (url?: string | null) =>
            url ? `${url}${url.includes("?") ? "&" : "?"}v=${Date.now()}` : url;
          setDetailItem((prev) =>
            prev && prev.name === detailItem.name
              ? {
                  ...prev,
                  wrong_annotations: saved,
                  image_annotated_with_wrong_notes: bust(
                    res.image_annotated_with_wrong_notes,
                  ),
                  annotated_with_wrong_notes_filename:
                    res.annotated_with_wrong_notes_filename,
                  image_marks_with_wrong_notes: bust(res.image_marks_with_wrong_notes),
                  marks_with_wrong_notes_filename: res.marks_with_wrong_notes_filename,
                }
              : prev,
          );
          if (!res.generated || !Object.keys(res.generated).length) {
            toast.error("生成失败，请稍后重试或手动编写");
          }
        }
      } catch (e: any) {
        toast.error(e?.message || "批注生成失败");
      } finally {
        setWrongAnnoRegenerating(null);
      }
    },
    [
      selectedFolder,
      detailItem?.name,
      wrongAnnoEngine,
      wrongAnnoRegenerating,
      wrongAnnotations,
    ],
  );

  /** 改为手动：来源置 manual，保留文本 */
  const handleWrongAnnoMarkManual = useCallback(
    (questionKey: string) => {
      const before = wrongAnnotations[questionKey];
      if (!before) return;
      const next: WrongAnnotationsMap = {
        ...wrongAnnotations,
        [questionKey]: {
          text: before.text || "",
          source: "manual",
          edited: true,
          ...(before.generated_at ? { generated_at: before.generated_at } : {}),
        },
      };
      setWrongAnnotations(next);
      void persistWrongAnnotations(next);
    },
    [wrongAnnotations, persistWrongAnnotations],
  );

  /** 删除批注 */
  const handleWrongAnnoDelete = useCallback(
    (questionKey: string) => {
      const { [questionKey]: _removed, ...rest } = wrongAnnotations;
      setWrongAnnotations(rest);
      void persistWrongAnnotations(rest);
    },
    [wrongAnnotations, persistWrongAnnotations],
  );

  const openAiCorrectDialog = useCallback(() => {
    if (!detailItem?.blocks?.length) return;
    const map: Record<string, "对" | "错" | "未作答" | "半对"> = {};
    const scores: Record<string, string> = {};
    for (const b of detailItem.blocks) {
      const key = `${b.index}::${b.sub_index ?? ""}`;
      if (b.result === "对" || b.result === "错" || b.result === "未作答" || b.result === "半对") {
        map[key] = b.result;
      }
      // 只回填老师手动打的作答区分（b.score），不要拿统分分数（question_scores）预填，
      // 否则保存时会把统分当手动分写进 block，导致留痕里 √/× 被画成「+分/0」。
      const existing = b.score;
      scores[key] =
        existing === null || existing === undefined ? "" : String(existing);
    }
    setAiCorrections(map);
    setAiScores(scores);
    setAiQuestionNotes(detailItem?.question_notes ?? {});
    setAiPaperNote(detailItem?.paper_note ?? "");
    setAiPaperNoteSource("manual");
    setAiNoteSource({});
    setAiCorrectOpen(true);
  }, [detailItem?.blocks, detailItem?.question_scores, detailItem?.question_notes, detailItem?.paper_note]);

  const handleSaveAiCorrect = async () => {
    if (!selectedFolder || !detailItem?.name || !detailItem?.blocks?.length)
      return;
    setAiCorrectSaving(true);
    try {
      const blocks = detailItem.blocks.map((b) => {
        const key = `${b.index}::${b.sub_index ?? ""}`;
        const scoreRaw = aiScores[key]?.trim();
        const score =
          scoreRaw === "" ? null : scoreRaw === undefined ? undefined : Number(scoreRaw);
        return {
          ...b,
          result: aiCorrections[key] ?? b.result,
          score:
            score === undefined
              ? (b.score ?? null)
              : score === null
                ? null
                : Number.isFinite(score)
                  ? score
                  : b.score,
        };
      });
      const res = await correctAiBlocks(
        selectedFolder,
        detailItem.name,
        gradingEngine,
        blocks,
        aiQuestionNotes,
        aiPaperNote.trim(),
        wrongAnnotations,
      );
      if (res.ok && res.item) {
        // 留痕图同名覆盖，给 URL 追加缓存破坏参数，强制浏览器重新拉取新图
        const bust = (url?: string) =>
          url ? `${url}${url.includes("?") ? "&" : "?"}v=${Date.now()}` : url;
        updateManualCompletedItem({
          ...res.item,
          image_annotated: bust(res.item.image_annotated),
          image_marks_only: bust(res.item.image_marks_only),
          image_marks_with_wrong_notes: bust(res.item.image_marks_with_wrong_notes),
          image_annotated_with_wrong_notes: bust(res.item.image_annotated_with_wrong_notes),
          image_original: bust(res.item.image_original),
        } as RefCompleted);
        setAiCorrectOpen(false);
        toast.success("批改结果已修正");
      } else {
        toast.error("修正失败");
      }
    } catch (e: any) {
      toast.error(e?.message || "修正失败");
    } finally {
      setAiCorrectSaving(false);
    }
  };

  const handleGenerateAiSummary = async () => {
    if (!selectedFolder || !detailItem?.name || aiSummaryLoading) return;
    setAiSummaryLoading(true);
    try {
      const res = await aiPaperSummary(
        selectedFolder,
        detailItem.name,
        gradingEngine,
      );
      if (res.ok && res.summary) {
        setAiPaperNote(res.summary);
        toast.success("AI 总评已生成，可继续微调");
      } else {
        toast.error(res.detail || "AI 总评生成失败");
        setAiPaperNoteSource("manual");
      }
    } catch (e: any) {
      toast.error(e?.message || "AI 总评生成失败");
      setAiPaperNoteSource("manual");
    } finally {
      setAiSummaryLoading(false);
    }
  };

  const getManualStudentOrder = useCallback(
    () =>
      folderFiles.filter(
        (f) =>
          !standardAnswer ||
          (f.name !== standardAnswer.filename &&
            f.name !== standardAnswer.name),
      ),
    [folderFiles, standardAnswer],
  );

  const getCompletedDetailByName = useCallback(
    (filename: string) =>
      gradingsPersisted?.completed.find((c) => c.name === filename) ||
      refProgress?.completed.find((c) => c.name === filename) ||
      null,
    [gradingsPersisted?.completed, refProgress?.completed],
  );

  const persistManualScores = useCallback(
    async (scores: Record<string, string>, generateMarks: boolean) => {
      if (!selectedFolder || !detailItem?.name) return null;
      const res = await saveManualGrade(
        selectedFolder,
        detailItem.name,
        scores,
        generateMarks,
        undefined,
        undefined,
        dingtalkPushMode === "auto",
        // 清分联动动过扣分项才整体覆盖回写；否则省略 = 本次不改（后端 None 语义）
        manualDeductionsDirtyRef.current ? manualDeductionsRef.current : undefined,
      );
      if (res.ok && res.item) {
        manualDeductionsDirtyRef.current = false;
        updateManualCompletedItem(res.item as RefCompleted);
        return res.item as RefCompleted;
      }
      return null;
    },
    [
      detailItem?.name,
      selectedFolder,
      updateManualCompletedItem,
      dingtalkPushMode,
    ],
  );

  const openManualSibling = useCallback(
    async (direction: -1 | 1) => {
      if (!detailItem?.name) return;
      const studentOrder = getManualStudentOrder();
      const currentIndex = studentOrder.findIndex(
        (f) => f.name === detailItem.name,
      );
      if (currentIndex === -1) return;
      const targetIndex = currentIndex + direction;
      if (targetIndex < 0 || targetIndex >= studentOrder.length) {
        toast.info(
          direction > 0
            ? t("grading.toast.lastPaper")
            : t("grading.toast.firstPaper"),
        );
        return;
      }

      setManualSwitching(true);
      try {
        if (manualAutosaveTimerRef.current) {
          clearTimeout(manualAutosaveTimerRef.current);
          manualAutosaveTimerRef.current = null;
        }
        await persistManualScores(manualGradeScores, false);
        const targetFile = studentOrder[targetIndex];
        const nextCompleted = getCompletedDetailByName(targetFile.name);
        if (nextCompleted) {
          setDetailItem(nextCompleted);
          setDetailShowOriginal(false);
          setManualEditingName(targetFile.name);
        } else {
          toast.info(
            direction > 0
              ? t("grading.toast.nextNotReady")
              : t("grading.toast.prevNotReady"),
          );
        }
      } catch (e: any) {
        toast.error(e?.message || t("grading.toast.switchPaperFailed"));
      } finally {
        setManualSwitching(false);
      }
    },
    [
      detailItem?.name,
      getCompletedDetailByName,
      getManualStudentOrder,
      manualGradeScores,
      persistManualScores,
    ],
  );

  const handleSaveManualGrade = async () => {
    if (!selectedFolder || !detailItem?.name) return;
    setManualGradeSaving(true);
    try {
      if (manualAutosaveTimerRef.current) {
        clearTimeout(manualAutosaveTimerRef.current);
        manualAutosaveTimerRef.current = null;
      }
      const savedItem = await persistManualScores(manualGradeScores, true);
      if (savedItem) {
        toast.success(t("grading.toast.saveMarkSuccess"));
        setManualEditingName(null);

        // 自动切换到{t("grading.action.nextPaper")}试卷
        const studentOrder = getManualStudentOrder();
        const currentIndex = studentOrder.findIndex(
          (f) => f.name === detailItem.name,
        );
        if (currentIndex !== -1 && currentIndex + 1 < studentOrder.length) {
          const nextFile = studentOrder[currentIndex + 1];
          const nextCompleted = getCompletedDetailByName(nextFile.name);
          if (nextCompleted) {
            setDetailItem(nextCompleted);
            setDetailShowOriginal(false);
            setManualEditingName(nextFile.name);
          } else {
            toast.info(t("grading.toast.nextNotReady"));
          }
        }
      }
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.saveFailed"));
    } finally {
      setManualGradeSaving(false);
    }
  };

  const handleClearManualScores = async () => {
    if (!selectedFolder || !detailItem?.name) return;
    setManualClearing(true);
    try {
      if (manualAutosaveTimerRef.current) {
        clearTimeout(manualAutosaveTimerRef.current);
        manualAutosaveTimerRef.current = null;
      }
      const res = await clearManualGrade(selectedFolder, detailItem.name);
      if (res.ok && res.item) {
        setManualGradeScores({});
        updateManualCompletedItem(res.item as RefCompleted);
        setManualEditingName(detailItem.name);
        setDetailShowOriginal(false);
        setManualClearConfirmOpen(false);
        toast.success(t("grading.toast.scoresCleared"));
      }
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.clearFailed"));
    } finally {
      setManualClearing(false);
    }
  };

  const handleAutoSaveManualPaper = useCallback(
    async (decisions: Record<string, ManualSlotDecision>, annotations: ManualAnnotations) => {
      if (!selectedFolder || !manualGradingItem?.name) return;
      const currentName = manualGradingItem.name;
      try {
        const response = await saveManualSlotDecisions(
          selectedFolder,
          currentName,
          decisions,
          true,
          annotations.questionNotes,
          annotations.paperNote,
          dingtalkPushMode === "auto",
          annotations.wrongAnnotations,
          annotations.deductionItems,
        );
        if (!response.ok || !response.item) {
          throw new Error(response.message || t("grading.toast.saveFailed"));
        }
        const saved = response.item as RefCompleted;
        setGradingsPersisted((current) => {
          const completed = (current?.completed || []).filter(
            (item) => item.name !== saved.name,
          );
          return {
            completed: [...completed, saved],
            failed: current?.failed || [],
          };
        });
        setManualGradingItem((current) =>
          current?.name === saved.name ? saved : current,
        );
      } catch (error: unknown) {
        toast.error(
          error instanceof Error
            ? error.message
            : t("grading.toast.saveFailed"),
        );
        throw error;
      }
    },
    [manualGradingItem?.name, selectedFolder, t, dingtalkPushMode],
  );

  const persistManualPaperDecisions = useCallback(
    async (
      decisions: Record<string, ManualSlotDecision>,
      annotations: ManualAnnotations,
    ): Promise<RefCompleted> => {
      if (!selectedFolder || !manualGradingItem?.name) {
        throw new Error(t("grading.toast.saveFailed"));
      }
      const currentName = manualGradingItem.name;
      const response = await saveManualSlotDecisions(
        selectedFolder,
        currentName,
        decisions,
        true,
        annotations.questionNotes,
        annotations.paperNote,
        dingtalkPushMode === "auto",
        annotations.wrongAnnotations,
        annotations.deductionItems,
      );
      if (!response.ok || !response.item) {
        throw new Error(response.message || t("grading.toast.saveFailed"));
      }
      const saved = response.item as RefCompleted;
      setGradingsPersisted((current) => {
        const completed = (current?.completed || []).filter(
          (item) => item.name !== saved.name,
        );
        return {
          completed: [...completed, saved],
          failed: current?.failed || [],
        };
      });
      setManualGradingItem((current) =>
        current?.name === saved.name ? saved : current,
      );
      return saved;
    },
    [manualGradingItem?.name, selectedFolder, t, dingtalkPushMode],
  );

  /** 手动批改对话框里单题重新生成 AI 批注（覆盖旧稿），返回完整映射 */
  const handleManualWrongAnnoRegenerate = useCallback(
    async (questionKey: string): Promise<WrongAnnotationsMap | null> => {
      if (!selectedFolder || !manualGradingItem?.name) return null;
      try {
        const res = await generateWrongAnnotation(
          selectedFolder,
          manualGradingItem.name,
          "manual",
          questionKey,
        );
        if (!res.ok) return null;
        if (!res.generated || !Object.keys(res.generated).length) {
          toast.error("生成失败，请稍后重试或手动编写");
        }
        return res.wrong_annotations ?? null;
      } catch (e: any) {
        toast.error(e?.message || "批注生成失败");
        return null;
      }
    },
    [selectedFolder, manualGradingItem?.name],
  );

  const handleManualPrintPreview = useCallback(
    async (
      decisions: Record<string, ManualSlotDecision>,
      annotations: ManualAnnotations,
    ): Promise<string | null> => {
      try {
        const saved = await persistManualPaperDecisions(decisions, annotations);
        if (!saved.image_annotated) {
          throw new Error(t("grading.toast.noPrintableMarks"));
        }
        return saved.image_annotated;
      } catch (error: unknown) {
        toast.error(
          error instanceof Error
            ? error.message
            : t("grading.toast.saveFailed"),
        );
        return null;
      }
    },
    [persistManualPaperDecisions, t],
  );

  const handlePrintManualPaper = useCallback(
    async (decisions: Record<string, ManualSlotDecision>, annotations: ManualAnnotations) => {
      setManualPaperPrinting(true);
      try {
        const saved = await persistManualPaperDecisions(decisions, annotations);
        const filename = marksFilenameForPrint(saved);
        if (!filename) {
          throw new Error(t("grading.toast.noMarkFilename"));
        }
        const customPaper = getCustomPaperSetting((message) =>
          toast.error(message),
        );
        if (printPaperSize === "custom" && !customPaper) return;
        const outputMode = printerOutputMode(selectedPrinter);
        if (outputMode === "pdf") {
          await exportMarksPdf([filename]);
          toast.success(t("grading.toast.pdfDownloaded"));
          return;
        }
        if (outputMode === "browser") {
          await browserPrintMarksPdf([filename]);
          toast.success(t("grading.toast.printSent"));
          return;
        }
        const response = await printMarks(
          filename,
          resolvePrinterName(),
          printPaperSize,
          customPaper,
          paperSourceId > 0 ? paperSourceId : undefined,
        );
        if (!response.ok) {
          throw new Error(response.msg || t("grading.toast.printFailed"));
        }
        toast.success(response.msg || t("grading.toast.printSent"));
      } catch (error: unknown) {
        toast.error(
          error instanceof Error
            ? error.message
            : t("grading.toast.printFailed"),
        );
      } finally {
        setManualPaperPrinting(false);
      }
    },
    [
      getCustomPaperSetting,
      paperSourceId,
      persistManualPaperDecisions,
      printPaperSize,
      resolvePrinterName,
      selectedPrinter,
      t,
    ],
  );

  const handleSaveManualPaper = useCallback(
    async (decisions: Record<string, ManualSlotDecision>, direction: ManualPaperDirection, annotations: ManualAnnotations) => {
      if (!selectedFolder || !manualGradingItem?.name) return;
      setManualPaperSaving(true);
      try {
        const currentName = manualGradingItem.name;
        const response = await saveManualSlotDecisions(
          selectedFolder,
          currentName,
          decisions,
          true,
          annotations.questionNotes,
          annotations.paperNote,
          dingtalkPushMode === "auto",
          annotations.wrongAnnotations,
          annotations.deductionItems,
        );
        if (!response.ok || !response.item) return;
        const saved = response.item as RefCompleted;
        setGradingsPersisted((current) => {
          const completed = (current?.completed || []).filter(
            (item) => item.name !== saved.name,
          );
          return {
            completed: [...completed, saved],
            failed: current?.failed || [],
          };
        });
        toast.success(t("grading.toast.saveMarkSuccess"));
        if (direction === "save") {
          setManualGradingItem(saved);
          return;
        }
        const order = folderFiles;
        const currentIndex = order.findIndex(
          (file) => file.name === currentName,
        );
        const targetIndex =
          currentIndex >= 0
            ? currentIndex + (direction === "next" ? 1 : -1)
            : -1;
        const targetFile =
          targetIndex >= 0 && targetIndex < order.length
            ? order[targetIndex]
            : null;
        if (!targetFile) {
          setManualGradingItem(saved);
          toast.info(
            direction === "next"
              ? t("grading.toast.lastPaper")
              : t("grading.toast.firstPaper"),
          );
          return;
        }
        const targetItem =
          gradingsPersisted?.completed.find(
            (item) => item.name === targetFile.name,
          ) ||
          refProgress?.completed.find((item) => item.name === targetFile.name);
        if (targetItem) {
          setManualGradingItem({ ...targetItem, name: targetFile.name });
        } else {
          setManualGradingItem(saved);
          toast.info(t("grading.toast.nextNotReady"));
        }
      } catch (error: unknown) {
        toast.error(
          error instanceof Error
            ? error.message
            : t("grading.toast.saveFailed"),
        );
      } finally {
        setManualPaperSaving(false);
      }
    },
    [
      folderFiles,
      gradingsPersisted?.completed,
      manualGradingItem?.name,
      refProgress?.completed,
      selectedFolder,
      t,
      dingtalkPushMode,
    ],
  );

  // 把「大题 + 小题」分数框里的编辑回填到题目块满分（scoringConfig 以题目块为键）。
  // 块 → (大题, 小题号) 由 questionStructure 提供；小题号对得上就用纸面分数，对不上保留原块分。
  const reconcileScoringConfig = () => {
    const next: Record<string, number> = { ...scoringConfig };
    const struct = questionStructure || {};
    for (const blockTitle of Object.keys(struct)) {
      const s = struct[blockTitle] || {};
      const major = String(s.major || "").trim();
      const sub = String(s.sub || "").trim();
      if (!major) continue;
      const subs = paperSubs[major];
      if (!Array.isArray(subs)) continue;
      const hit = subs.find((x) => String(x.num).trim() === sub);
      if (hit && typeof hit.score === "number") next[blockTitle] = hit.score;
    }
    return next;
  };

  const handleSaveScoringConfig = async () => {
    if (!selectedFolder) return;
    setScoringSaving(true);
    try {
      const res = await saveScoringConfig(
        selectedFolder,
        reconcileScoringConfig(),
        fullScore,
        questionStructure,
        majorScores,
        majorOrder,
        majorTitles,
        paperSubs,
      );
      if (res.ok) {
        toast.success(t("grading.toast.scoringSaved"));
      } else {
        toast.error(res.message || t("grading.toast.saveFailed"));
      }
    } catch (err: any) {
      toast.error(err?.message || t("grading.toast.saveFailed"));
    } finally {
      setScoringSaving(false);
    }
  };

  const handleApplyScoringConfig = async () => {
    if (!selectedFolder) return;
    setScoringApplying(true);
    try {
      const saveRes = await saveScoringConfig(
        selectedFolder,
        reconcileScoringConfig(),
        fullScore,
        questionStructure,
        majorScores,
        majorOrder,
        majorTitles,
        paperSubs,
      );
      if (!saveRes.ok) {
        toast.error(saveRes.message || t("grading.toast.scoringSaveFailed"));
        return;
      }
      const res = await applyScoringConfig(
        selectedFolder,
        reconcileScoringConfig(),
        fullScore,
        questionStructure,
        majorScores,
        majorOrder,
        majorTitles,
        paperSubs,
        dingtalkPushMode === "auto",
      );
      if (res.ok) {
        toast.success(res.message || t("grading.toast.autoScoreDone"));
        const h = await fetchGradingHistory(selectedFolder, gradingEngine);
        if (h.ok) {
          setGradingsPersisted({
            completed: (h.completed || []) as RefCompleted[],
            failed: h.failed || [],
          });
        }
        notifyAutoReportCheck();
      } else {
        toast.error(res.message || t("grading.toast.autoScoreFailed"));
      }
    } catch (err: any) {
      toast.error(err?.message || t("grading.toast.autoScoreFailed"));
    } finally {
      setScoringApplying(false);
    }
  };

  const handleAutoScoringConfig = async () => {
    if (!selectedFolder) return;
    setScoringAutoLoading(true);
    try {
      const res = await autoScoringConfig(selectedFolder);
      if (res.ok && res.scoring_config) {
        setScoringConfig(res.scoring_config);
        if (typeof res.full_score === "number") {
          setFullScore(res.full_score);
        }
        if (res.question_structure && Object.keys(res.question_structure).length) {
          setQuestionStructure(res.question_structure);
        }
        if (res.major_scores && Object.keys(res.major_scores).length) {
          setMajorScores(res.major_scores);
        }
        if (Array.isArray(res.major_order) && res.major_order.length) {
          setMajorOrder(res.major_order);
        }
        if (res.major_titles && Object.keys(res.major_titles).length) {
          setMajorTitles(res.major_titles);
        }
        if (res.paper_subs) {
          // 含空对象：标准答题区路径用逐题行（paper_subs=空），要把旧的纸面折叠小题行清掉
          setPaperSubs(res.paper_subs);
        }
        toast.success(t("grading.toast.autoAssignDone"));
      } else {
        toast.error(res.message || t("grading.toast.autoAssignFailed"));
      }
    } catch (err: any) {
      toast.error(err?.message || t("grading.toast.autoAssignFailed"));
    } finally {
      setScoringAutoLoading(false);
    }
  };

  const handleUploadStd = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length || !selectedFolder) return;
    if (files.length > paperBoxCapacity) {
      toast.error(
        t("grading.standardBox.tooManyPages", {
          count: files.length,
          capacity: paperBoxCapacity,
        }),
      );
      return;
    }
    const plannedPages = files.map((file, index) => ({
      file,
      pageNo: parseUploadPaperBoxSlot(file.name)?.pageNo ?? index + 1,
    }));
    const pageNumbers = plannedPages.map((item) => item.pageNo);
    if (new Set(pageNumbers).size !== pageNumbers.length) {
      toast.error(t("grading.standardBox.duplicatePages"));
      return;
    }
    const overflowPage = pageNumbers.find(
      (pageNo) => pageNo < 1 || pageNo > paperBoxCapacity,
    );
    if (overflowPage != null) {
      toast.error(
        t("grading.standardBox.pageOutOfRange", {
          page: overflowPage,
          capacity: paperBoxCapacity,
        }),
      );
      return;
    }
    setStandardBoxUploading(true);
    try {
      for (const item of plannedPages) {
        await uploadToFolder(selectedFolder, item.file, true, item.pageNo);
      }
      setReferenceLayoutStatus({
        confirmed: false,
        reviewed_pages: [],
        stale_pages: [],
      });
      setReferenceLayoutPages([]);
      setReferenceLayoutPrepareId(null);
      toast.success(
        t("grading.standardBox.pagesUploaded", { count: files.length }),
      );
      await loadFolderFiles(selectedFolder);
      setStandardBoxPageNo(1);
      // 上传完标准答案 → 自动识别每道题答案并列出
      void handleOpenAnswerTable({ auto: true });
    } catch (err: any) {
      toast.error(err?.message || t("grading.uploadFailed"));
    } finally {
      setStandardBoxUploading(false);
    }
  };

  const triggerStandardBoxUpload = useCallback((pageNo: number) => {
    standardBoxUploadTargetPageRef.current = pageNo;
    standardBoxUploadInputRef.current?.click();
  }, []);

  const handleStandardBoxSlotUpload = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !selectedFolder) return;
    const pageNo = standardBoxUploadTargetPageRef.current;
    if (pageNo < 1 || pageNo > paperBoxCapacity) return;
    setStandardBoxUploading(true);
    try {
      await uploadToFolder(selectedFolder, file, true, pageNo);
      setReferenceLayoutStatus({
        confirmed: false,
        reviewed_pages: [],
        stale_pages: [],
      });
      setReferenceLayoutPages([]);
      setReferenceLayoutPrepareId(null);
      await loadFolderFiles(selectedFolder, gradingEngine);
      setStandardBoxPageNo(pageNo);
      toast.success(t("grading.standardBox.pageUploaded", { page: pageNo }));
      // 试卷框里逐页上传：先关掉页槽对话框，自动识别并列出每道题答案
      setStandardBoxOpen(false);
      void handleOpenAnswerTable({ auto: true });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg || t("grading.uploadFailed"));
    } finally {
      setStandardBoxUploading(false);
    }
  };

  const handleConfirmStandardBoxDelete = async () => {
    if (!selectedFolder || !standardBoxCurrentSlot?.filename) {
      setStandardBoxDeleteOpen(false);
      return;
    }
    setStandardBoxDeleting(true);
    try {
      await deleteFolderFile(selectedFolder, standardBoxCurrentSlot.filename);
      setReferenceLayoutStatus({
        confirmed: false,
        reviewed_pages: [],
        stale_pages: [],
      });
      setReferenceLayoutPages([]);
      setReferenceLayoutPrepareId(null);
      await loadFolderFiles(selectedFolder, gradingEngine);
      setStandardBoxDeleteOpen(false);
      toast.success(
        t("grading.standardBox.pageDeleted", { page: standardBoxPageNo }),
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg || t("grading.toast.deleteFailed"));
    } finally {
      setStandardBoxDeleting(false);
    }
  };

  const handleUploadStudent = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const files = e.target.files;
    if (!files?.length || !selectedFolder) return;
    if (studentUploading) return;
    setStudentUploading(true);
    setStudentUploadProgress({ done: 0, total: files.length });
    try {
      const occupied = new Set(studentFiles.map((f) => f.name));
      let uploaded = 0;
      let namedCount = 0;
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const parsed = parseUploadPaperBoxSlot(file.name);
        let targetName: string | null = null;

        if (parsed && sortedClassStudents.length) {
          const student = findStudentForPaperBoxName(parsed.boxName);
          if (student) {
            if (parsed.pageNo >= 1 && parsed.pageNo <= paperBoxCapacity) {
              const { ext } = splitFilename(file.name);
              targetName = `${sanitizePaperBoxName(student.name)}_${parsed.pageNo}${ext || ".jpg"}`;
              namedCount += 1;
            } else {
              toast.warning(
                t("grading.pageOverflow", {
                  name: file.name,
                  max: paperBoxCapacity,
                }),
              );
            }
          } else if (parsed) {
            toast.warning(
              t("grading.studentNotMatch", {
                name: file.name,
                student: parsed.boxName,
              }),
            );
          }
        }

        if (!targetName) {
          const slot = findNextPaperBoxSlot(occupied);
          if (!slot) {
            toast.error(t("grading.capacityFull", { count: files.length - i }));
            break;
          }
          const { ext } = splitFilename(file.name);
          targetName = `${slot.stem}${ext || ".jpg"}`;
        }

        const uploadFile = new File([file], targetName, {
          type: file.type || "application/octet-stream",
        });
        await uploadToFolder(selectedFolder, uploadFile, false);
        occupied.add(targetName);
        uploaded += 1;
        setStudentUploadProgress({ done: uploaded, total: files.length });
      }
      if (uploaded > 0) {
        const namedHint =
          namedCount > 0
            ? t("grading.uploadNamedHint", { named: namedCount })
            : "";
        toast.success(
          `${t("grading.uploadSuccess", { count: uploaded })}${namedHint}`,
        );
        loadFolderFiles(selectedFolder);
      }
    } catch (err: any) {
      toast.error(err?.message || t("grading.uploadFailed"));
    } finally {
      setStudentUploading(false);
      setStudentUploadProgress(null);
    }
    e.target.value = "";
  };

  const handlePrepareReferenceLayout = async () => {
    if (
      !selectedFolder ||
      gradingEngine !== "aliyun" ||
      referenceLayoutPreparing ||
      refLoading
    )
      return;
    if (standardAnswers.length === 0) {
      toast.error(t("grading.preview.uploadStdFirst"));
      return;
    }
    setReferenceLayoutPreparing(true);
    try {
      const result = await prepareReferenceLayout(selectedFolder);
      setReferenceLayoutPages(result.pages || []);
      setReferenceLayoutPrepareId(result.prepare_id || null);
      setReferenceLayoutOpen(true);
    } catch (error: unknown) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("grading.layout.prepareFailed"),
      );
    } finally {
      setReferenceLayoutPreparing(false);
    }
  };

  const handleViewReferenceLayout = async () => {
    if (
      !selectedFolder ||
      gradingEngine !== "aliyun" ||
      referenceLayoutOpening ||
      refLoading
    )
      return;
    setReferenceLayoutOpening(true);
    try {
      const result = await getReferenceLayout(selectedFolder);
      setReferenceLayoutPages(result.pages || []);
      setReferenceLayoutPrepareId(result.prepare_id || null);
      setStandardBoxOpen(false);
      setReferenceLayoutOpen(true);
    } catch (error: unknown) {
      toast.error(
        error instanceof Error ? error.message : t("grading.layout.loadFailed"),
      );
    } finally {
      setReferenceLayoutOpening(false);
    }
  };

  const handleConfirmReferenceLayout = async (pages: ReferenceLayoutPage[]) => {
    if (!selectedFolder || !referenceLayoutPrepareId) {
      toast.error(t("grading.layout.sessionExpired"));
      return;
    }
    setReferenceLayoutSaving(true);
    try {
      const result = await confirmReferenceLayout(
        selectedFolder,
        referenceLayoutPrepareId,
        pages,
      );
      setReferenceLayoutStatus(
        result.reference_layout || {
          confirmed: Boolean(result.confirmed),
          reviewed_pages: pages.map((page) => page.page_no),
          stale_pages: [],
        },
      );
      setReferenceLayoutPages([]);
      setReferenceLayoutPrepareId(null);
      setReferenceLayoutOpen(false);
      toast.success(t("grading.layout.saved"));
      await loadFolderFiles(selectedFolder, gradingEngine);
      // 从识别列表「答题区框」进来的：改完框自动回识别列表（答案表按新框重建，手改保留）
      if (boxEditReturnRef.current) {
        boxEditReturnRef.current = false;
        await handleOpenAnswerTable({ auto: true });
      }
    } catch (error: unknown) {
      toast.error(
        error instanceof Error ? error.message : t("grading.layout.saveFailed"),
      );
    } finally {
      setReferenceLayoutSaving(false);
    }
  };

  // 布局模板：把当前布局（编辑会话页，或磁盘上已确认布局）存成命名模板
  const handleSaveLayoutTemplate = async (payload: {
    name: string;
    subject: string;
    class_id: string;
  }) => {
    if (!selectedFolder || layoutTemplateSaving) return;
    setLayoutTemplateSaving(true);
    try {
      let pages = referenceLayoutPages;
      if (!pages?.length) {
        const result = await getReferenceLayout(selectedFolder);
        pages = result.pages || [];
      }
      if (!pages?.length) {
        toast.error(t("layoutTemplate.noLayout"));
        return;
      }
      await saveLayoutTemplate({
        name: payload.name,
        layout: packLayoutForTemplate(pages),
        source_folder: selectedFolder,
        class_id: payload.class_id || selectedClass || "",
        subject: payload.subject || selectedSubject || "",
      });
      toast.success(t("layoutTemplate.saveSuccess"));
      setLayoutTemplateOpen(false);
    } catch (error: unknown) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("layoutTemplate.saveFailed"),
      );
    } finally {
      setLayoutTemplateSaving(false);
    }
  };

  // 布局模板：套到当前考试文件夹，开切题审查编辑器供核对，确认仍走 confirm_reference_layout
  const handleApplyLayoutTemplate = async (template: LayoutTemplateDetail) => {
    if (
      !selectedFolder ||
      referenceLayoutOpening ||
      referenceLayoutPreparing ||
      refLoading
    ) {
      return;
    }
    try {
      const result = referenceLayoutStatus.confirmed
        ? await getReferenceLayout(selectedFolder)
        : await prepareReferenceLayout(selectedFolder);
      const applied = applyTemplateToPages(
        result.pages || [],
        templateLayoutPages(template),
      );
      if (!applied.length) {
        toast.error(t("layoutTemplate.noLayout"));
        return;
      }
      setReferenceLayoutPages(applied);
      setReferenceLayoutPrepareId(result.prepare_id || null);
      setLayoutTemplateOpen(false);
      setStandardBoxOpen(false);
      setReferenceLayoutOpen(true);
      toast.success(t("layoutTemplate.applied"));
    } catch (error: unknown) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("grading.layout.loadFailed"),
      );
    }
  };

  // 上传完标准答案自动识别每道题答案，列出来供老师核对/手动修改
  const handleOpenAnswerTable = async (options?: {
    auto?: boolean;
  }) => {
    if (!selectedFolder || answerTableLoading) return;
    // auto=刚上传完，state 可能未刷新，不看 standardAnswers 直接识别
    if (!options?.auto && standardAnswers.length === 0) {
      toast.error(t("grading.preview.uploadStdFirst"));
      return;
    }
    setAnswerTableLoading(true);
    setAnswerTableOpen(true);
    try {
      const result = await getReferenceAnswerTable(selectedFolder, true);
      setAnswerTablePages(result.pages || []);
    } catch (error: unknown) {
      if (!options?.auto) {
        toast.error(
          error instanceof Error
            ? error.message
            : t("grading.answerTable.loadFailed"),
        );
      }
    } finally {
      setAnswerTableLoading(false);
    }
  };

  // 识别列表「答题区框」/缩略图：关列表进切题审查同款框编辑器改框（识别错了拖框即可）。
  // 框的唯一持久化路径是 confirm_reference_layout（批改只读 question.answer_bboxes），
  // 所以不做列表内改框；确认保存后 handleConfirmReferenceLayout 会自动带回本表。
  const handleEditAnswerBoxes = async (pageNo: number) => {
    if (
      !selectedFolder ||
      gradingEngine !== "aliyun" ||
      referenceLayoutOpening ||
      referenceLayoutPreparing
    )
      return;
    boxEditReturnRef.current = true;
    setBoxEditTargetPage(pageNo);
    setAnswerTableOpen(false);
    try {
      if (referenceLayoutStatus.confirmed) {
        // 已有确认过的切题审查：直接开编辑器（不动 OCR，旧布局就在磁盘上）
        const result = await getReferenceLayout(selectedFolder);
        setReferenceLayoutPages(result.pages || []);
        setReferenceLayoutPrepareId(result.prepare_id || null);
      } else {
        // 还没确认过切题审查：现场准备一份再开（每页一次新鲜 OCR）
        setReferenceLayoutPreparing(true);
        const result = await prepareReferenceLayout(selectedFolder);
        setReferenceLayoutPages(result.pages || []);
        setReferenceLayoutPrepareId(result.prepare_id || null);
      }
      setReferenceLayoutOpen(true);
    } catch (error: unknown) {
      boxEditReturnRef.current = false;
      toast.error(
        error instanceof Error ? error.message : t("grading.layout.loadFailed"),
      );
      // 编辑器打不开就退回识别列表，别把老师丢在空白处
      void handleOpenAnswerTable({ auto: true });
    } finally {
      setReferenceLayoutPreparing(false);
    }
  };

  const handleSaveAnswerTable = async (
    pageNo: number,
    questions: AnswerTableEdit[],
  ) => {
    if (!selectedFolder) return;
    setAnswerTableSaving(true);
    try {
      const result = await saveReferenceAnswerTable(
        selectedFolder,
        pageNo,
        questions,
      );
      setAnswerTablePages((prev) =>
        prev.map((page) =>
          page.page_no === pageNo
            ? {
                ...page,
                questions: result.questions || page.questions,
                updated_at: result.updated_at ?? page.updated_at,
              }
            : page,
        ),
      );
      toast.success(t("grading.answerTable.saved"));
    } catch (error: unknown) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("grading.answerTable.saveFailed"),
      );
      throw error;
    } finally {
      setAnswerTableSaving(false);
    }
  };

  const handleRebuildAnswerTable = async (resetEdits: boolean) => {
    if (!selectedFolder || answerTableLoading) return;
    setAnswerTableLoading(true);
    try {
      const result = await rebuildReferenceAnswerTable(
        selectedFolder,
        0,
        resetEdits,
      );
      setAnswerTablePages(result.pages || []);
    } catch (error: unknown) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("grading.answerTable.loadFailed"),
      );
    } finally {
      setAnswerTableLoading(false);
    }
  };

  // 空白卷模式第二上传：答案单独放在一张纸上——多页答案纸按页序 1、2、3… 传。
  // 传完「另开专窗」只识别答案（题号+答案），老师核对后与答题区按题号合并。
  const handleUploadAnswerSheets = async (files: File[]) => {
    if (!selectedFolder || !files.length) return;
    try {
      let pageNo = 1;
      for (const file of files) {
        await uploadAnswerSheet(selectedFolder, file, pageNo++);
      }
      toast.success(t("grading.answerSheet.uploaded"));
      await handleOpenAnswerSheet({ auto: true });
    } catch (error: unknown) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("grading.answerSheet.uploadFailed"),
      );
    }
  };

  // 工具栏「上传答案」隐藏文件框的 onChange 包装（顺手清空 value，同一文件可重选）
  const handleAnswerSheetFileChange = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    // 先快照再清 value：Chrome 的 input.files 是活列表，先清 value 会把刚选的
    // 文件也清空 → 上传静默消失（点上传答案没反应的根因）
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    await handleUploadAnswerSheets(files);
  };

  const handleOpenAnswerSheet = async (options?: { auto?: boolean }) => {
    if (!selectedFolder || answerSheetLoading) return;
    setAnswerSheetLoading(true);
    setAnswerSheetOpen(true);
    setAnswerSheetError("");
    try {
      const result = await getAnswerSheetRows(selectedFolder, true);
      setAnswerSheetRows(result.rows || []);
      if (result.error) setAnswerSheetError(result.error);
    } catch (error: unknown) {
      const message =
        error instanceof Error
          ? error.message
          : t("grading.answerSheet.loadFailed");
      setAnswerSheetError(message);
      if (!options?.auto) toast.error(message);
    } finally {
      setAnswerSheetLoading(false);
    }
  };

  // 专窗点「合并进答案表」：答案落盘后按题号合进答题区（每道题一行）
  const handleConfirmAnswerSheet = async (rows: AnswerSheetRow[]) => {
    if (!selectedFolder || answerSheetSaving) return;
    setAnswerSheetSaving(true);
    try {
      const result = await saveAnswerSheetRows(selectedFolder, { rows });
      setAnswerSheetRows(result.rows || []);
      setAnswerSheetOpen(false);
      toast.success(t("grading.answerSheet.merged"));
      void handleOpenAnswerTable({ auto: true });
    } catch (error: unknown) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("grading.answerSheet.mergeFailed"),
      );
    } finally {
      setAnswerSheetSaving(false);
    }
  };

  const handleRescanAnswerSheet = async () => {
    if (!selectedFolder || answerSheetLoading) return;
    setAnswerSheetLoading(true);
    setAnswerSheetError("");
    try {
      const result = await saveAnswerSheetRows(selectedFolder, {
        rescan: true,
      });
      setAnswerSheetRows(result.rows || []);
    } catch (error: unknown) {
      setAnswerSheetError(
        error instanceof Error
          ? error.message
          : t("grading.answerSheet.loadFailed"),
      );
    } finally {
      setAnswerSheetLoading(false);
    }
  };

  const handlePrepareManualLayout = async () => {
    if (
      !selectedFolder ||
      !isManualEngine(gradingEngine) ||
      manualLayoutPreparing ||
      refLoading
    )
      return;
    if (studentFiles.length === 0) {
      toast.error(t("grading.selectPapersFirst"));
      return;
    }
    setManualLayoutPreparing(true);
    try {
      // 自主阅卷（答题卡）走印刷框线检测；自主阅卷（试卷）取标准答题区做框线来源。
      const result = await prepareManualLayout(
        selectedFolder,
        gradingEngine === "manual_paper" ? "reference" : "answer_card",
      );
      setManualLayoutPages(result.pages || []);
      setManualLayoutPrepareId(result.prepare_id || null);
      setManualLayoutOpen(true);
    } catch (error: unknown) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("grading.manualLayout.prepareFailed"),
      );
    } finally {
      setManualLayoutPreparing(false);
    }
  };

  const handleViewManualLayout = async () => {
    if (
      !selectedFolder ||
      !isManualEngine(gradingEngine) ||
      manualLayoutPreparing ||
      refLoading
    )
      return;
    setManualLayoutPreparing(true);
    try {
      const result = await getManualLayout(selectedFolder);
      setManualLayoutPages(result.pages || []);
      setManualLayoutPrepareId(result.prepare_id || null);
      setManualLayoutOpen(true);
    } catch (error: unknown) {
      toast.error(
        error instanceof Error ? error.message : t("grading.layout.loadFailed"),
      );
    } finally {
      setManualLayoutPreparing(false);
    }
  };

  const handleConfirmManualLayout = async (pages: ReferenceLayoutPage[]) => {
    if (!selectedFolder || !manualLayoutPrepareId) {
      toast.error(t("grading.layout.sessionExpired"));
      return;
    }
    setManualLayoutSaving(true);
    try {
      const result = await confirmManualLayout(
        selectedFolder,
        manualLayoutPrepareId,
        pages,
      );
      setManualLayoutStatus(
        result.manual_layout || {
          confirmed: Boolean(result.confirmed),
          reviewed_pages: pages.map((page) => page.page_no),
          stale_pages: [],
        },
      );
      setManualLayoutPages([]);
      setManualLayoutPrepareId(null);
      setManualLayoutOpen(false);
      toast.success(t("grading.manualLayout.saved"));
      await loadFolderFiles(selectedFolder, "manual");
    } catch (error: unknown) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("grading.manualLayout.saveFailed"),
      );
    } finally {
      setManualLayoutSaving(false);
    }
  };

  const openAnswerKeyDialog = async () => {
    setAnswerKeyDialogOpen(true);
    if (selectedFolder) {
      try {
        const res = await getAnswerKey(selectedFolder);
        if (res?.ok && Object.keys(res.answers || {}).length > 0) {
          setAnswerKeyLoaded(res.answers);
          setAnswerKeyText(res.raw || "");
        }
      } catch {
        // 忽略回显失败
      }
    }
  };

  const handleSaveAnswerKey = async () => {
    if (!selectedFolder) return;
    if (!answerKeyText.trim() && !answerKeyImageFile) {
      toast.error(t("grading.answerKey.required"));
      return;
    }
    setAnswerKeySaving(true);
    try {
      const res = await saveAnswerKey(selectedFolder, answerKeyText, answerKeyImageFile);
      const answers = res.answers || {};
      setAnswerKeyLoaded(answers);
      setAnswerKeyText(res.raw || answerKeyText);
      setAnswerKeyImageFile(null);
      setAnswerKeyImageName("");
      if (answerKeyImageInputRef.current) answerKeyImageInputRef.current.value = "";
      toast.success(
        t("grading.answerKey.saved", { count: Object.keys(answers).length }),
      );
      setAnswerKeyDialogOpen(false);
    } catch (e: any) {
      toast.error(e?.message || t("grading.answerKey.saveFailed"));
    } finally {
      setAnswerKeySaving(false);
    }
  };

  const handleUploadOriginalPaper = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !selectedFolder) return;
    setOriginalPaperUploading(true);
    try {
      await uploadOriginalPaper(selectedFolder, file);
      setOriginalPaperName(file.name);
      setOriginalPaperScoreCount(0);
      await loadFolderFiles(selectedFolder, gradingEngine);
      toast.success(t("grading.originalPaper.uploaded"));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg || t("grading.uploadFailed"));
    } finally {
      setOriginalPaperUploading(false);
    }
  };

  const handleRecognizePaperScores = async () => {
    if (!selectedFolder) return;
    setOriginalPaperRecognizing(true);
    try {
      const res = await recognizePaperScores(selectedFolder);
      if (!res?.ok || !res.items?.length) {
        toast.error(t("grading.originalPaper.noItems"));
        return;
      }
      setOriginalPaperScoreItems(res.items);
      setOriginalPaperScoreOpen(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg || t("grading.originalPaper.recognizeFailed"));
    } finally {
      setOriginalPaperRecognizing(false);
    }
  };

  const handleApplyPaperScores = async (scores: Record<number, number>) => {
    if (!selectedFolder) return;
    setOriginalPaperApplying(true);
    try {
      const res = await applyPaperScores(selectedFolder, scores);
      const count = res?.count ?? Object.keys(scores).length;
      setOriginalPaperScoreCount(count);
      setOriginalPaperScoreOpen(false);
      setOriginalPaperOpen(false);
      toast.success(t("grading.originalPaper.applied", { count }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg || t("grading.originalPaper.applyFailed"));
    } finally {
      setOriginalPaperApplying(false);
    }
  };

  const startAnswerKeyGradePolling = (folderName: string, jobId: string) => {
    refGradeCancelledRef.current = false;
    clearRefGradePollTimer();
    setActiveGradingJobId(jobId);
    setRefLoading(true);

    const poll = async () => {
      if (refGradeCancelledRef.current) return;
      try {
        const st = await answerKeyGradeStatus(folderName, jobId);
        if (st.ok) {
          setRefProgress({
            total: st.total,
            completed: (st.completed || []) as RefCompleted[],
            failed: st.failed || [],
            currentName: st.current_name || null,
          });
          const done =
            !!st.done ||
            (st.total > 0 &&
              (st.completed?.length || 0) + (st.failed?.length || 0) >=
                st.total);
          if (done) {
            setRefLoading(false);
            setActiveGradingJobId(null);
            setStoredJobId(folderName, null);
            refGradePollTimerRef.current = null;
            fetchGradingHistory(folderName, "manual")
              .then((h) => {
                if (h.ok) {
                  setGradingsPersisted({
                    completed: (h.completed || []) as RefCompleted[],
                    failed: h.failed || [],
                  });
                }
              })
              .catch(() => {});
            if (st.failed?.length) {
              toast.error(st.failed[0]?.msg || t("grading.toast.gradeFailed"));
            } else {
              toast.success(t("grading.answerKey.done"));
            }
            return;
          }
        }
      } catch (e: any) {
        const msg = String(e?.message || "");
        if (msg.includes("任务不存在") || msg.includes("404")) {
          setRefLoading(false);
          setActiveGradingJobId(null);
          setStoredJobId(folderName, null);
          refGradePollTimerRef.current = null;
          return;
        }
      }
      if (refGradeCancelledRef.current) return;
      refGradePollTimerRef.current = setTimeout(poll, POLL_INTERVAL);
    };
    poll();
  };

  const handleStartAnswerKeyGrade = async () => {
    if (!selectedFolder) return;
    if (!manualLayoutStatus.confirmed) {
      void (manualLayoutStatus.confirmed
        ? handleViewManualLayout()
        : handlePrepareManualLayout());
      return;
    }
    let loaded = answerKeyLoaded;
    if (!loaded) {
      try {
        const res = await getAnswerKey(selectedFolder);
        if (res?.ok && Object.keys(res.answers || {}).length > 0) {
          loaded = res.answers;
          setAnswerKeyLoaded(res.answers);
          setAnswerKeyText(res.raw || "");
        }
      } catch {
        // 忽略
      }
    }
    if (!loaded && !answerKeyText.trim() && !answerKeyImageFile) {
      setAnswerKeyDialogOpen(true);
      toast.info(t("grading.answerKey.required"));
      return;
    }
    setRefLoading(true);
    setRefProgress(null);
    setActiveGradingJobId(null);
    try {
      if (answerKeyText.trim() || answerKeyImageFile) {
        await saveAnswerKey(selectedFolder, answerKeyText, answerKeyImageFile);
      }
      const res = await gradeByAnswerKey(selectedFolder);
      if (res.ok && res.job_id) {
        setStoredJobId(selectedFolder, res.job_id);
        setGradingsPersisted({ completed: [], failed: [] });
        setDetailItem(null);
        toast.success(t("grading.toast.gradeStarted"));
        startAnswerKeyGradePolling(selectedFolder, res.job_id);
      } else {
        setRefLoading(false);
        toast.error(t("grading.toast.gradeStartFailed"));
      }
    } catch (e: any) {
      setRefLoading(false);
      setActiveGradingJobId(null);
      toast.error(e?.message || t("grading.toast.gradeStartFailed"));
    }
  };

  const handleStartRefGrade = async (
    singleFilename?: string,
    selectedFilenames?: string[],
  ) => {
    if (!selectedFolder) return;
    if (gradingEngine === "aliyun" && !referenceLayoutStatus.confirmed) {
      toast.error(t("grading.layout.reviewFirst"));
      return;
    }
    const requestedNames = new Set(
      [singleFilename, ...(selectedFilenames || [])]
        .map((name) => String(name || "").trim())
        .filter(Boolean),
    );
    const requestedEssayNames =
      gradingEngine === "essay" && requestedNames.size > 0
        ? new Set(
            studentFiles
              .filter((file) => {
                const stem = String(file.name || "").replace(/\.[^.]+$/, "");
                const base = stem.replace(/_\d+$/, "");
                for (const requested of requestedNames) {
                  const requestedStem = requested.replace(/\.[^.]+$/, "");
                  const requestedBase = requestedStem.replace(/_\d+$/, "");
                  if (base && requestedBase && base === requestedBase)
                    return true;
                }
                return false;
              })
              .map((file) => file.name),
          )
        : requestedNames;
    if (gradingEngine === "aliyun" || gradingEngine === "smart_ref") {
      const targetFiles =
        requestedNames.size > 0
          ? studentFiles.filter((file) => requestedNames.has(file.name))
          : studentFiles;
      const missingPages = Array.from(
        new Set(
          targetFiles
            .map((file) => getFilenamePageNo(file.name))
            .filter((pageNo) => !standardAnswerPageSet.has(pageNo)),
        ),
      ).sort((a, b) => a - b);
      if (missingPages.length > 0) {
        toast.error(
          t("grading.standardBox.missingPages", {
            pages: missingPages.map((page) => `P${page}`).join("、"),
          }),
        );
        return;
      }
    }
    setDeleteMode(false);
    setDeletingIds(new Set());
    setSelectGradeMode(false);
    setSelectedGradeIds(new Set());
    setRefLoading(true);
    setRefProgress(null);
    setActiveGradingJobId(null);
    if (gradingEngine === "essay" && requestedEssayNames.size > 0) {
      setGradingsPersisted((prev) => {
        if (!prev) return prev;
        return {
          completed: (prev.completed || []).filter(
            (item) => !requestedEssayNames.has(String(item?.name || "")),
          ),
          failed: (prev.failed || []).filter(
            (item) => !requestedEssayNames.has(String(item?.name || "")),
          ),
        };
      });
      if (detailItem?.name && requestedEssayNames.has(detailItem.name)) {
        setDetailItem(null);
      }
    }
    try {
      const activeRubric = essayRubrics.find((r) => r.id === activeRubricId);
      // startEssayGrade 只透传后端需要的作文提示词字段，剔除 id/name/content/created_at/updated_at 等 UI 元数据
      const essayPrompts = activeRubric
        ? {
            summary_prompt: activeRubric.summary_prompt,
            comment_prompt: activeRubric.comment_prompt,
            rewrite_prompt: activeRubric.rewrite_prompt,
            guidance_prompt: activeRubric.guidance_prompt,
            scoring_prompt: activeRubric.scoring_prompt,
            topic_text: activeRubric.topic_text,
            topic_image_base64: activeRubric.topic_image_base64,
          }
        : undefined;
      const res =
        gradingEngine === "essay"
          ? await startEssayGrade(
              selectedFolder,
              activeRubric?.content?.trim() || "",
              singleFilename,
              selectedFilenames,
              essayPrompts,
              dingtalkPushMode === "auto",
            )
          : await startReferenceGrade(
              selectedFolder,
              gradingEngine,
              singleFilename,
              selectedFilenames,
              dingtalkPushMode === "auto",
            );
      if (res.ok && res.job_id) {
        if (gradingEngine === "essay")
          setStoredEssayJobId(selectedFolder, res.job_id);
        else {
          setStoredJobId(selectedFolder, res.job_id);
          setGradingsPersisted({ completed: [], failed: [] });
          setDetailItem(null);
        }
        toast.success(
          singleFilename
            ? t("grading.toast.gradeStartedOne")
            : selectedFilenames?.length
              ? t("grading.toast.gradeStartedSelected", {
                  count: selectedFilenames.length,
                })
              : t("grading.toast.gradeStarted"),
        );
        if (gradingEngine === "essay") {
          startEssayGradePolling(
            selectedFolder,
            res.job_id,
            singleFilename ? { singleFilename } : undefined,
          );
        } else {
          startRefGradePolling(
            selectedFolder,
            res.job_id,
            singleFilename ? { singleFilename } : undefined,
          );
        }
      } else {
        setRefLoading(false);
        toast.error(t("grading.toast.gradeStartFailed"));
      }
    } catch (e: any) {
      setRefLoading(false);
      setActiveGradingJobId(null);
      if (gradingEngine === "essay") {
        fetchEssayGradingHistory(selectedFolder)
          .then((h) => {
            if (h.ok) {
              setGradingsPersisted({
                completed: (h.completed || []) as any,
                failed: h.failed || [],
              });
            }
          })
          .catch(() => {});
      }
      toast.error(e?.message || t("grading.toast.gradeStartFailed"));
    }
  };

  const handleStopGrading = async () => {
    if (!selectedFolder || !activeGradingJobId) return;
    const jid = activeGradingJobId;
    refGradeCancelledRef.current = true;
    essayGradeCancelledRef.current = true;
    clearRefGradePollTimer();
    clearEssayGradePollTimer();
    try {
      if (gradingEngine === "essay")
        await cancelEssayGrade(selectedFolder, jid);
      else if (gradingEngine === "manual_reference")
        await cancelAnswerKeyGrade(selectedFolder, jid);
      else await cancelReferenceGrade(selectedFolder, jid);
      toast.success(t("grading.toast.gradeStopRequested"));
      try {
        const st =
          gradingEngine === "essay"
            ? await essayGradeStatus(selectedFolder, jid)
            : gradingEngine === "manual_reference"
              ? await answerKeyGradeStatus(selectedFolder, jid)
              : await referenceGradeStatus(selectedFolder, jid);
        if (st.ok) {
          setRefProgress({
            total: st.total,
            completed: (st.completed || []) as any,
            failed: st.failed || [],
            currentName: st.current_name || null,
          });
        }
        // 作文批改暂不写入 grading_history（避免与原两套互通），这里只刷新当前进度即可
        if (gradingEngine !== "essay") {
          const h = await fetchGradingHistory(
            selectedFolder,
            manualHistoryEngine(gradingEngine),
          );
          if (h.ok) {
            setGradingsPersisted({
              completed: (h.completed || []) as RefCompleted[],
              failed: h.failed || [],
            });
          }
        }
      } catch {
        //
      }
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.stopFailed"));
    } finally {
      setRefLoading(false);
      setActiveGradingJobId(null);
      if (gradingEngine === "essay") setStoredEssayJobId(selectedFolder, null);
      else setStoredJobId(selectedFolder, null);
    }
  };

  const toggleDeleteSelection = (filename: string) => {
    if (refLoading) return;
    setDeletingIds((prev) => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  };

  const toggleGradeSelection = (filename: string) => {
    if (refLoading) return;
    setSelectedGradeIds((prev) => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  };

  /** 从留痕图 URL 提取后端文件名（如 /api/v1/grading/modify/marks_only_xxx.jpg?t=123 -> marks_only_xxx.jpg） */
  const marksOnlyFilenameFromUrl = (url: string | undefined): string | null => {
    if (!url) return null;
    const nameWithQuery = url.split("/").pop() || "";
    const name = nameWithQuery.split("?")[0]; // 去除查询参数（如 ?t=时间戳）
    return name.startsWith("marks_only_") ? name : null;
  };

  /** 打印/导出用留痕文件名：「打印批注」开且带批注变体存在时用变体，否则普通留痕 */
  const marksFilenameForPrint = (
    item: {
      marks_only_filename?: string;
      marks_with_wrong_notes_filename?: string;
      image_marks_only?: string;
      image_marks_with_wrong_notes?: string;
    } | null | undefined,
  ): string | null => {
    if (!item) return null;
    const plain =
      item.marks_only_filename ||
      marksOnlyFilenameFromUrl(item.image_marks_only);
    const variant =
      item.marks_with_wrong_notes_filename ||
      marksOnlyFilenameFromUrl(item.image_marks_with_wrong_notes);
    return printWrongNotes && variant ? variant : plain;
  };

  const pageNoFromFilename = (filename: string) => {
    const { stem } = splitFilename(filename);
    const m = stem.match(/_(\d+)$/);
    return m ? Number(m[1]) : 1;
  };

  const studentBaseFromFilename = (filename: string) => {
    const { stem } = splitFilename(filename);
    return stem.replace(/_\d+$/, "");
  };

  const startScanImportAndRefresh = async () => {
    if (!selectedFolder) return;
    try {
      scanImportKnownFilesRef.current = new Set(
        studentFiles.map((f) => f.name),
      );
      await startScanImport(selectedFolder);
      setScanImportRunning(true);
      setScanError(false);
      setScanErrorMessage(null);
      scanErrorToastShownRef.current = false;
      toast.success(t("grading.toast.scanStarted"));
      loadFolderFiles(selectedFolder);
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.startFailed"));
    }
  };

  const stopScanImportAndRefresh = async () => {
    if (!selectedFolder) return;
    try {
      await stopScanImport();
      setScanImportRunning(false);
      setScanError(false);
      setScanErrorMessage(null);
      scanErrorToastShownRef.current = false;
      toast.success(t("grading.toast.scanStopped"));
      loadFolderFiles(selectedFolder);
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.stopFailed"));
    }
  };

  const handleTestPrint = async (file: File) => {
    setTestPrintOpen(true);
    setTestPrintPhase("grading");
    setTestPrintResult("");
    setTestPrintError("");
    setTestPrintLoading(true);
    try {
      const customPaper = getCustomPaperSetting((message) =>
        toast.error(message),
      );
      if (printPaperSize === "custom" && !customPaper) {
        setTestPrintError(t("grading.toast.printFailed"));
        setTestPrintPhase("error");
        return;
      }
      // 第一步：AI 批改，生成留痕
      const gradeRes = await printTestMarksGrade(file);
      if (!gradeRes.marks_only_filename) {
        throw new Error(t("grading.toast.printFailed"));
      }
      setTestPrintResult(gradeRes.result || "");
      // 第二步：打印留痕
      setTestPrintPhase("printing");
      const outputMode = printerOutputMode(selectedPrinter);
      if (outputMode === "pdf") {
        await exportMarksPdf([gradeRes.marks_only_filename]);
        setTestPrintPhase("done");
        toast.success(t("grading.toast.pdfDownloaded"));
        return;
      }
      if (outputMode === "browser") {
        await browserPrintMarksPdf([gradeRes.marks_only_filename]);
        setTestPrintPhase("done");
        toast.success(t("grading.testPrint.success"));
        return;
      }
      const printRes = await printMarks(
        gradeRes.marks_only_filename,
        resolvePrinterName(),
        printPaperSize,
        customPaper,
        paperSourceId > 0 ? paperSourceId : undefined,
      );
      if (!printRes.ok) {
        throw new Error(printRes.msg || t("grading.toast.printFailed"));
      }
      setTestPrintPhase("done");
      toast.success(printRes.msg || t("grading.testPrint.success"));
    } catch (error: unknown) {
      setTestPrintError(
        error instanceof Error
          ? error.message
          : t("grading.toast.printFailed"),
      );
      setTestPrintPhase("error");
    } finally {
      setTestPrintLoading(false);
      if (testPrintInputRef.current) testPrintInputRef.current.value = "";
    }
  };

  const handleBatchPrint = async (opts?: { onDone?: (st: any) => void }) => {
    let studentOrder: FolderFileItem[] = [];
    if (isManualEngine(gradingEngine) || sortedClassStudents.length > 0) {
      for (const box of paperBoxes) {
        studentOrder.push(...filesInPageOrder(box));
      }
      studentOrder.push(...unboxedStudentFiles);
    } else {
      studentOrder = folderFiles
        .filter(
          (f) =>
            !standardAnswer ||
            (f.name !== standardAnswer.filename &&
              f.name !== standardAnswer.name),
        )
        .sort((a, b) => {
          const ba = studentBaseFromFilename(a.name);
          const bb = studentBaseFromFilename(b.name);
          if (ba !== bb) {
            return ba.localeCompare(bb, "zh-Hans-CN", {
              numeric: true,
              sensitivity: "base",
            });
          }
          return pageNoFromFilename(a.name) - pageNoFromFilename(b.name);
        });
    }
    // 勾选模式下批量打印只打印勾选的试卷；无勾选保持全量打印
    if (selectGradeMode && selectedGradeIds.size > 0) {
      studentOrder = studentOrder.filter((f) => selectedGradeIds.has(f.name));
      if (studentOrder.length === 0) {
        toast.error(t("grading.toast.noSelectedPrintable"));
        return;
      }
    }
    studentOrder = sortFilesForPrint(studentOrder);
    const filenames = studentOrder
      .map((f) =>
        marksFilenameForPrint(completedByFilename[f.name]),
      )
      .filter((x): x is string => !!x);
    if (filenames.length === 0) {
      toast.error(t("grading.toast.noPrintableMarks"));
      return;
    }
    const customPaper = getCustomPaperSetting((msg) => toast.error(msg));
    if (printPaperSize === "custom" && !customPaper) return;
    const outputMode = printerOutputMode(selectedPrinter);
    if (outputMode === "pdf" || outputMode === "browser") {
      setPrintBatchLoading(true);
      try {
        if (outputMode === "pdf") {
          await exportMarksPdf(filenames);
          toast.success(t("grading.toast.pdfDownloaded"));
        } else {
          await browserPrintMarksPdf(filenames);
          toast.success(t("grading.toast.printSent"));
        }
      } catch (e: any) {
        toast.error(e?.message || t("grading.toast.printFailed"));
      } finally {
        setPrintBatchLoading(false);
      }
      try {
        opts?.onDone?.({ done: true, errors: [], cancelled: false });
      } catch {
        // 回调异常不影响原收尾逻辑
      }
      return;
    }
    setPrintBatchLoading(true);
    setActivePrintJobId(null);
    clearPrintBatchPollTimer();
    try {
      const start = await startPrintMarksBatch(
        filenames,
        resolvePrinterName(),
        printMode,
        printPaperSize,
        customPaper,
        paperSourceId > 0 ? paperSourceId : undefined,
      );
      if (!start.ok || !start.job_id) {
        toast.error(t("grading.toast.printRequestFailed"));
        setPrintBatchLoading(false);
        try {
          opts?.onDone?.({
            done: true,
            errors: [t("grading.toast.printRequestFailed")],
            cancelled: false,
          });
        } catch {
          // 回调异常不影响原收尾逻辑
        }
        return;
      }
      setActivePrintJobId(start.job_id);
      const poll = async () => {
        try {
          const st = await printMarksBatchStatus(start.job_id);
          if (st.ok && st.done) {
            clearPrintBatchPollTimer();
            setPrintBatchLoading(false);
            setActivePrintJobId(null);
            if (st.cancelled) {
              toast.success(
                printMode === "double"
                  ? t("grading.toast.printCancelledDuplex", {
                      count: st.printed,
                    })
                  : t("grading.toast.printCancelledSimple", {
                      count: st.printed,
                    }),
              );
            } else if (st.errors?.length) {
              toast.success(
                printMode === "double"
                  ? t("grading.toast.printPartialDuplex", {
                      count: st.printed,
                      errors: st.errors.length,
                    })
                  : t("grading.toast.printPartialSimple", {
                      count: st.printed,
                      errors: st.errors.length,
                    }),
              );
            } else {
              toast.success(
                printMode === "double"
                  ? t("grading.toast.printSentDuplex", { count: st.printed })
                  : t("grading.toast.printSentSimple", { count: st.printed }),
              );
            }
            try {
              opts?.onDone?.(st);
            } catch {
              // 回调异常不影响原收尾逻辑
            }
            return;
          }
        } catch {
          //
        }
        printBatchPollTimerRef.current = setTimeout(poll, 1200);
      };
      poll();
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.printFailed"));
      setPrintBatchLoading(false);
      setActivePrintJobId(null);
      clearPrintBatchPollTimer();
      try {
        opts?.onDone?.({
          done: true,
          errors: [e?.message || t("grading.toast.printFailed")],
          cancelled: false,
        });
      } catch {
        // 回调异常不影响原收尾逻辑
      }
    }
  };

  // ================= 一键编排（扫描→批阅→打印串行） =================
  // 供编排异步流程调用最新闭包的 handleBatchPrint（闭包陈旧读旧勾选会导致打印范围错误）
  latestHandleBatchPrintRef.current = (opts) => void handleBatchPrint(opts);
  // 供编排打印步读取最新可打印性（镜像 handleBatchPrint 的提前返回条件，避免打印步卡死）
  checkOrchestrPrintableRef.current = () => {
    let studentOrder = folderFiles.filter(
      (f) =>
        !standardAnswer ||
        (f.name !== standardAnswer.filename && f.name !== standardAnswer.name),
    );
    if (selectGradeMode && selectedGradeIds.size > 0) {
      studentOrder = studentOrder.filter((f) => selectedGradeIds.has(f.name));
    }
    const filenames = studentOrder
      .map((f) =>
        marksFilenameForPrint(completedByFilename[f.name]),
      )
      .filter((x): x is string => !!x);
    if (filenames.length === 0) return false;
    if (printPaperSize === "custom") {
      const customPaper = getCustomPaperSetting(() => {
        /* 静默校验，不打断流程 */
      });
      if (!customPaper) return false;
    }
    return true;
  };

  const orchestrateStepLabel = (step: OrchestrateStep) =>
    t(
      step === "scan"
        ? "grading.orchestrate.stepScan"
        : step === "grade"
          ? "grading.orchestrate.stepGrade"
          : "grading.orchestrate.stepPrint",
    );

  const orchestrationActiveStep = (): OrchestrateStep | null => {
    switch (orchestration.phase) {
      case "scanning":
        return "scan";
      case "grading":
        return "grade";
      case "printing":
        return "print";
      case "error":
        return orchestration.step;
      case "done":
        return "print";
      default:
        return null;
    }
  };

  const orchestrationStepState = (
    step: OrchestrateStep,
  ): "error" | "active" | "done" | "pending" => {
    if (!enabledSteps[step]) return "pending";
    if (orchestration.phase === "error" && orchestration.step === step)
      return "error";
    const activeStep = orchestrationActiveStep();
    const activeIdx = activeStep ? ORCHESTRATE_STEPS.indexOf(activeStep) : -1;
    const stepIdx = ORCHESTRATE_STEPS.indexOf(step);
    if (activeStep === step && orchestration.phase !== "done") return "active";
    if (
      orchestration.phase === "done" ||
      (activeIdx >= 0 && stepIdx < activeIdx)
    )
      return "done";
    return "pending";
  };

  const toggleOrchestrationStep = (step: OrchestrateStep) => {
    setEnabledSteps((prev) => {
      const next = { ...prev };
      next[step] = !next[step];
      return next;
    });
  };

  const handleOrchestrationPrintDone = (st: any) => {
    if (!orchestrationActiveRef.current) return;
    orchestrationActiveRef.current = false;
    if (st?.cancelled) {
      setOrchestration({ phase: "done" });
      return;
    }
    const errCount = (st?.errors || []).length;
    if (errCount > 0) {
      setOrchestration({ phase: "done" });
      toast.error(
        t("grading.orchestrate.error.printFailedCount", { count: errCount }),
      );
      return;
    }
    setOrchestration({ phase: "done" });
  };

  const runPrintStep = async () => {
    if (!orchestrationActiveRef.current) return;
    if (!selectedFolder) {
      orchestrationActiveRef.current = false;
      setOrchestration({
        phase: "error",
        step: "print",
        message: t("grading.orchestrate.error.noFolder"),
      });
      return;
    }
    // 批阅完成后 completedByFilename 有异步时间窗，先兜底刷新
    await loadFolderFiles(selectedFolder);
    if (!orchestrationActiveRef.current) return;
    // 从快照恢复勾选，让 handleBatchPrint 只打印编排批阅的子集
    if (orchestrationFilenamesRef.current?.length) {
      setSelectGradeMode(true);
      setSelectedGradeIds(new Set(orchestrationFilenamesRef.current));
    }
    // 置 printing 触发下方 effect：渲染后读取最新 completedByFilename / 勾选再打印
    setOrchestration({ phase: "printing" });
  };

  // 打印步真正的启动点：effect 在渲染后运行，读取最新状态，避免闭包陈旧读旧勾选
  useEffect(() => {
    if (orchestration.phase !== "printing") return;
    if (!orchestrationActiveRef.current) return;
    const gen = orchestrationPrintGenRef.current;
    if (!checkOrchestrPrintableRef.current()) {
      orchestrationActiveRef.current = false;
      setOrchestration({ phase: "done" });
      toast.error(t("grading.orchestrate.error.noPrintable"));
      return;
    }
    latestHandleBatchPrintRef.current({
      onDone: (st) => {
        // 代际校验：新编排启动后旧打印回调不再推进状态机
        if (orchestrationPrintGenRef.current !== gen) return;
        handleOrchestrationPrintDone(st);
      },
    });
    // 仅依赖 phase：打印轮询期间 phase 不变，不会重复触发；回调经 latest ref 读取最新值，无需列入依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orchestration.phase]);

  const handleOrchestrationGradeDone = (st: any) => {
    if (!orchestrationActiveRef.current) return;
    const failedCount = (st?.failed || []).length;
    if (failedCount > 0) {
      orchestrationActiveRef.current = false;
      setOrchestration({
        phase: "error",
        step: "grade",
        message: t("grading.orchestrate.error.gradeFailedCount", {
          count: failedCount,
        }),
      });
      return;
    }
    if (enabledSteps.print) {
      void runPrintStep();
    } else {
      orchestrationActiveRef.current = false;
      setOrchestration({ phase: "done" });
    }
  };

  const startOrchestrationGradeJob = async (gen: number) => {
    if (!orchestrationActiveRef.current) return;
    if (orchestrationGradeGenRef.current !== gen) return;
    if (!selectedFolder) return;
    orchestrationGradeStartedRef.current = true;
    const filenames = orchestrationFilenamesRef.current || undefined;
    setRefLoading(true);
    setRefProgress(null);
    setActiveGradingJobId(null);
    try {
      const activeRubric = essayRubrics.find((r) => r.id === activeRubricId);
      // startEssayGrade 只透传后端需要的作文提示词字段，剔除 UI 元数据
      const essayPrompts = activeRubric
        ? {
            summary_prompt: activeRubric.summary_prompt,
            comment_prompt: activeRubric.comment_prompt,
            rewrite_prompt: activeRubric.rewrite_prompt,
            guidance_prompt: activeRubric.guidance_prompt,
            scoring_prompt: activeRubric.scoring_prompt,
            topic_text: activeRubric.topic_text,
            topic_image_base64: activeRubric.topic_image_base64,
          }
        : undefined;
      const res =
        gradingEngine === "essay"
          ? await startEssayGrade(
              selectedFolder,
              activeRubric?.content?.trim() || "",
              undefined,
              filenames,
              essayPrompts,
              dingtalkPushMode === "auto",
            )
          : await startReferenceGrade(
              selectedFolder,
              gradingEngine,
              undefined,
              filenames,
              dingtalkPushMode === "auto",
            );
      // 编排可能已被中止（如等待期间切换文件夹/启动新编排）：不再启动轮询，避免游离任务
      if (
        !orchestrationActiveRef.current ||
        orchestrationGradeGenRef.current !== gen
      ) {
        setRefLoading(false);
        setActiveGradingJobId(null);
        return;
      }
      if (res.ok && res.job_id) {
        if (gradingEngine === "essay") {
          setStoredEssayJobId(selectedFolder, res.job_id);
        } else {
          setStoredJobId(selectedFolder, res.job_id);
          setGradingsPersisted({ completed: [], failed: [] });
          setDetailItem(null);
        }
        if (gradingEngine === "essay") {
          startEssayGradePolling(
            selectedFolder,
            res.job_id,
            undefined,
            (st) => {
              if (orchestrationGradeGenRef.current !== gen) return;
              handleOrchestrationGradeDone(st);
            },
          );
        } else {
          startRefGradePolling(selectedFolder, res.job_id, undefined, (st) => {
            if (orchestrationGradeGenRef.current !== gen) return;
            handleOrchestrationGradeDone(st);
          });
        }
      } else {
        orchestrationActiveRef.current = false;
        setRefLoading(false);
        setActiveGradingJobId(null);
        setOrchestration({
          phase: "error",
          step: "grade",
          message: t("grading.orchestrate.error.gradeStart"),
        });
      }
    } catch (e: any) {
      // 编排可能已被中止：不覆盖中止/取消状态
      if (
        !orchestrationActiveRef.current ||
        orchestrationGradeGenRef.current !== gen
      ) {
        setRefLoading(false);
        setActiveGradingJobId(null);
        return;
      }
      orchestrationActiveRef.current = false;
      setRefLoading(false);
      setActiveGradingJobId(null);
      setOrchestration({
        phase: "error",
        step: "grade",
        message: e?.message || t("grading.orchestrate.error.gradeStart"),
      });
    }
  };

  const runGradeStep = () => {
    if (!orchestrationActiveRef.current) return;
    if (!selectedFolder) return;
    if (isManualEngine(gradingEngine)) {
      orchestrationActiveRef.current = false;
      setOrchestration({
        phase: "error",
        step: "grade",
        message: t("grading.orchestrate.manualNotSupported"),
      });
      return;
    }
    // 批阅前快照勾选文件名（批阅会清空勾选）
    orchestrationFilenamesRef.current =
      selectGradeMode && selectedGradeIds.size > 0
        ? Array.from(selectedGradeIds)
        : null;
    setSelectGradeMode(false);
    setSelectedGradeIds(new Set());
    orchestrationGradeStartedRef.current = false;
    const gen = orchestrationGradeGenRef.current;
    setOrchestration({ phase: "grading" });
    // 隐私告知：复用现有 PrivacyNoticeDialog，确认后才真正启动批阅（不可绕过）
    setNoticePending(() => () => void startOrchestrationGradeJob(gen));
  };

  const runOrchestration = async () => {
    if (!selectedFolder) return;
    if (isManualEngine(gradingEngine)) {
      toast.error(t("grading.orchestrate.manualNotSupported"));
      return;
    }
    if (!enabledSteps.scan && !enabledSteps.grade && !enabledSteps.print) {
      toast.error(t("grading.orchestrate.noStep"));
      return;
    }
    orchestrationActiveRef.current = true;
    orchestrationFilenamesRef.current = null;
    // 新编排自增代际令牌，丢弃上一编排可能游离的 onDone
    orchestrationGradeGenRef.current += 1;
    orchestrationPrintGenRef.current += 1;
    if (enabledSteps.scan) {
      setOrchestration({ phase: "scanning" });
      await startScanImportAndRefresh();
      return; // 等待用户「扫描完成，下一步」或「跳过扫描」
    }
    if (enabledSteps.grade) {
      runGradeStep();
      return;
    }
    if (enabledSteps.print) {
      void runPrintStep();
      return;
    }
    orchestrationActiveRef.current = false;
    setOrchestration({ phase: "done" });
  };

  const advanceFromScan = async (skip: boolean) => {
    if (orchestration.phase !== "scanning") return;
    if (!orchestrationActiveRef.current) return;
    if (!skip && scanImportRunning) {
      await stopScanImportAndRefresh();
    }
    if (!orchestrationActiveRef.current) return;
    if (enabledSteps.grade) {
      runGradeStep();
    } else if (enabledSteps.print) {
      void runPrintStep();
    } else {
      orchestrationActiveRef.current = false;
      setOrchestration({ phase: "done" });
    }
  };

  const abortOrchestration = () => {
    orchestrationActiveRef.current = false;
    setOrchestration({ phase: "idle" });
    if (scanImportRunning && selectedFolder) {
      void stopScanImportAndRefresh();
    }
    if (activeGradingJobId) {
      void handleStopGrading();
    }
    if (activePrintJobId) {
      void handleCancelBatchPrint();
    }
    toast.info(t("grading.orchestrate.cancelled"));
  };

  const handleOrchestrationButtonClick = () => {
    if (orchestration.phase === "idle") {
      void runOrchestration();
    } else if (
      orchestration.phase === "scanning" ||
      orchestration.phase === "grading" ||
      orchestration.phase === "printing"
    ) {
      abortOrchestration();
    } else {
      // done / error：回到 idle
      orchestrationActiveRef.current = false;
      setOrchestration({ phase: "idle" });
    }
  };

  // 编排期间：切换文件夹/返回列表/切引擎 → 中止编排并提示
  useEffect(() => {
    const prev = orchestrationAbortGuardRef.current;
    orchestrationAbortGuardRef.current = {
      view,
      selectedFolder,
      gradingEngine,
    };
    if (
      prev.view === view &&
      prev.selectedFolder === selectedFolder &&
      prev.gradingEngine === gradingEngine
    ) {
      return;
    }
    if (
      orchestration.phase === "scanning" ||
      orchestration.phase === "grading" ||
      orchestration.phase === "printing"
    ) {
      orchestrationActiveRef.current = false;
      const step: OrchestrateStep =
        orchestration.phase === "grading"
          ? "grade"
          : orchestration.phase === "printing"
            ? "print"
            : "scan";
      setOrchestration({
        phase: "error",
        step,
        message: t("grading.orchestrate.cancelled"),
      });
      toast.error(t("grading.orchestrate.cancelled"));
    }
  }, [view, selectedFolder, gradingEngine, orchestration, t]);

  // 编排完成：几秒后自动回到 idle（用户也可点按钮关闭）
  useEffect(() => {
    if (orchestration.phase !== "done") return;
    const timer = setTimeout(() => {
      setOrchestration((prev) =>
        prev.phase === "done" ? { phase: "idle" } : prev,
      );
    }, 6000);
    return () => clearTimeout(timer);
  }, [orchestration.phase]);

  // 隐私告知弹窗被取消（noticePending 清空但批阅尚未启动）→ 编排中止回 idle
  useEffect(() => {
    if (
      orchestration.phase === "grading" &&
      noticePending === null &&
      !orchestrationGradeStartedRef.current
    ) {
      orchestrationActiveRef.current = false;
      setOrchestration({ phase: "idle" });
      toast.error(t("grading.orchestrate.cancelled"));
    }
  }, [orchestration.phase, noticePending, t]);

  const handleCancelBatchPrint = async () => {
    if (!activePrintJobId) return;
    try {
      await cancelPrintMarksBatch(activePrintJobId);
      toast.success(t("grading.toast.printCancelRequested"));
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.printCancelFailed"));
    }
  };

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const essayReportName = (name: string) => {
    const base =
      String(name || "")
        .replace(/\.[^/.]+$/, "")
        .trim() || t("grading.unnamed");
    const m = base.match(/^(.*?)_\d+$/);
    const cleanBase = m ? m[1] : base;
    return t("grading.essay.reportSuffix", { name: cleanBase });
  };

  /** 留痕 PDF 的文件名（同学生的 P1/P2 归到同一个名字，便于分组） */
  const essayImagesName = (name: string) => {
    const base =
      String(name || "")
        .replace(/\.[^/.]+$/, "")
        .trim() || t("grading.unnamed");
    const m = base.match(/^(.*?)_\d+$/);
    return `${m ? m[1] : base}_留痕`;
  };

  const handleEssayDownloadPdf = async (singleName?: string) => {
    if (!selectedFolder) return;
    try {
      let items = singleName
        ? getEssayCompletedItems().filter((x) => x.name === singleName)
        : getEssayCompletedItems();

      // 注意：这里不能按学生去重——图片版 PDF 里同一学生的 P1/P2 是各自独立的内容，
      // 去重会把第 2 页整页丢掉（旧代码是文字报告，每人一份，才需要去重）。

      if (!items.length) {
        toast.error(t("grading.toast.noEssayToDownload"));
        return;
      }
      // 单张：按“XX_留痕.pdf”下载
      if (singleName) {
        const one = items[0];
        const nm = essayImagesName(one.name);
        const blob = await downloadEssayGradePdf(
          selectedFolder,
          [one],
          `${nm}.pdf`,
          { mode: "images", includeOriginal: false },
        );
        downloadBlob(blob, `${nm}.pdf`);
        toast.success(t("grading.toast.pdfDownloaded"));
        return;
      }

      // 一键下载：全部学生合成一个 PDF，每页一张留痕图（无原卷、无文字报告）
      const allName = "全部留痕.pdf";
      const blob = await downloadEssayGradePdf(
        selectedFolder,
        items,
        allName,
        { mode: "images", includeOriginal: false },
      );
      downloadBlob(blob, allName);
      toast.success(t("grading.toast.pdfDownloaded"));
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.downloadFailed"));
    }
  };

  const handleEssayPrintPdf = async (singleName?: string) => {
    if (!selectedFolder) return;
    try {
      const customPaper = getCustomPaperSetting((msg) => toast.error(msg));
      if (printPaperSize === "custom" && !customPaper) return;
      let items = singleName
        ? getEssayCompletedItems().filter((x) => x.name === singleName)
        : getEssayCompletedItems();

      // 勾选模式下批量打印只打印勾选的作文；无勾选保持全量打印
      if (!singleName && selectGradeMode && selectedGradeIds.size > 0) {
        items = items.filter((it) => selectedGradeIds.has(it.name));
      }

      // 批量打印时去重，避免同一个学生的多张图片导致重复打印相同的报告
      if (!singleName) {
        const seen = new Set<string>();
        items = items.filter((it) => {
          const report = essayReportName(it.name);
          if (seen.has(report)) return false;
          seen.add(report);
          return true;
        });
      }

      if (!items.length) {
        toast.error(t("grading.toast.noEssayToPrint"));
        return;
      }
      const outputMode = printerOutputMode(selectedPrinter);
      if (outputMode === "pdf" || outputMode === "browser") {
        // 逐张生成作文批改报告（与 handleEssayDownloadPdf 逻辑一致）
        let okCount = 0;
        for (const it of items) {
          const report = essayReportName(it.name);
          if (outputMode === "pdf") {
            await exportEssayGradePdf(selectedFolder, [it], `${report}.pdf`);
          } else {
            await browserPrintEssayGradePdf(selectedFolder, [it]);
          }
          okCount += 1;
          // 给浏览器一点时间处理多个下载/弹窗，降低被拦截概率
          await new Promise((r) => setTimeout(r, 80));
        }
        if (outputMode === "pdf") {
          toast.success(t("grading.toast.pdfsDownloaded", { count: okCount }));
        } else {
          toast.success(t("grading.toast.printSent"));
        }
        return;
      }
      const res = await printEssayGradePdf(
        selectedFolder,
        items,
        resolvePrinterName(),
        printPaperSize,
        customPaper,
        paperSourceId > 0 ? paperSourceId : undefined,
        printMode,
      );
      if (res.ok) toast.success(res.msg || t("grading.toast.printSent"));
      else toast.error(res.msg || t("grading.toast.printFailed"));
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.printFailed"));
    }
  };

  const handlePrintOne = async () => {
    if (!detailItem?.image_marks_only) return;
    const filename = marksFilenameForPrint(detailItem);
    if (!filename) {
      toast.error(t("grading.toast.noMarkFilename"));
      return;
    }
    setPrintOneLoading(true);
    try {
      const customPaper = getCustomPaperSetting((msg) => toast.error(msg));
      if (printPaperSize === "custom" && !customPaper) {
        setPrintOneLoading(false);
        return;
      }
      const outputMode = printerOutputMode(selectedPrinter);
      if (outputMode === "pdf") {
        await exportMarksPdf([filename]);
        toast.success(t("grading.toast.pdfDownloaded"));
        return;
      }
      if (outputMode === "browser") {
        await browserPrintMarksPdf([filename]);
        toast.success(t("grading.toast.printSent"));
        return;
      }
      const res = await printMarks(
        filename,
        resolvePrinterName(),
        printPaperSize,
        customPaper,
        paperSourceId > 0 ? paperSourceId : undefined,
      );
      if (res.ok) {
        toast.success(res.msg || t("grading.toast.printSent"));
      } else {
        toast.error(t("grading.toast.printFailed"));
      }
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.printFailed"));
    } finally {
      setPrintOneLoading(false);
    }
  };

  const handleExportMarksPdfOne = async () => {
    if (!detailItem?.image_marks_only) return;
    const filename = marksFilenameForPrint(detailItem);
    if (!filename) {
      toast.error(t("grading.toast.noMarkFilename"));
      return;
    }
    setExportPdfOneLoading(true);
    try {
      const blob = await downloadMarksPdf([filename]);
      downloadBlob(blob, `${filename.replace(/\.[^.]+$/, "")}.pdf`);
      toast.success(t("grading.toast.pdfExported"));
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.printFailed"));
    } finally {
      setExportPdfOneLoading(false);
    }
  };

  const handleBrowserPrintOne = async () => {
    if (!detailItem?.image_marks_only) return;
    const filename = marksFilenameForPrint(detailItem);
    if (!filename) {
      toast.error(t("grading.toast.noMarkFilename"));
      return;
    }
    setBrowserPrintOneLoading(true);
    try {
      await browserPrintMarksPdf([filename]);
      toast.success(t("grading.toast.browserPrintOpened"));
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.printFailed"));
    } finally {
      setBrowserPrintOneLoading(false);
    }
  };

  const handleRotateFile = async (
    file: FolderFileItem,
    direction: "left" | "right",
    completed?: RefCompleted | null,
  ) => {
    if (rotatingFileName) return;
    setRotatingFileName(file.name);
    try {
      // 已批改：用 marks_only 文件名定位 stem，整套（留痕三图 + 预览 + 原卷）一起转；
      // 未批改：直接传原始文件名（无 original_ 前缀），后端转预览 + 原卷。
      const marksFilename = completed?.image_marks_only
        ? marksOnlyFilenameFromUrl(completed.image_marks_only)
        : undefined;
      await rotateImage(
        marksFilename || file.name,
        direction,
        selectedFolder || undefined,
        file.name,
      );
      // 旋转后给预览 URL 追加缓存破坏参数，强制刷新
      const bust = (url?: string) =>
        url ? `${url}${url.includes("?") ? "&" : "?"}v=${Date.now()}` : url;
      setFolderFiles((prev) =>
        prev.map((f) => (f.name === file.name ? { ...f, url: bust(f.url) } : f)),
      );
      // 详情页若正打开这张，也一并刷新
      setDetailItem((prev) =>
        prev && prev.name === file.name
          ? {
              ...prev,
              image_original: bust(prev.image_original),
              image_annotated: bust(prev.image_annotated),
              image_marks_only: bust(prev.image_marks_only),
            }
          : prev,
      );
      toast.success(t("grading.toast.rotated"));
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.rotateFailed"));
    } finally {
      setRotatingFileName(null);
    }
  };

  const collectPrintableMarkFilenames = (): string[] | null => {
    let studentOrder: FolderFileItem[] = [];
    if (isManualEngine(gradingEngine) || sortedClassStudents.length > 0) {
      for (const box of paperBoxes) {
        studentOrder.push(...filesInPageOrder(box));
      }
      studentOrder.push(...unboxedStudentFiles);
    } else {
      studentOrder = folderFiles
        .filter(
          (f) =>
            !standardAnswer ||
            (f.name !== standardAnswer.filename &&
              f.name !== standardAnswer.name),
        )
        .sort((a, b) => {
          const ba = studentBaseFromFilename(a.name);
          const bb = studentBaseFromFilename(b.name);
          if (ba !== bb) {
            return ba.localeCompare(bb, "zh-Hans-CN", {
              numeric: true,
              sensitivity: "base",
            });
          }
          return pageNoFromFilename(a.name) - pageNoFromFilename(b.name);
        });
    }
    if (selectGradeMode && selectedGradeIds.size > 0) {
      studentOrder = studentOrder.filter((f) => selectedGradeIds.has(f.name));
      if (studentOrder.length === 0) {
        toast.error(t("grading.toast.noSelectedPrintable"));
        return null;
      }
    }
    studentOrder = sortFilesForPrint(studentOrder);
    const filenames = studentOrder
      .map((f) =>
        marksFilenameForPrint(completedByFilename[f.name]),
      )
      .filter((x): x is string => !!x);
    if (filenames.length === 0) {
      toast.error(t("grading.toast.noPrintableMarks"));
      return null;
    }
    return filenames;
  };

  const handleExportMarksPdfAll = async () => {
    const filenames = collectPrintableMarkFilenames();
    if (!filenames) return;
    setExportPdfLoading(true);
    try {
      const blob = await downloadMarksPdf(filenames);
      downloadBlob(blob, `marks_${filenames.length}.pdf`);
      toast.success(t("grading.toast.pdfExported"));
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.printFailed"));
    } finally {
      setExportPdfLoading(false);
    }
  };

  const handleBrowserPrintAll = async () => {
    const filenames = collectPrintableMarkFilenames();
    if (!filenames) return;
    setBrowserPrintLoading(true);
    try {
      await browserPrintMarksPdf(filenames);
      toast.success(t("grading.toast.browserPrintOpened"));
    } catch (e: any) {
      toast.error(e?.message || t("grading.toast.printFailed"));
    } finally {
      setBrowserPrintLoading(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!selectedFolder || deletingIds.size === 0) {
      setDeleteConfirmOpen(false);
      return;
    }
    setDeleteExecuting(true);
    const total = deletingIds.size;
    const failed: string[] = [];
    let lastError: any = null;
    for (const filename of deletingIds) {
      try {
        await deleteFolderFile(selectedFolder, filename);
      } catch (e: any) {
        // 单个失败不中断整批；失败的留在选中集里。结束时无条件刷新列表，
        // 免得已删掉的文件还挂在列表上、下次重试报「文件不存在」。
        failed.push(filename);
        lastError = e;
      }
    }
    if (failed.length === 0) {
      toast.success(t("grading.toast.filesDeleted", { count: total }));
      setDeletingIds(new Set());
      setDeleteMode(false);
    } else {
      toast.error(lastError?.message || t("grading.start.deleteFailed"));
      setDeletingIds(new Set(failed));
    }
    setDeleteConfirmOpen(false);
    setDeleteExecuting(false);
    loadFolderFiles(selectedFolder);
  };

  const openZoomPreview = (url: string, studentFilename?: string | null) => {
    if (!url) return;
    setZoomImageUrl(url);
    setZoomStudentFilename(studentFilename ?? null);
  };

  const completedByFilename = useMemo(() => {
    const merged: Record<string, RefCompleted> = {};
    for (const c of gradingsPersisted?.completed ?? []) {
      if (c?.name) merged[c.name] = c;
    }
    for (const c of refProgress?.completed ?? []) {
      if (!c?.name) continue;
      const existing = merged[c.name];
      if (
        !existing ||
        getCompletedItemRichness(c) >= getCompletedItemRichness(existing)
      ) {
        merged[c.name] = c;
      }
    }
    return merged;
  }, [gradingsPersisted, refProgress]);

  const firstSmartCompletedItem = useMemo(() => {
    if (gradingEngine !== "baidu" && gradingEngine !== "aliyun") return null;
    for (const f of folderFiles) {
      if (
        standardAnswer &&
        (f.name === standardAnswer.filename || f.name === standardAnswer.name)
      )
        continue;
      const item = completedByFilename[f.name];
      if (!item?.result) continue;
      const titles = extractAiScoringTitlesFromBlocks(
        parseAiResultBlocks(String(item.result), t),
      );
      if (titles.length > 0) return item;
    }
    return null;
  }, [completedByFilename, folderFiles, gradingEngine, standardAnswer, t]);

  const scoringQuestionTitles = useMemo(() => {
    if (gradingEngine !== "baidu" && gradingEngine !== "aliyun") return [];
    // 已有统分配置（自动识别/保存过）：题清单以配置键为准——标准答题区路径下
    // 它就是老师手改过的答题区题清单，比批改结果文本（页内题号、可能缺页）更全更准。
    const fromConfig = Object.keys(scoringConfig || {});
    if (fromConfig.length > 0)
      return fromConfig.sort((a, b) =>
        a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }),
      );
    if (!firstSmartCompletedItem?.result) return [];
    return extractAiScoringTitlesFromBlocks(
      parseAiResultBlocks(String(firstSmartCompletedItem.result), t),
    ).sort((a, b) =>
      a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }),
    );
  }, [scoringConfig, firstSmartCompletedItem?.result, gradingEngine, t]);

  const scoringQuestionGroups = useMemo(() => {
    if (gradingEngine !== "baidu" && gradingEngine !== "aliyun") return [];

    // 有纸面小题清单（大题→小题）时，按「大题 + 小题」展示（不放题干，只出题号 + 分数框）。
    // 大题顺序一律跟随 majorOrder（一/二/三/四…），即使某大题下暂时没有小题也要显示大题头；
    // 缺失时退回 paperSubs/majorScores 的键，保证一/二/三/四大题全部出现。
    const orderedMajors: string[] = [];
    for (const m of majorOrder) if (!orderedMajors.includes(m)) orderedMajors.push(m);
    for (const m of Object.keys(paperSubs)) if (!orderedMajors.includes(m)) orderedMajors.push(m);
    for (const m of Object.keys(majorScores)) if (!orderedMajors.includes(m)) orderedMajors.push(m);

    if (orderedMajors.length > 0) {
      // 每题分数框的归属：structure.major → 大题。大题下没有纸面小题行时（标准答题区路径
      // paper_subs 为空、或卷面某大题没切出小题），直接给逐题行，保证每道题都有分数框可改。
      const used = new Set<string>();
      const groups = orderedMajors.map((major) => {
        const subs = paperSubs[major] || [];
        const titles: string[] = [];
        if (subs.length === 0) {
          for (const title of scoringQuestionTitles) {
            const m = String(questionStructure?.[title]?.major || "").trim();
            if (m === major) {
              titles.push(title);
              used.add(title);
            }
          }
        }
        return { major, subs, titles, hasSubItems: true };
      });
      const orphans = scoringQuestionTitles.filter((title) => !used.has(title));
      // 没归属到任何大题的题（匹配失败/结构缺失）平铺到末尾，别把题弄丢
      if (orphans.length > 0) {
        groups.push({ major: "", subs: [], titles: orphans, hasSubItems: false });
      }
      return groups;
    }

    // 兜底：无纸面结构时退回「题目块」平铺（老逻辑，题块标题 + 分数框）
    const titles = extractAiScoringTitlesFromBlocks(
      parseAiResultBlocks(String(firstSmartCompletedItem?.result ?? ""), t),
    ).sort((a, b) =>
      a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }),
    );
    if (titles.length === 0) return [];
    return [{ major: "", subs: [], titles, hasSubItems: false }];
  }, [gradingEngine, majorOrder, paperSubs, majorScores, questionStructure, scoringQuestionTitles, firstSmartCompletedItem?.result, t]);

  // 打开统分设置时，若尚未分配分值，则自动触发 AI 自动分配分值（无需手动逐项填写）。
  // 题清单可以来自标准答题区（还没批改也能统分），所以不能只看批改结果标题。
  useEffect(() => {
    if (!scoringDialogOpen) {
      autoScoringTriggeredRef.current = false;
      return;
    }
    if (gradingEngine !== "baidu" && gradingEngine !== "aliyun") return;
    if (!selectedFolder) return;
    if (scoringQuestionTitles.length === 0 && standardAnswers.length === 0) return;
    if (Object.keys(scoringConfig).length > 0) return;
    if (autoScoringTriggeredRef.current) return;
    autoScoringTriggeredRef.current = true;
    void handleAutoScoringConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scoringDialogOpen, gradingEngine, selectedFolder, scoringQuestionTitles, scoringConfig, standardAnswers]);

  const getEssayCompletedItems = useCallback((): EssayPdfItem[] => {
    if (gradingEngine !== "essay") return [];
    const items: EssayPdfItem[] = [];

    let orderedFiles: FolderFileItem[] = [];
    if (sortedClassStudents.length > 0) {
      for (const box of paperBoxes) {
        orderedFiles.push(...filesInPageOrder(box));
      }
      orderedFiles.push(...unboxedStudentFiles);
    } else {
      orderedFiles = folderFiles.filter(
        (x) =>
          !standardAnswer ||
          (x.name !== standardAnswer.filename &&
            x.name !== standardAnswer.name),
      );
    }

    for (const f of orderedFiles) {
      const c: any = completedByFilename[f.name];
      if (c?.name && c?.result) {
        // 作文 PDF 直接用批改原文（含【作文得分】等板块），避免 parseAiResultBlocks 套上「总览」标题
        const raw = String(c.result || "")
          .replace(/<essay_score>[\s\S]*?<\/essay_score>/g, "")
          .trim();
        items.push({
          name: c.name,
          result: raw,
          ocr_title: c.ocr_title,
          ocr_content: c.ocr_content,
          // 下载「图片版 PDF」时要用：原卷 + 留痕
          image_original: c.image_original,
          image_annotated: c.image_annotated,
          image_marks_only: c.image_marks_only,
        });
      }
    }
    return items;
  }, [
    gradingEngine,
    folderFiles,
    standardAnswer,
    completedByFilename,
    sortedClassStudents,
    paperBoxes,
    unboxedStudentFiles,
    filesInPageOrder,
  ]);

  /** 根据文件名或 type 判断显示类型，避免后端未返回 type 时误当图片 */
  const fileType = (f: {
    name?: string;
    filename?: string;
    type?: string;
  }): "pdf" | "word" | "image" => {
    if (f.type === "pdf" || f.type === "word") return f.type;
    const name = (f.filename ?? f.name ?? "").toLowerCase();
    if (name.endsWith(".pdf")) return "pdf";
    if (name.endsWith(".doc") || name.endsWith(".docx")) return "word";
    return "image";
  };

  const studentCount = studentFiles.length;
  const selectableStudentIds = useMemo(
    () => studentFiles.map((f) => f.name),
    [studentFiles],
  );
  const allSelectedForGrade =
    selectGradeMode &&
    selectableStudentIds.length > 0 &&
    selectableStudentIds.every((id) => selectedGradeIds.has(id));

  const deletableIdsInView = useMemo(() => {
    const ids: string[] = [];
    if (gradingEngine === "aliyun" || gradingEngine === "smart_ref") {
      ids.push(...standardAnswers.map((item) => item.filename));
    }
    for (const f of studentFiles) {
      ids.push(f.name);
    }
    return ids;
  }, [gradingEngine, standardAnswers, studentFiles]);

  const allSelectedInDeleteMode =
    deleteMode &&
    deletableIdsInView.length > 0 &&
    deletableIdsInView.every((id) => deletingIds.has(id));

  /** 按学生聚合：班级模式用试卷框，否则按文件名前缀分组 */
  const studentPaperGroups = useMemo(() => {
    if (sortedClassStudents.length > 0) {
      return paperBoxes
        .filter((b) => b.files.length > 0)
        .map((b) => ({
          key: b.student.id,
          files: b.files.map((f) => f.name),
        }));
    }
    const groups = new Map<string, string[]>();
    for (const f of studentFiles) {
      const key = getEssayGroupBaseName(f.name);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(f.name);
    }
    return Array.from(groups.entries()).map(([key, files]) => ({ key, files }));
  }, [sortedClassStudents.length, paperBoxes, studentFiles]);

  const progressTotal = studentPaperGroups.length;
  const progressDone = useMemo(() => {
    return studentPaperGroups.filter((g) =>
      g.files.every((name) =>
        isFileMarkedGraded(name, completedByFilename, gradingEngine),
      ),
    ).length;
  }, [studentPaperGroups, completedByFilename, gradingEngine]);

  const pushToClassReview = useCallback(async () => {
    if (!selectedFolder || classReviewPushingRef.current) return;
    classReviewPushingRef.current = true;
    setClassReviewPushState({ status: "pushing", subject: selectedSubject });
    setClassReviewPushOpen(true);
    try {
      let res = await importClassReviewExams({
        class_id: selectedClass,
        subject: selectedSubject,
        exam_folder_names: [selectedFolder],
      });
      // 错题记录仍在生成中（pending）：等 5 秒重试，最多约 100 秒，避免推送半截快照
      let retries = 0;
      while (res?.pending && retries < 20) {
        await new Promise((r) => setTimeout(r, 5000));
        res = await importClassReviewExams({
          class_id: selectedClass,
          subject: selectedSubject,
          exam_folder_names: [selectedFolder],
        });
        retries += 1;
      }
      if (res?.pending) {
        setClassReviewPushState({
          status: "error",
          message: t("grading.classReviewPush.pendingTimeout"),
          subject: selectedSubject,
        });
        return;
      }
      markClassReviewPushed(selectedFolder, selectedSubject);
      setClassReviewPushState({ status: "success", subject: selectedSubject });
    } catch (e: any) {
      setClassReviewPushState({
        status: "error",
        message: e?.message || t("grading.classReviewPush.failed"),
        subject: selectedSubject,
      });
    } finally {
      classReviewPushingRef.current = false;
    }
  }, [selectedFolder, selectedClass, selectedSubject, t]);

  /** 手动推一次钉钉工作通知（「手动推送」模式下的按钮） */
  const handleManualDingtalkPush = async () => {
    if (!selectedFolder || dingtalkPushing) return;
    const kind =
      gradingEngine === "essay"
        ? "essay"
        : isManualEngine(gradingEngine)
          ? "manual"
          : "grading_done";
    setDingtalkPushing(true);
    try {
      const res = await pushDingtalkNotify(selectedFolder, kind);
      if (res.ok) {
        toast.success(res.message || t("grading.dingtalkPush.sent"));
      } else {
        toast.error(res.message || t("grading.dingtalkPush.failed"));
      }
    } catch (e: any) {
      toast.error(e?.message || t("grading.dingtalkPush.failed"));
    } finally {
      setDingtalkPushing(false);
    }
  };

  // 整批批改完成时自动推送一次到「课堂讲评」，并在弹窗中提示（需手动开启开关）
  useEffect(() => {
    if (!autoPushClassReview) return;
    if (view !== "folder" || !selectedFolder) return;
    if (progressTotal === 0 || progressDone !== progressTotal) return;
    if (refLoading) return;
    if (hasPushedClassReview(selectedFolder, selectedSubject)) return;
    void pushToClassReview();
  }, [
    autoPushClassReview,
    view,
    selectedFolder,
    progressDone,
    progressTotal,
    refLoading,
    selectedSubject,
    pushToClassReview,
  ]);

  useEffect(() => {
    if (!previewPaperBoxStudentId) return;
    syncPaperBoxDetailItem(previewPaperBoxStudentId, previewPaperBoxPageNo);
  }, [previewPaperBoxStudentId, previewPaperBoxPageNo, syncPaperBoxDetailItem]);

  const gradingPreviewOpen = Boolean(detailItem);
  const paperBoxPreviewMode = Boolean(
    previewPaperBoxStudentId && activePaperBox,
  );
  const manualGradingSource = useMemo(
    () =>
      folderFiles.find((file) => file.name === manualGradingItem?.name) || null,
    [folderFiles, manualGradingItem?.name],
  );
  const manualOtherPagesScore = useMemo(() => {
    if (!manualGradingItem?.name) return 0;
    const boxName = getEssayGroupBaseName(manualGradingItem.name);
    const completed = gradingsPersisted?.completed || [];
    return completed.reduce((sum, item) => {
      if (
        item.name === manualGradingItem.name ||
        getEssayGroupBaseName(item.name) !== boxName
      )
        return sum;
      return sum + getManualResultScore(item);
    }, 0);
  }, [gradingsPersisted?.completed, manualGradingItem?.name]);
  const manualHasNext = useMemo(() => {
    if (!manualGradingItem?.name) return false;
    const index = folderFiles.findIndex(
      (file) => file.name === manualGradingItem.name,
    );
    return index >= 0 && index + 1 < folderFiles.length;
  }, [folderFiles, manualGradingItem?.name]);
  const manualHasPrev = useMemo(() => {
    if (!manualGradingItem?.name) return false;
    const index = folderFiles.findIndex(
      (file) => file.name === manualGradingItem.name,
    );
    return index > 0;
  }, [folderFiles, manualGradingItem?.name]);

  const detailAiBlocks = useMemo(
    () => parseAiResultBlocks(detailItem?.result || "", t),
    [detailItem?.result, t],
  );
  const detailSourceFile = useMemo(
    () => folderFiles.find((f) => f.name === detailItem?.name) ?? null,
    [folderFiles, detailItem?.name],
  );
  const detailManualBlocks = useMemo(() => {
    if (!isManualEngine(gradingEngine) || !detailItem?.result) return [];
    try {
      const parsed = JSON.parse(detailItem.result || "{}");
      return Array.isArray(parsed.blocks) ? parsed.blocks : [];
    } catch {
      return [];
    }
  }, [gradingEngine, detailItem?.result]);
  const detailManualStatus = useMemo(() => {
    if (!isManualEngine(gradingEngine) || !detailItem?.result) return "";
    try {
      const parsed = JSON.parse(detailItem.result || "{}");
      return String(parsed.manual_status || "");
    } catch {
      return "";
    }
  }, [gradingEngine, detailItem?.result]);
  const manualHasFinalMarks = detailManualStatus
    ? detailManualStatus === "graded"
    : Boolean(detailItem?.image_marks_only || detailItem?.marks_only_filename);
  const isManualRegrading =
    isManualEngine(gradingEngine) &&
    !!detailItem?.name &&
    manualEditingName === detailItem.name;
  const showManualScoreInputs =
    isManualEngine(gradingEngine) && (isManualRegrading || !manualHasFinalMarks);
  useEffect(() => {
    if (
      !isManualEngine(gradingEngine) ||
      !detailItem?.name ||
      !showManualScoreInputs
    )
      return;
    const currentKey = `${detailItem.name}::${serializeManualScores(manualGradeScores)}`;
    if (currentKey === lastManualAutosaveKeyRef.current) return;
    if (manualAutosaveTimerRef.current)
      clearTimeout(manualAutosaveTimerRef.current);
    manualAutosaveTimerRef.current = setTimeout(() => {
      persistManualScores(manualGradeScores, false)
        .then((savedItem) => {
          if (savedItem) {
            lastManualAutosaveKeyRef.current = currentKey;
          }
        })
        .catch((err) => {
          console.error("自动保存分数失败:", err);
        })
        .finally(() => {
          manualAutosaveTimerRef.current = null;
        });
    }, 350);
    return () => {
      if (manualAutosaveTimerRef.current) {
        clearTimeout(manualAutosaveTimerRef.current);
        manualAutosaveTimerRef.current = null;
      }
    };
  }, [
    detailItem?.name,
    gradingEngine,
    manualGradeScores,
    persistManualScores,
    showManualScoreInputs,
  ]);
  const detailManualGroups = useMemo(() => {
    if (!isManualEngine(gradingEngine)) return [];
    const groups = new Map<
      string,
      {
        key: string;
        index: number;
        type: unknown;
        title: string;
        questionText: string;
        optionText: string;
        interpretationText: string;
        slots: Array<{
          scoreKey: string;
          label: string;
          answerText: string;
          bbox: unknown;
        }>;
        statuses: string[];
      }
    >();

    detailManualBlocks.forEach((b: any, idx: number) => {
      const index = Number(b?.index || idx + 1);
      const key = String(index);
      const existing = groups.get(key);
      const stemText = normalizeManualText(b?.stem_text);
      const blockText = normalizeManualText(b?.text);
      const optionText = normalizeManualText(b?.option_text);
      const interpretationText = normalizeManualText(b?.interpretation_text);
      const answerText = normalizeManualText(b?.answer_text);
      const scoreKey = b?.is_sub
        ? `第${index}题-作答区${b?.sub_index}`
        : `第${index}题`;
      const slotLabel = b?.is_sub ? `作答区 ${b?.sub_index}` : "作答区";
      const questionText = normalizeManualText(
        stemText ||
          (!b?.is_sub ? blockText : "") ||
          (existing?.questionText ?? ""),
      );
      const slotAnswerText = normalizeManualText(answerText || blockText);

      if (!existing) {
        groups.set(key, {
          key,
          index,
          type: b?.type,
          title: `第${index}题`,
          questionText,
          optionText,
          interpretationText,
          slots: [
            {
              scoreKey,
              label: slotLabel,
              answerText: slotAnswerText,
              bbox: b?.bbox,
            },
          ],
          statuses: [String(b?.status || "")],
        });
        return;
      }

      if (!existing.questionText && questionText)
        existing.questionText = questionText;
      if (!existing.optionText && optionText) existing.optionText = optionText;
      if (!existing.interpretationText && interpretationText)
        existing.interpretationText = interpretationText;
      existing.slots.push({
        scoreKey,
        label: slotLabel,
        answerText: slotAnswerText,
        bbox: b?.bbox,
      });
      existing.statuses.push(String(b?.status || ""));
    });

    return Array.from(groups.values()).sort((a, b) => a.index - b.index);
  }, [detailManualBlocks, gradingEngine]);
  const detailPreviewPath = useMemo(() => {
    if (!detailItem) return "";
    // 带错因批注的卷面变体（「显示批注」开时优先，无变体时回退普通卷面）
    const annotatedWithNotes =
      previewWrongNotes && !detailShowOriginal && !isManualRegrading
        ? detailItem.image_annotated_with_wrong_notes || null
        : null;
    if (isManualEngine(gradingEngine)) {
      if (detailShowOriginal || isManualRegrading) {
        return (
          detailItem.image_original ||
          detailSourceFile?.url ||
          detailItem.image_annotated ||
          ""
        );
      }
      if (manualHasFinalMarks) {
        return (
          annotatedWithNotes ||
          detailItem.image_annotated ||
          detailItem.image_original ||
          detailSourceFile?.url ||
          ""
        );
      }
      return (
        detailItem.image_original ||
        detailSourceFile?.url ||
        detailItem.image_annotated ||
        ""
      );
    }
    return detailShowOriginal
      ? detailItem.image_original ||
          detailItem.image_annotated ||
          detailSourceFile?.url ||
          ""
      : annotatedWithNotes ||
          detailItem.image_annotated ||
          detailItem.image_original ||
          detailSourceFile?.url ||
          "";
  }, [
    detailItem,
    detailShowOriginal,
    detailSourceFile?.url,
    gradingEngine,
    isManualRegrading,
    manualHasFinalMarks,
    previewWrongNotes,
  ]);

  const paperBoxPreviewAnimClass = cn(
    paperBoxSlideDirection > 0 &&
      "animate-in fade-in slide-in-from-right-4 duration-300",
    paperBoxSlideDirection < 0 &&
      "animate-in fade-in slide-in-from-left-4 duration-300",
    paperBoxSlideDirection === 0 &&
      paperBoxPreviewMode &&
      "animate-in fade-in duration-200",
  );

  const renderPaperBoxPageSidebar = () => {
    if (!paperBoxPreviewMode || !activePaperBox) return null;
    return (
      <div className="flex min-h-0 flex-row gap-0 border-b bg-muted/20 lg:flex-col lg:border-b-0 lg:border-r lg:py-3">
        <div className="flex flex-1 flex-row gap-1 overflow-x-auto p-2 lg:flex-col lg:overflow-y-auto lg:px-2">
          {Array.from({ length: paperBoxCapacity }, (_, i) => i + 1).map(
            (page) => {
              const slot = activePaperBox.slots[page - 1];
              const active = page === previewPaperBoxPageNo;
              return (
                <button
                  key={page}
                  type="button"
                  title={
                    slot
                      ? slot.name
                      : t("grading.paperBox.uploadPageTitle", { page })
                  }
                  className={cn(
                    "relative flex h-10 w-10 shrink-0 flex-col items-center justify-center rounded-lg border text-[11px] font-semibold transition-all duration-200 lg:h-12 lg:w-full",
                    active
                      ? "border-primary bg-primary text-primary-foreground shadow-sm scale-[1.02]"
                      : slot
                        ? "border-emerald-200/80 bg-emerald-50/80 text-emerald-800 hover:border-emerald-300"
                        : "border-dashed border-muted-foreground/35 bg-background text-muted-foreground hover:border-primary/40 hover:bg-muted/50",
                  )}
                  onClick={() => switchPaperBoxPage(page)}
                >
                  P{page}
                  {slot && !active && (
                    <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-background" />
                  )}
                </button>
              );
            },
          )}
        </div>
      </div>
    );
  };

  const renderPaperBoxUploadButton = (className?: string) =>
    paperBoxPreviewMode ? (
      <Button
        variant="outline"
        size="sm"
        className={cn("gap-1.5 shrink-0 whitespace-nowrap", className)}
        disabled={previewPaperBoxUploading || previewPaperBoxDeleting}
        onClick={() => triggerPaperBoxUpload(previewPaperBoxPageNo)}
      >
        {previewPaperBoxUploading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Upload className="w-4 h-4" />
        )}
        {previewPaperBoxUploading
          ? t("grading.status.uploading")
          : t("grading.action.uploadThisPage")}
      </Button>
    ) : null;

  const renderPaperBoxDeleteButton = (className?: string) =>
    paperBoxPreviewMode && paperBoxCurrentSlot ? (
      <Button
        variant="outline"
        size="sm"
        className={cn(
          "gap-1.5 shrink-0 whitespace-nowrap border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700",
          className,
        )}
        disabled={previewPaperBoxUploading || previewPaperBoxDeleting}
        onClick={() => setPreviewPaperBoxDeleteOpen(true)}
      >
        {previewPaperBoxDeleting ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Trash2 className="w-4 h-4" />
        )}
        {previewPaperBoxDeleting
          ? t("grading.status.deleting")
          : t("grading.action.deleteThisPage")}
      </Button>
    ) : null;

  const renderPaperBoxEmptyPreview = () => (
    <div className="flex flex-col items-center justify-center gap-3 px-4 text-center">
      <p className="text-sm text-muted-foreground">
        {t("grading.paperBox.pageNotUploaded", { page: previewPaperBoxPageNo })}
      </p>
      <Button
        variant="secondary"
        size="sm"
        className="gap-2"
        disabled={previewPaperBoxUploading}
        onClick={() => triggerPaperBoxUpload(previewPaperBoxPageNo)}
      >
        {previewPaperBoxUploading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Upload className="w-4 h-4" />
        )}
        {previewPaperBoxUploading
          ? t("grading.status.uploading")
          : t("grading.action.clickUploadThisPage")}
      </Button>
    </div>
  );

  const renderAiStatusCounts = (b: AiResultBlock) => {
    const isQuestion =
      /^第([0-9A-Za-z\(\)（）一二三四五六七八九十百千两]+)题/.test(b.title);
    if (!isQuestion || !b.subItems || b.subItems.length === 0) return null; // “总览”不显示状态

    let correct = 0;
    let wrong = 0;
    let partial = 0;
    b.subItems.forEach((sub) => {
      if (sub.status === "correct") correct++;
      else if (sub.status === "wrong" || sub.status === "blank") wrong++;
      else if (sub.status === "partial") partial++;
    });

    if (correct === 0 && wrong === 0 && partial === 0) return null;

    return (
      <div className="flex gap-1.5 text-[11px] font-medium ml-2">
        {correct > 0 && (
          <span className="text-green-600 bg-green-100/50 px-1.5 py-0.5 rounded border border-green-200/50">
            {t("grading.ai.correctCount", { count: correct })}
          </span>
        )}
        {partial > 0 && (
          <span className="text-amber-600 bg-amber-100/50 px-1.5 py-0.5 rounded border border-amber-200/50">
            {t("grading.ai.partialCount", { count: partial })}
          </span>
        )}
        {wrong > 0 && (
          <span className="text-red-600 bg-red-100/50 px-1.5 py-0.5 rounded border border-red-200/50">
            {t("grading.ai.wrongCount", { count: wrong })}
          </span>
        )}
      </div>
    );
  };

  const renderManualTextSection = (
    label: string,
    value: unknown,
    tone: "default" | "answer" | "reference" = "default",
  ) => {
    const text = normalizeManualText(value);
    if (!text) return null;
    return (
      <div
        className={cn(
          "rounded-lg border px-3 py-2",
          tone === "answer" && "border-emerald-200/70 bg-emerald-50/60",
          tone === "reference" && "border-blue-200/70 bg-blue-50/60",
          tone === "default" && "border-border/70 bg-background/80",
        )}
      >
        <div className="text-[11px] font-semibold tracking-wide text-muted-foreground">
          {label}
        </div>
        <div className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-foreground/90">
          {text}
        </div>
      </div>
    );
  };

  const renderManualGroupCard = (group: {
    key: string;
    index: number;
    type: unknown;
    title: string;
    questionText: string;
    optionText: string;
    interpretationText: string;
    slots: Array<{
      scoreKey: string;
      label: string;
      answerText: string;
      bbox: unknown;
    }>;
    statuses?: string[];
  }) => {
    const statuses = group.statuses ?? [];
    const wrongLike = statuses.some((s) => s === "wrong" || s === "partial");
    const blankLike = statuses.some((s) => s === "unanswered");
    const allCorrect =
      statuses.length > 0 && statuses.every((s) => s === "correct");
    const showWrongAnno =
      Boolean(wrongAnnotations[group.key]) ||
      wrongLike ||
      blankLike ||
      showManualScoreInputs;
    return (
      <div
        key={group.key}
        className="rounded-xl border border-border/60 bg-muted/20 p-3 shadow-sm"
      >
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-foreground">
              {group.title}
            </span>
            <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
              {getManualQuestionTypeLabel(group.type, t)}
            </span>
          </div>

          <div className="space-y-2">
            {renderManualTextSection(
              t("grading.manual.question"),
              group.questionText || t("grading.manual.noQuestionText"),
            )}
            {group.optionText &&
              renderManualTextSection(
                t("grading.manual.options"),
                group.optionText,
              )}
            {group.interpretationText &&
              renderManualTextSection(
                t("grading.manual.referenceAnswer"),
                group.interpretationText,
                "reference",
              )}
          </div>

          <div className="space-y-3">
            {group.slots.map((slot) => {
              const scoreVal = manualGradeScores[slot.scoreKey];
              const slotDeductions = manualDeductions[slot.scoreKey] || [];
              return (
                <div
                  key={slot.scoreKey}
                  className="grid w-full max-w-[620px] gap-2 rounded-lg border border-border/70 bg-background/90 p-2 lg:grid-cols-[minmax(0,1fr)_92px]"
                >
                  <div className="min-w-0 space-y-2">
                    <div className="text-xs font-semibold tracking-wide text-muted-foreground">
                      {slot.label}
                    </div>
                    {renderManualTextSection(
                      t("grading.manual.answerContent"),
                      slot.answerText || t("grading.manual.noAnswerContent"),
                      "answer",
                    )}
                  </div>
                  <div className="flex min-h-[90px] w-[92px] flex-col justify-between rounded-lg border border-border/70 bg-background p-2">
                    <div className="text-center text-[11px] font-medium text-muted-foreground">
                      {t("grading.manual.scoring")}
                    </div>
                    <div className="flex items-center justify-center gap-1">
                      {showManualScoreInputs ? (
                        <>
                          <Input
                            type="text"
                            inputMode="decimal"
                            className={cn(
                              "h-8 w-full px-1 text-center [appearance:textfield]",
                              scoreVal !== undefined &&
                                scoreVal !== "" &&
                                "border-primary/50 text-primary font-bold",
                            )}
                            placeholder={t("grading.manual.scorePlaceholder")}
                            value={scoreVal || ""}
                            onWheel={(e) => {
                              e.currentTarget.blur();
                            }}
                            onChange={(e) => {
                              const value = normalizeManualScoreInput(
                                e.target.value,
                              );
                              const prevValue =
                                manualGradeScores[slot.scoreKey] ?? "";
                              const newScores = {
                                ...manualGradeScores,
                                [slot.scoreKey]: value,
                              };
                              setManualGradeScores(newScores);
                              // 清空分数 → 该题扣分项一并清空（客户清单 #9 步骤 4）；
                              // 纯改分不动扣分项则原样保留
                              if (
                                value === "" &&
                                prevValue !== "" &&
                                (manualDeductions[slot.scoreKey]?.length || 0) >
                                  0
                              ) {
                                const next = { ...manualDeductionsRef.current };
                                delete next[slot.scoreKey];
                                manualDeductionsRef.current = next;
                                manualDeductionsDirtyRef.current = true;
                                setManualDeductions(next);
                              }
                            }}
                          />
                        </>
                      ) : (
                        <span className="text-center text-sm font-bold text-primary">
                          {scoreVal !== undefined && scoreVal !== ""
                            ? t("grading.manual.scoreDisplay", {
                                score: scoreVal,
                              })
                            : t("grading.manual.notScored")}
                        </span>
                      )}
                    </div>
                    {slotDeductions.length > 0 && (
                      <TooltipProvider delayDuration={80}>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <div className="mt-1 cursor-default truncate text-center text-[10px] leading-3 text-amber-700">
                              {t("grading.manual.deductionBadge", {
                                count: String(slotDeductions.length),
                                total: String(
                                  slotDeductions.reduce(
                                    (s, d) => s + (Number(d.points) || 0),
                                    0,
                                  ),
                                ),
                              })}
                            </div>
                          </TooltipTrigger>
                          <TooltipContent
                            side="left"
                            className="max-w-[260px] whitespace-pre-line"
                          >
                            {slotDeductions
                              .map((d) =>
                                d.label
                                  ? `${d.label} -${d.points}`
                                  : `-${d.points}`,
                              )
                              .join("\n")}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {showWrongAnno &&
            renderWrongAnnotationCard(group.key, {
              wrong: wrongLike,
              muted: allCorrect,
            })}
        </div>
      </div>
    );
  };

  /** 错因批注编辑卡（详情右栏/修正对话框共用）：错/半对常显，未作答可手写，已有批注始终可改删 */
  const renderWrongAnnotationCard = (
    questionKey: string | undefined,
    opts: { wrong?: boolean; muted?: boolean } = {},
  ) => {
    if (!questionKey || !wrongAnnoEngine) return null;
    return (
      <WrongAnnotationCard
        questionKey={questionKey}
        annotation={wrongAnnotations[questionKey]}
        wrong={opts.wrong ?? true}
        regenerating={wrongAnnoRegenerating === questionKey}
        onEditText={(text) => handleWrongAnnoEdit(questionKey, text)}
        onRegenerate={() => void handleWrongAnnoRegenerate(questionKey)}
        onMarkManual={() => handleWrongAnnoMarkManual(questionKey)}
        onDelete={() => handleWrongAnnoDelete(questionKey)}
        muted={opts.muted}
      />
    );
  };

  /** 智能卷解析块下的批注卡：块内子项共用一个题号 key，错/半对/未作答或已有批注时显示 */
  const renderWrongAnnoForAiBlock = (b: AiResultBlock) => {
    const key = b.key || b.subItems?.find((s) => s.key)?.key;
    if (!key || !wrongAnnoEngine) return null;
    const subs = b.subItems ?? [];
    const wrongLike = subs.some(
      (s) => s.status === "wrong" || s.status === "partial",
    );
    const blankLike = subs.some((s) => s.status === "blank");
    const allCorrect = subs.length > 0 && subs.every((s) => s.status === "correct");
    if (!wrongAnnotations[key] && !wrongLike && !blankLike) return null;
    return renderWrongAnnotationCard(key, {
      wrong: wrongLike,
      muted: allCorrect,
    });
  };

  /** 打印/导出旁的「打印批注」快捷开关（全局偏好，单张/批量同用） */
  const renderPrintWrongNotesToggle = () => (
    <button
      type="button"
      onClick={() => setPrintWrongNotes(!printWrongNotes)}
      className={cn(
        "flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md border px-2 py-1.5 text-xs transition-colors",
        printWrongNotes
          ? "border-orange-300 bg-orange-50 text-orange-700"
          : "border-border/70 bg-background text-muted-foreground",
      )}
      title={t(
        "grading.printWrongNotes.hint",
        undefined,
        "打印/导出留痕时是否带上错因批注",
      )}
    >
      {printWrongNotes ? (
        <Check className="w-3 h-3" />
      ) : (
        <X className="w-3 h-3" />
      )}
      {t("grading.printWrongNotes.short", undefined, "打印批注")}
    </button>
  );

  const opGlassBtnClass =
    "border-sky-300/80 bg-white/70 text-foreground backdrop-blur-sm transition-all duration-300 " +
    "hover:border-cyan-300 hover:text-foreground hover:bg-[linear-gradient(120deg,rgba(255,255,255,0.86),rgba(186,230,253,0.58),rgba(196,181,253,0.45),rgba(129,140,248,0.32),rgba(255,255,255,0.86))] " +
    "hover:shadow-[0_8px_24px_-14px_rgba(56,189,248,0.8)]";

  if (view === "folder" && selectedFolder) {
    const folderTitle = displayFolderName(selectedFolder);
    const scoringPanelVisible = gradingEngine === "baidu" || gradingEngine === "aliyun";
    const scoringPanelOpen = scoringPanelVisible && scoringDialogOpen;
    const referenceLayoutPending =
      gradingEngine === "aliyun" && !referenceLayoutStatus.confirmed;
    return (
      <GradingErrorBoundary
        fallback={
          <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-dashed bg-muted/30 p-8 text-center">
            <p className="text-muted-foreground">{t("grading.loadError")}</p>
            <Button variant="outline" onClick={handleBackToList}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              {t("common.backToList")}
            </Button>
          </div>
        }
      >
        <div className="space-y-6 animate-in fade-in duration-300">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3 min-w-0">
              <Button
                variant="ghost"
                size="icon"
                onClick={handleBackToList}
                className="shrink-0 rounded-full"
              >
                <ArrowLeft className="w-5 h-5" />
              </Button>
              <div className="min-w-0">
                <h1
                  className="text-xl font-bold text-foreground truncate"
                  title={folderTitle}
                >
                  {folderTitle}
                </h1>
                <p className="text-sm text-muted-foreground">
                  {t("grading.folderHint")}
                </p>
              </div>
            </div>
            <div className="text-sm font-medium text-muted-foreground whitespace-nowrap shrink-0 pt-0.5 flex flex-col items-end">
              {selectGradeMode && (
                <Button
                  variant="outline"
                  size="sm"
                  className="mb-2 h-8"
                  disabled={refLoading || selectableStudentIds.length === 0}
                  onClick={() => {
                    if (allSelectedForGrade) setSelectedGradeIds(new Set());
                    else setSelectedGradeIds(new Set(selectableStudentIds));
                  }}
                >
                  {allSelectedForGrade
                    ? t("common.deselectAll")
                    : t("common.selectAll")}
                </Button>
              )}
              <div>
                {t("grading.progressDone", {
                  done: progressDone,
                  total: progressTotal,
                })}
              </div>
              {refLoading && refProgress?.currentName && (
                <div
                  className="mt-1 max-w-[320px] truncate text-xs font-normal text-muted-foreground/90"
                  title={refProgress.currentName}
                >
                  {isManualEngine(gradingEngine)
                    ? t("grading.analyzingNow")
                    : t("grading.gradingNow")}
                  {refProgress.currentName}
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {(gradingEngine === "aliyun" || gradingEngine === "smart_ref") && (
              <>
                {/* 上传入口只留试卷框里的标准答案卡片（避免与工具栏重复）；这里只留隐藏文件框 */}
                <input
                  ref={stdInputRef}
                  type="file"
                  accept="image/*,.pdf,.doc,.docx"
                  multiple
                  className="hidden"
                  disabled={refLoading || standardBoxUploading}
                  onChange={handleUploadStd}
                />
                {/* 答案纸入口放工具栏（上次藏在弹窗里被漏点，答案整页识别成空气）——传完自动开专窗核对 */}
                <input
                  ref={answerSheetInputRef}
                  type="file"
                  accept="image/*,.pdf"
                  multiple
                  className="hidden"
                  disabled={refLoading || standardBoxUploading}
                  onChange={(e) => void handleAnswerSheetFileChange(e)}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => answerSheetInputRef.current?.click()}
                  className={cn("gap-2", opGlassBtnClass)}
                  disabled={refLoading || standardBoxUploading}
                >
                  <Upload className="w-4 h-4" />
                  {t("grading.answerTable.uploadAnswers")}
                </Button>
                {standardAnswers.length > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void handleOpenAnswerTable()}
                    className={cn("gap-2", opGlassBtnClass)}
                    disabled={refLoading || answerTableLoading || standardBoxUploading}
                  >
                    {answerTableLoading ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <ClipboardList className="w-4 h-4" />
                    )}
                    {t("grading.answerTable.button")}
                  </Button>
                )}
              </>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => studentInputRef.current?.click()}
              className={cn("gap-2", opGlassBtnClass)}
              disabled={refLoading || studentUploading}
            >
              {studentUploading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Upload className="w-4 h-4" />
              )}
              {studentUploading && studentUploadProgress
                ? t("grading.status.uploadingProgress", {
                    done: studentUploadProgress.done,
                    total: studentUploadProgress.total,
                  })
                : t("grading.uploadStudentPapers")}
            </Button>
            <input
              ref={studentInputRef}
              type="file"
              accept="image/*,.pdf,.doc,.docx"
              multiple
              className="hidden"
              disabled={refLoading || studentUploading}
              onChange={handleUploadStudent}
            />
            <Button
              variant={scanImportRunning ? "secondary" : "outline"}
              size="sm"
              onClick={async () => {
                if (refLoading) return;
                if (!selectedFolder) return;
                if (scanImportRunning) {
                  await stopScanImportAndRefresh();
                } else {
                  await startScanImportAndRefresh();
                }
              }}
              className={cn("gap-2", opGlassBtnClass)}
              disabled={refLoading}
            >
              {scanImportRunning ? (
                <Loader2 className="w-4 h-4 animate-spin text-primary" />
              ) : null}
              {scanImportRunning
                ? t("grading.stopScan")
                : t("grading.scanImport")}
            </Button>
            {scanError ? (
              <div className="flex w-full flex-col gap-2">
                <Alert
                  variant="destructive"
                  className="border-red-300 bg-red-50 text-red-800"
                >
                  <AlertCircle className="w-4 h-4" />
                  <AlertTitle>{t("grading.scan.errorTitle")}</AlertTitle>
                  <AlertDescription>
                    {scanErrorMessage || t("grading.scan.error")}
                    {scanImportedCount > 0
                      ? ` · ${t("grading.scan.imported", {
                          count: scanImportedCount,
                        })}`
                      : ""}
                  </AlertDescription>
                </Alert>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={refLoading}
                    onClick={async () => {
                      if (!selectedFolder) return;
                      try {
                        scanImportKnownFilesRef.current = new Set(
                          studentFiles.map((f) => f.name),
                        );
                        await startScanImport(selectedFolder);
                        setScanImportRunning(true);
                        setScanError(false);
                        setScanErrorMessage(null);
                        scanErrorToastShownRef.current = false;
                        toast.success(t("grading.toast.scanStarted"));
                        loadFolderFiles(selectedFolder);
                      } catch (e: any) {
                        toast.error(
                          e?.message || t("grading.toast.startFailed"),
                        );
                      }
                    }}
                    className={cn("gap-2", opGlassBtnClass)}
                  >
                    <RefreshCw className="w-4 h-4" />
                    {t("grading.scan.retry")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={refLoading}
                    onClick={async () => {
                      try {
                        await stopScanImport();
                        setScanImportRunning(false);
                        setScanError(false);
                        setScanErrorMessage(null);
                        scanErrorToastShownRef.current = false;
                        toast.success(t("grading.toast.scanStopped"));
                        if (selectedFolder) loadFolderFiles(selectedFolder);
                      } catch (e: any) {
                        toast.error(
                          e?.message || t("grading.toast.stopFailed"),
                        );
                      }
                    }}
                    className={cn("gap-2", opGlassBtnClass)}
                  >
                    <StopCircle className="w-4 h-4" />
                    {t("grading.scan.stop")}
                  </Button>
                </div>
              </div>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setPaperBoxCapacityDraft(String(paperBoxCapacity));
                setPaperBoxSettingsOpen(true);
              }}
              className={cn("gap-2", opGlassBtnClass)}
              disabled={refLoading}
            >
              <Settings className="w-4 h-4" />
              {t("grading.paperBoxSettings")}
            </Button>
            <div
              className={cn(
                "flex h-9 items-center gap-2 rounded-md border px-3",
                autoPushClassReview
                  ? "border-sky-300/80 bg-sky-50/70 text-sky-700"
                  : "border-border bg-background text-muted-foreground",
              )}
              title={t("grading.classReviewPush.autoToggleHint")}
            >
              <Switch
                checked={autoPushClassReview}
                onCheckedChange={setAutoPushClassReview}
                disabled={refLoading}
              />
              <span className="whitespace-nowrap text-sm font-medium">
                {t("grading.classReviewPush.autoToggle")}
              </span>
            </div>
            <div
              className={cn(
                "flex h-9 items-center gap-2 rounded-md border px-3",
                dingtalkPushMode === "auto"
                  ? "border-emerald-300/80 bg-emerald-50/70 text-emerald-700"
                  : "border-border bg-background text-muted-foreground",
              )}
              title={t("grading.dingtalkPush.autoToggleHint")}
            >
              <Switch
                checked={dingtalkPushMode === "auto"}
                onCheckedChange={(checked) =>
                  setDingtalkPushMode(checked ? "auto" : "manual")
                }
                disabled={refLoading}
              />
              <span className="whitespace-nowrap text-sm font-medium">
                {t("grading.dingtalkPush.autoToggle")}
              </span>
            </div>
            <div className="mx-1 h-6 w-px bg-sky-200/90" />
            <Select
              value={gradingEngine}
              onValueChange={(v) => setGradingEngine(v as GradingEngine)}
              disabled={refLoading}
            >
              <SelectTrigger
                className={cn(
                  "w-[180px] h-9 text-sm border-sky-300/80",
                  opGlassBtnClass,
                )}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="baidu">
                  {t("grading.engine.baidu")}
                </SelectItem>
                <SelectItem value="aliyun">
                  {t("grading.engine.aliyun")}
                </SelectItem>
                <SelectItem value="manual_paper">
                  {t("grading.engine.manualPaper")}
                </SelectItem>
                <SelectItem value="essay">
                  {t("grading.engine.essay")}
                </SelectItem>
                <SelectItem value="manual">
                  {t("grading.engine.manual")}
                </SelectItem>
                <SelectItem value="manual_reference">
                  {t("grading.engine.manualReference")}
                </SelectItem>
              </SelectContent>
            </Select>
            {gradingEngine === "essay" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setEssayRubricOpen(true)}
                className={cn("gap-2", opGlassBtnClass)}
                disabled={refLoading}
              >
                {activeRubricId
                  ? essayRubrics.find((r) => r.id === activeRubricId)?.name ||
                    t("grading.rubric")
                  : t("grading.rubric")}
              </Button>
            )}
            {isManualEngine(gradingEngine) && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => void openAnswerKeyDialog()}
                className={cn(
                  "gap-2",
                  opGlassBtnClass,
                  answerKeyLoaded && "border-emerald-400/80 text-emerald-700",
                )}
                disabled={refLoading}
              >
                <ClipboardList className="w-4 h-4" />
                {answerKeyLoaded
                  ? t("grading.answerKey.filled", {
                      count: Object.keys(answerKeyLoaded).length,
                    })
                  : t("grading.answerKey.fill")}
              </Button>
            )}
            {isManualEngine(gradingEngine) && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOriginalPaperOpen(true)}
                className={cn(
                  "gap-2",
                  opGlassBtnClass,
                  originalPaperScoreCount > 0 &&
                    "border-emerald-400/80 text-emerald-700",
                )}
                disabled={refLoading}
              >
                <ImagePlus className="w-4 h-4" />
                {originalPaperScoreCount > 0
                  ? t("grading.originalPaper.filled", {
                      count: originalPaperScoreCount,
                    })
                  : t("grading.originalPaper.button")}
              </Button>
            )}
            <Button
              onClick={() => {
                if (gradingEngine === "manual_reference") {
                  void handleStartAnswerKeyGrade();
                  return;
                }
                if (isManualEngine(gradingEngine)) {
                  void (manualLayoutStatus.confirmed
                    ? handleViewManualLayout()
                    : handlePrepareManualLayout());
                  return;
                }
                if (gradingEngine === "aliyun" && referenceLayoutPending) {
                  void handlePrepareReferenceLayout();
                  return;
                }
                if (!selectGradeMode) {
                  setNoticePending(() => () => void handleStartRefGrade());
                  return;
                }
                if (selectedGradeIds.size === 0) {
                  toast.error(t("grading.selectPapersFirst"));
                  return;
                }
                setNoticePending(
                  () => () =>
                    void handleStartRefGrade(
                      undefined,
                      Array.from(selectedGradeIds),
                    ),
                );
              }}
              disabled={
                refLoading ||
                referenceLayoutPreparing ||
                manualLayoutPreparing ||
                (gradingEngine === "aliyun" && !standardAnswer) ||
                (gradingEngine !== "aliyun" && studentCount === 0) ||
                (gradingEngine === "aliyun" &&
                  !referenceLayoutPending &&
                  studentCount === 0)
              }
              className="gap-2"
            >
              {refLoading ||
              referenceLayoutPreparing ||
              manualLayoutPreparing ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <PenTool className="w-4 h-4" />
              )}
              {gradingEngine === "manual_reference"
                ? manualLayoutStatus.confirmed
                  ? t("grading.answerKey.startCompare")
                  : manualLayoutPreparing
                    ? t("grading.manualLayout.preparing")
                    : t("grading.action.cutAnalysis")
                : isManualEngine(gradingEngine)
                  ? manualLayoutPreparing
                    ? t("grading.manualLayout.preparing")
                    : t("grading.action.cutAnalysis")
                  : refLoading
                    ? t("grading.status.grading")
                    : referenceLayoutPreparing
                      ? t("grading.layout.preparing")
                      : referenceLayoutPending
                        ? t("grading.layout.reviewButton")
                        : selectGradeMode
                          ? t("grading.action.startGradeCount", {
                              count: selectedGradeIds.size,
                            })
                          : t("grading.action.gradeAll")}
            </Button>
            {gradingEngine === "aliyun" ? (
              <Button
                variant="outline"
                size="sm"
                className={cn("gap-2", opGlassBtnClass)}
                disabled={
                  refLoading ||
                  referenceLayoutPreparing ||
                  referenceLayoutOpening ||
                  layoutTemplateSaving
                }
                onClick={() => {
                  setLayoutTemplateMode("apply");
                  setLayoutTemplateOpen(true);
                }}
              >
                <Sparkles className="w-4 h-4" />
                {t("layoutTemplate.apply")}
              </Button>
            ) : null}
            {!isManualEngine(gradingEngine) && (
              <Button
                variant="outline"
                size="sm"
                disabled={
                  refLoading ||
                  studentCount === 0 ||
                  (gradingEngine === "aliyun" && referenceLayoutPending)
                }
                onClick={() => {
                  if (refLoading) return;
                  if (!selectGradeMode) {
                    setDeleteMode(false);
                    setDeletingIds(new Set());
                    setSelectGradeMode(true);
                    setSelectedGradeIds(new Set());
                    return;
                  }
                  setSelectGradeMode(false);
                  setSelectedGradeIds(new Set());
                }}
                className={cn(
                  "gap-2",
                  opGlassBtnClass,
                  selectGradeMode && "border-primary/70 ring-2 ring-primary/30",
                )}
              >
                {selectGradeMode
                  ? t("grading.action.cancelSelect")
                  : t("grading.action.selectGrade")}
                {selectGradeMode && selectedGradeIds.size > 0
                  ? t("grading.action.selectedCount", {
                      count: selectedGradeIds.size,
                    })
                  : ""}
              </Button>
            )}
            {dingtalkPushMode === "manual" &&
              !refLoading &&
              (gradingsPersisted?.completed?.length || 0) > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleManualDingtalkPush}
                  disabled={dingtalkPushing}
                  className={cn("gap-2", opGlassBtnClass)}
                  title={t("grading.dingtalkPush.manualButtonHint")}
                >
                  {dingtalkPushing ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  {t("grading.dingtalkPush.manualButton")}
                </Button>
              )}
            <div className="mx-1 h-6 w-px bg-sky-200/90" />
            {refLoading && activeGradingJobId && (
              <Button
                variant="destructive"
                size="sm"
                onClick={handleStopGrading}
                className={cn("gap-2", opGlassBtnClass)}
              >
                <StopCircle className="w-4 h-4" />
                {gradingEngine === "manual"
                  ? t("grading.action.stopAnalyze")
                  : t("grading.action.stopGrade")}
              </Button>
            )}
            <Button
              variant={deleteMode ? "secondary" : "outline"}
              size="sm"
              onClick={() => {
                if (refLoading) return;
                setSelectGradeMode(false);
                setSelectedGradeIds(new Set());
                setDeleteMode((m) => !m);
                if (deleteMode) setDeletingIds(new Set());
              }}
              className={cn("gap-2", opGlassBtnClass)}
              disabled={refLoading}
            >
              <Trash2 className="w-4 h-4" />
              {deleteMode
                ? t("grading.action.cancelDelete")
                : t("grading.action.deletePapers")}
            </Button>
            {deleteMode && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (refLoading) return;
                  if (allSelectedInDeleteMode) {
                    setDeletingIds(new Set());
                    return;
                  }
                  setDeletingIds(new Set(deletableIdsInView));
                }}
                className={cn("gap-2", opGlassBtnClass)}
                disabled={refLoading || deletableIdsInView.length === 0}
              >
                {allSelectedInDeleteMode
                  ? t("common.deselectAll")
                  : t("common.selectAll")}
              </Button>
            )}
            {deleteMode && deletingIds.size > 0 && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setDeleteConfirmOpen(true)}
                className={cn(
                  "gap-2 animate-in fade-in slide-in-from-right-2 duration-200",
                  opGlassBtnClass,
                )}
                disabled={refLoading}
              >
                {t("grading.action.batchDelete", { count: deletingIds.size })}
              </Button>
            )}
            <div className="mx-1 h-6 w-px bg-sky-200/90" />
            {(() => {
              const studentOrder = folderFiles.filter(
                (f) =>
                  !standardAnswer ||
                  (f.name !== standardAnswer.filename &&
                    f.name !== standardAnswer.name),
              );
              const isPrintable = (f: FolderFileItem) =>
                gradingEngine === "essay"
                  ? !!(completedByFilename as any)[f.name]?.result
                  : !!marksOnlyFilenameFromUrl(
                      completedByFilename[f.name]?.image_marks_only,
                    );
              const printableCount = studentOrder.filter(isPrintable).length;
              const selectedPrintableCount =
                selectGradeMode && selectedGradeIds.size > 0
                  ? studentOrder.filter(
                      (f) => selectedGradeIds.has(f.name) && isPrintable(f),
                    ).length
                  : 0;
              const currentPrinter =
                selectedPrinter === PRINTER_DEFAULT
                  ? printers.find((p) => p.is_default)
                  : printers.find((p) => p.name === selectedPrinter);
              const printerReady = currentPrinter?.ready ?? false;
              return (
                <>
                  {gradingEngine !== "essay" &&
                    renderPrintWrongNotesToggle()}
                  {gradingEngine === "essay" ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={printableCount === 0 || printBatchLoading}
                          className={cn("gap-2", opGlassBtnClass)}
                        >
                          {printBatchLoading ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Printer className="w-4 h-4" />
                          )}
                          {printBatchLoading
                            ? t("grading.status.printing")
                            : t("grading.action.batchPrint")}
                          {selectGradeMode && selectedGradeIds.size > 0
                            ? t("grading.action.batchPrintCountSelected", {
                                count: selectedPrintableCount,
                              })
                            : printableCount > 0 &&
                              !printBatchLoading &&
                              t("grading.action.batchPrintCountCopy", {
                                count: printableCount,
                              })}
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {/* 作文模式不做「打印留痕」：作文 completed 项(契约 name/result/ocr_title/ocr_content)
                            从不含 image_marks_only,handleBatchPrint 恒 toast「无可打印留痕」,故只保留打印报告 */}
                        <DropdownMenuItem
                          onClick={() => void handleEssayPrintPdf()}
                        >
                          {t("grading.action.printReport")}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setPrintConfirmOpen(true);
                      }}
                      disabled={printableCount === 0 || printBatchLoading}
                      className={cn("gap-2", opGlassBtnClass)}
                    >
                      {printBatchLoading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Printer className="w-4 h-4" />
                      )}
                      {printBatchLoading
                        ? t("grading.status.printing")
                        : t("grading.action.batchPrint")}
                      {selectGradeMode && selectedGradeIds.size > 0
                        ? t("grading.action.batchPrintCountSelected", {
                            count: selectedPrintableCount,
                          })
                        : printableCount > 0 &&
                          !printBatchLoading &&
                          t("grading.action.batchPrintCountPaper", {
                            count: printableCount,
                          })}
                    </Button>
                  )}
                  {gradingEngine !== "essay" && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void handleExportMarksPdfAll()}
                      disabled={printableCount === 0 || exportPdfLoading}
                      className={cn("gap-2", opGlassBtnClass)}
                    >
                      {exportPdfLoading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Download className="w-4 h-4" />
                      )}
                      {t("grading.action.exportMarksPdfAll")}
                    </Button>
                  )}
                  {gradingEngine !== "essay" && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void handleBrowserPrintAll()}
                      disabled={printableCount === 0 || browserPrintLoading}
                      className={cn("gap-2", opGlassBtnClass)}
                    >
                      {browserPrintLoading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Printer className="w-4 h-4" />
                      )}
                      {t("grading.action.browserPrintAll")}
                    </Button>
                  )}
                  {gradingEngine === "essay" && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void handleEssayDownloadPdf()}
                      disabled={printableCount === 0 || printBatchLoading}
                      className={cn("gap-2", opGlassBtnClass)}
                    >
                      {t("grading.action.downloadPdfAll")}
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void openPrintSettings()}
                    disabled={printBatchLoading}
                    className={cn("gap-2", opGlassBtnClass)}
                  >
                    <Settings className="w-4 h-4" />
                    {t("grading.action.printSettings")}
                  </Button>
                  <span
                    className={cn(
                      "w-2 h-2 rounded-full shrink-0 self-center",
                      printerReady ? "bg-green-500" : "bg-muted-foreground/50",
                    )}
                    title={
                      printerReady
                        ? t("grading.action.printerReady")
                        : t("grading.action.printerUnavailable")
                    }
                  />
                  <div className="mx-1 h-6 w-px bg-sky-200/90" />
                  {(gradingEngine === "baidu" || gradingEngine === "aliyun") && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setScoringDialogOpen(true);
                      }}
                      disabled={refLoading}
                      className={cn(
                        "gap-2",
                        opGlassBtnClass,
                        Object.keys(scoringConfig).length > 0 &&
                          "border-green-400 text-green-700",
                      )}
                    >
                      <BarChart3 className="w-4 h-4" />
                      {t("grading.action.scoringSettings")}
                    </Button>
                  )}
                  {printBatchLoading && activePrintJobId && (
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={handleCancelBatchPrint}
                      className={cn("gap-2", opGlassBtnClass)}
                    >
                      {t("grading.action.cancelPrint")}
                    </Button>
                  )}
                </>
              );
            })()}
            <div className="mx-1 h-6 w-px bg-sky-200/90" />
            <Button
              variant={orchestration.phase === "idle" ? "outline" : "secondary"}
              size="sm"
              onClick={handleOrchestrationButtonClick}
              className={cn("gap-2", opGlassBtnClass)}
              disabled={
                isManualEngine(gradingEngine) ||
                (orchestration.phase === "idle" &&
                  (refLoading || scanImportRunning))
              }
              title={t("grading.orchestrate.title")}
            >
              {orchestration.phase === "scanning" ||
              orchestration.phase === "grading" ||
              orchestration.phase === "printing" ? (
                <StopCircle className="w-4 h-4" />
              ) : orchestration.phase === "idle" ? (
                <Split className="w-4 h-4" />
              ) : (
                <Check className="w-4 h-4" />
              )}
              {orchestration.phase === "idle"
                ? t("grading.orchestrate.start")
                : orchestration.phase === "scanning" ||
                    orchestration.phase === "grading" ||
                    orchestration.phase === "printing"
                  ? t("grading.orchestrate.stop")
                  : orchestration.phase === "done"
                    ? t("grading.orchestrate.doneShort")
                    : t("grading.orchestrate.reset")}
            </Button>
            {orchestration.phase !== "idle" && (
              <div className="flex w-full flex-wrap items-center gap-2 rounded-lg border border-sky-200/80 bg-white/60 px-3 py-2 backdrop-blur-sm">
                <div className="flex flex-wrap items-center gap-1.5">
                  {ORCHESTRATE_STEPS.map((step, idx) => {
                    const state = orchestrationStepState(step);
                    return (
                      <Fragment key={step}>
                        {idx > 0 && (
                          <ArrowRight className="w-3 h-3 text-muted-foreground/50" />
                        )}
                        <button
                          type="button"
                          onClick={() => toggleOrchestrationStep(step)}
                          disabled={
                            (orchestration.phase === "scanning" &&
                              step === "scan") ||
                            orchestration.phase === "grading" ||
                            orchestration.phase === "printing"
                          }
                          className={cn(
                            "flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-all",
                            !enabledSteps[step] && "opacity-40 line-through",
                            state === "error" &&
                              "border-red-300 bg-red-50 text-red-700",
                            state === "active" &&
                              "border-primary/60 bg-primary/10 text-primary",
                            state === "done" &&
                              "border-emerald-300 bg-emerald-50 text-emerald-700",
                            state === "pending" &&
                              "border-border/70 bg-muted/20 text-muted-foreground",
                          )}
                          title={
                            enabledSteps[step]
                              ? t("grading.orchestrate.stepEnabledTitle", {
                                  step: orchestrateStepLabel(step),
                                })
                              : t("grading.orchestrate.stepDisabledTitle", {
                                  step: orchestrateStepLabel(step),
                                })
                          }
                        >
                          {state === "error" ? (
                            <X className="w-3 h-3" />
                          ) : state === "active" ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : state === "done" ? (
                            <Check className="w-3 h-3" />
                          ) : step === "scan" ? (
                            <Camera className="w-3 h-3" />
                          ) : step === "grade" ? (
                            <PenTool className="w-3 h-3" />
                          ) : (
                            <Printer className="w-3 h-3" />
                          )}
                          {orchestrateStepLabel(step)}
                        </button>
                      </Fragment>
                    );
                  })}
                </div>
                {orchestration.phase === "scanning" && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-muted-foreground">
                      {t("grading.orchestrate.scanPrompt")}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void advanceFromScan(false)}
                      className={cn("gap-1 h-7", opGlassBtnClass)}
                    >
                      <Check className="w-3.5 h-3.5" />
                      {t("grading.orchestrate.scanNext")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void advanceFromScan(true)}
                      className="gap-1 h-7"
                    >
                      {t("grading.orchestrate.skipScan")}
                    </Button>
                  </div>
                )}
                {orchestration.phase === "done" && (
                  <span className="flex items-center gap-1 text-xs font-medium text-emerald-600">
                    <Check className="w-3.5 h-3.5" />
                    {t("grading.orchestrate.done")}
                  </span>
                )}
                {orchestration.phase === "error" && (
                  <span className="flex items-center gap-1 text-xs font-medium text-red-600">
                    <AlertCircle className="w-3.5 h-3.5" />
                    {orchestration.message}
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-4">
            <div className="min-w-0 flex-1">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {/* 参照答案批改（aliyun）和智能参照批改（smart_ref）需要{t("grading.preview.altStdAnswer")}；智能模型批改（baidu）不依赖{t("grading.preview.altStdAnswer")} */}
                {(gradingEngine === "aliyun" ||
                  gradingEngine === "smart_ref") &&
                  (() => {
                    const standardFilledCount =
                      standardAnswerSlots.filter(Boolean).length;
                    const standardFileNames = standardAnswers.map(
                      (item) => item.filename,
                    );
                    const allStandardDeleting =
                      standardFileNames.length > 0 &&
                      standardFileNames.every((name) => deletingIds.has(name));
                    const standardPreview =
                      standardAnswerSlots.find(
                        (item): item is StandardAnswerItem => Boolean(item),
                      ) ?? standardAnswer;

                    if (!standardPreview) {
                      return (
                        <Card
                          className="overflow-hidden border border-dashed hover:border-primary/40 hover:bg-muted/30 transition-colors cursor-pointer"
                          onClick={() =>
                            !deleteMode &&
                            !refLoading &&
                            !standardBoxUploading &&
                            stdInputRef.current?.click()
                          }
                        >
                          <CardContent className="p-0 flex flex-col items-center justify-center aspect-[3/4] text-muted-foreground">
                            {standardBoxUploading ? (
                              <Loader2 className="w-10 h-10 mb-2 animate-spin opacity-60" />
                            ) : (
                              <Upload className="w-10 h-10 mb-2 opacity-60" />
                            )}
                            <span className="text-sm">
                              {t("grading.uploadStdAnswer")}
                            </span>
                            <span className="text-xs mt-1">
                              {t("grading.standardBox.capacityHint", {
                                capacity: paperBoxCapacity,
                              })}
                            </span>
                          </CardContent>
                        </Card>
                      );
                    }

                    return (
                      <Card
                        className={cn(
                          "overflow-hidden border-emerald-100 bg-white shadow-sm transition-shadow",
                          !deleteMode && "cursor-pointer hover:shadow-md",
                          deleteMode && "ring-2 ring-primary/50",
                        )}
                        onClick={() => {
                          if (deleteMode) {
                            setDeletingIds((prev) => {
                              const next = new Set(prev);
                              standardFileNames.forEach((name) =>
                                allStandardDeleting
                                  ? next.delete(name)
                                  : next.add(name),
                              );
                              return next;
                            });
                            return;
                          }
                          const firstPage = Math.max(
                            1,
                            standardAnswerSlots.findIndex(Boolean) + 1,
                          );
                          setStandardBoxPageNo(firstPage);
                          setStandardBoxOpen(true);
                        }}
                      >
                        <CardHeader className="border-b bg-emerald-50/60 px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <div className="min-w-0">
                              <CardTitle className="truncate text-sm font-semibold">
                                {t("grading.preview.altStdAnswer")}
                              </CardTitle>
                              <CardDescription className="text-[11px]">
                                {t("grading.paperBox.pageCount", {
                                  filled: standardFilledCount,
                                  capacity: paperBoxCapacity,
                                })}
                              </CardDescription>
                            </div>
                            {deleteMode ? (
                              <Checkbox
                                checked={allStandardDeleting}
                                onClick={(event) => event.stopPropagation()}
                                onCheckedChange={() => {
                                  setDeletingIds((prev) => {
                                    const next = new Set(prev);
                                    standardFileNames.forEach((name) =>
                                      allStandardDeleting
                                        ? next.delete(name)
                                        : next.add(name),
                                    );
                                    return next;
                                  });
                                }}
                              />
                            ) : (
                              <span className="rounded bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                                {t("grading.standardBox.strictMatch")}
                              </span>
                            )}
                          </div>
                        </CardHeader>
                        <CardContent className="p-0">
                          <div className="relative aspect-[3/4] bg-muted/40">
                            {fileType(standardPreview) === "word" ? (
                              <div className="flex h-full flex-col items-center justify-center gap-2 p-2">
                                <span className="text-sm text-muted-foreground">
                                  {t("grading.preview.wordDoc")}
                                </span>
                              </div>
                            ) : (
                              <img
                                src={gradingImageUrl(standardPreview.url)}
                                alt={t("grading.preview.altStdAnswer")}
                                className="h-full w-full object-contain"
                              />
                            )}
                            <div className="absolute inset-x-2 bottom-2 flex flex-wrap gap-1">
                              {standardAnswerSlots.map((item, index) => (
                                <span
                                  key={`standard-slot-${index + 1}`}
                                  className={cn(
                                    "flex h-6 min-w-6 items-center justify-center rounded px-1 text-[10px] font-semibold shadow-sm",
                                    item
                                      ? "bg-emerald-600 text-white"
                                      : "border border-dashed border-background/80 bg-background/85 text-muted-foreground",
                                  )}
                                >
                                  P{index + 1}
                                </span>
                              ))}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })()}

                {sortedClassStudents.length > 0 && (
                  <>
                    {paperBoxes.map((box) => {
                      const filledCount = box.slots.filter(Boolean).length;
                      const previewFile =
                        box.slots.find(
                          (item): item is FolderFileItem => !!item,
                        ) || null;
                      const boxFileNames = box.files.map((file) => file.name);
                      const boxAllGraded =
                        boxFileNames.length > 0 &&
                        boxFileNames.every((name) =>
                          isFileMarkedGraded(
                            name,
                            completedByFilename,
                            gradingEngine,
                          ),
                        );
                      const boxStatus = getPaperBoxStatus(
                        filledCount,
                        paperBoxCapacity,
                        boxAllGraded,
                      );
                      const boxScoreGrade = computeBoxScoreGrade(
                        box,
                        completedByFilename,
                        gradingEngine,
                      );
                      const boxBreakdown = computeBoxPageBreakdown(
                        box,
                        completedByFilename,
                        gradingEngine,
                      );
                      const allBoxDeleting =
                        boxFileNames.length > 0 &&
                        boxFileNames.every((name) => deletingIds.has(name));
                      const allBoxSelected =
                        boxFileNames.length > 0 &&
                        boxFileNames.every((name) =>
                          selectedGradeIds.has(name),
                        );
                      return (
                        <Card
                          key={box.student.id}
                          className={cn(
                            "overflow-hidden border-sky-100 bg-gradient-to-br from-white via-sky-50/50 to-emerald-50/40 shadow-sm transition-shadow",
                            !deleteMode &&
                              !selectGradeMode &&
                              "cursor-pointer hover:shadow-md",
                          )}
                          onClick={() => {
                            if (deleteMode) {
                              setDeletingIds((prev) => {
                                const next = new Set(prev);
                                const shouldRemove = boxFileNames.every(
                                  (name) => next.has(name),
                                );
                                boxFileNames.forEach((name) =>
                                  shouldRemove
                                    ? next.delete(name)
                                    : next.add(name),
                                );
                                return next;
                              });
                              return;
                            }
                            if (selectGradeMode) {
                              setSelectedGradeIds((prev) => {
                                const next = new Set(prev);
                                const shouldRemove = boxFileNames.every(
                                  (name) => next.has(name),
                                );
                                boxFileNames.forEach((name) =>
                                  shouldRemove
                                    ? next.delete(name)
                                    : next.add(name),
                                );
                                return next;
                              });
                              return;
                            }
                            openPaperBoxDialog(box.student.id);
                          }}
                        >
                          <CardHeader className="border-b bg-white/70 px-3 py-2">
                            <div className="flex items-center justify-between gap-2">
                              <div className="min-w-0">
                                <CardTitle
                                  className="truncate text-sm font-semibold"
                                  title={box.student.name}
                                >
                                  {box.student.name}
                                </CardTitle>
                                <CardDescription className="text-[11px]">
                                  {t("grading.paperBox.studentNo", {
                                    number: box.student.student_number || "-",
                                  })}{" "}
                                  ·{" "}
                                  {t("grading.paperBox.pageCount", {
                                    filled: filledCount,
                                    capacity: paperBoxCapacity,
                                  })}
                                </CardDescription>
                              </div>
                              <div className="flex items-center gap-1 shrink-0">
                                {boxScoreGrade.score != null && (
                                  <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-xs font-bold text-primary shrink-0">
                                    {boxBreakdown || `${boxScoreGrade.score}分`}
                                    {boxScoreGrade.grade
                                      ? `·${boxScoreGrade.grade}`
                                      : ""}
                                  </span>
                                )}
                                <span
                                  className={cn(
                                    "rounded-full px-2 py-0.5 text-[11px] font-semibold shrink-0",
                                    getPaperBoxStatusBadgeClass(
                                      boxStatus,
                                      gradingEngine,
                                    ),
                                  )}
                                >
                                  {getPaperBoxStatusLabel(
                                    boxStatus,
                                    gradingEngine,
                                    t,
                                  )}
                                </span>
                              </div>
                            </div>
                          </CardHeader>
                          <CardContent className="p-3">
                            <div
                              className={cn(
                                "group overflow-hidden rounded-lg border bg-card transition-all duration-200 hover:shadow-md",
                                deleteMode &&
                                  boxFileNames.length > 0 &&
                                  "ring-2 ring-primary/50",
                                boxStatus === "graded" &&
                                  !deleteMode &&
                                  "ring-2 ring-green-500/30",
                              )}
                            >
                              <div className="relative aspect-[3/4] bg-muted/50">
                                <div className="absolute left-2 top-2 z-10 rounded bg-background/85 px-2 py-0.5 text-[10px] font-semibold shadow">
                                  {t("grading.paperBox.coverPreview")}
                                </div>
                                {deleteMode && boxFileNames.length > 0 && (
                                  <div
                                    className="absolute right-2 top-2 z-10"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <Checkbox
                                      checked={allBoxDeleting}
                                      onCheckedChange={() => {
                                        setDeletingIds((prev) => {
                                          const next = new Set(prev);
                                          boxFileNames.forEach((name) =>
                                            allBoxDeleting
                                              ? next.delete(name)
                                              : next.add(name),
                                          );
                                          return next;
                                        });
                                      }}
                                    />
                                  </div>
                                )}
                                {selectGradeMode && boxFileNames.length > 0 && (
                                  <div
                                    className="absolute right-2 top-2 z-10"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <Checkbox
                                      checked={allBoxSelected}
                                      onCheckedChange={() => {
                                        setSelectedGradeIds((prev) => {
                                          const next = new Set(prev);
                                          boxFileNames.forEach((name) =>
                                            allBoxSelected
                                              ? next.delete(name)
                                              : next.add(name),
                                          );
                                          return next;
                                        });
                                      }}
                                    />
                                  </div>
                                )}
                                {previewFile ? (
                                  fileType(previewFile) === "word" ? (
                                    <div className="flex h-full flex-col items-center justify-center gap-1 p-2 text-xs text-muted-foreground">
                                      Word
                                    </div>
                                  ) : (
                                    <img
                                      src={gradingImageUrl(previewFile.url)}
                                      alt={previewFile.name}
                                      className="h-full w-full object-contain"
                                    />
                                  )
                                ) : (
                                  <div className="flex h-full flex-col items-center justify-center text-center text-xs text-muted-foreground">
                                    <Upload className="mb-2 h-7 w-7 opacity-50" />
                                    {t("grading.paperBox.noPaper")}
                                  </div>
                                )}
                                {previewFile &&
                                  !deleteMode &&
                                  !selectGradeMode && (
                                    <>
                                      <button
                                        type="button"
                                        aria-label={t(
                                          "grading.preview.detailTitle",
                                        )}
                                        title={t(
                                          "grading.preview.detailTitle",
                                        )}
                                        className="absolute right-11 bottom-2 flex h-8 w-8 items-center justify-center rounded-full bg-background/85 opacity-0 shadow transition-opacity hover:bg-background group-hover:opacity-100"
                                        disabled={refLoading}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          openPaperBoxDialog(box.student.id, {
                                            previewOnly: true,
                                          });
                                        }}
                                      >
                                        <Search className="h-4 w-4" />
                                      </button>
                                      <button
                                        type="button"
                                        aria-label={t(
                                          "grading.action.renameCoverPaper",
                                        )}
                                        title={t(
                                          "grading.action.renameCoverPaper",
                                        )}
                                        className="absolute right-2 bottom-2 flex h-8 w-8 items-center justify-center rounded-full bg-background/85 opacity-0 shadow transition-opacity hover:bg-background group-hover:opacity-100"
                                        disabled={refLoading}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          openRenameFileDialog(previewFile.name);
                                        }}
                                      >
                                        <Edit2 className="h-4 w-4" />
                                      </button>
                                    </>
                                  )}
                              </div>
                              {paperBoxCapacity > 1 && (
                                <div className="flex flex-wrap items-center gap-1 px-2 pt-2">
                                  {box.slots.map((slot, idx) => {
                                    const pageNo = idx + 1;
                                    const graded = slot
                                      ? isFileMarkedGraded(
                                          slot.name,
                                          completedByFilename,
                                          gradingEngine,
                                        )
                                      : false;
                                    const hasFile = !!slot;
                                    return (
                                      <span
                                        key={pageNo}
                                        title={
                                          !hasFile
                                            ? t("grading.paperBox.noPaper")
                                            : graded
                                              ? t("grading.status.graded")
                                              : t("grading.status.ungraded")
                                        }
                                        className={cn(
                                          "inline-flex h-5 min-w-[2rem] items-center justify-center gap-0.5 rounded border px-1 text-[10px] font-medium leading-none",
                                          !hasFile &&
                                            "border-transparent bg-muted text-muted-foreground",
                                          hasFile &&
                                            graded &&
                                            "border-emerald-200 bg-emerald-50 text-emerald-700",
                                          hasFile &&
                                            !graded &&
                                            "border-red-200 bg-red-50 text-red-700",
                                        )}
                                      >
                                        P{pageNo}
                                        {hasFile ? (graded ? " ✓" : " ×") : ""}
                                      </span>
                                    );
                                  })}
                                </div>
                              )}
                              <div className="flex items-center justify-between gap-2 px-2 py-2 text-[11px] text-muted-foreground">
                                <span
                                  className="truncate"
                                  title={previewFile?.name || ""}
                                >
                                  {previewFile?.name ||
                                    t("grading.paperBox.waitingImport")}
                                </span>
                                <span className="shrink-0 rounded bg-muted px-1.5 py-0.5">
                                  {filledCount}/{paperBoxCapacity}
                                </span>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      );
                    })}
                    {unboxedStudentFiles.length > 0 && (
                      <Card className="border-amber-200 bg-amber-50/60">
                        <CardHeader className="px-3 py-2">
                          <CardTitle className="text-sm">
                            {t("grading.paperBox.unassignedTitle")}
                          </CardTitle>
                          <CardDescription className="text-xs">
                            {t("grading.paperBox.unassignedDesc")}
                          </CardDescription>
                        </CardHeader>
                        <CardContent className="grid gap-2 p-3 sm:grid-cols-2 xl:grid-cols-4">
                          {unboxedStudentFiles.map((file) => (
                            <Button
                              key={file.name}
                              variant="outline"
                              className="h-auto justify-start truncate py-2 text-xs"
                              onClick={() => openRenameFileDialog(file.name)}
                            >
                              <Edit2 className="mr-2 h-3.5 w-3.5" />
                              <span className="truncate">{file.name}</span>
                            </Button>
                          ))}
                        </CardContent>
                      </Card>
                    )}
                  </>
                )}

                {(sortedClassStudents.length ? [] : folderFiles)
                  .filter(
                    (f) =>
                      !standardAnswer ||
                      (f.name !== standardAnswer.filename &&
                        f.name !== standardAnswer.name),
                  )
                  .map((file) => {
                    const completed = findCompletedEntryForFile(
                      file.name,
                      completedByFilename,
                      gradingEngine,
                    );
                    const graded = isFileMarkedGraded(
                      file.name,
                      completedByFilename,
                      gradingEngine,
                    );
                    return (
                      <Card
                        key={file.name}
                        className={cn(
                          "overflow-hidden group transition-all duration-200 hover:shadow-md cursor-pointer",
                          deleteMode && "ring-2 ring-primary/50",
                          graded && !deleteMode && "ring-2 ring-green-500/30",
                        )}
                        onClick={() => {
                          if (deleteMode) {
                            toggleDeleteSelection(file.name);
                          } else if (selectGradeMode) {
                            toggleGradeSelection(file.name);
                          } else if (isManualEngine(gradingEngine)) {
                            openManualPaper(file.name);
                          } else if (graded && completed) {
                            setPreviewPaperBoxStudentId(null);
                            setDetailItem({ ...completed, name: file.name });
                          } else {
                            openZoomPreview(file.url, file.name);
                          }
                        }}
                      >
                        <CardContent className="p-0">
                          <div className="relative aspect-[3/4] bg-muted/50">
                            {deleteMode && (
                              <div
                                className="absolute left-2 top-2 z-10"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <Checkbox
                                  checked={deletingIds.has(file.name)}
                                  onCheckedChange={() =>
                                    toggleDeleteSelection(file.name)
                                  }
                                />
                              </div>
                            )}
                            {graded && !deleteMode && (
                              <div
                                className={cn(
                                  "absolute left-2 top-2 z-10 rounded text-white px-1.5 py-0.5 text-xs",
                                  isManualEngine(gradingEngine)
                                    ? "bg-blue-500/90"
                                    : "bg-green-500/90",
                                )}
                              >
                                {t("grading.status.graded")}
                              </div>
                            )}
                            {selectGradeMode && (
                              <div
                                className="absolute right-2 top-2 z-10"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <Checkbox
                                  checked={selectedGradeIds.has(file.name)}
                                  onCheckedChange={() =>
                                    toggleGradeSelection(file.name)
                                  }
                                />
                              </div>
                            )}
                            {fileType(file) === "pdf" ? (
                              <img
                                src={gradingImageUrl(file.url)}
                                alt={file.name}
                                className="w-full h-full object-contain cursor-pointer"
                                onClick={(e) => {
                                  if (
                                    deleteMode ||
                                    completed ||
                                    selectGradeMode
                                  )
                                    return;
                                  e.stopPropagation();
                                  openZoomPreview(file.url, file.name);
                                }}
                              />
                            ) : fileType(file) === "word" ? (
                              <div
                                className="w-full h-full flex flex-col items-center justify-center gap-2 p-2 cursor-pointer"
                                onClick={(e) => {
                                  if (
                                    deleteMode ||
                                    completed ||
                                    selectGradeMode
                                  )
                                    return;
                                  e.stopPropagation();
                                  openZoomPreview(file.url, file.name);
                                }}
                              >
                                <span className="text-muted-foreground text-sm">
                                  {t("grading.preview.wordDoc")}
                                </span>
                                <a
                                  href={gradingImageUrl(file.url)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-primary text-sm underline"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {t("grading.preview.openPreview")}
                                </a>
                              </div>
                            ) : (
                              <img
                                src={gradingImageUrl(file.url)}
                                alt={file.name}
                                className="w-full h-full object-contain"
                                onClick={(e) => {
                                  if (
                                    deleteMode ||
                                    completed ||
                                    selectGradeMode
                                  )
                                    return;
                                  e.stopPropagation();
                                  openZoomPreview(file.url, file.name);
                                }}
                              />
                            )}
                            {!deleteMode && !selectGradeMode && (
                              <button
                                type="button"
                                aria-label={t("grading.action.renamePaper")}
                                title={t("grading.action.renamePaper")}
                                className="absolute right-2 top-2 w-8 h-8 rounded-full bg-background/85 shadow flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-background disabled:opacity-50"
                                disabled={refLoading}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openRenameFileDialog(file.name);
                                }}
                              >
                                <Edit2 className="w-4 h-4" />
                              </button>
                            )}
                            {!deleteMode && !selectGradeMode && (
                              <>
                                <button
                                  type="button"
                                  aria-label={t("grading.action.rotateLeft")}
                                  title={t("grading.action.rotateLeft")}
                                  className="absolute right-12 top-2 w-8 h-8 rounded-full bg-background/85 shadow flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-background disabled:opacity-50"
                                  disabled={
                                    refLoading || rotatingFileName === file.name
                                  }
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    void handleRotateFile(file, "left", completed);
                                  }}
                                >
                                  {rotatingFileName === file.name ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                  ) : (
                                    <RotateCcw className="w-4 h-4" />
                                  )}
                                </button>
                                <button
                                  type="button"
                                  aria-label={t("grading.action.rotateRight")}
                                  title={t("grading.action.rotateRight")}
                                  className="absolute right-[5.5rem] top-2 w-8 h-8 rounded-full bg-background/85 shadow flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-background disabled:opacity-50"
                                  disabled={
                                    refLoading || rotatingFileName === file.name
                                  }
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    void handleRotateFile(file, "right", completed);
                                  }}
                                >
                                  {rotatingFileName === file.name ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                  ) : (
                                    <RotateCw className="w-4 h-4" />
                                  )}
                                </button>
                              </>
                            )}
                            <button
                              type="button"
                              className="absolute right-2 bottom-2 w-8 h-8 rounded-full bg-background/80 shadow flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-background"
                              onClick={(e) => {
                                if (!selectGradeMode) e.stopPropagation();
                                if (deleteMode) return;
                                if (selectGradeMode) return;
                                if (isManualEngine(gradingEngine)) {
                                  // 放大镜 = 统分/批改详情入口（卡片点按才是打分弹窗）；
                                  // 未开批的直接进打分弹窗
                                  if (completed) {
                                    setPreviewPaperBoxStudentId(null);
                                    setDetailItem({ ...completed, name: file.name });
                                  } else {
                                    openManualPaper(file.name);
                                  }
                                  return;
                                }
                                if (completed) {
                                  setPreviewPaperBoxStudentId(null);
                                  setDetailItem(completed);
                                } else {
                                  openZoomPreview(file.url, file.name);
                                }
                              }}
                            >
                              <Search className="w-4 h-4" />
                            </button>
                          </div>
                          <p
                            className="p-2 text-xs text-center text-muted-foreground truncate"
                            title={file.name}
                          >
                            {file.name}
                          </p>
                        </CardContent>
                      </Card>
                    );
                  })}
              </div>
            </div>

            {scoringPanelVisible && (
              <div
                className={cn(
                  "fixed right-4 top-[92px] bottom-4 z-40 w-[min(380px,calc(100vw-1rem))] max-w-[calc(100vw-1rem)] transition-all duration-300 ease-out",
                  scoringPanelOpen
                    ? "translate-x-0 opacity-100"
                    : "pointer-events-none translate-x-[110%] opacity-0",
                )}
                aria-hidden={!scoringPanelOpen}
              >
                <Card className="flex h-full w-full flex-col overflow-hidden border-border/60 shadow-xl">
                  <CardHeader className="space-y-2 border-b bg-muted/10">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <CardTitle className="flex items-center gap-2 text-base">
                          <BarChart3 className="w-5 h-5 text-primary" />
                          {t("grading.action.scoringSettings")}
                        </CardTitle>
                        <CardDescription className="mt-1">
                          {t("grading.scoring.currentFolder", {
                            name: displayFolderName(selectedFolder || ""),
                          })}
                        </CardDescription>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 shrink-0"
                        onClick={() => setScoringDialogOpen(false)}
                        disabled={scoringSaving || scoringApplying}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {t("grading.scoring.hint")}
                    </p>
                  </CardHeader>
                  <CardContent className="flex flex-1 flex-col gap-4 overflow-hidden p-4">
                    <div className="space-y-2 rounded-lg border border-border/50 bg-muted/20 p-3">
                      <div className="space-y-0.5">
                        <Label className="text-sm font-medium">
                          {t("grading.scoring.batchLabel")}
                        </Label>
                        <p className="text-[11px] text-muted-foreground">
                          {t("grading.scoring.batchHint")}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Input
                          id="batch-score-input"
                          type="text"
                          inputMode="decimal"
                          className="h-8 w-16 text-center"
                          placeholder="0"
                          defaultValue="0"
                          onWheel={(e) => e.currentTarget.blur()}
                        />
                        <Button
                          size="sm"
                          variant="secondary"
                          className="h-8"
                          onClick={() => {
                            const input = document.getElementById(
                              "batch-score-input",
                            ) as HTMLInputElement;
                            const normalized = normalizeManualScoreInput(
                              input?.value || "",
                            );
                            const val =
                              normalized === "" ? 0 : parseFloat(normalized);
                            if (!isNaN(val) && val >= 0) {
                              const next = { ...scoringConfig };
                              scoringQuestionTitles.forEach(
                                (t) => (next[t] = val),
                              );
                              setScoringConfig(next);
                              // 同步到「大题 + 小题」分数框
                              setPaperSubs((prev) => {
                                const out: Record<
                                  string,
                                  { num: string; score: number }[]
                                > = {};
                                for (const [m, subs] of Object.entries(prev)) {
                                  out[m] = subs.map((s) => ({
                                    ...s,
                                    score: val,
                                  }));
                                }
                                return out;
                              });
                              input.value = "0";
                              toast.success(
                                t("grading.toast.batchScoreSet", {
                                  score: val,
                                }),
                              );
                            } else {
                              toast.error(t("grading.toast.invalidScore"));
                            }
                          }}
                        >
                          {t("grading.action.batchFill")}
                        </Button>
                        <Button
                          size="sm"
                          className="h-8 gap-1.5"
                          onClick={() => void handleAutoScoringConfig()}
                          disabled={
                            scoringAutoLoading ||
                            scoringQuestionTitles.length === 0
                          }
                        >
                          {scoringAutoLoading ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Sparkles className="h-3.5 w-3.5" />
                          )}
                          {t("grading.action.autoScore")}
                        </Button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
                      <span>{t("grading.scoring.questionHeader")}</span>
                      <span>{t("grading.scoring.scoreHeader")}</span>
                    </div>

                    <ScrollArea className="min-h-0 flex-1 rounded-md border p-1">
                      <div className="space-y-2 p-1">
                        {scoringQuestionGroups.length === 0 ? (
                          <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
                            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/30" />
                            <span>{t("grading.scoring.emptyHint")}</span>
                          </div>
                        ) : (
                          scoringQuestionGroups.map((group) => (
                            <div key={group.major || "__none"} className="space-y-1.5">
                              {group.hasSubItems ? (
                                <div className="flex items-center justify-between rounded-md border border-border/50 bg-card px-3 py-2">
                                  <span className="text-sm font-semibold text-foreground">
                                    {majorTitles[group.major]
                                      ? `${group.major}、${majorTitles[group.major]}`
                                      : group.major}
                                  </span>
                                  <div className="flex shrink-0 items-center gap-2">
                                    <Input
                                      type="text"
                                      inputMode="decimal"
                                      value={String(
                                        majorScores[group.major] ?? "",
                                      )}
                                      onWheel={(e) =>
                                        e.currentTarget.blur()
                                      }
                                      onChange={(e) => {
                                        const normalized =
                                          normalizeManualScoreInput(
                                            e.target.value,
                                          );
                                        const val =
                                          normalized === ""
                                            ? 0
                                            : parseFloat(normalized);
                                        setMajorScores((prev) => ({
                                          ...prev,
                                          [group.major]: Number.isFinite(val)
                                            ? val
                                            : 0,
                                        }));
                                      }}
                                      className="h-8 w-20 text-center font-semibold [appearance:textfield] focus-visible:ring-primary/50"
                                      placeholder="0"
                                    />
                                    <span className="w-4 text-xs text-muted-foreground">
                                      {t("grading.unit.score").trim()}
                                    </span>
                                  </div>
                                </div>
                              ) : null}
                              {group.subs.length > 0
                                ? group.subs.map((sub, subIdx) => (
                                    <div
                                      key={`${group.major}-${sub.num}-${subIdx}`}
                                      className="ml-4 flex items-center justify-between gap-4 rounded-md border-l-2 border-muted bg-muted/10 p-2 transition-colors hover:bg-muted/50"
                                    >
                                      <Label
                                        className="shrink-0 text-sm font-normal text-muted-foreground"
                                        title={sub.num}
                                      >
                                        {sub.num}
                                      </Label>
                                      <div className="flex shrink-0 items-center gap-2">
                                        <Input
                                          type="text"
                                          inputMode="decimal"
                                          value={String(sub.score ?? 0)}
                                          onWheel={(e) =>
                                            e.currentTarget.blur()
                                          }
                                          onChange={(e) => {
                                            const normalized =
                                              normalizeManualScoreInput(
                                                e.target.value,
                                              );
                                            const val =
                                              normalized === ""
                                                ? 0
                                                : parseFloat(normalized);
                                            setPaperSubs((prev) => {
                                              const arr =
                                                prev[group.major] || [];
                                              const nextArr = arr.map(
                                                (s, i) =>
                                                  i === subIdx
                                                    ? {
                                                        ...s,
                                                        score: Number.isFinite(
                                                          val,
                                                        )
                                                          ? val
                                                          : 0,
                                                      }
                                                    : s,
                                              );
                                              return {
                                                ...prev,
                                                [group.major]: nextArr,
                                              };
                                            });
                                          }}
                                          className="h-8 w-20 text-center font-medium [appearance:textfield] focus-visible:ring-primary/50"
                                          placeholder="0"
                                        />
                                        <span className="w-4 text-xs text-muted-foreground">
                                          {t("grading.unit.score").trim()}
                                        </span>
                                      </div>
                                    </div>
                                  ))
                                : null}
                              {group.titles.map((title) => (
                                <div
                                  key={title}
                                  className={cn(
                                    "flex items-center justify-between gap-4 rounded-md p-2 transition-colors hover:bg-muted/50",
                                    group.hasSubItems
                                      ? "ml-4 border-l-2 border-muted bg-muted/10"
                                      : "border border-border/50 bg-card",
                                  )}
                                >
                                  <Label
                                    className={cn(
                                      "truncate text-sm font-normal shrink-0",
                                      group.hasSubItems
                                        ? "text-muted-foreground"
                                        : "font-medium text-foreground",
                                    )}
                                    title={title}
                                  >
                                    {structureNumberOnly(questionStructure, title)}
                                  </Label>
                                  <div className="flex shrink-0 items-center gap-2">
                                    <Input
                                      type="text"
                                      inputMode="decimal"
                                      value={String(scoringConfig[title] ?? 0)}
                                      onWheel={(e) => e.currentTarget.blur()}
                                      onChange={(e) => {
                                        const normalized =
                                          normalizeManualScoreInput(
                                            e.target.value,
                                          );
                                        const val =
                                          normalized === ""
                                            ? 0
                                            : parseFloat(normalized);
                                        setScoringConfig((prev) => ({
                                          ...prev,
                                          [title]: Number.isFinite(val)
                                            ? val
                                            : 0,
                                        }));
                                      }}
                                      className="h-8 w-20 text-center font-medium [appearance:textfield] focus-visible:ring-primary/50"
                                      placeholder="0"
                                    />
                                    <span className="w-4 text-xs text-muted-foreground">
                                      {t("grading.unit.score").trim()}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ))
                        )}
                      </div>
                    </ScrollArea>

                    <div className="flex items-center justify-between rounded-lg border border-border/50 bg-muted/10 p-3">
                      <div className="flex flex-col">
                        <span className="text-xs text-muted-foreground">
                          {t("grading.scoring.recognizedCount")}
                        </span>
                        <span className="text-sm font-medium">
                          {t("grading.scoring.itemCount", {
                            count: scoringQuestionTitles.length,
                          })}
                        </span>
                      </div>
                      <div className="flex flex-col items-end">
                        <span className="text-xs text-muted-foreground">
                          {fullScore != null
                            ? t("grading.scoring.fullScoreLabel")
                            : t("grading.scoring.totalScore")}
                        </span>
                        <div className="flex items-center gap-1">
                          <Input
                            type="text"
                            inputMode="decimal"
                            className="h-9 w-24 text-center text-lg font-bold text-primary"
                            value={fullScore != null ? String(fullScore) : ""}
                            placeholder={scoringQuestionTitles
                              .reduce(
                                (acc, t) => acc + (scoringConfig[t] || 0),
                                0,
                              )
                              .toFixed(1)}
                            onWheel={(e) => e.currentTarget.blur()}
                            onChange={(e) => {
                              const normalized = normalizeManualScoreInput(
                                e.target.value,
                              );
                              setFullScore(
                                normalized === ""
                                  ? null
                                  : parseFloat(normalized),
                              );
                            }}
                          />
                          <span className="text-xs font-normal">
                            {t("grading.unit.score").trim()}
                          </span>
                        </div>
                        {fullScore != null && (
                          <span className="text-xs text-muted-foreground">
                            {t("grading.scoring.sumHint", {
                              sum: scoringQuestionTitles
                                .reduce(
                                  (acc, t) => acc + (scoringConfig[t] || 0),
                                  0,
                                )
                                .toFixed(1),
                            })}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-wrap justify-end gap-2">
                      <Button
                        variant="outline"
                        onClick={() => setScoringDialogOpen(false)}
                        disabled={scoringSaving || scoringApplying}
                      >
                        {t("grading.action.close")}
                      </Button>
                      <Button
                        onClick={() =>
                          setNoticePending(
                            () => () => void handleApplyScoringConfig(),
                          )
                        }
                        disabled={
                          scoringSaving ||
                          scoringApplying ||
                          scoringQuestionTitles.length === 0
                        }
                        className="gap-2"
                      >
                        {scoringApplying ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <BarChart3 className="w-4 h-4" />
                        )}
                        {t("grading.action.applyScoring")}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}
          </div>

          {/* 放大预览 */}
          <Dialog
            open={!!zoomImageUrl}
            onOpenChange={(o) => {
              if (!o) {
                setZoomImageUrl(null);
                setZoomStudentFilename(null);
              }
            }}
          >
            {/*
            说明：DialogContent 默认是 grid + 垂直居中 translate，配合 max-h 容易把内容裁切到视口外（表现为只有遮罩/下半截被挡）。
            这里强制 flex，并改为靠上对齐（top + translate-y-0），整卡可滚动。
          */}
            <DialogContent
              className={cn(
                "!flex !flex-col gap-0 overflow-y-auto overflow-x-hidden",
                "z-[51] max-h-[min(92vh,100dvh)] w-[min(95vw,1200px)] p-0 pt-12 pb-4",
                "top-[4vh] left-1/2 -translate-x-1/2 translate-y-0",
                "border bg-background shadow-lg sm:rounded-lg",
              )}
            >
              <DialogTitle className="sr-only">
                {t("grading.preview.title")}
              </DialogTitle>
              {zoomStudentFilename &&
                !completedByFilename[zoomStudentFilename] &&
                !deleteMode && (
                  <div className="sticky top-0 z-10 flex items-center justify-end gap-2 border-b bg-background/95 px-4 py-2 backdrop-blur supports-[backdrop-filter]:bg-background/80">
                    <Button
                      size="sm"
                      className="gap-1.5"
                      disabled={
                        refLoading ||
                        ((gradingEngine === "aliyun" ||
                          gradingEngine === "smart_ref") &&
                          !standardAnswer)
                      }
                      title={
                        (gradingEngine === "aliyun" ||
                          gradingEngine === "smart_ref") &&
                        !standardAnswer
                          ? t("grading.preview.uploadStdFirst")
                          : undefined
                      }
                      onClick={() => {
                        if (
                          !zoomStudentFilename ||
                          ((gradingEngine === "aliyun" ||
                            gradingEngine === "smart_ref") &&
                            !standardAnswer)
                        )
                          return;
                        setNoticePending(
                          () => () =>
                            void handleStartRefGrade(zoomStudentFilename),
                        );
                      }}
                    >
                      {refLoading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <PenTool className="w-4 h-4" />
                      )}
                      {t("grading.action.gradeOne")}
                    </Button>
                  </div>
                )}
              <div className="px-3">
                {zoomImageUrl &&
                  (() => {
                    // url 可能带 ?v=mtime；判断类型需去掉 query/hash
                    const clean = zoomImageUrl
                      .split("?")[0]
                      .split("#")[0]
                      .toLowerCase();
                    const fullUrl = gradingImageUrl(zoomImageUrl);
                    if (clean.endsWith(".pdf")) {
                      return (
                        <div className="space-y-2">
                          <p className="text-sm text-muted-foreground text-center">
                            {t("grading.preview.pdfScrollHint")}
                          </p>
                          <div className="w-full overflow-auto rounded border bg-muted/30 p-2">
                            <div className="flex w-full justify-center">
                              <GradingErrorBoundary>
                                <PdfPreview
                                  url={zoomImageUrl}
                                  className="w-full max-w-full"
                                  width={Math.min(
                                    800,
                                    typeof window !== "undefined"
                                      ? window.innerWidth * 0.85
                                      : 800,
                                  )}
                                />
                              </GradingErrorBoundary>
                            </div>
                          </div>
                          <div className="text-center text-xs text-muted-foreground">
                            {t("grading.preview.pdfFallbackHint")}
                            <a
                              className="text-primary underline ml-1"
                              href={fullUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {t("grading.action.openInNewTab")}
                            </a>
                          </div>
                        </div>
                      );
                    }
                    if (clean.endsWith(".doc") || clean.endsWith(".docx")) {
                      return (
                        <div className="flex flex-col items-center justify-center gap-4 py-10 text-center">
                          <p className="text-muted-foreground">
                            {t("grading.preview.wordOpenHint")}
                          </p>
                          <a
                            href={fullUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary underline"
                          >
                            {t("grading.action.openInNewTab")}
                          </a>
                        </div>
                      );
                    }
                    if (zoomPreviewError) {
                      return (
                        <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
                          <p className="text-sm text-muted-foreground">
                            {t("grading.preview.loadFailed")}
                          </p>
                          <a
                            href={fullUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary underline"
                          >
                            {t("grading.action.openInNewTab")}
                          </a>
                        </div>
                      );
                    }
                    return (
                      <div className="flex w-full items-center justify-center py-2">
                        <img
                          src={fullUrl}
                          alt={t("grading.preview.altPreview")}
                          className="max-h-[min(72vh,720px)] max-w-full w-auto object-contain rounded shadow-sm"
                          onError={() => setZoomPreviewError(true)}
                        />
                      </div>
                    );
                  })()}
              </div>
            </DialogContent>
          </Dialog>

          <Dialog open={standardBoxOpen} onOpenChange={setStandardBoxOpen}>
            <DialogContent className="max-h-[92vh] w-full max-w-[min(94vw,980px)] overflow-hidden p-0 sm:max-w-[min(94vw,980px)]">
              <DialogHeader className="border-b bg-emerald-50/50 px-6 py-4 pr-14 text-left">
                <DialogTitle>{t("grading.standardBox.title")}</DialogTitle>
                <DialogDescription>
                  {t("grading.standardBox.description", {
                    capacity: paperBoxCapacity,
                  })}
                </DialogDescription>
              </DialogHeader>
              <div className="grid min-h-0 grid-cols-1 lg:grid-cols-[5rem_minmax(0,1fr)]">
                <div className="flex gap-1 overflow-x-auto border-b bg-muted/20 p-2 lg:flex-col lg:overflow-y-auto lg:border-b-0 lg:border-r lg:py-3">
                  {Array.from(
                    { length: paperBoxCapacity },
                    (_, index) => index + 1,
                  ).map((page) => {
                    const slot = standardAnswerSlots[page - 1];
                    const active = standardBoxPageNo === page;
                    return (
                      <button
                        key={`standard-page-${page}`}
                        type="button"
                        title={
                          slot?.filename ||
                          t("grading.standardBox.emptyPage", { page })
                        }
                        className={cn(
                          "relative flex h-10 w-10 shrink-0 items-center justify-center rounded border text-xs font-semibold transition-colors lg:h-12 lg:w-full",
                          active
                            ? "border-primary bg-primary text-primary-foreground"
                            : slot
                              ? "border-emerald-200 bg-emerald-50 text-emerald-800 hover:border-emerald-300"
                              : "border-dashed border-muted-foreground/35 bg-background text-muted-foreground hover:border-primary/40",
                        )}
                        onClick={() => setStandardBoxPageNo(page)}
                      >
                        P{page}
                        {slot && !active ? (
                          <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-background" />
                        ) : null}
                      </button>
                    );
                  })}
                </div>
                <div className="flex min-h-0 flex-col gap-3 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-semibold">
                        {t("grading.standardBox.pageTitle", {
                          page: standardBoxPageNo,
                        })}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {t("grading.standardBox.pagePairing", {
                          page: standardBoxPageNo,
                        })}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {gradingEngine === "aliyun" &&
                      referenceLayoutStatus.confirmed ? (
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-1.5"
                          disabled={referenceLayoutOpening || refLoading}
                          onClick={() => void handleViewReferenceLayout()}
                        >
                          {referenceLayoutOpening ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Eye className="h-4 w-4" />
                          )}
                          {t("grading.layout.viewButton")}
                        </Button>
                      ) : null}
                      {gradingEngine === "aliyun" ? (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1.5"
                            disabled={refLoading || layoutTemplateSaving}
                            onClick={() => {
                              setLayoutTemplateMode("save");
                              setLayoutTemplateOpen(true);
                            }}
                          >
                            <Save className="h-4 w-4" />
                            {t("layoutTemplate.save")}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1.5"
                            disabled={
                              refLoading ||
                              referenceLayoutPreparing ||
                              referenceLayoutOpening
                            }
                            onClick={() => {
                              setLayoutTemplateMode("apply");
                              setLayoutTemplateOpen(true);
                            }}
                          >
                            <Sparkles className="h-4 w-4" />
                            {t("layoutTemplate.apply")}
                          </Button>
                        </>
                      ) : null}
                      {standardBoxCurrentSlot ? (
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-1.5 border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
                          disabled={
                            standardBoxUploading ||
                            standardBoxDeleting ||
                            refLoading
                          }
                          onClick={() => setStandardBoxDeleteOpen(true)}
                        >
                          {standardBoxDeleting ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                          {t("grading.action.deleteThisPage")}
                        </Button>
                      ) : null}
                      <Button
                        size="sm"
                        className="gap-1.5"
                        disabled={
                          standardBoxUploading ||
                          standardBoxDeleting ||
                          refLoading
                        }
                        onClick={() =>
                          triggerStandardBoxUpload(standardBoxPageNo)
                        }
                      >
                        {standardBoxUploading ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Upload className="h-4 w-4" />
                        )}
                        {standardBoxCurrentSlot
                          ? t("grading.standardBox.replacePage")
                          : t("grading.action.uploadThisPage")}
                      </Button>
                    </div>
                  </div>
                  <div className="flex h-[min(66vh,650px)] min-h-[320px] items-center justify-center overflow-hidden rounded border bg-muted/20">
                    {standardBoxCurrentSlot ? (
                      fileType(standardBoxCurrentSlot) === "word" ? (
                        <div className="flex flex-col items-center justify-center gap-3 text-center">
                          <span className="text-sm text-muted-foreground">
                            {t("grading.preview.wordDoc")}
                          </span>
                          <a
                            href={gradingImageUrl(standardBoxCurrentSlot.url)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-primary underline"
                          >
                            {t("grading.preview.openPreview")}
                          </a>
                        </div>
                      ) : (
                        <img
                          src={gradingImageUrl(standardBoxCurrentSlot.url)}
                          alt={t("grading.standardBox.pageTitle", {
                            page: standardBoxPageNo,
                          })}
                          className="h-full w-full object-contain"
                        />
                      )
                    ) : (
                      <div className="flex flex-col items-center justify-center gap-3 text-center">
                        <p className="text-sm text-muted-foreground">
                          {t("grading.standardBox.emptyPage", {
                            page: standardBoxPageNo,
                          })}
                        </p>
                        <Button
                          variant="secondary"
                          size="sm"
                          className="gap-2"
                          disabled={standardBoxUploading || refLoading}
                          onClick={() =>
                            triggerStandardBoxUpload(standardBoxPageNo)
                          }
                        >
                          {standardBoxUploading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Upload className="h-4 w-4" />
                          )}
                          {t("grading.action.clickUploadThisPage")}
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </DialogContent>
          </Dialog>

          <input
            ref={standardBoxUploadInputRef}
            type="file"
            accept="image/*,.pdf,.doc,.docx"
            className="hidden"
            disabled={standardBoxUploading || refLoading}
            onChange={handleStandardBoxSlotUpload}
          />

          <AlertDialog
            open={standardBoxDeleteOpen}
            onOpenChange={setStandardBoxDeleteOpen}
          >
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t("grading.standardBox.deleteTitle")}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t("grading.standardBox.deleteDescription", {
                    page: standardBoxPageNo,
                  })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={standardBoxDeleting}>
                  {t("common.cancel")}
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={(event) => {
                    event.preventDefault();
                    void handleConfirmStandardBoxDelete();
                  }}
                  disabled={standardBoxDeleting || !standardBoxCurrentSlot}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {standardBoxDeleting
                    ? t("grading.status.deleting")
                    : t("grading.action.confirmDelete")}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <input
            ref={paperBoxUploadInputRef}
            type="file"
            accept="image/*,.pdf,.doc,.docx"
            className="hidden"
            onChange={handlePaperBoxSlotUpload}
          />

          {/* 批改详情：试卷预览 + AI */}
          <Dialog
            open={gradingPreviewOpen}
            onOpenChange={(o) => {
              if (!o) closeGradingPreviewDialog();
            }}
          >
            <DialogContent className="max-h-[96vh] w-full max-w-[min(98vw,1380px)] flex flex-col gap-0 overflow-hidden p-0 sm:max-w-[min(98vw,1380px)]">
              {detailItem && (
                <>
                  <div className="shrink-0 border-b bg-muted/30 px-6 py-4 pr-14">
                    <DialogHeader className="space-y-1 text-left">
                      <DialogTitle className="text-lg">
                        {paperBoxPreviewMode
                          ? t("grading.paperBox.previewTitle")
                          : t("grading.preview.detailTitle")}
                      </DialogTitle>
                      <DialogDescription className="truncate">
                        {paperBoxPreviewMode && activePaperBox ? (
                          <span title={activePaperBox.student.name}>
                            {activePaperBox.student.name}
                            <span className="text-muted-foreground">
                              {" "}
                              {t("grading.paperBox.pageIndicator", {
                                current: previewPaperBoxPageNo,
                                total: paperBoxCapacity,
                              })}
                              {detailItem?.name ? ` · ${detailItem.name}` : ""}
                            </span>
                          </span>
                        ) : (
                          <span title={detailItem?.name}>
                            {detailItem?.name}
                          </span>
                        )}
                      </DialogDescription>
                    </DialogHeader>
                  </div>
                  {detailItem?.result ? (
                    <div
                      className={cn(
                        "grid min-h-0 flex-1 gap-0 lg:min-h-[min(76vh,calc(92vh-6rem))]",
                        paperBoxPreviewMode
                          ? "grid-cols-1 lg:grid-cols-[4.5rem_minmax(0,1fr)_minmax(0,1fr)] lg:divide-x"
                          : "grid-cols-1 lg:grid-cols-2 lg:divide-x",
                      )}
                    >
                      {renderPaperBoxPageSidebar()}
                      <div
                        key={`pb-preview-${previewPaperBoxPageNo}-${detailItem?.name || "empty"}`}
                        className={cn(
                          "flex min-h-0 flex-col gap-3 bg-muted/15 p-4 lg:h-full",
                          paperBoxPreviewAnimClass,
                        )}
                      >
                        <div className="flex shrink-0 flex-wrap items-start justify-between gap-2">
                          <Label className="text-sm font-semibold text-foreground">
                            {t("grading.preview.marksPreview")}
                          </Label>
                          <div className="flex flex-wrap items-center justify-end gap-2">
                            {renderPaperBoxUploadButton()}
                            {renderPaperBoxDeleteButton()}
                            {detailItem?.name && isManualEngine(gradingEngine) ? (
                              showManualScoreInputs ? (
                                <>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void openManualSibling(-1)}
                                    disabled={
                                      manualSwitching ||
                                      manualGradeSaving ||
                                      manualClearing
                                    }
                                    className="gap-1.5 shrink-0 whitespace-nowrap"
                                  >
                                    {manualSwitching ? (
                                      <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                      <ArrowLeft className="w-4 h-4" />
                                    )}
                                    {t("grading.action.prevPaper")}
                                  </Button>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void openManualSibling(1)}
                                    disabled={
                                      manualSwitching ||
                                      manualGradeSaving ||
                                      manualClearing
                                    }
                                    className="gap-1.5 shrink-0 whitespace-nowrap"
                                  >
                                    {manualSwitching ? (
                                      <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                      <ArrowRight className="w-4 h-4" />
                                    )}
                                    {t("grading.action.nextPaper")}
                                  </Button>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() =>
                                      setManualClearConfirmOpen(true)
                                    }
                                    disabled={
                                      manualSwitching ||
                                      manualGradeSaving ||
                                      manualClearing
                                    }
                                    className="gap-1.5 shrink-0 whitespace-nowrap"
                                  >
                                    <Eraser className="w-4 h-4" />
                                    {t("grading.action.clearAllScores")}
                                  </Button>
                                  <Button
                                    variant="default"
                                    size="sm"
                                    onClick={handleSaveManualGrade}
                                    disabled={
                                      manualGradeSaving ||
                                      manualSwitching ||
                                      manualClearing
                                    }
                                    className="gap-1.5 shrink-0 whitespace-nowrap"
                                  >
                                    {manualGradeSaving ? (
                                      <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                      <Save className="w-4 h-4" />
                                    )}
                                    {t("grading.action.finishNext")}
                                  </Button>
                                </>
                              ) : (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() =>
                                    setManualEditingName(detailItem!.name)
                                  }
                                  className="gap-1.5 shrink-0 whitespace-nowrap"
                                >
                                  <PenTool className="w-4 h-4" />
                                  {t("grading.action.regrade")}
                                </Button>
                              )
                            ) : (
                              detailItem?.name && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() =>
                                    setNoticePending(
                                      () => () =>
                                        void handleStartRefGrade(
                                          detailItem!.name,
                                        ),
                                    )
                                  }
                                  disabled={refLoading}
                                  className="gap-1.5 shrink-0 whitespace-nowrap"
                                >
                                  {refLoading ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                  ) : (
                                    <PenTool className="w-4 h-4" />
                                  )}
                                  {t("grading.action.regradeSmart")}
                                </Button>
                              )
                            )}
                            {(gradingEngine === "baidu" ||
                              gradingEngine === "smart_ref" ||
                              gradingEngine === "aliyun") &&
                              detailItem?.blocks?.length ? (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={openAiCorrectDialog}
                                className="gap-1.5 shrink-0 whitespace-nowrap"
                              >
                                <Edit2 className="w-4 h-4" />
                                编辑批改
                              </Button>
                            ) : null}
                            {detailItem?.image_original && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setDetailShowOriginal((v) => !v)}
                                className="shrink-0 whitespace-nowrap"
                              >
                                {detailShowOriginal
                                  ? t("grading.action.viewGraded")
                                  : t("grading.action.viewOriginal")}
                              </Button>
                            )}
                            {detailItem?.image_annotated &&
                            !detailShowOriginal &&
                            wrongAnnoEngine &&
                            (detailItem.image_annotated_with_wrong_notes ||
                              Object.keys(wrongAnnotations).length > 0) ? (
                              <button
                                type="button"
                                onClick={() => setPreviewWrongNotes((v) => !v)}
                                className={cn(
                                  "flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md border px-2 py-1.5 text-xs transition-colors",
                                  previewWrongNotes
                                    ? "border-orange-300 bg-orange-50 text-orange-700"
                                    : "border-border/70 bg-background text-muted-foreground",
                                )}
                                title={t(
                                  "grading.preview.showWrongNotesHint",
                                  undefined,
                                  "预览试卷上是否显示错因批注",
                                )}
                              >
                                {previewWrongNotes ? (
                                  <Check className="w-3 h-3" />
                                ) : (
                                  <X className="w-3 h-3" />
                                )}
                                {t(
                                  "grading.preview.showWrongNotes",
                                  undefined,
                                  "显示批注",
                                )}
                              </button>
                            ) : null}
                            {gradingEngine === "essay" &&
                              detailItem?.result && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() =>
                                    void handleEssayDownloadPdf(
                                      detailItem!.name,
                                    )
                                  }
                                  className="gap-2 shrink-0 whitespace-nowrap"
                                >
                                  <Download className="w-4 h-4" />
                                  {t("grading.action.downloadPdf")}
                                </Button>
                              )}
                            {detailItem?.image_marks_only &&
                              renderPrintWrongNotesToggle()}
                            {detailItem?.image_marks_only && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={handlePrintOne}
                                disabled={printOneLoading}
                                className="gap-2 shrink-0 whitespace-nowrap"
                              >
                                {printOneLoading ? (
                                  <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                  <Printer className="w-4 h-4" />
                                )}
                                {printOneLoading
                                  ? t("grading.status.sending")
                                  : t("grading.action.printMarks")}
                              </Button>
                            )}
                            {detailItem?.image_marks_only && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={handleExportMarksPdfOne}
                                disabled={exportPdfOneLoading}
                                className="gap-2 shrink-0 whitespace-nowrap"
                              >
                                {exportPdfOneLoading ? (
                                  <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                  <Download className="w-4 h-4" />
                                )}
                                {t("grading.action.exportMarksPdf")}
                              </Button>
                            )}
                            {detailItem?.image_marks_only && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={handleBrowserPrintOne}
                                disabled={browserPrintOneLoading}
                                className="gap-2 shrink-0 whitespace-nowrap"
                              >
                                {browserPrintOneLoading ? (
                                  <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                  <Printer className="w-4 h-4" />
                                )}
                                {t("grading.action.browserPrint")}
                              </Button>
                            )}
                          </div>
                        </div>
                        <div className="flex h-[min(52vh,500px)] w-full items-center justify-center overflow-hidden rounded-xl border border-border/80 bg-background shadow-inner lg:h-[min(66vh,calc(92vh-12rem))]">
                          <div className="flex h-full w-full items-center justify-center p-3">
                            {paperBoxPreviewMode && !paperBoxCurrentSlot ? (
                              renderPaperBoxEmptyPreview()
                            ) : detailPreviewPath ? (
                              <ZoomableImage
                                src={gradingImageUrl(detailPreviewPath)}
                                alt={
                                  detailShowOriginal ||
                                  isManualRegrading ||
                                  !manualHasFinalMarks
                                    ? t("grading.preview.altOriginal")
                                    : t("grading.preview.altMarked")
                                }
                              />
                            ) : (
                              <div className="text-sm text-muted-foreground">
                                {t("grading.preview.notFound")}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                      <div
                        key={`pb-ai-${previewPaperBoxPageNo}-${detailItem?.name || "empty"}`}
                        className={cn(
                          "flex min-h-0 flex-col gap-3 p-4 lg:h-full",
                          paperBoxPreviewMode && paperBoxPreviewAnimClass,
                        )}
                      >
                        <div className="flex shrink-0 items-center justify-between gap-2">
                          <div className="flex shrink-0 items-center gap-2">
                            <Label className="shrink-0 text-sm font-semibold text-foreground">
                              {isManualEngine(gradingEngine)
                                ? t("grading.manual.title")
                                : t("grading.ai.title")}
                            </Label>
                            {!isManualEngine(gradingEngine) && <AIGeneratedBadge />}
                          </div>
                          {isManualEngine(gradingEngine) && (
                            <div className="text-sm font-bold text-primary mr-2">
                              {t("grading.manual.totalScore", {
                                score: Object.values(manualGradeScores).reduce(
                                  (acc, v) => acc + (parseFloat(v) || 0),
                                  0,
                                ),
                              })}
                            </div>
                          )}
                          {gradingEngine === "essay" && detailItem?.name && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={openEssayResultEdit}
                              className="gap-1.5 shrink-0"
                            >
                              <Edit2 className="h-3.5 w-3.5" />
                              {t("grading.essay.editResult", undefined, "编辑文案")}
                            </Button>
                          )}
                          {gradingEngine === "essay" && detailItem?.name && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={openEssayNoteEdit}
                              className="gap-1.5 shrink-0"
                            >
                              <PenTool className="h-3.5 w-3.5" />
                              老师总评
                            </Button>
                          )}
                        </div>
                        {gradingEngine === "essay" && detailItem?.name && (
                          <EssayDimensionScoreCard
                            dimensions={rubricDimensions}
                            dimensionScores={detailItem?.dimension_scores}
                            totalScore={detailItem?.score_total}
                            essayGrade={detailItem?.essay_grade}
                            filename={detailItem.name}
                            onSave={handleSaveEssayScore}
                            t={t}
                          />
                        )}
                        <ScrollArea className="h-[min(60vh,620px)] w-full rounded-xl border border-border/80 bg-card p-4 text-sm leading-relaxed shadow-sm lg:h-[min(76vh,calc(96vh-11rem))]">
                          <div className="space-y-3">
                            {isManualEngine(gradingEngine)
                              ? (() => {
                                  if (detailManualGroups.length === 0) {
                                    return (
                                      <div className="text-muted-foreground py-4 text-center">
                                        {t("grading.manual.noAnalysisData")}
                                      </div>
                                    );
                                  }

                                  return detailManualGroups.map(
                                    renderManualGroupCard,
                                  );
                                })()
                              : detailAiBlocks.map((b, idx) => (
                                  <div key={`${b.title}-${idx}`}>
                                    {idx > 0 && (
                                      <div className="mb-3 border-t border-border/70" />
                                    )}
                                    <div className="mb-1.5 flex items-center">
                                      <div className="text-xs font-semibold text-muted-foreground">
                                        {structureDisplayFor(questionStructure, b.title)}
                                      </div>
                                      {renderAiStatusCounts(b)}
                                    </div>
                                    <div className="space-y-1.5">
                                      {b.subItems && b.subItems.length > 0 ? (
                                        b.subItems.map((sub, subIdx) => (
                                          <div
                                            key={subIdx}
                                            className={cn(
                                              "whitespace-pre-wrap rounded-md px-2.5 py-1.5",
                                              sub.status === "wrong" ||
                                                sub.status === "blank"
                                                ? "bg-red-50 text-red-900 border border-red-100"
                                                : sub.status === "partial"
                                                  ? "bg-amber-50 text-amber-900 border border-amber-100"
                                                  : "text-foreground/95",
                                            )}
                                          >
                                            {renderSubItemContent(b.title, sub.content, questionStructure)}
                                          </div>
                                        ))
                                      ) : (
                                        <p className="whitespace-pre-wrap text-foreground/95 px-2.5">
                                          {b.content}
                                        </p>
                                      )}
                                    </div>
                                    {renderWrongAnnoForAiBlock(b)}
                                  </div>
                                ))}
                          </div>
                        </ScrollArea>
                      </div>
                    </div>
                  ) : (
                    <div
                      className={cn(
                        "grid min-h-0 flex-1 gap-0 lg:min-h-[min(76vh,calc(92vh-6rem))]",
                        paperBoxPreviewMode
                          ? "grid-cols-1 lg:grid-cols-[4.5rem_minmax(0,1fr)_minmax(0,1fr)] lg:divide-x"
                          : "grid-cols-1 lg:grid-cols-2 lg:divide-x",
                      )}
                    >
                      {renderPaperBoxPageSidebar()}
                      <div
                        key={`pb-preview-${previewPaperBoxPageNo}-${detailItem?.name || "empty"}`}
                        className={cn(
                          "flex min-h-0 flex-col gap-3 bg-muted/15 p-4 lg:h-full",
                          paperBoxPreviewAnimClass,
                        )}
                      >
                        <div className="flex shrink-0 flex-wrap items-start justify-between gap-2">
                          <Label className="text-sm font-semibold text-foreground">
                            {paperBoxPreviewMode
                              ? t("grading.preview.marksPreview")
                              : t("grading.preview.paperPreview")}
                          </Label>
                          <div className="flex flex-wrap items-center justify-end gap-2">
                            {renderPaperBoxUploadButton()}
                            {renderPaperBoxDeleteButton()}
                            {detailItem?.name && isManualEngine(gradingEngine) ? (
                              showManualScoreInputs ? (
                                <>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void openManualSibling(-1)}
                                    disabled={
                                      manualSwitching ||
                                      manualGradeSaving ||
                                      manualClearing
                                    }
                                    className="gap-1.5 shrink-0 whitespace-nowrap"
                                  >
                                    {manualSwitching ? (
                                      <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                      <ArrowLeft className="w-4 h-4" />
                                    )}
                                    {t("grading.action.prevPaper")}
                                  </Button>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void openManualSibling(1)}
                                    disabled={
                                      manualSwitching ||
                                      manualGradeSaving ||
                                      manualClearing
                                    }
                                    className="gap-1.5 shrink-0 whitespace-nowrap"
                                  >
                                    {manualSwitching ? (
                                      <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                      <ArrowRight className="w-4 h-4" />
                                    )}
                                    {t("grading.action.nextPaper")}
                                  </Button>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() =>
                                      setManualClearConfirmOpen(true)
                                    }
                                    disabled={
                                      manualSwitching ||
                                      manualGradeSaving ||
                                      manualClearing
                                    }
                                    className="gap-1.5 shrink-0 whitespace-nowrap"
                                  >
                                    <Eraser className="w-4 h-4" />
                                    {t("grading.action.clearAllScores")}
                                  </Button>
                                  <Button
                                    variant="default"
                                    size="sm"
                                    onClick={handleSaveManualGrade}
                                    disabled={
                                      manualGradeSaving ||
                                      manualSwitching ||
                                      manualClearing
                                    }
                                    className="gap-1.5 shrink-0 whitespace-nowrap"
                                  >
                                    {manualGradeSaving ? (
                                      <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                      <Save className="w-4 h-4" />
                                    )}
                                    {t("grading.action.finishNext")}
                                  </Button>
                                </>
                              ) : (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() =>
                                    setManualEditingName(detailItem!.name)
                                  }
                                  className="gap-1.5 shrink-0 whitespace-nowrap"
                                >
                                  <PenTool className="w-4 h-4" />
                                  {t("grading.action.regrade")}
                                </Button>
                              )
                            ) : gradingEngine === "essay" &&
                              detailItem?.name ? (
                              <>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() =>
                                    void handleEssayPrintPdf(detailItem!.name)
                                  }
                                  className="gap-2 shrink-0 whitespace-nowrap"
                                >
                                  <Printer className="w-4 h-4" />
                                  {t("grading.action.printResult")}
                                </Button>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() =>
                                    void handleEssayDownloadPdf(
                                      detailItem!.name,
                                    )
                                  }
                                  className="shrink-0 whitespace-nowrap"
                                >
                                  {t("grading.action.downloadPdf")}
                                </Button>
                              </>
                            ) : (
                              detailItem?.name && (
                                <>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() =>
                                      setNoticePending(
                                        () => () =>
                                          void handleStartRefGrade(
                                            detailItem!.name,
                                          ),
                                      )
                                    }
                                    disabled={refLoading}
                                    className="gap-1.5 shrink-0 whitespace-nowrap"
                                  >
                                    {refLoading ? (
                                      <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                      <PenTool className="w-4 h-4" />
                                    )}
                                    {t("grading.action.regradeSmart")}
                                  </Button>
                                  {detailItem?.image_marks_only &&
                                    renderPrintWrongNotesToggle()}
                                  {detailItem?.image_marks_only && (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={handlePrintOne}
                                      disabled={printOneLoading}
                                      className="gap-2 shrink-0 whitespace-nowrap"
                                    >
                                      {printOneLoading ? (
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                      ) : (
                                        <Printer className="w-4 h-4" />
                                      )}
                                      {printOneLoading
                                        ? t("grading.status.sending")
                                        : t("grading.action.printMarks")}
                                    </Button>
                                  )}
                                  {detailItem?.image_marks_only && (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={handleExportMarksPdfOne}
                                      disabled={exportPdfOneLoading}
                                      className="gap-2 shrink-0 whitespace-nowrap"
                                    >
                                      {exportPdfOneLoading ? (
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                      ) : (
                                        <Download className="w-4 h-4" />
                                      )}
                                      {t("grading.action.exportMarksPdf")}
                                    </Button>
                                  )}
                                  {detailItem?.image_marks_only && (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={handleBrowserPrintOne}
                                      disabled={browserPrintOneLoading}
                                      className="gap-2 shrink-0 whitespace-nowrap"
                                    >
                                      {browserPrintOneLoading ? (
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                      ) : (
                                        <Printer className="w-4 h-4" />
                                      )}
                                      {t("grading.action.browserPrint")}
                                    </Button>
                                  )}
                                </>
                              )
                            )}
                          </div>
                        </div>
                        <div className="flex h-[min(52vh,500px)] w-full items-center justify-center overflow-hidden rounded-xl border border-border/80 bg-background shadow-inner lg:h-[min(66vh,calc(92vh-12rem))]">
                          <div className="flex h-full w-full items-center justify-center p-3">
                            {paperBoxPreviewMode && !paperBoxCurrentSlot
                              ? renderPaperBoxEmptyPreview()
                              : (() => {
                                  const file = folderFiles.find(
                                    (f) => f.name === detailItem?.name,
                                  );
                                  const url = file?.url || "";
                                  const fullUrl = gradingImageUrl(url);
                                  if (!url)
                                    return (
                                      <div className="text-sm text-muted-foreground">
                                        {t("grading.preview.notFound")}
                                      </div>
                                    );
                                  return (
                                    <ZoomableImage
                                      src={fullUrl}
                                      alt={t("grading.preview.paperPreview")}
                                    />
                                  );
                                })()}
                          </div>
                        </div>
                      </div>
                      <div
                        key={`pb-ai-ungraded-${previewPaperBoxPageNo}-${detailItem?.name || "empty"}`}
                        className={cn(
                          "flex min-h-0 flex-col gap-3 p-4 lg:h-full",
                          paperBoxPreviewMode && paperBoxPreviewAnimClass,
                        )}
                      >
                        <div className="flex shrink-0 items-center justify-between gap-2">
                          <div className="flex shrink-0 items-center gap-2">
                            <Label className="shrink-0 text-base font-semibold text-foreground">
                              {isManualEngine(gradingEngine)
                                ? t("grading.manual.title")
                                : t("grading.ai.title")}
                            </Label>
                            {!isManualEngine(gradingEngine) && <AIGeneratedBadge />}
                          </div>
                          {isManualEngine(gradingEngine) && (
                            <div className="text-sm font-bold text-primary mr-2">
                              {t("grading.manual.totalScore", {
                                score: Object.values(manualGradeScores).reduce(
                                  (acc, v) => acc + (parseFloat(v) || 0),
                                  0,
                                ),
                              })}
                            </div>
                          )}
                        </div>
                        <ScrollArea className="h-[min(60vh,620px)] w-full rounded-xl border border-border/80 bg-card p-4 text-base leading-relaxed shadow-sm lg:h-[min(76vh,calc(96vh-11rem))]">
                          <div className="space-y-4">
                            {paperBoxPreviewMode && !detailItem?.result ? (
                              <div className="flex min-h-[200px] flex-col items-center justify-center py-12 text-center text-base text-muted-foreground">
                                {t("grading.ai.noResult")}
                              </div>
                            ) : isManualEngine(gradingEngine) ? (
                              (() => {
                                if (detailManualBlocks.length === 0) {
                                  return (
                                    <div className="text-muted-foreground py-4 text-center">
                                      {t("grading.manual.noAnalysisData")}
                                    </div>
                                  );
                                }

                                return detailManualGroups.map(
                                  renderManualGroupCard,
                                );
                              })()
                            ) : (
                              detailAiBlocks.map((b, idx) => (
                                <div key={`${b.title}-${idx}`}>
                                  {idx > 0 && (
                                    <div className="mb-4 border-t border-border/70" />
                                  )}
                                  <div className="mb-2 flex items-center">
                                    <div className="text-sm font-semibold text-muted-foreground">
                                      {structureDisplayFor(questionStructure, b.title)}
                                    </div>
                                    {renderAiStatusCounts(b)}
                                  </div>
                                  <div className="space-y-2">
                                    {b.subItems && b.subItems.length > 0 ? (
                                      b.subItems.map((sub, subIdx) => (
                                        <div
                                          key={subIdx}
                                          className={cn(
                                            "whitespace-pre-wrap rounded-md px-2.5 py-1.5",
                                            sub.status === "wrong" ||
                                              sub.status === "blank"
                                              ? "bg-red-50 text-red-900 border border-red-100"
                                              : sub.status === "partial"
                                                ? "bg-amber-50 text-amber-900 border border-amber-100"
                                                : "text-foreground/95",
                                          )}
                                        >
                                          {renderSubItemContent(b.title, sub.content, questionStructure)}
                                        </div>
                                      ))
                                    ) : (
                                      <p className="whitespace-pre-wrap text-foreground/95 px-2.5">
                                        {b.content}
                                      </p>
                                    )}
                                  </div>
                                  {renderWrongAnnoForAiBlock(b)}
                                </div>
                              ))
                            )}
                          </div>
                        </ScrollArea>
                      </div>
                    </div>
                  )}
                </>
              )}
            </DialogContent>
          </Dialog>

          <Dialog open={aiCorrectOpen} onOpenChange={setAiCorrectOpen}>
            <DialogContent className="max-w-2xl h-[92vh] flex flex-col overflow-hidden">
              <DialogHeader className="shrink-0">
                <DialogTitle>手动修正智能批改</DialogTitle>
                <DialogDescription className="truncate">
                  {detailItem?.name} · 逐题改对错/分数，批注会写在卷面留痕上
                </DialogDescription>
              </DialogHeader>
              <div className="min-h-0 flex-1 overflow-y-auto rounded-md border">
                <div className="space-y-2 p-4">
                  {(() => {
                    const groups: Record<string, AiBlock[]> = {};
                    for (const b of detailItem?.blocks ?? []) {
                      const qKey = String(b.index);
                      (groups[qKey] ??= []).push(b);
                    }
                    return Object.entries(groups).map(([qKey, blocks]) => {
                      const qNote = aiQuestionNotes[qKey] ?? "";
                      return (
                        <div
                          key={qKey}
                          className="space-y-2 rounded-md border px-3 py-2.5"
                        >
                          <span className="text-sm font-medium">
                            {structureDisplayFor(questionStructure, `第${qKey}题`)}
                          </span>
                          {blocks.map((b) => {
                            const key = `${b.index}::${b.sub_index ?? ""}`;
                            const value = aiCorrections[key] ?? b.result;
                            const score = aiScores[key] ?? "";
                            const subLabel =
                              b.baidu_is_slot && b.sub_index
                                ? subLabelAt(questionStructure?.[`第${qKey}题`]?.sub, b.sub_index)
                                : null;
                            return (
                              <div
                                key={key}
                                className="flex flex-wrap items-center gap-2"
                              >
                                {subLabel && (
                                  <span className="w-16 shrink-0 text-xs text-muted-foreground">
                                    {subLabel}
                                  </span>
                                )}
                                <div className="flex gap-1">
                                  {(["对", "错", "半对", "未作答"] as const).map((opt) => (
                                    <button
                                      key={opt}
                                      type="button"
                                      onClick={() =>
                                        setAiCorrections((prev) => ({
                                          ...prev,
                                          [key]: opt,
                                        }))
                                      }
                                      className={cn(
                                        "rounded-md px-3 py-1 text-sm font-medium transition-colors",
                                        value === opt
                                          ? "bg-primary text-primary-foreground"
                                          : "bg-muted text-muted-foreground hover:bg-muted/70",
                                      )}
                                    >
                                      {opt}
                                    </button>
                                  ))}
                                </div>
                                <div className="flex items-center gap-1.5">
                                  <span className="whitespace-nowrap text-xs text-muted-foreground">
                                    分数
                                  </span>
                                  <Input
                                    type="number"
                                    min={0}
                                    value={score}
                                    onChange={(e) =>
                                      setAiScores((prev) => ({
                                        ...prev,
                                        [key]: e.target.value,
                                      }))
                                    }
                                    placeholder="分"
                                    className="h-8 w-20 text-sm"
                                  />
                                </div>
                              </div>
                            );
                          })}
                          <div className="flex items-center gap-1.5">
                            <span className="whitespace-nowrap text-xs text-muted-foreground">
                              批注
                            </span>
                            <div className="flex shrink-0 gap-1">
                              {(["ai", "manual"] as const).map((src) => (
                                <button
                                  key={src}
                                  type="button"
                                  onClick={() => {
                                    setAiNoteSource((prev) => ({
                                      ...prev,
                                      [qKey]: src,
                                    }));
                                    if (src === "ai") {
                                      setAiQuestionNotes((prev) => ({
                                        ...prev,
                                        [qKey]: aiNoteTextForQuestion(blocks),
                                      }));
                                    }
                                  }}
                                  className={cn(
                                    "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                                    (aiNoteSource[qKey] ?? "manual") === src
                                      ? "bg-primary text-primary-foreground"
                                      : "bg-muted text-muted-foreground hover:bg-muted/70",
                                  )}
                                >
                                  {src === "ai" ? "AI批注" : "手动批注"}
                                </button>
                              ))}
                            </div>
                            <Input
                              value={qNote}
                              onChange={(e) =>
                                setAiQuestionNotes((prev) => ({
                                  ...prev,
                                  [qKey]: e.target.value,
                                }))
                              }
                              placeholder="老师批注（会写在该题下方）"
                              className="h-8 flex-1 text-sm"
                            />
                          </div>
                          {(() => {
                            const vals = blocks.map(
                              (b) =>
                                aiCorrections[`${b.index}::${b.sub_index ?? ""}`] ??
                                b.result,
                            );
                            const wrongLike = vals.some(
                              (v) => v === "错" || v === "半对",
                            );
                            const blankLike = vals.some((v) => v === "未作答");
                            const allCorrect =
                              vals.length > 0 && vals.every((v) => v === "对");
                            if (
                              !wrongAnnotations[qKey] &&
                              !wrongLike &&
                              !blankLike
                            )
                              return null;
                            return renderWrongAnnotationCard(qKey, {
                              wrong: wrongLike,
                              muted: allCorrect,
                            });
                          })()}
                        </div>
                      );
                    });
                  })()}
                  <div className="space-y-1.5 rounded-md border px-3 py-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">试卷总评</span>
                      <div className="flex shrink-0 gap-1">
                        {(["ai", "manual"] as const).map((src) => (
                          <button
                            key={src}
                            type="button"
                            onClick={() => {
                              if (src === "ai") {
                                setAiPaperNoteSource("ai");
                                handleGenerateAiSummary();
                              } else {
                                setAiPaperNoteSource("manual");
                              }
                            }}
                            className={cn(
                              "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                              aiPaperNoteSource === src
                                ? "bg-primary text-primary-foreground"
                                : "bg-muted text-muted-foreground hover:bg-muted/70",
                            )}
                          >
                            {src === "ai"
                              ? aiSummaryLoading
                                ? "生成中…"
                                : "AI批注"
                              : "手动批注"}
                          </button>
                        ))}
                      </div>
                    </div>
                    <Textarea
                      value={aiPaperNote}
                      onChange={(e) => setAiPaperNote(e.target.value)}
                      placeholder="整卷总评（会写在卷面底部）"
                      className="min-h-[64px] text-sm"
                    />
                  </div>
                </div>
              </div>
              <DialogFooter className="shrink-0 pt-3">
                <Button
                  variant="outline"
                  onClick={() => setAiCorrectOpen(false)}
                  disabled={aiCorrectSaving}
                >
                  取消
                </Button>
                <Button onClick={handleSaveAiCorrect} disabled={aiCorrectSaving}>
                  {aiCorrectSaving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4" />
                  )}
                  保存
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Dialog open={essayResultEditOpen} onOpenChange={setEssayResultEditOpen}>
            <DialogContent className="max-w-3xl max-h-[92vh] flex flex-col">
              <DialogHeader>
                <DialogTitle>{t("grading.essay.editResultTitle", undefined, "编辑批改文案")}</DialogTitle>
                <DialogDescription className="truncate">
                  {detailItem?.name} · 直接修改 AI 生成的评语/总评/建议等文案后保存
                </DialogDescription>
              </DialogHeader>
              <Textarea
                value={essayResultDraft}
                onChange={(e) => setEssayResultDraft(e.target.value)}
                className="min-h-[60vh] flex-1 resize-none font-mono text-sm leading-relaxed"
                placeholder="批改文案…"
              />
              <DialogFooter className="pt-3">
                <Button
                  variant="outline"
                  onClick={() => setEssayResultEditOpen(false)}
                  disabled={essayResultSaving}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={handleSaveEssayResult}
                  disabled={essayResultSaving}
                  className="gap-1.5"
                >
                  {essayResultSaving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  {t("common.save")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Dialog open={essayNoteOpen} onOpenChange={setEssayNoteOpen}>
            <DialogContent className="max-w-xl max-h-[92vh] flex flex-col">
              <DialogHeader>
                <DialogTitle>老师总评</DialogTitle>
                <DialogDescription className="truncate">
                  {detailItem?.name} · 总评会写在卷面底部（尾批位置），旁批保持不变
                </DialogDescription>
              </DialogHeader>
              <Textarea
                value={essayNoteDraft}
                onChange={(e) => setEssayNoteDraft(e.target.value)}
                className="min-h-[40vh] flex-1 resize-none text-sm leading-relaxed"
                placeholder="输入老师总评，留空则恢复 AI 尾批…"
              />
              <DialogFooter className="pt-3">
                <Button
                  variant="outline"
                  onClick={() => setEssayNoteOpen(false)}
                  disabled={essayNoteSaving}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={handleSaveEssayNote}
                  disabled={essayNoteSaving}
                  className="gap-1.5"
                >
                  {essayNoteSaving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  {t("common.save")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <AlertDialog
            open={previewPaperBoxDeleteOpen}
            onOpenChange={setPreviewPaperBoxDeleteOpen}
          >
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t("grading.paperBox.deletePageTitle")}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t("grading.paperBox.deletePageDesc", {
                    page: previewPaperBoxPageNo,
                    namePart: paperBoxCurrentSlot?.name
                      ? t("grading.paperBox.deletePageNamePart", {
                          name: paperBoxCurrentSlot.name,
                        })
                      : "",
                  })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={previewPaperBoxDeleting}>
                  {t("common.cancel")}
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={(e) => {
                    e.preventDefault();
                    void handleConfirmPaperBoxDelete();
                  }}
                  disabled={previewPaperBoxDeleting || !paperBoxCurrentSlot}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {previewPaperBoxDeleting
                    ? t("grading.status.deleting")
                    : t("grading.action.confirmDelete")}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <AlertDialog
            open={manualClearConfirmOpen}
            onOpenChange={setManualClearConfirmOpen}
          >
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t("grading.manual.clearConfirmTitle")}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t("grading.manual.clearConfirmDesc")}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={manualClearing}>
                  {t("common.cancel")}
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={(e) => {
                    e.preventDefault();
                    void handleClearManualScores();
                  }}
                  disabled={manualClearing}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {manualClearing
                    ? t("grading.status.clearing")
                    : t("grading.action.confirmClear")}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          {/* 删除确认 */}
          <Dialog
            open={renameFileDialogOpen}
            onOpenChange={(open) => {
              if (renameFileLoading) return;
              setRenameFileDialogOpen(open);
              if (!open) {
                setRenameFileTarget(null);
                setRenameFileNewName("");
              }
            }}
          >
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>{t("grading.print.renamePaperTitle")}</DialogTitle>
                <DialogDescription>
                  {t("grading.print.renamePaperDesc")}
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-2 py-2">
                {classStudents.length > 0 && (
                  <div className="grid gap-2">
                    <Label>{t("grading.start.matchStudent")}</Label>
                    <Select
                      value=""
                      onValueChange={(id) => {
                        const s = classStudents.find((x) => x.id === id);
                        if (s) setRenameFileNewName(s.name);
                      }}
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue
                          placeholder={t("grading.start.matchStudentPlaceholder")}
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {classStudents.map((s) => (
                          <SelectItem key={s.id} value={s.id}>
                            {s.name}
                            {s.student_number ? `（${s.student_number}）` : ""}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <Label htmlFor="rename-file-name">
                  {t("grading.start.newName")}
                </Label>
                <Input
                  id="rename-file-name"
                  value={renameFileNewName}
                  onChange={(e) => setRenameFileNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void handleRenameFile();
                  }}
                  autoFocus
                  disabled={renameFileLoading}
                />
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setRenameFileDialogOpen(false)}
                  disabled={renameFileLoading}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={() => void handleRenameFile()}
                  disabled={renameFileLoading || !renameFileNewName.trim()}
                >
                  {renameFileLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : null}
                  {t("common.confirm")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Dialog
            open={paperBoxSettingsOpen}
            onOpenChange={setPaperBoxSettingsOpen}
          >
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>{t("grading.paperBox.settingsTitle")}</DialogTitle>
                <DialogDescription>
                  {t("grading.paperBox.settingsDesc")}
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-2">
                  <Label htmlFor="paper-box-capacity">
                    {t("grading.paperBox.maxPerBox")}
                  </Label>
                  <div className="flex items-center gap-2">
                    <Input
                      id="paper-box-capacity"
                      type="number"
                      min={1}
                      max={MAX_PAPER_BOX_CAPACITY}
                      value={paperBoxCapacityDraft}
                      onChange={(e) => setPaperBoxCapacityDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") applyPaperBoxCapacity();
                      }}
                    />
                    <span className="shrink-0 text-sm text-muted-foreground">
                      {t("grading.unit.paper")}
                    </span>
                  </div>
                </div>
                <div className="rounded-lg border bg-muted/30 p-3 text-xs leading-relaxed text-muted-foreground">
                  {t("grading.paperBox.exampleHint")}
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setPaperBoxSettingsOpen(false)}
                >
                  {t("common.cancel")}
                </Button>
                <Button onClick={applyPaperBoxCapacity}>
                  {t("grading.paperBox.saveSettings")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <AlertDialog
            open={deleteConfirmOpen}
            onOpenChange={setDeleteConfirmOpen}
          >
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t("grading.action.confirmDelete")}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t("grading.print.deleteConfirmDesc", {
                    count: deletingIds.size,
                  })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={deleteExecuting}>
                  {t("common.cancel")}
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={(e) => {
                    e.preventDefault();
                    handleConfirmDelete();
                  }}
                  disabled={deleteExecuting}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {deleteExecuting
                    ? t("grading.status.deleting")
                    : t("grading.action.confirmDelete")}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <AlertDialog
            open={printConfirmOpen}
            onOpenChange={setPrintConfirmOpen}
          >
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t("grading.print.confirmAllTitle")}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t("grading.print.confirmAllDesc")}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={printBatchLoading}>
                  {t("common.cancel")}
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={(e) => {
                    e.preventDefault();
                    setPrintConfirmOpen(false);
                    void handleBatchPrint();
                  }}
                  disabled={printBatchLoading}
                >
                  {printBatchLoading
                    ? t("grading.status.printing")
                    : t("grading.action.confirmPrint")}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <Dialog open={printSettingsOpen} onOpenChange={setPrintSettingsOpen}>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>{t("grading.print.settingsTitle")}</DialogTitle>
                <DialogDescription>
                  {t("grading.print.settingsDesc")}
                </DialogDescription>
              </DialogHeader>
              <PrinterSettingsPanel
                printers={printers}
                printersLoading={printersLoading}
                selectedPrinter={selectedPrinter}
                onSelectedPrinterChange={setSelectedPrinter}
                printPaperSize={printPaperSize}
                onPrintPaperSizeChange={setPrintPaperSize}
                customPaperWidthMm={customPaperWidthMm}
                onCustomPaperWidthMmChange={setCustomPaperWidthMm}
                customPaperHeightMm={customPaperHeightMm}
                onCustomPaperHeightMmChange={setCustomPaperHeightMm}
                paperSourceId={paperSourceId}
                onPaperSourceIdChange={setPaperSourceId}
                printMode={printMode}
                onPrintModeChange={setPrintMode}
                selectTriggerClassName={cn(
                  "border-sky-300/80",
                  opGlassBtnClass,
                )}
              />
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setPrintSettingsOpen(false)}
                >
                  {t("grading.action.done")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Dialog open={essayRubricOpen} onOpenChange={setEssayRubricOpen}>
            <DialogContent className="max-w-7xl max-h-[95vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{t("grading.essay.rubricTitle")}</DialogTitle>
              </DialogHeader>
              <div className="flex flex-col gap-4">
                <div className="flex items-center justify-between">
                  <div className="flex flex-wrap gap-2 items-center flex-1">
                    {essayRubrics.map((r) => (
                      <Button
                        key={r.id}
                        variant={
                          activeRubricId === r.id ? "default" : "outline"
                        }
                        size="sm"
                        onClick={() => {
                          if (rubricDeleteMode) {
                            toggleRubricDeleteSelection(r.id);
                          } else {
                            setActiveRubricId(r.id);
                          }
                        }}
                        className={cn(
                          "relative",
                          rubricDeleteMode &&
                            deletingRubricIds.has(r.id) &&
                            "ring-2 ring-destructive",
                        )}
                      >
                        {r.name}
                        {rubricDeleteMode && (
                          <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-background border border-destructive">
                            {deletingRubricIds.has(r.id) && (
                              <div className="w-full h-full rounded-full bg-destructive" />
                            )}
                          </div>
                        )}
                      </Button>
                    ))}
                    {essayRubrics.length === 0 && (
                      <span className="text-sm text-muted-foreground">
                        {t("grading.essay.noRules")}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-4">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setNewRubricDialogOpen(true)}
                    >
                      {t("grading.action.newRule")}
                    </Button>
                    <Button
                      variant={rubricDeleteMode ? "destructive" : "outline"}
                      size="sm"
                      onClick={() => {
                        if (rubricDeleteMode) {
                          if (deletingRubricIds.size > 0) {
                            setDeleteRubricConfirmOpen(true);
                          } else {
                            setRubricDeleteMode(false);
                          }
                        } else {
                          setRubricDeleteMode(true);
                          setDeletingRubricIds(new Set());
                        }
                      }}
                    >
                      {rubricDeleteMode
                        ? t("grading.action.confirmDelete")
                        : t("grading.action.deleteRule")}
                      {rubricDeleteMode &&
                        deletingRubricIds.size > 0 &&
                        `(${deletingRubricIds.size})`}
                    </Button>
                    {rubricDeleteMode && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setRubricDeleteMode(false);
                          setDeletingRubricIds(new Set());
                        }}
                      >
                        {t("common.cancel")}
                      </Button>
                    )}
                  </div>
                </div>
                <div className="space-y-4 mt-2">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-8 items-stretch min-h-[650px]">
                    {/* 左1栏：作文题目要求 */}
                    <div className="flex flex-col space-y-2 h-full">
                      <Label className="text-sm font-bold text-primary">
                        {t("grading.essay.topicLabel")}
                      </Label>
                      <div className="flex flex-col gap-4 flex-1 p-3 border border-border rounded-md bg-muted/20">
                        {/* 选择题目的方式，只能选一种。如果已有图片，就不能填文本，反之亦然。 */}
                        {(() => {
                          const currentRubric = activeRubricId
                            ? essayRubrics.find((r) => r.id === activeRubricId)
                            : null;
                          const hasImage = !!currentRubric?.topic_image_base64;
                          const hasText = !!currentRubric?.topic_text;

                          return (
                            <>
                              {/* 文本输入区 */}
                              <div
                                className={cn(
                                  "flex flex-col flex-1 gap-2 transition-opacity",
                                  hasImage
                                    ? "opacity-30 pointer-events-none"
                                    : "",
                                )}
                              >
                                <Label className="text-xs text-muted-foreground">
                                  {t("grading.essay.topicTextMode")}
                                </Label>
                                <Textarea
                                  value={currentRubric?.topic_text || ""}
                                  onChange={(e) => {
                                    const newVal = e.target.value;
                                    setEssayRubrics((prev) =>
                                      prev.map((r) =>
                                        r.id === activeRubricId
                                          ? { ...r, topic_text: newVal }
                                          : r,
                                      ),
                                    );
                                  }}
                                  onBlur={async () => {
                                    if (activeRubricId) {
                                      try {
                                        const activeRubric = essayRubrics.find(
                                          (r) => r.id === activeRubricId,
                                        );
                                        await updateEssayRubric(
                                          activeRubricId,
                                          activeRubric?.content || "",
                                          undefined,
                                          activeRubric,
                                        );
                                        loadEssayRubrics();
                                      } catch (err) {}
                                    }
                                  }}
                                  placeholder={
                                    hasImage
                                      ? t("grading.essay.topicTextBlocked")
                                      : t("grading.essay.topicTextPlaceholder")
                                  }
                                  className={cn(
                                    "text-sm flex-1 resize-none focus-visible:ring-2 focus-visible:ring-primary/50",
                                    !activeRubricId && "opacity-50",
                                  )}
                                  disabled={!activeRubricId || hasImage}
                                />
                              </div>

                              {/* 分隔线 */}
                              <div className="relative py-2">
                                <div className="absolute inset-0 flex items-center">
                                  <span className="w-full border-t border-muted-foreground/20" />
                                </div>
                                <div className="relative flex justify-center text-xs uppercase">
                                  <span className="bg-background px-2 text-muted-foreground">
                                    OR
                                  </span>
                                </div>
                              </div>

                              {/* 图片上传区 */}
                              <div
                                className={cn(
                                  "flex flex-col gap-2 transition-opacity h-32",
                                  hasText
                                    ? "opacity-30 pointer-events-none"
                                    : "",
                                )}
                              >
                                <Label className="text-xs text-muted-foreground">
                                  {t("grading.essay.topicImageMode")}
                                </Label>
                                <div className="flex items-center gap-4 h-16 mt-2">
                                  <Label
                                    className={cn(
                                      "cursor-pointer flex items-center justify-center gap-2 px-4 py-2 h-full border border-primary/20 rounded-md bg-primary/5 text-primary hover:bg-primary/10 hover:scale-105 transition-all duration-300 flex-1",
                                      (!activeRubricId || hasText) &&
                                        "opacity-50 cursor-not-allowed hover:scale-100 hover:bg-primary/5",
                                    )}
                                  >
                                    <Camera className="w-5 h-5" />
                                    <span className="text-sm font-medium">
                                      {hasText
                                        ? t("grading.essay.topicImageBlocked")
                                        : t("grading.action.uploadTopicImage")}
                                    </span>
                                    <Input
                                      type="file"
                                      accept="image/*"
                                      disabled={!activeRubricId || hasText}
                                      onChange={(e) => {
                                        const file = e.target.files?.[0];
                                        if (
                                          file &&
                                          activeRubricId &&
                                          !hasText
                                        ) {
                                          const reader = new FileReader();
                                          reader.onload = async (ev) => {
                                            const base64 = ev.target
                                              ?.result as string;
                                            setEssayRubrics((prev) =>
                                              prev.map((r) =>
                                                r.id === activeRubricId
                                                  ? {
                                                      ...r,
                                                      topic_image_base64:
                                                        base64,
                                                    }
                                                  : r,
                                              ),
                                            );
                                            try {
                                              const activeRubric =
                                                essayRubrics.find(
                                                  (r) =>
                                                    r.id === activeRubricId,
                                                );
                                              await updateEssayRubric(
                                                activeRubricId,
                                                activeRubric?.content || "",
                                                undefined,
                                                {
                                                  ...activeRubric,
                                                  topic_image_base64: base64,
                                                },
                                              );
                                              loadEssayRubrics();
                                            } catch (err) {}
                                          };
                                          reader.readAsDataURL(file);
                                        }
                                      }}
                                      className="hidden"
                                    />
                                  </Label>
                                  {hasImage && (
                                    <div className="relative group shrink-0 h-full aspect-square">
                                      <img
                                        src={currentRubric?.topic_image_base64}
                                        alt={t("grading.essay.topicPreviewAlt")}
                                        className="h-full w-full object-cover rounded-md border shadow-sm"
                                      />
                                      <button
                                        type="button"
                                        className="absolute -top-2 -right-2 bg-destructive text-white rounded-full w-5 h-5 flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity shadow-md hover:scale-110"
                                        onClick={async () => {
                                          setEssayRubrics((prev) =>
                                            prev.map((r) =>
                                              r.id === activeRubricId
                                                ? {
                                                    ...r,
                                                    topic_image_base64: "",
                                                  }
                                                : r,
                                            ),
                                          );
                                          try {
                                            const activeRubric =
                                              essayRubrics.find(
                                                (r) => r.id === activeRubricId,
                                              );
                                            await updateEssayRubric(
                                              activeRubricId,
                                              activeRubric?.content || "",
                                              undefined,
                                              {
                                                ...activeRubric,
                                                topic_image_base64: "",
                                              },
                                            );
                                            loadEssayRubrics();
                                          } catch (err) {}
                                        }}
                                      >
                                        ✕
                                      </button>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </>
                          );
                        })()}
                      </div>
                    </div>

                    {/* 中间栏：评分 */}
                    <div className="flex flex-col space-y-2 h-full">
                      <Label className="text-sm font-bold text-primary">
                        {t("grading.essay.scoringPrompt")}
                      </Label>
                      <Textarea
                        value={
                          activeRubricId
                            ? essayRubrics.find((r) => r.id === activeRubricId)
                                ?.scoring_prompt || ""
                            : ""
                        }
                        onChange={(e) => {
                          const newVal = e.target.value;
                          setEssayRubrics((prev) =>
                            prev.map((r) =>
                              r.id === activeRubricId
                                ? { ...r, scoring_prompt: newVal }
                                : r,
                            ),
                          );
                        }}
                        onBlur={async () => {
                          if (activeRubricId) {
                            try {
                              const activeRubric = essayRubrics.find(
                                (r) => r.id === activeRubricId,
                              );
                              await updateEssayRubric(
                                activeRubricId,
                                activeRubric?.content || "",
                                undefined,
                                activeRubric,
                              );
                              loadEssayRubrics();
                            } catch (err) {}
                          }
                        }}
                        placeholder={t("grading.essay.scoringPlaceholder")}
                        className={cn(
                          "text-sm flex-1 resize-none focus-visible:ring-2 focus-visible:ring-primary/50",
                          !activeRubricId && "opacity-50",
                        )}
                        disabled={!activeRubricId}
                      />
                    </div>

                    {/* 右1栏：其他四个栏 */}
                    <div className="flex flex-col gap-4 h-full">
                      <div className="flex flex-col space-y-1 flex-1">
                        <Label className="text-xs font-bold text-primary">
                          {t("grading.essay.summaryLabel")}
                        </Label>
                        <p className="text-[11px] text-muted-foreground leading-snug">
                          {t("grading.essay.summaryHint")}
                        </p>
                        <Textarea
                          value={
                            activeRubricId
                              ? essayRubrics.find(
                                  (r) => r.id === activeRubricId,
                                )?.summary_prompt || ""
                              : ""
                          }
                          onChange={(e) => {
                            const newVal = e.target.value;
                            setEssayRubrics((prev) =>
                              prev.map((r) =>
                                r.id === activeRubricId
                                  ? { ...r, summary_prompt: newVal }
                                  : r,
                              ),
                            );
                          }}
                          onBlur={async () => {
                            if (activeRubricId) {
                              try {
                                const activeRubric = essayRubrics.find(
                                  (r) => r.id === activeRubricId,
                                );
                                await updateEssayRubric(
                                  activeRubricId,
                                  activeRubric?.content || "",
                                  undefined,
                                  activeRubric,
                                );
                                loadEssayRubrics();
                              } catch (err) {}
                            }
                          }}
                          placeholder={t("grading.essay.summaryPlaceholder")}
                          className={cn(
                            "text-xs flex-1 resize-none focus-visible:ring-2 focus-visible:ring-primary/50 min-h-[60px]",
                            !activeRubricId && "opacity-50",
                          )}
                          disabled={!activeRubricId}
                        />
                      </div>

                      <div className="flex flex-col space-y-1 flex-1">
                        <Label className="text-xs font-bold text-primary">
                          {t("grading.essay.commentLabel")}
                        </Label>
                        <Textarea
                          value={
                            activeRubricId
                              ? essayRubrics.find(
                                  (r) => r.id === activeRubricId,
                                )?.comment_prompt || ""
                              : ""
                          }
                          onChange={(e) => {
                            const newVal = e.target.value;
                            setEssayRubrics((prev) =>
                              prev.map((r) =>
                                r.id === activeRubricId
                                  ? { ...r, comment_prompt: newVal }
                                  : r,
                              ),
                            );
                          }}
                          onBlur={async () => {
                            if (activeRubricId) {
                              try {
                                const activeRubric = essayRubrics.find(
                                  (r) => r.id === activeRubricId,
                                );
                                await updateEssayRubric(
                                  activeRubricId,
                                  activeRubric?.content || "",
                                  undefined,
                                  activeRubric,
                                );
                                loadEssayRubrics();
                              } catch (err) {}
                            }
                          }}
                          placeholder={t("grading.essay.commentPlaceholder")}
                          className={cn(
                            "text-xs flex-1 resize-none focus-visible:ring-2 focus-visible:ring-primary/50 min-h-[60px]",
                            !activeRubricId && "opacity-50",
                          )}
                          disabled={!activeRubricId}
                        />
                      </div>

                      <div className="flex flex-col space-y-1 flex-1">
                        <Label className="text-xs font-bold text-primary">
                          {t("grading.essay.rewriteLabel")}
                        </Label>
                        <Textarea
                          value={
                            activeRubricId
                              ? essayRubrics.find(
                                  (r) => r.id === activeRubricId,
                                )?.rewrite_prompt || ""
                              : ""
                          }
                          onChange={(e) => {
                            const newVal = e.target.value;
                            setEssayRubrics((prev) =>
                              prev.map((r) =>
                                r.id === activeRubricId
                                  ? { ...r, rewrite_prompt: newVal }
                                  : r,
                              ),
                            );
                          }}
                          onBlur={async () => {
                            if (activeRubricId) {
                              try {
                                const activeRubric = essayRubrics.find(
                                  (r) => r.id === activeRubricId,
                                );
                                await updateEssayRubric(
                                  activeRubricId,
                                  activeRubric?.content || "",
                                  undefined,
                                  activeRubric,
                                );
                                loadEssayRubrics();
                              } catch (err) {}
                            }
                          }}
                          placeholder={t("grading.essay.rewritePlaceholder")}
                          className={cn(
                            "text-xs flex-1 resize-none focus-visible:ring-2 focus-visible:ring-primary/50 min-h-[60px]",
                            !activeRubricId && "opacity-50",
                          )}
                          disabled={!activeRubricId}
                        />
                      </div>

                      <div className="flex flex-col space-y-1 flex-1">
                        <Label className="text-xs font-bold text-primary">
                          {t("grading.essay.guidanceLabel")}
                        </Label>
                        <Textarea
                          value={
                            activeRubricId
                              ? essayRubrics.find(
                                  (r) => r.id === activeRubricId,
                                )?.guidance_prompt || ""
                              : ""
                          }
                          onChange={(e) => {
                            const newVal = e.target.value;
                            setEssayRubrics((prev) =>
                              prev.map((r) =>
                                r.id === activeRubricId
                                  ? { ...r, guidance_prompt: newVal }
                                  : r,
                              ),
                            );
                          }}
                          onBlur={async () => {
                            if (activeRubricId) {
                              try {
                                const activeRubric = essayRubrics.find(
                                  (r) => r.id === activeRubricId,
                                );
                                await updateEssayRubric(
                                  activeRubricId,
                                  activeRubric?.content || "",
                                  undefined,
                                  activeRubric,
                                );
                                loadEssayRubrics();
                              } catch (err) {}
                            }
                          }}
                          placeholder={t("grading.essay.guidancePlaceholder")}
                          className={cn(
                            "text-xs flex-1 resize-none focus-visible:ring-2 focus-visible:ring-primary/50 min-h-[60px]",
                            !activeRubricId && "opacity-50",
                          )}
                          disabled={!activeRubricId}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="rounded-md border border-border p-3 space-y-3">
                    <EssayDimensionConfigEditor
                      dimensions={currentDimensions}
                      onChange={handleDimensionsChange}
                      t={t}
                    />
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-[11px] text-muted-foreground leading-snug">
                        {t("grading.dimension.hint")}
                      </p>
                      <Button
                        size="sm"
                        onClick={() => void handleSaveDimensions()}
                        disabled={!activeRubricId || dimensionSaving}
                        className="gap-1.5 shrink-0"
                      >
                        {dimensionSaving && (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        )}
                        <Save className="h-4 w-4" />
                        {t("grading.dimension.save")}
                      </Button>
                    </div>
                  </div>

                  {!activeRubricId && (
                    <div className="flex items-center justify-center p-8 border-2 border-dashed rounded-lg border-muted">
                      <p className="text-sm text-muted-foreground">
                        {t("grading.essay.selectRuleHint")}
                      </p>
                    </div>
                  )}
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="default"
                  onClick={() => setEssayRubricOpen(false)}
                >
                  {t("grading.action.close")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* 新建批改规则弹窗 */}
          <Dialog
            open={newRubricDialogOpen}
            onOpenChange={setNewRubricDialogOpen}
          >
            <DialogContent className="sm:max-w-sm">
              <DialogHeader>
                <DialogTitle>{t("grading.essay.newRuleTitle")}</DialogTitle>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="rubric-name">
                    {t("grading.essay.ruleName")}
                  </Label>
                  <Input
                    id="rubric-name"
                    placeholder={t("grading.essay.ruleNamePlaceholder")}
                    value={newRubricName}
                    onChange={(e) => setNewRubricName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleCreateRubric()}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setNewRubricDialogOpen(false)}
                  disabled={newRubricLoading}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={handleCreateRubric}
                  disabled={newRubricLoading || !newRubricName.trim()}
                >
                  {newRubricLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : null}
                  {t("common.confirm")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          {/* 删除规则确认弹窗 */}
          <AlertDialog
            open={deleteRubricConfirmOpen}
            onOpenChange={setDeleteRubricConfirmOpen}
          >
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {t("grading.essay.confirmDeleteRulesTitle")}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {t("grading.essay.confirmDeleteRulesDesc", {
                    count: deletingRubricIds.size,
                  })}
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={deleteRubricExecuting}>
                  {t("common.cancel")}
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={(e) => {
                    e.preventDefault();
                    handleConfirmDeleteRubrics();
                  }}
                  disabled={deleteRubricExecuting}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {deleteRubricExecuting
                    ? t("grading.status.deleting")
                    : t("grading.action.confirmDelete")}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <ReferenceLayoutCorrectionDialog
            open={referenceLayoutOpen}
            pages={referenceLayoutPages}
            loading={referenceLayoutSaving}
            preparing={referenceLayoutPreparing}
            initialPageNo={boxEditTargetPage || undefined}
            onOpenChange={(open) => {
              if (!referenceLayoutSaving && !referenceLayoutPreparing) {
                setReferenceLayoutOpen(open);
                if (!open) {
                  // 关掉不确认=放弃改框：清掉「回识别列表」标记与落点页
                  boxEditReturnRef.current = false;
                  setBoxEditTargetPage(0);
                }
              }
            }}
            onConfirm={handleConfirmReferenceLayout}
            onReprepare={handlePrepareReferenceLayout}
          />

          <LayoutTemplateDialog
            open={layoutTemplateOpen}
            mode={layoutTemplateMode}
            saving={layoutTemplateSaving}
            onOpenChange={(open) => {
              if (!layoutTemplateSaving) setLayoutTemplateOpen(open);
            }}
            onSave={handleSaveLayoutTemplate}
            onApply={handleApplyLayoutTemplate}
          />

          <StandardAnswerTableDialog
            open={answerTableOpen}
            pages={answerTablePages}
            loading={answerTableLoading}
            saving={answerTableSaving}
            onOpenChange={(open) => {
              if (!answerTableSaving && !answerTableLoading) setAnswerTableOpen(open);
            }}
            onSave={handleSaveAnswerTable}
            onRebuild={handleRebuildAnswerTable}
            onUploadAnswerSheets={handleUploadAnswerSheets}
            onEditBoxes={gradingEngine === "aliyun" ? handleEditAnswerBoxes : undefined}
          />

          <AnswerSheetDialog
            open={answerSheetOpen}
            rows={answerSheetRows}
            loading={answerSheetLoading}
            saving={answerSheetSaving}
            error={answerSheetError}
            onOpenChange={(open) => {
              if (!answerSheetSaving && !answerSheetLoading)
                setAnswerSheetOpen(open);
            }}
            onRescan={handleRescanAnswerSheet}
            onConfirm={handleConfirmAnswerSheet}
          />

          <ReferenceLayoutCorrectionDialog
            open={manualLayoutOpen}
            pages={manualLayoutPages}
            loading={manualLayoutSaving}
            preparing={manualLayoutPreparing}
            variant="manual"
            scoringEnabled
            onOpenChange={(open) => {
              if (!manualLayoutSaving && !manualLayoutPreparing)
                setManualLayoutOpen(open);
            }}
            onConfirm={handleConfirmManualLayout}
            onReprepare={handlePrepareManualLayout}
          />

          <ManualPaperGradingDialog
            open={Boolean(manualGradingItem)}
            filename={manualGradingItem?.name || ""}
            imageUrl={
              manualGradingSource?.url ||
              manualGradingItem?.image_original ||
              ""
            }
            result={manualGradingItem?.result || ""}
            answerKey={answerKeyLoaded}
            initialQuestionNotes={manualGradingItem?.question_notes}
            initialPaperNote={manualGradingItem?.paper_note}
            initialWrongAnnotations={manualGradingItem?.wrong_annotations}
            initialDeductionItems={manualGradingItem?.deduction_items}
            regenerateWrongAnnotation={handleManualWrongAnnoRegenerate}
            saving={manualPaperSaving}
            printing={manualPaperPrinting}
            otherPagesScore={manualOtherPagesScore}
            hasPrev={manualHasPrev}
            hasNext={manualHasNext}
            onOpenChange={(open) => {
              if (!open && !manualPaperSaving && !manualPaperPrinting)
                setManualGradingItem(null);
            }}
            onSave={handleSaveManualPaper}
            onAutoSave={handleAutoSaveManualPaper}
            onPrintPreview={handleManualPrintPreview}
            onPrint={handlePrintManualPaper}
          />

          <Dialog
            open={answerKeyDialogOpen}
            onOpenChange={setAnswerKeyDialogOpen}
          >
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>{t("grading.answerKey.title")}</DialogTitle>
                <DialogDescription>{t("grading.answerKey.hint")}</DialogDescription>
              </DialogHeader>
              <div className="flex flex-col gap-3 py-2">
                <Textarea
                  value={answerKeyText}
                  onChange={(e) => setAnswerKeyText(e.target.value)}
                  placeholder={t("grading.answerKey.placeholder")}
                  rows={6}
                  className="font-mono text-sm"
                />
                <div className="flex items-center gap-3">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="gap-2"
                    onClick={() => answerKeyImageInputRef.current?.click()}
                    disabled={answerKeySaving}
                  >
                    <ImagePlus className="w-4 h-4" />
                    {t("grading.answerKey.uploadImage")}
                  </Button>
                  <input
                    ref={answerKeyImageInputRef}
                    type="file"
                    accept="image/*,.pdf,.doc,.docx"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0] || null;
                      setAnswerKeyImageFile(f);
                      setAnswerKeyImageName(f?.name || "");
                    }}
                  />
                  <span className="truncate text-sm text-muted-foreground">
                    {answerKeyImageName || t("grading.answerKey.orUseImage")}
                  </span>
                </div>
                {answerKeyLoaded && Object.keys(answerKeyLoaded).length > 0 && (
                  <p className="text-sm font-medium text-emerald-700">
                    {t("grading.answerKey.parsed", {
                      count: Object.keys(answerKeyLoaded).length,
                    })}
                  </p>
                )}
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setAnswerKeyDialogOpen(false)}
                  disabled={answerKeySaving}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={() => void handleSaveAnswerKey()}
                  disabled={answerKeySaving}
                >
                  {answerKeySaving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : null}
                  {t("grading.answerKey.save")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Dialog open={originalPaperOpen} onOpenChange={setOriginalPaperOpen}>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>{t("grading.originalPaper.title")}</DialogTitle>
                <DialogDescription>
                  {t("grading.originalPaper.hint")}
                </DialogDescription>
              </DialogHeader>
              <div className="flex flex-col gap-3 py-2">
                <div className="flex items-center gap-3">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="gap-2"
                    onClick={() => originalPaperInputRef.current?.click()}
                    disabled={originalPaperUploading}
                  >
                    {originalPaperUploading ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <ImagePlus className="h-4 w-4" />
                    )}
                    {t("grading.originalPaper.upload")}
                  </Button>
                  <input
                    ref={originalPaperInputRef}
                    type="file"
                    accept="image/*,.pdf,.doc,.docx"
                    className="hidden"
                    disabled={originalPaperUploading}
                    onChange={(e) => void handleUploadOriginalPaper(e)}
                  />
                  <span className="truncate text-sm text-muted-foreground">
                    {originalPaperName || t("grading.answerKey.orUseImage")}
                  </span>
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setOriginalPaperOpen(false)}
                  disabled={originalPaperUploading || originalPaperRecognizing}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  onClick={() => void handleRecognizePaperScores()}
                  disabled={originalPaperUploading || originalPaperRecognizing}
                  className="gap-1.5"
                >
                  {originalPaperRecognizing ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}
                  {originalPaperRecognizing
                    ? t("grading.originalPaper.recognizing")
                    : t("grading.originalPaper.recognize")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <PaperScoreConfirmDialog
            open={originalPaperScoreOpen}
            onOpenChange={setOriginalPaperScoreOpen}
            items={originalPaperScoreItems}
            loading={originalPaperApplying}
            onConfirm={(scores) => void handleApplyPaperScores(scores)}
          />

          <PrivacyNoticeDialog
            open={noticePending !== null}
            onOpenChange={(open) => !open && setNoticePending(null)}
            onConfirm={() => {
              noticePending?.();
              setNoticePending(null);
            }}
            context="自动批改与分析"
          />

          <Dialog
            open={classReviewPushOpen}
            onOpenChange={setClassReviewPushOpen}
          >
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>
                  {classReviewPushState.status === "pushing"
                    ? t("grading.classReviewPush.pushing")
                    : classReviewPushState.status === "success"
                      ? t("grading.classReviewPush.success")
                      : t("grading.classReviewPush.failed")}
                </DialogTitle>
                <DialogDescription>
                  {classReviewPushState.status === "pushing"
                    ? t("grading.classReviewPush.pushingDesc")
                    : classReviewPushState.status === "success"
                      ? t("grading.classReviewPush.successDesc", {
                          subject:
                            classReviewPushState.subject || selectedSubject,
                        })
                      : classReviewPushState.message ||
                        t("grading.classReviewPush.failed")}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                {classReviewPushState.status === "error" && (
                  <Button
                    variant="outline"
                    onClick={() => void pushToClassReview()}
                    disabled={classReviewPushingRef.current}
                  >
                    {t("grading.classReviewPush.retry")}
                  </Button>
                )}
                {classReviewPushState.status === "success" && (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setClassReviewPushOpen(false);
                      navigate("/nav/ai-review");
                    }}
                  >
                    {t("grading.classReviewPush.goReview")}
                  </Button>
                )}
                <Button
                  onClick={() => setClassReviewPushOpen(false)}
                  disabled={classReviewPushState.status === "pushing"}
                >
                  {t("grading.classReviewPush.ok")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </GradingErrorBoundary>
    );
  }

  return (
    <div className={cn("space-y-6 animate-in fade-in duration-300")}>
      <div>
        <h1 className="text-xl font-bold text-foreground">
          {t("grading.start.title")}
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          {t("grading.start.subtitle")}
        </p>
      </div>

      <Card className="overflow-hidden border-border/50 shadow-sm">
        <CardHeader className="pb-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <FolderOpen className="w-5 h-5 text-primary" />
                {t("grading.start.folders")}
              </CardTitle>
              <CardDescription className="mt-1" />
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button
                onClick={() => {
                  setNewFolderSubject(selectedSubject);
                  setCreateDialogOpen(true);
                }}
                className="gap-2"
                disabled={!selectedClass}
              >
                <FolderOpen className="w-4 h-4" />
                {t("grading.start.createFolder")}
              </Button>
              <Button
                variant="outline"
                className="gap-2"
                onClick={() => testPrintInputRef.current?.click()}
                disabled={testPrintLoading}
              >
                <Printer className="w-4 h-4" />
                {t("grading.testPrint.button")}
              </Button>
              <input
                ref={testPrintInputRef}
                type="file"
                accept=".jpg,.jpeg,.png,.webp,.pdf,.doc,.docx,image/*"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void handleTestPrint(f);
                }}
              />
              <Button
                variant={folderDeleteMode ? "default" : "outline"}
                size="default"
                className="gap-2"
                disabled={!selectedClass}
                onClick={() => {
                  if (folderDeleteMode) {
                    if (deletingFolderIds.size === 0) {
                      toast.error(t("grading.start.selectFoldersToDelete"));
                      return;
                    }
                    setDeleteFolderDialogOpen(true);
                  } else {
                    setFolderDeleteMode(true);
                    setDeletingFolderIds(new Set());
                  }
                }}
              >
                <Trash2 className="w-4 h-4" />
                {folderDeleteMode
                  ? t("grading.start.confirmDeleteFolder")
                  : t("grading.start.deleteFolder")}
                {folderDeleteMode &&
                  deletingFolderIds.size > 0 &&
                  `（${deletingFolderIds.size}）`}
              </Button>
              {folderDeleteMode && (
                <Button
                  variant="ghost"
                  size="default"
                  onClick={() => {
                    setFolderDeleteMode(false);
                    setDeletingFolderIds(new Set());
                  }}
                >
                  {t("common.cancel")}
                </Button>
              )}
              <Button
                variant="outline"
                size="default"
                className="gap-2"
                disabled={!selectedClass || dataExporting || dataImporting}
                onClick={handleExportClassData}
              >
                {dataExporting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Download className="w-4 h-4" />
                )}
                {dataExporting
                  ? t("grading.dataExport.exporting")
                  : t("grading.dataExport.export")}
              </Button>
              <Button
                variant="outline"
                size="default"
                className="gap-2"
                disabled={!selectedClass || dataExporting || dataImporting}
                onClick={() => importInputRef.current?.click()}
              >
                {dataImporting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4" />
                )}
                {dataImporting
                  ? t("grading.dataExport.importing")
                  : t("grading.dataExport.import")}
              </Button>
              <input
                ref={importInputRef}
                type="file"
                accept=".zip,application/zip,application/x-zip-compressed"
                className="hidden"
                disabled={!selectedClass || dataImporting}
                onChange={handleImportFileChange}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {folders.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center rounded-lg border border-dashed bg-muted/20">
              <FolderOpen className="w-12 h-12 text-muted-foreground/50 mb-3" />
              <p className="text-sm text-muted-foreground mb-4">
                {selectedClass
                  ? t("grading.start.noFolders")
                  : t("grading.start.selectClassFirst")}
              </p>
              <Button
                onClick={() => {
                  setNewFolderSubject(selectedSubject);
                  setCreateDialogOpen(true);
                }}
                variant="outline"
                className="gap-2"
                disabled={!selectedClass}
              >
                {t("grading.start.createFolder")}
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {folders.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => {
                    if (folderDeleteMode) toggleFolderDeleteSelection(name);
                    else handleSelectFolder(name);
                  }}
                  className={cn(
                    "flex flex-col items-center gap-3 p-4 rounded-xl border transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary/20 animate-in fade-in zoom-in-95 relative group",
                    folderDeleteMode
                      ? "border-border/50 bg-card hover:bg-accent/50 cursor-pointer"
                      : "border-border/50 bg-card hover:bg-accent/50 hover:border-primary/30 hover:shadow-md",
                    folderDeleteMode &&
                      deletingFolderIds.has(name) &&
                      "ring-2 ring-primary/50 border-primary/50",
                  )}
                >
                  {folderDeleteMode && (
                    <div
                      className="absolute left-2 top-2 z-10"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Checkbox
                        checked={deletingFolderIds.has(name)}
                        onCheckedChange={() =>
                          toggleFolderDeleteSelection(name)
                        }
                      />
                    </div>
                  )}
                  {!folderDeleteMode && (
                    <div
                      className="absolute right-2 top-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenameFolderTarget(name);
                        setRenameFolderNewName(displayFolderName(name));
                        setRenameFolderHomeworkType(
                          folderMeta[name]?.homework_type || HOMEWORK_TYPES[0],
                        );
                        setRenameFolderDialogOpen(true);
                      }}
                    >
                      <Button
                        variant="ghost"
                        size="icon"
                        className="w-6 h-6 rounded-full hover:bg-primary/10"
                      >
                        <Edit2 className="w-3.5 h-3.5 text-muted-foreground hover:text-primary" />
                      </Button>
                    </div>
                  )}
                  <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                    <FolderOpen className="w-8 h-8 text-primary" />
                  </div>
                  <span
                    className="text-sm font-medium text-foreground truncate w-full text-center"
                    title={displayFolderName(name)}
                  >
                    {displayFolderName(name)}
                  </span>
                  {(() => {
                    const m = folderMeta[name];
                    const tags = [
                      m?.subject,
                      m?.grade,
                      m?.homework_type,
                    ].filter(Boolean) as string[];
                    return tags.length ? (
                      <span className="flex flex-wrap items-center justify-center gap-1">
                        {tags.map((tag) => (
                          <span
                            key={tag}
                            className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                          >
                            {tag}
                          </span>
                        ))}
                      </span>
                    ) : null;
                  })()}
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={testPrintOpen} onOpenChange={setTestPrintOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t("grading.testPrint.title")}</DialogTitle>
            <DialogDescription>
              {t("grading.testPrint.desc")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {testPrintPhase === "grading" && (
              <div className="flex items-center gap-3 text-sm">
                <Loader2 className="w-5 h-5 animate-spin text-primary" />
                <span className="font-medium">
                  {t("grading.status.grading")}
                </span>
              </div>
            )}
            {testPrintPhase === "printing" && (
              <div className="flex items-center gap-3 text-sm">
                <Loader2 className="w-5 h-5 animate-spin text-primary" />
                <span className="font-medium">
                  {t("grading.status.printing")}
                </span>
              </div>
            )}
            {testPrintPhase === "done" && (
              <div className="space-y-3">
                <div className="flex items-center gap-3 text-sm">
                  <Check className="w-5 h-5 text-emerald-500" />
                  <span className="font-medium">
                    {t("grading.testPrint.doneTitle")}
                  </span>
                </div>
                {testPrintResult && (
                  <ScrollArea className="max-h-72 rounded-md border bg-muted/30 p-3">
                    <pre className="whitespace-pre-wrap text-sm text-muted-foreground">
                      {testPrintResult}
                    </pre>
                  </ScrollArea>
                )}
              </div>
            )}
            {testPrintPhase === "error" && (
              <Alert variant="destructive">
                <AlertCircle className="w-4 h-4" />
                <AlertTitle>{t("grading.testPrint.errorTitle")}</AlertTitle>
                <AlertDescription>{testPrintError}</AlertDescription>
              </Alert>
            )}
          </div>
          <DialogFooter>
            {(testPrintPhase === "done" || testPrintPhase === "error") && (
              <Button
                variant="outline"
                onClick={() => testPrintInputRef.current?.click()}
              >
                {t("grading.testPrint.retry")}
              </Button>
            )}
            <Button
              variant={testPrintPhase === "done" ? "default" : "outline"}
              onClick={() => setTestPrintOpen(false)}
              disabled={
                testPrintPhase === "grading" || testPrintPhase === "printing"
              }
            >
              {t("common.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("grading.start.newFolderTitle")}</DialogTitle>
            <DialogDescription>
              {t("grading.start.newFolderDesc")}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="folder-name">
                {t("grading.start.folderName")}
              </Label>
              <Input
                id="folder-name"
                placeholder={t("grading.start.folderNamePlaceholder")}
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreateFolder()}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="folder-subject">
                {t("grading.start.folderSubject")}
              </Label>
              <Select
                value={newFolderSubject}
                onValueChange={setNewFolderSubject}
              >
                <SelectTrigger id="folder-subject" className="w-full">
                  <SelectValue
                    placeholder={t("grading.start.folderSubjectPlaceholder")}
                  />
                </SelectTrigger>
                <SelectContent>
                  {getSubjectsBySchoolLevel(schoolLevel).map((s) => (
                    <SelectItem key={s.id} value={s.name}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="folder-homework-type">
                {t("grading.start.homeworkType")}
              </Label>
              <Select
                value={newFolderHomeworkType}
                onValueChange={setNewFolderHomeworkType}
              >
                <SelectTrigger id="folder-homework-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HOMEWORK_TYPES.map((ht) => (
                    <SelectItem key={ht} value={ht}>
                      {ht}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCreateDialogOpen(false)}
              disabled={createLoading}
            >
              {t("common.cancel")}
            </Button>
            <Button
              onClick={handleCreateFolder}
              disabled={createLoading || !newFolderName.trim()}
            >
              {createLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : null}
              {t("common.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={renameFolderDialogOpen}
        onOpenChange={setRenameFolderDialogOpen}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("grading.start.renameFolderTitle")}</DialogTitle>
            <DialogDescription>
              {t("grading.start.renameFolderDesc")}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="rename-folder-name">
                {t("grading.start.newName")}
              </Label>
              <Input
                id="rename-folder-name"
                placeholder={t("grading.start.newNamePlaceholder")}
                value={renameFolderNewName}
                onChange={(e) => setRenameFolderNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleRenameFolder()}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="rename-folder-homework-type">
                {t("grading.start.homeworkType")}
              </Label>
              <Select
                value={renameFolderHomeworkType}
                onValueChange={setRenameFolderHomeworkType}
              >
                <SelectTrigger id="rename-folder-homework-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {HOMEWORK_TYPES.map((ht) => (
                    <SelectItem key={ht} value={ht}>
                      {ht}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRenameFolderDialogOpen(false)}
              disabled={renameFolderLoading}
            >
              {t("common.cancel")}
            </Button>
            <Button
              onClick={handleRenameFolder}
              disabled={renameFolderLoading || !renameFolderNewName.trim()}
            >
              {renameFolderLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : null}
              {t("common.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteFolderDialogOpen}
        onOpenChange={setDeleteFolderDialogOpen}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {t("grading.start.confirmDeleteFolderTitle")}
            </DialogTitle>
            <DialogDescription>
              {t("grading.start.confirmDeleteFolderDesc", {
                count: deletingFolderIds.size,
              })}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="delete-folder-password">
                {t("grading.start.loginPassword")}
              </Label>
              <Input
                id="delete-folder-password"
                type="password"
                placeholder={t("grading.start.loginPasswordPlaceholder")}
                value={deleteFolderPassword}
                onChange={(e) => setDeleteFolderPassword(e.target.value)}
                onKeyDown={(e) =>
                  e.key === "Enter" && handleConfirmDeleteFolders()
                }
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDeleteFolderDialogOpen(false);
                setDeleteFolderPassword("");
              }}
              disabled={deleteFolderExecuting}
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmDeleteFolders}
              disabled={deleteFolderExecuting || !deleteFolderPassword.trim()}
            >
              {deleteFolderExecuting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : null}
              {t("grading.action.confirmDelete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={importResultOpen} onOpenChange={setImportResultOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {t("grading.dataExport.importResultTitle")}
            </DialogTitle>
            <DialogDescription>
              {t("grading.dataExport.importSummary", {
                imported: importResult?.imported?.length ?? 0,
                skipped: importResult?.skipped?.length ?? 0,
                failed: importResult?.errors?.length ?? 0,
              })}
            </DialogDescription>
          </DialogHeader>
          <div className="grid max-h-[320px] gap-3 overflow-y-auto py-2">
            {importResult?.skipped?.length ? (
              <div>
                <p className="mb-1 text-sm font-medium">
                  {t("grading.dataExport.skippedList")}
                </p>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {importResult.skipped.map((item, i) => (
                    <li
                      key={i}
                      className="flex items-start justify-between gap-2"
                    >
                      <span className="truncate">{item.exam_name}</span>
                      <span className="shrink-0">{item.reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {importResult?.errors?.length ? (
              <div>
                <p className="mb-1 text-sm font-medium text-destructive">
                  {t("grading.dataExport.errorsList")}
                </p>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {importResult.errors.map((item, i) => (
                    <li
                      key={i}
                      className="flex items-start justify-between gap-2"
                    >
                      <span className="truncate">{item.name}</span>
                      <span className="shrink-0">{item.message}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {!importResult?.skipped?.length && !importResult?.errors?.length ? (
              <p className="text-sm text-muted-foreground">
                {t("grading.dataExport.noSkippedOrErrors")}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setImportResultOpen(false)}
            >
              {t("common.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
