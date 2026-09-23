import { useState, useCallback, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  FolderOpen,
  Loader2,
  ArrowLeft,
  FileText,
  ChevronRight,
  BarChart3,
  Users,
  Target,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { listFolders, getErrorBookFolderStats } from "@/services/gradingApi";
import { ErrorBookDetail } from "./ErrorBookDetail";
import { useLocale } from "@/contexts/LocaleContext";

interface ErrorBookPageProps {
  selectedClass: string;
}

export function ErrorBookPage({ selectedClass }: ErrorBookPageProps) {
  const { t } = useLocale();

  const displayFolderName = useCallback((name: string) => {
    const s = String(name || "");
    if (s.startsWith("cls_")) {
      const i = s.indexOf("__");
      if (i > 4 && i + 2 < s.length) return s.slice(i + 2);
    }
    return s;
  }, []);

  const [folders, setFolders] = useState<
    {
      name: string;
      student_count: number;
      question_count: number;
      error_rate: number;
      stats_error?: boolean;
    }[]
  >([]);
  const [loading, setLoading] = useState(false);
  const [selectedFolderName, setSelectedFolderName] = useState<string | null>(
    null,
  );

  const loadFolders = useCallback(async () => {
    if (!selectedClass) {
      setFolders([]);
      return;
    }
    setLoading(true);
    try {
      const res = await listFolders(selectedClass || undefined);
      if (res.ok) {
        const foldersWithCounts = await Promise.all(
          (res.folders || []).map(async (name) => {
            try {
              const statsRes = await getErrorBookFolderStats(name);
              if (statsRes.ok) {
                return {
                  name,
                  student_count: statsRes.student_count,
                  question_count: statsRes.question_count,
                  error_rate: statsRes.error_rate,
                  stats_error: false,
                };
              }
              return {
                name,
                student_count: 0,
                question_count: 0,
                error_rate: 0,
                stats_error: true,
              };
            } catch {
              return {
                name,
                student_count: 0,
                question_count: 0,
                error_rate: 0,
                stats_error: true,
              };
            }
          }),
        );
        // 保留全部真实文件夹（含 student_count=0 的空错题本），不静默过滤；
        // 统计请求失败的文件夹用 stats_error 单独标记，避免后端瞬时故障让文件夹从列表消失。
        setFolders(foldersWithCounts);
      }
    } catch {
      toast.error(t("grading.errorBook.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [selectedClass, t]);

  useEffect(() => {
    loadFolders();
  }, [loadFolders]);

  const handleSelectFolder = (name: string) => {
    setSelectedFolderName(name);
  };

  if (selectedFolderName) {
    return (
      <ErrorBookDetail
        folderName={selectedFolderName}
        onBack={() => setSelectedFolderName(null)}
      />
    );
  }

  return (
    <div
      className={cn(
        "space-y-6 animate-in fade-in duration-300 h-full flex flex-col",
      )}
    >
      <div className="shrink-0 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground tracking-tight">
            {t("grading.errorBook.title")}
          </h1>
          <p className="text-sm text-muted-foreground mt-1.5">
            {t("grading.errorBook.subtitle")}
          </p>
        </div>
      </div>

      <Card className="flex-1 overflow-hidden border-border/50 shadow-sm flex flex-col">
        <CardHeader className="pb-4 shrink-0 bg-muted/20 border-b border-border/50">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2 text-primary">
                <FileText className="w-5 h-5" />
                {t("grading.errorBook.recordsTitle")}
              </CardTitle>
            </div>
            {folders.length > 0 && (
              <div className="text-sm text-muted-foreground">
                {t("grading.errorBook.recordsFound", { count: folders.length })}
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent className="p-0 flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-full min-h-[300px]">
              <Loader2 className="w-8 h-8 animate-spin text-primary/50 mb-4" />
              <p className="text-sm text-muted-foreground animate-pulse">
                {t("grading.errorBook.loading")}
              </p>
            </div>
          ) : folders.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center">
              <div className="w-20 h-20 bg-muted/30 rounded-full flex items-center justify-center mb-4 border border-dashed border-muted-foreground/20">
                <Target className="w-10 h-10 text-muted-foreground/40" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">
                {selectedClass
                  ? t("grading.errorBook.noRecordsClass")
                  : t("grading.start.selectClassFirst")}
              </h3>
              <p className="text-sm text-muted-foreground max-w-sm">
                {selectedClass
                  ? t("grading.errorBook.noRecordsHintClass")
                  : t("grading.errorBook.noRecordsHintNoClass")}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-0 divide-y md:divide-y-0 md:gap-4 p-4">
              {folders.map((folder) => {
                return (
                  <div
                    key={folder.name}
                    role="button"
                    tabIndex={0}
                    aria-label={t("grading.errorBook.openErrorBook", {
                      name: displayFolderName(folder.name),
                    })}
                    onClick={() => handleSelectFolder(folder.name)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleSelectFolder(folder.name);
                      }
                    }}
                    className="group flex flex-col p-5 rounded-xl border border-border/40 bg-card hover:bg-accent/30 hover:border-primary/30 transition-all duration-300 cursor-pointer hover:shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 group-hover:bg-primary/20 transition-colors">
                          <FileText className="w-5 h-5 text-primary" />
                        </div>
                        <div className="min-w-0">
                          <h4
                            className="text-base font-semibold text-foreground truncate group-hover:text-primary transition-colors"
                            title={displayFolderName(folder.name)}
                          >
                            {displayFolderName(folder.name)}
                          </h4>
                          <div className="flex items-center gap-2 text-xs mt-1 min-h-[1.125rem]">
                            {folder.stats_error ? (
                              <span className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 bg-destructive/10 text-destructive border border-destructive/20">
                                <AlertCircle className="w-3 h-3" />
                                {t("home.errorBook.statsFailed")}
                              </span>
                            ) : folder.student_count === 0 ? (
                              <span className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 bg-muted text-muted-foreground border border-border/40">
                                <FileText className="w-3 h-3" />
                                {t("home.errorBook.noWrongQuestions")}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </div>
                      <ChevronRight className="w-5 h-5 text-muted-foreground/30 group-hover:text-primary/70 transition-colors shrink-0" />
                    </div>

                    <div className="grid grid-cols-3 gap-2 mt-auto pt-4 border-t border-border/40">
                      <div className="flex flex-col">
                        <span className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                          <Users className="w-3 h-3" />{" "}
                          {t("grading.errorBook.participants")}
                        </span>
                        <span className="text-sm font-medium">
                          {t("grading.errorBook.participantCount", {
                            count: folder.student_count,
                          })}
                        </span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                          <FileText className="w-3 h-3" />{" "}
                          {t("grading.errorBook.questionsCollected")}
                        </span>
                        <span className="text-sm font-medium text-muted-foreground">
                          {t("grading.errorBook.questionCount", {
                            count: folder.question_count,
                          })}
                        </span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                          <BarChart3 className="w-3 h-3" />{" "}
                          {t("grading.errorBook.avgErrorRate")}
                        </span>
                        <span className="text-sm font-medium text-orange-500">
                          {folder.error_rate.toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
