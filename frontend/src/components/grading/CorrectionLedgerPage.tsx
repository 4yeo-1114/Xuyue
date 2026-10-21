import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ClipboardList,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useLocale } from "@/contexts/LocaleContext";
import {
  fetchCorrectionLedger,
  type CorrectionLedgerRow,
} from "@/services/gradingApi";

const WINDOW_OPTIONS = [7, 30, 90] as const;

function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatScore(v?: number | null): string {
  if (v === null || v === undefined) return "—";
  return String(v);
}

/** 题号列：主号 + 小题/作答区 */
function questionLabel(row: CorrectionLedgerRow): string {
  const idx = row.index != null && String(row.index).trim() !== "" ? String(row.index) : "—";
  const sub = row.sub_index != null && String(row.sub_index).trim() !== "" ? String(row.sub_index) : "";
  return sub ? `${idx}-${sub}` : idx;
}

/**
 * 改分/评语台账查看页（客户清单 #8「人工批改记录」）。
 * 列表展示 GET /grading/correction-ledger：时间 / 学生卷 / 题号 / 改动前后 / 来源。
 */
export function CorrectionLedgerPage() {
  const { t } = useLocale();
  const [rows, setRows] = useState<CorrectionLedgerRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [days, setDays] = useState<number>(30);
  const [includeVoided, setIncludeVoided] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetchCorrectionLedger({ days, includeVoided });
      setRows(res.rows || []);
    } catch (e) {
      setError(e?.message || t("grading.ledger.loadError"));
    } finally {
      setLoading(false);
    }
  }, [days, includeVoided, t]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, includeVoided]);

  const sourceLabel = useCallback(
    (source?: string | null) => {
      const key = `grading.ledger.source.${source || ""}`;
      const label = t(key);
      // t 找不到时原样返回 key，此时退回原始 source
      return label === key ? source || "—" : label;
    },
    [t],
  );

  /** 改动前/后单元格：判定 + 分数 + 评语摘要 */
  const changeCell = useCallback(
    (row: CorrectionLedgerRow, side: "before" | "after") => {
      const result = side === "before" ? row.was_result : row.new_result;
      const score = side === "before" ? row.was_score : row.new_score;
      const comment = side === "before" ? row.was_comment : row.new_comment;
      const showScore = row.was_score != null || row.new_score != null;
      return (
        <div className="space-y-0.5 text-xs">
          <div className="font-medium text-foreground">
            {result || t("grading.ledger.unchanged")}
          </div>
          {showScore ? (
            <div className="text-muted-foreground">
              {t("grading.ledger.colScore")} {formatScore(score)}
            </div>
          ) : null}
          {comment ? (
            <div className="text-muted-foreground line-clamp-2 max-w-[200px]">
              {comment}
            </div>
          ) : null}
        </div>
      );
    },
    [t],
  );

  const countText = useMemo(
    () => t("grading.ledger.totalCount", { count: rows.length }),
    [t, rows.length],
  );

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-foreground">
            {t("grading.ledger.title")}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t("grading.ledger.subtitle")}
          </p>
        </div>
        <div className="flex items-end gap-3 flex-wrap">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">
              {t("grading.ledger.windowDays")}
            </Label>
            <Select
              value={String(days)}
              onValueChange={(v) => setDays(Number(v) || 30)}
            >
              <SelectTrigger className="w-[140px] h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {WINDOW_OPTIONS.map((d) => (
                  <SelectItem key={d} value={String(d)}>
                    {t("grading.ledger.windowDaysOption", { days: d })}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2 pb-1">
            <Switch
              id="ledger-voided"
              checked={includeVoided}
              onCheckedChange={setIncludeVoided}
            />
            <Label htmlFor="ledger-voided" className="text-xs cursor-pointer">
              {t("grading.ledger.includeVoided")}
            </Label>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={load}
            disabled={loading}
            className="mb-0.5"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            {t("grading.ledger.refresh")}
          </Button>
        </div>
      </div>

      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-primary" />
            {t("grading.ledger.title")}
            <span className="text-xs font-normal text-muted-foreground ml-auto">
              {countText}
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin mr-2" />
              {t("grading.ledger.loading")}
            </div>
          ) : error ? (
            <div className="flex flex-col items-center py-16 text-center">
              <AlertTriangle className="w-8 h-8 text-muted-foreground mb-3" />
              <p className="text-sm text-muted-foreground">{error}</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={load}
              >
                {t("grading.ledger.retry")}
              </Button>
            </div>
          ) : rows.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-center">
              <div className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center mb-4">
                <ClipboardList className="w-8 h-8 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium text-foreground">
                {t("grading.ledger.empty")}
              </p>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm">
                {t("grading.ledger.emptyHint")}
              </p>
            </div>
          ) : (
            <div className="rounded-md border border-border/50 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="whitespace-nowrap">
                      {t("grading.ledger.colTime")}
                    </TableHead>
                    <TableHead className="whitespace-nowrap">
                      {t("grading.ledger.colStudent")}
                    </TableHead>
                    <TableHead className="whitespace-nowrap">
                      {t("grading.ledger.colQuestion")}
                    </TableHead>
                    <TableHead>
                      {t("grading.ledger.colBefore")}
                    </TableHead>
                    <TableHead>
                      {t("grading.ledger.colAfter")}
                    </TableHead>
                    <TableHead className="whitespace-nowrap">
                      {t("grading.ledger.colSource")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row, i) => (
                    <TableRow key={row.id || `${row.created_at}-${i}`}>
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                        {formatTime(row.created_at)}
                      </TableCell>
                      <TableCell className="text-sm max-w-[180px]">
                        <div className="truncate" title={row.paper_name || ""}>
                          {row.paper_name || "—"}
                        </div>
                        {row.voided ? (
                          <Badge
                            variant="outline"
                            className="mt-0.5 text-[10px] text-muted-foreground"
                          >
                            {t("grading.ledger.voidedBadge")}
                          </Badge>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-sm whitespace-nowrap">
                        {questionLabel(row)}
                      </TableCell>
                      <TableCell>{changeCell(row, "before")}</TableCell>
                      <TableCell>{changeCell(row, "after")}</TableCell>
                      <TableCell className="text-xs whitespace-nowrap">
                        <Badge variant="secondary" className="font-normal">
                          {sourceLabel(row.source)}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default CorrectionLedgerPage;
