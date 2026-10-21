import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { API_PREFIX } from "@/config/api";
import { translateSubjectName } from "@/i18n";
import {
  BookOpen,
  Check,
  Download,
  ExternalLink,
  FileInput,
  Loader2,
  Minus,
  Plus,
  RefreshCcw,
  Search,
  Sparkles,
  Stethoscope,
  Target,
  TrendingDown,
  TrendingUp,
  User,
  X,
} from "lucide-react";
import {
  getRecommendationContent,
  getTargetedReport,
  listTargetedStudents,
  listTargetedSubjects,
  reevaluateDiagnosis,
  saveTargetedRecommendations,
  type TargetedReport,
  type TargetedStudentItem,
} from "@/services/api";
import { TargetedImportExamDialog } from "./targeted-improve/TargetedImportExamDialog";
import { TargetedTaskList } from "./targeted-improve/TargetedTaskList";
import { PrivacyNoticeDialog } from "@/components/common/PrivacyNoticeDialog";
import { AIGeneratedBadge } from "@/components/common/AIGeneratedBadge";
import { toast } from "sonner";

interface TargetedImprovePageProps {
  selectedSubject: string;
  selectedClass: string;
  onNavChange: (id: string) => void;
  initialStudentName?: string;
  onNavigateToStudent?: (name: string) => void;
}

const FALLBACK_SUBJECTS = [
  "语文",
  "数学",
  "英语",
  "科学",
  "物理",
  "化学",
  "生物",
  "历史",
  "地理",
  "政治",
];
const SUBJECT_STORAGE_PREFIX = "targeted-improve-subject:";

type Translate = (
  key: string,
  params?: Record<string, string | number>,
  fallback?: string,
) => string;

function formatScore(score: number | null | undefined, t: Translate) {
  if (score === null || score === undefined || Number.isNaN(Number(score)))
    return t("targeted.noData");
  const s = Number(score);
  return Number.isInteger(s) ? String(s) : s.toFixed(1);
}

function trendLabel(value?: number) {
  const n = Number(value || 0);
  if (n > 0)
    return (
      <span className="inline-flex items-center text-emerald-600">
        <TrendingUp className="mr-0.5 h-3 w-3" />+{n}
      </span>
    );
  if (n < 0)
    return (
      <span className="inline-flex items-center text-destructive">
        <TrendingDown className="mr-0.5 h-3 w-3" />
        {n}
      </span>
    );
  return (
    <span className="inline-flex items-center text-muted-foreground">
      <Minus className="mr-0.5 h-3 w-3" />0
    </span>
  );
}

function asArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((x) => String(x ?? "").trim()).filter(Boolean);
}

type Tone = "neutral" | "blue" | "amber" | "rose" | "emerald" | "violet";

const toneClasses: Record<Tone, string> = {
  neutral: "border-border/60 bg-muted/20 text-foreground",
  blue: "border-sky-200 bg-sky-50 text-sky-950",
  amber: "border-amber-200 bg-amber-50 text-amber-950",
  rose: "border-rose-200 bg-rose-50 text-rose-950",
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-950",
  violet: "border-violet-200 bg-violet-50 text-violet-950",
};

function TextList({
  items,
  empty,
  tone = "neutral",
}: {
  items?: unknown;
  empty?: string;
  tone?: Tone;
}) {
  const { t } = useLocale();
  const emptyText = empty ?? t("targeted.emptyData");
  const list = asArray(items);
  if (list.length === 0)
    return <p className="text-[15px] text-muted-foreground">{emptyText}</p>;
  return (
    <div className="space-y-2">
      {list.map((item, index) => (
        <div
          key={`${item}-${index}`}
          className={cn(
            "rounded-md border px-3.5 py-2.5 text-[15px] leading-relaxed",
            toneClasses[tone],
          )}
        >
          {item}
        </div>
      ))}
    </div>
  );
}

function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderReportList(
  items: unknown,
  t: (key: string) => string,
  empty?: string,
) {
  const list = asArray(items);
  const emptyText = empty ?? t("targeted.emptyData");
  if (list.length === 0) return `<p class="muted">${escapeHtml(emptyText)}</p>`;
  return `<ol>${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>`;
}

function longDiagnosisSummary(
  report: TargetedReport | null | undefined,
  t: Translate,
) {
  const diagnosis = report?.diagnosis || {};
  const base = String(diagnosis.summary || report?.diagnosis_text || "").trim();
  const strengths = asArray(diagnosis.strengths).slice(0, 2).join("、");
  const weak = asArray(diagnosis.weak_points).slice(0, 2).join("、");
  const root = asArray(diagnosis.root_causes).slice(0, 2).join("、");
  const evidenceCount = asArray(diagnosis.evidence).length;
  if (!base) return t("targeted.summary.empty");
  const extras = [];
  if (strengths)
    extras.push(t("targeted.summary.strengths", { value: strengths }));
  if (weak) extras.push(t("targeted.summary.weaknesses", { value: weak }));
  if (root) extras.push(t("targeted.summary.causes", { value: root }));
  if (evidenceCount > 0)
    extras.push(t("targeted.summary.evidence", { count: evidenceCount }));
  return extras.length
    ? t("targeted.summary.combined", {
        base,
        extras: extras.join(t("targeted.summary.separator")),
      })
    : base;
}

