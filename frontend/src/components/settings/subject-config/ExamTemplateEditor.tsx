import { useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FileText, Plus, Pencil, Trash2, Check, X, Download, Loader2, Database, FlaskConical, GripVertical } from "lucide-react";
import { useExamTemplates, ExamTemplate } from "@/hooks/useExamTemplates";
import { cn } from "@/lib/utils";
import { useLocale } from "@/contexts/LocaleContext";

const QUESTION_TYPE_KEYS: Record<string, string> = {
  选择题: "settingsSubject.questionType.choice",
  填空题: "settingsSubject.questionType.fill",
  简答题: "settingsSubject.questionType.shortAnswer",
  作文: "settingsSubject.questionType.essay",
  判断题: "settingsSubject.questionType.judge",
};

function getDefaultQuestionTypes(subject: string) {
  if (subject === "语文" || subject === "英语") {
    return [
      { type: "选择题", count: 10, scoreEach: 2 },
      { type: "填空题", count: 10, scoreEach: 2 },
      { type: "简答题", count: 5, scoreEach: 6 },
      { type: "作文", count: 1, scoreEach: 30 },
    ];
  }
  return [
    { type: "选择题", count: 15, scoreEach: 3 },
    { type: "填空题", count: 10, scoreEach: 2 },
    { type: "判断题", count: 10, scoreEach: 1 },
    { type: "简答题", count: 5, scoreEach: 5 },
  ];
}

interface Props {
  fullSubject: string;
  rawSubject: string;
  displaySubject?: string;
}

interface EditRow {
  type_name: string;
  default_count: number;
  default_score_each: number;
}

