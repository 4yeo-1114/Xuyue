import { useQuery } from "@tanstack/react-query";
import { listStudentsByClass } from "@/services/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLocale } from "@/contexts/LocaleContext";
import { Loader2 } from "lucide-react";

interface StudentPickerProps {
  classId: string;
  value: string;
  onChange: (studentId: string) => void;
  placeholder?: string;
  excludeIds?: string[];
  className?: string;
}

/** 单选学生选择器（按班级拉取学生） */
export function StudentPicker({
  classId,
  value,
  onChange,
  placeholder,
  excludeIds = [],
  className,
}: StudentPickerProps) {
  const { t } = useLocale();
  const { data: students = [], isLoading } = useQuery({
    queryKey: ["students", classId],
    queryFn: () => listStudentsByClass(classId),
    enabled: !!classId,
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> {t("studentOps.loading")}
      </div>
    );
  }

  const options = students.filter((s) => !excludeIds.includes(s.id));

  return (
    <Select value={value || undefined} onValueChange={onChange}>
      <SelectTrigger className={className || "w-full"}>
        <SelectValue placeholder={placeholder || t("studentOps.selectStudent")} />
      </SelectTrigger>
      <SelectContent>
        {options.length === 0 && (
          <div className="px-2 py-3 text-center text-sm text-muted-foreground">
            {t("studentOps.empty")}
          </div>
        )}
        {options.map((s) => (
          <SelectItem key={s.id} value={s.id}>
            {s.name}
            {s.student_number ? `（${s.student_number}）` : ""}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
