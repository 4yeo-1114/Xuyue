import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Target, RefreshCw, Pencil, Video, FileText, ClipboardList, Award, Users, Star } from "lucide-react";
import type { ImprovePlan, KnowledgeTarget, QuestionTarget, VariantQuestion, TargetMode } from "./targetedData";

interface PlanGeneratorProps {
  mode: TargetMode;
  plan?: ImprovePlan;
  knowledgeTarget?: KnowledgeTarget;
  questionTarget?: QuestionTarget;
  variants?: VariantQuestion[];
}

function PersonPlan({ plan }: { plan: ImprovePlan }) {
  const { t } = useLocale();
  return (
    <div className="space-y-3 text-xs">
      <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 space-y-1">
        <p className="font-bold text-foreground">{plan.planName}</p>
        <div className="flex gap-3 text-[11px] text-muted-foreground">
          <span>{t("classDetail.periodLabel", { value: plan.duration })}</span>
          <span>{t("classDetail.targetRangeLabel", { from: plan.targetFrom, to: plan.targetTo })}</span>
          <span>{t("classDetail.enterTierLabel", { tier: plan.targetTier })}</span>
        </div>
      </div>

      {plan.stages.map((stage, i) => (
        <div key={i} className="rounded-lg border border-border/50 p-3 space-y-1.5">
          <div className="flex items-center gap-2">
            <Badge variant={i === 0 ? "default" : "secondary"} className="text-[10px]">{t("classDetail.stageLabel", { index: i + 1 })}</Badge>
            <span className="font-semibold text-foreground">{stage.name}</span>
            <span className="text-[10px] text-muted-foreground">{stage.weeks}</span>
          </div>
          <p className="text-[11px] text-muted-foreground">{t("classDetail.coreTaskLabel", { task: stage.coreTask })}</p>
          <div className="space-y-0.5 text-[11px] text-muted-foreground pl-2">
            {stage.dailyTasks.map((task, j) => <p key={j}>• {task}</p>)}
          </div>
          <div className="flex gap-2 text-[11px] text-muted-foreground mt-1">
            <span className="flex items-center gap-0.5"><Video className="w-3 h-3" />{t("classDetail.microVideoCount", { count: stage.resources.videos })}</span>
            <span className="flex items-center gap-0.5"><FileText className="w-3 h-3" />{t("classDetail.exerciseCount", { count: stage.resources.exercises })}</span>
            <span className="flex items-center gap-0.5"><ClipboardList className="w-3 h-3" />{t("classDetail.templateCount", { count: stage.resources.templates })}</span>
          </div>
        </div>
      ))}

      <div className="rounded-lg border border-border/50 p-3 space-y-1.5" data-tour="ti-motivation">
        <p className="font-semibold text-foreground flex items-center gap-1.5">
          <Award className="w-3.5 h-3.5 text-primary" />{t("classDetail.激励策略")}
        </p>
        <div className="text-[11px] text-muted-foreground space-y-0.5">
          <p>{t("classDetail.milestoneRewardLabel", { reward: plan.milestoneReward })}</p>
          <p><Star className="w-3 h-3 inline mr-0.5 text-amber-500" />{t("classDetail.badgeSystemLabel", { badge: plan.badge })}</p>
          <p><Users className="w-3 h-3 inline mr-0.5 text-primary" />{t("classDetail.peerSupportLabel", { buddy: plan.buddy })}</p>
        </div>
      </div>

      <div className="flex gap-1.5">
        <Button size="sm" className="h-7 text-[11px]"><Target className="w-3 h-3 mr-1" />{t("classDetail.confirmGeneratePlan")}</Button>
        <Button variant="outline" size="sm" className="h-7 text-[11px]"><Pencil className="w-3 h-3 mr-1" />{t("classDetail.manualAdjust")}</Button>
        <Button variant="ghost" size="sm" className="h-7 text-[11px]"><RefreshCw className="w-3 h-3 mr-1" />{t("classDetail.regenerate")}</Button>
      </div>
    </div>
  );
}

