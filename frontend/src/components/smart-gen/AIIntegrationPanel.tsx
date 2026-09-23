import { useRef, useEffect, useCallback, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Circle,
  Sparkles,
  RefreshCw,
  Square,
  Loader2,
  Download,
  Eye,
} from "lucide-react";
import { toast } from "sonner";
import DOMPurify from "dompurify";
import { PdfPreviewDialog } from "@/components/shared/PdfPreviewDialog";
import { INTEGRATION_STEPS, COURSEWARE_PREVIEW } from "./smartGenData";
import { useLocale } from "@/contexts/LocaleContext";
import { generateCoursewarePptx } from "@/services/api";

interface Props {
  isGenerating: boolean;
  streamedContent: string;
  title: string;
  subject: string;
  genType: string;
  progress: number;
  onCancel: () => void;
  onRegenerate: () => void;
}

export function AIIntegrationPanel({
  isGenerating,
  streamedContent,
  title,
  subject,
  genType,
  progress,
  onCancel,
  onRegenerate,
}: Props) {
  const { t } = useLocale();
  const contentRef = useRef<HTMLDivElement>(null);
  const [exporting, setExporting] = useState(false);
  const [pptxLoading, setPptxLoading] = useState(false);
  const [previewBlobUrl, setPreviewBlobUrl] = useState("");
  const [previewFilename, setPreviewFilename] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);

  // 生成中自动跟随到底部（内容不再用内部滚动框，改为整段展开）
  useEffect(() => {
    if (contentRef.current && isGenerating) {
      contentRef.current.scrollIntoView({ block: "end" });
    }
  }, [streamedContent, isGenerating]);

  const hasContent = streamedContent.length > 0;

  /** 生成 PDF（导出与预览共用，避免重复生成耗时）。
   *  按块级元素边界断页：先整段栅格化，再沿 h1/h2/h3/p/li 的底边裁切，
   *  避免固定高度切图把一行文字拦腰截断到上下两页。 */
  const buildLessonPdf = useCallback(async () => {
    const el = contentRef.current;
    if (!el) return null;
    const html2canvas = (await import("html2canvas")).default;
    const { jsPDF } = await import("jspdf");

    const scale = 2;
    const canvas = await html2canvas(el, {
      scale,
      useCORS: true,
      backgroundColor: "#ffffff",
    });

    const pdf = new jsPDF("p", "mm", "a4");
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 10;
    const contentWidth = pageWidth - margin * 2; // 190mm
    const contentHeight = pageHeight - margin * 2; // 277mm

    const elWidthCss = el.scrollWidth || el.clientWidth;
    const totalCss = canvas.height / scale;
    // 一页内容对应的 CSS 像素高度（PDF 中 190mm 宽等比映射到内容原宽）
    const pageContentCss = (contentHeight / contentWidth) * elWidthCss;

    // 收集块级元素底边（相对内容顶），用于在整块末尾断页
    const elTop = el.getBoundingClientRect().top;
    const boundaries = Array.from(el.querySelectorAll("h1, h2, h3, h4, p, li"))
      .map((node) => node.getBoundingClientRect().bottom - elTop)
      .filter((y) => y > 0 && y < totalCss)
      .sort((a, b) => a - b);

    // 贪心断页：每页尽量在块边界处结束
    const pages: Array<[number, number]> = [];
    let cursor = 0;
    while (cursor < totalCss - 0.5) {
      const limit = cursor + pageContentCss;
      let end = limit;
      for (const y of boundaries) {
        if (y > cursor + 0.5 && y <= limit) end = y;
      }
      if (end <= cursor + 0.5) end = limit; // 首块超高，只能按满页截断
      end = Math.min(end, totalCss);
      pages.push([cursor, end]);
      cursor = end;
    }

    // 逐页裁切 canvas 并写入 PDF
    pages.forEach(([top, bottom], idx) => {
      if (idx > 0) pdf.addPage();
      const sliceTopPx = Math.max(0, Math.floor(top * scale));
      const sliceBottomPx = Math.min(canvas.height, Math.ceil(bottom * scale));
      const sliceHpx = Math.max(1, sliceBottomPx - sliceTopPx);

      const slice = document.createElement("canvas");
      slice.width = canvas.width;
      slice.height = sliceHpx;
      const ctx = slice.getContext("2d");
      if (ctx) {
        ctx.drawImage(
          canvas,
          0,
          sliceTopPx,
          canvas.width,
          sliceHpx,
          0,
          0,
          canvas.width,
          sliceHpx,
        );
      }
      const sliceHmm = ((bottom - top) / elWidthCss) * contentWidth;
      pdf.addImage(
        slice.toDataURL("image/png"),
        "PNG",
        margin,
        margin,
        contentWidth,
        sliceHmm,
      );
    });

    const date = new Date().toISOString().slice(0, 10);
    const filename = `${t("smartGen.aiIntegration.pdfFileBase")}_${date}.pdf`;
    return { pdf, blob: pdf.output("blob"), filename };
  }, [t]);

  const handleExportPDF = useCallback(async () => {
    if (!contentRef.current) return;
    setExporting(true);
    try {
      const result = await buildLessonPdf();
      if (!result) return;
      result.pdf.save(result.filename);
      toast.success(t("smartGen.aiIntegration.pdfExportSuccess"));
    } catch (e) {
      console.error("PDF export error:", e);
      toast.error(t("smartGen.aiIntegration.pdfExportFailed"));
    } finally {
      setExporting(false);
    }
  }, [buildLessonPdf, t]);

  const handleDownloadPptx = useCallback(async () => {
    if (!hasContent) return;
    setPptxLoading(true);
    try {
      const blob = await generateCoursewarePptx({
        title: title || t("smartGen.aiIntegration.unnamed"),
        markdown: streamedContent,
        subject,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(title || t("smartGen.aiIntegration.unnamed")).replace(/[\\/:*?"<>|]/g, "_")}.pptx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(t("smartGen.aiIntegration.pptxSuccess"));
    } catch (e: any) {
      toast.error(e?.message || t("smartGen.aiIntegration.pptxFailed"));
    } finally {
      setPptxLoading(false);
    }
  }, [hasContent, streamedContent, subject, title, t]);

  const handlePreviewPdf = useCallback(async () => {
    if (!contentRef.current) return;
    setExporting(true);
    try {
      const result = await buildLessonPdf();
      if (!result) return;
      const url = URL.createObjectURL(result.blob);
      setPreviewBlobUrl(url);
      setPreviewFilename(result.filename);
      setPreviewOpen(true);
    } catch (e) {
      console.error("PDF preview error:", e);
      toast.error(t("smartGen.aiIntegration.pdfExportFailed"));
    } finally {
      setExporting(false);
    }
  }, [buildLessonPdf, t]);

  const handlePreviewClose = useCallback(() => {
    setPreviewOpen(false);
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl("");
      setPreviewFilename("");
    }
  }, [previewBlobUrl]);

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-1.5">
          <Sparkles className="w-4 h-4 text-primary" />
          {t("smartGen.aiIntegration.title")} ·{" "}
          {isGenerating
            ? t("smartGen.aiIntegration.generating")
            : hasContent
              ? t("smartGen.aiIntegration.complete")
              : t("smartGen.aiIntegration.generateFullPlan")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Progress */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">
              {isGenerating
                ? t("smartGen.aiIntegration.progressGenerating")
                : hasContent
                  ? t("smartGen.aiIntegration.progressComplete")
                  : t("smartGen.aiIntegration.progressWaiting")}
            </span>
            <span className="font-medium text-foreground">{progress}%</span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>

        {/* Cancel button during generation */}
        {isGenerating && (
          <Button
            variant="outline"
            size="sm"
            className="w-full text-xs h-7 gap-1"
            onClick={onCancel}
          >
            <Square className="w-3 h-3" />
            {t("smartGen.aiIntegration.stopGenerating")}
          </Button>
        )}

        {/* Streamed AI content */}
        {hasContent ? (
          <div
            ref={contentRef}
            className="p-4 rounded-lg bg-muted/40 border border-border"
          >
            <div className="prose prose-sm max-w-none text-foreground text-xs leading-relaxed">
              {streamedContent.split("\n").map((line, i) => {
                if (!line.trim()) return <br key={i} />;
                // Heading rendering
                if (line.startsWith("## ")) {
                  return (
                    <h2
                      key={i}
                      className="text-sm font-bold text-foreground mt-3 mb-1.5 flex items-center gap-1"
                    >
                      {line.slice(3)}
                    </h2>
                  );
                }
                if (line.startsWith("### ")) {
                  return (
                    <h3
                      key={i}
                      className="text-xs font-bold text-foreground mt-2 mb-1"
                    >
                      {line.slice(4)}
                    </h3>
                  );
                }
                if (line.startsWith("# ")) {
                  return (
                    <h1
                      key={i}
                      className="text-base font-bold text-foreground mt-3 mb-2"
                    >
                      {line.slice(2)}
                    </h1>
                  );
                }
                // Bold text
                const boldRendered = DOMPurify.sanitize(
                  line.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>"),
                  {
                    ALLOWED_TAGS: ["strong", "b", "em", "i", "code", "br"],
                    ALLOWED_ATTR: [],
                  },
                );
                // List items
                if (
                  line.trim().startsWith("- ") ||
                  line.trim().startsWith("* ")
                ) {
                  return (
                    <li
                      key={i}
                      className="text-xs text-muted-foreground ml-4 list-disc"
                      dangerouslySetInnerHTML={{
                        __html: boldRendered.replace(/^[\s]*[-*]\s/, ""),
                      }}
                    />
                  );
                }
                if (/^\d+\.\s/.test(line.trim())) {
                  return (
                    <li
                      key={i}
                      className="text-xs text-muted-foreground ml-4 list-decimal"
                      dangerouslySetInnerHTML={{
                        __html: boldRendered.replace(/^[\s]*\d+\.\s/, ""),
                      }}
                    />
                  );
                }
                return (
                  <p
                    key={i}
                    className="text-xs text-muted-foreground mb-1"
                    dangerouslySetInnerHTML={{ __html: boldRendered }}
                  />
                );
              })}
              {isGenerating && (
                <span className="inline-flex items-center gap-1 text-primary text-[11px]">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  {t("smartGen.aiIntegration.streaming")}
                </span>
              )}
            </div>
          </div>
        ) : !isGenerating ? (
          <>
            {/* Static fallback when no content yet */}
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-foreground">
                {t("smartGen.aiIntegration.aiWill")}
              </p>
              {INTEGRATION_STEPS.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]">
                  <Circle className="w-3.5 h-3.5 text-muted-foreground/40 shrink-0" />
                  <span className="text-muted-foreground">
                    {t(`smartGen.aiIntegration.step.${i}`)}
                  </span>
                </div>
              ))}
            </div>

            <div className="p-3 rounded-lg bg-muted/40 border border-border space-y-2">
              <p className="text-xs font-medium text-foreground">
                {t("smartGen.aiIntegration.coursewareStructure")}
              </p>
              {COURSEWARE_PREVIEW.map((sec, i) => (
                <div
                  key={i}
                  className="pl-2 border-l-2 border-primary/30 space-y-0.5"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-semibold text-foreground">
                      {t(`smartGen.aiIntegration.section.${i}.pages`)}
                    </span>
                    <Badge variant="secondary" className="text-[9px]">
                      {t(`smartGen.aiIntegration.section.${i}.source`)}
                    </Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    {t(`smartGen.aiIntegration.section.${i}.content`)}
                  </p>
                  {sec.interaction && (
                    <p className="text-[10px] text-primary/80">
                      ⏸️ {t(`smartGen.aiIntegration.section.${i}.interaction`)}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </>
        ) : null}

        {/* Actions */}
        <div className="flex flex-wrap gap-2 pt-1">
          {genType === "courseware" && (
            <Button
              size="sm"
              className="text-xs h-7 gap-1"
              disabled={isGenerating || !hasContent || pptxLoading}
              onClick={handleDownloadPptx}
            >
              {pptxLoading ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Download className="w-3 h-3" />
              )}
              {pptxLoading
                ? t("smartGen.aiIntegration.generatingPptx")
                : t("smartGen.aiIntegration.downloadPptx")}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            disabled={isGenerating || !hasContent || exporting}
            onClick={handlePreviewPdf}
          >
            <Eye className="w-3 h-3" />
            {t("smartGen.aiIntegration.preview")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            disabled={isGenerating || !hasContent || exporting}
            onClick={handleExportPDF}
          >
            {exporting ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Download className="w-3 h-3" />
            )}
            {exporting
              ? t("smartGen.aiIntegration.exporting")
              : t("smartGen.aiIntegration.exportPdf")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-xs h-7 gap-1"
            onClick={onRegenerate}
            disabled={isGenerating}
          >
            <RefreshCw className="w-3 h-3" />
            {t("smartGen.aiIntegration.regenerate")}
          </Button>
        </div>

        <PdfPreviewDialog
          open={previewOpen}
          onClose={handlePreviewClose}
          blobUrl={previewBlobUrl}
          filename={previewFilename}
        />
      </CardContent>
    </Card>
  );
}
