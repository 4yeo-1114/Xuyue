import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocale } from "@/contexts/LocaleContext";
import { toast } from "sonner";
import {
  type LucideIcon,
  Loader2,
  BookOpen,
  FileText,
  ClipboardList,
  Trophy,
  Quote,
  Landmark,
  Medal,
  Wallet,
  Images,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  getDossier,
  downloadGrowthAlbumPdf,
  saveBlob,
  resolveMemoryUrl,
  type DossierResponse,
  type DossierGrowthRecord,
  type DossierMemoryItem,
  type DossierBadgeItem,
  type DossierCreditTransaction,
  type DossierAssessmentResult,
  type CommentSection,
  type ReportResponse,
} from "@/services/wuyuApi";
import { DimensionBars } from "@/components/assessment/shared";
import {
  DIMENSIONS,
  DIMENSION_LABEL_KEY,
  DIMENSION_COLORS,
  formatDateTime,
} from "./portfolioShared";
import { cn } from "@/lib/utils";

interface DossierPanelProps {
  studentId: string;
  studentName?: string;
}

/**
 * 综评档案一体化查看（G3 前端）— 学生完整档案聚合只读面板。
 * 单次 GET /portfolio/students/{id}/dossier 拉取报告 + 成长记录 + 印记 + 奖章 + 学分 + 测评 + 成档状态。
 * 一屏优先展示报告核心区，明细区用二级 Tabs 收纳避免页面过长。
 */
