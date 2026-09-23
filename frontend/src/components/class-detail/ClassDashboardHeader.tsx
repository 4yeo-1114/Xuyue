import { useNavigate } from "react-router-dom";
import { useLocale } from "@/contexts/LocaleContext";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, TrendingDown, AlertTriangle, BookOpen, Users, CheckCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ClassDashboardData {
  avgScore: number;
  avgScoreChange: number;
  weakPointsCount: number;
  attentionStudentsCount: number;
  homeworkCompletionRate: number;
}

interface ClassDashboardHeaderProps {
  className: string;
  grade: string;
  selectedSubject: string;
  data: ClassDashboardData;
}

const mockData: ClassDashboardData = {
  avgScore: 82.5,
  avgScoreChange: 3.2,
  weakPointsCount: 12,
  attentionStudentsCount: 5,
  homeworkCompletionRate: 87,
};

export { mockData as classDashboardMockData };

export function ClassDashboardHeader({
  className: classNameStr,
  grade,
  selectedSubject,
  data,
}: ClassDashboardHeaderProps) {
  const { t, locale } = useLocale();

  const navigate = useNavigate();
  const isUp = data.avgScoreChange >= 0;

  const cards = [
    {
      icon: TrendingUp,
      label: t("classDetail.班级均分"),
      value: data.avgScore.toFixed(1),
      extra: (
        <span className={cn("text-sm font-medium flex items-center gap-0.5", isUp ? "text-success" : "text-destructive")}>
          {isUp ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
          {isUp ? "+" : ""}{data.avgScoreChange.toFixed(1)}%
        </span>
      ),
    },
    {
      icon: BookOpen,
      label: t("classDetail.薄弱知识点"),
      value: data.weakPointsCount,
      extra: (
        <button className="text-xs text-primary hover:underline" onClick={() => console.log("查看详情")}>
          {t("classDetail.查看详情")} →
        </button>
      ),
    },
    {
      icon: Users,
      label: t("classDetail.需关注学生"),
      value: data.attentionStudentsCount,
      extra: (
        <Badge variant="destructive" className="text-xs px-1.5 py-0">
          <AlertTriangle className="w-3 h-3 mr-0.5" />
          {t("classDetail.关注")}
        </Badge>
      ),
    },
    {
      icon: CheckCircle,
      label: t("classDetail.作业完成率"),
      value: `${data.homeworkCompletionRate}%`,
      extra: (
        <Progress value={data.homeworkCompletionRate} className="h-2 mt-1" />
      ),
    },
  ];

  return (
    <div className="space-y-5">
      {/* Top row: breadcrumb with current subject */}
      <div className="flex items-center flex-wrap gap-3">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink className="cursor-pointer" onClick={() => navigate("/")}>
                {t("nav.home")}
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{t("classDetail.classNameGrade", { name: classNameStr, grade })}</BreadcrumbPage>
            </BreadcrumbItem>
            {selectedSubject && (
              <>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>{selectedSubject}</BreadcrumbPage>
                </BreadcrumbItem>
              </>
            )}
          </BreadcrumbList>
        </Breadcrumb>
      </div>

      {/* Overview cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="bg-card rounded-xl p-5 shadow-sm border border-border transition-transform duration-200 hover:-translate-y-1 hover:shadow-md"
          >
            <div className="flex items-center gap-2 mb-3">
              <div className="p-1.5 rounded-lg bg-primary/10">
                <card.icon className="w-4 h-4 text-primary" />
              </div>
              <span className="text-sm text-muted-foreground">{card.label}</span>
            </div>
            <div className="text-3xl font-bold text-foreground">{card.value}</div>
            <div className="mt-1.5">{card.extra}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
