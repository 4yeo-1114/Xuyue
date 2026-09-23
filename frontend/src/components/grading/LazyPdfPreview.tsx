import { useState, useEffect, useRef } from "react";
import { PdfPreview } from "./PdfPreview";
import { GradingErrorBoundary } from "./GradingErrorBoundary";
import { useLocale } from "@/contexts/LocaleContext";

interface LazyPdfPreviewProps {
  url: string;
  className?: string;
  width?: number;
}

export function LazyPdfPreview({ url, className = "", width }: LazyPdfPreviewProps) {
  const { t } = useLocale();
  const [hasBeenInView, setHasBeenInView] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = rootRef.current;
    if (!el || hasBeenInView) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) setHasBeenInView(true);
      },
      { rootMargin: "100px", threshold: 0.01 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [hasBeenInView]);

  return (
    <div ref={rootRef} className={className || "w-full h-full"}>
      {!hasBeenInView ? (
        <div className="flex items-center justify-center bg-muted/50 w-full h-full min-h-[100px]">
          <span className="text-muted-foreground text-xs">PDF</span>
        </div>
      ) : (
        <GradingErrorBoundary
          key={`${url}-${retryKey}`}
          fallback={
            <div
              className="flex flex-col items-center justify-center gap-1 rounded border border-dashed bg-muted/30 p-3 text-center text-sm text-muted-foreground min-h-[100px] cursor-pointer hover:bg-muted/50"
              onClick={() => setRetryKey((k) => k + 1)}
              role="button"
              title={t("grading.action.retryClick")}
            >
              <span>{t("grading.preview.loadFailed")}</span>
              <span className="text-[10px]">{t("grading.action.retryClick")}</span>
            </div>
          }
        >
          <PdfPreview url={url} className="w-full h-full min-h-[100px]" width={width} />
        </GradingErrorBoundary>
      )}
    </div>
  );
}
