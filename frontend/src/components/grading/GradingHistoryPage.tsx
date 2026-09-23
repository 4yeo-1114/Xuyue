import { useEffect, useMemo, useState } from "react";
import {
  History,
  FolderOpen,
  ArrowRight,
  RefreshCw,
  Loader2,
  AlertTriangle,
  PenTool,
  Search,
  Trash2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import {
  fetchRecentHistory,
  deleteFolders,
  type RecentHistoryFolder,
} from "@/services/gradingApi";
import { parseAiResultBlocks, type AiResultBlock } from "@/utils/aiResultBlocks";

/** 年级全量目录：筛选下拉始终展示全部年级，不随有无批改记录变化 */
const ALL_GRADES = [
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

/** 学科全量目录（小学/初中/高中）：筛选下拉始终展示全部学科 */
const ALL_SUBJECTS = [
  "语文",
  "数学",
  "英语",
  "科学",
  "物理",
  "化学",
  "生物",
  "道德与法治",
  "历史",
  "地理",
  "思想政治",
];

interface GradingHistoryPageProps {
  onOpenFolder?: (folderName: string) => void;
  onStartGrading?: () => void;
}

function formatTime(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 把 AI 批改结果文本压成「对 N · 错 N · 半对 N · 未答 N」的紧凑摘要 */
function paperSummary(result?: string): string {
  if (!result) return "";
  const blocks = parseAiResultBlocks(result);
  const counts = { correct: 0, wrong: 0, partial: 0, blank: 0 };
  const walk = (b: AiResultBlock) => {
    const subs = b.subItems?.length ? b.subItems : [b];
    for (const s of subs) {
      if (s.status === "correct") counts.correct++;
      else if (s.status === "wrong") counts.wrong++;
      else if (s.status === "partial") counts.partial++;
      else if (s.status === "blank") counts.blank++;
    }
  };
  for (const b of blocks) {
    // 跳过「总览/解析结果」块，避免把摘要头行也当一道题计数
    if (
      b.title === "总览" ||
      b.title === "解析结果" ||
      b.title === "Overview" ||
      b.title === "Parse Result"
    ) {
      continue;
    }
    walk(b);
  }
  const parts: string[] = [];
  if (counts.correct) parts.push(`对 ${counts.correct}`);
  if (counts.wrong) parts.push(`错 ${counts.wrong}`);
  if (counts.partial) parts.push(`半对 ${counts.partial}`);
  if (counts.blank) parts.push(`未答 ${counts.blank}`);
  if (parts.length) return parts.join(" · ");
  const firstLine = result.split("\n").find((l) => l.trim())?.trim() || "";
  return firstLine.length > 48 ? firstLine.slice(0, 48) + "…" : firstLine;
}

export function GradingHistoryPage({
  onOpenFolder,
  onStartGrading,
}: GradingHistoryPageProps) {
  const [folders, setFolders] = useState<RecentHistoryFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // R7 任务列表筛选：关键词 + 年级 + 学科 + 状态
  const [keyword, setKeyword] = useState("");
  const [gradeFilter, setGradeFilter] = useState("all");
  const [subjectFilter, setSubjectFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  // R7 删除：单文件夹删除，需登录密码确认
  const [deleteTarget, setDeleteTarget] = useState<RecentHistoryFolder | null>(
    null,
  );
  const [deletePassword, setDeletePassword] = useState("");
  const [deleting, setDeleting] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetchRecentHistory();
      if (res.ok) setFolders(res.folders || []);
      else setError("加载失败，请稍后重试");
    } catch (e: any) {
      setError(e?.message || "加载失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 筛选选项：始终展示全量年级/学科目录，并合并列表里出现的额外值（保证不丢任何值）
  const gradeOptions = useMemo(
    () => [
      ...ALL_GRADES,
      ...folders
        .map((f) => f.grade || "")
        .filter((g) => g && !ALL_GRADES.includes(g)),
    ],
    [folders],
  );
  const subjectOptions = useMemo(
    () => [
      ...ALL_SUBJECTS,
      ...folders
        .map((f) => f.subject || "")
        .filter((s) => s && !ALL_SUBJECTS.includes(s)),
    ],
    [folders],
  );

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return folders.filter((f) => {
      if (gradeFilter !== "all" && (f.grade || "") !== gradeFilter) return false;
      if (subjectFilter !== "all" && (f.subject || "") !== subjectFilter)
        return false;
      if (statusFilter !== "all" && (f.status || "completed") !== statusFilter)
        return false;
      if (kw) {
        const hay =
          `${f.display_name || ""} ${f.folder_name} ${f.class_name || ""}`.toLowerCase();
        if (!hay.includes(kw)) return false;
      }
      return true;
    });
  }, [folders, keyword, gradeFilter, subjectFilter, statusFilter]);

  const confirmDelete = async () => {
    if (!deleteTarget || !deletePassword.trim()) return;
    setDeleting(true);
    try {
      const res = await deleteFolders(
        [deleteTarget.folder_name],
        deletePassword.trim(),
      );
      if (res.ok) {
        toast.success(res.msg || "已删除");
        setDeleteTarget(null);
        setDeletePassword("");
        load();
      } else {
        toast.error(res.msg || "删除失败");
      }
    } catch (e: any) {
      toast.error(e?.message || "删除失败");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-foreground">批改历史</h1>
          <p className="text-sm text-muted-foreground mt-1">
            最近批改过的试卷与结果，点击文件夹可继续编辑
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          刷新
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin mr-2" />
          加载中…
        </div>
      ) : error ? (
        <Card className="border-border/50">
          <CardContent className="flex flex-col items-center py-16 text-center">
            <AlertTriangle className="w-8 h-8 text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button variant="outline" size="sm" className="mt-4" onClick={load}>
              重试
            </Button>
          </CardContent>
        </Card>
      ) : folders.length === 0 ? (
        <Card className="border-border/50 shadow-sm">
          <CardContent className="flex flex-col items-center py-16 text-center">
            <div className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center mb-4">
              <History className="w-8 h-8 text-muted-foreground" />
            </div>
            <p className="text-sm font-medium text-foreground">暂无批改记录</p>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm">
              完成一次批改后，这里会按时间列出最近批改的文件夹与每张卷的结果。
            </p>
            <Button className="mt-4" onClick={onStartGrading}>
              <PenTool className="w-4 h-4 mr-1" />
              去开始批改
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {/* R7 筛选栏：关键词 + 年级 + 学科 + 状态 */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[200px] max-w-xs">
              <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="搜索文件夹 / 班级"
                className="h-9 pl-8"
              />
            </div>
            <Select value={gradeFilter} onValueChange={setGradeFilter}>
              <SelectTrigger className="h-9 w-[120px]">
                <SelectValue placeholder="年级" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部年级</SelectItem>
                {gradeOptions.map((g) => (
                  <SelectItem key={g} value={g}>
                    {g}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={subjectFilter} onValueChange={setSubjectFilter}>
              <SelectTrigger className="h-9 w-[120px]">
                <SelectValue placeholder="学科" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部学科</SelectItem>
                {subjectOptions.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="h-9 w-[120px]">
                <SelectValue placeholder="状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="completed">已完成</SelectItem>
                <SelectItem value="failed">有失败</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {filtered.length === 0 ? (
            <Card className="border-border/50 shadow-sm">
              <CardContent className="flex flex-col items-center py-12 text-center">
                <p className="text-sm text-muted-foreground">
                  没有符合条件的批改记录
                </p>
              </CardContent>
            </Card>
          ) : (
            filtered.map((f) => (
              <Card
                key={f.folder_name}
                className="overflow-hidden border-border/50 shadow-sm cursor-pointer transition-colors hover:border-border"
                onClick={() => onOpenFolder?.(f.folder_name)}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <CardTitle className="text-base flex items-center gap-2">
                        <FolderOpen className="w-5 h-5 text-primary shrink-0" />
                        <span className="truncate">
                          {f.display_name || f.folder_name}
                        </span>
                      </CardTitle>
                      <div className="flex flex-wrap items-center gap-2 mt-1.5 text-xs text-muted-foreground">
                        {f.class_name && (
                          <span className="rounded bg-primary/10 text-primary px-1.5 py-0.5">
                            {f.class_name}
                          </span>
                        )}
                        {f.grade && (
                          <span className="rounded bg-muted px-1.5 py-0.5">
                            {f.grade}
                          </span>
                        )}
                        {f.subject && (
                          <span className="rounded bg-muted px-1.5 py-0.5">
                            {f.subject}
                          </span>
                        )}
                        {f.engines.map((e) => (
                          <span
                            key={e}
                            className="rounded bg-muted px-1.5 py-0.5"
                          >
                            {e}
                          </span>
                        ))}
                        <span>
                          {f.completed.length} 卷
                          {f.failed_count ? ` · 失败 ${f.failed_count}` : ""}
                        </span>
                        {f.updated_at && (
                          <span>更新于 {formatTime(f.updated_at)}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          onOpenFolder?.(f.folder_name);
                        }}
                      >
                        继续批改
                        <ArrowRight className="w-4 h-4 ml-1" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-9 w-9 px-0 text-destructive hover:text-destructive"
                        aria-label="删除任务"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteTarget(f);
                          setDeletePassword("");
                        }}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-1">
                  <div className="flex gap-3 overflow-x-auto pb-1">
                    {f.completed.slice(0, 24).map((p) => (
                      <div key={p.name} className="w-28 shrink-0">
                        <div className="aspect-[3/4] w-28 rounded-md border bg-muted overflow-hidden">
                          {p.image_annotated || p.image_original ? (
                            <img
                              src={p.image_annotated || p.image_original}
                              alt={p.name}
                              className="w-full h-full object-cover"
                              loading="lazy"
                            />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-muted-foreground">
                              <History className="w-5 h-5" />
                            </div>
                          )}
                        </div>
                        <p
                          className="mt-1 text-xs font-medium truncate"
                          title={p.name}
                        >
                          {p.name}
                        </p>
                        <p
                          className="text-[11px] text-muted-foreground truncate"
                          title={p.result}
                        >
                          {paperSummary(p.result)}
                        </p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))
          )}

          {/* R7 删除确认弹窗 */}
          <Dialog
            open={!!deleteTarget}
            onOpenChange={(open) => {
              if (!open) {
                setDeleteTarget(null);
                setDeletePassword("");
              }
            }}
          >
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>确认删除任务</DialogTitle>
                <DialogDescription>
                  将删除「
                  {deleteTarget?.display_name || deleteTarget?.folder_name}
                  」及其全部批改记录与图片，此操作不可恢复。请输入登录密码确认。
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-2 py-2">
                <Label htmlFor="history-delete-password">登录密码</Label>
                <Input
                  id="history-delete-password"
                  type="password"
                  placeholder="请输入登录密码"
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") confirmDelete();
                  }}
                />
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => {
                    setDeleteTarget(null);
                    setDeletePassword("");
                  }}
                  disabled={deleting}
                >
                  取消
                </Button>
                <Button
                  variant="destructive"
                  onClick={confirmDelete}
                  disabled={deleting || !deletePassword.trim()}
                >
                  {deleting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : null}
                  删除
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      )}
    </div>
  );
}
