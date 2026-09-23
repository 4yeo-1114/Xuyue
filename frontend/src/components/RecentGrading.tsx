import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSubjectName } from "@/i18n";
import {
  Printer,
  Camera,
  Smartphone,
  Monitor,
  CheckCircle2,
  Clock,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";

interface GradingRecord {
  id: string;
  className: string;
  subject: string;
  count: number;
  completedCount: number;
  source: "copier" | "camera" | "phone" | "computer";
  timestamp: string;
  avgScore?: number;
}

interface RecentGradingProps {
  records: GradingRecord[];
  className?: string;
}

const sourceConfig = {
  copier: { icon: Printer, color: "text-primary bg-primary/10" },
  camera: { icon: Camera, color: "text-physics bg-physics/10" },
  phone: { icon: Smartphone, color: "text-success bg-success/10" },
  computer: { icon: Monitor, color: "text-accent bg-accent/10" },
};

export function RecentGrading({ records, className }: RecentGradingProps) {
  const { t, locale } = useLocale();
  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-foreground">
          {t("home.recentGrading.title")}
        </h3>
        <Button variant="ghost" size="sm" className="text-primary">
          {t("home.recentGrading.viewAll")}{" "}
          <ChevronRight className="w-4 h-4 ml-1" />
        </Button>
      </div>

      <div className="space-y-3">
        {records.map((record) => {
          const source = sourceConfig[record.source];
          const SourceIcon = source.icon;
          const isComplete = record.completedCount === record.count;
          const progress = (record.completedCount / record.count) * 100;

          return (
            <div
              key={record.id}
              className="group p-4 rounded-xl bg-card border border-border/50 hover:border-primary/30 transition-all duration-300 cursor-pointer card-elevated"
            >
              <div className="flex items-start gap-4">
                {/* Source Icon */}
                <div className={cn("p-2.5 rounded-lg", source.color)}>
                  <SourceIcon className="w-5 h-5" />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-medium text-foreground truncate">
                      {record.className}
                    </h4>
                    <span className="px-2 py-0.5 text-xs rounded-full bg-muted text-muted-foreground">
                      {translateSubjectName(locale, record.subject)}
                    </span>
                  </div>

                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1">
                      {isComplete ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                      ) : (
                        <Clock className="w-3.5 h-3.5" />
                      )}
                      {t("home.recentGrading.progress", {
                        done: record.completedCount,
                        total: record.count,
                      })}
                    </span>
                    <span>{record.timestamp}</span>
                    {record.avgScore !== undefined && (
                      <span className="text-primary font-medium">
                        {t("home.recentGrading.avgScore", {
                          score: record.avgScore,
                        })}
                      </span>
                    )}
                  </div>

                  {/* Progress bar for incomplete */}
                  {!isComplete && (
                    <div className="mt-2 h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full progress-gradient rounded-full"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                  )}
                </div>

                {/* Arrow */}
                <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
