import { useEffect, useMemo, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { ClipboardCheck, DownloadCloud, ListChecks, Loader2 } from "lucide-react";
import { toast } from "sonner";
import {
  listTargetedTasks,
  syncTargetedTasks,
  updateTargetedTask,
  type TargetedTaskItem,
} from "./targetedTasksApi";
import { calcTaskProgress, filterTasks, type TaskFilter } from "./taskListUtils";

interface StudentOption {
  id: string;
  name: string;
  student_number?: string;
}

interface TargetedTaskListProps {
  classId: string;
  subject: string;
  students?: StudentOption[];
  selectedStudentName?: string;
  reportId?: string | null;
}

const FILTERS: TaskFilter[] = ["all", "pending", "done"];

export function TargetedTaskList({
  classId,
  subject,
  students = [],
  selectedStudentName,
  reportId,
}: TargetedTaskListProps) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [studentName, setStudentName] = useState(selectedStudentName || "");
  const [filter, setFilter] = useState<TaskFilter>("all");

  useEffect(() => {
    if (selectedStudentName) setStudentName(selectedStudentName);
  }, [selectedStudentName]);

  useEffect(() => {
    if (!studentName && students.length > 0) {
      setStudentName(selectedStudentName || students[0].name);
    }
    if (studentName && students.length > 0 && !students.some((s) => s.name === studentName)) {
      setStudentName(selectedStudentName || students[0].name);
    }
  }, [students, studentName, selectedStudentName]);

  const selectedStudent = useMemo(
    () => students.find((s) => s.name === studentName) || null,
    [students, studentName],
  );

  const queryKey = [
    "targeted-tasks",
    classId,
    subject,
    selectedStudent?.id || studentName,
  ];

  const {
    data: taskData,
    isLoading,
    isError,
  } = useQuery({
    queryKey,
    queryFn: () =>
      listTargetedTasks({
        classId,
        subject,
        studentId: selectedStudent?.id,
        studentName: selectedStudent ? undefined : studentName || undefined,
        includeDone: true,
      }),
    enabled: !!classId && !!subject && (!!selectedStudent?.id || !!studentName),
  });

  const tasks = taskData?.tasks || [];
  const progress = calcTaskProgress(tasks);
  const visibleTasks = filterTasks(tasks, filter);

  const toggleMutation = useMutation({
    mutationFn: ({ id, isDone }: { id: string; isDone: boolean }) =>
      updateTargetedTask(id, isDone),
    onMutate: async ({ id, isDone }) => {
      // 乐观更新：先改本地缓存，失败再回滚
      await queryClient.cancelQueries({ queryKey });
      const prev = queryClient.getQueryData<{
        tasks: TargetedTaskItem[];
        total: number;
        done: number;
      }>(queryKey);
      if (prev) {
        const nextTasks = prev.tasks.map((item) =>
          item.id === id
            ? { ...item, is_done: isDone, done_at: isDone ? new Date().toISOString() : null }
            : item,
        );
        queryClient.setQueryData(queryKey, {
          ...prev,
          tasks: nextTasks,
          done: nextTasks.filter((x) => x.is_done).length,
        });
      }
      return { prev };
    },
    onError: (err: any, _vars, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(queryKey, ctx.prev);
      toast.error(t("classDetail.targetedImprove.taskList.toggleFailed"), {
        description: err?.message || undefined,
      });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey });
    },
  });

  const syncMutation = useMutation({
    mutationFn: () =>
      syncTargetedTasks({
        report_id: reportId || undefined,
        class_id: classId,
        student_id: selectedStudent?.id,
        student_name: selectedStudent ? undefined : studentName || undefined,
        subject,
      }),
    onSuccess: (res) => {
      toast.success(
        t("classDetail.targetedImprove.taskList.syncSuccess", {
          created: res.created_count,
          total: res.total,
        }),
      );
      queryClient.invalidateQueries({ queryKey });
    },
    onError: (err: any) => {
      toast.error(t("classDetail.targetedImprove.taskList.syncFailed"), {
        description: err?.message || undefined,
      });
    },
  });

  const filterLabel = (key: TaskFilter) =>
    key === "all"
      ? t("classDetail.targetedImprove.taskList.filterAll")
      : key === "pending"
        ? t("classDetail.targetedImprove.taskList.filterPending")
        : t("classDetail.targetedImprove.taskList.filterDone");

  return (
    <Card className="min-w-[320px] flex-1 border-border/70 shadow-sm">
      <CardHeader className="border-b bg-emerald-50/70 pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          <ListChecks className="h-5 w-5 text-primary" />
          {t("classDetail.targetedImprove.taskList.title")}
          <Badge variant="secondary" className="text-[11px] font-normal">
            {t("classDetail.targetedImprove.taskList.progressBadge", {
              done: progress.done,
              total: progress.total,
            })}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-center gap-2">
          {students.length > 0 && (
            <Select value={studentName} onValueChange={setStudentName}>
              <SelectTrigger className="h-9 w-[160px] text-sm">
                <SelectValue
                  placeholder={t("classDetail.targetedImprove.taskList.selectStudent")}
                />
              </SelectTrigger>
              <SelectContent>
                {students.map((s) => (
                  <SelectItem key={s.id} value={s.name}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <div className="flex rounded-lg bg-muted p-0.5">
            {FILTERS.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-xs font-medium transition-all",
                  filter === key
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {filterLabel(key)}
              </button>
            ))}
          </div>
          <Button
            size="sm"
            className="ml-auto h-8 gap-1.5 text-xs"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending || !classId || !subject}
          >
            {syncMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <DownloadCloud className="h-3.5 w-3.5" />
            )}
            {t("classDetail.targetedImprove.taskList.importFromReport")}
          </Button>
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {t("classDetail.targetedImprove.taskList.progressLabel", {
                done: progress.done,
                total: progress.total,
              })}
            </span>
            <span>{progress.percent}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-2 rounded-full bg-emerald-500 transition-all"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-10 text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            {t("classDetail.targetedImprove.taskList.loading")}
          </div>
        ) : isError ? (
          <p className="rounded-lg border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground">
            {t("classDetail.targetedImprove.taskList.loadFailed")}
          </p>
        ) : visibleTasks.length === 0 ? (
          <div className="rounded-lg border border-dashed bg-muted/20 p-6 text-sm text-muted-foreground">
            {tasks.length === 0
              ? t("classDetail.targetedImprove.taskList.empty")
              : t("classDetail.targetedImprove.taskList.emptyFiltered")}
          </div>
        ) : (
          <ul className="space-y-2">
            {visibleTasks.map((task) => (
              <li
                key={task.id}
                className={cn(
                  "flex items-start gap-3 rounded-lg border border-border/60 bg-background p-3",
                  task.is_done && "opacity-70",
                )}
              >
                <Checkbox
                  id={`task-${task.id}`}
                  checked={task.is_done}
                  disabled={toggleMutation.isPending}
                  onCheckedChange={(checked) =>
                    toggleMutation.mutate({
                      id: task.id,
                      isDone: checked === true,
                    })
                  }
                  className="mt-0.5"
                />
                <div className="min-w-0 flex-1">
                  <label
                    htmlFor={`task-${task.id}`}
                    className={cn(
                      "block cursor-pointer text-sm leading-relaxed text-foreground",
                      task.is_done && "text-muted-foreground line-through",
                    )}
                  >
                    {task.task_text}
                  </label>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    {task.stage_label ? (
                      <Badge variant="outline" className="text-[10px]">
                        {task.stage_label}
                      </Badge>
                    ) : null}
                    {task.report_id ? (
                      <span className="text-[10px] text-muted-foreground">
                        {t("classDetail.targetedImprove.taskList.fromReport")}
                      </span>
                    ) : null}
                    {task.is_done && task.done_at ? (
                      <span className="text-[10px] text-muted-foreground">
                        <ClipboardCheck className="mr-0.5 inline h-3 w-3" />
                        {t("classDetail.targetedImprove.taskList.doneAt")}
                      </span>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
