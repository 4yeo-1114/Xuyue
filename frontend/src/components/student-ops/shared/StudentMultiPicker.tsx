import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listStudentsByClass } from "@/services/api";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/contexts/LocaleContext";
import { Loader2, Search } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";

interface StudentMultiPickerProps {
  classId: string;
  selected: string[];
  onChange: (ids: string[]) => void;
  excludeIds?: string[];
  maxHeight?: string;
}

/** 多选学生组件：搜索 + 全选 + 勾选列表 */
export function StudentMultiPicker({
  classId,
  selected,
  onChange,
  excludeIds = [],
  maxHeight = "240px",
}: StudentMultiPickerProps) {
  const { t } = useLocale();
  const [keyword, setKeyword] = useState("");
  const { data: students = [], isLoading } = useQuery({
    queryKey: ["students", classId],
    queryFn: () => listStudentsByClass(classId),
    enabled: !!classId,
  });

  const options = useMemo(
    () => students.filter((s) => !excludeIds.includes(s.id)),
    [students, excludeIds]
  );
  const filtered = useMemo(
    () =>
      keyword.trim()
        ? options.filter(
            (s) => s.name.includes(keyword.trim()) || (s.student_number || "").includes(keyword.trim())
          )
        : options,
    [options, keyword]
  );

  const toggle = (id: string) => {
    if (selected.includes(id)) {
      onChange(selected.filter((x) => x !== id));
    } else {
      onChange([...selected, id]);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> {t("studentOps.loading")}
      </div>
    );
  }

  const allChecked = filtered.length > 0 && filtered.every((s) => selected.includes(s.id));

  const toggleAll = () => {
    if (allChecked) {
      onChange(selected.filter((id) => !filtered.some((s) => s.id === id)));
    } else {
      const ids = new Set(selected);
      filtered.forEach((s) => ids.add(s.id));
      onChange([...ids]);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-8 h-9"
            placeholder={t("studentOps.search")}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
        <Button type="button" variant="outline" size="sm" className="h-9" onClick={toggleAll}>
          {t("studentOps.all")}
        </Button>
      </div>
      <ScrollArea style={{ height: maxHeight }} className="rounded-md border border-border/60">
        <div className="p-2">
          {filtered.length === 0 && (
            <div className="py-6 text-center text-sm text-muted-foreground">{t("studentOps.empty")}</div>
          )}
          {filtered.map((s) => (
            <label
              key={s.id}
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent/60 cursor-pointer"
            >
              <Checkbox
                checked={selected.includes(s.id)}
                onCheckedChange={() => toggle(s.id)}
              />
              <span className="truncate">{s.name}</span>
              {s.student_number && (
                <span className="text-xs text-muted-foreground">{s.student_number}</span>
              )}
            </label>
          ))}
        </div>
      </ScrollArea>
      <div className="text-xs text-muted-foreground">
        {t("studentOps.selectedCount", { count: selected.length })}
      </div>
    </div>
  );
}
