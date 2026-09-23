import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Trophy, Plus, Loader2 } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Badge } from "@/components/ui/badge";
import {
  listReadingRecords,
  createReadingRecord,
  readingLeaderboard,
} from "@/services/studentOpsApi";
import { StudentPicker } from "@/components/student-ops/shared/StudentPicker";
import { Pagination } from "@/components/student-ops/shared/Pagination";
import { EmptyState } from "@/components/student-ops/shared/EmptyState";
import { LoadingRow, ErrorBox } from "./campusCommon";

/* ═══════════ 阅读打卡 ═══════════ */
export function ReadingTab({ classId }: { classId: string }) {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [period, setPeriod] = useState("month");
  const [createOpen, setCreateOpen] = useState(false);

  const recordsQuery = useQuery({
    queryKey: ["so-reading", classId, page],
    queryFn: () =>
      listReadingRecords({ classId: classId || undefined, page, pageSize: 20 }),
  });

  const boardQuery = useQuery({
    queryKey: ["so-reading-board", period, classId],
    queryFn: () =>
      readingLeaderboard({ period, classId: classId || undefined, limit: 10 }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["so-reading"] });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Trophy className="h-4 w-4 text-amber-500" />
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-[120px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="week">
                {t("studentOps.campus.periodWeek")}
              </SelectItem>
              <SelectItem value="month">
                {t("studentOps.campus.periodMonth")}
              </SelectItem>
              <SelectItem value="term">
                {t("studentOps.campus.periodTerm")}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button
          size="sm"
          onClick={() => setCreateOpen(true)}
          disabled={!classId}
        >
          <Plus className="h-4 w-4 mr-1" />{" "}
          {t("studentOps.campus.readingCreate")}
        </Button>
      </div>

      {boardQuery.data && boardQuery.data.leaderboard.length > 0 && (
        <Card>
          <CardHeader className="pb-2 text-sm font-medium">
            {t("studentOps.campus.leaderboard")} · {boardQuery.data.startDate} ~{" "}
            {boardQuery.data.endDate}
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableBody>
                {boardQuery.data.leaderboard.map((it) => (
                  <TableRow key={it.studentId}>
                    <TableCell className="w-14">
                      {it.rank <= 3 ? (
                        <Badge
                          className={
                            it.rank === 1
                              ? "bg-amber-100 text-amber-700 border-0"
                              : it.rank === 2
                                ? "bg-slate-200 text-slate-700 border-0"
                                : "bg-orange-100 text-orange-700 border-0"
                          }
                        >
                          {it.rank}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">{it.rank}</span>
                      )}
                    </TableCell>
                    <TableCell className="font-medium">
                      {it.studentName}
                    </TableCell>
                    <TableCell>{it.className}</TableCell>
                    <TableCell>
                      {t("studentOps.campus.totalPages")} {it.totalPages}
                    </TableCell>
                    <TableCell>
                      {t("studentOps.campus.totalMinutes")} {it.totalMinutes}
                    </TableCell>
                    <TableCell className="text-right">
                      {t("studentOps.campus.booksCount")} {it.booksCount}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          {recordsQuery.isLoading ? (
            <LoadingRow />
          ) : recordsQuery.isError ? (
            <ErrorBox />
          ) : recordsQuery.data?.items.length === 0 ? (
            <EmptyState title={t("studentOps.campus.noReading")} />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("studentOps.practice.student")}</TableHead>
                    <TableHead>{t("studentOps.campus.bookTitle")}</TableHead>
                    <TableHead>{t("studentOps.campus.pagesRead")}</TableHead>
                    <TableHead>
                      {t("studentOps.campus.readingMinutes")}
                    </TableHead>
                    <TableHead>{t("studentOps.campus.readingDate")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recordsQuery.data?.items.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="font-medium">
                        {r.studentName}
                      </TableCell>
                      <TableCell>{r.bookTitle}</TableCell>
                      <TableCell>{r.pagesRead}</TableCell>
                      <TableCell>{r.readingMinutes}</TableCell>
                      <TableCell>{r.readingDate}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="p-3">
                <Pagination
                  page={recordsQuery.data?.page || 1}
                  pageSize={recordsQuery.data?.pageSize || 20}
                  total={recordsQuery.data?.total || 0}
                  onPageChange={setPage}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <ReadingFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        classId={classId}
        onSaved={invalidate}
      />
    </div>
  );
}

export function ReadingFormDialog({
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
  const [pagesRead, setPagesRead] = useState(0);
  const [readingMinutes, setReadingMinutes] = useState(0);
  const [readingDate, setReadingDate] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );

  useEffect(() => {
    if (open) {
      setStudentId("");
      setBookTitle("");
      setPagesRead(0);
      setReadingMinutes(0);
      setReadingDate(new Date().toISOString().slice(0, 10));
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: () =>
      createReadingRecord({
        studentId,
        bookTitle: bookTitle.trim(),
        pagesRead,
        readingMinutes,
        readingDate,
      }),
    onSuccess: () => {
      toast.success(t("studentOps.campus.readingSuccess"));
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
          <DialogTitle>{t("studentOps.campus.readingCreate")}</DialogTitle>
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
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>{t("studentOps.campus.pagesRead")}</Label>
              <Input
                type="number"
                min={0}
                value={pagesRead}
                onChange={(e) => setPagesRead(Number(e.target.value))}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("studentOps.campus.readingMinutes")}</Label>
              <Input
                type="number"
                min={0}
                value={readingMinutes}
                onChange={(e) => setReadingMinutes(Number(e.target.value))}
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label>{t("studentOps.campus.readingDate")}</Label>
            <Input
              type="date"
              value={readingDate}
              onChange={(e) => setReadingDate(e.target.value)}
            />
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
