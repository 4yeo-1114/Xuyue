import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLocale } from "@/contexts/LocaleContext";
import {
  translateSubjectName,
  translateGradeValue,
  normalizeGrade,
} from "@/i18n";
import {
  listTextbookCatalogOptions,
  type TextbookCatalogOptions,
} from "@/services/api";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { LayoutGrid, ArrowRight, Loader2, RefreshCw } from "lucide-react";

/**
 * 四维定位矩阵：学科 × 年级 × 版本 × 目录。
 * 年级行 × 科目列；点击单元格携带 subject/grade/edition 跳转到教材目录页（/nav/prep-catalog）。
 *
 * 数据同步：学科/年级/版本的结构为产品固定维度，但「单元格是否点亮」由后端
 * 教材目录（textbook_catalogs）真实数据驱动——仅对存在目录内容的组合开放跳转，
 * 版本下拉也改为读真实数据，避免硬编码导致点击后落到空目录页。
 */
const PRIMARY_SUBJECTS = ["语文", "数学", "英语", "科学", "道德与法治"];
const JUNIOR_SUBJECTS = [
  "语文",
  "数学",
  "英语",
  "道德与法治",
  "历史",
  "地理",
  "生物",
  "物理",
  "化学",
];

const PRIMARY_GRADES = [
  "一年级",
  "二年级",
  "三年级",
  "四年级",
  "五年级",
  "六年级",
];
const JUNIOR_GRADES = ["七年级", "八年级", "九年级"];
const SENIOR_GRADES = ["高一", "高二", "高三"];
const SENIOR_SUBJECTS = [
  "语文",
  "数学",
  "英语",
  "物理",
  "化学",
  "生物",
  "历史",
  "地理",
  "政治",
];

/** 教材版本兜底常量（后端无数据时使用；有数据则以后端真实版本为准） */
const EDITIONS = ["人教版", "北师大版", "苏教版", "外研版", "冀教版"];

const SUBJECT_COLORS: Record<string, string> = {
  语文: "bg-rose-50 text-rose-600 border-rose-200 hover:bg-rose-100",
  数学: "bg-blue-50 text-blue-600 border-blue-200 hover:bg-blue-100",
  英语: "bg-violet-50 text-violet-600 border-violet-200 hover:bg-violet-100",
  科学: "bg-emerald-50 text-emerald-600 border-emerald-200 hover:bg-emerald-100",
  道德与法治:
    "bg-orange-50 text-orange-600 border-orange-200 hover:bg-orange-100",
  历史: "bg-amber-50 text-amber-600 border-amber-200 hover:bg-amber-100",
  地理: "bg-sky-50 text-sky-600 border-sky-200 hover:bg-sky-100",
  生物: "bg-lime-50 text-lime-600 border-lime-200 hover:bg-lime-100",
  物理: "bg-indigo-50 text-indigo-600 border-indigo-200 hover:bg-indigo-100",
  化学: "bg-cyan-50 text-cyan-600 border-cyan-200 hover:bg-cyan-100",
  政治: "bg-pink-50 text-pink-600 border-pink-200 hover:bg-pink-100",
};

const subjectColor = (subject: string) =>
  SUBJECT_COLORS[subject] ||
  "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100";

interface MatrixSection {
  key: "primary" | "junior" | "senior";
  labelKey: string;
  grades: string[];
  subjects: string[];
}

