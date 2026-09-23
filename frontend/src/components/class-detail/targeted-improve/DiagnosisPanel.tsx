import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMemo } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { AIGeneratedBadge } from "@/components/common/AIGeneratedBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Stethoscope, Brain, Sparkles, AlertCircle, CheckCircle2, Heart } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";
import type { Diagnosis, KnowledgeTarget, QuestionTarget, TargetMode } from "./targetedData";

interface DiagnosisPanelProps {
  mode: TargetMode;
  studentName?: string;
  diagnosis?: Diagnosis;
  knowledgeTarget?: KnowledgeTarget;
  questionTarget?: QuestionTarget;
}

function PersonDiagnosis({ studentName, diagnosis }: { studentName: string; diagnosis: Diagnosis }) {
  const { t } = useLocale();
  const errorCauses = useMemo(
    () => [
      { name: t("classDetail.知识漏洞"), color: "hsl(var(--destructive))" },
      { name: t("classDetail.方法缺失"), color: "hsl(var(--warning))" },
      { name: t("classDetail.审题失误"), color: "hsl(var(--accent))" },
      { name: t("classDetail.计算粗心"), color: "hsl(var(--primary))" },
    ],
    [t]
  );
  const pieData = errorCauses.map((c, i) => ({ ...c, value: 35 - i * 8 }));
  return (
    <div className="space-y-3 text-xs">
      {/* Academic diagnosis */}
      <div className="rounded-lg border border-border/50 p-3 space-y-2">
        <p className="font-semibold flex items-center gap-1.5 text-foreground">
          <Stethoscope className="w-3.5 h-3.5 text-primary" />{t("classDetail.academicDiagnosis")}
        </p>
        <div className="space-y-1 text-[11px]">
          <p>{t("classDetail.currentLevelLabel")}<strong className="text-foreground">{diagnosis.level}</strong></p>
          <p>{t("classDetail.coreProblemLabel")}<strong className="text-destructive">{diagnosis.coreProblems.join(" + ")}</strong></p>
          <p className="font-medium mt-1.5">{t("classDetail.rootCauseLabel")}</p>
          {diagnosis.rootCauses.map((c, i) => (
            <p key={i} className="text-muted-foreground pl-2">
              <AlertCircle className="w-3 h-3 inline mr-1 text-destructive" />{c}
            </p>
          ))}
        </div>
      </div>

      {/* Error cause pie */}
      <div className="rounded-lg border border-border/50 p-3">
        <p className="font-semibold flex items-center gap-1.5 text-foreground mb-2">
          <Brain className="w-3.5 h-3.5 text-primary" />{t("classDetail.errorCauseAnalysis")}
        </p>
        <div className="flex items-center gap-4">
          <div className="w-20 h-20">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" cx="50%" cy="50%" innerRadius={18} outerRadius={36} strokeWidth={1}>
                  {pieData.map((d, i) => <Cell key={i} fill={d.color} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="space-y-1">
            {pieData.map(d => (
              <div key={d.name} className="flex items-center gap-1.5 text-[11px]">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: d.color }} />
                <span>{d.name}</span>
                <span className="font-bold text-foreground">{d.value}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Learning quality */}
      <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
        <p className="font-semibold flex items-center gap-1.5 text-foreground">
          <Heart className="w-3.5 h-3.5 text-primary" />{t("classDetail.learningQualityDiagnosis")}
        </p>
        <div className="grid grid-cols-2 gap-1.5 text-[11px] text-muted-foreground">
          <span>{t("classDetail.motivationLabel")}<strong className="text-foreground">{diagnosis.motivation}</strong></span>
          <span>{t("classDetail.habitLabel")}<strong className="text-foreground">{diagnosis.habit}</strong></span>
          <span>{t("classDetail.methodLabel")}<strong className="text-foreground">{diagnosis.method}</strong></span>
          <span>{t("classDetail.timeManagementLabel")}<strong className="text-foreground">{diagnosis.timeManagement}</strong></span>
        </div>
      </div>

      {/* Personality */}
      <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
        <p className="font-semibold flex items-center gap-1.5 text-foreground">
          <Sparkles className="w-3.5 h-3.5 text-primary" />{t("classDetail.personalityTraits")}
        </p>
        <div className="text-[11px] space-y-1">
          <p><CheckCircle2 className="w-3 h-3 inline mr-1 text-emerald-600" />{t("classDetail.strengthsLabel", { value: diagnosis.strengths.join("、") })}</p>
          <p><AlertCircle className="w-3 h-3 inline mr-1 text-destructive" />{t("classDetail.weaknessesLabel", { value: diagnosis.weaknesses.join("、") })}</p>
          <p><Heart className="w-3 h-3 inline mr-1 text-primary" />{t("classDetail.interestsLabel", { value: diagnosis.interests.join("、") })}</p>
        </div>
      </div>

      <div className="flex gap-1.5">
        <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]">{t("classDetail.viewDetailedDiagnosis")}</Button>
        <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]">{t("classDetail.adjustDiagnosisWeight")}</Button>
      </div>
    </div>
  );
}

