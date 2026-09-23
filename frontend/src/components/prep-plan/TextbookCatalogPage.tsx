import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useLocale } from "@/contexts/LocaleContext";
import {
  translateSubjectName,
  translateGradeValue,
  normalizeGrade,
} from "@/i18n";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { listTextbookCatalogs, type TextbookCatalogNode } from "@/services/api";
import {
  BookMarked,
  ChevronDown,
  ChevronRight,
  FolderTree,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";

/** 教材目录节点（含 children，用于树形渲染） */
interface CatalogTreeNode extends TextbookCatalogNode {
  children: CatalogTreeNode[];
}

/** 跳转到教案编辑时携带的上下文 key（#48b 读取该值初始化 AI 生成） */
export const PREP_LESSON_CONTEXT_KEY = "prep_lesson_context";

const SUBJECT_OPTIONS = [
  "语文",
  "数学",
  "英语",
  "科学",
  "道德与法治",
  "历史",
  "地理",
  "生物",
  "物理",
  "化学",
  "政治",
];
const GRADE_OPTIONS = [
  "一年级",
  "二年级",
  "三年级",
  "四年级",
  "五年级",
  "六年级",
  "七年级",
  "八年级",
  "九年级",
  "高一",
  "高二",
  "高三",
];
const EDITION_OPTIONS = ["人教版", "北师大版", "苏教版", "外研版", "冀教版"];

const DEFAULT_SUBJECT = "语文";
const DEFAULT_GRADE = "一年级";
const DEFAULT_EDITION = "人教版";

/** 把平铺的目录节点按 parent_id 组织成树 */
function buildTree(nodes: TextbookCatalogNode[]): CatalogTreeNode[] {
  const map = new Map<string, CatalogTreeNode>();
  nodes.forEach((n) =>
    map.set(String(n.id), { ...n, children: [] as CatalogTreeNode[] }),
  );
  const roots: CatalogTreeNode[] = [];
  map.forEach((node) => {
    if (node.parent_id != null && map.has(String(node.parent_id))) {
      const parent = map.get(String(node.parent_id));
      if (parent) parent.children.push(node);
    } else {
      roots.push(node);
    }
  });
  // 目录稳定排序：unit_index 升序，空值排后，再按名称兜底
  const sortByIndex = (a: CatalogTreeNode, b: CatalogTreeNode) => {
    if (a.unit_index == null && b.unit_index == null) {
      return a.name.localeCompare(b.name, "zh-Hans-CN");
    }
    if (a.unit_index == null) return 1;
    if (b.unit_index == null) return -1;
    return Number(a.unit_index) - Number(b.unit_index);
  };
  roots.sort(sortByIndex);
  map.forEach((node) => node.children.sort(sortByIndex));
  return roots;
}

function gradeLabel(locale: "zh" | "en", value: string): string {
  if (value.startsWith("高")) {
    return translateGradeValue(locale, "senior", value);
  }
  if (/^[七八九]年级$/.test(value)) {
    return translateGradeValue(locale, "junior", value);
  }
  return translateGradeValue(locale, "primary", value);
}

interface Props {
  onNavChange: (id: string) => void;
}

export function TextbookCatalogPage({ onNavChange }: Props) {
  const { t, locale } = useLocale();
  const [searchParams] = useSearchParams();

  const [subject, setSubject] = useState<string>(
    () => searchParams.get("subject") || DEFAULT_SUBJECT,
  );
  const [grade, setGrade] = useState<string>(
    () => searchParams.get("grade") || DEFAULT_GRADE,
  );
  const [edition, setEdition] = useState<string>(
    () => searchParams.get("edition") || DEFAULT_EDITION,
  );

  const [nodes, setNodes] = useState<TextbookCatalogNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listTextbookCatalogs({
        subject,
        grade: normalizeGrade(grade),
        edition,
      });
      setNodes(data || []);
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : t("prepCatalog.errorTitle");
      setError(msg);
      setNodes([]);
    } finally {
      setLoading(false);
    }
  }, [subject, grade, edition, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const tree = useMemo(() => buildTree(nodes), [nodes]);

  const toggleNode = (id: number | string) => {
    const key = String(id);
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const isCollapsed = (id: number | string) => collapsed.has(String(id));

  /** 点击「AI 生成教案」：把目录上下文写入 sessionStorage 供 #48b 读取，并跳转教案编辑 */
  const goGenerateLesson = (node: CatalogTreeNode) => {
    try {
      sessionStorage.setItem(
        PREP_LESSON_CONTEXT_KEY,
        JSON.stringify({
          subject,
          grade,
          edition,
          nodeId: node.id,
          nodeName: node.name,
          level: node.level,
          timestamp: Date.now(),
        }),
      );
    } catch {
      // sessionStorage 不可用时静默降级，仍跳转教案编辑
    }
    onNavChange("prep-lesson");
  };

  const renderNode = (node: CatalogTreeNode, depth: number) => {
    const hasChildren = node.children.length > 0;
    const isClosed = isCollapsed(node.id);
    const nodeLabel = (() => {
      if (node.level === "lesson") return t("prepCatalog.level.lesson");
      if (node.level === "unit") return t("prepCatalog.level.unit");
      return t("prepCatalog.level.edition");
    })();

    return (
      <div key={String(node.id)}>
        <div
          className={cn(
            "group flex items-center gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-muted/60",
            depth === 0 && "bg-muted/30",
          )}
          style={{ paddingLeft: depth * 20 + 8 }}
        >
          {hasChildren ? (
            <button
              type="button"
              onClick={() => toggleNode(node.id)}
              className="shrink-0 rounded p-0.5 text-muted-foreground hover:bg-muted"
              aria-label={
                isClosed ? t("prepCatalog.expand") : t("prepCatalog.collapse")
              }
            >
              {isClosed ? (
                <ChevronRight className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>
          ) : (
            <span className="w-5 shrink-0" />
          )}
          <Badge
            variant="outline"
            className={cn(
              "shrink-0 text-[10px] px-1.5 py-0 h-4",
              node.level === "lesson" &&
                "bg-primary/5 text-primary border-primary/20",
              node.level === "unit" &&
                "bg-emerald-50 text-emerald-600 border-emerald-200",
              node.level === "edition" &&
                "bg-slate-100 text-slate-600 border-slate-200",
            )}
          >
            {nodeLabel}
          </Badge>
          <span className="flex-1 truncate text-sm">{node.name}</span>
          <Button
            size="sm"
            variant="outline"
            className="opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity h-7 px-2.5 gap-1 text-xs"
            onClick={() => goGenerateLesson(node)}
          >
            <Sparkles className="w-3.5 h-3.5" />
            {t("prepCatalog.aiGenerate")}
          </Button>
        </div>
        {hasChildren && !isClosed && (
          <div className="border-l border-muted ml-[22px]">
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Badge variant="outline" className="gap-1">
            <FolderTree className="w-3 h-3" />
            {t("prepCatalog.badge")}
          </Badge>
        </div>
        <h2 className="text-lg font-semibold text-foreground">
          {t("prepCatalog.title")}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          {t("prepCatalog.subtitle")}
        </p>
      </div>

      {/* 筛选区 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            {t("prepCatalog.subject")}
          </span>
          <Select value={subject} onValueChange={setSubject}>
            <SelectTrigger className="w-32">
              <SelectValue placeholder={t("prepCatalog.selectSubject")} />
            </SelectTrigger>
            <SelectContent>
              {SUBJECT_OPTIONS.map((item) => (
                <SelectItem key={item} value={item}>
                  {translateSubjectName(locale, item)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            {t("prepCatalog.grade")}
          </span>
          <Select value={grade} onValueChange={setGrade}>
            <SelectTrigger className="w-32">
              <SelectValue placeholder={t("prepCatalog.selectGrade")} />
            </SelectTrigger>
            <SelectContent>
              {GRADE_OPTIONS.map((item) => (
                <SelectItem key={item} value={item}>
                  {gradeLabel(locale, item)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            {t("prepCatalog.edition")}
          </span>
          <Select value={edition} onValueChange={setEdition}>
            <SelectTrigger className="w-32">
              <SelectValue placeholder={t("prepCatalog.selectEdition")} />
            </SelectTrigger>
            <SelectContent>
              {EDITION_OPTIONS.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* 内容区 */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <BookMarked className="w-4 h-4 text-muted-foreground" />
            {t("prepCatalog.title")}
          </CardTitle>
          <CardDescription className="text-xs">
            {subject && grade ? (
              <>
                {translateSubjectName(locale, subject)} ·{" "}
                {gradeLabel(locale, grade)} · {edition}
              </>
            ) : (
              t("prepCatalog.subtitle")
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin mb-3" />
              <span className="text-sm">{t("prepCatalog.loading")}</span>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-16">
              <p className="text-sm text-destructive mb-3">{error}</p>
              <Button variant="outline" size="sm" onClick={() => void load()}>
                <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                {t("prepCatalog.retry")}
              </Button>
            </div>
          ) : tree.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <FolderTree className="w-8 h-8 text-muted-foreground/40 mb-3" />
              <p className="text-sm font-medium text-foreground mb-1">
                {t("prepCatalog.emptyTitle")}
              </p>
              <p className="text-xs text-muted-foreground max-w-md">
                {t("prepCatalog.emptyDesc")}
              </p>
            </div>
          ) : (
            <div className="space-y-0.5">
              {tree.map((root) => renderNode(root, 0))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
