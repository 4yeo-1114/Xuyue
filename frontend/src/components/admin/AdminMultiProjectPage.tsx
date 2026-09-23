import { useCallback, useEffect, useRef, useState } from "react";
import {
  Database,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Server,
  Trash2,
  Type,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
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
import { useProjectBranding } from "@/contexts/ProjectBrandingContext";
import { useLocale } from "@/contexts/LocaleContext";
import {
  applyDbProfile,
  createDbProfile,
  deleteDbProfile,
  fetchMultiProjectSettings,
  updateDbProfile,
  updateProjectName,
  type DbProfile,
  type DbProfileInput,
} from "@/services/multiProjectApi";

const EMPTY_FORM: DbProfileInput = {
  name: "",
  host: "",
  port: 3306,
  user: "",
  password: "",
  database: "",
};

export function AdminMultiProjectPage() {
  const { projectName, setProjectName, refreshBranding } = useProjectBranding();
  const { t } = useLocale();
  const [nameDraft, setNameDraft] = useState(projectName);
  const [savingName, setSavingName] = useState(false);

  const [loading, setLoading] = useState(true);
  // 是否已完成首载:仅首载整页 loading,后续保存/删除/切换/刷新用局部态,避免整页闪屏
  const isFirstLoadRef = useRef(true);
  const [refreshing, setRefreshing] = useState(false);
  const [profiles, setProfiles] = useState<DbProfile[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DbProfile | null>(null);
  const [editing, setEditing] = useState<DbProfile | null>(null);
  const [selected, setSelected] = useState<DbProfile | null>(null);
  const [form, setForm] = useState<DbProfileInput>(EMPTY_FORM);
  const [savingProfile, setSavingProfile] = useState(false);
  const [applying, setApplying] = useState(false);

  const loadSettings = useCallback(async () => {
    const isFirstLoad = isFirstLoadRef.current;
    if (isFirstLoad) {
      setLoading(true);
    } else {
      // 非首载(保存/删除/切换/刷新):保留旧数据展示,新值到达后再替换,避免整页 loading 闪屏
      setRefreshing(true);
    }
    try {
      const data = await fetchMultiProjectSettings();
      setProfiles(data.db_profiles || []);
      setActiveId(data.active_db_profile_id || null);
      setNameDraft(data.project_name || projectName);
    } catch (e: unknown) {
      toast.error(
        e instanceof Error
          ? e.message
          : t("admin.multiProject.toast.loadFailed"),
      );
    } finally {
      if (isFirstLoad) setLoading(false);
      setRefreshing(false);
      isFirstLoadRef.current = false;
    }
  }, [projectName, t]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    setNameDraft(projectName);
  }, [projectName]);

  const handleSaveName = async () => {
    const trimmed = nameDraft.trim();
    if (!trimmed) {
      toast.error(t("admin.multiProject.toast.nameRequired"));
      return;
    }
    setSavingName(true);
    try {
      const saved = await updateProjectName(trimmed);
      setProjectName(saved);
      await refreshBranding();
      toast.success(t("admin.multiProject.toast.nameSaved"));
    } catch (e: unknown) {
      toast.error(
        e instanceof Error ? e.message : t("admin.common.saveFailed"),
      );
    } finally {
      setSavingName(false);
    }
  };

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormOpen(true);
  };

  const openEdit = (profile: DbProfile) => {
    setEditing(profile);
    setForm({
      name: profile.name,
      host: profile.host,
      port: profile.port,
      user: profile.user,
      password: "",
      database: profile.database,
    });
    setFormOpen(true);
  };

  const openDetail = (profile: DbProfile) => {
    setSelected(profile);
    setDetailOpen(true);
  };

  const handleSaveProfile = async () => {
    setSavingProfile(true);
    try {
      if (editing) {
        await updateDbProfile(editing.id, form);
        toast.success(t("admin.multiProject.toast.profileUpdated"));
      } else {
        await createDbProfile(form);
        toast.success(t("admin.multiProject.toast.profileCreated"));
      }
      setFormOpen(false);
      await loadSettings();
    } catch (e: unknown) {
      toast.error(
        e instanceof Error ? e.message : t("admin.common.saveFailed"),
      );
    } finally {
      setSavingProfile(false);
    }
  };

  const handleApply = async () => {
    if (!selected) return;
    setApplying(true);
    try {
      const result = await applyDbProfile(selected.id);
      toast.success(result.message || t("admin.multiProject.toast.dbSwitched"));
      setDetailOpen(false);
      await loadSettings();
    } catch (e: unknown) {
      toast.error(
        e instanceof Error
          ? e.message
          : t("admin.multiProject.toast.switchFailed"),
      );
    } finally {
      setApplying(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteDbProfile(deleteTarget.id);
      toast.success(t("admin.multiProject.toast.profileDeleted"));
      setDeleteTarget(null);
      await loadSettings();
    } catch (e: unknown) {
      toast.error(
        e instanceof Error ? e.message : t("admin.common.deleteFailed"),
      );
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h2 className="text-xl font-bold text-foreground">
          {t("admin.multiProject.title")}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          {t("admin.multiProject.description")}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Type className="w-4 h-4 text-primary" />
            {t("admin.multiProject.projectName.sectionTitle")}
          </CardTitle>
          <CardDescription>
            {t("admin.multiProject.projectName.sectionDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2 max-w-md">
            <Label htmlFor="project-name">
              {t("admin.multiProject.projectName.label")}
            </Label>
            <Input
              id="project-name"
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              placeholder={t("admin.multiProject.projectName.placeholder")}
              maxLength={32}
            />
            <p className="text-xs text-muted-foreground">
              {t("admin.multiProject.projectName.current", {
                name: projectName,
              })}
            </p>
          </div>
          <Button
            onClick={handleSaveName}
            disabled={savingName || nameDraft.trim() === projectName}
          >
            {savingName ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Save className="w-4 h-4 mr-2" />
            )}
            {t("admin.multiProject.projectName.save")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Database className="w-4 h-4 text-primary" />
              {t("admin.multiProject.database.sectionTitle")}
            </CardTitle>
            <CardDescription className="mt-1.5">
              {t("admin.multiProject.database.sectionDescription")}
            </CardDescription>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void loadSettings()}
              disabled={refreshing}
            >
              {refreshing ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4 mr-1" />
              )}{" "}
              {t("admin.multiProject.database.refresh")}
            </Button>
            <Button size="sm" onClick={openCreate}>
              <Plus className="w-4 h-4 mr-1" />{" "}
              {t("admin.multiProject.database.create")}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {profiles.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              {t("admin.multiProject.database.empty")}
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {profiles.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => openDetail(p)}
                  className="text-left rounded-xl border border-border bg-card p-4 hover:border-primary/40 hover:shadow-sm transition-all"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-foreground truncate">
                        {p.name}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1 truncate">
                        {p.host}:{p.port}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">
                        {t("admin.multiProject.database.dbPrefix")}
                        {p.database}
                      </p>
                    </div>
                    {p.id === activeId || p.is_active ? (
                      <Badge className="shrink-0">
                        {t("admin.multiProject.database.activeBadge")}
                      </Badge>
                    ) : null}
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 新建/编辑弹窗 */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editing
                ? t("admin.multiProject.form.editTitle")
                : t("admin.multiProject.form.createTitle")}
            </DialogTitle>
            <DialogDescription>
              {t("admin.multiProject.form.description")}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="db-profile-name">
                {t("admin.multiProject.form.name")}
              </Label>
              <Input
                id="db-profile-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder={t("admin.multiProject.form.namePlaceholder")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="db-profile-host">
                {t("admin.multiProject.form.host")}
              </Label>
              <Input
                id="db-profile-host"
                value={form.host}
                onChange={(e) => setForm({ ...form, host: e.target.value })}
                placeholder="rm-xxx.mysql.rds.aliyuncs.com"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label htmlFor="db-profile-port">
                  {t("admin.multiProject.form.port")}
                </Label>
                <Input
                  id="db-profile-port"
                  type="number"
                  value={form.port}
                  onChange={(e) =>
                    setForm({ ...form, port: Number(e.target.value) || 3306 })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="db-profile-database">
                  {t("admin.multiProject.form.database")}
                </Label>
                <Input
                  id="db-profile-database"
                  value={form.database}
                  onChange={(e) =>
                    setForm({ ...form, database: e.target.value })
                  }
                  placeholder="grade"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="db-profile-user">
                {t("admin.multiProject.form.user")}
              </Label>
              <Input
                id="db-profile-user"
                value={form.user}
                onChange={(e) => setForm({ ...form, user: e.target.value })}
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="db-profile-password">
                {t("admin.multiProject.form.password")}
              </Label>
              <Input
                id="db-profile-password"
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder={
                  editing
                    ? t("admin.multiProject.form.passwordKeepPlaceholder")
                    : t("admin.multiProject.form.passwordPlaceholder")
                }
                autoComplete="new-password"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)}>
              {t("admin.common.cancel")}
            </Button>
            <Button onClick={handleSaveProfile} disabled={savingProfile}>
              {savingProfile ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Save className="w-4 h-4 mr-2" />
              )}
              {t("admin.common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 详情 + 转换 */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Server className="w-5 h-5 text-primary" />
              {selected?.name}
            </DialogTitle>
            <DialogDescription>
              {t("admin.multiProject.detail.description")}
            </DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="space-y-2 text-sm rounded-lg bg-muted/50 p-4">
              <p>
                <span className="text-muted-foreground">
                  {t("admin.multiProject.detail.host")}
                </span>
                {selected.host}:{selected.port}
              </p>
              <p>
                <span className="text-muted-foreground">
                  {t("admin.multiProject.detail.database")}
                </span>
                {selected.database}
              </p>
              <p>
                <span className="text-muted-foreground">
                  {t("admin.multiProject.detail.user")}
                </span>
                {selected.user}
              </p>
              <p>
                <span className="text-muted-foreground">
                  {t("admin.multiProject.detail.password")}
                </span>
                {selected.password || "******"}
              </p>
              {(selected.id === activeId || selected.is_active) && (
                <Badge variant="secondary" className="mt-2">
                  {t("admin.multiProject.detail.activeBadge")}
                </Badge>
              )}
            </div>
          )}
          <DialogFooter className="flex-col sm:flex-row gap-2">
            <Button
              variant="outline"
              onClick={() => selected && openEdit(selected)}
            >
              <Pencil className="w-4 h-4 mr-1" /> {t("admin.common.edit")}
            </Button>
            <Button
              variant="outline"
              className="text-destructive"
              onClick={() => {
                setDetailOpen(false);
                setDeleteTarget(selected);
              }}
            >
              <Trash2 className="w-4 h-4 mr-1" /> {t("admin.common.delete")}
            </Button>
            <Button
              onClick={handleApply}
              disabled={
                applying ||
                !selected ||
                selected.id === activeId ||
                selected.is_active
              }
            >
              {applying ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : null}
              {t("admin.multiProject.detail.apply")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("admin.multiProject.delete.title", {
                name: deleteTarget?.name ?? "",
              })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t("admin.multiProject.delete.description")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("admin.common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t("admin.multiProject.delete.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
