import { useState, useMemo, useRef } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Loader2, FileText, CheckCircle2, UploadCloud } from "lucide-react";
import { importStudentScores, importStudentScoresExcel } from "@/services/api";
import { listFolders, getErrorBookFolderStats, getErrorBookFolderDetail } from "@/services/gradingApi";
import { toast } from "sonner";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  subject: string;
}

export function ImportScoresDialog({ open, onOpenChange, classId, subject }: Props) {
  const { t } = useLocale();

  const queryClient = useQueryClient();
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null);
  
  // Excel import state
  const [activeTab, setActiveTab] = useState<string>("grading");
  const [excelExamName, setExcelExamName] = useState("");
  const [excelFile, setExcelFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const displayFolderName = (name: string) => {
    const s = String(name || "");
    if (s.startsWith("cls_")) {
      const i = s.indexOf("__");
      if (i > 4 && i + 2 < s.length) return s.slice(i + 2);
    }
    return s;
  };

  const paperBoxName = (filename: string) => {
    const stem = String(filename || "").replace(/\.[^/.]+$/, "");
    const match = stem.match(/^(.+)_\d+$/);
    return match?.[1] || stem;
  };

  const { data: recordsData, isLoading: loadingRecords } = useQuery({
    queryKey: ["grading-records-folders", classId],
    queryFn: async () => {
      const res = await listFolders(classId);
       if (!res.ok) throw new Error(t("studentAnalysis.import.loadFailed"));
      
      const foldersWithCounts = await Promise.all(
        (res.folders || []).map(async (name) => {
          try {
            const statsRes = await getErrorBookFolderStats(name);
            if (statsRes.ok) {
              return { 
                id: name,
                title: displayFolderName(name),
                total_count: statsRes.student_count,
              };
            }
            return { id: name, title: displayFolderName(name), total_count: 0 };
          } catch {
            return { id: name, title: displayFolderName(name), total_count: 0 };
          }
        })
      );
      // Filter out empty folders
      return foldersWithCounts.filter(f => f.total_count > 0);
    },
    enabled: open && !!classId,
  });

  const records = useMemo(() => recordsData || [], [recordsData]);

  const { mutate: importScores, isPending: importing } = useMutation({
    mutationFn: async () => {
      if (!selectedRecordId) throw new Error(t("studentAnalysis.import.selectRecord"));
      const record = records.find(r => r.id === selectedRecordId);
      if (!record) throw new Error(t("studentAnalysis.import.recordMissing"));

      const scoresMap = new Map<string, number>();

      try {
        const res = await getErrorBookFolderDetail(selectedRecordId);

        if (res.ok && res.students) {
          res.students.forEach(s => {
            if (s.score_total != null) {
              const name = paperBoxName(s.filename);
              scoresMap.set(name, s.score_total);
            }
          });
        }

        if (scoresMap.size === 0) {
          throw new Error(t("studentAnalysis.import.noScores"));
        }

        const scoresPayload = Array.from(scoresMap.entries()).map(([student_name, score]) => ({
          student_name,
          score
        }));

        let class_avg: number | undefined = undefined;
        if (scoresPayload.length > 0) {
          const totalSum = scoresPayload.reduce((sum, item) => sum + item.score, 0);
          class_avg = Math.round(totalSum / scoresPayload.length);
        }

        return importStudentScores({
          class_id: classId,
          subject,
          exam_name: record.title,
          record_id: selectedRecordId,
          class_avg,
          scores: scoresPayload
        });
      } catch (err: any) {
        throw new Error(err.message || t("studentAnalysis.import.extractFailed"));
      }
    },
    onSuccess: (res) => {
      toast.success(t("studentAnalysis.import.success", { action: res.refreshed ? t("studentAnalysis.import.refreshed") : t("studentAnalysis.import.imported"), count: res.imported_count }));
      queryClient.invalidateQueries({ queryKey: ["student-analysis-list", classId, subject] });
      queryClient.invalidateQueries({ queryKey: ["student-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["student-score-history"] });
      onOpenChange(false);
      setSelectedRecordId(null);
    },
    onError: (err: any) => {
      toast.error(t("studentAnalysis.import.failed"), { description: err.message });
    }
  });

  const { mutate: importScoresExcel, isPending: importingExcel } = useMutation({
    mutationFn: async () => {
      if (!excelExamName.trim()) throw new Error(t("studentAnalysis.import.examRequired"));
      if (!excelFile) throw new Error(t("studentAnalysis.import.fileRequired"));
      return importStudentScoresExcel(classId, subject, excelExamName.trim(), excelFile);
    },
    onSuccess: (res) => {
      toast.success(t("studentAnalysis.import.success", { action: res.refreshed ? t("studentAnalysis.import.refreshed") : t("studentAnalysis.import.excelImported"), count: res.imported_count }));
      queryClient.invalidateQueries({ queryKey: ["student-analysis-list", classId, subject] });
      queryClient.invalidateQueries({ queryKey: ["student-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["student-score-history"] });
      onOpenChange(false);
      setExcelFile(null);
      setExcelExamName("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    onError: (err: any) => {
      toast.error(t("studentAnalysis.import.failed"), { description: err.message });
    }
  });

  return (
    <Dialog open={open} onOpenChange={(o) => {
      if (!o) {
        setExcelFile(null);
        setExcelExamName("");
      }
      onOpenChange(o);
    }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("studentAnalysis.import.title")}</DialogTitle>
          <DialogDescription>
            {t("studentAnalysis.import.description")}
          </DialogDescription>
        </DialogHeader>
        
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2 mb-4">
            <TabsTrigger value="grading">{t("studentAnalysis.import.gradingTab")}</TabsTrigger>
            <TabsTrigger value="excel">{t("studentAnalysis.import.excelTab")}</TabsTrigger>
          </TabsList>

          <TabsContent value="grading" className="mt-0">
            <div className="py-2">
              {loadingRecords ? (
                <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                  <Loader2 className="w-6 h-6 animate-spin mb-2" />
                  <p className="text-sm">{t("studentAnalysis.import.loading")}</p>
                </div>
              ) : records.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-muted-foreground bg-muted/20 rounded-lg border border-dashed">
                  <FileText className="w-8 h-8 opacity-20 mb-2" />
                  <p className="text-sm">{t("studentAnalysis.import.empty")}</p>
                </div>
              ) : (
                <ScrollArea className="h-[280px] pr-3">
                  <div className="space-y-2">
                    {records.map((record) => (
                      <button
                        key={record.id}
                        onClick={() => setSelectedRecordId(record.id)}
                        className={cn(
                          "w-full flex items-start justify-between p-3 rounded-lg border transition-all text-left",
                          selectedRecordId === record.id 
                            ? "bg-primary/5 border-primary shadow-sm" 
                            : "bg-card hover:bg-muted/50 border-border"
                        )}
                      >
                        <div className="flex-1 min-w-0 pr-4">
                          <p className={cn("text-sm font-medium truncate mb-1", selectedRecordId === record.id ? "text-primary" : "text-foreground")}>
                            {record.title || t("studentAnalysis.import.unnamed")}
                          </p>
                          <div className="flex items-center gap-3 text-xs text-muted-foreground">
                            <span>{t("studentAnalysis.import.paperCount", { count: record.total_count })}</span>
                          </div>
                        </div>
                        {selectedRecordId === record.id && (
                          <CheckCircle2 className="w-5 h-5 text-primary shrink-0 mt-0.5" />
                        )}
                      </button>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </div>

            <DialogFooter className="mt-4">
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={importing}>{t("studentAnalysis.import.cancel")}</Button>
              <Button onClick={() => importScores()} disabled={!selectedRecordId || importing}>
                {importing ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                {importing ? t("studentAnalysis.import.importing") : t("studentAnalysis.import.confirm")}
              </Button>
            </DialogFooter>
          </TabsContent>

          <TabsContent value="excel" className="mt-0">
            <div className="py-2 space-y-4 min-h-[280px]">
              <div className="space-y-2">
                <Label htmlFor="exam-name">{t("studentAnalysis.import.examName")}</Label>
                <Input 
                  id="exam-name" 
                  placeholder={t("studentAnalysis.import.examPlaceholder")}
                  value={excelExamName}
                  onChange={(e) => setExcelExamName(e.target.value)}
                />
              </div>
              
              <div className="space-y-2">
                <Label>{t("studentAnalysis.import.uploadSheet")}</Label>
                <div 
                  className={cn(
                    "border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center transition-colors text-center cursor-pointer",
                    excelFile ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:bg-muted/50 hover:border-primary/50"
                  )}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input 
                    type="file" 
                    ref={fileInputRef} 
                    className="hidden" 
                    accept=".xlsx,.xls"
                    onChange={(e) => {
                      if (e.target.files && e.target.files.length > 0) {
                        setExcelFile(e.target.files[0]);
                      }
                    }}
                  />
                  {excelFile ? (
                    <>
                      <FileText className="w-8 h-8 text-primary mb-2" />
                      <p className="text-sm font-medium text-primary">{excelFile.name}</p>
                      <p className="text-xs text-muted-foreground mt-1">{t("studentAnalysis.import.reselect")}</p>
                    </>
                  ) : (
                    <>
                      <UploadCloud className="w-8 h-8 text-muted-foreground mb-2" />
                      <p className="text-sm font-medium">{t("studentAnalysis.import.uploadExcel")}</p>
                      <p className="text-xs text-muted-foreground mt-1">{t("studentAnalysis.import.columnsHint")}</p>
                    </>
                  )}
                </div>
              </div>
            </div>

            <DialogFooter className="mt-4">
              <Button variant="outline" onClick={() => onOpenChange(false)} disabled={importingExcel}>{t("studentAnalysis.import.cancel")}</Button>
              <Button onClick={() => importScoresExcel()} disabled={!excelExamName.trim() || !excelFile || importingExcel}>
                {importingExcel ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                {importingExcel ? t("studentAnalysis.import.importing") : t("studentAnalysis.import.confirm")}
              </Button>
            </DialogFooter>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
