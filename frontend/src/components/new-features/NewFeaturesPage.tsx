import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useLocale } from "@/contexts/LocaleContext";
import {
  ArrowRight,
  Database,
  Bot,
  Target,
  ChartColumn,
  Network,
  FileSearch,
  BrainCircuit,
  BookOpen,
  SquareUserRound,
  ShieldCheck,
  LayoutGrid,
  Sparkles,
  LucideIcon,
} from "lucide-react";

interface WhatsNewItem {
  key: string;
  icon: LucideIcon;
  /** 点击「前往使用」跳转的功能域 id；缺省时展示入口路径文案 */
  navId?: string;
  /** 跳转时额外携带的 class-dashboard 子标签（如「错题变式推荐」→ wrong-questions） */
  tab?: string;
}

const CATEGORY_A: WhatsNewItem[] = [
  { key: "a1", icon: Database, navId: "school-dashboard" },
  { key: "a2", icon: Bot },
  { key: "a3", icon: Target, navId: "class-dashboard", tab: "wrong-questions" },
  { key: "a4", icon: ChartColumn, navId: "school-dashboard" },
  { key: "a5", icon: Network, navId: "class-knowledge" },
  { key: "a6", icon: FileSearch, navId: "class-dashboard", tab: "wrong-questions" },
  { key: "a7", icon: BrainCircuit, navId: "ai-targeted" },
];

const CATEGORY_B: WhatsNewItem[] = [
  { key: "b1", icon: BookOpen, navId: "prep-matrix" },
  { key: "b2", icon: SquareUserRound, navId: "wuyu-profile" },
  { key: "b3", icon: ShieldCheck, navId: "school-dashboard" },
];

export function NewFeaturesPage({
  onNavChange,
}: {
  onNavChange: (id: string, tab?: string) => void;
}) {
  const { t } = useLocale();

  const renderItem = (item: WhatsNewItem) => {
    const Icon = item.icon;
    return (
      <Card key={item.key} className="flex flex-col">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
              <Icon className="w-5 h-5 text-primary" />
            </div>
            <CardTitle className="text-sm">
              {t(`whatsnew.${item.key}.name`, undefined, item.key)}
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent className="flex-1 flex flex-col gap-3">
          <CardDescription className="text-xs leading-relaxed">
            {t(`whatsnew.${item.key}.desc`)}
          </CardDescription>
          <div className="mt-auto pt-1">
            {item.navId ? (
              <Button
                size="sm"
                variant="outline"
                className="gap-1"
                onClick={() => onNavChange(item.navId!, item.tab)}
              >
                {t("whatsnew.enter")}
                <ArrowRight className="w-3 h-3" />
              </Button>
            ) : (
              <span className="text-xs text-muted-foreground">
                {t("whatsnew.entryPath")}
                {t(`whatsnew.${item.key}.path`)}
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-lg font-semibold text-foreground">
          {t("whatsnew.title")}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          {t("whatsnew.subtitle")}
        </p>
      </div>

      {/* 热点推荐 */}
      <div className="relative overflow-hidden rounded-2xl border border-primary/30 bg-gradient-to-br from-primary/10 via-primary/5 to-background p-6">
        <div className="absolute right-4 top-4">
          <Badge variant="secondary" className="gap-1">
            <Sparkles className="w-3 h-3" />
            {t("whatsnew.hot.badge")}
          </Badge>
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
            <LayoutGrid className="w-6 h-6 text-primary" />
          </div>
          <div className="flex-1">
            <h3 className="text-base font-semibold text-foreground">
              {t("whatsnew.hot.title")}
            </h3>
            <p className="text-sm text-muted-foreground mt-1">
              {t("whatsnew.hot.desc")}
            </p>
          </div>
          <Button className="gap-1.5" onClick={() => onNavChange("prep-matrix")}>
            {t("whatsnew.hot.enter")}
            <ArrowRight className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* A 类 · 题库驱动能力 */}
      <section className="space-y-3">
        <h3 className="text-sm font-medium text-foreground">
          {t("whatsnew.cat.a")}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {CATEGORY_A.map(renderItem)}
        </div>
      </section>

      {/* B 类 · 平台能力 */}
      <section className="space-y-3">
        <h3 className="text-sm font-medium text-foreground">
          {t("whatsnew.cat.b")}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {CATEGORY_B.map(renderItem)}
        </div>
      </section>
    </div>
  );
}
