import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  UserPlus,
  Search,
  Pencil,
  Trash2,
  ShieldAlert,
  Upload,
  Loader2,
  Download,
  X,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { API_PREFIX } from "@/config/api";
import { batchImportAdminUsers } from "@/services/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AuthUser } from "@/hooks/useAuth";
import { isPlatformAdmin } from "@/lib/adminAccess";
import { SYSTEM_ROLES } from "@/constants/systemRoles";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSystemRole, translateSubjectName } from "@/i18n/index";

import * as XLSX from "xlsx";

const TEACHING_SUBJECTS = [
  "语文",
  "数学",
  "英语",
  "地理",
  "历史",
  "政治",
  "生物",
  "科学",
  "信息",
  "物理",
  "化学",
];
const AVAILABLE_ROLES = [...SYSTEM_ROLES];

interface AdminUserRecord extends AuthUser {
  created_at: string;
}

interface AdminSaveUserPayload {
  display_name: string | null;
  teaching_subject: string | null;
  job_title: string | null;
  roles: string[];
  personal_email: string | null;
  caller_password: string;
  email?: string;
  password?: string;
}

export function AccountManagePage() {
  const { user } = useAuth();
  const { t, locale } = useLocale();
  const [users, setUsers] = useState<AdminUserRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUserRecord | null>(null);
  const [formEmail, setFormEmail] = useState("");
  const [formPassword, setFormPassword] = useState("");
  const [formDisplayName, setFormDisplayName] = useState("");
  const [formJobTitle, setFormJobTitle] = useState("");
  const [formSubject, setFormSubject] = useState("");
  const [formRole, setFormRole] = useState<string>("任课教师");
  // 角色数组整体保存，避免多角色用户编辑时被静默剥离为单个角色
  const [formRoles, setFormRoles] = useState<string[]>(["任课教师"]);
  const [formPersonalEmail, setFormPersonalEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [saving, setSaving] = useState(false);

  const [deleteUser, setDeleteUser] = useState<AdminUserRecord | null>(null);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [batchDeleteMode, setBatchDeleteMode] = useState(false);
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([]);
  const [batchDeleteOpen, setBatchDeleteOpen] = useState(false);
  const [batchDeletePassword, setBatchDeletePassword] = useState("");
  const [batchDeleting, setBatchDeleting] = useState(false);

  const [batchImportOpen, setBatchImportOpen] = useState(false);
  const [batchFile, setBatchFile] = useState<File | null>(null);
  const [batchPassword, setBatchPassword] = useState("");
  const [batchImporting, setBatchImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isSuperAdmin = user?.roles?.includes("系统管理员");
  const canAccess = isPlatformAdmin(user);

  // 卸载守卫：异步 fetch 完成后若组件已卸载则不再 setState，避免 React 告警与内存泄漏
  const mountedRef = useRef(true);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_PREFIX}/admin/users`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("grade_buddy_access_token")}`,
        },
      });
      if (!mountedRef.current) return;
      if (res.ok) {
        const json = await res.json();
        const list = Array.isArray(json.data) ? json.data : null;
        if (list) {
          setUsers(list);
          setSelectedUserIds((current) =>
            current.filter((id) =>
              list.some((item: AdminUserRecord) => item.id === id),
            ),
          );
        }
      } else {
        toast.error(t("account.toast.fetchFailed"));
      }
    } catch (e) {
      if (!mountedRef.current) return;
      console.error(e);
      toast.error(t("account.toast.networkError"));
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    mountedRef.current = true;
    if (!canAccess) return;
    fetchUsers();
    return () => {
      mountedRef.current = false;
    };
  }, [canAccess, fetchUsers]);

  const resetBatchImportForm = useCallback(() => {
    setBatchFile(null);
    setBatchPassword("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  const handleBatchImportOpenChange = (open: boolean) => {
    if (!open && batchImporting) return;
    setBatchImportOpen(open);
    if (!open) {
      resetBatchImportForm();
    }
  };

  const handleOpenDialog = (u?: AdminUserRecord) => {
    if (u) {
      if (isSuperAdmin && u.roles?.includes("系统管理员")) {
        toast.error(t("account.toast.cannotEditSystemAdmin"));
        return;
      }
      setEditingUser(u);
      setFormEmail(u.email);
      setFormPassword("");
      setFormDisplayName(u.display_name || "");
      setFormJobTitle(u.job_title || "");
      setFormSubject(u.teaching_subject || "");
      setFormRole(u.roles?.[0] || "任课教师");
      setFormRoles(u.roles?.length ? [...u.roles] : ["任课教师"]);
      setFormPersonalEmail(u.personal_email || "");
    } else {
      setEditingUser(null);
      setFormEmail("");
      setFormPassword("");
      setFormDisplayName("");
      setFormJobTitle("");
      setFormSubject("");
      setFormRole("任课教师");
      setFormRoles(["任课教师"]);
      setFormPersonalEmail("");
    }
    setAdminPassword("");
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!formEmail || (!editingUser && !formPassword) || !formRole) {
      toast.error(t("account.toast.requiredFields"));
      return;
    }
    if (!adminPassword) {
      toast.error(t("account.toast.verifyPasswordRequired"));
      return;
    }

    setSaving(true);
    try {
      const url = editingUser
        ? `${API_PREFIX}/admin/users/${editingUser.id}`
        : `${API_PREFIX}/admin/users`;

      const method = editingUser ? "PATCH" : "POST";

      const payload: AdminSaveUserPayload = {
        display_name: formDisplayName.trim() || null,
        teaching_subject:
          formSubject === "__none__" || !formSubject ? null : formSubject,
        job_title: formJobTitle.trim() || null,
        roles: formRoles,
        personal_email: formPersonalEmail.trim() || null,
        caller_password: adminPassword,
      };

      if (!editingUser) {
        payload.email = formEmail;
      }
      if (formPassword) {
        payload.password = formPassword;
      }

      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("grade_buddy_access_token")}`,
        },
        body: JSON.stringify(payload),
      });

      // 先判 res.ok 再解析：非 JSON 错误体（HTML 500/代理错误）json() 会抛错，
      // 避免掩盖真实失败原因而误报 networkError
      if (!res.ok) {
        let detail: string | undefined;
        try {
          const body = await res.json();
          detail = body?.detail;
        } catch {
          // 非 JSON 错误体，忽略解析，用通用文案兜底
        }
        toast.error(detail || t("account.toast.actionFailed"));
        return;
      }

      await res.json();
      toast.success(
        editingUser
          ? t("account.toast.updateSuccess")
          : t("account.toast.createSuccess"),
      );
      setDialogOpen(false);
      fetchUsers();
    } catch (e) {
      console.error(e);
      toast.error(t("account.toast.networkError"));
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteUser) return;
    if (!deletePassword) {
      toast.error(t("account.toast.verifyPasswordRequired"));
      return;
    }

    setDeleting(true);
    try {
      const res = await fetch(`${API_PREFIX}/admin/users/${deleteUser.id}`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("grade_buddy_access_token")}`,
        },
        body: JSON.stringify({ caller_password: deletePassword }),
      });
      if (res.ok) {
        toast.success(t("account.toast.deleteSuccess"));
        setDeleteUser(null);
        fetchUsers();
      } else {
        const json = await res.json();
        toast.error(json.detail || t("account.toast.deleteFailed"));
      }
    } catch (e) {
      toast.error(t("account.toast.networkError"));
    } finally {
      setDeleting(false);
    }
  };

  const handleDelete = (u: AdminUserRecord) => {
    if (u.roles?.includes("系统管理员")) {
      toast.error(t("account.toast.cannotDeleteSystemAdmin"));
      return;
    }
    setDeleteUser(u);
    setDeletePassword("");
  };

  const leaveBatchDeleteMode = () => {
    setBatchDeleteMode(false);
    setSelectedUserIds([]);
    setBatchDeleteOpen(false);
    setBatchDeletePassword("");
  };

  const toggleBatchDeleteSelection = (targetId: string) => {
    setSelectedUserIds((current) =>
      current.includes(targetId)
        ? current.filter((id) => id !== targetId)
        : [...current, targetId],
    );
  };

  // 账号分组逻辑
  const groupedUsers = useMemo(() => {
    const groups: Record<string, AdminUserRecord[]> = {};
    AVAILABLE_ROLES.forEach((r) => (groups[r] = []));

    users.forEach((u) => {
      const role = u.roles?.[0] || "任课教师";
      // 模糊匹配搜索
      const searchStr =
        `${u.display_name || ""} ${u.email} ${u.job_title || ""}`.toLowerCase();
      if (search && !searchStr.includes(search.toLowerCase())) return;

      if (groups[role]) {
        groups[role].push(u);
      } else {
        groups["任课教师"].push(u);
      }
    });
    return groups;
  }, [users, search]);

  const canEditUser = (targetUser: AdminUserRecord) => {
    const targetIsSuper = targetUser.roles?.includes("系统管理员");
    if (isSuperAdmin && targetIsSuper) return false; // 系统管理员不能修改系统管理员（包括自己）
    if (targetIsSuper) return false; // 子系统管理员不能改系统管理员
    return true;
  };

  const canDeleteUser = (targetUser: AdminUserRecord) => {
    if (targetUser.id === user?.id) return false;
    const targetIsSuper = targetUser.roles?.includes("系统管理员");
    if (targetIsSuper) return false;
    return true;
  };

  const selectedUsers = useMemo(
    () =>
      selectedUserIds
        .map((id) => users.find((account) => account.id === id))
        .filter((account): account is AdminUserRecord => Boolean(account)),
    [selectedUserIds, users],
  );

  const handleBatchDeleteConfirm = async () => {
    if (selectedUserIds.length === 0) {
      toast.error(t("account.toast.selectAccountsToDelete"));
      return;
    }
    if (!batchDeletePassword) {
      toast.error(t("account.toast.verifyPasswordRequired"));
      return;
    }

    setBatchDeleting(true);
    try {
      const res = await fetch(`${API_PREFIX}/admin/users/batch-delete`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("grade_buddy_access_token")}`,
        },
        body: JSON.stringify({
          user_ids: selectedUserIds,
          caller_password: batchDeletePassword,
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(json.detail || t("account.toast.batchDeleteFailed"));
        return;
      }

      const deletedCount =
        Number(json.data?.deleted_count) || selectedUserIds.length;
      toast.success(
        t("account.toast.batchDeleteSuccess", { count: deletedCount }),
      );
      leaveBatchDeleteMode();
      await fetchUsers();
    } catch (e) {
      console.error(e);
      toast.error(t("account.toast.networkError"));
    } finally {
      setBatchDeleting(false);
    }
  };

  const handleBatchImport = async () => {
    if (!batchFile) {
      toast.error(t("account.toast.selectExcelFile"));
      return;
    }
    if (!batchPassword) {
      toast.error(t("account.toast.verifyPasswordRequired"));
      return;
    }

    setBatchImporting(true);
    try {
      const res = await batchImportAdminUsers(batchFile, batchPassword);
      toast.success(
        t("account.toast.batchImportSuccess", { count: res.success_count }),
      );
      if (res.errors && res.errors.length > 0) {
        res.errors.forEach((err) => toast.error(err, { duration: 5000 }));
      }
      setBatchImportOpen(false);
      resetBatchImportForm();
      fetchUsers();
    } catch (e: unknown) {
      console.error(e);
      toast.error(
        e instanceof Error ? e.message : t("account.toast.batchImportFailed"),
      );
    } finally {
      setBatchImporting(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setBatchFile(e.target.files[0]);
    }
  };

  const handleExportUsers = () => {
    try {
      if (!users || users.length === 0) {
        toast.warning(t("account.toast.noExportData"));
        return;
      }

      const colName = t("account.export.colName");
      const colAccount = t("account.export.colAccount");
      const colRole = t("account.export.colRole");

      const exportData = users.map((u) => ({
        [colName]: u.display_name || t("account.unnamed"),
        [colAccount]: u.email,
        [colRole]: u.roles?.[0] || "任课教师",
      }));

      const worksheet = XLSX.utils.json_to_sheet(exportData);
      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(
        workbook,
        worksheet,
        t("account.export.sheetName"),
      );

      // 调整列宽
      const wscols = [
        { wch: 15 }, // 姓名
        { wch: 30 }, // 账号
        { wch: 20 }, // 系统角色
      ];
      worksheet["!cols"] = wscols;

      // 导出文件
      XLSX.writeFile(
        workbook,
        `${t("account.export.fileNamePrefix")}_${new Date().toISOString().split("T")[0]}.xlsx`,
      );
      toast.success(t("account.toast.exportSuccess"));
    } catch (error) {
      console.error("导出失败:", error);
      toast.error(t("account.toast.exportFailed"));
    }
  };

  if (!canAccess) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t("account.accessDenied.title")}</CardTitle>
          <CardDescription>
            {t("account.accessDenied.description")}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 pb-10">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-primary" />
            {t("account.title")}
          </h2>
          <p className="text-muted-foreground mt-1">{t("account.subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3">
          <Button
            onClick={handleExportUsers}
            variant="outline"
            className="gap-2 shadow-sm text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 border-emerald-200"
          >
            <Download className="w-4 h-4" />
            {t("account.export")}
          </Button>
          <Button
            onClick={() => setBatchImportOpen(true)}
            variant="outline"
            className="gap-2 shadow-sm"
          >
            <Upload className="w-4 h-4" />
            {t("account.batchCreate")}
          </Button>
          <Button
            onClick={() => handleOpenDialog()}
            className="gap-2 shadow-sm"
          >
            <UserPlus className="w-4 h-4" />
            {t("account.createNew")}
          </Button>
          {batchDeleteMode ? (
            <>
              <Button
                onClick={leaveBatchDeleteMode}
                variant="outline"
                className="gap-2 shadow-sm"
              >
                <X className="w-4 h-4" />
                {t("account.multiDelete.cancel")}
              </Button>
              <Button
                onClick={() => {
                  setBatchDeletePassword("");
                  setBatchDeleteOpen(true);
                }}
                variant="destructive"
                className="gap-2 shadow-sm"
                disabled={selectedUserIds.length === 0}
              >
                <Trash2 className="w-4 h-4" />
                {t("account.multiDelete.deleteSelected", {
                  count: selectedUserIds.length,
                })}
              </Button>
            </>
          ) : (
            <Button
              onClick={() => setBatchDeleteMode(true)}
              variant="outline"
              className="gap-2 border-destructive/30 text-destructive shadow-sm hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="w-4 h-4" />
              {t("account.multiDelete.button")}
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            type="search"
            name="account-list-filter"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            data-1p-ignore
            data-lpignore="true"
            readOnly={!searchFocused}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            placeholder={t("account.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 bg-card"
          />
        </div>
        {batchDeleteMode && (
          <div className="rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm font-medium text-destructive">
            {t("account.multiDelete.selectedCount", {
              count: selectedUserIds.length,
            })}
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center p-12 text-muted-foreground">
          {t("account.loading")}
        </div>
      ) : (
        <div className="space-y-8">
          {AVAILABLE_ROLES.map((role) => {
            const groupList = groupedUsers[role];
            if (!groupList || groupList.length === 0) return null;

            return (
              <div key={role} className="space-y-3">
                <h3 className="text-lg font-semibold flex items-center gap-2 text-foreground/90 border-b pb-2">
                  <div className="w-2 h-4 rounded-sm bg-primary/80"></div>
                  {translateSystemRole(locale, role)}{" "}
                  <span className="text-sm font-normal text-muted-foreground ml-1">
                    {t("account.groupCount", { count: groupList.length })}
                  </span>
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {groupList.map((u) => {
                    const selectable = canDeleteUser(u);
                    const selected = selectedUserIds.includes(u.id);
                    return (
                      <Card
                        key={u.id}
                        className={`overflow-hidden transition-all group ${
                          batchDeleteMode && selectable
                            ? "cursor-pointer hover:border-destructive/40 hover:shadow-md"
                            : "hover:shadow-md"
                        } ${selected ? "border-destructive bg-destructive/5 ring-1 ring-destructive/20" : ""}`}
                        onClick={
                          batchDeleteMode && selectable
                            ? () => toggleBatchDeleteSelection(u.id)
                            : undefined
                        }
                      >
                        <CardContent className="p-4 flex justify-between items-start">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-semibold text-base truncate">
                                {u.display_name || t("account.unnamed")}
                              </span>
                              {u.id === user?.id && (
                                <Badge
                                  variant="secondary"
                                  className="text-[10px] px-1 py-0 h-4"
                                >
                                  {t("account.myself")}
                                </Badge>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground truncate mb-2">
                              {u.email}
                            </p>
                            <div className="flex flex-col gap-1.5 mt-2">
                              {u.job_title && (
                                <span className="text-xs bg-sky-50 text-sky-700 px-2 py-0.5 rounded w-fit border border-sky-100">
                                  {u.job_title}
                                </span>
                              )}
                              {u.teaching_subject && (
                                <span className="text-xs bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded w-fit border border-emerald-100">
                                  {t("account.subjectLabel", {
                                    subject: translateSubjectName(
                                      locale,
                                      u.teaching_subject,
                                    ),
                                  })}
                                </span>
                              )}
                            </div>
                          </div>
                          {batchDeleteMode ? (
                            <div
                              className="ml-3 flex h-8 w-8 shrink-0 items-center justify-center"
                              onClick={(event) => event.stopPropagation()}
                            >
                              {selectable && (
                                <Checkbox
                                  checked={selected}
                                  onCheckedChange={() =>
                                    toggleBatchDeleteSelection(u.id)
                                  }
                                  aria-label={t(
                                    "account.multiDelete.selectAccount",
                                    { name: u.display_name || u.email },
                                  )}
                                  className="h-5 w-5 border-destructive/50 data-[state=checked]:border-destructive data-[state=checked]:bg-destructive"
                                />
                              )}
                            </div>
                          ) : (
                            <div className="flex flex-col gap-1 ml-2 shrink-0">
                              {canEditUser(u) && (
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8 text-muted-foreground hover:text-primary"
                                  onClick={() => handleOpenDialog(u)}
                                  aria-label={t("account.action.edit")}
                                >
                                  <Pencil className="w-4 h-4" />
                                </Button>
                              )}
                              {canDeleteUser(u) && (
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                                  onClick={() => handleDelete(u)}
                                  aria-label={t("account.action.delete")}
                                >
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              )}
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 弹窗 */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent
          className="sm:max-w-[425px]"
          onCloseAutoFocus={(e) => e.preventDefault()}
        >
          <DialogHeader>
            <DialogTitle>
              {editingUser
                ? t("account.dialog.editTitle")
                : t("account.dialog.createTitle")}
            </DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>{t("account.form.loginEmail")}</Label>
              <Input
                value={formEmail}
                onChange={(e) => setFormEmail(e.target.value)}
                placeholder={t("account.form.emailPlaceholder")}
                disabled={!!editingUser}
                autoComplete="off"
                name="managed-user-email"
                className={editingUser ? "bg-muted" : ""}
              />
            </div>
            <div className="grid gap-2">
              <Label>
                {t("account.form.password")}{" "}
                {editingUser && (
                  <span className="text-muted-foreground font-normal text-xs">
                    {t("account.form.passwordOptionalHint")}
                  </span>
                )}
              </Label>
              <Input
                type="password"
                value={formPassword}
                onChange={(e) => setFormPassword(e.target.value)}
                placeholder={t("account.form.passwordPlaceholder")}
                autoComplete="new-password"
                name="managed-user-password"
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("account.form.displayName")}</Label>
              <Input
                value={formDisplayName}
                onChange={(e) => setFormDisplayName(e.target.value)}
                placeholder={t("account.form.displayNamePlaceholder")}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("account.form.systemRole")}</Label>
              <Select
                value={formRole}
                onValueChange={(v) => {
                  setFormRole(v);
                  // 保留其余角色，仅替换主角色（多角色用户不被剥离）
                  setFormRoles((prev) => {
                    const idx = prev.indexOf(formRole);
                    if (idx >= 0) {
                      const next = [...prev];
                      next[idx] = v;
                      return next;
                    }
                    return prev.includes(v) ? prev : [...prev, v];
                  });
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t("account.form.selectRole")} />
                </SelectTrigger>
                <SelectContent>
                  {AVAILABLE_ROLES.map((role) => (
                    <SelectItem
                      key={role}
                      value={role}
                      disabled={!isSuperAdmin && role === "系统管理员"}
                    >
                      {translateSystemRole(locale, role)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>{t("account.form.jobTitle")}</Label>
              <Input
                value={formJobTitle}
                onChange={(e) => setFormJobTitle(e.target.value)}
                placeholder={t("account.form.jobTitlePlaceholder")}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("account.form.teachingSubject")}</Label>
              <Select
                value={formSubject || "__none__"}
                onValueChange={setFormSubject}
              >
                <SelectTrigger>
                  <SelectValue placeholder={t("account.form.selectSubject")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">
                    {t("account.form.subjectUnset")}
                  </SelectItem>
                  {TEACHING_SUBJECTS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {translateSubjectName(locale, s)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>
                {t("account.form.personalEmail")}{" "}
                <span className="text-muted-foreground font-normal text-xs">
                  {t("account.form.personalEmailHint")}
                </span>
              </Label>
              <Input
                type="email"
                value={formPersonalEmail}
                onChange={(e) => setFormPersonalEmail(e.target.value)}
                placeholder={t("account.form.personalEmailPlaceholder")}
              />
            </div>

            <div className="border-t pt-4 mt-2 space-y-2">
              <Label className="text-destructive font-semibold">
                {t("account.form.verifyPassword")}{" "}
                <span className="text-muted-foreground font-normal">
                  {t("account.form.required")}
                </span>
              </Label>
              <Input
                type="password"
                value={adminPassword}
                onChange={(e) => setAdminPassword(e.target.value)}
                placeholder={t("account.form.verifyPasswordPlaceholder")}
                autoComplete="new-password"
                name="admin-action-verify-password"
                className="border-destructive/30 focus-visible:ring-destructive/30"
              />
              <p className="text-xs text-muted-foreground">
                {t("account.form.verifyPasswordHint")}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              {t("account.form.cancel")}
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? t("account.form.saving") : t("account.form.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认弹窗 */}
      <Dialog
        open={!!deleteUser}
        onOpenChange={(open) => !open && setDeleteUser(null)}
      >
        <DialogContent
          className="sm:max-w-[425px]"
          onCloseAutoFocus={(e) => e.preventDefault()}
        >
          <DialogHeader>
            <DialogTitle className="text-destructive">
              {t("account.delete.title")}
            </DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-4">
            <p className="text-sm">
              {t("account.delete.message", {
                name: deleteUser?.display_name || deleteUser?.email || "",
              })}
            </p>
            <div className="space-y-2">
              <Label className="text-destructive font-semibold">
                {t("account.form.verifyPassword")}{" "}
                <span className="text-muted-foreground font-normal">
                  {t("account.form.required")}
                </span>
              </Label>
              <Input
                type="password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                placeholder={t("account.form.verifyPasswordPlaceholder")}
                autoComplete="new-password"
                name="admin-delete-verify-password"
                className="border-destructive/30 focus-visible:ring-destructive/30"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteUser(null)}>
              {t("account.form.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteConfirm}
              disabled={deleting}
            >
              {deleting
                ? t("account.delete.deleting")
                : t("account.delete.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 多选删除确认弹窗 */}
      <Dialog
        open={batchDeleteOpen}
        onOpenChange={(open) => {
          if (batchDeleting) return;
          setBatchDeleteOpen(open);
          if (!open) setBatchDeletePassword("");
        }}
      >
        <DialogContent
          className="sm:max-w-[480px]"
          onCloseAutoFocus={(e) => e.preventDefault()}
        >
          <DialogHeader>
            <DialogTitle className="text-destructive">
              {t("account.multiDelete.title")}
            </DialogTitle>
            <DialogDescription>
              {t("account.multiDelete.description", {
                count: selectedUsers.length,
              })}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="max-h-48 overflow-y-auto rounded-md border bg-muted/20 p-2">
              {selectedUsers.map((account) => (
                <div
                  key={account.id}
                  className="flex items-center justify-between gap-3 border-b px-2 py-2 text-sm last:border-b-0"
                >
                  <span className="min-w-0 truncate font-medium">
                    {account.display_name || t("account.unnamed")}
                  </span>
                  <span className="min-w-0 truncate text-xs text-muted-foreground">
                    {account.email}
                  </span>
                </div>
              ))}
            </div>
            <div className="space-y-2">
              <Label className="font-semibold text-destructive">
                {t("account.form.verifyPassword")}{" "}
                <span className="font-normal text-muted-foreground">
                  {t("account.form.required")}
                </span>
              </Label>
              <Input
                type="password"
                value={batchDeletePassword}
                onChange={(e) => setBatchDeletePassword(e.target.value)}
                placeholder={t("account.form.verifyPasswordPlaceholder")}
                autoComplete="new-password"
                name="admin-batch-delete-verify-password"
                className="border-destructive/30 focus-visible:ring-destructive/30"
                disabled={batchDeleting}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setBatchDeleteOpen(false)}
              disabled={batchDeleting}
            >
              {t("account.form.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={handleBatchDeleteConfirm}
              disabled={
                !batchDeletePassword ||
                selectedUsers.length === 0 ||
                batchDeleting
              }
              className="gap-2"
            >
              {batchDeleting && <Loader2 className="h-4 w-4 animate-spin" />}
              {batchDeleting
                ? t("account.multiDelete.deleting")
                : t("account.multiDelete.confirm", {
                    count: selectedUsers.length,
                  })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 批量导入：文件选择器放在 Dialog 外，避免弹窗关闭时卸载导致状态异常 */}
      <Input
        type="file"
        accept=".xlsx,.xls"
        onChange={handleFileChange}
        ref={fileInputRef}
        disabled={batchImporting}
        className="hidden"
      />

      {/* 批量导入账号弹窗 */}
      <Dialog open={batchImportOpen} onOpenChange={handleBatchImportOpenChange}>
        <DialogContent
          className="sm:max-w-[425px]"
          onCloseAutoFocus={(e) => e.preventDefault()}
        >
          <DialogHeader>
            <DialogTitle>{t("account.batch.title")}</DialogTitle>
            <DialogDescription>
              {t("account.batch.description")}
              <br />
              {t("account.batch.ruleRequired")}
              <br />
              {t("account.batch.ruleAutoAccount")}
              <br />
              {t("account.batch.ruleDefaultPassword")}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">
                {t("account.batch.excelFile")}
              </Label>
              <div className="col-span-3">
                <div
                  className={`border-2 border-dashed rounded-md p-6 text-center cursor-pointer transition-colors
                    ${batchImporting ? "opacity-50 cursor-not-allowed" : "hover:border-primary hover:bg-primary/5 active:bg-primary/10"}
                    ${batchFile ? "border-primary/50 bg-primary/5" : "border-border"}`}
                  onClick={() =>
                    !batchImporting && fileInputRef.current?.click()
                  }
                >
                  <Upload
                    className={`w-8 h-8 mx-auto mb-2 ${batchFile ? "text-primary" : "text-muted-foreground"}`}
                  />
                  <p className="text-sm font-medium">
                    {batchFile
                      ? t("account.batch.reselectFile")
                      : t("account.batch.uploadFile")}
                  </p>
                  {batchFile ? (
                    <p className="text-xs text-primary mt-1 font-semibold">
                      {batchFile.name}
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground mt-1">
                      {t("account.batch.fileFormats")}
                    </p>
                  )}
                </div>
              </div>
            </div>

            <div className="bg-muted/30 border border-border/50 p-4 rounded-lg space-y-3 mt-2">
              <Label className="text-xs font-semibold text-destructive flex items-center gap-1">
                <ShieldAlert className="w-3 h-3" />
                {t("account.batch.sensitiveVerify")}
              </Label>
              <Input
                type="password"
                value={batchPassword}
                onChange={(e) => setBatchPassword(e.target.value)}
                placeholder={t("account.batch.verifyPasswordPlaceholder")}
                autoComplete="new-password"
                name="admin-batch-verify-password"
                className="text-sm h-9"
                disabled={batchImporting}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => handleBatchImportOpenChange(false)}
              disabled={batchImporting}
            >
              {t("account.form.cancel")}
            </Button>
            <Button
              onClick={handleBatchImport}
              disabled={!batchFile || !batchPassword || batchImporting}
              className="gap-2"
            >
              {batchImporting && <Loader2 className="w-4 h-4 animate-spin" />}
              {t("account.batch.startImport")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
