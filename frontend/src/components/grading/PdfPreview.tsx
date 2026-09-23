import { useState, useEffect, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { fetchGradingFileArrayBuffer } from "@/services/gradingApi";
import { useLocale } from "@/contexts/LocaleContext";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import pdfjsWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
pdfjs.GlobalWorkerOptions.workerSrc = pdfjsWorker;

const MAX_FETCH_RETRIES = 3;
const RETRY_DELAY_MS = 400;
const MAX_PARSE_RETRIES = 2;
const CACHE_MAX = 10;
const pdfCache = new Map<string, ArrayBuffer>();

function normalizeUrl(u: string): string {
  if (!u) return "";
  try {
    if (u.startsWith("http")) return new URL(u).pathname;
    return u.startsWith("/") ? u : `/${u}`;
  } catch {
    return u;
  }
}

function getCached(normalized: string): ArrayBuffer | undefined {
  return pdfCache.get(normalized);
}
function setCached(normalized: string, buf: ArrayBuffer) {
  if (pdfCache.size >= CACHE_MAX) {
    const first = pdfCache.keys().next().value;
    if (first !== undefined) pdfCache.delete(first);
  }
  pdfCache.set(normalized, buf);
}

interface PdfPreviewProps {
  url: string;
  className?: string;
  width?: number;
}

export function PdfPreview({ url, className = "", width }: PdfPreviewProps) {
  const { t } = useLocale();
  const [data, setData] = useState<ArrayBuffer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [numPages, setNumPages] = useState<number>(1);
  const [parseRetryKey, setParseRetryKey] = useState(0);
  const requestIdRef = useRef(0);
  const loadedUrlRef = useRef<string>("");

  useEffect(() => {
    if (!url) return;
    const normalized = normalizeUrl(url);
    if (loadedUrlRef.current === normalized) return;
    setError(null);
    setData(null);
    const ac = new AbortController();
    const currentId = ++requestIdRef.current;
    let cancelled = false;

    const isStale = () => cancelled || currentId !== requestIdRef.current;

    const load = (fetchAttempt = 0): void => {
      const cached = getCached(normalized);
      if (cached) {
        if (isStale()) return;
        loadedUrlRef.current = normalized;
        setData(cached);
        return;
      }

      const signal = fetchAttempt > 0 ? undefined : ac.signal;
      fetchGradingFileArrayBuffer(url, signal)
        .then((buf) => {
          if (isStale()) return;
          setCached(normalized, buf);
          loadedUrlRef.current = normalized;
          setData(buf);
        })
        .catch((e) => {
          if (isStale()) return;
          if (e?.name === "AbortError") return;
          const nextAttempt = fetchAttempt + 1;
          if (nextAttempt < MAX_FETCH_RETRIES) {
            setTimeout(() => load(nextAttempt), RETRY_DELAY_MS);
            return;
          }
          setError(e?.message || t("grading.preview.loadFailedShort"));
        });
    };
    load();

    return () => {
      cancelled = true;
      ac.abort();
    };
  }, [url, parseRetryKey, t]);

  const handleParseError = (e?: unknown) => {
    const msg = typeof e === "object" && e !== null && "message" in e ? String((e as { message: unknown }).message) : t("grading.preview.pdfParseFailed");
    if (typeof console !== "undefined" && console.error) console.error("[PdfPreview] onLoadError", msg, e);
    const key = parseRetryKey + 1;
    if (key <= MAX_PARSE_RETRIES) {
      pdfCache.delete(normalizeUrl(url));
      loadedUrlRef.current = "";
      setData(null);
      setError(null);
      setParseRetryKey(key);
    } else {
      setError(msg || t("grading.preview.pdfParseFailed"));
    }
  };

  const handleRetryClick = () => {
    const normalized = normalizeUrl(url);
    setError(null);
    setData(null);
    loadedUrlRef.current = "";
    setParseRetryKey(0);
    requestIdRef.current += 1;
    const cached = getCached(normalized);
    if (cached) {
      loadedUrlRef.current = normalized;
      setData(cached);
      return;
    }
    fetchGradingFileArrayBuffer(url)
      .then((buf) => {
        setCached(normalized, buf);
        loadedUrlRef.current = normalized;
        setData(buf);
      })
      .catch((e) => setError(e?.message || t("grading.preview.loadFailedShort")));
  };

  if (error) {
    return (
      <div
        className={`flex flex-col items-center justify-center gap-1 bg-muted/50 cursor-pointer hover:bg-muted/70 ${className}`}
        onClick={handleRetryClick}
        title={t("grading.action.retryClick")}
        role="button"
      >
        <span className="text-muted-foreground text-xs">{error}</span>
        <span className="text-muted-foreground text-[10px]">{t("grading.action.retryClick")}</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className={`flex items-center justify-center bg-muted/50 ${className}`}>
        <span className="text-muted-foreground text-xs">{t("grading.preview.loading")}</span>
      </div>
    );
  }

  const dataCopy = data.byteLength > 0 ? data.slice(0) : data;

  return (
    <div className={`flex items-center justify-center overflow-hidden bg-muted/50 [&_.react-pdf__Page]:!max-w-full [&_.react-pdf__Page__canvas]:!max-w-full [&_.react-pdf__Page__canvas]:!h-auto ${className}`}>
      <Document
        file={{ data: dataCopy }}
        onLoadSuccess={({ numPages: n }) => setNumPages(n)}
        onLoadError={handleParseError}
        loading={
          <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
            {t("grading.preview.loading")}
          </div>
        }
      >
        <Page
          pageNumber={1}
          width={width ?? undefined}
          renderTextLayer={false}
          renderAnnotationLayer={true}
          className="!max-w-full !h-auto"
        />
      </Document>
    </div>
  );
}
