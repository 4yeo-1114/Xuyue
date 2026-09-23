import { useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Search, ChevronDown, ChevronUp, TrendingUp, TrendingDown, Minus, Eye, History } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StudentCandidate } from "./targetedData";

interface StudentSelectorProps {
  recommended: StudentCandidate[];
  allStudents: StudentCandidate[];
  selected: StudentCandidate | null;
  onSelect: (s: StudentCandidate) => void;
  onNavChange: (id: string) => void;
}

const STATUS_COLORS: Record<string, string> = {
  warning: "bg-destructive/10 border-destructive/30 text-destructive",
  attention: "bg-orange-50 border-orange-200 text-orange-700",
  fluctuate: "bg-amber-50 border-amber-200 text-amber-700",
  improving: "bg-emerald-50 border-emerald-200 text-emerald-700",
  stable: "bg-muted border-border text-muted-foreground",
};

const TIER_COLORS: Record<string, string> = {
  A: "bg-emerald-100 text-emerald-800",
  B: "bg-amber-100 text-amber-800",
  C: "bg-red-100 text-red-800",
};

function TrendIcon({ trend }: { trend: number }) {
  if (trend > 0) return <span className="flex items-center text-emerald-600 text-[11px]"><TrendingUp className="w-3 h-3 mr-0.5" />+{trend}</span>;
  if (trend < 0) return <span className="flex items-center text-destructive text-[11px]"><TrendingDown className="w-3 h-3 mr-0.5" />{trend}</span>;
  return <span className="flex items-center text-muted-foreground text-[11px]"><Minus className="w-3 h-3 mr-0.5" />0</span>;
}

export function StudentSelector({ recommended, allStudents, selected, onSelect, onNavChange }: StudentSelectorProps) {
  const { t, locale } = useLocale();

  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState(false);

  const filtered = allStudents.filter(s => s.name.includes(search) || s.number.includes(search));

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{t("classDetail.selectTargetStudentTitle")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-muted-foreground" />
          <Input placeholder={t("classDetail.搜索姓名 学号")} className="pl-8 h-9 text-xs" value={search} onChange={e => setSearch(e.target.value)} />
        </div>

        {/* AI Recommended */}
        {!search && (
          <div data-tour="ti-recommended">
            <p className="text-[11px] text-muted-foreground mb-2">{t("classDetail.aiRecommendedTargetsTitle")}</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {recommended.map(s => (
                <button
                  key={s.name}
                  onClick={() => onSelect(s)}
                  className={cn(
                    "rounded-lg border p-2.5 text-left transition-all hover:shadow-sm",
                    STATUS_COLORS[s.status],
                    selected?.name === s.name && "ring-2 ring-primary ring-offset-1"
                  )}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    <div className="w-6 h-6 rounded-full bg-background/80 flex items-center justify-center text-[10px] font-bold">
                      {s.name[0]}
                    </div>
                    <span className="text-xs font-semibold">{s.name}</span>
                  </div>
                  <div className="text-[11px] font-bold">{t("classDetail.scorePoints", { score: s.score })}</div>
                  <TrendIcon trend={s.trend} />
                  <p className="text-[10px] mt-1 opacity-80 truncate">{s.weakPoints.join("+")}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Expand full list */}
        <div>
          <button onClick={() => setExpanded(!expanded)} className="text-xs text-primary flex items-center gap-1 hover:underline">
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? t("classDetail.collapseList") : t("classDetail.expandClassList", { count: allStudents.length })}
          </button>
          {(expanded || search) && (
            <div className="mt-2 max-h-48 overflow-y-auto space-y-1 border rounded-lg p-2">
              {filtered.map(s => (
                <button
                  key={s.name}
                  onClick={() => onSelect(s)}
                  className={cn(
                    "w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-xs hover:bg-muted/50 transition-colors",
                    selected?.name === s.name && "bg-primary/5 ring-1 ring-primary/20"
                  )}
                >
                  <div className="w-5 h-5 rounded-full bg-muted flex items-center justify-center text-[10px] font-bold">{s.name[0]}</div>
                  <span className="font-medium">{s.name}</span>
                  <Badge variant="secondary" className={cn("text-[10px] px-1.5 py-0", TIER_COLORS[s.tier])}>{t("classDetail.tierLabel", { tier: s.tier })}</Badge>
                  <span className="ml-auto font-bold">{s.score}</span>
                  <TrendIcon trend={s.trend} />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Selected summary */}
        {selected && (
          <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-sm font-bold text-primary">{selected.name[0]}</div>
              <div>
                <p className="text-xs font-semibold">{selected.name}
                  <span className="text-muted-foreground font-normal ml-1">{t("classDetail.studentNumberLabel", { number: selected.number })}</span>
                </p>
                <p className="text-[11px] text-muted-foreground">{t("classDetail.selectedStudentSummary", { score: selected.score, status: selected.statusLabel, weakPoints: selected.weakPoints.join("、") })}</p>
              </div>
            </div>
            <div className="flex gap-1">
              <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]" onClick={() => onNavChange("class-students")}>
                <Eye className="w-3 h-3 mr-0.5" />{t("classDetail.fullProfile")}
              </Button>
              <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px]">
                <History className="w-3 h-3 mr-0.5" />{t("classDetail.historyTrack")}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