function KnowledgePlan({ target }: { target: KnowledgeTarget }) {
  const { t } = useLocale();
  const layers = [
    { label: t("classDetail.A层拓展"), color: "bg-emerald-50 border-emerald-200", desc: t("classDetail.深化理解 综合应用"), count: Math.max(2, Math.round(target.affectedCount * 0.2)) },
    { label: t("classDetail.B层巩固"), color: "bg-amber-50 border-amber-200", desc: t("classDetail.基本方法训练 强化薄弱环节"), count: Math.max(3, Math.round(target.affectedCount * 0.5)) },
    { label: t("classDetail.C层补救"), color: "bg-red-50 border-red-200", desc: t("classDetail.基础概念重建 微课辅助"), count: Math.max(2, Math.round(target.affectedCount * 0.3)) },
  ];
  return (
    <div className="space-y-3 text-xs">
      <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
        <p className="font-bold text-foreground">{t("classDetail.tieredReinforcementTitle", { name: target.name })}</p>
        <p className="text-[11px] text-muted-foreground">{t("classDetail.coverWeakStudentsLabel", { count: target.affectedCount })}</p>
      </div>
      {layers.map((l, i) => (
        <div key={i} className={`rounded-lg border p-3 space-y-1 ${l.color}`}>
          <p className="font-semibold text-foreground">{t("classDetail.layerCountLabel", { label: l.label, count: l.count })}</p>
          <p className="text-[11px] text-muted-foreground">{l.desc}</p>
        </div>
      ))}
      <Button size="sm" className="h-7 text-[11px]"><Target className="w-3 h-3 mr-1" />{t("classDetail.oneClickPushWeakStudents")}</Button>
    </div>
  );
}

function QuestionPlan({ variants }: { variants: VariantQuestion[] }) {
  const { t } = useLocale();
  const LEVEL_COLORS = { "巩固": "bg-emerald-100 text-emerald-800", "提升": "bg-amber-100 text-amber-800", "拓展": "bg-primary/10 text-primary" };
  return (
    <div className="space-y-3 text-xs">
      <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
        <p className="font-bold text-foreground">{t("classDetail.variantTrainingTitle")}</p>
        <p className="text-[11px] text-muted-foreground">{t("classDetail.variantCountDesc")}</p>
      </div>
      {variants.map(v => (
        <div key={v.id} className="rounded-lg border border-border/50 p-3 space-y-1.5">
          <div className="flex items-center gap-2">
            <Badge className={`text-[10px] ${LEVEL_COLORS[v.level]}`}>{v.level}</Badge>
            <span className="text-[11px] text-muted-foreground">{t("classDetail.difficultyLabel")}{"★".repeat(v.difficulty)}{"☆".repeat(5 - v.difficulty)}</span>
          </div>
          <p className="text-[11px] text-foreground">{v.content}</p>
          <Badge variant="outline" className="text-[10px]">{v.knowledgePoint}</Badge>
        </div>
      ))}
      <Button size="sm" className="h-7 text-[11px]"><Target className="w-3 h-3 mr-1" />{t("classDetail.pushToWrongStudents")}</Button>
    </div>
  );
}

export function PlanGenerator({ mode, plan, knowledgeTarget, questionTarget, variants }: PlanGeneratorProps) {
  const { t, locale } = useLocale();

  const title = mode === "person" ? t("classDetail.AI生成个性化提升方案") :
                mode === "knowledge" ? t("classDetail.AI生成分层强化方案") : t("classDetail.AI生成变式训练");
  return (
    <Card className="flex-1 min-w-[320px]" data-tour="ti-plan">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {mode === "person" && plan && <PersonPlan plan={plan} />}
        {mode === "knowledge" && knowledgeTarget && <KnowledgePlan target={knowledgeTarget} />}
        {mode === "question" && variants && <QuestionPlan variants={variants} />}
        {mode === "person" && !plan && <p className="text-xs text-muted-foreground">{t("classDetail.selectStudentToGenerate")}</p>}
        {mode === "knowledge" && !knowledgeTarget && <p className="text-xs text-muted-foreground">{t("classDetail.selectKnowledgeFirst")}</p>}
        {mode === "question" && !variants && <p className="text-xs text-muted-foreground">{t("classDetail.selectQuestionFirst")}</p>}
      </CardContent>
    </Card>
  );
}
