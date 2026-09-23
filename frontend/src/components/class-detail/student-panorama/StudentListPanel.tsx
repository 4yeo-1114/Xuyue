import { useState, useMemo, useEffect, useRef } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface StudentSummary {
  name: string;
  studentNumber: string;
  targetScore?: number | null;
  currentScore?: number | null;
  /** 当前掌握分数（StudentProfilePanel 使用，可能未提供） */
  score?: number | null;
}

interface StudentListPanelProps {
  students: StudentSummary[];
  selectedName: string | null;
  onSelect: (name: string) => void;
  initialStudentName?: string;
}

type SortKey =
  "default" | "name" | "gap-desc" | "gap-asc" | "score-desc" | "score-asc";

export function StudentListPanel({
  students,
  selectedName,
  onSelect,
  initialStudentName,
}: StudentListPanelProps) {
  const { t } = useLocale();

  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("default");
  const listRef = useRef<HTMLDivElement>(null);

  // Auto-select initial student
  useEffect(() => {
    if (initialStudentName) {
      onSelect(initialStudentName);
    }
  }, [initialStudentName]);

  // Read persisted sort key on mount
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem("student_panorama_sort_key");
    } catch {
      saved = null;
    }
    if (
      saved &&
      [
        "default",
        "name",
        "gap-desc",
        "gap-asc",
        "score-desc",
        "score-asc",
      ].includes(saved)
    ) {
      setSortKey(saved as SortKey);
    }
  }, []);

  const handleSortChange = (v: SortKey) => {
    setSortKey(v);
    try {
      localStorage.setItem("student_panorama_sort_key", v);
    } catch {
      // 浏览器存储不可用时(隐私模式/配额),静默忽略,排序仍即时生效
    }
  };

  const filtered = useMemo(() => {
    let arr = students;
    if (search) {
      const q = search.toLowerCase();
      arr = arr.filter(
        (s) => s.name.includes(q) || s.studentNumber.includes(q),
      );
    }

    // Sort
    const sorted = [...arr];
    if (sortKey === "name") {
      sorted.sort((a, b) => a.name.localeCompare(b.name, "zh"));
    } else if (sortKey === "gap-desc" || sortKey === "gap-asc") {
      sorted.sort((a, b) => {
        const gapA =
          a.targetScore != null && a.currentScore != null
            ? a.targetScore - a.currentScore
            : -9999;
        const gapB =
          b.targetScore != null && b.currentScore != null
            ? b.targetScore - b.currentScore
            : -9999;

        if (sortKey === "gap-desc") {
          return gapB - gapA;
        } else {
          // Put the ones with valid gaps before the ones without valid gaps (-9999) when ascending
          if (gapA === -9999 && gapB !== -9999) return 1;
          if (gapA !== -9999 && gapB === -9999) return -1;
          return gapA - gapB;
        }
      });
    } else if (sortKey === "score-desc" || sortKey === "score-asc") {
      sorted.sort((a, b) => {
        const scoreA = a.currentScore != null ? a.currentScore : -9999;
        const scoreB = b.currentScore != null ? b.currentScore : -9999;

        if (sortKey === "score-desc") {
          return scoreB - scoreA;
        } else {
          if (scoreA === -9999 && scoreB !== -9999) return 1;
          if (scoreA !== -9999 && scoreB === -9999) return -1;
          return scoreA - scoreB;
        }
      });
    }
    return sorted;
  }, [students, search, sortKey]);

  const getScoreColor = (
    target: number | null | undefined,
    current: number | null | undefined,
  ) => {
    if (target == null || current == null || target === 0)
      return "text-primary";
    const ratio = (target - current) / target;
    // 语义与真实学情一致：达到/超过目标 = 良好(绿)，差距越大 = 越偏红橙
    if (current >= target) return "text-emerald-500"; // 已达到/超过目标，绿色
    if (ratio > 0.5) return "text-destructive"; // 差比高于 50%，严重落后，红色
    if (ratio >= 0.2) return "text-orange-500"; // 差比 20% - 49%，橙色
    return "text-emerald-500"; // 差比 0% - 19%，接近目标，绿色
  };

  return (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="p-3 border-b border-border/50 space-y-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("studentAnalysis.searchPlaceholder")}
            className="pl-9 h-9 text-sm"
          />
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={sortKey}
            onValueChange={(v) => handleSortChange(v as SortKey)}
          >
            <SelectTrigger className="h-7 text-xs w-[110px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">
                {t("studentAnalysis.list.defaultSort")}
              </SelectItem>
              <SelectItem value="name">
                {t("studentAnalysis.list.nameSort")}
              </SelectItem>
              <SelectItem value="score-desc">
                {t("studentAnalysis.list.scoreDesc")}
              </SelectItem>
              <SelectItem value="score-asc">
                {t("studentAnalysis.list.scoreAsc")}
              </SelectItem>
              <SelectItem value="gap-desc">
                {t("studentAnalysis.list.gapDesc")}
              </SelectItem>
              <SelectItem value="gap-asc">
                {t("studentAnalysis.list.gapAsc")}
              </SelectItem>
            </SelectContent>
          </Select>
          <span className="text-xs text-muted-foreground ml-auto">
            {t("studentAnalysis.list.count", { count: filtered.length })}
          </span>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5" ref={listRef}>
        {filtered.map((s) => {
          const isSelected = selectedName === s.name;

          return (
            <button
              key={s.name}
              className={cn(
                "w-full text-left px-4 py-3 rounded-xl border transition-all duration-200 cursor-pointer flex items-center justify-between",
                isSelected
                  ? "bg-primary/10 border-primary shadow-md -translate-y-0.5 ring-1 ring-primary/30"
                  : "bg-card border-border/50 hover:bg-muted/60 hover:border-primary/30 hover:-translate-y-0.5 hover:shadow-sm",
              )}
              onClick={() => onSelect(s.name)}
            >
              <div className="flex flex-col gap-1">
                <span
                  className={cn(
                    "text-sm font-semibold transition-colors",
                    isSelected ? "text-primary" : "text-foreground",
                  )}
                >
                  {s.name}
                </span>
                <span className="text-[12px] text-muted-foreground">
                  {t("studentAnalysis.list.studentNumber", {
                    number: s.studentNumber,
                  })}
                </span>
              </div>
              <div className="flex flex-col items-end gap-1">
                <span className="text-[12px] font-medium text-muted-foreground">
                  {t("studentAnalysis.list.targetCurrent")}
                </span>
                <span className="text-base font-bold tracking-tight">
                  <span className="text-foreground">
                    {s.targetScore != null ? s.targetScore : "-"}
                  </span>
                  <span className="text-muted-foreground/40 mx-1">/</span>
                  <span
                    className={getScoreColor(s.targetScore, s.currentScore)}
                  >
                    {s.currentScore != null ? s.currentScore : "-"}
                  </span>
                </span>
              </div>
            </button>
          );
        })}
        {filtered.length === 0 && (
          <div className="text-center py-12 text-sm text-muted-foreground">
            {t("studentAnalysis.list.empty")}
          </div>
        )}
      </div>
    </div>
  );
}
