import { cn } from "@/lib/utils";
import { FileText, Play, Pause, RotateCcw, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/contexts/LocaleContext";

interface ScanFile {
  id: string;
  name: string;
  pages: number;
  status: "queued" | "processing" | "completed" | "paused";
  progress?: number;
}

interface ScanQueueProps {
  files: ScanFile[];
  className?: string;
}

const statusConfig = {
  queued: { color: "text-muted-foreground" },
  processing: { color: "text-primary" },
  completed: { color: "text-success" },
  paused: { color: "text-warning" },
};

export function ScanQueue({ files, className }: ScanQueueProps) {
  const { t } = useLocale();
  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
          {t("home.scanQueue.title")}
          <span className="px-2 py-0.5 text-xs rounded-full bg-primary/10 text-primary">
            {t("home.scanQueue.pendingCount", {
              count: files.filter((f) => f.status !== "completed").length,
            })}
          </span>
        </h3>
      </div>

      <div className="space-y-2">
        {files.map((file) => {
          const status = statusConfig[file.status];

          return (
            <div
              key={file.id}
              className="p-3 rounded-lg bg-muted/50 border border-border/50 hover:border-primary/30 transition-colors"
            >
              <div className="flex items-center gap-3">
                <FileText className="w-5 h-5 text-primary" />

                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {file.name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t("home.scanQueue.pageCount", { count: file.pages })} ·{" "}
                    <span className={status.color}>
                      {t(`home.scanQueue.status.${file.status}`)}
                    </span>
                  </p>
                </div>

                {file.status === "processing" &&
                  file.progress !== undefined && (
                    <div className="w-20 h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full progress-gradient rounded-full transition-all"
                        style={{ width: `${file.progress}%` }}
                      />
                    </div>
                  )}

                {file.status === "completed" && (
                  <CheckCircle2 className="w-5 h-5 text-success" />
                )}

                {file.status === "queued" && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-primary"
                  >
                    <Play className="w-4 h-4 mr-1" />
                    {t("home.scanQueue.start")}
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