function KnowledgeDiagnosis({ target }: { target: KnowledgeTarget }) {
  const { t } = useLocale();
  return (
    <div className="space-y-3 text-xs">
      <div className="rounded-lg border border-border/50 p-3 space-y-2">
        <p className="font-semibold flex items-center gap-1.5 text-foreground">
          <Stethoscope className="w-3.5 h-3.5 text-primary" />{t("classDetail.knowledgeDiagnosisTitle", { name: target.name })}
        </p>
        <div className="text-[11px] space-y-1">
          <p>{t("classDetail.classMasteryRateLabel")}<strong className={target.masteryRate < 50 ? "text-destructive" : "text-foreground"}>{target.masteryRate}%</strong></p>
          <p>{t("classDetail.weakStudentCountLabel")}<strong className="text-foreground">{t("header.studentsCount", { count: target.affectedCount })}</strong></p>
          <p>{t("classDetail.commonIssueLabel")}<strong className="text-foreground">{target.commonIssue}</strong></p>
        </div>
      </div>
      <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
        <p className="font-semibold text-foreground text-[11px]">{t("classDetail.weakStudentList")}</p>
        <div className="flex flex-wrap gap-1">
          {target.affectedStudents.map(s => (
            <Badge key={s} variant="secondary" className="text-[10px]">{s}</Badge>
          ))}
        </div>
      </div>
    </div>
  );
}

function QuestionDiagnosis({ target }: { target: QuestionTarget }) {
  const { t } = useLocale();
  return (
    <div className="space-y-3 text-xs">
      <div className="rounded-lg border border-border/50 p-3 space-y-2">
        <p className="font-semibold flex items-center gap-1.5 text-foreground">
          <Stethoscope className="w-3.5 h-3.5 text-primary" />{t("classDetail.wrongQuestionDiagnosis")}
        </p>
        <p className="text-[11px] bg-muted/50 rounded p-2">{target.content}</p>
        <div className="text-[11px] space-y-1">
          <p>{t("classDetail.sourceLabel", { source: target.source })} · {t("classDetail.errorRateColonLabel")}<strong className="text-destructive">{target.errorRate}%</strong></p>
          <p>{t("classDetail.involvedKnowledgePointsLabel")}{target.knowledgePoints.map(kp => <Badge key={kp} variant="outline" className="text-[10px] mr-1">{kp}</Badge>)}</p>
        </div>
      </div>
      <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
        <p className="font-semibold text-foreground text-[11px]">{t("classDetail.typicalErrorCategories")}</p>
        <div className="flex gap-1.5">
          {target.typicalErrors.map(e => (
            <span key={e} className="text-[10px] px-2 py-1 rounded-md bg-destructive/10 text-destructive">{e}</span>
          ))}
        </div>
      </div>
      <div className="rounded-lg border border-border/50 p-3 space-y-1.5">
        <p className="font-semibold text-foreground text-[11px]">{t("classDetail.wrongStudentCount", { count: target.affectedStudents.length })}</p>
        <div className="flex flex-wrap gap-1">
          {target.affectedStudents.map(s => (
            <Badge key={s} variant="secondary" className="text-[10px]">{s}</Badge>
          ))}
        </div>
      </div>
    </div>
  );
}

export function DiagnosisPanel({ mode, studentName, diagnosis, knowledgeTarget, questionTarget }: DiagnosisPanelProps) {
  const { t, locale } = useLocale();

  const title = mode === "person" ? t("classDetail.aiDeepDiagnosisTitle", { name: studentName || "" }) :
                mode === "knowledge" ? t("classDetail.AI知识点诊断") : t("classDetail.AI错题诊断");
  return (
    <Card className="flex-1 min-w-[320px]" data-tour="ti-diagnosis">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          {title}
          <AIGeneratedBadge />
        </CardTitle>
      </CardHeader>
      <CardContent>
        {mode === "person" && diagnosis && <PersonDiagnosis studentName={studentName!} diagnosis={diagnosis} />}
        {mode === "knowledge" && knowledgeTarget && <KnowledgeDiagnosis target={knowledgeTarget} />}
        {mode === "question" && questionTarget && <QuestionDiagnosis target={questionTarget} />}
        {!diagnosis && mode === "person" && <p className="text-xs text-muted-foreground">{t("classDetail.selectStudentFirst")}</p>}
        {!knowledgeTarget && mode === "knowledge" && <p className="text-xs text-muted-foreground">{t("classDetail.selectKnowledgeFirst")}</p>}
        {!questionTarget && mode === "question" && <p className="text-xs text-muted-foreground">{t("classDetail.selectQuestionFirst")}</p>}
      </CardContent>
    </Card>
  );
}