function createReportElement(params: {
  subject: string;
  student?: TargetedStudentItem | null;
  report?: TargetedReport | null;
  t: Translate;
  locale: string;
}) {
  const { subject, student, report, t, locale } = params;
  const diagnosis = report?.diagnosis || {};
  const plan = report?.plan || {};
  const source = report?.source_summary || {};
  const phases = Array.isArray(plan.phases) ? plan.phases : [];
  const examNames = report?.exam_names || [];
  const generatedAt = report?.generated_at
    ? new Date(report.generated_at).toLocaleString(
        locale === "en" ? "en-US" : "zh-CN",
      )
    : new Date().toLocaleString(locale === "en" ? "en-US" : "zh-CN");
  const reportEl = document.createElement("div");
  reportEl.style.position = "fixed";
  reportEl.style.left = "-10000px";
  reportEl.style.top = "0";
  reportEl.style.width = "794px";
  reportEl.style.background = "#fff";
  const metaHtml = `
    <div class="meta">
      <div><b>${escapeHtml(t("targeted.report.student"))}</b>${escapeHtml(student?.name || report?.student_name || "-")}</div>
      <div><b>${escapeHtml(t("targeted.report.studentNumber"))}</b>${escapeHtml(student?.student_number || report?.student_number || "-")}</div>
      <div><b>${escapeHtml(t("targeted.report.subject"))}</b>${escapeHtml(subject)}</div>
      <div><b>${escapeHtml(t("targeted.report.generatedAt"))}</b>${escapeHtml(generatedAt)}</div>
      <div><b>${escapeHtml(t("targeted.report.importedExams"))}</b>${escapeHtml(t("targeted.report.examCount", { count: source.exam_count ?? examNames.length ?? 0 }))}</div>
      <div><b>${escapeHtml(t("targeted.report.wrongCount"))}</b>${escapeHtml(String(source.wrong_question_count ?? 0))}</div>
    </div>
  `;
  reportEl.innerHTML = `
    <style>
      .targeted-report-page { box-sizing: border-box; width: 794px; min-height: 1123px; padding: 38px 46px; color: #172033; font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif; background: #fff; }
      .targeted-report-page + .targeted-report-page { margin-top: 24px; }
      .targeted-report-page * { box-sizing: border-box; }
      .targeted-report .top { border-bottom: 3px solid #2563eb; padding-bottom: 16px; margin-bottom: 18px; }
      .targeted-report h1 { margin: 0; font-size: 28px; line-height: 1.25; letter-spacing: 0; color: #10203f; }
      .targeted-report .subtitle { margin-top: 8px; color: #64748b; font-size: 13px; }
      .targeted-report .meta { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 16px; margin: 16px 0 18px; padding: 13px; border: 1px solid #dbeafe; background: #f8fbff; border-radius: 8px; }
      .targeted-report .meta div { font-size: 13px; color: #334155; }
      .targeted-report .meta b { color: #0f172a; margin-right: 6px; }
      .targeted-report section { margin-top: 15px; break-inside: avoid; page-break-inside: avoid; }
      .targeted-report h2 { margin: 0 0 9px; font-size: 18px; line-height: 1.3; color: #0f172a; border-left: 5px solid #2563eb; padding-left: 10px; }
      .targeted-report .summary { border: 1px solid #bfdbfe; background: #eff6ff; border-radius: 8px; padding: 12px 14px; font-size: 14px; line-height: 1.75; color: #1e3a8a; }
      .targeted-report .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
      .targeted-report .box { border-radius: 8px; padding: 10px 12px; border: 1px solid #e2e8f0; background: #fff; }
      .targeted-report .box h3 { margin: 0 0 8px; font-size: 15px; color: #111827; }
      .targeted-report .amber { background: #fffbeb; border-color: #fde68a; }
      .targeted-report .rose { background: #fff1f2; border-color: #fecdd3; }
      .targeted-report .emerald { background: #ecfdf5; border-color: #a7f3d0; }
      .targeted-report .violet { background: #f5f3ff; border-color: #ddd6fe; }
      .targeted-report ol { margin: 0; padding-left: 20px; }
      .targeted-report li { margin: 4px 0; font-size: 13px; line-height: 1.55; }
      .targeted-report .muted { margin: 0; color: #64748b; font-size: 13px; }
      .targeted-report .phase { border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 12px; margin-top: 9px; }
      .targeted-report .phase-title { display: flex; gap: 8px; align-items: baseline; margin-bottom: 8px; font-weight: 700; color: #0f172a; }
      .targeted-report .phase-title span { color: #64748b; font-size: 12px; font-weight: 400; }
      .targeted-report .exam-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
      .targeted-report .pill { border-radius: 999px; padding: 5px 9px; font-size: 12px; background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe; }
    </style>
    <div class="targeted-report">
      <div class="targeted-report-page" data-report-page>
        <div class="top">
          <h1>${escapeHtml(t("targeted.report.title"))}</h1>
          <div class="subtitle">${escapeHtml(t("targeted.report.subtitle"))}</div>
        </div>
        ${metaHtml}
      <section>
        <h2>${escapeHtml(t("targeted.report.dataBasis"))}</h2>
        <div class="box">
          <div class="exam-list">${examNames.length ? examNames.map((name) => `<span class="pill">${escapeHtml(name)}</span>`).join("") : `<span class="muted">${escapeHtml(t("targeted.report.noExamNames"))}</span>`}</div>
        </div>
      </section>
      <section>
        <h2>${escapeHtml(t("targeted.diagnosis.title"))}</h2>
        <div class="summary">${escapeHtml(longDiagnosisSummary(report, t))}</div>
      </section>
      <section class="grid">
        <div class="box emerald"><h3>${escapeHtml(t("targeted.diagnosis.strengths"))}</h3>${renderReportList(diagnosis.strengths, t)}</div>
        <div class="box"><h3>${escapeHtml(t("targeted.diagnosis.positiveEvidence"))}</h3>${renderReportList(diagnosis.positive_evidence, t)}</div>
      </section>
      <section class="grid">
        <div class="box amber"><h3>${escapeHtml(t("targeted.diagnosis.weaknesses"))}</h3>${renderReportList(diagnosis.weak_points, t)}</div>
        <div class="box rose"><h3>${escapeHtml(t("targeted.diagnosis.causes"))}</h3>${renderReportList(diagnosis.root_causes, t)}</div>
      </section>
      <section class="grid">
        <div class="box"><h3>${escapeHtml(t("targeted.diagnosis.evidence"))}</h3>${renderReportList(diagnosis.evidence, t)}</div>
        <div class="box emerald"><h3>${escapeHtml(t("targeted.diagnosis.teacherNotes"))}</h3>${renderReportList(diagnosis.teacher_notes, t)}</div>
      </section>
      </div>
      <div class="targeted-report-page" data-report-page>
        <div class="top">
          <h1>${escapeHtml(t("targeted.report.title"))}</h1>
          <div class="subtitle">${escapeHtml(t("targeted.plan.title"))}</div>
        </div>
        ${metaHtml}
      <section>
        <h2>${escapeHtml(t("targeted.plan.title"))}</h2>
        <div class="summary">${escapeHtml(plan.goal || report?.plan_text || t("targeted.plan.emptyGoal"))}<br/>${escapeHtml(t("targeted.plan.duration", { value: plan.duration || t("targeted.plan.defaultDuration") }))}</div>
        ${phases
          .map(
            (phase: any, index: number) => `
          <div class="phase">
            <div class="phase-title">${escapeHtml(t("targeted.plan.phase", { index: index + 1 }))}: ${escapeHtml(phase.title || t("targeted.plan.special"))} <span>${escapeHtml(phase.period || "")}</span></div>
            <div class="grid">
              <div class="box"><h3>${escapeHtml(t("targeted.plan.teacherActions"))}</h3>${renderReportList(phase.teacher_actions, t)}</div>
              <div class="box"><h3>${escapeHtml(t("targeted.plan.studentTasks"))}</h3>${renderReportList(phase.student_tasks, t)}</div>
              <div class="box violet"><h3>${escapeHtml(t("targeted.plan.practiceFocus"))}</h3>${renderReportList(phase.practice_focus, t)}</div>
              <div class="box"><h3>${escapeHtml(t("targeted.plan.checkpoints"))}</h3>${renderReportList(phase.checkpoints, t)}</div>
            </div>
          </div>
        `,
          )
          .join("")}
      </section>
      <section class="grid">
        <div class="box violet"><h3>${escapeHtml(t("targeted.plan.dailyRoutine"))}</h3>${renderReportList(plan.daily_routine, t)}</div>
        <div class="box emerald"><h3>${escapeHtml(t("targeted.plan.followUp"))}</h3>${renderReportList(plan.follow_up, t)}</div>
      </section>
      </div>
    </div>
  `;
  document.body.appendChild(reportEl);
  return reportEl;
}

