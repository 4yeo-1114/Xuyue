import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { useClasses } from "@/hooks/useClasses";
import { useDeleteExam } from "@/hooks/useExams";
import { listExams } from "@/services/api";
import type { ExamRecord } from "@/services/api";
import { translateSubjectName } from "@/i18n";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
import { ClipboardList, Inbox, RefreshCw, Trash2 } from "lucide-react";

/** 全校考试行：ExamRecord + 所在班级名称 */
interface ExamRow extends ExamRecord {
  className: string;
}

const ALL_CLASSES = "__all__";
const ALL_SUBJECTS = "__all__";

/** 可筛选学科（与班级成绩管理页一致） */
const subjectOptions = [
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

export function ExamManagePage() {
  const { t, locale } = useLocale();
  const { data: classes = [], isLoading: classesLoading } = useClasses();

  const [selectedClassId, setSelectedClassId] = useState<string>(ALL_CLASSES);
  const [filterSubject, setFilterSubject] = useState<string>(ALL_SUBJECTS);
  const [deleting, setDeleting] = useState<ExamRow | null>(null);

  const classesKey = useMemo(
    () =>
      classes
        .map((c) => c.id)
        .sort()
        .join(","),
    [classes],
  );

  // 全校考试列表：逐个班级拉取考试记录后合并（Promise.allSettled，
  // 单个班级失败不影响其余班级数据）。后端 /exams 必须传 class_id，
  // 无全校接口，故在班级维度聚合。
  const {
    data: rows = [],
    isLoading: examsLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["school-exam-roster", classesKey, filterSubject],
    queryFn: async () => {
      const settled = await Promise.allSettled(
        classes.map(async (c) => {
          const records = await listExams(
            c.id,
            filterSubject === ALL_SUBJECTS ? undefined : filterSubject,
          );
          return records.map((r): ExamRow => ({ ...r, className: c.name }));
        }),
      );
      return settled.flatMap((r) => (r.status === "fulfilled" ? r.value : []));
    },
    enabled: classes.length > 0,
    staleTime: 30_000,
  });

  const deleteExam = useDeleteExam();

  const filtered = useMemo(
    () =>
      selectedClassId === ALL_CLASSES
        ? rows
        : rows.filter((r) => r.class_id === selectedClassId),
    [rows, selectedClassId],
  );

  const selectedClass = classes.find((c) => c.id === selectedClassId) || null;

  const isLoading = classesLoading || (classes.length > 0 && examsLoading);

  const handleDelete = async (row: ExamRow) => {
    setDeleting(null);
    await deleteExam.mutateAsync({ id: row.id, class_id: row.class_id });
    // useDeleteExam 只失效「按班级」的查询键，全校聚合需手动刷新
    refetch();
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 pb-10">
      {/* 页头 */}
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <ClipboardList className="w-6 h-6 text-primary" />
            {t("examManage.title")}
          </h2>
          <p className="text-muted-foreground mt-1">
            {t("examManage.subtitle")}
          </p>
        </div>
        <Badge variant="secondary" className="px-3 py-1">
          {t("examManage.count", { count: filtered.length })}
        </Badge>
      </div>

      {/* 筛选区 */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={selectedClassId} onValueChange={setSelectedClassId}>
          <SelectTrigger className="w-[220px]">
            <SelectValue
              placeholder={t("examManage.filter.classPlaceholder")}
            />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_CLASSES}>
              {t("examManage.filter.allClasses")}
            </SelectItem>
            {classes.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={filterSubject} onValueChange={setFilterSubject}>
          <SelectTrigger className="w-[220px]">
            <SelectValue
              placeholder={t("examManage.filter.subjectPlaceholder")}
            />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_SUBJECTS}>
              {t("examManage.filter.allSubjects")}
            </SelectItem>
            {subjectOptions.map((s) => (
              <SelectItem key={s} value={s}>
                {translateSubjectName(locale, s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* 内容区 */}
      {isLoading ? (
        <Card>
          <CardContent className="p-6 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : classes.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            <Inbox className="w-8 h-8 mx-auto mb-2 text-muted-foreground/40" />
            <p className="text-sm font-medium">{t("examManage.noClasses")}</p>
            <p className="text-xs mt-1">{t("examManage.noClassesHint")}</p>
          </CardContent>
        </Card>
      ) : isError ? (
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            <Inbox className="w-8 h-8 mx-auto mb-2 text-muted-foreground/40" />
            <p className="text-sm">{t("examManage.error")}</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3 gap-1.5"
              onClick={() => refetch()}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              {t("examManage.errorRetry")}
            </Button>
          </CardContent>
        </Card>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            <Inbox className="w-8 h-8 mx-auto mb-2 text-muted-foreground/40" />
            <p className="text-sm">{t("examManage.empty")}</p>
            <p className="text-xs mt-1">{t("examManage.emptyHint")}</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold">
              {selectedClass
                ? selectedClass.name
                : t("examManage.filter.allClasses")}
            </CardTitle>
            <CardDescription>
              {t("examManage.count", { count: filtered.length })}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("examManage.table.name")}</TableHead>
                  <TableHead>{t("examManage.table.class")}</TableHead>
                  <TableHead>{t("examManage.table.subject")}</TableHead>
                  <TableHead>{t("examManage.table.totalScore")}</TableHead>
                  <TableHead>{t("examManage.table.examDate")}</TableHead>
                  <TableHead className="text-right">
                    {t("examManage.table.action")}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="font-medium">{row.title}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {row.className}
                    </TableCell>
                    <TableCell>
                      {translateSubjectName(locale, row.subject)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {row.total_score}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {row.exam_date}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive hover:text-destructive"
                        onClick={() => setDeleting(row)}
                        aria-label={t("examManage.delete")}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* 删除确认 */}
      <AlertDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("examManage.deleteTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("examManage.deleteConfirmDesc")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleting) handleDelete(deleting);
              }}
              disabled={deleteExam.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("examManage.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