export function DossierPanel({ studentId, studentName }: DossierPanelProps) {
  const { t } = useLocale();
  const [albumDownloading, setAlbumDownloading] = useState(false);

  const {
    data: dossier,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["wuyu-dossier", studentId],
    queryFn: () => getDossier(studentId),
    enabled: !!studentId,
  });

  const handleDownloadAlbum = async () => {
    if (!dossier) return;
    setAlbumDownloading(true);
    try {
      const { blob, filename } = await downloadGrowthAlbumPdf(
        studentId,
        dossier.term || undefined,
      );
      saveBlob(blob, filename);
      toast.success(t("wuyu.report.albumPdfSuccess"));
    } catch (err) {
      toast.error(t("wuyu.report.albumPdfFailed"), {
        description: err instanceof Error ? err.message : String(err ?? ""),
      });
    } finally {
      setAlbumDownloading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin mb-2" />
        <p className="text-sm">{t("wuyu.loading")}</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-16 border border-dashed rounded-lg text-muted-foreground">
        <p className="text-sm mb-2">{t("wuyu.loadFailed")}</p>
        <Button size="sm" variant="outline" onClick={() => refetch()}>
          {t("wuyu.retry")}
        </Button>
      </div>
    );
  }

  if (!dossier) {
    return (
      <div className="flex flex-col items-center justify-center py-16 border border-dashed rounded-lg text-muted-foreground">
        <FileText className="w-8 h-8 opacity-30 mb-2" />
        <p className="text-sm">{t("wuyu.empty")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <DossierHeader
        dossier={dossier}
        studentName={studentName}
        albumDownloading={albumDownloading}
        onDownloadAlbum={handleDownloadAlbum}
      />
      {dossier.report ? (
        <ReportSection report={dossier.report} />
      ) : (
        <EmptyCard icon={FileText} text={t("wuyu.dossier.noReport")} />
      )}
      <DetailsSection dossier={dossier} />
    </div>
  );
}

/* ── 头部：身份 + 成档状态 + 下载成长册 ── */

function DossierHeader({
  dossier,
  studentName,
  albumDownloading,
  onDownloadAlbum,
}: {
  dossier: DossierResponse;
  studentName?: string;
  albumDownloading: boolean;
  onDownloadAlbum: () => void;
}) {
  const { t } = useLocale();
  const archive = dossier.archive_status;
  return (
    <Card>
      <CardHeader className="pb-3 flex-row items-start justify-between space-y-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">
              {t("wuyu.dossier.title")}
            </CardTitle>
          </div>
          <CardDescription>{t("wuyu.dossier.subtitle")}</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-base font-semibold text-foreground">
            {studentName || dossier.name}
          </span>
          {dossier.class_name ? (
            <Badge variant="secondary">{dossier.class_name}</Badge>
          ) : null}
          {dossier.grade ? (
            <Badge variant="outline">{dossier.grade}</Badge>
          ) : null}
          {dossier.term ? (
            <Badge variant="outline">{dossier.term}</Badge>
          ) : null}
          {archive?.status ? (
            <ArchiveStatusBadge status={archive.status} />
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={onDownloadAlbum}
            disabled={albumDownloading}
          >
            {albumDownloading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
            ) : (
              <BookOpen className="w-3.5 h-3.5 mr-1" />
            )}
            {albumDownloading
              ? t("wuyu.report.albumGenerating")
              : t("wuyu.dossier.downloadAlbum")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ArchiveStatusBadge({ status }: { status: string }) {
  const { t } = useLocale();
  const style: Record<string, string> = {
    selected: "bg-sky-100 text-sky-700 border-sky-200",
    publicizing: "bg-amber-100 text-amber-700 border-amber-200",
    archived: "bg-emerald-100 text-emerald-700 border-emerald-200",
  };
  return (
    <Badge
      variant="outline"
      className={cn("border-transparent", style[status])}
    >
      {t(`wuyu.dossier.status.${status}`, undefined, status)}
    </Badge>
  );
}

/* ── 报告区：概要 / 五维 / 里程碑 / 评语 / 学分银行 ── */

function ReportSection({ report }: { report: DossierResponse["report"] }) {
  const { t } = useLocale();
  if (!report) return null;
  const hasDataDim = (dim: string) => report.data_status?.[dim] === "has_data";

  return (
    <>
      <Card>
        <CardContent className="pt-5">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <Badge variant={report.from_snapshot ? "default" : "secondary"}>
              {report.from_snapshot
                ? t("wuyu.report.fromSnapshot")
                : t("wuyu.report.live")}
            </Badge>
            {report.version != null && (
              <Badge variant="outline">
                {t("wuyu.report.version")} v{report.version}
              </Badge>
            )}
            {report.term ? (
              <Badge variant="outline">{report.term}</Badge>
            ) : null}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MetricBox
              label={t("wuyu.report.totalGrowth")}
              value={String(report.total_growth_point)}
            />
            <MetricBox
              label={t("wuyu.report.growthCount")}
              value={String(report.growth_records_count)}
            />
            <MetricBox
              label={t("wuyu.report.sources")}
              value={String(Object.keys(report.source_stats ?? {}).length)}
            />
            <MetricBox
              label={t("wuyu.report.growthRecords")}
              value={
                report.date_from
                  ? `${report.date_from} ~ ${report.date_to}`
                  : "—"
              }
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">
            {t("wuyu.report.dimSection", { dim: t("wuyu.title") })}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-6 gap-3">
            {DIMENSIONS.map((dim) => {
              const meta = report.dimensions?.[dim];
              const color = DIMENSION_COLORS[dim];
              const has = hasDataDim(dim);
              return (
                <div
                  key={dim}
                  className={cn(
                    "rounded-lg border border-border/50 p-3",
                    !has && "opacity-70 bg-muted/20",
                  )}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-foreground">
                      {t(DIMENSION_LABEL_KEY[dim])}
                    </span>
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: color }}
                    />
                  </div>
                  {has ? (
                    <div className="text-sm space-y-1">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground text-xs">
                          {t("wuyu.report.autoPoints")}
                        </span>
                        <span className="text-foreground">
                          +{meta?.auto_points ?? 0}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground text-xs">
                          {t("wuyu.report.growthRecords")}
                        </span>
                        <span className="text-foreground">
                          {meta?.growth_records ?? 0}
                        </span>
                      </div>
                      <div className="flex justify-between border-t border-border/50 pt-1 mt-1">
                        <span className="text-xs font-medium">
                          {t("wuyu.overview.growthPoint")}
                        </span>
                        <span className="font-bold text-foreground">
                          {meta?.total ?? 0}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="py-2 text-xs text-muted-foreground">
                      {t("wuyu.overview.insufficient")}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Trophy className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-semibold">
              {t("wuyu.report.milestones")}
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {(report.milestones ?? []).length === 0 ? (
            <EmptyBox text={t("wuyu.report.noMilestones")} />
          ) : (
            <div className="space-y-2">
              {(report.milestones ?? []).map((m, i) => (
                <div
                  key={`${m.event_type}-${i}`}
                  className="flex items-center gap-3 rounded-lg border border-border/50 px-3 py-2 text-sm"
                >
                  <span className="text-xs text-muted-foreground shrink-0">
                    {formatDateTime(m.occurred_at)}
                  </span>
                  <span className="flex-1 text-foreground">{m.name}</span>
                  <Badge variant="secondary">+{m.points ?? 0}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <CommentCard comment={report.comment} />
      <CreditBankCard credit={report.credit} />
    </>
  );
}

function CommentCard({ comment }: { comment?: CommentSection | null }) {
  const { t } = useLocale();
  const text =
    comment?.confirmed_content || comment?.content || comment?.ai_content;
  const status = comment?.status;
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Quote className="w-4 h-4 text-primary" />
          <CardTitle className="text-sm font-semibold">
            {t("wuyu.dossier.comment")}
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        {status ? (
          <Badge variant="outline" className="mb-2">
            {t(`wuyu.comment.status.${status}`, undefined, status)}
          </Badge>
        ) : null}
        {text ? (
          <p className="text-sm text-foreground whitespace-pre-wrap">{text}</p>
        ) : (
          <EmptyBox text={t("wuyu.dossier.noComment")} />
        )}
      </CardContent>
    </Card>
  );
}

function CreditBankCard({ credit }: { credit?: ReportResponse["credit"] }) {
  const { t } = useLocale();
  const c = credit;
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Landmark className="w-4 h-4 text-primary" />
          <CardTitle className="text-sm font-semibold">
            {t("wuyu.report.creditBank")}
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        {c?.balance != null ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <MetricBox
              label={t("wuyu.report.creditBalance")}
              value={(c.balance ?? 0).toLocaleString()}
            />
            <MetricBox
              label={t("wuyu.report.creditTotalEarned")}
              value={(c.total_earned ?? 0).toLocaleString()}
            />
            <MetricBox
              label={t("wuyu.report.creditTotalSpent")}
              value={(c.total_spent ?? 0).toLocaleString()}
            />
            <MetricBox
              label={t("wuyu.report.creditTermEarned")}
              value={c.term_earned.toLocaleString()}
            />
            <MetricBox
              label={t("wuyu.report.creditTermSpent")}
              value={c.term_spent.toLocaleString()}
            />
            <MetricBox
              label={t("wuyu.report.creditTxnCount")}
              value={c.txn_count.toLocaleString()}
            />
          </div>
        ) : (
          <EmptyBox text={t("wuyu.report.creditEmpty")} />
        )}
      </CardContent>
    </Card>
  );
}

/* ── 明细区：二级 Tabs 收纳 ── */

function DetailsSection({ dossier }: { dossier: DossierResponse }) {
  const { t } = useLocale();
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <ClipboardList className="w-4 h-4 text-primary" />
          <CardTitle className="text-sm font-semibold">
            {t("wuyu.dossier.details")}
          </CardTitle>
        </div>
        <CardDescription>{t("wuyu.dossier.detailsHint")}</CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <Tabs defaultValue="growth" className="w-full">
          <TabsList className="flex-wrap h-auto">
            <TabsTrigger value="growth">{t("wuyu.dossier.growth")}</TabsTrigger>
            <TabsTrigger value="memories">
              {t("wuyu.dossier.memories")}
            </TabsTrigger>
            <TabsTrigger value="badges">{t("wuyu.dossier.badges")}</TabsTrigger>
            <TabsTrigger value="credits">
              {t("wuyu.dossier.credits")}
            </TabsTrigger>
            <TabsTrigger value="assessment">
              {t("wuyu.dossier.assessment")}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="growth" className="mt-2">
            <GrowthRecordsBrief items={dossier.growth_records ?? []} />
          </TabsContent>
          <TabsContent value="memories" className="mt-2">
            <MemoriesBrief items={dossier.memories ?? []} />
          </TabsContent>
          <TabsContent value="badges" className="mt-2">
            <BadgesBrief items={dossier.badges ?? []} />
          </TabsContent>
          <TabsContent value="credits" className="mt-2">
            <CreditsBrief items={dossier.credit_transactions ?? []} />
          </TabsContent>
          <TabsContent value="assessment" className="mt-2">
            <AssessmentBrief items={dossier.assessment_results ?? []} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function GrowthRecordsBrief({ items }: { items: DossierGrowthRecord[] }) {
  const { t } = useLocale();
  const rows = items.slice(0, 10);
  if (rows.length === 0) {
    return <EmptyBox icon={ClipboardList} text={t("wuyu.dossier.noGrowth")} />;
  }
  return (
    <div className="space-y-2">
      {rows.map((r, i) => {
        const color = r.dimension ? DIMENSION_COLORS[r.dimension] : "#94a3b8";
        return (
          <div
            key={r.id ?? i}
            className="flex items-center gap-3 rounded-lg border border-border/50 px-3 py-2.5"
          >
            <span
              className="w-1.5 h-8 rounded-full shrink-0"
              style={{ backgroundColor: color }}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                {r.dimension ? (
                  <span className="text-sm font-medium text-foreground">
                    {t(DIMENSION_LABEL_KEY[r.dimension])}
                  </span>
                ) : null}
                {r.indicator_name ? (
                  <Badge variant="outline" className="text-[10px]">
                    {r.indicator_name}
                  </Badge>
                ) : null}
                <span className="text-xs text-muted-foreground">
                  {formatDateTime(r.occurred_at)}
                </span>
              </div>
              {r.note ? (
                <p
                  className="text-xs text-muted-foreground mt-0.5 truncate"
                  title={r.note}
                >
                  {r.note}
                </p>
              ) : null}
            </div>
            {r.growth_points != null ? (
              <span
                className={cn(
                  "text-sm font-bold shrink-0",
                  r.growth_points >= 0
                    ? "text-emerald-600"
                    : "text-destructive",
                )}
              >
                {r.growth_points >= 0 ? "+" : ""}
                {r.growth_points}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function MemoriesBrief({ items }: { items: DossierMemoryItem[] }) {
  const { t } = useLocale();
  const rows = items.slice(0, 8);
  if (rows.length === 0) {
    return <EmptyBox icon={Images} text={t("wuyu.dossier.noMemories")} />;
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {rows.map((m, i) => {
        const src = resolveMemoryUrl(
          m.thumb_url || m.download_url || m.image_path || m.image || m.url,
        );
        return (
          <div
            key={m.id ?? i}
            className="rounded-lg border border-border/50 overflow-hidden bg-muted/20"
          >
            {src ? (
              <img
                src={src}
                alt={m.caption || ""}
                loading="lazy"
                className="w-full aspect-square object-cover"
              />
            ) : (
              <div className="w-full aspect-square flex items-center justify-center text-muted-foreground">
                <Images className="w-6 h-6 opacity-40" />
              </div>
            )}
            <div className="px-2 py-1.5">
              <p className="text-[11px] text-muted-foreground">
                {formatDateTime(m.created_at)}
              </p>
              {m.caption ? (
                <p
                  className="text-xs text-foreground truncate mt-0.5"
                  title={m.caption}
                >
                  {m.caption}
                </p>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BadgesBrief({ items }: { items: DossierBadgeItem[] }) {
  const { t } = useLocale();
  if (items.length === 0) {
    return <EmptyBox icon={Medal} text={t("wuyu.dossier.noBadges")} />;
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {items.map((b, i) => {
        const name = b.name || b.badge_name;
        const points = b.points ?? b.points_awarded;
        const when = b.awarded_at || b.award_date;
        return (
          <div
            key={b.id ?? i}
            className="rounded-lg border border-border/50 p-3 flex flex-col items-center gap-2 text-center bg-muted/20"
          >
            <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center">
              <Medal className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              {name ? (
                <p className="text-xs font-medium text-foreground truncate">
                  {name}
                </p>
              ) : null}
              <p className="text-[11px] text-muted-foreground mt-0.5">
                {t("wuyu.dossier.awardedAt")}：{fmtDate(when)}
              </p>
            </div>
            {points != null ? (
              <Badge variant="secondary">
                {t("wuyu.dossier.points")} {points}
              </Badge>
            ) : null}
            {b.reason ? (
              <p
                className="text-[11px] text-muted-foreground truncate w-full"
                title={b.reason}
              >
                {b.reason}
              </p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function CreditsBrief({ items }: { items: DossierCreditTransaction[] }) {
  const { t } = useLocale();
  const rows = items.slice(0, 10);
  if (rows.length === 0) {
    return <EmptyBox icon={Wallet} text={t("wuyu.dossier.noCredits")} />;
  }
  return (
    <div className="space-y-1.5">
      {rows.map((tx, i) => (
        <div
          key={tx.id ?? i}
          className="flex items-center gap-3 rounded-lg border border-border/50 px-3 py-2"
        >
          <span
            className={cn(
              "w-1.5 h-7 rounded-full shrink-0",
              (tx.amount ?? 0) >= 0 ? "bg-emerald-500" : "bg-destructive",
            )}
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-foreground">
                {t(creditTypeKey(tx.transaction_type ?? ""))}
              </span>
              <span className="text-[11px] text-muted-foreground">
                {formatDateTime(tx.created_at)}
              </span>
            </div>
            {tx.description ? (
              <p
                className="text-[11px] text-muted-foreground truncate mt-0.5"
                title={tx.description}
              >
                {tx.description}
              </p>
            ) : null}
          </div>
          <div className="text-right shrink-0">
            <span
              className={cn(
                "text-sm font-bold tabular-nums",
                (tx.amount ?? 0) >= 0 ? "text-green-600" : "text-destructive",
              )}
            >
              {(tx.amount ?? 0) >= 0 ? "+" : ""}
              {tx.amount}
            </span>
            {tx.balance_after != null ? (
              <p className="text-[11px] text-muted-foreground">
                {t("wuyu.incentive.balanceAfter")}：{tx.balance_after}
              </p>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

function AssessmentBrief({ items }: { items: DossierAssessmentResult[] }) {
  const { t } = useLocale();
  if (items.length === 0) {
    return (
      <EmptyBox icon={ClipboardList} text={t("wuyu.dossier.noAssessment")} />
    );
  }
  return (
    <div className="space-y-3">
      {items.map((r, i) => {
        const percents = r.dimension_percents ?? {};
        const labels = r.labels ?? [];
        const hasBars = Object.keys(percents).length > 0;
        return (
          <div
            key={r.id ?? i}
            className="rounded-lg border border-border/50 p-4 space-y-3"
          >
            {r.definition_name ? (
              <p className="text-sm font-medium text-foreground">
                {r.definition_name}
              </p>
            ) : null}
            {r.created_at ? (
              <p className="text-xs text-muted-foreground">
                {formatDateTime(r.created_at)}
              </p>
            ) : null}
            {labels.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {labels.map((lb) => (
                  <span
                    key={lb}
                    className="inline-flex items-center rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground"
                  >
                    {lb}
                  </span>
                ))}
              </div>
            ) : null}
            {hasBars ? (
              <DimensionBars percents={percents} />
            ) : (
              <p className="text-xs text-muted-foreground">
                {t("wuyu.dossier.noAssessment")}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── 小工具 ── */

function MetricBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/50 px-3 py-2.5">
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      <p className="text-sm font-semibold text-foreground truncate">{value}</p>
    </div>
  );
}

function EmptyBox({
  icon: Icon = FileText,
  text,
}: {
  icon?: LucideIcon;
  text: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-6 border border-dashed rounded-lg text-muted-foreground">
      <Icon className="w-7 h-7 opacity-30 mb-2" />
      <p className="text-sm">{text}</p>
    </div>
  );
}

function EmptyCard({ icon: Icon, text }: { icon: LucideIcon; text: string }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center justify-center py-10 text-muted-foreground">
        <Icon className="w-8 h-8 opacity-30 mb-2" />
        <p className="text-sm">{text}</p>
      </CardContent>
    </Card>
  );
}

/** 学分流水类型 → 激励中心（studentOps）i18n key，缺省回退原值 */
function creditTypeKey(type: string): string {
  const map: Record<string, string> = {
    badge_award: "studentOps.credits.typeBadgeAward",
    manual_add: "studentOps.credits.typeManualAdd",
    redemption: "studentOps.credits.typeRedemption",
    manual_deduct: "studentOps.credits.typeManualDeduct",
    adjustment: "studentOps.credits.typeAdjustment",
    practice_approved: "studentOps.credits.typePracticeApproved",
    expire: "studentOps.credits.typeExpire",
  };
  return map[type] || type;
}

/** 日期格式化为 YYYY-MM-DD */
function fmtDate(v?: string | null): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