export function PrepMatrixPage() {
  const { t, locale } = useLocale();
  const navigate = useNavigate();
  const [edition, setEdition] = useState("人教版");

  const [options, setOptions] = useState<TextbookCatalogOptions | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const loadOptions = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const data = await listTextbookCatalogOptions();
      setOptions(data ?? { editions: [], subjects: [], grades: [], pairs: [] });
    } catch {
      setError(true);
      setOptions(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  // 版本下拉读真实数据；无数据时回退到兜底常量
  const editionOptions = useMemo(() => {
    const list = options?.editions ?? [];
    return list.length > 0 ? list : EDITIONS;
  }, [options]);

  // 后端返回的版本若不含当前选中值，自动切到第一个真实版本
  useEffect(() => {
    if (
      options &&
      options.editions.length > 0 &&
      !options.editions.includes(edition)
    ) {
      setEdition(options.editions[0]);
    }
  }, [options, edition]);

  // 按当前版本构建「学科|年级 → 目录节点数」映射，用于点亮单元格
  const dataMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const p of options?.pairs ?? []) {
      if (p.edition && p.edition !== edition) continue;
      const key = `${p.subject}|${normalizeGrade(p.grade)}`;
      map.set(key, Math.max(map.get(key) ?? 0, p.node_count || 0));
    }
    return map;
  }, [options, edition]);

  const hasData = (subject: string, grade: string) =>
    dataMap.has(`${subject}|${normalizeGrade(grade)}`);
  const nodeCount = (subject: string, grade: string) =>
    dataMap.get(`${subject}|${normalizeGrade(grade)}`) ?? 0;

  const sections = useMemo<MatrixSection[]>(
    () => [
      {
        key: "primary",
        labelKey: "prepMatrix.schoolLevel.primary",
        grades: PRIMARY_GRADES,
        subjects: PRIMARY_SUBJECTS,
      },
      {
        key: "junior",
        labelKey: "prepMatrix.schoolLevel.junior",
        grades: JUNIOR_GRADES,
        subjects: JUNIOR_SUBJECTS,
      },
      {
        key: "senior",
        labelKey: "prepMatrix.schoolLevel.senior",
        grades: SENIOR_GRADES,
        subjects: SENIOR_SUBJECTS,
      },
    ],
    [],
  );

  const goToCatalog = (subject: string, grade: string) => {
    const params = new URLSearchParams({ subject, grade, edition });
    navigate(`/nav/prep-catalog?${params.toString()}`);
  };

  const hasAnyData = dataMap.size > 0;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Badge variant="outline" className="gap-1">
            <LayoutGrid className="w-3 h-3" />
            {t("prepMatrix.badge")}
          </Badge>
        </div>
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              {t("prepMatrix.title")}
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              {t("prepMatrix.subtitle")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {loading && (
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            )}
            <span className="text-sm text-muted-foreground">
              {t("prepMatrix.edition")}
            </span>
            <Select value={edition} onValueChange={setEdition}>
              <SelectTrigger className="w-36">
                <SelectValue placeholder={t("prepCatalog.selectEdition")} />
              </SelectTrigger>
              <SelectContent>
                {editionOptions.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* 同步状态条：加载失败 / 无任何目录数据时给出提示，矩阵结构仍正常渲染 */}
      {error && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          <span>{t("prepMatrix.error")}</span>
          <button
            type="button"
            onClick={() => void loadOptions()}
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium underline-offset-2 hover:underline"
          >
            <RefreshCw className="w-3 h-3" />
            {t("prepMatrix.retry")}
          </button>
        </div>
      )}
      {!error && !loading && options && !hasAnyData && (
        <div className="rounded-md border border-muted bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
          {t("prepMatrix.empty")}
        </div>
      )}

      {sections.map((section) => (
        <Card key={section.key}>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t(section.labelKey)}</CardTitle>
            <CardDescription className="text-xs">
              {t("prepMatrix.clickHint")}
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-28 whitespace-nowrap">
                    {t("prepMatrix.subject")}
                  </TableHead>
                  {section.subjects.map((subject) => (
                    <TableHead
                      key={subject}
                      className="text-center whitespace-nowrap"
                    >
                      {translateSubjectName(locale, subject)}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {section.grades.map((grade) => (
                  <TableRow key={grade}>
                    <TableCell className="font-medium whitespace-nowrap">
                      {translateGradeValue(locale, section.key, grade)}
                    </TableCell>
                    {section.subjects.map((subject) => {
                      const active = hasData(subject, grade);
                      const count = nodeCount(subject, grade);
                      const label = `${translateSubjectName(
                        locale,
                        subject,
                      )} · ${translateGradeValue(locale, section.key, grade)}`;
                      return (
                        <TableCell
                          key={subject}
                          className="text-center p-1.5"
                        >
                          {active ? (
                            <button
                              type="button"
                              onClick={() => goToCatalog(subject, grade)}
                              className={cn(
                                "relative w-full min-w-16 rounded-lg border px-2 py-2 text-sm transition-colors",
                                subjectColor(subject),
                              )}
                              aria-label={label}
                            >
                              <span className="inline-flex items-center gap-1">
                                {translateSubjectName(locale, subject)}
                                <ArrowRight className="w-3.5 h-3.5" />
                              </span>
                              <span className="absolute -top-2 -right-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-medium text-primary-foreground">
                                {count}
                              </span>
                            </button>
                          ) : (
                            <div
                              className="w-full min-w-16 rounded-lg border border-dashed border-muted px-2 py-2 text-sm text-muted-foreground/50 cursor-not-allowed"
                              title={t("prepMatrix.noData")}
                            >
                              <span className="inline-flex items-center gap-1">
                                {translateSubjectName(locale, subject)}
                              </span>
                            </div>
                          )}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
