import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import {
  BookOpen,
  Bell,
  LogOut,
  GraduationCap,
  BookMarked,
  ChevronDown,
  FolderCog,
  Settings,
  Clock,
  BarChart3,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useAuth } from "@/hooks/useAuth";
import { getTeacherDisplayName } from "@/lib/userDisplay";
import { useNavigate } from "react-router-dom";
import { useClasses } from "@/hooks/useClasses";
import { getSubjectsBySchoolLevel } from "@/components/SubjectTabs";
import { toast } from "@/hooks/use-toast";
import { useQuery } from "@tanstack/react-query";
import { listClasses } from "@/services/api";
import {
  listHomeRecentGrades,
  type HomeRecentItem,
} from "@/services/gradingApi";
import { useLocale } from "@/contexts/LocaleContext";
import { LanguageToggle } from "@/components/LanguageToggle";
import { BrandLogo } from "@/components/BrandLogo";
import {
  buildGradeLevels,
  translateGradeValue,
  translateRole,
  translateSchoolLevel,
  translateSubjectName,
} from "@/i18n";

/** 班级管理：白 + 浅蓝底、浅蓝边，悬停略加深；仅颜色短过渡，避免夸张动效 */
const classManageGlassBtnClass =
  "border border-sky-200/90 bg-gradient-to-b from-white to-sky-50/90 text-foreground " +
  "shadow-[0_1px_2px_rgba(14,165,233,0.06)] " +
  "transition-colors duration-150 ease-out " +
  "hover:from-sky-50 hover:to-sky-100/95 hover:border-sky-300/90 hover:text-foreground";

interface NotificationItem {
  id: number;
  title: string;
  time: string;
  read: boolean;
  icon: LucideIcon;
}

// Real stats will be fetched from database

interface TopHeaderProps {
  className?: string;
  selectedSchoolLevel: string;
  selectedGrade: string;
  selectedClass: string;
  selectedSubject: string;
  onSchoolLevelChange: (level: string) => void;
  onGradeChange: (grade: string) => void;
  onClassChange: (cls: string) => void;
  onSubjectChange: (subject: string) => void;
  onManageClasses?: () => void;
  onNavChange?: (id: string) => void;
  showTeachingFilters?: boolean;
  /** 单科老师端：科目锁定，顶部显示只读「我的学科」徽章、隐藏科目下拉 */
  subjectLocked?: string;
}