export function ExamTemplateEditor({ fullSubject, rawSubject, displaySubject }: Props) {
  const { t } = useLocale();
  const translateQuestionType = (type: string) => t(QUESTION_TYPE_KEYS[type] ?? type);
  const { templates, isLoading, isEmpty, create, update, remove, reorder, seedDefaults } = useExamTemplates(fullSubject);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editRow, setEditRow] = useState<EditRow>({ type_name: "", default_count: 10, default_score_each: 2 });
  const [adding, setAdding] = useState(false);
  const [newRow, setNewRow] = useState<EditRow>({ type_name: "", default_count: 10, default_score_each: 2 });
  const dragItem = useRef<number | null>(null);
  const dragOverItem = useRef<number | null>(null);
  const [dragIdx, setDragIdx] = useState<number | null>(null);

  const defaults = getDefaultQuestionTypes(rawSubject);
  const displayItems = templates.length > 0
    ? templates
    : defaults.map((d, i) => ({ id: `mock-${i}`, type_name: d.type, default_count: d.count, default_score_each: d.scoreEach, sort_order: i, subject: fullSubject }));
  const usingDb = templates.length > 0;

  const totalScore = displayItems.reduce((s, t) => s + t.default_count * t.default_score_each, 0);

  const startEdit = (template: ExamTemplate) => {
    setEditingId(template.id);
    setEditRow({ type_name: template.type_name, default_count: template.default_count, default_score_each: template.default_score_each });
  };

  const saveEdit = () => {
    if (!editingId) return;
    update.mutate({ id: editingId, ...editRow }, { onSuccess: () => setEditingId(null) });
  };

  const handleAdd = () => {
    if (!newRow.type_name.trim()) return;
    create.mutate({ ...newRow, sort_order: displayItems.length }, {
      onSuccess: () => { setAdding(false); setNewRow({ type_name: "", default_count: 10, default_score_each: 2 }); },
    });
  };

  const handleDragStart = (idx: number) => {
    dragItem.current = idx;
    setDragIdx(idx);
  };

  const handleDragEnter = (idx: number) => {
    dragOverItem.current = idx;
  };

  const handleDragEnd = () => {
    if (dragItem.current === null || dragOverItem.current === null || dragItem.current === dragOverItem.current || !usingDb) {
      setDragIdx(null);
      return;
    }
    const ids = displayItems.map(t => t.id);
    const [removed] = ids.splice(dragItem.current, 1);
    ids.splice(dragOverItem.current, 0, removed);
    reorder.mutate(ids);
    dragItem.current = null;
    dragOverItem.current = null;
    setDragIdx(null);
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary" />
            {t("settingsSubject.examTemplate.title")}
            <Badge variant="outline" className="text-xs font-normal">{displaySubject ?? fullSubject}</Badge>
          </CardTitle>
          <div className="flex items-center gap-2">
            {usingDb ? (
              <Badge className="text-[10px] gap-1 bg-green-500/10 text-green-700 border-green-200 hover:bg-green-500/10">
                <Database className="w-3 h-3" />{t("settingsSubject.examTemplate.sourceDb")}
              </Badge>
            ) : (
              <Badge variant="secondary" className="text-[10px] gap-1">
                <FlaskConical className="w-3 h-3" />{t("settingsSubject.examTemplate.sourceDefault")}
              </Badge>
            )}
            <span className="text-xs text-muted-foreground">
              {t("settingsSubject.examTemplate.totalScore", { total: totalScore })}
            </span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground text-sm gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />{t("common.loading")}
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  {usingDb && <TableHead className="w-[40px]"></TableHead>}
                  <TableHead className="w-[140px]">{t("settingsSubject.examTemplate.colType")}</TableHead>
                  <TableHead className="w-[80px] text-center">{t("settingsSubject.examTemplate.colCount")}</TableHead>
                  <TableHead className="w-[80px] text-center">{t("settingsSubject.examTemplate.colScoreEach")}</TableHead>
                  <TableHead className="w-[80px] text-center">{t("settingsSubject.examTemplate.colSubtotal")}</TableHead>
                  {usingDb && <TableHead className="w-[100px] text-right">{t("settingsSubject.examTemplate.colActions")}</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {displayItems.map((item, idx) => (
                  editingId === item.id ? (
                    <TableRow key={item.id}>
                      {usingDb && <TableCell />}
                      <TableCell>
                        <Input value={editRow.type_name} onChange={e => setEditRow(p => ({ ...p, type_name: e.target.value }))} className="h-7 text-xs" />
                      </TableCell>
                      <TableCell>
                        <Input type="number" value={editRow.default_count} onChange={e => setEditRow(p => ({ ...p, default_count: Number(e.target.value) }))} className="h-7 text-xs text-center" />
                      </TableCell>
                      <TableCell>
                        <Input type="number" value={editRow.default_score_each} onChange={e => setEditRow(p => ({ ...p, default_score_each: Number(e.target.value) }))} className="h-7 text-xs text-center" />
                      </TableCell>
                      <TableCell className="text-center text-xs font-medium">{editRow.default_count * editRow.default_score_each}</TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={saveEdit} disabled={update.isPending}>
                          <Check className="w-3.5 h-3.5 text-green-600" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setEditingId(null)}>
                          <X className="w-3.5 h-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ) : (
                    <TableRow
                      key={item.id}
                      draggable={usingDb && !editingId}
                      onDragStart={() => handleDragStart(idx)}
                      onDragEnter={() => handleDragEnter(idx)}
                      onDragEnd={handleDragEnd}
                      onDragOver={e => e.preventDefault()}
                      className={cn(
                        usingDb && !editingId && "cursor-grab active:cursor-grabbing",
                        dragIdx === idx && "opacity-50"
                      )}
                    >
                      {usingDb && (
                        <TableCell className="w-[40px] px-2">
                          <GripVertical className="w-4 h-4 text-muted-foreground" />
                        </TableCell>
                      )}
                      <TableCell className="text-xs font-medium">{translateQuestionType(item.type_name)}</TableCell>
                      <TableCell className="text-xs text-center">{item.default_count}</TableCell>
                      <TableCell className="text-xs text-center">{item.default_score_each}</TableCell>
                      <TableCell className="text-xs text-center font-medium">{item.default_count * item.default_score_each}</TableCell>
                      {usingDb && (
                        <TableCell className="text-right">
                          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => startEdit(item as ExamTemplate)}>
                            <Pencil className="w-3.5 h-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => remove.mutate(item.id)} disabled={remove.isPending}>
                            <Trash2 className="w-3.5 h-3.5 text-destructive" />
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                  )
                ))}
                {adding && (
                  <TableRow>
                    {usingDb && <TableCell />}
                    <TableCell>
                      <Input value={newRow.type_name} onChange={e => setNewRow(p => ({ ...p, type_name: e.target.value }))} placeholder={t("settingsSubject.examTemplate.typeNamePlaceholder")} className="h-7 text-xs" />
                    </TableCell>
                    <TableCell>
                      <Input type="number" value={newRow.default_count} onChange={e => setNewRow(p => ({ ...p, default_count: Number(e.target.value) }))} className="h-7 text-xs text-center" />
                    </TableCell>
                    <TableCell>
                      <Input type="number" value={newRow.default_score_each} onChange={e => setNewRow(p => ({ ...p, default_score_each: Number(e.target.value) }))} className="h-7 text-xs text-center" />
                    </TableCell>
                    <TableCell className="text-center text-xs font-medium">{newRow.default_count * newRow.default_score_each}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleAdd} disabled={create.isPending}>
                        <Check className="w-3.5 h-3.5 text-green-600" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setAdding(false)}>
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
            <div className="flex items-center gap-2">
              {usingDb && !adding && (
                <Button variant="outline" size="sm" className="text-xs gap-1" onClick={() => setAdding(true)}>
                  <Plus className="w-3.5 h-3.5" />{t("settingsSubject.examTemplate.addType")}
                </Button>
              )}
              {!usingDb && (
                <Button variant="outline" size="sm" className="text-xs gap-1" onClick={() => seedDefaults.mutate(rawSubject)} disabled={seedDefaults.isPending}>
                  {seedDefaults.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                  {t("settingsSubject.examTemplate.importDefaults")}
                </Button>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
