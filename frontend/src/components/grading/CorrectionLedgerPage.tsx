import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Loader2,
  RefreshCw,
  Search,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
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
const PAGE_SIZE_OPTIONS = [20, 50, 100] as const;

/** 来源 chip 展示顺序（未知来源排尾部） */
const SOURCE_ORDER = [
  "human_ai_correct",
  "human_note",
  "human_paper_note",
  "human_wrong_note",
  "form_guard",
  "vl_ink",
];

const CHANGE_KIND_OPTIONS = ["result", "score", "comment"] as const;

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
 * 支持来源分类 chip、改动类型/考试筛选、关键词搜索、分页——成千上万条不卡。
 */
export function CorrectionLedgerPage() {
  const { t } = useLocale();
  const [rows, setRows] = useState<CorrectionLedgerRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [days, setDays] = useState<number>(30);
  const [includeVoided, setIncludeVoided] = useState(false);

  // 分类 / 搜索 / 分页
  const [source, setSource] = useState<string>(""); // "" = 全部
  const [changeKind, setChangeKind] = useState<string>(""); // "" = 全部
  const [folder, setFolder] = useState<string>(""); // "" = 全部考试
  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(50);
  const [total, setTotal] = useState(0);
  const [sourceCounts, setSourceCounts] = useState<Record<string, number>>({});
  const [folderCounts, setFolderCounts] = useState<
    Array<{ folder?: string | null; count?: number }>
  >([]);

  // 请求序号守卫：过滤条件连跳时丢弃过期响应
  const seqRef = useRef(0);
  const qRef = useRef("");

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    setLoading(true);
    setError("");
    try {
      const res = await fetchCorrectionLedger({
        days,
        includeVoided,
        source: source || undefined,
        folder: folder || undefined,
        changeKind: changeKind || undefined,
        q: q || undefined,
        page,
        pageSize,
      });
      if (seq !== seqRef.current) return; // 过期响应丢弃
      setRows(res.rows || []);
      setTotal(res.total ?? 0);
      setSourceCounts(res.source_counts || {});
      setFolderCounts(res.folder_counts || []);
    } catch (e) {
      if (seq !== seqRef.current) return;
      setError(e?.message || t("grading.ledger.loadError"));
    } finally {
      if (seq === seqRef.current) setLoading(false);
    }
  }, [days, includeVoided, source, folder, changeKind, q, page, pageSize, t]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, includeVoided, source, folder, changeKind, q, page, pageSize]);

  // 搜索防抖 300ms：输入停顿后才打后端，回车立即搜
  useEffect(() => {
    const h = window.setTimeout(() => {
      const next = searchInput.trim();
      if (next !== qRef.current) {
        qRef.current = next;
        setQ(next);
        setPage(1);
      }
    }, 300);
    return () => window.clearTimeout(h);
  }, [searchInput]);

  const applyFilter = useCallback((setter: (v: string) => void, v: string) => {
    setter(v);
    setPage(1);
  }, []);

  const sourceLabel = useCallback(
    (sourceKey?: string | null) => {
      const key = `grading.ledger.source.${sourceKey || ""}`;
      const label = t(key);
      // t 找不到时原样返回 key，此时退回原始 source
      return label === key ? sourceKey || "—" : label;
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

  const sortedSourceKeys = useMemo(() => {
    const keys = Object.keys(sourceCounts);
    return keys.sort((a, b) => {
      const ia = SOURCE_ORDER.indexOf(a);
      const ib = SOURCE_ORDER.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b);
    });
  }, [sourceCounts]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const countText = useMemo(
    () => t("grading.ledger.totalCount", { count: total }),
    [t, total],
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
              onValueChange={(v) => {
                setDays(Number(v) || 30);
                setPage(1);
              }}
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
              onCheckedChange={(v) => {
                setIncludeVoided(v);
                setPage(1);
              }}
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
        <CardContent className="space-y-3">
          {/* 搜索框 + 改动类型/考试筛选 */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <Input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder={t("grading.ledger.searchPlaceholder")}
                className="h-8 w-[260px] pl-8"
              />
            </div>
            <Select
              value={changeKind || "all"}
              onValueChange={(v) => applyFilter(setChangeKind, v === "all" ? "" : v)}
            >
              <SelectTrigger className="w-[130px] h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("grading.ledger.changeKindAll")}</SelectItem>
                {CHANGE_KIND_OPTIONS.map((k) => (
                  <SelectItem key={k} value={k}>
                    {t(`grading.ledger.changeKind.${k}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={folder || "all"}
              onValueChange={(v) => applyFilter(setFolder, v === "all" ? "" : v)}
            >
              <SelectTrigger className="w-[180px] h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("grading.ledger.folderAll")}</SelectItem>
                {folderCounts.map((f) => (
                  <SelectItem key={f.folder || ""} value={f.folder || ""}>
                    {f.folder || "—"}（{f.count ?? 0}）
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* 来源分类 chip（带计数，点选过滤） */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <Badge
              variant={source === "" ? "default" : "outline"}
              className="cursor-pointer font-normal"
              onClick={() => applyFilter(setSource, "")}
            >
              {t("grading.ledger.chipAll")}
            </Badge>
            {sortedSourceKeys.map((k) => (
              <Badge
                key={k}
                variant={source === k ? "default" : "outline"}
                className="cursor-pointer font-normal"
                onClick={() => applyFilter(setSource, source === k ? "" : k)}
              >
                {sourceLabel(k)}（{sourceCounts[k] ?? 0}）
              </Badge>
            ))}
          </div>

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
                {q || source || changeKind || folder
                  ? t("grading.ledger.noMatch")
                  : t("grading.ledger.empty")}
              </p>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm">
                {q || source || changeKind || folder
                  ? t("grading.ledger.noMatchHint")
                  : t("grading.ledger.emptyHint")}
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

          {/* 分页脚：成千上万条靠这个翻，不再一次拉全量 */}
          {total > 0 ? (
            <div className="flex items-center justify-between gap-2 flex-wrap pt-1">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>{countText}</span>
                <Select
                  value={String(pageSize)}
                  onValueChange={(v) => {
                    setPageSize(Number(v) || 50);
                    setPage(1);
                  }}
                >
                  <SelectTrigger className="h-7 w-[100px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PAGE_SIZE_OPTIONS.map((n) => (
                      <SelectItem key={n} value={String(n)}>
                        {t("grading.ledger.pageSize", { size: n })}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7"
                  disabled={loading || page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  {t("grading.ledger.prevPage")}
                </Button>
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  {t("grading.ledger.pageInfo", { page, pages: totalPages })}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7"
                  disabled={loading || page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  {t("grading.ledger.nextPage")}
                  <ChevronRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

export default CorrectionLedgerPage;
