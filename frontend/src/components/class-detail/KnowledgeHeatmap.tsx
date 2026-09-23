import { Fragment, useState } from "react";
import { useLocale } from "@/contexts/LocaleContext";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface HeatmapData {
  students: string[];
  knowledgeNodes: string[];
  scores: (number | null)[][]; // rows = students, cols = knowledge nodes
}

interface KnowledgeHeatmapProps {
  data: HeatmapData;
  onCellClick?: (
    student: string,
    knowledgeNode: string,
    score: number | null,
  ) => void;
}

const mockStudents = [
  "张三",
  "李四",
  "王五",
  "赵六",
  "孙七",
  "周八",
  "吴九",
  "郑十",
];
const mockNodes = ["字词积累", "语法病句", "阅读理解", "作文", "文言文"];

function seedRandom(seed: number) {
  return () => {
    seed = (seed * 16807 + 0) % 2147483647;
    return (seed - 1) / 2147483646;
  };
}

const rand = seedRandom(42);
const mockScores: (number | null)[][] = mockStudents.map(() =>
  mockNodes.map(() => {
    const v = rand();
    return v < 0.1 ? null : Math.round(v * 100);
  }),
);

export const heatmapMockData: HeatmapData = {
  students: mockStudents,
  knowledgeNodes: mockNodes,
  scores: mockScores,
};

function getCellColor(score: number | null): string {
  if (score === null) return "bg-muted";
  if (score > 80) return "bg-success";
  if (score >= 60) return "bg-warning";
  return "bg-destructive";
}

function getCellTextColor(score: number | null): string {
  if (score === null) return "text-muted-foreground";
  return "text-white";
}

export function KnowledgeHeatmap({ data, onCellClick }: KnowledgeHeatmapProps) {
  const { t, locale } = useLocale();

  const [selected, setSelected] = useState<{ row: number; col: number } | null>(
    null,
  );

  const handleClick = (row: number, col: number) => {
    setSelected({ row, col });
    onCellClick?.(
      data.students[row],
      data.knowledgeNodes[col],
      data.scores[row][col],
    );
  };

  return (
    <div className="bg-card rounded-xl border border-border shadow-sm p-5">
      <h3 className="text-lg font-semibold text-foreground mb-4">
        {t("classDetail.knowledgeHeatmapTitle")}
      </h3>

      {/* Legend */}
      <div className="flex items-center gap-4 mb-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-success inline-block" /> &gt;80%
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-warning inline-block" /> 60-80%
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-destructive inline-block" />{" "}
          &lt;60%
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-muted inline-block" />{" "}
          {t("classDetail.无数据")}
        </span>
      </div>

      <TooltipProvider delayDuration={100}>
        <div className="overflow-auto max-h-[420px] relative">
          <div
            className="grid gap-1.5"
            style={{
              gridTemplateColumns: `100px repeat(${data.knowledgeNodes.length}, 4rem)`,
            }}
          >
            {/* Header row */}
            <div className="sticky top-0 left-0 z-30 bg-card" />
            {data.knowledgeNodes.map((node) => (
              <div
                key={node}
                className="sticky top-0 z-20 bg-card h-10 flex items-end justify-center text-xs font-medium text-muted-foreground pb-1 text-center leading-tight"
              >
                {node}
              </div>
            ))}

            {/* Data rows */}
            {data.students.map((student, rowIdx) => (
              <Fragment key={student}>
                {/* Student name - sticky left */}
                <div
                  key={`name-${rowIdx}`}
                  className="sticky left-0 z-10 bg-card h-12 flex items-center text-sm font-medium text-foreground truncate pr-2"
                >
                  {student}
                </div>

                {/* Score cells */}
                {data.knowledgeNodes.map((node, colIdx) => {
                  const score = data.scores[rowIdx][colIdx];
                  const isSelected =
                    selected?.row === rowIdx && selected?.col === colIdx;

                  return (
                    <Tooltip key={`${rowIdx}-${colIdx}`}>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => handleClick(rowIdx, colIdx)}
                          className={cn(
                            "w-16 h-12 rounded-md flex items-center justify-center text-sm font-semibold transition-all duration-150",
                            getCellColor(score),
                            getCellTextColor(score),
                            "hover:scale-105 hover:shadow-md",
                            isSelected && "ring-2 ring-primary ring-offset-1",
                          )}
                        >
                          {score !== null ? `${score}%` : "—"}
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs">
                        <p className="font-medium">
                          {student} - {node}
                        </p>
                        <p>
                          {score !== null
                            ? t("classDetail.scoreRateLabel", { rate: score })
                            : t("classDetail.暂无数据")}
                        </p>
                      </TooltipContent>
                    </Tooltip>
                  );
                })}
              </Fragment>
            ))}
          </div>
        </div>
      </TooltipProvider>
    </div>
  );
}