function DiagnosisCard({
  report,
  loading,
  studentName,
}: {
  report?: TargetedReport | null;
  loading: boolean;
  studentName?: string;
}) {
  const { t } = useLocale();
  const diagnosis = report?.diagnosis || {};
  const source = report?.source_summary || {};
  return (
    <Card className="min-w-[320px] flex-1 border-border/70 shadow-sm">
      <CardHeader className="border-b bg-sky-50/70 pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Stethoscope className="h-5 w-5 text-primary" />
          {t("targeted.diagnosis.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5 p-5">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            {t("targeted.diagnosis.loading")}
          </div>
        ) : !report ? (
          <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-sm text-muted-foreground">
            {studentName
              ? t("targeted.diagnosis.importHint")
              : t("targeted.selectStudent")}
          </div>
        ) : (
          <>
            <div className="rounded-lg border border-sky-200 bg-sky-50 p-4">
              <p className="text-[15px] font-semibold leading-relaxed text-sky-950">
                {longDiagnosisSummary(report, t)}
              </p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                <Badge variant="secondary">
                  {t("targeted.diagnosis.level", {
                    value: diagnosis.level || t("targeted.diagnosis.followUp"),
                  })}
                </Badge>
                <Badge variant="secondary">
                  {t("targeted.diagnosis.examCount", {
                    count: source.exam_count ?? report.exam_names?.length ?? 0,
                  })}
                </Badge>
                <Badge variant="secondary">
                  {t("targeted.diagnosis.wrongCount", {
                    count: source.wrong_question_count ?? 0,
                  })}
                </Badge>
                <Badge variant="secondary">
                  {t("targeted.diagnosis.latestScore", {
                    value: formatScore(source.latest_score, t),
                  })}
                </Badge>
              </div>
            </div>

            <section className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <Label className="text-[15px] font-semibold text-emerald-900">
                  {t("targeted.diagnosis.strengths")}
                </Label>
                <TextList items={diagnosis.strengths} tone="emerald" />
              </div>
              <div className="space-y-2">
                <Label className="text-[15px] font-semibold text-sky-900">
                  {t("targeted.diagnosis.positiveEvidence")}
                </Label>
                <TextList items={diagnosis.positive_evidence} tone="blue" />
              </div>
            </section>
            <section className="space-y-2">
              <Label className="text-[15px] font-semibold text-sky-900">
                {t("targeted.diagnosis.evidence")}
              </Label>
              <TextList items={diagnosis.evidence} tone="blue" />
            </section>
            <section className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <Label className="text-[15px] font-semibold text-amber-900">
                  {t("targeted.diagnosis.weaknesses")}
                </Label>
                <TextList items={diagnosis.weak_points} tone="amber" />
              </div>
              <div className="space-y-2">
                <Label className="text-[15px] font-semibold text-rose-900">
                  {t("targeted.diagnosis.causes")}
                </Label>
                <TextList items={diagnosis.root_causes} tone="rose" />
              </div>
            </section>
            <section className="space-y-2">
              <Label className="text-[15px] font-semibold text-emerald-900">
                {t("targeted.diagnosis.teacherNotes")}
              </Label>
              <TextList items={diagnosis.teacher_notes} tone="emerald" />
            </section>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function PlanCard({
  report,
  loading,
  studentName,
}: {
  report?: TargetedReport | null;
  loading: boolean;
  studentName?: string;
}) {
  const { t } = useLocale();
  const plan = report?.plan || {};
  const phases = Array.isArray(plan.phases) ? plan.phases : [];
  return (
    <Card className="min-w-[320px] flex-1 border-border/70 shadow-sm">
      <CardHeader className="border-b bg-violet-50/70 pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Sparkles className="h-5 w-5 text-primary" />
          {t("targeted.plan.title")}
          <AIGeneratedBadge />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5 p-5">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            {t("targeted.plan.loading")}
          </div>
        ) : !report ? (
          <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-sm text-muted-foreground">
            {studentName
              ? t("targeted.plan.importHint")
              : t("targeted.selectStudent")}
          </div>
        ) : (
          <>
            <div className="rounded-lg border border-violet-200 bg-violet-50 p-4">
              <p className="text-[15px] font-semibold leading-relaxed text-violet-950">
                {plan.goal ||
                  report.plan_text ||
                  t("targeted.plan.personalGoal")}
              </p>
              <p className="mt-1 text-sm text-violet-700">
                {t("targeted.plan.duration", {
                  value: plan.duration || t("targeted.plan.defaultDuration"),
                })}
              </p>
            </div>

            {phases.length > 0 ? (
              <div className="space-y-3">
                {phases.map((phase: any, index: number) => (
                  <div
                    key={index}
                    className="rounded-lg border border-border/70 bg-background p-4 shadow-sm"
                  >
                    <div className="mb-3 flex flex-wrap items-center gap-2">
                      <Badge variant={index === 0 ? "default" : "secondary"}>
                        {t("targeted.plan.phase", { index: index + 1 })}
                      </Badge>
                      <span className="text-[15px] font-semibold">
                        {phase.title || t("targeted.plan.special")}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {phase.period || ""}
                      </span>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <div>
                        <p className="mb-1 text-sm font-semibold text-muted-foreground">
                          {t("targeted.plan.teacherActions")}
                        </p>
                        <TextList
                          items={phase.teacher_actions}
                          empty={t("targeted.noData")}
                          tone="blue"
                        />
                      </div>
                      <div>
                        <p className="mb-1 text-sm font-semibold text-muted-foreground">
                          {t("targeted.plan.studentTasks")}
                        </p>
                        <TextList
                          items={phase.student_tasks}
                          empty={t("targeted.noData")}
                          tone="emerald"
                        />
                      </div>
                      <div>
                        <p className="mb-1 text-sm font-semibold text-muted-foreground">
                          {t("targeted.plan.practiceFocus")}
                        </p>
                        <TextList
                          items={phase.practice_focus}
                          empty={t("targeted.noData")}
                          tone="amber"
                        />
                      </div>
                      <div>
                        <p className="mb-1 text-sm font-semibold text-muted-foreground">
                          {t("targeted.plan.checkpoints")}
                        </p>
                        <TextList
                          items={phase.checkpoints}
                          empty={t("targeted.noData")}
                          tone="violet"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                {t("targeted.plan.emptyPhases")}
              </p>
            )}

            <section className="grid gap-3 md:grid-cols-2">
              <div className="space-y-2">
                <Label className="text-[15px] font-semibold">
                  {t("targeted.plan.dailyRoutine")}
                </Label>
                <TextList items={plan.daily_routine} tone="violet" />
              </div>
              <div className="space-y-2">
                <Label className="text-[15px] font-semibold">
                  {t("targeted.plan.followUp")}
                </Label>
                <TextList items={plan.follow_up} tone="emerald" />
              </div>
            </section>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── 🟡 学情驱动内容推荐闭环：内容推荐 + 复测 ───────────────────────────────────
const RECOMMEND_LEARNED_STORAGE_KEY = "targeted-recommend-learned";

function buildResourceUrl(url: string): string {
  if (!url) return "#";
  if (url.startsWith("http") || url.startsWith("/api")) return url;
  return `${API_PREFIX}/${url.replace(/^\/+/, "")}`;
}

function loadLearnedResources(): Set<string> {
  try {
    const raw = localStorage.getItem(RECOMMEND_LEARNED_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed))
        return new Set<string>(parsed.filter((x) => typeof x === "string"));
    }
  } catch {
    // ignore storage errors
  }
  return new Set<string>();
}

function masteryRate(dims: unknown): number | null {
  if (!Array.isArray(dims) || dims.length === 0) return null;
  const values = dims
    .map((item) => Number((item as { student?: unknown })?.student))
    .filter((value) => !Number.isNaN(value));
  if (values.length === 0) return null;
  return Math.round(values.reduce((a, b) => a + b, 0) / values.length);
}

/** 复测前掌握率：before 可能是维度数组（旧格式），也可能是 targeted-improvement 的诊断 dict（含嵌套 diagnosis），按实际结构取值 */
function masteryRateBefore(before: unknown): number | null {
  if (Array.isArray(before)) return masteryRate(before);
  if (before && typeof before === "object") {
    const b = before as Record<string, unknown>;
    const candidates = [b, b.diagnosis];
    for (const candidate of candidates) {
      if (!candidate || typeof candidate !== "object") continue;
      const dict = candidate as Record<string, unknown>;
      const numericKey = [
        "mastery_rate",
        "avg_mastery",
        "overall_mastery",
        "average_mastery",
      ].find(
        (k) => typeof dict[k] === "number" && !Number.isNaN(Number(dict[k])),
      );
      if (numericKey) return Math.round(Number(dict[numericKey]));
      if (Array.isArray(dict.dimensions)) return masteryRate(dict.dimensions);
    }
  }
  return null;
}

function ContentRecommendationList({
  classId,
  subject,
  studentId,
  hasReport,
}: {
  classId: string;
  subject: string;
  studentId: string;
  hasReport: boolean;
}) {
  const { t } = useLocale();
  const [learned, setLearned] = useState<Set<string>>(loadLearnedResources);
  const enabled = !!classId && !!subject && !!studentId && hasReport;
  const { data: groups = [], isLoading } = useQuery({
    queryKey: ["targeted-recommend-content", classId, subject, studentId],
    queryFn: () => getRecommendationContent(classId, subject, studentId),
    enabled,
  });

  const total = groups.reduce((acc, group) => acc + group.resources.length, 0);
  const learnedCount = groups.reduce(
    (acc, group) =>
      acc +
      group.resources.filter((resource) => learned.has(resource.id)).length,
    0,
  );

  const toggleLearned = (resourceId: string) => {
    setLearned((prev) => {
      const next = new Set(prev);
      if (next.has(resourceId)) next.delete(resourceId);
      else next.add(resourceId);
      try {
        localStorage.setItem(
          RECOMMEND_LEARNED_STORAGE_KEY,
          JSON.stringify([...next]),
        );
      } catch {
        // ignore storage errors
      }
      return next;
    });
  };

  return (
    <Card className="min-w-[320px] flex-1 border-border/70 shadow-sm">
      <CardHeader className="border-b bg-amber-50/70 pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          <BookOpen className="h-5 w-5 text-primary" />
          {t("classDetail.targetedImprove.recommendContent.title")}
          {total > 0 && (
            <Badge variant="secondary" className="text-[11px] font-normal">
              {t("classDetail.targetedImprove.recommendContent.learnedCount", {
                learned: learnedCount,
                total,
              })}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-5">
        {isLoading ? (
          <div className="flex items-center justify-center py-10 text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            {t("classDetail.targetedImprove.recommendContent.loading")}
          </div>
        ) : !enabled ? (
          <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-sm text-muted-foreground">
            {t("classDetail.targetedImprove.recommendContent.needReport")}
          </div>
        ) : groups.length === 0 ? (
          <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-sm text-muted-foreground">
            {t("classDetail.targetedImprove.recommendContent.empty")}
          </div>
        ) : (
          <div className="max-h-[480px] space-y-4 overflow-y-auto pr-1">
            {groups.map((group) => (
              <div
                key={group.knowledge_point_id}
                className="rounded-lg border border-border/70 bg-background p-3.5 shadow-sm"
              >
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge
                    variant="secondary"
                    className="border-amber-200 bg-amber-100 text-amber-900"
                  >
                    {t(
                      "classDetail.targetedImprove.recommendContent.weakPoint",
                      { name: group.knowledge_point_name },
                    )}
                  </Badge>
                  {typeof group.mastery === "number" && (
                    <span className="text-xs text-muted-foreground">
                      {t(
                        "classDetail.targetedImprove.recommendContent.mastery",
                        { value: group.mastery },
                      )}
                    </span>
                  )}
                  <span className="ml-auto text-xs text-muted-foreground">
                    {t(
                      "classDetail.targetedImprove.recommendContent.resourceCount",
                      { count: group.resources.length },
                    )}
                  </span>
                </div>
                <div className="space-y-2">
                  {group.resources.map((resource) => {
                    const isLearned = learned.has(resource.id);
                    return (
                      <div
                        key={resource.id}
                        className={cn(
                          "flex items-start gap-2.5 rounded-md border px-3 py-2.5",
                          isLearned
                            ? "border-emerald-200 bg-emerald-50/60"
                            : "border-border/60 bg-muted/10",
                        )}
                      >
                        <button
                          type="button"
                          aria-label={t(
                            "classDetail.targetedImprove.recommendContent.markLearned",
                          )}
                          onClick={() => toggleLearned(resource.id)}
                          className={cn(
                            "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors",
                            isLearned
                              ? "border-emerald-500 bg-emerald-500 text-white"
                              : "border-muted-foreground/40 bg-white text-transparent hover:border-emerald-500",
                          )}
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-semibold">
                              {resource.title}
                            </span>
                            {resource.type && (
                              <Badge
                                variant="outline"
                                className="text-[10px] font-normal"
                              >
                                {resource.type}
                              </Badge>
                            )}
                            {typeof resource.difficulty === "number" && (
                              <Badge
                                variant="outline"
                                className="text-[10px] font-normal"
                              >
                                {t(
                                  "classDetail.targetedImprove.recommendContent.difficulty",
                                  { value: resource.difficulty },
                                )}
                              </Badge>
                            )}
                          </div>
                          {resource.description && (
                            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                              {resource.description}
                            </p>
                          )}
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                            {resource.file_name && (
                              <span className="truncate">
                                {resource.file_name}
                              </span>
                            )}
                            {(resource.tags || []).slice(0, 4).map((tag) => (
                              <span
                                key={tag}
                                className="rounded bg-muted px-1.5 py-0.5"
                              >
                                {tag}
                              </span>
                            ))}
                            {resource.file_url && (
                              <a
                                href={buildResourceUrl(resource.file_url)}
                                target="_blank"
                                rel="noreferrer"
                                className="ml-auto inline-flex items-center gap-1 text-primary hover:underline"
                              >
                                <ExternalLink className="h-3 w-3" />
                                {t(
                                  "classDetail.targetedImprove.recommendContent.openResource",
                                )}
                              </a>
                            )}
                          </div>
                        </div>
                        {isLearned && (
                          <Badge
                            variant="secondary"
                            className="shrink-0 text-[10px]"
                          >
                            {t(
                              "classDetail.targetedImprove.recommendContent.learned",
                            )}
                          </Badge>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ReEvaluateButton({
  classId,
  subject,
  studentId,
  disabled,
}: {
  classId: string;
  subject: string;
  studentId: string;
  disabled: boolean;
}) {
  const { t } = useLocale();
  const [result, setResult] = useState<{
    before: unknown;
    after: unknown;
  } | null>(null);
  const mutation = useMutation({
    mutationFn: () =>
      reevaluateDiagnosis({
        class_id: classId,
        student_id: studentId,
        subject,
      }),
    onSuccess: (data) => setResult({ before: data.before, after: data.after }),
    onError: (err: any) => {
      toast.error(
        t("classDetail.targetedImprove.recommendContent.reevaluateFailed"),
        {
          description: err?.message || undefined,
        },
      );
    },
  });

  const beforeRate = masteryRateBefore(result?.before);
  const afterRate = masteryRate(result?.after);
  const afterDims = Array.isArray(result?.after)
    ? (result.after as Array<{
        dim?: string;
        student?: number;
        class?: number;
      }>)
    : [];
  const beforeDict =
    result?.before && !Array.isArray(result.before)
      ? (result.before as {
          weak_points?: unknown;
          diagnosis?: { weak_points?: unknown };
        })
      : null;
  // 后端 before = 上次诊断 dict（weak_points 嵌套在 diagnosis 中），flat 字段兜底兼容旧格式
  const beforeWeakPoints = asArray(
    beforeDict?.diagnosis?.weak_points ?? beforeDict?.weak_points ?? [],
  );
  // 班级平均掌握率：取各维度班级掌握率（>0 视为有效值），无则 null 走「共 N 个维度」兜底
  const classRates = afterDims
    .map((dim) => Number(dim.class))
    .filter((value) => !Number.isNaN(value) && value > 0);
  const afterClassAvg =
    classRates.length > 0
      ? Math.round(
          classRates.reduce((sum, value) => sum + value, 0) / classRates.length,
        )
      : null;

  return (
    <Card className="min-w-[320px] flex-1 border-border/70 shadow-sm">
      <CardHeader className="border-b bg-emerald-50/70 pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          <RefreshCcw className="h-5 w-5 text-primary" />
          {t("classDetail.targetedImprove.recommendContent.reevaluateTitle")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-5">
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
          <p className="text-[15px] font-semibold leading-relaxed text-emerald-950">
            {t("classDetail.targetedImprove.recommendContent.reevaluateDesc")}
          </p>
          <Button
            size="sm"
            className="mt-3 gap-2"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || disabled || !studentId}
          >
            {mutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCcw className="h-4 w-4" />
            )}
            {mutation.isPending
              ? t("classDetail.targetedImprove.recommendContent.reevaluating")
              : t("classDetail.targetedImprove.recommendContent.reevaluate")}
          </Button>
        </div>

        {result && (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="flex-1 rounded-lg border border-border/70 bg-background p-3 text-center">
                <p className="text-xs text-muted-foreground">
                  {t("classDetail.targetedImprove.recommendContent.before")}
                </p>
                <p className="mt-1 text-lg font-bold">
                  {beforeRate !== null
                    ? t("classDetail.targetedImprove.recommendContent.rate", {
                        rate: beforeRate,
                      })
                    : t(
                        "classDetail.targetedImprove.recommendContent.noBeforeData",
                      )}
                </p>
                {beforeWeakPoints.length > 0 && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {t(
                      "classDetail.targetedImprove.recommendContent.weakPointCount",
                      { count: beforeWeakPoints.length },
                    )}
                  </p>
                )}
              </div>
              <TrendingUp className="h-4 w-4 shrink-0 text-muted-foreground" />
              <div className="flex-1 rounded-lg border border-border/70 bg-background p-3 text-center">
                <p className="text-xs text-muted-foreground">
                  {t("classDetail.targetedImprove.recommendContent.after")}
                </p>
                <p className="mt-1 text-lg font-bold text-emerald-600">
                  {afterRate !== null
                    ? t("classDetail.targetedImprove.recommendContent.rate", {
                        rate: afterRate,
                      })
                    : t("classDetail.targetedImprove.recommendContent.noData")}
                </p>
                {afterClassAvg !== null ? (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {t(
                      "classDetail.targetedImprove.recommendContent.classAvgRate",
                      { rate: afterClassAvg },
                    )}
                  </p>
                ) : (
                  afterDims.length > 0 && (
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      {t(
                        "classDetail.targetedImprove.recommendContent.dimCount",
                        { count: afterDims.length },
                      )}
                    </p>
                  )
                )}
              </div>
            </div>

            {afterDims.length > 0 && (
              <div className="space-y-2.5">
                {afterDims.map((dim, index) => {
                  const rate = Number(dim.student) || 0;
                  const classRate = Number(dim.class) || 0;
                  return (
                    <div
                      key={`${dim.dim || index}-${index}`}
                      className="space-y-1"
                    >
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="font-medium">
                          {dim.dim || `#${index + 1}`}
                        </span>
                        <span className="text-muted-foreground">
                          {t(
                            "classDetail.targetedImprove.recommendContent.rate",
                            { rate },
                          )}
                          {classRate > 0 && (
                            <span className="ml-2">
                              {t(
                                "classDetail.targetedImprove.recommendContent.dimClass",
                                { value: classRate },
                              )}
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-muted">
                        <div
                          className="h-2 rounded-full bg-emerald-500"
                          style={{
                            width: `${Math.min(100, Math.max(0, rate))}%`,
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {beforeWeakPoints.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                <p className="mb-1 text-xs font-semibold text-amber-900">
                  {t(
                    "classDetail.targetedImprove.recommendContent.weakPointsBefore",
                  )}
                </p>
                <ul className="list-disc space-y-0.5 pl-4 text-xs leading-relaxed text-amber-950">
                  {beforeWeakPoints.slice(0, 6).map((item, idx) => (
                    <li key={`${item}-${idx}`}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setResult(null)}
              >
                {t("classDetail.targetedImprove.recommendContent.close")}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function TargetedImprovePage({
  selectedSubject,
  selectedClass,
  onNavChange,
  initialStudentName,
  onNavigateToStudent,
}: TargetedImprovePageProps) {
  const { t, locale } = useLocale();

  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [selectedStudentName, setSelectedStudentName] = useState<string>("");
  const [importOpen, setImportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [recNotice, setRecNotice] = useState<(() => void) | null>(null);
  const storageKey = `${SUBJECT_STORAGE_PREFIX}${selectedClass}`;
  const [subject, setSubject] = useState(() => {
    try {
      return localStorage.getItem(storageKey) || selectedSubject || "语文";
    } catch {
      return selectedSubject || "语文";
    }
  });

  const { data: subjectOptions = FALLBACK_SUBJECTS, isError: subjectsError } =
    useQuery({
      queryKey: ["targeted-subjects"],
      queryFn: listTargetedSubjects,
    });
  const availableSubjects = useMemo(() => {
    const base = subjectOptions.length ? subjectOptions : FALLBACK_SUBJECTS;
    return base.includes(subject) ? base : [subject, ...base];
  }, [subject, subjectOptions]);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      setSubject(stored || selectedSubject || "语文");
    } catch {
      setSubject(selectedSubject || "语文");
    }
  }, [selectedClass, selectedSubject, storageKey]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, subject);
    } catch {
      // ignore
    }
  }, [storageKey, subject]);

  const {
    data: studentData,
    isLoading: studentsLoading,
    isError: studentsError,
  } = useQuery({
    queryKey: ["targeted-students", selectedClass, subject],
    queryFn: () => listTargetedStudents(selectedClass, subject),
    enabled: !!selectedClass && !!subject,
  });

  const students = studentData?.students || [];
  const recommendedNames = studentData?.recommended_names || [];
  const studentsByName = useMemo(
    () => new Map(students.map((s) => [s.name, s])),
    [students],
  );
  const recommendedStudents = useMemo(
    () =>
      recommendedNames
        .map((name) => studentsByName.get(name))
        .filter(Boolean) as TargetedStudentItem[],
    [recommendedNames, studentsByName],
  );
  const filteredStudents = useMemo(() => {
    const q = search.trim();
    if (!q) return students;
    return students.filter(
      (s) => s.name.includes(q) || String(s.student_number || "").includes(q),
    );
  }, [students, search]);

  useEffect(() => {
    if (!students.length) {
      setSelectedStudentName("");
      return;
    }
    if (initialStudentName && studentsByName.has(initialStudentName)) {
      setSelectedStudentName(initialStudentName);
      return;
    }
    if (selectedStudentName && studentsByName.has(selectedStudentName)) return;
    setSelectedStudentName(recommendedNames[0] || students[0].name);
  }, [
    initialStudentName,
    recommendedNames,
    selectedStudentName,
    students,
    studentsByName,
  ]);

  const selectedStudent = selectedStudentName
    ? studentsByName.get(selectedStudentName) || null
    : null;
  const {
    data: reportData,
    isLoading: reportLoading,
    isError: reportError,
  } = useQuery({
    queryKey: ["targeted-report", selectedClass, subject, selectedStudentName],
    queryFn: () =>
      getTargetedReport(selectedClass, subject, selectedStudentName),
    enabled: !!selectedClass && !!subject && !!selectedStudentName,
  });
  const report = reportData?.report || null;
  const reportExamNames = report?.exam_names || [];

  // 查询失败静默兜底：toast 提示
  useEffect(() => {
    if (subjectsError) toast.error(t("classDetail.subjectsLoadFailed"));
  }, [subjectsError, t]);

  useEffect(() => {
    if (studentsError) toast.error(t("classDetail.loadStudentsFailed"));
  }, [studentsError, t]);

  useEffect(() => {
    if (reportError) toast.error(t("classDetail.reportLoadFailed"));
  }, [reportError, t]);

  const saveRecs = useMutation({
    mutationFn: (names: string[]) =>
      saveTargetedRecommendations({
        class_id: selectedClass,
        subject,
        student_names: names,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["targeted-students", selectedClass, subject],
      });
    },
    onError: (err: any) => {
      toast.error(t("targeted.saveFailed"), {
        description: err?.message || t("classReview.retry"),
      });
    },
  });

  const addRecommended = (name: string) => {
    if (recommendedNames.includes(name)) return;
    if (recommendedNames.length >= 5) {
      toast.info(t("targeted.maxRecommended"));
      return;
    }
    setRecNotice(() => () => saveRecs.mutate([...recommendedNames, name]));
  };

  const removeRecommended = (name: string) => {
    setRecNotice(
      () => () => saveRecs.mutate(recommendedNames.filter((n) => n !== name)),
    );
  };

  const handleExportPDF = useCallback(async () => {
    if (exporting) return;
    if (!selectedStudent || !report) {
      toast.info(t("targeted.export.selectReport"));
      return;
    }
    setExporting(true);
    let reportEl: HTMLDivElement | null = null;
    try {
      reportEl = createReportElement({
        subject: translateSubjectName(locale, subject),
        student: selectedStudent,
        report,
        t,
        locale,
      });
      const pdf = new jsPDF("p", "mm", "a4");
      const pageWidth = 210;
      const pageHeight = 297;
      const pages = Array.from(
        reportEl.querySelectorAll<HTMLElement>("[data-report-page]"),
      );
      for (let index = 0; index < pages.length; index += 1) {
        const pageCanvas = await html2canvas(pages[index], {
          scale: 2,
          useCORS: true,
          logging: false,
          backgroundColor: "#ffffff",
        });
        const pageImg = pageCanvas.toDataURL("image/jpeg", 0.94);
        if (index > 0) pdf.addPage();
        pdf.addImage(pageImg, "JPEG", 0, 0, pageWidth, pageHeight);
      }
      pdf.save(
        `${t("targeted.export.fileName")}_${translateSubjectName(locale, subject)}_${selectedStudent.name}.pdf`,
      );
    } catch (error: unknown) {
      toast.error(t("classDetail.导出 PDF 失败"), {
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      if (reportEl?.parentNode) reportEl.parentNode.removeChild(reportEl);
      setExporting(false);
    }
  }, [exporting, locale, report, selectedStudent, subject, t]);

  return (
    <div className="space-y-5 pb-6 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Target className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h2 className="flex items-center gap-2 text-xl font-bold text-foreground">
              {t("targeted.title")}
              <Badge variant="secondary" className="text-[11px] font-normal">
                {translateSubjectName(locale, subject)}
              </Badge>
            </h2>
            <p className="text-sm text-muted-foreground">
              {t("targeted.subtitle")}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={subject} onValueChange={setSubject}>
            <SelectTrigger className="h-9 w-[140px] text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {availableSubjects.map((item) => (
                <SelectItem key={item} value={item}>
                  {translateSubjectName(locale, item)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={handleExportPDF}
            disabled={exporting}
          >
            {exporting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            {t("targeted.exportPdf")}
          </Button>
          <Button
            size="sm"
            className="gap-2"
            onClick={() => setImportOpen(true)}
          >
            <FileInput className="h-4 w-4" />
            {t("targeted.importExams")}
          </Button>
        </div>
      </div>

      <Card className="border-sky-200 bg-sky-50/70 shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base font-semibold text-sky-950">
            <FileInput className="h-4 w-4 text-sky-700" />
            {t("targeted.dataBasis")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {reportExamNames.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {reportExamNames.map((name) => (
                <Badge
                  key={name}
                  variant="secondary"
                  className="border border-sky-200 bg-white/80 px-2.5 py-1 text-sm text-sky-900"
                >
                  {name}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-sky-800/80">
              {t("targeted.dataBasisEmpty")}
            </p>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/70 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base font-semibold">
            <User className="h-4 w-4 text-primary" />
            {t("targeted.selector.title")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("targeted.selector.search")}
              className="h-10 pl-8 text-[15px]"
            />
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-sm font-semibold text-foreground">
                {t("targeted.selector.recommended")}
              </p>
              <span className="text-xs text-muted-foreground">
                {t("targeted.selector.recommendedHint", {
                  count: recommendedStudents.length,
                })}
              </span>
            </div>
            {studentsLoading ? (
              <div className="flex items-center justify-center rounded-lg border border-dashed py-8 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {t("targeted.selector.loading")}
              </div>
            ) : recommendedStudents.length === 0 ? (
              <div className="rounded-lg border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground">
                {t("targeted.selector.empty")}
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {recommendedStudents.map((student) => (
                  <button
                    key={student.id}
                    type="button"
                    onClick={() => setSelectedStudentName(student.name)}
                    className={cn(
                      "relative overflow-hidden rounded-xl border p-3 text-left transition-all hover:-translate-y-0.5 hover:shadow-md",
                      selectedStudentName === student.name
                        ? "border-primary/60 bg-gradient-to-br from-sky-50 via-white to-violet-50 ring-2 ring-primary/20"
                        : "border-white/70 bg-gradient-to-br from-white via-sky-50/70 to-violet-50/60 hover:border-primary/30",
                    )}
                  >
                    <span className="pointer-events-none absolute inset-x-0 top-0 h-1/2 bg-gradient-to-b from-white/80 to-transparent" />
                    <span className="pointer-events-none absolute -right-8 -top-10 h-20 w-20 rounded-full bg-white/60 blur-xl" />
                    <div className="relative z-10 flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-base font-semibold text-foreground">
                          {student.name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {t("targeted.selector.studentNumber", {
                            number: student.student_number || "-",
                          })}
                        </p>
                      </div>
                      <button
                        type="button"
                        aria-label={t("classDetail.removeRecommendedStudent", {
                          name: student.name,
                        })}
                        className="relative z-10 rounded-full p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          removeRecommended(student.name);
                        }}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <div className="relative z-10 mt-4 flex items-center justify-between text-xs">
                      <Badge
                        variant={student.has_report ? "default" : "secondary"}
                        className="text-[11px]"
                      >
                        {student.has_report
                          ? t("targeted.selector.reportReady")
                          : t("targeted.selector.reportPending")}
                      </Badge>
                      <span className="text-muted-foreground">
                        {t("targeted.selector.view")}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(280px,0.7fr)]">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="text-sm font-semibold text-foreground">
                  {t("targeted.selector.allStudents")}
                </p>
                <span className="text-xs text-muted-foreground">
                  {t("targeted.selector.count", {
                    count: filteredStudents.length,
                  })}
                </span>
              </div>
              <ScrollArea className="h-[260px] rounded-lg border">
                <div className="divide-y">
                  {filteredStudents.map((student) => {
                    const isRec = recommendedNames.includes(student.name);
                    return (
                      <button
                        key={student.id}
                        type="button"
                        onClick={() => setSelectedStudentName(student.name)}
                        className={cn(
                          "flex w-full items-center gap-3 px-3 py-3 text-left text-[15px] hover:bg-muted/40",
                          selectedStudentName === student.name &&
                            "bg-primary/5",
                        )}
                      >
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-xs font-bold">
                          {student.name.slice(0, 1)}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium">{student.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {t("targeted.selector.studentNumber", {
                              number: student.student_number || "-",
                            })}
                          </p>
                        </div>
                        <div className="hidden text-right text-xs sm:block">
                          <p className="text-muted-foreground">
                            {t("targeted.selector.wrongCount", {
                              count: student.wrong_question_count || 0,
                            })}
                          </p>
                        </div>
                        <Button
                          type="button"
                          variant={isRec ? "secondary" : "ghost"}
                          size="sm"
                          className="h-7 px-2 text-[11px]"
                          disabled={isRec || saveRecs.isPending}
                          onClick={(e) => {
                            e.stopPropagation();
                            addRecommended(student.name);
                          }}
                        >
                          <Plus className="mr-1 h-3 w-3" />
                          {isRec
                            ? t("targeted.selector.recommendedStatus")
                            : t("targeted.selector.add")}
                        </Button>
                      </button>
                    );
                  })}
                </div>
              </ScrollArea>
            </div>

            <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
              {selectedStudent ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 font-bold text-primary">
                      {selectedStudent.name.slice(0, 1)}
                    </div>
                    <div>
                      <p className="font-semibold">{selectedStudent.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {t("targeted.selector.studentNumber", {
                          number: selectedStudent.student_number || "-",
                        })}
                      </p>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center text-xs">
                    <div className="rounded-md bg-background/70 p-2">
                      <p className="text-muted-foreground">
                        {t("targeted.selector.latestScore")}
                      </p>
                      <p className="mt-1 font-bold">
                        {formatScore(selectedStudent.current_score, t)}
                      </p>
                    </div>
                    <div className="rounded-md bg-background/70 p-2">
                      <p className="text-muted-foreground">
                        {t("targeted.selector.trend")}
                      </p>
                      <p className="mt-1 font-bold">
                        {trendLabel(selectedStudent.score_trend)}
                      </p>
                    </div>
                    <div className="rounded-md bg-background/70 p-2">
                      <p className="text-muted-foreground">
                        {t("targeted.selector.wrong")}
                      </p>
                      <p className="mt-1 font-bold">
                        {selectedStudent.wrong_question_count || 0}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {(selectedStudent.weak_points || []).length > 0 ? (
                      selectedStudent.weak_points?.map((item) => (
                        <Badge
                          key={item}
                          variant="secondary"
                          className="text-[10px]"
                        >
                          {item}
                        </Badge>
                      ))
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        {t("targeted.selector.noWeakness")}
                      </p>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-8 w-full text-xs"
                    onClick={() =>
                      onNavigateToStudent
                        ? onNavigateToStudent(selectedStudent.name)
                        : onNavChange("class-students")
                    }
                  >
                    {t("targeted.selector.viewProfile")}
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {t("targeted.selector.selectPrompt")}
                </p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-4">
        <DiagnosisCard
          report={report}
          loading={reportLoading}
          studentName={selectedStudentName}
        />
        <PlanCard
          report={report}
          loading={reportLoading}
          studentName={selectedStudentName}
        />
      </div>

      {/* 客户功能 #15：未掌握知识点 → 个性化学习任务清单（勾完成 / 进度跟踪） */}
      <TargetedTaskList
        classId={selectedClass}
        subject={subject}
        students={students}
        selectedStudentName={selectedStudentName}
        reportId={report?.id}
      />

      <div className="flex flex-wrap gap-4">
        <ContentRecommendationList
          classId={selectedClass}
          subject={subject}
          studentId={selectedStudent?.id || ""}
          hasReport={Boolean(report)}
        />
        <ReEvaluateButton
          classId={selectedClass}
          subject={subject}
          studentId={selectedStudent?.id || ""}
          disabled={!selectedStudent}
        />
      </div>

      <TargetedImportExamDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        classId={selectedClass}
        subject={subject}
        onImported={async (result) => {
          const nextStudent =
            result.generated.length > 0 &&
            !result.generated.some(
              (item) => item.student_name === selectedStudentName,
            )
              ? result.generated[0].student_name
              : selectedStudentName;
          if (nextStudent && nextStudent !== selectedStudentName) {
            setSelectedStudentName(nextStudent);
          }
          if (nextStudent) {
            await queryClient.fetchQuery({
              queryKey: [
                "targeted-report",
                selectedClass,
                subject,
                nextStudent,
              ],
              queryFn: () =>
                getTargetedReport(selectedClass, subject, nextStudent),
            });
          }
        }}
      />
      <PrivacyNoticeDialog
        open={recNotice !== null}
        onOpenChange={(open) => !open && setRecNotice(null)}
        onConfirm={() => {
          recNotice?.();
          setRecNotice(null);
        }}
        context="靶向提升"
      />
    </div>
  );
}
