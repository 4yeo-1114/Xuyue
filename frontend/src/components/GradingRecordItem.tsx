import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n/index";

interface GradingRecordItemProps {
  subject: string;
  subjectColor: string;
  title: string;
  studentName: string;
  gradingTime: string;
  score: number;
  onViewDetails?: () => void;
}

const subjectColorMap: Record<string, string> = {
  语文: "bg-rose-100 text-rose-600",
  数学: "bg-blue-100 text-blue-600",
  英语: "bg-purple-100 text-purple-600",
  物理: "bg-cyan-100 text-cyan-600",
  化学: "bg-green-100 text-green-600",
  生物: "bg-emerald-100 text-emerald-600",
  历史: "bg-amber-100 text-amber-600",
  地理: "bg-teal-100 text-teal-600",
  政治: "bg-pink-100 text-pink-600",
};

export function GradingRecordItem({
  subject,
  title,
  studentName,
  gradingTime,
  score,
  onViewDetails,
}: GradingRecordItemProps) {
  const { t, locale } = useLocale();
  const colorClass = subjectColorMap[subject] || "bg-gray-100 text-gray-600";
  const subjectLabel = translateSubjectName(locale, subject);
  
  return (
    <div className="p-4 bg-card rounded-xl border border-border hover:border-primary/30 transition-colors">
      <div className="flex items-center gap-4">
        <span className={cn(
          "px-3 py-1.5 rounded-lg text-sm font-medium shrink-0",
          colorClass
        )}>
          {subjectLabel}
        </span>

        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-foreground truncate">{title}</h4>
          <p className="text-sm text-muted-foreground mt-0.5">
            {t("grading.record.student", { name: studentName })}  |  {t("grading.record.time", { time: gradingTime })}
          </p>
        </div>

        <div className="text-right shrink-0">
          <p className="text-2xl font-bold text-primary">{score}</p>
          <p className="text-xs text-muted-foreground">{t("grading.unit.score").trim()}</p>
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={onViewDetails}
          className="shrink-0"
        >
          {t("grading.record.viewDetail")}
        </Button>
      </div>
    </div>
  );
}
