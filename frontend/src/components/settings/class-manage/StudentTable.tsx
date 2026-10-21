import { useState, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Search,
  Plus,
  RefreshCw,
  Download,
  Pencil,
  ChevronLeft,
  ChevronRight,
  MoreHorizontal,
  Trash2,
} from "lucide-react";
import { useCreateStudent, useClearStudents } from "@/hooks/useStudents";
import { useQueryClient } from "@tanstack/react-query";
import { deleteStudent as deleteStudentApi } from "@/services/api";
import type { StudentInfo } from "@/types/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
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
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { useLocale } from "@/contexts/LocaleContext";
import {
  translateGender,
  translateStudentStatus,
  translateTierLabel,
} from "@/i18n";

interface StudentTableProps {
  classId: string;
  students: StudentInfo[];
  className: string;
  selectedStudentId: string | null;
  onSelectStudent: (id: string) => void;
}

const PAGE_SIZE = 9;

const tierColors: Record<string, string> = {
  A: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  B: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  C: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

const statusColors: Record<string, string> = {
  正常: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  预警: "bg-destructive/10 text-destructive",
  转出: "bg-muted text-muted-foreground",
  休学: "bg-muted text-muted-foreground",
};

const STATUS_FILTER_VALUES = ["正常", "预警"] as const;

export function StudentTable({
  classId,
  students,
  className,
  selectedStudentId,
  onSelectStudent,
}: StudentTableProps) {
  const { t, locale } = useLocale();
  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [page, setPage] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [newNumber, setNewNumber] = useState("");
  const [newName, setNewName] = useState("");
  const [newGender, setNewGender] = useState<"男" | "女">("男");

  const [deleteMode, setDeleteMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);

  const createStudent = useCreateStudent();
  const clearStudents = useClearStudents();
  const queryClient = useQueryClient();

  const filtered = useMemo(() => {
    const list = students.filter((s) => {
      const num = s.student_number || "";
      const name = s.name || "";
      if (search && !name.includes(search) && !num.includes(search))
        return false;
      if (tierFilter !== "all" && (s.tier || "B") !== tierFilter) return false;
      if (statusFilter !== "all" && (s.status || "正常") !== statusFilter)
        return false;
      return true;
    });

    return list.sort((a, b) => {
      const numA = a.student_number || "";
      const numB = b.student_number || "";

      if (!numA && !numB) return 0;
      if (!numA) return 1;
      if (!numB) return -1;

      return numA.localeCompare(numB, undefined, {
        numeric: true,
        sensitivity: "base",
      });
    });
  }, [students, search, tierFilter, statusFilter]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const toggleSelectAll = () => {
    if (selectedIds.size === paged.length && paged.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(paged.map((s) => s.id)));
    }
  };

  const toggleSelect = (id: string) => {
    const newSet = new Set(selectedIds);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedIds(newSet);
  };

  const allSelected = paged.length > 0 && selectedIds.size === paged.length;

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;

    let succeeded = 0;
    let failed = 0;
    let firstError: string | null = null;

    for (const id of selectedIds) {
      try {
        await deleteStudentApi(id);
        succeeded += 1;
      } catch (e) {
        failed += 1;
        const msg = e instanceof Error ? e.message : String(e);
        if (msg && !firstError) firstError = msg;
        console.error("Delete failed for student", id, e);
      }
    }

    // 批量删除完成后只刷新一次并聚合提示，避免逐条触发 toast 刷屏
    queryClient.invalidateQueries({ queryKey: ["students", classId] });
    queryClient.invalidateQueries({ queryKey: ["classes"] });

    if (succeeded > 0) {
      toast.success(
        t("settingsClass.table.toast.deleted", { count: succeeded }),
      );
    }
    if (failed > 0) {
      toast.error(
        firstError ||
          t("settingsClass.table.toast.deleteFailed", { count: failed }),
      );
    }

    setConfirmDeleteOpen(false);
    setDeleteMode(false);
    setSelectedIds(new Set());
    if (paged.length === selectedIds.size && page > 0) {
      setPage(page - 1);
    }
  };

  const handleClearAll = async () => {
    try {
      await clearStudents.mutateAsync(classId);
      setConfirmClearOpen(false);
      setDeleteMode(false);
      setSelectedIds(new Set());
      setPage(0);
    } catch (e) {
      console.error("Clear failed", e);
      toast.error(
        e instanceof Error && e.message
          ? e.message
          : t("settingsClass.table.toast.clearFailed"),
      );
    }
  };

  return (
    <div className="rounded-2xl border border-border bg-card p-5 flex flex-col h-[685px]">
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-foreground truncate">
            {t("settingsClass.table.title")}
          </h3>
          <p className="text-sm text-muted-foreground mt-0.5 truncate">
            {t("settingsClass.table.classCount", {
              className,
              count: filtered.length,
            })}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            size="sm"
            variant="outline"
            className="h-9 text-sm gap-1.5"
            onClick={() => setCreateOpen(true)}
          >
            <Plus className="w-4 h-4" />
            {t("settingsClass.table.add")}
          </Button>
          {deleteMode ? (
            <>
              <Button
                size="sm"
                variant="destructive"
                className="h-9 text-sm gap-1.5"
                onClick={() => setConfirmDeleteOpen(true)}
                disabled={selectedIds.size === 0}
              >
                {t("settingsClass.table.confirmDelete", {
                  count: selectedIds.size,
                })}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                className="h-9 text-sm gap-1.5 bg-red-100 text-red-600 hover:bg-red-200 dark:bg-red-900/30 dark:hover:bg-red-900/50"
                onClick={() => setConfirmClearOpen(true)}
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t("settingsClass.table.deleteAll")}
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="h-9 text-sm gap-1.5 text-destructive hover:text-destructive hover:bg-destructive/10"
              onClick={() => setDeleteMode(true)}
            >
              {t("common.delete")}
            </Button>
          )}
          {deleteMode && (
            <Button
              size="sm"
              variant="ghost"
              className="h-9 text-sm"
              onClick={() => {
                setDeleteMode(false);
                setSelectedIds(new Set());
              }}
            >
              {t("common.cancel")}
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            placeholder={t("settingsClass.table.searchPlaceholder")}
            className="h-9 pl-8 text-sm"
          />
        </div>
        <Select
          value={tierFilter}
          onValueChange={(v) => {
            setTierFilter(v);
            setPage(0);
          }}
        >
          <SelectTrigger className="h-9 w-[110px] text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">
              {t("settingsClass.table.allTiers")}
            </SelectItem>
            <SelectItem value="A">{t("settingsClass.table.tierA")}</SelectItem>
            <SelectItem value="B">{t("settingsClass.table.tierB")}</SelectItem>
            <SelectItem value="C">{t("settingsClass.table.tierC")}</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={statusFilter}
          onValueChange={(v) => {
            setStatusFilter(v);
            setPage(0);
          }}
        >
          <SelectTrigger className="h-9 w-[110px] text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">
              {t("settingsClass.table.allStatus")}
            </SelectItem>
            {STATUS_FILTER_VALUES.map((status) => (
              <SelectItem key={status} value={status}>
                {translateStudentStatus(locale, status)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex-1 overflow-hidden rounded-xl border border-border flex flex-col min-h-0">
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-sm table-fixed min-w-[500px]">
            <thead>
              <tr className="border-b border-border text-muted-foreground bg-muted/40 sticky top-0 z-10">
                {deleteMode && (
                  <th className="text-left py-2 px-3 font-medium w-[40px]">
                    <div
                      role="checkbox"
                      aria-checked={allSelected}
                      aria-label={t("common.selectAll")}
                      tabIndex={0}
                      className={`w-4 h-4 rounded-full border border-primary/50 cursor-pointer flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${allSelected ? "bg-primary border-primary" : "bg-transparent"}`}
                      onClick={toggleSelectAll}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggleSelectAll();
                        }
                      }}
                    >
                      {allSelected && (
                        <div className="w-2 h-2 rounded-full bg-primary-foreground" />
                      )}
                    </div>
                  </th>
                )}
                <th className="text-left py-2 px-2 font-medium w-[80px] lg:w-[100px]">
                  {t("settingsClass.table.colNumber")}
                </th>
                <th className="text-left py-2 px-2 font-medium w-[70px] lg:w-[90px]">
                  {t("settingsClass.table.colName")}
                </th>
                <th className="text-left py-2 px-2 font-medium w-[50px] lg:w-[60px]">
                  {t("settingsClass.table.colGender")}
                </th>
                <th className="text-left py-2 px-2 font-medium w-[60px] lg:w-[70px]">
                  {t("settingsClass.table.colTier")}
                </th>
                <th className="text-left py-2 px-2 font-medium w-[60px] lg:w-[70px]">
                  {t("settingsClass.table.colStatus")}
                </th>
                <th className="text-left py-2 px-2 font-medium w-[80px] lg:w-[90px]">
                  {t("settingsClass.table.colCadre")}
                </th>
                <th className="text-right py-2 px-2 font-medium w-[50px] lg:w-[60px]">
                  {t("settingsClass.table.colActions")}
                </th>
              </tr>
            </thead>
            <tbody>
              {paged.map((s) => {
                const isSelected = selectedIds.has(s.id);
                const tier = (s.tier || "B") as string;
                const status = (s.status || "正常") as string;
                return (
                  <tr
                    key={s.id}
                    role="button"
                    tabIndex={0}
                    aria-label={t("settingsClass.table.selectRow", {
                      name: s.name || s.student_number || "",
                    })}
                    onClick={() =>
                      deleteMode ? toggleSelect(s.id) : onSelectStudent(s.id)
                    }
                    onKeyDown={(e) => {
                      if (e.target !== e.currentTarget) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        if (deleteMode) toggleSelect(s.id);
                        else onSelectStudent(s.id);
                      }
                    }}
                    className={`border-b border-border/50 cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset ${
                      deleteMode && isSelected
                        ? "bg-primary/10"
                        : selectedStudentId === s.id
                          ? "bg-primary/5"
                          : "hover:bg-muted/50"
                    }`}
                  >
                    {deleteMode && (
                      <td className="py-2.5 px-3">
                        <div
                          className={`w-4 h-4 rounded-full border cursor-pointer flex items-center justify-center transition-colors ${isSelected ? "bg-primary border-primary" : "border-primary/50 bg-transparent"}`}
                        >
                          {isSelected && (
                            <div className="w-2 h-2 rounded-full bg-primary-foreground" />
                          )}
                        </div>
                      </td>
                    )}
                    <td
                      className="py-2.5 px-2 font-mono text-muted-foreground truncate"
                      title={s.student_number || ""}
                    >
                      {s.student_number}
                    </td>
                    <td
                      className="py-2.5 px-2 font-semibold text-foreground truncate"
                      title={s.name}
                    >
                      {s.name}
                    </td>
                    <td className="py-2.5 px-2 truncate">
                      {s.gender ? translateGender(locale, s.gender) : "-"}
                    </td>
                    <td className="py-2.5 px-2 truncate">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${tierColors[tier]}`}
                      >
                        {translateTierLabel(locale, tier)}
                      </span>
                    </td>
                    <td className="py-2.5 px-2 truncate">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[status]}`}
                      >
                        {translateStudentStatus(locale, status)}
                      </span>
                    </td>
                    <td
                      className="py-2.5 px-2 truncate"
                      title={s.cadre_role || ""}
                    >
                      {s.cadre_role ? (
                        <Badge
                          variant="secondary"
                          className="text-xs truncate max-w-full"
                        >
                          {s.cadre_role}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="py-2.5 px-2 text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectStudent(s.id);
                        }}
                        disabled={deleteMode}
                        aria-label={t("common.edit")}
                      >
                        <Pencil className="w-3 h-3" />
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex items-center justify-between mt-3 pt-3 border-t border-border shrink-0">
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0 || totalPages === 0}
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </Button>

          <div className="flex items-center gap-1">
            {Array.from({ length: totalPages }, (_, i) => {
              if (totalPages <= 15) {
                return (
                  <Button
                    key={i}
                    size="sm"
                    variant={page === i ? "default" : "outline"}
                    className="h-7 w-7 p-0 text-sm"
                    onClick={() => setPage(i)}
                  >
                    {i + 1}
                  </Button>
                );
              }

              if (
                i === 0 ||
                i === totalPages - 1 ||
                (i >= page - 1 && i <= page + 1)
              ) {
                return (
                  <Button
                    key={i}
                    size="sm"
                    variant={page === i ? "default" : "outline"}
                    className="h-7 w-7 p-0 text-sm"
                    onClick={() => setPage(i)}
                  >
                    {i + 1}
                  </Button>
                );
              }
              if (i === page - 2 || i === page + 2) {
                return (
                  <div
                    key={i}
                    className="h-7 w-7 flex items-center justify-center text-muted-foreground"
                  >
                    <MoreHorizontal className="w-3 h-3" />
                  </div>
                );
              }
              return null;
            })}
          </div>

          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1 || totalPages === 0}
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </Button>
        </div>
        <span className="text-xs text-muted-foreground">
          {t("settingsClass.table.totalRows", { count: filtered.length })}
        </span>
      </div>

      <div className="flex items-center gap-2 mt-3 shrink-0">
        <Button
          size="sm"
          variant="outline"
          className="h-8 text-sm gap-1.5"
          disabled
        >
          <RefreshCw className="w-4 h-4" />
          {t("settingsClass.syncDingTalk")}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-8 text-sm gap-1.5 ml-auto"
          disabled
        >
          <Download className="w-4 h-4" />
          {t("settingsClass.table.downloadTemplate")}
        </Button>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>{t("settingsClass.table.addStudent")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>{t("settingsClass.table.colNumber")}</Label>
              <Input
                value={newNumber}
                onChange={(e) => setNewNumber(e.target.value)}
                placeholder={t("settingsClass.table.optional")}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("settingsClass.table.colName")}</Label>
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder={t("settingsClass.table.required")}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("settingsClass.table.colGender")}</Label>
              <Select
                value={newGender}
                onValueChange={(v) => setNewGender(v as "男" | "女")}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="男">
                    {translateGender(locale, "男")}
                  </SelectItem>
                  <SelectItem value="女">
                    {translateGender(locale, "女")}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={async () => {
                if (!newName.trim()) {
                  toast.error(t("settingsClass.table.toast.nameRequired"));
                  return;
                }
                const num = newNumber.trim();
                await createStudent.mutateAsync({
                  class_id: classId,
                  ...(num ? { student_number: num } : {}),
                  name: newName.trim(),
                  gender: newGender,
                });
                setCreateOpen(false);
                setNewNumber("");
                setNewName("");
                setNewGender("男");
              }}
              disabled={createStudent.isPending}
            >
              {createStudent.isPending
                ? t("settingsClass.table.creating")
                : t("settingsClass.table.create")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("settingsClass.table.confirmDeleteTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("settingsClass.table.confirmDeleteDesc", {
                count: selectedIds.size,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleBatchDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("settingsClass.table.confirmDeleteTitle")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmClearOpen} onOpenChange={setConfirmClearOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-destructive flex items-center gap-2">
              <Trash2 className="w-5 h-5" />
              {t("settingsClass.table.clearClassTitle")}
            </AlertDialogTitle>
            <AlertDialogDescription className="text-base pt-2">
              {t("settingsClass.table.clearClassDesc", {
                className,
                count: students.length,
              })}
              <br />
              <span className="text-destructive mt-1 inline-block text-sm">
                {t("settingsClass.table.clearClassWarning")}
              </span>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleClearAll}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={clearStudents.isPending}
            >
              {clearStudents.isPending
                ? t("settingsClass.table.clearing")
                : t("settingsClass.table.confirmClearAll")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
