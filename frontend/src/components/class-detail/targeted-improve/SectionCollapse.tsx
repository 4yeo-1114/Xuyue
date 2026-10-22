import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

type Accent = "sky" | "cyan" | "violet" | "amber" | "emerald" | "indigo";

/**
 * 每个步骤一套主题色：收起=浅色描边节点，展开=实心点亮节点。
 * 与页面左侧时间轴脊线（left 21px）配套，节点盖在脊线上。
 */
const ACCENTS: Record<
  Accent,
  {
    nodeOff: string;
    nodeOn: string;
    iconOff: string;
    iconOn: string;
    headOpen: string;
  }
> = {
  sky: {
    nodeOff: "border-sky-200 bg-sky-50 text-sky-600",
    nodeOn: "border-sky-500 bg-sky-500 text-white shadow-lg shadow-sky-200/70",
    iconOff: "bg-sky-100 text-sky-600",
    iconOn: "bg-sky-500 text-white",
    headOpen: "border-sky-300/80 bg-gradient-to-r from-sky-50 via-card to-card",
  },
  cyan: {
    nodeOff: "border-cyan-200 bg-cyan-50 text-cyan-600",
    nodeOn: "border-cyan-500 bg-cyan-500 text-white shadow-lg shadow-cyan-200/70",
    iconOff: "bg-cyan-100 text-cyan-600",
    iconOn: "bg-cyan-500 text-white",
    headOpen: "border-cyan-300/80 bg-gradient-to-r from-cyan-50 via-card to-card",
  },
  violet: {
    nodeOff: "border-violet-200 bg-violet-50 text-violet-600",
    nodeOn: "border-violet-500 bg-violet-500 text-white shadow-lg shadow-violet-200/70",
    iconOff: "bg-violet-100 text-violet-600",
    iconOn: "bg-violet-500 text-white",
    headOpen:
      "border-violet-300/80 bg-gradient-to-r from-violet-50 via-card to-card",
  },
  amber: {
    nodeOff: "border-amber-200 bg-amber-50 text-amber-600",
    nodeOn: "border-amber-500 bg-amber-500 text-white shadow-lg shadow-amber-200/70",
    iconOff: "bg-amber-100 text-amber-600",
    iconOn: "bg-amber-500 text-white",
    headOpen: "border-amber-300/80 bg-gradient-to-r from-amber-50 via-card to-card",
  },
  emerald: {
    nodeOff: "border-emerald-200 bg-emerald-50 text-emerald-600",
    nodeOn:
      "border-emerald-500 bg-emerald-500 text-white shadow-lg shadow-emerald-200/70",
    iconOff: "bg-emerald-100 text-emerald-600",
    iconOn: "bg-emerald-500 text-white",
    headOpen:
      "border-emerald-300/80 bg-gradient-to-r from-emerald-50 via-card to-card",
  },
  indigo: {
    nodeOff: "border-indigo-200 bg-indigo-50 text-indigo-600",
    nodeOn: "border-indigo-500 bg-indigo-500 text-white shadow-lg shadow-indigo-200/70",
    iconOff: "bg-indigo-100 text-indigo-600",
    iconOn: "bg-indigo-500 text-white",
    headOpen: "border-indigo-300/80 bg-gradient-to-r from-indigo-50 via-card to-card",
  },
};

/** 脊线 x=21px（与页面级脊线对齐），节点 42px 盖在线上，卡片从 56px 起 */
const SPINE_X = 21;
const CARD_PAD = 56;

interface SectionCollapseProps {
  /** 步骤序号（1 起），显示在左侧时间轴节点上；不传则无节点 */
  step?: number;
  accent?: Accent;
  icon: ReactNode;
  title: string;
  /** 折叠状态下的一行摘要（选了谁 / 数量 / 进度），点开前一眼知道里面有什么 */
  summary?: ReactNode;
  /** 角标（如 AI 生成标识），挂在标题行右侧、箭头前 */
  rightExtra?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}

/**
 * 靶向提升页折叠分区（20261022 二次改版：编号时间轴结构）：
 * 左侧脊线 + 步骤节点，卡片收起点标题条展开；展开时节点点亮、卡片描边染色。
 */
export function SectionCollapse({
  step,
  accent = "sky",
  icon,
  title,
  summary,
  rightExtra,
  defaultOpen = false,
  className,
  children,
}: SectionCollapseProps) {
  const [open, setOpen] = useState(defaultOpen);
  const a = ACCENTS[accent];
  return (
    <div className={cn("relative pb-3", className)}>
      {typeof step === "number" ? (
        <div
          className={cn(
            "absolute top-2 z-10 flex h-[42px] w-[42px] -translate-x-1/2 items-center justify-center rounded-full border-2 bg-white transition-all duration-200",
            open ? a.nodeOn : a.nodeOff,
          )}
          style={{ left: SPINE_X }}
        >
          <span className="text-[11px] font-bold tracking-wider">
            {String(step).padStart(2, "0")}
          </span>
        </div>
      ) : null}

      <div style={{ paddingLeft: CARD_PAD }}>
        <Collapsible open={open} onOpenChange={setOpen}>
          <CollapsibleTrigger
            className={cn(
              "group flex w-full items-center gap-3 rounded-2xl border px-4 py-3.5 text-left shadow-sm transition-all duration-200 hover:shadow-md",
              open
                ? a.headOpen
                : "border-border/70 bg-card hover:border-primary/30 hover:bg-muted/30",
            )}
          >
            <div
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors duration-200",
                open ? a.iconOn : a.iconOff,
              )}
            >
              {icon}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-semibold text-foreground">
                {title}
              </p>
              {summary ? (
                <div className="mt-0.5 truncate text-xs text-muted-foreground">
                  {summary}
                </div>
              ) : null}
            </div>
            {rightExtra ? (
              <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
                {rightExtra}
              </div>
            ) : null}
            <div
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border bg-background/80 text-muted-foreground transition-colors duration-200 group-hover:border-primary/40 group-hover:text-primary",
                open && "border-primary/40 text-primary",
              )}
            >
              <ChevronDown
                className={cn(
                  "h-4 w-4 transition-transform duration-200",
                  open && "rotate-180",
                )}
              />
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent className="overflow-hidden duration-200 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-2">
            <div className="pt-3">{children}</div>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </div>
  );
}

/**
 * 阶段分隔（骑在时间轴脊线上）：菱形节点 + 两端渐隐短线 + 居中阶段标签。
 */
export function PhaseDivider({ label }: { label: string }) {
  return (
    <div className="relative flex items-center gap-3 py-3">
      <div
        className="absolute top-1/2 z-10 h-[11px] w-[11px] -translate-x-1/2 -translate-y-1/2 rotate-45 rounded-[2px] border-2 border-primary/50 bg-white"
        style={{ left: SPINE_X }}
      />
      <div
        className="flex flex-1 items-center gap-3"
        style={{ paddingLeft: CARD_PAD }}
      >
        <div className="h-[1.5px] flex-1 rounded-full bg-gradient-to-r from-transparent via-primary/25 to-primary/40" />
        <span className="whitespace-nowrap rounded-full border border-primary/20 bg-primary/[0.07] px-3.5 py-1 text-xs font-semibold tracking-wide text-primary">
          {label}
        </span>
        <div className="h-[1.5px] flex-1 rounded-full bg-gradient-to-r from-primary/40 via-primary/25 to-transparent" />
      </div>
    </div>
  );
}

export default SectionCollapse;
