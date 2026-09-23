import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { ChevronDown, ChevronRight, Network, AlertTriangle, Edit3, ArrowUpDown, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";
import type { Unit } from "./subjectConfigData";

interface Props {
  units: Unit[];
  selectedKnowledgeId: string | null;
  onSelectKnowledge: (id: string) => void;
  onCreateKP?: (data: { unitId: string; code: string; name: string; level: string }) => void;
  subjectLabel?: string;
}

const BLOOM_LEVELS = ["识记", "理解", "应用", "评价"] as const;
const BLOOM_KEYS: Record<string, string> = {
  识记: "settingsSubject.bloom.remember",
  理解: "settingsSubject.bloom.understand",
  应用: "settingsSubject.bloom.apply",
  评价: "settingsSubject.bloom.evaluate",
};

export function KnowledgePreview({ units, selectedKnowledgeId, onSelectKnowledge, onCreateKP, subjectLabel }: Props) {
  const { t } = useLocale();
  const [expandedUnits, setExpandedUnits] = useState<Set<string>>(() => new Set(units.slice(0, 2).map(u => u.id)));
  const [addOpen, setAddOpen] = useState(false);
  const [addUnitId, setAddUnitId] = useState("");
  const [addCode, setAddCode] = useState("");
  const [addName, setAddName] = useState("");
  const [addLevel, setAddLevel] = useState<string>("识记");

  const translateBloom = (level: string) => t(BLOOM_KEYS[level] ?? level);

  const getMasteryBadge = (m: number) => {
    if (m < 60) return <Badge variant="destructive" className="text-[10px] h-4 px-1.5">{t("settingsSubject.knowledgePreview.weakBadge", { m })}</Badge>;
    return null;
  };

  const toggle = (id: string) => {
    setExpandedUnits(prev => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const totalKnowledge = units.reduce((s, u) => s + u.knowledgePoints.length, 0);
  const totalRelations = units.reduce((s, u) => s + u.knowledgePoints.reduce((ss, k) => ss + k.prerequisite.length + k.postrequisite.length + k.related.length, 0), 0);
  const avgMastery = totalKnowledge > 0 ? Math.round(units.flatMap(u => u.knowledgePoints).reduce((s, k) => s + k.mastery, 0) / totalKnowledge) : 0;

  const handleAdd = () => {
    if (!addUnitId || !addCode || !addName || !onCreateKP) return;
    onCreateKP({ unitId: addUnitId, code: addCode, name: addName, level: addLevel });
    setAddCode("");
    setAddName("");
    setAddOpen(false);
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Network className="w-4 h-4 text-primary" />
            {subjectLabel || t("settingsSubject.knowledgePreview.title")}
          </CardTitle>
          <div className="flex items-center gap-2">
            {onCreateKP && (
              <Dialog open={addOpen} onOpenChange={setAddOpen}>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm" className="h-7 text-xs"><Plus className="w-3 h-3 mr-1" />{t("settingsSubject.knowledgePreview.addPoint")}</Button>
                </DialogTrigger>
                <DialogContent className="sm:max-w-sm">
                  <DialogHeader><DialogTitle>{t("settingsSubject.knowledgePreview.addPoint")}</DialogTitle></DialogHeader>
                  <div className="space-y-3 pt-2">
                    <div className="space-y-1">
                      <label className="text-sm font-medium">{t("settingsSubject.knowledgePreview.unit")}</label>
                      <Select value={addUnitId} onValueChange={setAddUnitId}>
                        <SelectTrigger><SelectValue placeholder={t("settingsSubject.knowledgePreview.selectUnit")} /></SelectTrigger>
                        <SelectContent>
                          {units.map(u => (
                            <SelectItem key={u.id} value={u.id}>
                              {t("settingsSubject.knowledgePreview.unitLabel", { n: u.index })}{u.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <label className="text-sm font-medium">{t("settingsSubject.knowledgeEditor.code")}</label>
                      <Input value={addCode} onChange={e => setAddCode(e.target.value)} placeholder={t("settingsSubject.knowledgePreview.codePlaceholder")} className="h-8" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-sm font-medium">{t("settingsSubject.knowledgeEditor.name")}</label>
                      <Input value={addName} onChange={e => setAddName(e.target.value)} placeholder={t("settingsSubject.knowledgePreview.namePlaceholder")} className="h-8" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-sm font-medium">{t("settingsSubject.knowledgePreview.abilityLevel")}</label>
                      <Select value={addLevel} onValueChange={setAddLevel}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {BLOOM_LEVELS.map(l => <SelectItem key={l} value={l}>{translateBloom(l)}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                    <Button className="w-full" onClick={handleAdd} disabled={!addUnitId || !addCode || !addName}>{t("settingsSubject.knowledgePreview.confirmAdd")}</Button>
                  </div>
                </DialogContent>
              </Dialog>
            )}
            <Button variant="outline" size="sm" className="h-7 text-xs"><Edit3 className="w-3 h-3 mr-1" />{t("settingsSubject.knowledgePreview.editStructure")}</Button>
            <Button variant="outline" size="sm" className="h-7 text-xs"><ArrowUpDown className="w-3 h-3 mr-1" />{t("settingsSubject.knowledgePreview.reorderUnits")}</Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-1">
        {units.map(unit => (
          <div key={unit.id}>
            <button
              onClick={() => toggle(unit.id)}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted/60 text-left transition-colors"
            >
              {expandedUnits.has(unit.id) ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
              <span className="text-sm font-medium text-foreground">{t("settingsSubject.knowledgePreview.unitLabel", { n: unit.index })}{unit.name}</span>
              <span className="text-xs text-muted-foreground">（{unit.subtitle}）</span>
              {unit.knowledgePoints.some(k => k.isWeak) && <AlertTriangle className="w-3.5 h-3.5 text-destructive" />}
            </button>

            {expandedUnits.has(unit.id) && (
              <div className="ml-6 pl-3 border-l border-border/50 space-y-0.5 pb-1">
                {unit.knowledgePoints.map(kp => (
                  <button
                    key={kp.id}
                    onClick={() => onSelectKnowledge(kp.id)}
                    className={cn(
                      "w-full flex items-center gap-2 px-3 py-1.5 rounded-md text-left text-xs transition-all",
                      selectedKnowledgeId === kp.id ? "bg-primary/10 text-primary font-medium" : "hover:bg-muted/60 text-foreground/80"
                    )}
                  >
                    <span className="text-muted-foreground">{kp.code}</span>
                    <span className="flex-1 truncate">{kp.name}</span>
                    {getMasteryBadge(kp.mastery)}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        <div className="flex items-center gap-3 pt-3 text-xs text-muted-foreground border-t border-border mt-2">
          <span>{t("settingsSubject.knowledgePreview.unitCount", { n: units.length })}</span>
          <span>·</span>
          <span>{t("settingsSubject.knowledgePreview.pointCount", { n: totalKnowledge })}</span>
          <span>·</span>
          <span>{t("settingsSubject.knowledgePreview.relationCount", { n: totalRelations })}</span>
          <span>·</span>
          <span>{t("settingsSubject.knowledgePreview.avgMastery", { n: avgMastery })}</span>
          <span className="flex-1" />
          <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => setExpandedUnits(new Set(units.map(u => u.id)))}>{t("settingsSubject.knowledgePreview.expandAll")}</Button>
        </div>
      </CardContent>
    </Card>
  );
}
