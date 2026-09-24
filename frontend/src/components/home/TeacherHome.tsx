import type { ClassRecord } from "@/hooks/useClasses";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Camera,
  Upload,
  ClipboardList,
  FileText,
  BookOpen,
  Clock,
  AlertTriangle,
  ChevronRight,
} from "lucide-react";

interface TeacherHomeProps {
  subject: string;
  classes: ClassRecord[];
  onNavChange: (id: string) => void;
  onOpenClass: (classId: string) => void;
  onPhotoClick: () => void;
}

/** 单科老师端工作台（首页）：今日任务导向，学科锁定 */
export function TeacherHome({
  subject,
  classes,
  onNavChange,
  onOpenClass,
  onPhotoClick,
}: TeacherHomeProps) {
  const quickActions = [
    { key: "photo", label: "拍照批改", icon: Camera, onClick: onPhotoClick },
    { key: "upload", label: "上传批改", icon: Upload, onClick: () => onNavChange("grading-start") },
    { key: "flow", label: "流水阅卷", icon: ClipboardList, onClick: () => onNavChange("flow-tasks") },
    { key: "exam", label: "智能组卷", icon: FileText, onClick: () => onNavChange("prep-exam") },
  ];

  return (
    <div className="space-y-6">
      {/* 我的学科徽章 */}
      <div className="flex items-center gap-2 text-sm">
        <BookOpen className="w-4 h-4 text-primary" strokeWidth={1.75} />
        <span className="text-muted-foreground">我的学科：</span>
        <span className="font-semibold text-foreground">{subject}</span>
      </div>

      {/* 快捷操作 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {quickActions.map((a) => (
          <button
            key={a.key}
            type="button"
            onClick={a.onClick}
            className="flex flex-col items-start gap-2.5 p-4 rounded-xl bg-card border border-border/50 hover:border-primary/30 hover:shadow-md transition-all text-left"
          >
            <a.icon className="w-6 h-6 text-primary" strokeWidth={1.75} />
            <span className="text-sm font-medium">{a.label}</span>
          </button>
        ))}
      </div>

      {/* 待办卡片（数据待后端 /teacher/overview 聚合接入） */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <TodoCard icon={Clock} label="今日待批改" value="—" hint="数据接入中" />
        <TodoCard icon={ClipboardList} label="待阅卷任务" value="—" hint="数据接入中" />
        <TodoCard icon={AlertTriangle} label="待订正错题" value="—" hint="数据接入中" />
      </div>

      {/* 我的班级 */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-foreground">我的班级 · {subject}</h3>
          <Button variant="ghost" size="sm" onClick={() => onNavChange("settings-class")}>
            + 管理班级
          </Button>
        </div>
        {classes.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-sm text-muted-foreground">
              暂无班级，点击右上角「管理班级」新建
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {classes.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => onOpenClass(c.id)}
                className="p-4 rounded-xl bg-card border border-border/50 hover:border-primary/30 hover:shadow-md transition-all text-left"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-foreground">{c.name}</span>
                  <ChevronRight className="w-4 h-4 text-muted-foreground" />
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {c.student_count ?? 0} 名学生
                </p>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TodoCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{label}</p>
          <Icon className="w-4 h-4 text-muted-foreground/50" strokeWidth={1.75} />
        </div>
        <p className="text-2xl font-semibold mt-2 tabular-nums">{value}</p>
        <p className="text-xs text-muted-foreground mt-1">{hint}</p>
      </CardContent>
    </Card>
  );
}
