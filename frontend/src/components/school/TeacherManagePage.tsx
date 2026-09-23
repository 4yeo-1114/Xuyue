import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { useClasses } from "@/hooks/useClasses";
import { listClassTeachers } from "@/services/api";
import type { ClassTeacherRecord } from "@/types/api";
import { translateSubjectName } from "@/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { GraduationCap, Inbox, RefreshCw, Search, UserCog } from "lucide-react";

/** 班级维度教师行：ClassTeacherRecord + 所在班级信息 */
interface ClassTeacherRow extends ClassTeacherRecord {
  classId: string;
  className: string;
}

interface ClassAssignment {
  classId: string;
  className: string;
  role: string;
}

interface TeacherEntry {
  key: string;
  userId: string;
  email: string;
  displayName: string;
  subjects: string[];
  assignments: ClassAssignment[];
}

const ALL_CLASSES = "__all__";

function roleTone(role: string): string {
  switch ((role || "").toLowerCase()) {
    case "head":
      return "bg-sky-50 text-sky-700 border-sky-200";
    case "deputy":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

export function TeacherManagePage() {
  const { t, locale } = useLocale();
  const { data: classes = [], isLoading: classesLoading } = useClasses();

  const [selectedClassId, setSelectedClassId] = useState<string>(ALL_CLASSES);
  const [search, setSearch] = useState("");

  const classesKey = useMemo(
    () =>
      classes
        .map((c) => c.id)
        .sort()
        .join(","),
    [classes],
  );

  // 全校教师花名册：逐个班级拉取协作教师后按用户合并（Promise.allSettled，
  // 单个班级失败不影响其余班级数据）
  const {
    data: rows = [],
    isLoading: teachersLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["school-teacher-roster", classesKey],
    queryFn: async () => {
      const settled = await Promise.allSettled(
        classes.map(async (c) => {
          const teachers = await listClassTeachers(c.id);
          return teachers.map((t): ClassTeacherRow => ({
            ...t,
            classId: c.id,
            className: c.name,
          }));
        }),
      );
      return settled.flatMap((r) => (r.status === "fulfilled" ? r.value : []));
    },
    enabled: classes.length > 0,
    staleTime: 30_000,
  });

  const roster = useMemo<TeacherEntry[]>(() => {
    const map = new Map<string, TeacherEntry>();
    for (const row of rows) {
      const key = row.user_id || row.email;
      if (!key) continue;
      const subject =
        row.subject && row.subject !== "__CLEAR__" ? row.subject : null;
      const assignment: ClassAssignment = {
        classId: row.classId,
        className: row.className,
        role: row.role,
      };
      const existing = map.get(key);
      if (existing) {
        existing.assignments.push(assignment);
        if (subject && !existing.subjects.includes(subject)) {
          existing.subjects.push(subject);
        }
      } else {
        map.set(key, {
          key,
          userId: row.user_id,
          email: row.email,
          displayName: row.display_name || row.email?.split("@")[0] || "—",
          subjects: subject ? [subject] : [],
          assignments: [assignment],
        });
      }
    }
    return [...map.values()];
  }, [rows]);

  const filtered = useMemo(() => {
    const byClass =
      selectedClassId === ALL_CLASSES
        ? roster
        : roster.filter((t) =>
            t.assignments.some((a) => a.classId === selectedClassId),
          );
    const q = search.trim().toLowerCase();
    if (!q) return byClass;
    return byClass.filter(
      (t) =>
        t.displayName.toLowerCase().includes(q) ||
        t.email.toLowerCase().includes(q),
    );
  }, [roster, selectedClassId, search]);

  const selectedClass = classes.find((c) => c.id === selectedClassId) || null;

  const roleLabel = (role: string): string => {
    switch ((role || "").toLowerCase()) {
      case "head":
        return t("teacherManage.role.head");
      case "deputy":
        return t("teacherManage.role.deputy");
      case "teacher":
        return t("teacherManage.role.teacher");
      default:
        return role || t("teacherManage.role.unknown");
    }
  };

  const renderRoleBadges = (entry: TeacherEntry) => {
    const assignments =
      selectedClassId === ALL_CLASSES
        ? entry.assignments
        : entry.assignments.filter((a) => a.classId === selectedClassId);
    const distinct = assignments.filter(
      (a, i, arr) => arr.findIndex((x) => x.role === a.role) === i,
    );
    return (
      <div className="flex flex-wrap gap-1">
        {distinct.map((a, i) => (
          <span
            key={`${a.role}-${i}`}
            className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${roleTone(a.role)}`}
            title={a.className}
          >
            {roleLabel(a.role)}
          </span>
        ))}
      </div>
    );
  };

  const renderClassNames = (entry: TeacherEntry) => {
    const assignments =
      selectedClassId === ALL_CLASSES
        ? entry.assignments
        : entry.assignments.filter((a) => a.classId === selectedClassId);
    if (assignments.length === 0) return "—";
    return assignments.map((a) => a.className).join("、");
  };

  const subjectText = (entry: TeacherEntry) =>
    entry.subjects.length
      ? entry.subjects.map((s) => translateSubjectName(locale, s)).join("、")
      : t("teacherManage.subjectUnset");

  const isLoading = classesLoading || (classes.length > 0 && teachersLoading);

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500 pb-10">
      {/* 页头 */}
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <UserCog className="w-6 h-6 text-primary" />
            {t("teacherManage.title")}
          </h2>
          <p className="text-muted-foreground mt-1">
            {t("teacherManage.subtitle")}
          </p>
        </div>
        <Badge variant="secondary" className="px-3 py-1">
          {t("teacherManage.count", { count: filtered.length })}
        </Badge>
      </div>

      {/* 筛选区 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            type="search"
            placeholder={t("teacherManage.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 bg-card"
          />
        </div>
        <Select value={selectedClassId} onValueChange={setSelectedClassId}>
          <SelectTrigger className="w-[220px]">
            <SelectValue
              placeholder={t("teacherManage.filter.classPlaceholder")}
            />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_CLASSES}>
              {t("teacherManage.filter.allClasses")}
            </SelectItem>
            {classes.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* 内容区 */}
      {isLoading ? (
        <Card>
          <CardContent className="p-6 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : classes.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            <GraduationCap className="w-8 h-8 mx-auto mb-2 text-muted-foreground/40" />
            <p className="text-sm font-medium">
              {t("teacherManage.noClasses")}
            </p>
            <p className="text-xs mt-1">{t("teacherManage.noClassesHint")}</p>
          </CardContent>
        </Card>
      ) : isError ? (
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            <Inbox className="w-8 h-8 mx-auto mb-2 text-muted-foreground/40" />
            <p className="text-sm">{t("teacherManage.error")}</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3 gap-1.5"
              onClick={() => refetch()}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              {t("teacherManage.errorRetry")}
            </Button>
          </CardContent>
        </Card>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            <Inbox className="w-8 h-8 mx-auto mb-2 text-muted-foreground/40" />
            <p className="text-sm">{t("teacherManage.empty")}</p>
            <p className="text-xs mt-1">{t("teacherManage.emptyHint")}</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold">
              {selectedClass
                ? selectedClass.name
                : t("teacherManage.filter.allClasses")}
            </CardTitle>
            <CardDescription>
              {t("teacherManage.count", { count: filtered.length })}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("teacherManage.table.name")}</TableHead>
                  <TableHead>{t("teacherManage.table.account")}</TableHead>
                  <TableHead>{t("teacherManage.table.role")}</TableHead>
                  <TableHead>{t("teacherManage.table.classes")}</TableHead>
                  <TableHead>{t("teacherManage.table.subject")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((entry) => (
                  <TableRow key={entry.key}>
                    <TableCell className="font-medium">
                      {entry.displayName}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {entry.email}
                    </TableCell>
                    <TableCell>{renderRoleBadges(entry)}</TableCell>
                    <TableCell>{renderClassNames(entry)}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {subjectText(entry)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
