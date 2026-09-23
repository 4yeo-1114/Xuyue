import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { MoreHorizontal, Upload } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLocale } from "@/contexts/LocaleContext";

interface ClassManageHeaderProps {
  classCount: number;
  totalStudents: number;
  activeClassName: string;
  activeHeadTeacherName: string;
  activeStudentCount: number;
  onBatchImport?: () => void;
}

export function ClassManageHeader({
  classCount,
  totalStudents,
  activeClassName,
  activeHeadTeacherName,
  activeStudentCount,
  onBatchImport,
}: ClassManageHeaderProps) {
  const { t } = useLocale();

  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h1 className="text-3xl font-bold text-foreground tracking-tight">{t("nav.settings-class")}</h1>
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <Badge variant="secondary" className="text-xs">{t("settingsClass.classesCount", { count: classCount })}</Badge>
          <Badge variant="secondary" className="text-xs">{t("settingsClass.totalStudents", { count: totalStudents })}</Badge>
          <span className="text-sm text-muted-foreground">·</span>
          <Badge variant="outline" className="text-xs">{t("settingsClass.currentClass", { name: activeClassName })}</Badge>
          <Badge variant="outline" className="text-xs">{t("settingsClass.headTeacher", { name: activeHeadTeacherName })}</Badge>
          <Badge variant="outline" className="text-xs">{t("settingsClass.classStudents", { count: activeStudentCount })}</Badge>
        </div>
      </div>
      <div className="flex items-center gap-2 pt-1">
        <Button size="sm" className="gap-1.5" onClick={onBatchImport}>
          <Upload className="w-4 h-4" />
          {t("settingsClass.batchImport")}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="outline" className="gap-1.5">
              <MoreHorizontal className="w-4 h-4" />
              {t("settingsClass.more")}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem disabled>{t("settingsClass.newClass")}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled>{t("settingsClass.exportList")}</DropdownMenuItem>
            <DropdownMenuItem disabled>{t("settingsClass.syncDingTalk")}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
