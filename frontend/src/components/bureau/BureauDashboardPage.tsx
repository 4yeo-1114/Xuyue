import { useMemo, useState } from "react";
import {
  ArrowUpRight,
  BarChart3,
  BookOpenCheck,
  Building2,
  CalendarRange,
  ChevronRight,
  GraduationCap,
  Info,
  School,
  TrendingUp,
  Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";

type StatCard = {
  id: string;
  titleKey: string;
  value: string;
  icon: React.ElementType;
  accent?: "blue" | "green" | "orange" | "purple";
  subtextKey: string;
};

type StatDetail = {
  id: string;
  title: string;
  period: string;
  description: string;
  trendLabel: string;
  trendValue: string;
  summary: Array<{ label: string; value: string }>;
  focusSchools: Array<{ name: string; value: string; note: string }>;
  insights: string[];
};

type ComplianceItem = {
  name: string;
  rate: number;
};

type TopSchoolItem = {
  name: string;
  value: number;
};

type SchoolRow = {
  rank: number;
  name: string;
  avgScore: number;
  classCount: number;
  teacherCount: number;
  studentCount: number;
  examCount: number;
  trend: "up" | "down";
};

const statCards: StatCard[] = [
  {
    id: "school-total",
    titleKey: "bureau.dashboard.kpi.schoolTotal",
    value: "25",
    icon: School,
    accent: "blue",
    subtextKey: "bureau.dashboard.kpi.schoolTotalSub",
  },
  {
    id: "teacher-total",
    titleKey: "bureau.dashboard.kpi.teacherTotal",
    value: "5135",
    icon: Users,
    accent: "blue",
    subtextKey: "bureau.dashboard.kpi.teacherTotalSub",
  },
  {
    id: "exam-total",
    titleKey: "bureau.dashboard.kpi.examTotal",
    value: "28",
    icon: BookOpenCheck,
    accent: "blue",
    subtextKey: "bureau.dashboard.kpi.examTotalSub",
  },
  {
    id: "improve-rate",
    titleKey: "bureau.dashboard.kpi.improveRate",
    value: "16.8%",
    icon: TrendingUp,
    accent: "orange",
    subtextKey: "bureau.dashboard.kpi.improveRateSub",
  },
  {
    id: "exam-batch",
    titleKey: "bureau.dashboard.kpi.examBatch",
    value: "328",
    icon: BarChart3,
    accent: "blue",
    subtextKey: "bureau.dashboard.kpi.examBatchSub",
  },
  {
    id: "student-participation",
    titleKey: "bureau.dashboard.kpi.participation",
    value: "12629",
    icon: GraduationCap,
    accent: "blue",
    subtextKey: "bureau.dashboard.kpi.participationSub",
  },
  {
    id: "excellent-schools",
    titleKey: "bureau.dashboard.kpi.excellentSchools",
    value: "7",
    icon: Building2,
    accent: "green",
    subtextKey: "bureau.dashboard.kpi.excellentSchoolsSub",
  },
  {
    id: "ai-coverage",
    titleKey: "bureau.dashboard.kpi.aiCoverage",
    value: "25",
    icon: ArrowUpRight,
    accent: "purple",
    subtextKey: "bureau.dashboard.kpi.aiCoverageSub",
  },
];

const statDetails: StatDetail[] = [
  {
    id: "school-total",
    title: "学校总数详细信息",
    period: "统计周期：2026 年春季学期",
    description:
      "展示当前已纳入教育局数据治理平台的学校数量，以及不同学段、不同片区的接入情况。",
    trendLabel: "接入进度",
    trendValue: "100%",
    summary: [
      { label: "小学", value: "18 所" },
      { label: "初中", value: "5 所" },
      { label: "九年一贯制", value: "2 所" },
      { label: "本月新增", value: "3 所" },
    ],
    focusSchools: [
      { name: "红星小学", value: "已接入", note: "课堂、作业、考试数据已联通" },
      {
        name: "开发区实验学校",
        value: "已接入",
        note: "支持校级画像与局端汇总",
      },
      { name: "宏图实验小学", value: "新增接入", note: "本周完成历史成绩导入" },
    ],
    insights: [
      "当前全区学校已全部接入，无未覆盖学校。",
      "新增接入学校主要集中在东部新区片区。",
      "建议下一步完善校际数据口径统一配置。",
    ],
  },
  {
    id: "teacher-total",
    title: "教师总数详细信息",
    period: "统计周期：近 30 天",
    description:
      "展示局端教师总量、学科教师结构和活跃教师情况，用于评估平台覆盖广度。",
    trendLabel: "活跃教师占比",
    trendValue: "89.4%",
    summary: [
      { label: "语文教师", value: "1312 人" },
      { label: "数学教师", value: "1458 人" },
      { label: "英语教师", value: "1185 人" },
      { label: "综合学科", value: "1180 人" },
    ],
    focusSchools: [
      { name: "周城中心小学", value: "262 人", note: "本月活跃率 96%" },
      { name: "阳光小学", value: "245 人", note: "AI 讲评使用率最高" },
      {
        name: "龙港实验学校",
        value: "231 人",
        note: "新增教师培训完成率 100%",
      },
    ],
    insights: [
      "数学教师使用平台频率最高，集中在作业批改和学情分析。",
      "英语与综合学科教师增长较快，适合扩展更多资源库内容。",
      "建议针对低活跃学校开展一次平台能力培训。",
    ],
  },
  {
    id: "exam-total",
    title: "考试总数详细信息",
    period: "统计周期：本月累计",
    description:
      "反映局端已归集的考试数量，包含校级周测、月考、联考与阶段性诊断。",
    trendLabel: "较上月",
    trendValue: "+6 场",
    summary: [
      { label: "区级联考", value: "4 场" },
      { label: "校级月考", value: "9 场" },
      { label: "周测", value: "11 场" },
      { label: "阶段诊断", value: "4 场" },
    ],
    focusSchools: [
      { name: "和平路小学", value: "4 场", note: "月度考试覆盖最完整" },
      { name: "育才小学", value: "3 场", note: "同步上传速度最快" },
      { name: "新桥小学", value: "3 场", note: "考试分析完整率 98%" },
    ],
    insights: [
      "本月考试数量较上月明显增长，反映学校阶段检测更密集。",
      "联考数据上传稳定，适合支撑局端横向对比。",
      "建议对周测数据补充试卷标签，便于后续按知识点追踪。",
    ],
  },
  {
    id: "improve-rate",
    title: "平均提升率详细信息",
    period: "统计周期：近两次考试对比",
    description: "以学校最近两次可比考试为基准，计算平均提分率和稳定增幅。",
    trendLabel: "核心指标",
    trendValue: "+16.8%",
    summary: [
      { label: "增幅 >20%", value: "6 所" },
      { label: "增幅 10-20%", value: "11 所" },
      { label: "增幅 0-10%", value: "5 所" },
      { label: "轻微回落", value: "3 所" },
    ],
    focusSchools: [
      { name: "红星小学", value: "+24.6%", note: "数学分层推送后提升明显" },
      { name: "开发区实验学校", value: "+23.9%", note: "讲评课设计效果突出" },
      { name: "中心三小", value: "-2.1%", note: "近期考试稳定性不足" },
    ],
    insights: [
      "头部学校提升率稳定，说明优质校已形成可复制打法。",
      "中段学校提升空间大，建议重点推广靶向提升模块。",
      "个别学校出现回落，可结合局端督导查看课堂落实情况。",
    ],
  },
  {
    id: "exam-batch",
    title: "考试批次详细信息",
    period: "统计周期：本学期累计",
    description:
      "统计各校上传的考试批次总量，用于观察局端评测密度和过程性评价覆盖。",
    trendLabel: "批次达标率",
    trendValue: "92%",
    summary: [
      { label: "月均批次", value: "54.7" },
      { label: "区均批次", value: "13.1/校" },
      { label: "完成归档", value: "305 批" },
      { label: "待补材料", value: "23 批" },
    ],
    focusSchools: [
      { name: "春晖路小学", value: "18 批", note: "试卷与成绩归档规范" },
      { name: "东城小学", value: "17 批", note: "覆盖周测与单元测" },
      { name: "朝阳小学", value: "11 批", note: "仍需补齐月考材料" },
    ],
    insights: [
      "多数学校已形成常态化批次上传机制。",
      "待补材料主要集中在单元练习和周测附件。",
      "建议增加局端批次完整性提醒，降低漏传风险。",
    ],
  },
  {
    id: "student-participation",
    title: "参考总人次详细信息",
    period: "统计周期：近 30 天",
    description:
      "汇总所有已接入学校的参考学生人次，便于观察区域内考试参与度与活跃度。",
    trendLabel: "参与率",
    trendValue: "97.2%",
    summary: [
      { label: "小学段", value: "9156 人次" },
      { label: "初中段", value: "2448 人次" },
      { label: "九年一贯制", value: "1025 人次" },
      { label: "缺考率", value: "2.8%" },
    ],
    focusSchools: [
      { name: "西江路小学", value: "674 人次", note: "全勤参与率最高" },
      { name: "和平路小学", value: "664 人次", note: "月考参与稳定" },
      { name: "博雅小学", value: "487 人次", note: "请假学生较多" },
    ],
    insights: [
      "大部分学校考试参与稳定，说明考试组织已规范化。",
      "局端可重点关注缺考率高于 4% 的学校。",
      "建议在详情页加入缺考学生名单联动，便于后续追踪。",
    ],
  },
  {
    id: "excellent-schools",
    title: "优秀学校详细信息",
    period: "统计规则：达标率大于 75%",
    description:
      "按照教学增效、均分率、过程性评价完整度综合判定，筛选优质样板学校。",
    trendLabel: "样板校数量",
    trendValue: "7 所",
    summary: [
      { label: "增效领先", value: "4 所" },
      { label: "管理规范", value: "2 所" },
      { label: "AI 应用标杆", value: "1 所" },
      { label: "待观测候选", value: "3 所" },
    ],
    focusSchools: [
      { name: "坪桥小学", value: "82.0%", note: "局端样板校推荐" },
      { name: "周城中心小学", value: "81.8%", note: "课堂讲评效果突出" },
      { name: "阳光小学", value: "81.6%", note: "AI 诊断应用最全面" },
    ],
    insights: [
      "优质校集中在城区学校，但新区学校成长速度较快。",
      "样板校共同特征是考试组织规范、讲评闭环完整。",
      "建议形成经验案例库，向中段学校复制推广。",
    ],
  },
  {
    id: "ai-coverage",
    title: "AI 诊断覆盖详细信息",
    period: "统计周期：本月累计",
    description:
      "展示各校是否使用 AI 讲评、靶向提升、分层推送等能力，衡量平台深度应用情况。",
    trendLabel: "覆盖学校",
    trendValue: "25/25",
    summary: [
      { label: "AI 讲评", value: "25 所" },
      { label: "靶向提升", value: "19 所" },
      { label: "分层推送", value: "16 所" },
      { label: "资源推荐", value: "21 所" },
    ],
    focusSchools: [
      {
        name: "开发区实验学校",
        value: "全量覆盖",
        note: "四项 AI 能力全部使用",
      },
      { name: "红星小学", value: "高频使用", note: "每周稳定生成教学建议" },
      { name: "东城小学", value: "部分覆盖", note: "靶向提升尚未全面推广" },
    ],
    insights: [
      "AI 讲评已全覆盖，但深度能力使用还存在分化。",
      "优质校往往会把 AI 建议纳入日常教研流程。",
      "建议下一步增加学校使用热力图，方便局端督导。",
    ],
  },
];

const complianceList: ComplianceItem[] = [
  { name: "坪桥小学", rate: 82.0 },
  { name: "周城中心小学", rate: 81.8 },
  { name: "阳光小学", rate: 81.6 },
];

const topSchools: TopSchoolItem[] = [
  { name: "红星小学", value: 62.4 },
  { name: "开发区实验学校", value: 62.1 },
  { name: "西江路小学", value: 61.8 },
  { name: "和平路小学", value: 61.3 },
  { name: "育才小学", value: 61.1 },
  { name: "同心小学", value: 60.9 },
  { name: "春晖路小学", value: 60.7 },
  { name: "明星小学", value: 60.4 },
  { name: "龙港实验学校", value: 60.1 },
  { name: "启航小学", value: 59.8 },
];

const schoolRows: SchoolRow[] = [
  {
    rank: 1,
    name: "红星小学",
    avgScore: 62.4,
    classCount: 680,
    teacherCount: 71,
    studentCount: 707,
    examCount: 17,
    trend: "up",
  },
  {
    rank: 2,
    name: "开发区实验学校",
    avgScore: 62.1,
    classCount: 663,
    teacherCount: 69,
    studentCount: 692,
    examCount: 16,
    trend: "up",
  },
  {
    rank: 3,
    name: "西江路小学",
    avgScore: 61.8,
    classCount: 654,
    teacherCount: 67,
    studentCount: 674,
    examCount: 17,
    trend: "up",
  },
  {
    rank: 4,
    name: "和平路小学",
    avgScore: 61.3,
    classCount: 649,
    teacherCount: 67,
    studentCount: 674,
    examCount: 14,
    trend: "up",
  },
  {
    rank: 5,
    name: "育才小学",
    avgScore: 61.1,
    classCount: 648,
    teacherCount: 66,
    studentCount: 664,
    examCount: 15,
    trend: "up",
  },
  {
    rank: 6,
    name: "同心小学",
    avgScore: 60.9,
    classCount: 639,
    teacherCount: 64,
    studentCount: 658,
    examCount: 16,
    trend: "up",
  },
  {
    rank: 7,
    name: "春晖路小学",
    avgScore: 60.7,
    classCount: 588,
    teacherCount: 63,
    studentCount: 602,
    examCount: 15,
    trend: "up",
  },
  {
    rank: 8,
    name: "明星小学",
    avgScore: 60.4,
    classCount: 561,
    teacherCount: 61,
    studentCount: 573,
    examCount: 15,
    trend: "down",
  },
  {
    rank: 9,
    name: "龙港实验学校",
    avgScore: 60.1,
    classCount: 548,
    teacherCount: 59,
    studentCount: 558,
    examCount: 13,
    trend: "down",
  },
  {
    rank: 10,
    name: "启航小学",
    avgScore: 59.8,
    classCount: 536,
    teacherCount: 58,
    studentCount: 553,
    examCount: 13,
    trend: "down",
  },
  {
    rank: 11,
    name: "宏图实验小学",
    avgScore: 59.4,
    classCount: 526,
    teacherCount: 55,
    studentCount: 543,
    examCount: 14,
    trend: "up",
  },
  {
    rank: 12,
    name: "东城小学",
    avgScore: 59.1,
    classCount: 500,
    teacherCount: 54,
    studentCount: 514,
    examCount: 12,
    trend: "down",
  },
  {
    rank: 13,
    name: "新桥小学",
    avgScore: 58.7,
    classCount: 499,
    teacherCount: 53,
    studentCount: 515,
    examCount: 11,
    trend: "up",
  },
  {
    rank: 14,
    name: "中心三小",
    avgScore: 58.5,
    classCount: 497,
    teacherCount: 52,
    studentCount: 516,
    examCount: 11,
    trend: "up",
  },
  {
    rank: 15,
    name: "博雅小学",
    avgScore: 58.2,
    classCount: 478,
    teacherCount: 51,
    studentCount: 487,
    examCount: 13,
    trend: "up",
  },
  {
    rank: 16,
    name: "第二小学",
    avgScore: 58.0,
    classCount: 477,
    teacherCount: 50,
    studentCount: 486,
    examCount: 12,
    trend: "up",
  },
  {
    rank: 17,
    name: "中心一小",
    avgScore: 57.6,
    classCount: 472,
    teacherCount: 49,
    studentCount: 491,
    examCount: 13,
    trend: "down",
  },
  {
    rank: 18,
    name: "朝阳小学",
    avgScore: 57.1,
    classCount: 464,
    teacherCount: 48,
    studentCount: 475,
    examCount: 13,
    trend: "up",
  },
];

const accentClasses = {
  blue: "bg-blue-50 text-blue-600",
  green: "bg-emerald-50 text-emerald-600",
  orange: "bg-orange-50 text-orange-600",
  purple: "bg-violet-50 text-violet-600",
};

function SchoolBarChart() {
  const { t } = useLocale();
  return (
    <Card className="border-border/70 shadow-sm">
      <CardHeader className="pb-4">
        <CardTitle className="text-base font-semibold">
          {t("bureau.dashboard.chartTitle")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-[140px_1fr_56px] items-center gap-y-3 gap-x-4">
          {topSchools.map((item) => (
            <div key={item.name} className="contents">
              <div className="truncate text-sm text-slate-600">{item.name}</div>
              <div className="h-8 rounded-md bg-slate-100 p-1">
                <div
                  className="h-full rounded bg-blue-500 transition-all"
                  style={{ width: `${item.value}%` }}
                />
              </div>
              <div className="text-right text-sm font-medium text-slate-600">
                {item.value}%
              </div>
            </div>
          ))}
        </div>
        <div className="flex justify-between text-xs text-slate-400">
          <span>0%</span>
          <span>25%</span>
          <span>50%</span>
          <span>75%</span>
          <span>100%</span>
        </div>
      </CardContent>
    </Card>
  );
}

export function BureauDashboardPage() {
  const { t } = useLocale();
  const [selectedStatId, setSelectedStatId] = useState<string | null>(null);

  const activeDetail = useMemo(
    () => statDetails.find((item) => item.id === selectedStatId) ?? null,
    [selectedStatId],
  );

  return (
    <>
      <div className="space-y-5">
        <Card className="border-border/70 bg-white shadow-sm">
          <CardContent className="flex flex-col gap-4 p-5">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className="border-blue-200 bg-blue-50 text-blue-600"
                  >
                    {t("bureau.dashboard.badge")}
                  </Badge>
                  <span className="text-xs text-slate-400">
                    {t("bureau.dashboard.subtitle")}
                  </span>
                </div>
                <div>
                  <h2 className="text-2xl font-semibold text-slate-900">
                    {t("bureau.dashboard.title")}
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {t("bureau.dashboard.desc")}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {[
                  "bureau.dashboard.filter.primary",
                  "bureau.dashboard.filter.math",
                  "bureau.dashboard.filter.rate",
                  "bureau.dashboard.filter.range",
                ].map((item) => (
                  <Button
                    key={item}
                    variant="outline"
                    className="h-9 rounded-lg border-slate-200 bg-slate-50 px-4 text-slate-600 hover:bg-slate-100"
                  >
                    {t(item)}
                  </Button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {statCards.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedStatId(item.id)}
                  className="text-left outline-none"
                >
                  <Card className="h-full border-border/70 shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-md focus-visible:ring-2 focus-visible:ring-blue-300">
                    <CardContent className="p-5">
                      <div className="flex items-start justify-between gap-3">
                        <div className="space-y-3">
                          <p className="text-sm text-slate-500">
                            {t(item.titleKey)}
                          </p>
                          <div className="text-3xl font-semibold tracking-tight text-slate-900">
                            {item.value}
                          </div>
                          <p className="text-xs text-slate-400">
                            {t(item.subtextKey)}
                          </p>
                          <div className="inline-flex items-center gap-1 text-xs font-medium text-blue-600">
                            {t("bureau.dashboard.viewDetails")}
                            <ChevronRight className="h-3.5 w-3.5" />
                          </div>
                        </div>
                        <div
                          className={cn(
                            "flex h-10 w-10 items-center justify-center rounded-xl",
                            accentClasses[item.accent || "blue"],
                          )}
                        >
                          <Icon className="h-5 w-5" />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </button>
              );
            })}
          </div>

          <Card className="border-emerald-200 bg-emerald-50/40 shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-emerald-700">
                {t("bureau.dashboard.complianceTitle")}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {complianceList.map((item, index) => (
                <div
                  key={item.name}
                  className="flex items-center justify-between gap-3 rounded-lg bg-white/90 px-4 py-3"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-100 text-xs font-semibold text-emerald-700">
                      {index + 1}
                    </div>
                    <span className="text-sm font-medium text-slate-700">
                      {item.name}
                    </span>
                  </div>
                  <span className="text-sm font-semibold text-emerald-600">
                    {item.rate}%
                  </span>
                </div>
              ))}
              <div className="rounded-lg border border-dashed border-emerald-200 bg-white/60 px-4 py-3 text-xs text-emerald-700">
                {t("bureau.dashboard.complianceHint")}
              </div>
            </CardContent>
          </Card>
        </div>

        <SchoolBarChart />

        <Card className="border-border/70 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold">
              {t("bureau.dashboard.rankTitle")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50 hover:bg-slate-50">
                  <TableHead className="w-16">#</TableHead>
                  <TableHead>{t("bureau.dashboard.colSchool")}</TableHead>
                  <TableHead>{t("bureau.dashboard.colAvgScore")}</TableHead>
                  <TableHead>{t("bureau.dashboard.colClassCount")}</TableHead>
                  <TableHead>{t("bureau.dashboard.colTeacher")}</TableHead>
                  <TableHead>{t("bureau.dashboard.colStudent")}</TableHead>
                  <TableHead>{t("bureau.dashboard.colExam")}</TableHead>
                  <TableHead className="text-right">
                    {t("bureau.dashboard.colTrend")}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {schoolRows.map((row) => (
                  <TableRow key={row.rank}>
                    <TableCell className="font-medium text-slate-500">
                      {row.rank}
                    </TableCell>
                    <TableCell className="font-medium text-slate-800">
                      {row.name}
                    </TableCell>
                    <TableCell
                      className={cn(
                        "font-semibold",
                        row.avgScore >= 60 ? "text-amber-500" : "text-rose-500",
                      )}
                    >
                      {row.avgScore}%
                    </TableCell>
                    <TableCell>{row.classCount}</TableCell>
                    <TableCell>{row.teacherCount}</TableCell>
                    <TableCell>{row.studentCount}</TableCell>
                    <TableCell>{row.examCount}</TableCell>
                    <TableCell className="text-right">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 text-sm font-medium",
                          row.trend === "up"
                            ? "text-emerald-600"
                            : "text-rose-500",
                        )}
                      >
                        {row.trend === "up" ? "↑" : "↓"}
                        {row.trend === "up"
                          ? t("bureau.dashboard.trendUp")
                          : t("bureau.dashboard.trendDown")}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={!!activeDetail}
        onOpenChange={(open) => !open && setSelectedStatId(null)}
      >
        <DialogContent className="max-h-[85vh] max-w-4xl overflow-hidden border-slate-200 p-0">
          {activeDetail && (
            <div className="flex max-h-[85vh] flex-col">
              <DialogHeader className="border-b border-slate-100 px-6 py-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className="border-blue-200 bg-blue-50 text-blue-600"
                      >
                        {t("bureau.dashboard.detailBadge")}
                      </Badge>
                      <span className="inline-flex items-center gap-1 text-xs text-slate-400">
                        <CalendarRange className="h-3.5 w-3.5" />
                        {activeDetail.period}
                      </span>
                    </div>
                    <DialogTitle className="text-xl text-slate-900">
                      {activeDetail.title}
                    </DialogTitle>
                    <DialogDescription className="max-w-2xl text-sm leading-6 text-slate-500">
                      {activeDetail.description}
                    </DialogDescription>
                  </div>
                  <div className="rounded-xl bg-blue-50 px-4 py-3 text-right">
                    <div className="text-xs text-slate-500">
                      {activeDetail.trendLabel}
                    </div>
                    <div className="mt-1 text-2xl font-semibold text-blue-600">
                      {activeDetail.trendValue}
                    </div>
                  </div>
                </div>
              </DialogHeader>

              <div className="overflow-y-auto px-6 py-5">
                <div className="grid gap-4 md:grid-cols-4">
                  {activeDetail.summary.map((item) => (
                    <Card
                      key={item.label}
                      className="border-slate-200 bg-slate-50/70 shadow-none"
                    >
                      <CardContent className="p-4">
                        <div className="text-xs text-slate-500">
                          {item.label}
                        </div>
                        <div className="mt-2 text-2xl font-semibold text-slate-900">
                          {item.value}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>

                <div className="mt-6 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
                  <Card className="border-slate-200 shadow-none">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base font-semibold text-slate-900">
                        {t("bureau.dashboard.focusTitle")}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {activeDetail.focusSchools.map((item) => (
                        <div
                          key={item.name}
                          className="rounded-xl border border-slate-100 bg-slate-50/70 p-4"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm font-semibold text-slate-800">
                              {item.name}
                            </div>
                            <Badge
                              variant="outline"
                              className="border-emerald-200 bg-emerald-50 text-emerald-600"
                            >
                              {item.value}
                            </Badge>
                          </div>
                          <p className="mt-2 text-sm text-slate-500">
                            {item.note}
                          </p>
                        </div>
                      ))}
                    </CardContent>
                  </Card>

                  <Card className="border-slate-200 shadow-none">
                    <CardHeader className="pb-3">
                      <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-900">
                        <Info className="h-4 w-4 text-blue-500" />
                        {t("bureau.dashboard.insightTitle")}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        {activeDetail.insights.map((item) => (
                          <div
                            key={item}
                            className="flex gap-3 rounded-xl bg-blue-50/60 p-4"
                          >
                            <div className="mt-1 h-2 w-2 rounded-full bg-blue-500" />
                            <p className="text-sm leading-6 text-slate-600">
                              {item}
                            </p>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
