import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { BookOpen, Link2, Save, Trash2, BarChart3, Users, Loader2 } from "lucide-react";
import { useLocale } from "@/contexts/LocaleContext";
import type { KnowledgePoint } from "./subjectConfigData";

interface Props {
  point: KnowledgePoint | null;
  onSave: (data: Record<string, any>) => void;
  onDelete: () => void;
  isSaving: boolean;
  isDeleting: boolean;
  isDbMode: boolean;
}

const BLOOM_LEVELS = ["识记", "理解", "应用", "评价"] as const;
const BLOOM_KEYS: Record<string, string> = {
  识记: "settingsSubject.bloom.remember",
  理解: "settingsSubject.bloom.understand",
  应用: "settingsSubject.bloom.apply",
  评价: "settingsSubject.bloom.evaluate",
};

export function KnowledgePointEditor({ point, onSave, onDelete, isSaving, isDeleting, isDbMode }: Props) {
  const { t } = useLocale();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<Record<string, any>>({});

  const translateBloom = (level: string) => t(BLOOM_KEYS[level] ?? level);

  useEffect(() => {
    if (point) {
      setForm({
        code: point.code,
        name: point.name,
        level: point.level,
        mastery: point.mastery,
        hours: point.hours,
        keyPoint: point.keyPoint,
        difficulty: point.difficulty,
        commonErrors: point.commonErrors,
        prerequisite: point.prerequisite,
        postrequisite: point.postrequisite,
        related: point.related,
        resources: point.resources,
      });
      setEditing(false);
    }
  }, [point?.id]);

  if (!point) {
    return (
      <Card className="h-full">
        <CardContent className="flex items-center justify-center h-full min-h-[400px] text-muted-foreground text-sm">
          {t("settingsSubject.knowledgeEditor.emptyHint")}
        </CardContent>
      </Card>
    );
  }

  const handleSave = () => {
    onSave(form);
    setEditing(false);
  };

  return (
    <Card className="h-full overflow-auto">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-primary" />
            {t("settingsSubject.knowledgeEditor.title")} · {point.code} {point.name}
          </CardTitle>
          {isDbMode && !editing && (
            <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setEditing(true)}>{t("common.edit")}</Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="space-y-2">
          <h4 className="font-medium text-foreground">{t("settingsSubject.knowledgeEditor.basicInfo")}</h4>
          {editing ? (
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">{t("settingsSubject.knowledgeEditor.code")}</label>
                <Input value={form.code} onChange={e => setForm(f => ({ ...f, code: e.target.value }))} className="h-8 text-xs" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">{t("settingsSubject.knowledgeEditor.name")}</label>
                <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="h-8 text-xs" />
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2 rounded bg-muted/50"><span className="text-muted-foreground">{t("settingsSubject.knowledgeEditor.code")}：</span>{point.code}</div>
              <div className="p-2 rounded bg-muted/50"><span className="text-muted-foreground">{t("settingsSubject.knowledgeEditor.name")}：</span>{point.name}</div>
            </div>
          )}
          <div className="flex flex-wrap gap-1.5">
            {point.prerequisite.length > 0 && (
              <div className="text-xs text-muted-foreground"><Link2 className="w-3 h-3 inline mr-0.5" />{t("settingsSubject.knowledgeEditor.prerequisite")}{point.prerequisite.join("、")}</div>
            )}
            {point.postrequisite.length > 0 && (
              <div className="text-xs text-muted-foreground ml-2">{t("settingsSubject.knowledgeEditor.postrequisite")}{point.postrequisite.join("、")}</div>
            )}
            {point.related.length > 0 && (
              <div className="text-xs text-muted-foreground ml-2">{t("settingsSubject.knowledgeEditor.related")}{point.related.join("、")}</div>
            )}
          </div>
        </div>

        <Separator />

        <div className="space-y-2">
          <h4 className="font-medium text-foreground">{t("settingsSubject.knowledgeEditor.abilityReq")}</h4>
          {editing ? (
            <Select value={form.level} onValueChange={v => setForm(f => ({ ...f, level: v }))}>
              <SelectTrigger className="h-8 text-xs w-32"><SelectValue /></SelectTrigger>
              <SelectContent>
                {BLOOM_LEVELS.map(l => <SelectItem key={l} value={l}>{translateBloom(l)}</SelectItem>)}
              </SelectContent>
            </Select>
          ) : (
            <Badge variant={point.level === "评价" ? "default" : point.level === "应用" ? "secondary" : "outline"} className="text-xs">
              {translateBloom(point.level)}
            </Badge>
          )}
        </div>

        <Separator />

        <div className="space-y-2">
          <h4 className="font-medium text-foreground">{t("settingsSubject.knowledgeEditor.teachingAdvice")}</h4>
          {editing ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">{t("settingsSubject.knowledgeEditor.hours")}</label>
                  <Input type="number" value={form.hours} onChange={e => setForm(f => ({ ...f, hours: Number(e.target.value) }))} className="h-8 text-xs" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">{t("settingsSubject.knowledgeEditor.mastery")}</label>
                  <Input type="number" value={form.mastery} onChange={e => setForm(f => ({ ...f, mastery: Number(e.target.value) }))} className="h-8 text-xs" />
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">{t("settingsSubject.knowledgeEditor.keyPoint")}</label>
                <Input value={form.keyPoint} onChange={e => setForm(f => ({ ...f, keyPoint: e.target.value }))} className="h-8 text-xs" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">{t("settingsSubject.knowledgeEditor.difficulty")}</label>
                <Input value={form.difficulty} onChange={e => setForm(f => ({ ...f, difficulty: e.target.value }))} className="h-8 text-xs" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">{t("settingsSubject.knowledgeEditor.commonErrors")}</label>
                <Textarea value={form.commonErrors} onChange={e => setForm(f => ({ ...f, commonErrors: e.target.value }))} className="min-h-[60px] text-xs" />
              </div>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="p-2 rounded bg-muted/50"><span className="text-muted-foreground">{t("settingsSubject.knowledgeEditor.hours")}：</span>{t("settingsSubject.knowledgeEditor.hoursUnit", { n: point.hours })}</div>
                <div className="p-2 rounded bg-muted/50"><span className="text-muted-foreground">{t("settingsSubject.knowledgeEditor.mastery")}：</span><span className={point.mastery < 60 ? "text-destructive font-medium" : "text-foreground"}>{point.mastery}%</span></div>
              </div>
              <div className="text-xs space-y-1">
                <p><span className="text-muted-foreground">{t("settingsSubject.knowledgeEditor.keyPoint")}：</span>{point.keyPoint}</p>
                <p><span className="text-muted-foreground">{t("settingsSubject.knowledgeEditor.difficulty")}：</span>{point.difficulty}</p>
                <p><span className="text-muted-foreground">{t("settingsSubject.knowledgeEditor.commonErrors")}：</span><span className="text-destructive/80">{point.commonErrors}</span></p>
              </div>
            </>
          )}
        </div>

        <Separator />

        <div className="space-y-2">
          <h4 className="font-medium text-foreground">{t("settingsSubject.knowledgeEditor.resources")}</h4>
          {point.resources.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t("settingsSubject.knowledgeEditor.noResources")}</p>
          ) : (
            <div className="space-y-1">
              {point.resources.map((r, i) => (
                <div key={i} className="flex items-center gap-2 text-xs p-1.5 rounded bg-muted/40">
                  <Badge variant="outline" className="text-[10px] h-4 px-1">{r.type}</Badge>
                  <span>{r.name}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <Separator />

        <div className="flex items-center gap-2 pt-1">
          {editing ? (
            <>
              <Button size="sm" className="flex-1" onClick={handleSave} disabled={isSaving}>
                {isSaving && <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />}
                <Save className="w-3.5 h-3.5 mr-1" />{t("common.save")}
              </Button>
              <Button variant="outline" size="sm" onClick={() => setEditing(false)}>{t("common.cancel")}</Button>
            </>
          ) : (
            <>
              <Button variant="outline" size="sm"><BarChart3 className="w-3.5 h-3.5 mr-1" />{t("settingsSubject.knowledgeEditor.teachingData")}</Button>
              <Button variant="outline" size="sm"><Users className="w-3.5 h-3.5 mr-1" />{t("settingsSubject.knowledgeEditor.masteryStatus")}</Button>
            </>
          )}
          {isDbMode && (
            <Button variant="ghost" size="sm" className="text-destructive" onClick={onDelete} disabled={isDeleting}>
              {isDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
