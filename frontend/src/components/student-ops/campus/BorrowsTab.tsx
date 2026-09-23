import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Loader2, AlertTriangle, RotateCcw } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  listBookBorrows,
  createBookBorrow,
  returnBookBorrow,
  listOverdueBookBorrows,
} from "@/services/studentOpsApi";
import { StudentPicker } from "@/components/student-ops/shared/StudentPicker";
import { StatusBadge } from "@/components/student-ops/shared/StatusBadge";
import { Pagination } from "@/components/student-ops/shared/Pagination";
import { EmptyState } from "@/components/student-ops/shared/EmptyState";
import { LoadingRow, ErrorBox } from "./campusCommon";
import { cap } from "./campusUtils";

/* ═══════════ 图书借阅 ═══════════ */
export function BorrowsTab({ classId }: { classId: string }) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"all" | "overdue">("all");
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [confirmReturn, setConfirmReturn] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["so-borrows", classId, mode, status, page],
    queryFn: () => {
      const base = { page, pageSize: 20, classId: classId || undefined };
      if (mode === "overdue") return listOverdueBookBorrows(base);
      return listBookBorrows({ ...base, status: status || undefined });
    },
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["so-borrows"] });

  const returnMutation = useMutation({
    mutationFn: (id: string) =>
      returnBookBorrow(id, {
        returnedAt: new Date().toISOString().slice(0, 10),
      }),
    onSuccess: () => {
      toast.success(t("studentOps.campus.returnSuccess"));
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Tabs
            value={mode}
            onValueChange={(v) => {
              setMode(v as "all" | "overdue");
              setPage(1);
            }}
          >
            <TabsList>
              <TabsTrigger value="all">{t("studentOps.all")}</TabsTrigger>
              <TabsTrigger value="overdue">
                <AlertTriangle className="h-3.5 w-3.5 mr-1" />
                {t("studentOps.campus.overdueList")}
              </TabsTrigger>
            </TabsList>
          </Tabs>
          {mode === "all" && (
            <Select
              value={status}
              onValueChange={(v) => {
                setStatus(v);
                setPage(1);
              }}
            >
              <SelectTrigger className="w-[140px]">
                <SelectValue
                  placeholder={t("studentOps.campus.statusBorrowed")}
                />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all">{t("studentOps.all")}</SelectItem>
                <SelectItem value="borrowed">
                  {t("studentOps.campus.statusBorrowed")}
                </SelectItem>
                <SelectItem value="returned">
                  {t("studentOps.campus.statusReturned")}
                </SelectItem>
                <SelectItem value="overdue">
                  {t("studentOps.campus.statusOverdue")}
                </SelectItem>
              </SelectContent>
            </Select>
          )}
        </div>
        <Button
          size="sm"
          onClick={() => setCreateOpen(true)}
          disabled={!classId}
        >
          <Plus className="h-4 w-4 mr-1" />{" "}
          {t("studentOps.campus.borrowCreate")}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          {query.isLoading ? (
            <LoadingRow />
          ) : query.isError ? (
            <ErrorBox />
          ) : query.data?.items.length === 0 ? (
            <EmptyState title={t("studentOps.campus.noBorrows")} />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("studentOps.campus.bookTitle")}</TableHead>
                    <TableHead>{t("studentOps.campus.bookIsbn")}</TableHead>
                    <TableHead>{t("studentOps.practice.student")}</TableHead>
                    <TableHead>{t("studentOps.campus.borrowedAt")}</TableHead>
                    <TableHead>{t("studentOps.campus.dueAt")}</TableHead>
                    <TableHead>{t("studentOps.badges.status")}</TableHead>
                    <TableHead className="text-right">
                      {t("studentOps.actions")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data?.items.map((b) => (
                    <TableRow
                      key={b.id}
                      className={
                        b.status === "overdue" ? "bg-orange-50/50" : ""
                      }
                    >
                      <TableCell className="font-medium">
                        {b.bookTitle}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {b.bookIsbn || "—"}
                      </TableCell>
                      <TableCell>{b.studentName}</TableCell>
                      <TableCell>{b.borrowedAt}</TableCell>
                      <TableCell
                        className={
                          b.status === "overdue"
                            ? "text-orange-600 font-medium"
                            : ""
                        }
                      >
                        {b.dueAt}
                      </TableCell>
                      <TableCell>
                        <StatusBadge
                          value={b.status}
                          label={t(`studentOps.campus.status${cap(b.status)}`)}
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        {b.status !== "returned" ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label={t("studentOps.campus.return")}
                            onClick={() => setConfirmReturn(b.id)}
                          >
                            <RotateCcw className="h-4 w-4 text-blue-600" />
                          </Button>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            {b.returnedAt}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="p-3">
                <Pagination
                  page={query.data?.page || 1}
                  pageSize={query.data?.pageSize || 20}
                  total={query.data?.total || 0}
                  onPageChange={setPage}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <BorrowFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        classId={classId}
        onSaved={invalidate}
      />

      <AlertDialog
        open={!!confirmReturn}
        onOpenChange={(open) => !open && setConfirmReturn(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("studentOps.campus.return")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("studentOps.campus.returnConfirm")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("studentOps.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (!confirmReturn) return;
                const targetId = confirmReturn;
                setConfirmReturn(null);
                returnMutation.mutate(targetId);
              }}
            >
              {t("studentOps.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export function BorrowFormDialog({
  open,
  onOpenChange,
  classId,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classId: string;
  onSaved: () => void;
}) {
  const { t } = useLocale();
  const [studentId, setStudentId] = useState("");
  const [bookTitle, setBookTitle] = useState("");
  const [bookIsbn, setBookIsbn] = useState("");
  const [bookAuthor, setBookAuthor] = useState("");
  const [borrowedAt, setBorrowedAt] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [dueAt, setDueAt] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 14);
    return d.toISOString().slice(0, 10);
  });

  useEffect(() => {
    if (open) {
      setStudentId("");
      setBookTitle("");
      setBookIsbn("");
      setBookAuthor("");
      setBorrowedAt(new Date().toISOString().slice(0, 10));
      const d = new Date();
      d.setDate(d.getDate() + 14);
      setDueAt(d.toISOString().slice(0, 10));
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: () =>
      createBookBorrow({
        studentId,
        bookTitle: bookTitle.trim(),
        bookIsbn: bookIsbn || null,
        bookAuthor: bookAuthor || null,
        borrowedAt,
        dueAt,
      }),
    onSuccess: () => {
      toast.success(t("studentOps.campus.borrowSuccess"));
      onSaved();
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const submit = () => {
    if (!studentId) {
      toast.error(t("studentOps.practice.requireStudent"));
      return;
    }
    if (!bookTitle.trim()) {
      toast.error(t("studentOps.required"));
      return;
    }
    mutation.mutate();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t("studentOps.campus.borrowCreate")}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label>{t("studentOps.practice.student")} *</Label>
            <StudentPicker
              classId={classId}
              value={studentId}
              onChange={setStudentId}
            />
          </div>
          <div className="grid gap-2">
            <Label>{t("studentOps.campus.bookTitle")} *</Label>
            <Input
              value={bookTitle}
              onChange={(e) => setBookTitle(e.target.value)}
              placeholder={t("studentOps.campus.bookTitlePlaceholder")}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>{t("studentOps.campus.bookIsbn")}</Label>
              <Input
                value={bookIsbn}
                onChange={(e) => setBookIsbn(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.campus.bookAuthor")}</Label>
              <Input
                value={bookAuthor}
                onChange={(e) => setBookAuthor(e.target.value)}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>{t("studentOps.campus.borrowedAt")}</Label>
              <Input
                type="date"
                value={borrowedAt}
                onChange={(e) => setBorrowedAt(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.campus.dueAt")}</Label>
              <Input
                type="date"
                value={dueAt}
                onChange={(e) => setDueAt(e.target.value)}
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("studentOps.cancel")}
          </Button>
          <Button onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending && (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            )}
            {t("studentOps.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