export function TopHeader({
  className,
  selectedSchoolLevel,
  selectedGrade,
  selectedClass,
  selectedSubject,
  onSchoolLevelChange,
  onGradeChange,
  onClassChange,
  onSubjectChange,
  onManageClasses,
  onNavChange,
  showTeachingFilters = true,
  subjectLocked,
}: TopHeaderProps) {
  const { signOut, user } = useAuth();
  const { t, locale } = useLocale();
  const navigate = useNavigate();

  const gradeLevels = useMemo(() => buildGradeLevels(locale), [locale]);
  const currentLevel = gradeLevels.find((l) => l.id === selectedSchoolLevel);
  const grades = currentLevel?.grades || [];
  const { data: classes = [], isLoading: classesLoading } = useClasses(
    selectedSchoolLevel,
    selectedGrade,
  );
  const subjects = getSubjectsBySchoolLevel(selectedSchoolLevel);

  // 「我的数据」统计统一走 FastAPI 后端（班级/学生数来自 /classes，本周批改来自 /grading/home/recent），
  // 不再读取 Supabase exam_scores（与 FastAPI 数据源不一致，恒为 0）。
  const { data: userStats } = useQuery({
    queryKey: ["user-stats", user?.id],
    queryFn: async () => {
      if (!user?.id)
        return {
          classCount: 0,
          studentCount: 0,
          gradedThisWeek: 0,
        };

      const [classesRes, recentRes] = await Promise.all([
        listClasses(),
        listHomeRecentGrades().catch(() => ({
          ok: false,
          items: [] as HomeRecentItem[],
        })),
      ]);
      const classCount = classesRes.length;
      const studentCount = classesRes.reduce(
        (sum, c) => sum + (c.student_count || 0),
        0,
      );
      const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
      const gradedThisWeek = recentRes.items.filter((it) => {
        const created = new Date(it.created_at).getTime();
        return !Number.isNaN(created) && created >= weekAgo;
      }).length;
      return { classCount, studentCount, gradedThisWeek };
    },
    enabled: !!user?.id,
  });

  const stats = userStats ?? {
    classCount: 0,
    studentCount: 0,
    gradedThisWeek: 0,
  };

  const handleSignOut = async () => {
    await signOut();
    navigate("/auth");
  };

  // 通知暂为空：后端通知体系接入前不展示任何占位数据，避免虚假未读
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [showAll, setShowAll] = useState(false);
  const visibleNotifications = showAll
    ? notifications
    : notifications.slice(0, 3);
  const unreadCount = notifications.filter((n) => !n.read).length;

  const handleMarkAllRead = () => {
    const hasUnread = notifications.some((n) => !n.read);
    if (!hasUnread) {
      toast({ title: t("home.notifications.noneUnread") });
      return;
    }
    setNotifications((ns) => ns.map((n) => ({ ...n, read: true })));
    toast({ title: t("home.notifications.markedAllRead") });
  };

  const handleToggleViewAll = () => {
    const next = !showAll;
    setShowAll(next);
    toast({
      title: next
        ? t("home.notifications.viewAllExpanded")
        : t("home.notifications.viewAllCollapsed"),
    });
  };

  const displayName = getTeacherDisplayName(user);

  const getGreeting = () => {
    const hour = new Date().getHours();
    let greetingKey = "header.greeting.evening";
    if (hour < 6) greetingKey = "header.greeting.dawn";
    else if (hour < 12) greetingKey = "header.greeting.morning";
    else if (hour < 14) greetingKey = "header.greeting.noon";
    else if (hour < 18) greetingKey = "header.greeting.afternoon";
    return `${displayName}${t(greetingKey)}`;
  };

  return (
    <header
      className={cn(
        "top-nav bg-sidebar border-b border-sidebar-border sticky top-0 z-50 shadow-[0_2px_12px_-6px_rgba(148,163,184,0.3)]",
        className,
      )}
    >
      {/* Row 1: Logo + User Actions */}
      <div className="h-14 px-6 flex items-center justify-between border-b border-sidebar-border/50">
        <div
          className="flex items-center gap-3 min-w-0 cursor-pointer group"
          onClick={() => navigate("/")}
        >
          <BrandLogo
            className="w-8 h-8 rounded-lg bg-white group-hover:opacity-90 transition-opacity"
            alt=""
          />
          <span className="text-[15px] font-semibold text-foreground tracking-tight truncate group-hover:text-primary/80 transition-colors">
            {getGreeting()}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {onManageClasses && (
            <Button
              variant="outline"
              size="sm"
              className={cn("h-9 gap-1.5 text-sm", classManageGlassBtnClass)}
              onClick={onManageClasses}
            >
              <FolderCog className="w-4 h-4 shrink-0" strokeWidth={1.75} />
              <span className="hidden lg:inline">
                {t("header.classManage")}
              </span>
            </Button>
          )}

          {onManageClasses && (
            <div className="w-px h-5 bg-border mx-1.5 shrink-0" />
          )}

          {/* Notifications */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t("header.notifications")}
                className="h-9 w-9 relative text-muted-foreground hover:bg-sidebar-accent hover:text-foreground rounded-lg"
              >
                <Bell className="w-4 h-4" strokeWidth={1.75} />
                {unreadCount > 0 && (
                  <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 rounded-full bg-destructive text-destructive-foreground text-[10px] font-bold flex items-center justify-center">
                    {unreadCount}
                  </span>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-80">
              <DropdownMenuLabel className="flex items-center justify-between">
                <span>{t("header.notifications")}</span>
                <button
                  type="button"
                  onClick={handleMarkAllRead}
                  className="text-xs text-primary hover:underline font-normal"
                >
                  {t("header.markAllRead")}
                </button>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {visibleNotifications.length === 0 ? (
                <div className="px-4 py-8 text-sm text-muted-foreground text-center">
                  {t("home.notifications.empty")}
                </div>
              ) : (
                visibleNotifications.map((notification) => {
                  const Icon = notification.icon;
                  return (
                    <DropdownMenuItem
                      key={notification.id}
                      className="flex items-start gap-3 py-2.5 cursor-pointer"
                    >
                      <div
                        className={cn(
                          "w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5",
                          notification.read ? "bg-muted" : "bg-primary/10",
                        )}
                      >
                        <Icon
                          className={cn(
                            "w-3.5 h-3.5",
                            notification.read
                              ? "text-muted-foreground"
                              : "text-primary",
                          )}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p
                          className={cn(
                            "text-sm leading-snug",
                            !notification.read && "font-medium",
                          )}
                        >
                          {notification.title}
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {notification.time}
                        </p>
                      </div>
                      {!notification.read && (
                        <div className="w-2 h-2 rounded-full bg-primary shrink-0 mt-1.5" />
                      )}
                    </DropdownMenuItem>
                  );
                })
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={handleToggleViewAll}
                className="justify-center text-primary text-xs cursor-pointer"
              >
                {t("header.viewAllNotifications")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* 「我的」个人中心 */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-9 gap-1.5 text-muted-foreground hover:bg-sidebar-accent hover:text-foreground rounded-lg"
              >
                <Avatar className="w-7 h-7">
                  <AvatarFallback className="bg-primary/10 text-primary text-xs font-medium">
                    {displayName.charAt(0)}
                  </AvatarFallback>
                </Avatar>
                <span className="hidden md:inline text-sm font-medium text-foreground/90">
                  {displayName}
                </span>
                <ChevronDown className="w-3.5 h-3.5" strokeWidth={1.75} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              {/* 用户信息 */}
              <DropdownMenuLabel className="font-normal">
                <div className="flex items-center gap-3">
                  <Avatar className="w-9 h-9">
                    <AvatarFallback className="bg-primary/10 text-primary text-sm font-semibold">
                      {displayName.charAt(0)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex flex-col gap-1.5">
                    <div>
                      <p className="text-sm font-semibold">{displayName}</p>
                      <p className="text-xs text-muted-foreground">
                        {user?.email || "—"}
                      </p>
                    </div>
                    {user?.job_title && (
                      <p className="text-xs text-sky-600 font-medium bg-sky-50 px-1.5 py-0.5 rounded w-fit mt-0.5">
                        {user.job_title}
                      </p>
                    )}
                    {user?.roles && user.roles.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-0.5">
                        {user.roles.map((r) => (
                          <span
                            key={r}
                            className="px-1.5 py-0.5 rounded bg-primary/10 text-primary text-[10px] border border-primary/20"
                          >
                            {translateRole(locale, r)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />

              {/* 我的数据 */}
              <DropdownMenuLabel className="text-xs text-muted-foreground">
                {t("header.myData")}
              </DropdownMenuLabel>
              <div className="px-2 pb-2 grid grid-cols-2 gap-1.5">
                <div className="flex items-center gap-1.5 rounded-md bg-muted/50 px-2.5 py-1.5">
                  <BarChart3 className="w-3.5 h-3.5 text-primary" />
                  <div>
                    <p className="text-xs font-medium">
                      {stats.gradedThisWeek}
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      {t("header.gradedThisWeek")}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 rounded-md bg-muted/50 px-2.5 py-1.5">
                  <BookMarked className="w-3.5 h-3.5 text-blue-500" />
                  <div>
                    <p className="text-xs font-medium">{stats.classCount}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {t("header.managedClasses")}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 rounded-md bg-muted/50 px-2.5 py-1.5">
                  <Users className="w-3.5 h-3.5 text-green-500" />
                  <div>
                    <p className="text-xs font-medium">{stats.studentCount}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {t("header.totalStudents")}
                    </p>
                  </div>
                </div>
              </div>
              <DropdownMenuSeparator />

              {/* 快捷入口 */}
              <DropdownMenuLabel className="text-xs text-muted-foreground">
                {t("header.quickLinks")}
              </DropdownMenuLabel>
              <DropdownMenuItem
                onClick={() => onNavChange?.("class-dashboard")}
              >
                <BarChart3 className="w-4 h-4 mr-2" />
                {t("header.dashboard")}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onNavChange?.("home")}>
                <BookOpen className="w-4 h-4 mr-2" />
                {t("header.startGrading")}
              </DropdownMenuItem>
              <DropdownMenuSeparator />

              <DropdownMenuItem
                onClick={handleSignOut}
                className="text-destructive focus:text-destructive cursor-pointer"
              >
                <LogOut className="w-4 h-4 mr-2" />
                {t("header.signOut")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Row 2: School Level + Selectors */}
      <div
        data-tour="top-filters"
        className="h-12 px-6 flex w-full items-center gap-4"
      >
        {showTeachingFilters && (
          <>
            <div className="flex items-center gap-0.5 bg-muted/60 rounded-lg p-0.5 shrink-0 border border-border/40">
              {gradeLevels.map((level) => {
                const isSelected = selectedSchoolLevel === level.id;
                return (
                  <button
                    key={level.id}
                    onClick={() => {
                      onSchoolLevelChange(level.id);
                      onGradeChange(level.grades[0].value);
                    }}
                    className={cn(
                      "px-3.5 h-8 rounded-md text-[13px] font-medium transition-all duration-200",
                      isSelected
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground hover:bg-white/70",
                    )}
                  >
                    {translateSchoolLevel(locale, level.id)}
                  </button>
                );
              })}
            </div>

            <div className="w-px h-5 bg-border shrink-0" />

            <div className="flex items-center gap-2">
              <Select value={selectedGrade} onValueChange={onGradeChange}>
                <SelectTrigger className="w-[120px] h-9 text-sm bg-card border-border/80 hover:border-primary/60 focus-within:border-primary transition-colors shadow-sm">
                  <div className="flex items-center gap-1.5">
                    <GraduationCap
                      className="w-4 h-4 text-muted-foreground"
                      strokeWidth={1.75}
                    />
                    <SelectValue placeholder={t("header.selectGrade")} />
                  </div>
                </SelectTrigger>
                <SelectContent>
                  {grades.map((grade) => (
                    <SelectItem key={grade.value} value={grade.value}>
                      {translateGradeValue(
                        locale,
                        selectedSchoolLevel,
                        grade.value,
                      )}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={selectedClass} onValueChange={onClassChange}>
                <SelectTrigger className="w-[180px] h-9 text-sm bg-card border-border/80 hover:border-primary/60 focus-within:border-primary transition-colors shadow-sm">
                  <div className="flex items-center gap-1.5">
                    <BookMarked
                      className="w-4 h-4 text-muted-foreground"
                      strokeWidth={1.75}
                    />
                    <SelectValue
                      placeholder={
                        classesLoading
                          ? t("header.loadingClasses")
                          : classes.length === 0
                            ? t("header.noClasses")
                            : t("header.selectClass")
                      }
                    />
                  </div>
                </SelectTrigger>
                <SelectContent className="max-h-60">
                  {classes.map((cls) => (
                    <SelectItem key={cls.id} value={cls.id}>
                      {cls.name}（
                      {t("header.studentsCount", { count: cls.student_count })}
                      ）
                    </SelectItem>
                  ))}
                  {classes.length === 0 && (
                    <div className="px-2 py-3 text-sm text-muted-foreground text-center">
                      {t("header.noClassesHint")}
                    </div>
                  )}
                </SelectContent>
              </Select>

              {subjectLocked ? (
                <div className="flex items-center gap-1.5 h-9 px-3 rounded-lg bg-primary/10 border border-primary/20 text-primary text-sm font-medium shrink-0">
                  <BookOpen className="w-4 h-4" strokeWidth={1.75} />
                  <span>
                    我的学科：{translateSubjectName(locale, subjectLocked)}
                  </span>
                </div>
              ) : (
                <Select value={selectedSubject} onValueChange={onSubjectChange}>
                  <SelectTrigger className="w-[110px] h-9 text-sm bg-card border-border/80 hover:border-primary/60 focus-within:border-primary transition-colors shadow-sm">
                    <div className="flex items-center gap-1.5">
                      <BookOpen
                        className="w-4 h-4 text-muted-foreground"
                        strokeWidth={1.75}
                      />
                      <SelectValue placeholder={t("header.selectSubject")} />
                    </div>
                  </SelectTrigger>
                  <SelectContent>
                    {subjects.map((subject) => (
                      <SelectItem key={subject.id} value={subject.name}>
                        {translateSubjectName(locale, subject.name)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          </>
        )}

        <LanguageToggle className="ml-auto shrink-0 bg-card hover:bg-muted/70" />
      </div>
    </header>
  );
}
