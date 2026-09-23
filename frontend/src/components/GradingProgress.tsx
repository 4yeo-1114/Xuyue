import { cn } from "@/lib/utils";
import { CheckCircle2, Clock, AlertCircle, Loader2 } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";

interface GradingTask {
  id: string;
  studentName: string;
  studentId: string;
  subject: string;
  status: "pending" | "processing" | "completed" | "error";
  progress?: number;
  score?: number;
}

interface GradingProgressProps {
  tasks: GradingTask[];
  className?: string;
}

export function GradingProgress({ tasks, className }: GradingProgressProps) {
  const { t } = useLocale();

  const statusConfig = {
    pending: {
      icon: Clock,
      color: "text-muted-foreground",
      bg: "bg-muted",
      labelKey: "grading.progress.status.pending",
    },
    processing: {
      icon: Loader2,
      color: "text-primary",
      bg: "bg-primary/10",
      labelKey: "grading.progress.status.processing",
    },
    completed: {
      icon: CheckCircle2,
      color: "text-success",
      bg: "bg-success/10",
      labelKey: "grading.progress.status.completed",
    },
    error: {
      icon: AlertCircle,
      color: "text-destructive",
      bg: "bg-destructive/10",
      labelKey: "grading.progress.status.error",
    },
  };

  const completed = tasks.filter(task => task.status === "completed").length;
  const total = tasks.length;
  const progressPercent = total > 0 ? (completed / total) * 100 : 0;

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-foreground">{t("grading.progress.title")}</h3>
          <p className="text-sm text-muted-foreground">
            {t("grading.progress.completed", { done: completed, total })}
          </p>
        </div>
        <div className="text-3xl font-bold text-gradient-hero">
          {Math.round(progressPercent)}%
        </div>
      </div>

      <div className="h-3 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full progress-gradient rounded-full transition-all duration-500 ease-out"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      <div className="grid grid-cols-5 sm:grid-cols-9 gap-2 mt-4">
        {tasks.map((task) => {
          const config = statusConfig[task.status];
          const StatusIcon = config.icon;
          const label = t(config.labelKey);
          
          return (
            <div
              key={task.id}
              className={cn(
                "aspect-square rounded-lg flex items-center justify-center relative group cursor-pointer",
                "transition-all duration-200 hover:scale-110",
                config.bg
              )}
              title={`${task.studentName} - ${label}`}
            >
              <StatusIcon className={cn(
                "w-4 h-4",
                config.color,
                task.status === "processing" && "animate-spin"
              )} />
              
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-foreground text-background text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-10">
                {task.studentName}
                {task.score !== undefined && ` - ${task.score}${t("grading.unit.score")}`}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-4 text-sm">
        {Object.entries(statusConfig).map(([key, config]) => {
          const Icon = config.icon;
          return (
            <div key={key} className="flex items-center gap-1.5">
              <Icon className={cn("w-4 h-4", config.color)} />
              <span className="text-muted-foreground">{t(config.labelKey)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
