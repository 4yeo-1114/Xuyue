import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  CalendarRange,
  CheckCircle2,
  FileText,
  Folder,
  Loader2,
  Search,
  Upload,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import { translateSystemRole } from "@/i18n/index";
import {
  fetchAdminGradingStats,
  listAdminUsers,
  type AdminUserBrief,
  type GradingStatsResponse,
} from "@/services/api";
import { SYSTEM_ROLES } from "@/constants/systemRoles";

const ROLE_ORDER = [...SYSTEM_ROLES];

/** Windows 经典文件夹浅黄色 */
const FOLDER_BOX_CLASS =
  "rounded-md border border-[#E5C76B] bg-[#FFF4CE] shadow-sm hover:shadow-md transition-shadow";

function formatDateInput(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function defaultDateRange() {
  const end = new Date();
  const start = new Date(end.getFullYear(), end.getMonth(), 1);
  return { start: formatDateInput(start), end: formatDateInput(end) };
}

function teacherLabel(user: AdminUserBrief, unnamedLabel: string): string {
  return user.display_name || user.email || unnamedLabel;
}

export function AdminTeacherGradingPage() {
  const { t, locale } = useLocale();
  const collatorLocale = locale === "en" ? "en-US" : "zh-CN";
  const unnamedLabel = t("admin.teacherGrading.unnamed");

  const [{ start: defaultStart, end: defaultEnd }] = useState(defaultDateRange);
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);
  const [teachers, setTeachers] = useState<AdminUserBrief[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [stats, setStats] = useState<GradingStatsResponse | null>(null);
  const [loadingTeachers, setLoadingTeachers] = useState(true);
  const [teachersError, setTeachersError] = useState(false);
  const [loadingStats, setLoadingStats] = useState(false);
  const [nameSearch, setNameSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);

  const teacherBtnRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const searchWrapRef = useRef<HTMLDivElement>(null);
  // 竞态守卫：切换用户/日期时丢弃过期响应
  const statsSeqRef = useRef(0);

  const groupedTeachers = useMemo(() => {
    const groups: Record<string, AdminUserBrief[]> = {};
    ROLE_ORDER.forEach((r) => {
      groups[r] = [];
    });
    teachers.forEach((user) => {
      const role = user.roles?.[0] || "任课教师";
      if (!groups[role]) groups[role] = [];
      groups[role].push(user);
    });
    ROLE_ORDER.forEach((r) => {
      groups[r]?.sort((a, b) =>
        teacherLabel(a, unnamedLabel).localeCompare(
          teacherLabel(b, unnamedLabel),
          collatorLocale,
        ),
      );
    });
    return groups;
  }, [teachers, unnamedLabel, collatorLocale]);

  const searchMatches = useMemo(() => {
    const q = nameSearch.trim().toLowerCase();
    if (!q) return [];
    return teachers
      .filter((user) => {
        const name = (user.display_name || "").toLowerCase();
        const email = (user.email || "").toLowerCase();
        return name.includes(q) || email.includes(q);
      })
      .slice(0, 12);
  }, [nameSearch, teachers]);

  const allUsersTableRows = useMemo(() => {
    return [...(stats?.all_users_summary.users ?? [])].sort((a, b) =>
      (a.display_name || a.email || "").localeCompare(
        b.display_name || b.email || "",
        collatorLocale,
      ),
    );
  }, [stats, collatorLocale]);

  const scrollToTeacher = useCallback((userId: string) => {
    setSelectedUserId(userId);
    window.requestAnimationFrame(() => {
      const btn = teacherBtnRefs.current.get(userId);
      btn?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }, []);

  const handleSelectFromSearch = useCallback(
    (userId: string) => {
      scrollToTeacher(userId);
      setNameSearch("");
      setSearchOpen(false);
    },
    [scrollToTeacher],
  );

  const loadTeachers = useCallback(async () => {
    setLoadingTeachers(true);
    setTeachersError(false);
    try {
      const list = await listAdminUsers();
      setTeachers(list);
      if (list.length > 0) {
        setSelectedUserId((prev) => prev || list[0].id);
      }
    } catch {
      // 不再静默降级为空：展示错误态，避免用户误以为「没有教师」
      setTeachers([]);
      setTeachersError(true);
    } finally {
      setLoadingTeachers(false);
    }
  }, []);

  const loadStats = useCallback(async () => {
    if (!selectedUserId || !startDate || !endDate) return;
    const seq = ++statsSeqRef.current;
    setLoadingStats(true);
    try {
      const data = await fetchAdminGradingStats({
        start_date: startDate,
        end_date: endDate,
        user_id: selectedUserId,
      });
      if (seq !== statsSeqRef.current) return; // 过期响应丢弃
      setStats(data);
    } catch (err: unknown) {
      if (seq !== statsSeqRef.current) return;
      setStats(null);
      toast.error(t("admin.teacherGrading.toast.statsLoadFailed"), {
        description:
          err instanceof Error
            ? err.message
            : typeof err === "string"
              ? err
              : undefined,
      });
    } finally {
      if (seq === statsSeqRef.current) setLoadingStats(false);
    }
  }, [selectedUserId, startDate, endDate]);

  useEffect(() => {
    loadTeachers();
  }, [loadTeachers]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!searchWrapRef.current?.contains(e.target as Node)) {
        setSearchOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const selectedUser = stats?.selected_user;
  const globalSummary = stats?.all_users_summary;

  return (
    <div className="flex gap-6 h-[calc(100vh-7rem)] min-h-[520px] overflow-x-auto">
      {/* 左侧主内容 */}
      <div className="flex-1 min-w-0 flex flex-col gap-4 overflow-hidden">
        <div>
          <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <FileText className="w-6 h-6 text-primary" />
            {t("admin.teacherGrading.title")}
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            {t("admin.teacherGrading.subtitle")}
          </p>
        </div>

        {/* 日期范围 + 名称搜索 */}
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex flex-wrap items-end gap-6">
              <div className="flex flex-wrap items-end gap-4">
                <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground pb-2">
                  <CalendarRange className="w-4 h-4" />
                  {t("admin.teacherGrading.dateRange.label")}
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">
                      {t("admin.teacherGrading.dateRange.start")}
                    </Label>
                    <Input
                      type="date"
                      value={startDate}
                      max={endDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className="w-[160px]"
                    />
                  </div>
                  <span className="text-muted-foreground pb-2">
                    {t("admin.teacherGrading.dateRange.to")}
                  </span>
                  <div className="space-y-1">
                    <Label className="text-xs text-muted-foreground">
                      {t("admin.teacherGrading.dateRange.end")}
                    </Label>
                    <Input
                      type="date"
                      value={endDate}
                      min={startDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="w-[160px]"
                    />
                  </div>
                </div>
              </div>

              <div
                ref={searchWrapRef}
                className="relative space-y-1 min-w-[200px] flex-1 max-w-xs"
              >
                <Label className="text-xs text-muted-foreground">
                  {t("admin.teacherGrading.search.label")}
                </Label>
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                  <Input
                    value={nameSearch}
                    placeholder={t("admin.teacherGrading.search.placeholder")}
                    className="pl-8"
                    onChange={(e) => {
                      setNameSearch(e.target.value);
                      setSearchOpen(true);
                    }}
                    onFocus={() => setSearchOpen(true)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && searchMatches.length > 0) {
                        handleSelectFromSearch(searchMatches[0].id);
                      }
                    }}
                  />
                </div>
                {searchOpen && nameSearch.trim() && (
                  <div className="absolute z-20 top-full left-0 right-0 mt-1 rounded-md border bg-popover shadow-md max-h-56 overflow-y-auto">
                    {searchMatches.length === 0 ? (
                      <p className="text-sm text-muted-foreground px-3 py-2">
                        {t("admin.teacherGrading.search.noResults")}
                      </p>
                    ) : (
                      searchMatches.map((user) => (
                        <button
                          key={user.id}
                          type="button"
                          className="w-full text-left px-3 py-2 text-sm hover:bg-muted transition-colors truncate"
                          onClick={() => handleSelectFromSearch(user.id)}
                        >
                          <span className="font-medium">
                            {teacherLabel(user, unnamedLabel)}
                          </span>
                          {user.email && user.display_name ? (
                            <span className="text-muted-foreground ml-2 text-xs">
                              {user.email}
                            </span>
                          ) : null}
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="flex-1 min-h-0 overflow-y-auto space-y-4 pr-1">
          {/* 上方：当前选中用户 */}
          <section>
            <h3 className="text-base font-semibold mb-3">
              {t("admin.teacherGrading.selectedTeacher.label")}
              {selectedUser?.display_name ||
                selectedUser?.email ||
                t("admin.teacherGrading.selectedTeacher.none")}
              {selectedUser?.email && selectedUser.display_name ? (
                <span className="text-sm font-normal text-muted-foreground ml-2">
                  {selectedUser.email}
                </span>
              ) : null}
            </h3>

            {loadingStats ? (
              <div className="flex items-center justify-center py-12 text-muted-foreground gap-2">
                <Loader2 className="w-5 h-5 animate-spin" />
                {t("admin.teacherGrading.loading.stats")}
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3 mb-4 max-w-md">
                  <Card className="bg-sky-50/50 border-sky-100">
                    <CardContent className="p-4 flex items-center gap-3">
                      <Upload className="w-8 h-8 text-sky-600" />
                      <div>
                        <p className="text-xs text-muted-foreground">
                          {t("admin.teacherGrading.stats.uploadTotal")}
                        </p>
                        <p className="text-2xl font-bold text-sky-700">
                          {selectedUser?.total_upload ?? 0}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                  <Card className="bg-emerald-50/50 border-emerald-100">
                    <CardContent className="p-4 flex items-center gap-3">
                      <CheckCircle2 className="w-8 h-8 text-emerald-600" />
                      <div>
                        <p className="text-xs text-muted-foreground">
                          {t("admin.teacherGrading.stats.gradeTotal")}
                        </p>
                        <p className="text-2xl font-bold text-emerald-700">
                          {selectedUser?.total_grade ?? 0}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">
                      {t("admin.teacherGrading.folders.title")}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-4">
                    {!selectedUser?.folders?.length ? (
                      <p className="text-sm text-muted-foreground">
                        {t("admin.teacherGrading.folders.empty")}
                      </p>
                    ) : (
                      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                        {selectedUser.folders.map((f) => (
                          <div
                            key={f.folder_safe}
                            className={cn(FOLDER_BOX_CLASS, "p-3")}
                          >
                            <div className="flex flex-col items-center text-center gap-2">
                              <Folder
                                className="w-10 h-10 text-[#E0A800] fill-[#FFE680]"
                                strokeWidth={1.25}
                              />
                              <p
                                className="text-sm font-medium leading-tight line-clamp-2 w-full"
                                title={f.folder_name}
                              >
                                {f.folder_name}
                              </p>
                              <div className="w-full pt-1 border-t border-[#E5C76B]/60 flex justify-around text-xs text-[#5C4B00]">
                                <span>
                                  {t("admin.teacherGrading.folders.upload")}{" "}
                                  <strong className="tabular-nums text-[#1a1a1a]">
                                    {f.upload_count}
                                  </strong>
                                </span>
                                <span>
                                  {t("admin.teacherGrading.folders.grade")}{" "}
                                  <strong className="tabular-nums text-[#1a1a1a]">
                                    {f.grade_count}
                                  </strong>
                                </span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </>
            )}
          </section>

          <Separator />

          {/* 下方：全部用户汇总（全局，不受切换用户影响） */}
          <section>
            <h3 className="text-base font-semibold mb-3">
              {t("admin.teacherGrading.summary.title", {
                start: startDate,
                end: endDate,
              })}
            </h3>
            <div className="grid grid-cols-2 gap-3 mb-4 max-w-md">
              <Card>
                <CardContent className="p-4">
                  <p className="text-xs text-muted-foreground">
                    {t("admin.teacherGrading.summary.uploadTotal")}
                  </p>
                  <p className="text-2xl font-bold">
                    {globalSummary?.total_upload ?? 0}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <p className="text-xs text-muted-foreground">
                    {t("admin.teacherGrading.summary.gradeTotal")}
                  </p>
                  <p className="text-2xl font-bold">
                    {globalSummary?.total_grade ?? 0}
                  </p>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">
                  {t("admin.teacherGrading.summary.tableTitle")}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {loadingStats ? (
                  <div className="flex items-center justify-center py-8 text-muted-foreground gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {t("admin.teacherGrading.summary.loading")}
                  </div>
                ) : !allUsersTableRows.length ? (
                  <p className="text-sm text-muted-foreground p-4">
                    {t("admin.teacherGrading.summary.empty")}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b bg-muted/40 text-left">
                          <th className="px-4 py-2 font-medium">
                            {t("admin.teacherGrading.summary.table.name")}
                          </th>
                          <th className="px-4 py-2 font-medium">
                            {t("admin.teacherGrading.summary.table.account")}
                          </th>
                          <th className="px-4 py-2 font-medium text-right w-28">
                            {t("admin.teacherGrading.summary.table.upload")}
                          </th>
                          <th className="px-4 py-2 font-medium text-right w-28">
                            {t("admin.teacherGrading.summary.table.grade")}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {allUsersTableRows.map((u) => (
                          <tr
                            key={u.user_id}
                            role="button"
                            tabIndex={0}
                            aria-label={t(
                              "admin.teacherGrading.summary.table.selectTeacher",
                              {
                                name: u.display_name || u.email || unnamedLabel,
                              },
                            )}
                            className={cn(
                              "border-b last:border-0 hover:bg-muted/20 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
                              u.user_id === selectedUserId && "bg-primary/5",
                            )}
                            onClick={() => scrollToTeacher(u.user_id)}
                            onKeyDown={(e) => {
                              if (e.target !== e.currentTarget) return;
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                scrollToTeacher(u.user_id);
                              }
                            }}
                          >
                            <td className="px-4 py-2">
                              {u.display_name || unnamedLabel}
                            </td>
                            <td className="px-4 py-2 text-muted-foreground">
                              {u.email}
                            </td>
                            <td className="px-4 py-2 text-right tabular-nums">
                              {u.upload_count}
                            </td>
                            <td className="px-4 py-2 text-right tabular-nums">
                              {u.grade_count}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </section>
        </div>
      </div>

      {/* 右侧教师名单 */}
      <aside className="w-[240px] shrink-0 border-l border-border pl-4 flex flex-col min-h-0">
        <h3 className="text-sm font-semibold mb-3 shrink-0">
          {t("admin.teacherGrading.teacherList.title")}
        </h3>
        <div className="flex-1 min-h-0 overflow-y-auto space-y-4 pr-1">
          {loadingTeachers ? (
            <div className="flex justify-center py-8 text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin" />
            </div>
          ) : teachersError ? (
            <div className="py-6 text-center text-sm text-destructive px-2">
              {t("admin.teacherGrading.loading.teachersFailed")}
            </div>
          ) : (
            ROLE_ORDER.map((role) => {
              const list = groupedTeachers[role];
              if (!list?.length) return null;
              return (
                <div key={role} className="space-y-1">
                  <div className="flex items-center gap-2 text-xs font-semibold text-foreground/80 border-b pb-1.5">
                    <div className="w-1.5 h-3.5 rounded-sm bg-primary/80" />
                    {translateSystemRole(locale, role)}
                    <span className="text-muted-foreground font-normal">
                      ({list.length})
                    </span>
                  </div>
                  <ul className="space-y-0.5">
                    {list.map((user) => {
                      const active = user.id === selectedUserId;
                      return (
                        <li key={user.id}>
                          <button
                            ref={(el) => {
                              if (el) teacherBtnRefs.current.set(user.id, el);
                              else teacherBtnRefs.current.delete(user.id);
                            }}
                            type="button"
                            onClick={() => setSelectedUserId(user.id)}
                            className={cn(
                              "w-full text-left px-2.5 py-2 rounded-md text-sm transition-colors truncate",
                              active
                                ? "bg-primary/10 text-primary font-medium"
                                : "text-muted-foreground hover:bg-muted hover:text-foreground",
                            )}
                            title={teacherLabel(user, unnamedLabel)}
                          >
                            {teacherLabel(user, unnamedLabel)}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })
          )}
        </div>
      </aside>
    </div>
  );
}
