import { useState } from "react";
import { toast } from "sonner";
import { Download, Loader2, Pencil, Search, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  Dialog,
  DialogContent,
  DialogDescription,
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
import { useLocale } from "@/contexts/LocaleContext";
import {
  correctRightsData,
  deleteRightsData,
  exportRightsData,
  getRightsData,
  type RightsDataResponse,
} from "@/services/complianceApi";

// 可更正字段白名单（与后端 app/routers/admin_rights.py CORRECTABLE_FIELDS 对齐，
// 仅联系方式类字段可更正；成绩/画像维度等敏感核心字段走删除匿名化）。
const CORRECTABLE_FIELDS = [
  "phone",
  "parent_phone",
  "address",
  "parent_name",
  "notes",
] as const;

function SummaryTile({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p
        className="text-xl font-bold text-foreground truncate"
        title={String(value)}
      >
        {value}
      </p>
      <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
    </div>
  );
}

function consentVariant(
  status: string,
): "default" | "secondary" | "destructive" {
  switch (status) {
    case "granted":
      return "default";
    case "withdrawn":
      return "destructive";
    default:
      return "secondary";
  }
}

function consentLabel(status: string, t: (key: string) => string): string {
  switch (status) {
    case "granted":
      return t("admin.compliance.consent.granted");
    case "withdrawn":
      return t("admin.compliance.consent.withdrawn");
    case "not_required":
      return t("admin.compliance.consent.notRequired");
    default:
      return t("admin.compliance.consent.unknown");
  }
}

export function AdminRightsPage() {
  const { t } = useLocale();
  const [studentId, setStudentId] = useState("");
  const [data, setData] = useState<RightsDataResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  // 更正弹窗
  const [correctOpen, setCorrectOpen] = useState(false);
  const [correctField, setCorrectField] = useState("");
  const [correctValue, setCorrectValue] = useState("");
  const [correcting, setCorrecting] = useState(false);

  // 删除确认
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const fieldOptions = CORRECTABLE_FIELDS;

  const handleSearch = async () => {
    const id = studentId.trim();
    if (!id) {
      toast.error(t("admin.rights.search.required"));
      return;
    }
    setLoading(true);
    try {
      const result = await getRightsData(id);
      setData(result);
      setCorrectOpen(false);
      setDeleteOpen(false);
      setConfirmChecked(false);
    } catch (e) {
      setData(null);
      toast.error(
        e instanceof Error ? e.message : t("admin.rights.search.notFound"),
      );
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    if (!data) return;
    setExporting(true);
    try {
      await exportRightsData(data.student.id);
      toast.success(t("admin.rights.actions.exported"));
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : t("admin.rights.search.loadFailed"),
      );
    } finally {
      setExporting(false);
    }
  };

  const handleCorrect = async () => {
    if (!data) return;
    if (!correctField || !correctValue.trim()) {
      toast.error(t("admin.rights.correct.required"));
      return;
    }
    setCorrecting(true);
    try {
      await correctRightsData({
        student_id: data.student.id,
        field: correctField,
        value: correctValue.trim(),
      });
      toast.success(t("admin.rights.correct.success"));
      setCorrectOpen(false);
      setCorrectField("");
      setCorrectValue("");
      const refreshed = await getRightsData(data.student.id);
      setData(refreshed);
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : t("admin.rights.correct.failed"),
      );
    } finally {
      setCorrecting(false);
    }
  };

  const handleDelete = async () => {
    if (!data || !confirmChecked) return;
    setDeleting(true);
    try {
      await deleteRightsData(data.student.id);
      toast.success(t("admin.rights.delete.success"));
      setDeleteOpen(false);
      setData(null);
      setStudentId("");
      setConfirmChecked(false);
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : t("admin.rights.delete.failed"),
      );
    } finally {
      setDeleting(false);
    }
  };

  const openCorrect = () => {
    setCorrectField("");
    setCorrectValue("");
    setCorrectOpen(true);
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-foreground">
          {t("admin.rights.title")}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          {t("admin.rights.description")}
        </p>
      </div>

      {/* 搜索学生 */}
      <Card>
        <CardContent className="p-5">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">
                {t("admin.rights.search.label")}
              </Label>
              <Input
                className="h-9 w-64"
                value={studentId}
                onChange={(e) => setStudentId(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleSearch();
                }}
                placeholder={t("admin.rights.search.placeholder")}
              />
            </div>
            <Button size="sm" onClick={handleSearch} disabled={loading}>
              {loading ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <Search className="w-4 h-4 mr-1" />
              )}
              {t("admin.rights.search.button")}
            </Button>
          </div>
        </CardContent>
      </Card>

      {data ? (
        <>
          {/* 个人信息汇总 */}
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <CardTitle className="text-base">
                {t("admin.rights.summary.title")}
              </CardTitle>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs text-muted-foreground">
                  {t("admin.rights.summary.consent")}
                </span>
                <Badge variant={consentVariant(data.consent_status)}>
                  {consentLabel(data.consent_status, t)}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                <SummaryTile
                  label={t("admin.rights.summary.name")}
                  value={data.student.name}
                />
                <SummaryTile
                  label={t("admin.rights.summary.className")}
                  value={data.student.class_name}
                />
                <SummaryTile
                  label={t("admin.rights.summary.profileDims")}
                  value={Object.keys(data.profile ?? {}).length}
                />
                <SummaryTile
                  label={t("admin.rights.summary.growthCount")}
                  value={data.growth_count}
                />
                <SummaryTile
                  label={t("admin.rights.summary.archiveCount")}
                  value={data.archive_count}
                />
                <SummaryTile
                  label={t("admin.rights.summary.scoresCount")}
                  value={data.scores_count}
                />
              </div>
            </CardContent>
          </Card>

          {/* 画像维度详情 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                {t("admin.rights.profile.title")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {Object.keys(data.profile ?? {}).length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  {t("admin.rights.profile.empty")}
                </p>
              ) : (
                <div className="rounded-lg border border-border overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("admin.rights.profile.field")}</TableHead>
                        <TableHead>{t("admin.rights.profile.value")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {Object.entries(data.profile).map(([k, v]) => (
                        <TableRow key={k}>
                          <TableCell className="font-mono text-xs">
                            {k}
                          </TableCell>
                          <TableCell className="text-sm break-all">
                            {typeof v === "object" && v !== null
                              ? JSON.stringify(v)
                              : String(v ?? "—")}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 行权操作 */}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleExport}
              disabled={exporting}
            >
              {exporting ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <Download className="w-4 h-4 mr-1" />
              )}
              {t("admin.rights.actions.export")}
            </Button>
            <Button size="sm" variant="outline" onClick={openCorrect}>
              <Pencil className="w-4 h-4 mr-1" />
              {t("admin.rights.actions.correct")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-destructive hover:text-destructive"
              onClick={() => {
                setConfirmChecked(false);
                setDeleteOpen(true);
              }}
            >
              <Trash2 className="w-4 h-4 mr-1" />
              {t("admin.rights.actions.delete")}
            </Button>
          </div>
        </>
      ) : (
        !loading && (
          <p className="text-sm text-muted-foreground py-8 text-center">
            {t("admin.rights.search.notFound")}
          </p>
        )
      )}

      {/* 更正弹窗 */}
      <Dialog open={correctOpen} onOpenChange={setCorrectOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("admin.rights.correct.title")}</DialogTitle>
            <DialogDescription>
              {t("admin.rights.correct.description")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="correct-field">
                {t("admin.rights.correct.field")}
              </Label>
              <Select value={correctField} onValueChange={setCorrectField}>
                <SelectTrigger id="correct-field" className="w-full">
                  <SelectValue
                    placeholder={t("admin.rights.correct.fieldPlaceholder")}
                  />
                </SelectTrigger>
                <SelectContent>
                  {fieldOptions.length === 0 ? (
                    <SelectItem value="__none__" disabled>
                      {t("admin.rights.correct.emptyFields")}
                    </SelectItem>
                  ) : (
                    fieldOptions.map((f) => (
                      <SelectItem key={f} value={f}>
                        {t(`admin.rights.correct.field.${f}`)}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="correct-value">
                {t("admin.rights.correct.value")}
              </Label>
              <Input
                id="correct-value"
                value={correctValue}
                onChange={(e) => setCorrectValue(e.target.value)}
                placeholder={t("admin.rights.correct.valuePlaceholder")}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCorrectOpen(false)}>
              {t("admin.common.cancel")}
            </Button>
            <Button onClick={handleCorrect} disabled={correcting}>
              {correcting ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Pencil className="w-4 h-4 mr-2" />
              )}
              {t("admin.rights.correct.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认 */}
      <AlertDialog
        open={deleteOpen}
        onOpenChange={(o) => !o && setDeleteOpen(false)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("admin.rights.delete.title")}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("admin.rights.delete.description")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <Checkbox
              checked={confirmChecked}
              onCheckedChange={(c) => setConfirmChecked(Boolean(c))}
            />
            <span>{t("admin.rights.delete.confirmCheck")}</span>
          </label>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("admin.common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              disabled={!confirmChecked || deleting}
              onClick={(e) => {
                e.preventDefault();
                void handleDelete();
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : null}
              {t("admin.rights.delete.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
