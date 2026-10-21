import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import {
  Download,
  Upload,
  Loader2,
  Database,
  Shield,
  Info,
  RefreshCw,
} from "lucide-react";
import { exportClassData, importClassData } from "@/services/gradingApi";
import { saveBlob } from "@/services/complianceApi";
import { useLocale } from "@/contexts/LocaleContext";
import {
  getDingtalkSyncStatus,
  listDingtalkDepartments,
  listDingtalkDeptUsers,
  syncDingtalkClasses,
  type DingtalkDepartment,
  type DingtalkDeptUser,
  type DingtalkSyncStatus,
} from "@/services/api";

type RecentAction = {
  id: number;
  action: string;
  result: "成功" | "失败";
  detail: string;
  time: string;
};

export function DataSyncPanel({
  classId,
  className,
}: {
  classId: string;
  className?: string;
}) {
  const { t } = useLocale();
  const { toast } = useToast();
  const importInputRef = useRef<HTMLInputElement>(null);
  const nextIdRef = useRef(1);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [recentActions, setRecentActions] = useState<RecentAction[]>([]);

  // 钉钉通讯录同步
  const [status, setStatus] = useState<DingtalkSyncStatus | null>(null);
  const [departments, setDepartments] = useState<DingtalkDepartment[]>([]);
  const [selectedDeptId, setSelectedDeptId] = useState("");
  const [schoolLevel, setSchoolLevel] = useState<
    "primary" | "junior" | "senior"
  >("primary");
  const [grade, setGrade] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [loadingDepts, setLoadingDepts] = useState(false);
  const [syncResult, setSyncResult] = useState("");
  // 同步范围：class=整班名单 / student=只同步单个学生
  const [syncScope, setSyncScope] = useState<"class" | "student">("class");
  const [deptUsers, setDeptUsers] = useState<DingtalkDeptUser[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState("");

  const timeNow = () => {
    const d = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const addAction = (
    action: string,
    result: "成功" | "失败",
    detail: string,
  ) => {
    setRecentActions((prev) =>
      [
        { id: nextIdRef.current++, action, result, detail, time: timeNow() },
        ...prev,
      ].slice(0, 8),
    );
  };

  const loadStatus = async () => {
    try {
      setStatus(await getDingtalkSyncStatus());
    } catch {
      // 未登录/后端未就绪时忽略，保持 null
    }
  };

  const loadDepartments = async () => {
    setLoadingDepts(true);
    try {
      setDepartments(await listDingtalkDepartments());
    } catch (e: any) {
      toast({
        variant: "destructive",
        title: t("settingsClass.sync.noDepartments"),
        description: e?.message || t("settingsClass.sync.noDepartments"),
      });
    } finally {
      setLoadingDepts(false);
    }
  };

  useEffect(() => {
    void (async () => {
      const st = await getDingtalkSyncStatus().catch(() => null);
      if (st) {
        setStatus(st);
        if (st.configured) void loadDepartments();
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 「只同步单个学生」模式下拉取所选部门的成员列表
  useEffect(() => {
    if (syncScope !== "student" || !selectedDeptId) {
      setDeptUsers([]);
      setSelectedUserId("");
      return;
    }
    let cancelled = false;
    setLoadingUsers(true);
    listDingtalkDeptUsers(Number(selectedDeptId))
      .then((users) => {
        if (!cancelled) setDeptUsers(users);
      })
      .catch(() => {
        if (!cancelled) setDeptUsers([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingUsers(false);
      });
    return () => {
      cancelled = true;
    };
  }, [syncScope, selectedDeptId]);

  const handleSync = async () => {
    const deptId = Number(selectedDeptId);
    if (!deptId) {
      toast({
        variant: "destructive",
        title: t("settingsClass.sync.chooseDeptFirst"),
      });
      return;
    }
    if (!grade.trim()) {
      toast({
        variant: "destructive",
        title: t("settingsClass.sync.chooseGradeFirst"),
      });
      return;
    }
    if (syncScope === "student" && !selectedUserId) {
      toast({
        variant: "destructive",
        title: t("settingsClass.sync.selectStudentFirst"),
      });
      return;
    }
    setSyncing(true);
    setSyncResult("");
    try {
      const res = await syncDingtalkClasses({
        dept_id: deptId,
        school_level: schoolLevel,
        grade: grade.trim(),
        scope: syncScope,
        student_userid: syncScope === "student" ? selectedUserId : undefined,
      });
      const msg = t("settingsClass.sync.syncDone", {
        cc: res.classes_created,
        cu: res.classes_updated,
        sc: res.students_created,
        su: res.students_updated,
      });
      setSyncResult(msg);
      toast({ title: t("settingsClass.sync.syncNow"), description: msg });
      await loadStatus();
    } catch (e: any) {
      toast({
        variant: "destructive",
        title: t("settingsClass.sync.syncFailed"),
        description: e?.message || t("settingsClass.sync.syncFailed"),
      });
    } finally {
      setSyncing(false);
    }
  };

  const handleExport = async () => {
    if (!classId) {
      toast({ title: t("settingsClass.sync.needSelectClass") });
      return;
    }
    setExporting(true);
    try {
      const blob = await exportClassData(classId);
      const now = new Date();
      const dateStamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}`;
      const safeClassId = String(classId).replace(/[\\/:*?"<>|]/g, "_");
      saveBlob(blob, `grade_buddy_export_${safeClassId}_${dateStamp}.zip`);
      toast({ title: t("grading.dataExport.exportSuccess") });
      addAction(
        t("settingsClass.sync.actionExport"),
        "成功",
        t("settingsClass.sync.exportDoneDetail", {
          className: className || String(classId),
        }),
      );
    } catch (e: any) {
      toast({
        variant: "destructive",
        title: t("grading.dataExport.exportFailed"),
        description: e?.message || t("grading.dataExport.exportFailed"),
      });
      addAction(
        t("settingsClass.sync.actionExport"),
        "失败",
        e?.message || t("grading.dataExport.exportFailed"),
      );
    } finally {
      setExporting(false);
    }
  };

  const handleImport = async (file: File) => {
    if (!classId) {
      toast({ title: t("settingsClass.sync.needSelectClass") });
      return;
    }
    setImporting(true);
    try {
      const res = await importClassData(file, classId);
      const importedCount = res.imported?.length ?? 0;
      const skippedCount = res.skipped?.length ?? 0;
      const failedCount = res.errors?.length ?? 0;
      toast({
        title: t("grading.dataExport.importSummary", {
          imported: importedCount,
          skipped: skippedCount,
          failed: failedCount,
        }),
      });
      addAction(
        t("settingsClass.sync.actionImport"),
        "成功",
        t("settingsClass.sync.importDoneDetail", {
          imported: importedCount,
          skipped: skippedCount,
          failed: failedCount,
        }),
      );
    } catch (e: any) {
      toast({
        variant: "destructive",
        title: t("grading.dataExport.importFailed"),
        description: e?.message || t("grading.dataExport.importFailed"),
      });
      addAction(
        t("settingsClass.sync.actionImport"),
        "失败",
        e?.message || t("grading.dataExport.importFailed"),
      );
    } finally {
      setImporting(false);
    }
  };

  const handleImportFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void handleImport(file);
    e.target.value = "";
  };

  const translateResult = (result: string) =>
    result === "成功"
      ? t("settingsClass.sync.resultSuccess")
      : t("settingsClass.sync.resultFailed");

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h3 className="text-sm font-semibold text-foreground mb-3">
        {t("settingsClass.sync.title")}
      </h3>

      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs text-muted-foreground">
          {t("settingsClass.sync.statusLabel")}
        </span>
        {status?.configured ? (
          <Badge className="bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400 text-[10px]">
            {t("settingsClass.sync.connectedStatus")}
          </Badge>
        ) : (
          <Badge className="bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400 text-[10px]">
            {t("settingsClass.sync.notIntegrated")}
          </Badge>
        )}
      </div>

      {!status?.configured ? (
        <div
          className="flex items-start gap-2.5 rounded-lg border border-amber-300/70 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300 mb-3"
          role="note"
        >
          <Info className="w-4 h-4 shrink-0 mt-0.5" />
          <p className="text-[11px] leading-5">
            {t("settingsClass.sync.dingTalkNote")}
          </p>
        </div>
      ) : (
        <div className="space-y-2 mb-3">
          <p className="text-[11px] text-muted-foreground">
            {t("settingsClass.sync.statusSummary", {
              classes: status?.synced_class_count ?? 0,
              students: status?.synced_student_count ?? 0,
            })}
          </p>

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-[88px] shrink-0">
              {t("settingsClass.sync.selectDept")}
            </span>
            <select
              value={selectedDeptId}
              onChange={(e) => {
                setSelectedDeptId(e.target.value);
                setSelectedUserId(""); // 换部门后重新选学生
              }}
              className="h-7 flex-1 min-w-0 rounded-md border border-input bg-background px-2 text-xs"
            >
              <option value="">
                {loadingDepts
                  ? t("settingsClass.sync.syncing")
                  : t("settingsClass.sync.selectDept")}
              </option>
              {departments.map((d) => (
                <option key={d.dept_id} value={d.dept_id}>
                  {d.name}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs gap-1"
              onClick={loadDepartments}
              disabled={loadingDepts}
              aria-label={t("settingsClass.sync.forceRefresh")}
            >
              <RefreshCw
                className={`w-3 h-3 ${loadingDepts ? "animate-spin" : ""}`}
              />
            </Button>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-[88px] shrink-0">
              {t("settingsClass.sync.schoolLevel")}
            </span>
            <select
              value={schoolLevel}
              onChange={(e) =>
                setSchoolLevel(e.target.value as "primary" | "junior" | "senior")
              }
              className="h-7 rounded-md border border-input bg-background px-2 text-xs"
            >
              <option value="primary">{t("settingsClass.sync.levelPrimary")}</option>
              <option value="junior">{t("settingsClass.sync.levelJunior")}</option>
              <option value="senior">{t("settingsClass.sync.levelSenior")}</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-[88px] shrink-0">
              {t("settingsClass.sync.grade")}
            </span>
            <input
              value={grade}
              onChange={(e) => setGrade(e.target.value)}
              placeholder={t("settingsClass.sync.grade")}
              className="h-7 flex-1 rounded-md border border-input bg-background px-2 text-xs"
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground w-[88px] shrink-0">
              {t("settingsClass.sync.scopeLabel")}
            </span>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => setSyncScope("class")}
                className={`h-7 w-[88px] rounded-md border text-xs transition-colors ${
                  syncScope === "class"
                    ? "border-emerald-400 bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
                    : "border-input bg-background text-muted-foreground hover:bg-accent"
                }`}
              >
                {t("settingsClass.sync.scopeClass")}
              </button>
              <button
                type="button"
                onClick={() => setSyncScope("student")}
                className={`h-7 w-[88px] rounded-md border text-xs transition-colors ${
                  syncScope === "student"
                    ? "border-emerald-400 bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
                    : "border-input bg-background text-muted-foreground hover:bg-accent"
                }`}
              >
                {t("settingsClass.sync.scopeStudent")}
              </button>
            </div>
          </div>

          {syncScope === "student" && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground w-[88px] shrink-0">
                {t("settingsClass.sync.selectStudent")}
              </span>
              <select
                value={selectedUserId}
                onChange={(e) => setSelectedUserId(e.target.value)}
                disabled={!selectedDeptId || loadingUsers}
                className="h-7 flex-1 min-w-0 rounded-md border border-input bg-background px-2 text-xs"
              >
                <option value="">
                  {loadingUsers
                    ? t("settingsClass.sync.syncing")
                    : t("settingsClass.sync.selectStudent")}
                </option>
                {deptUsers.map((u) => (
                  <option key={u.userid} value={u.userid}>
                    {u.name || u.userid}
                    {u.mobile ? `（${u.mobile}）` : ""}
                  </option>
                ))}
              </select>
              {!loadingUsers && selectedDeptId && deptUsers.length === 0 && (
                <span className="text-[10px] text-amber-600 shrink-0">
                  {t("settingsClass.sync.noDeptUsers")}
                </span>
              )}
            </div>
          )}

          <Button
            size="sm"
            className="h-7 text-xs gap-1"
            onClick={handleSync}
            disabled={
              syncing ||
              !selectedDeptId ||
              (syncScope === "student" && !selectedUserId)
            }
          >
            {syncing ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <RefreshCw className="w-3 h-3" />
            )}
            {syncing
              ? t("settingsClass.sync.syncing")
              : syncScope === "student"
                ? t("settingsClass.sync.syncStudentNow")
                : t("settingsClass.sync.syncNow")}
          </Button>

          {syncResult && (
            <p className="text-[11px] text-emerald-600">{syncResult}</p>
          )}
        </div>
      )}

      <Separator className="my-3" />

      <p className="text-xs font-medium text-foreground mb-1">
        {t("settingsClass.sync.roamingTitle")}
      </p>
      <p className="text-[11px] text-muted-foreground mb-2">
        {t("settingsClass.sync.roamingDesc")}
      </p>
      <div className="flex gap-2 mb-3">
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs gap-1"
          onClick={handleExport}
          disabled={!classId || exporting || importing}
        >
          {exporting ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Download className="w-3 h-3" />
          )}
          {exporting
            ? t("grading.dataExport.exporting")
            : t("grading.dataExport.export")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs gap-1"
          onClick={() => importInputRef.current?.click()}
          disabled={!classId || exporting || importing}
        >
          {importing ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <Upload className="w-3 h-3" />
          )}
          {importing
            ? t("grading.dataExport.importing")
            : t("grading.dataExport.import")}
        </Button>
        <input
          ref={importInputRef}
          type="file"
          accept=".zip,application/zip,application/x-zip-compressed"
          className="hidden"
          disabled={!classId || importing}
          onChange={handleImportFileChange}
        />
      </div>

      <div className="flex items-center justify-between mb-1">
        <p className="text-xs font-medium text-foreground">
          {t("settingsClass.sync.recentActions")}
        </p>
      </div>
      {recentActions.length === 0 ? (
        <p className="text-[10px] text-muted-foreground mb-3">
          {t("settingsClass.sync.noRecentActions")}
        </p>
      ) : (
        <div className="space-y-1 mb-3 max-h-[120px] overflow-y-auto">
          {recentActions.map((log) => (
            <div
              key={log.id}
              className="flex items-center gap-2 text-[10px] text-muted-foreground py-1"
            >
              <span className="shrink-0 w-[80px]">{log.time}</span>
              <span className="shrink-0">{log.action}</span>
              <Badge
                variant="outline"
                className={`text-[9px] px-1 py-0 ${
                  log.result === "成功"
                    ? "text-emerald-600"
                    : "text-destructive"
                }`}
              >
                {translateResult(log.result)}
              </Badge>
              <span className="truncate">{log.detail}</span>
            </div>
          ))}
        </div>
      )}

      <Separator className="my-3" />

      <p className="text-xs font-medium text-foreground mb-2">
        {t("settingsClass.sync.securityLabel")}
      </p>
      <div className="space-y-1 text-xs text-muted-foreground">
        <p className="flex items-center gap-1">
          <Database className="w-3 h-3" /> {t("settingsClass.sync.localBackup")}
        </p>
        <p className="flex items-center gap-1">
          <Shield className="w-3 h-3" /> {t("settingsClass.sync.cloudBackup")}
        </p>
      </div>
    </div>
  );
}
