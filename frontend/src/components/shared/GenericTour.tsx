import { useState, useEffect, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import { X, ChevronRight, Check, PartyPopper } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/contexts/LocaleContext";

export interface TourStep {
  targetSelector: string;
  title: string;
  description: string;
  buttonLabel: string;
  arrowPosition?: "top" | "bottom" | "left" | "right";
}

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

function getRect(selector: string): Rect | null {
  const el = document.querySelector(selector);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

interface GenericTourProps {
  storageKey: string;
  steps: TourStep[];
  completeTitle: string;
  completeDescription: string;
}

export function GenericTour({ storageKey, steps, completeTitle, completeDescription }: GenericTourProps) {
  const { t } = useLocale();
  const [active, setActive] = useState(false);
  const [step, setStep] = useState(0);
  const [showComplete, setShowComplete] = useState(false);
  const [targetRect, setTargetRect] = useState<Rect | null>(null);
  const rafRef = useRef<number>();

  useEffect(() => {
    try {
      if (!localStorage.getItem(storageKey)) {
        const t = setTimeout(() => setActive(true), 800);
        return () => clearTimeout(t);
      }
    } catch {}
  }, [storageKey]);

  const updateRect = useCallback(() => {
    if (!active || showComplete) return;
    const r = getRect(steps[step].targetSelector);
    setTargetRect((prev) => {
      if (!r) return prev;
      // 命中缓存：位置未变则返回原值，跳过重渲染
      if (prev && prev.top === r.top && prev.left === r.left && prev.width === r.width && prev.height === r.height) {
        return prev;
      }
      return r;
    });
    rafRef.current = requestAnimationFrame(updateRect);
  }, [active, step, showComplete, steps]);

  useEffect(() => {
    if (active && !showComplete) {
      rafRef.current = requestAnimationFrame(updateRect);
      const el = document.querySelector(steps[step].targetSelector);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [active, step, showComplete, updateRect, steps]);

  const handleNext = () => {
    if (step < steps.length - 1) setStep(step + 1);
    else setShowComplete(true);
  };

  const handleFinish = () => {
    try { localStorage.setItem(storageKey, "1"); } catch {}
    setActive(false);
    setShowComplete(false);
  };

  if (!active) return null;

  if (showComplete) {
    return (
      <div className="fixed inset-0 z-[9999] flex items-center justify-center" style={{ backgroundColor: "rgba(0,0,0,0.5)" }}>
        <div className="bg-card rounded-2xl shadow-2xl p-8 max-w-sm mx-4 text-center animate-scale-in">
          <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
            <PartyPopper className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-xl font-bold text-foreground mb-2">{completeTitle}</h2>
          <p className="text-muted-foreground text-sm mb-6">{completeDescription}</p>
          <Button onClick={handleFinish} className="w-full">{t("common.tour.start")}</Button>
        </div>
      </div>
    );
  }

  const currentStep = steps[step];
  const padding = 8;
  const highlightStyle = targetRect
    ? {
        top: targetRect.top - padding,
        left: targetRect.left - padding,
        width: targetRect.width + padding * 2,
        height: targetRect.height + padding * 2,
      }
    : { top: 0, left: 0, width: 0, height: 0 };

  const tooltipStyle: React.CSSProperties = {};
  if (targetRect) {
    const ap = currentStep.arrowPosition || "top";
    if (ap === "top" || ap === "bottom") {
      tooltipStyle.left = Math.max(16, targetRect.left + targetRect.width / 2 - 160);
      if (ap === "top") tooltipStyle.top = targetRect.top + targetRect.height + padding + 16;
      else tooltipStyle.bottom = window.innerHeight - targetRect.top + padding + 16;
    } else if (ap === "left") {
      tooltipStyle.left = targetRect.left + targetRect.width + padding + 16;
      tooltipStyle.top = Math.max(16, targetRect.top + targetRect.height / 2 - 60);
    } else {
      tooltipStyle.right = window.innerWidth - targetRect.left + padding + 16;
      tooltipStyle.top = Math.max(16, targetRect.top + targetRect.height / 2 - 60);
    }
  }
  if (tooltipStyle.left && typeof tooltipStyle.left === "number") {
    tooltipStyle.left = Math.min(tooltipStyle.left, window.innerWidth - 340);
  }
  if (tooltipStyle.top && typeof tooltipStyle.top === "number") {
    const maxTop = window.innerHeight - 220;
    if (tooltipStyle.top > maxTop) {
      // Flip tooltip above the target instead
      tooltipStyle.top = Math.max(16, (targetRect?.top ?? 0) - padding - 200);
    }
  }

  return (
    <div className="fixed inset-0 z-[9999]" style={{ pointerEvents: "auto" }}>
      <div
        className="absolute transition-all duration-300 ease-out rounded-xl"
        style={{
          ...highlightStyle,
          boxShadow: "0 0 0 9999px rgba(0,0,0,0.5)",
          border: "2px solid hsl(var(--primary))",
          pointerEvents: "none",
          animation: "pulse 2s cubic-bezier(0.4,0,0.6,1) infinite",
        }}
      />
      <div className="absolute inset-0" onClick={(e) => e.stopPropagation()} />
      <div
        className="absolute bg-card rounded-xl shadow-2xl p-5 w-[320px] animate-fade-in border border-border"
        style={{ ...tooltipStyle, pointerEvents: "auto" }}
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted-foreground font-medium">{step + 1} / {steps.length}</span>
          <button onClick={handleFinish} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <h3 className="text-base font-semibold text-foreground mb-1">{currentStep.title}</h3>
        <p className="text-sm text-muted-foreground mb-4">{currentStep.description}</p>
        <div className="flex items-center justify-between">
          <button onClick={handleFinish} className="text-xs text-muted-foreground hover:text-foreground transition-colors">
            {t("common.tour.skip")}
          </button>
          <Button size="sm" onClick={handleNext} className="gap-1.5">
            {currentStep.buttonLabel}
            {step < steps.length - 1 ? <ChevronRight className="w-3.5 h-3.5" /> : <Check className="w-3.5 h-3.5" />}
          </Button>
        </div>
        <div className="flex items-center justify-center gap-1.5 mt-3">
          {steps.map((_, i) => (
            <div
              key={i}
              className={cn(
                "w-1.5 h-1.5 rounded-full transition-all",
                i === step ? "w-4 bg-primary" : i < step ? "bg-primary/40" : "bg-muted-foreground/20"
              )}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
