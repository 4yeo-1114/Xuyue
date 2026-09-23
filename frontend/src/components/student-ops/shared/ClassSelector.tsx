import { useQuery } from "@tanstack/react-query";
import { listClasses } from "@/services/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLocale } from "@/contexts/LocaleContext";
import { Loader2 } from "lucide-react";

interface ClassSelectorProps {
  value: string;
  onChange: (classId: string) => void;
  className?: string;
}

/** 班级选择器：读取全部可访问班级，展示「年级 + 班级名」 */
export function ClassSelector({ value, onChange, className }: ClassSelectorProps) {
  const { t } = useLocale();
  const { data: classes = [], isLoading } = useQuery({
    queryKey: ["student-ops-classes"],
    queryFn: () => listClasses(),
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> {t("studentOps.loading")}
      </div>
    );
  }

  return (
    <Select value={value || undefined} onValueChange={onChange}>
      <SelectTrigger className={className || "w-[220px]"}>
        <SelectValue placeholder={t("studentOps.selectClass")} />
      </SelectTrigger>
      <SelectContent>
        {classes.length === 0 && (
          <div className="px-2 py-3 text-center text-sm text-muted-foreground">
            {t("studentOps.empty")}
          </div>
        )}
        {classes.map((c) => (
          <SelectItem key={c.id} value={c.id}>
            {c.grade}
            {c.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
