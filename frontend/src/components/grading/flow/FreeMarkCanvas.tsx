import { useCallback, useRef, useState } from "react";
import { gradingImageUrl, type FlowMark, type FlowReviewStatus } from "@/services/gradingApi";

const MARK_COLOR = "#FF0000";
const MARK_FONT_FAMILY = '"Microsoft YaHei", "Noto Sans CJK SC", sans-serif';

type Props = {
  imageUrl: string;
  marks: FlowMark[];
  activeType: FlowReviewStatus;
  readOnly?: boolean;
  onMarksChange?: (marks: FlowMark[]) => void;
};

/**
 * 自由布点留痕画布：<img> 上叠一个 viewBox 为「图片原始像素」的 SVG，
 * marks 存归一化 [{x,y,type}]，渲染时换算到像素坐标（与 ManualPaperGradingDialog 一致），
 * 避免 preserveAspectRatio="none" 下文字被非等比拉伸。
 */
export function FreeMarkCanvas({ imageUrl, marks, activeType, readOnly, onMarksChange }: Props) {
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleClick = useCallback(
    (event: React.MouseEvent<SVGSVGElement>) => {
      if (readOnly || !onMarksChange) return;
      const el = containerRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
      const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
      onMarksChange([...marks, { x, y, type: activeType }]);
    },
    [readOnly, onMarksChange, marks, activeType],
  );

  const renderMark = (mark: FlowMark, idx: number) => {
    if (!natural) return null;
    const px = mark.x * natural.w;
    const py = mark.y * natural.h;
    const size = Math.max(18, natural.w * 0.05);
    const strokeWidth = Math.max(2.5, size * 0.1);
    if (mark.type === "unanswered") {
      return (
        <ellipse
          key={idx}
          cx={px}
          cy={py}
          rx={size * 0.55}
          ry={size * 0.55}
          fill="none"
          stroke={MARK_COLOR}
          strokeWidth={strokeWidth}
        />
      );
    }
    if (mark.type === "partial") {
      return (
        <g key={idx}>
          <text x={px} y={py} textAnchor="middle" dominantBaseline="central" fill={MARK_COLOR} fontSize={size} fontFamily={MARK_FONT_FAMILY}>
            √
          </text>
          <line
            x1={px - size * 0.3}
            y1={py + size * 0.45}
            x2={px + size * 0.3}
            y2={py + size * 0.45}
            stroke={MARK_COLOR}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
          />
        </g>
      );
    }
    return (
      <text key={idx} x={px} y={py} textAnchor="middle" dominantBaseline="central" fill={MARK_COLOR} fontSize={size} fontFamily={MARK_FONT_FAMILY}>
        {mark.type === "correct" ? "√" : "×"}
      </text>
    );
  };

  return (
    <div ref={containerRef} className="relative inline-block max-w-full">
      <img
        src={gradingImageUrl(imageUrl)}
        alt="答题卡裁图"
        className="block max-h-[68vh] max-w-full select-none"
        draggable={false}
        onLoad={(e) => {
          const img = e.currentTarget;
          if (img.naturalWidth && img.naturalHeight) {
            setNatural({ w: img.naturalWidth, h: img.naturalHeight });
          }
        }}
      />
      {natural && (
        <svg
          className="absolute inset-0 h-full w-full"
          viewBox={`0 0 ${natural.w} ${natural.h}`}
          preserveAspectRatio="none"
          onClick={handleClick}
          style={{ cursor: readOnly ? "default" : "crosshair" }}
        >
          {marks.map(renderMark)}
        </svg>
      )}
    </div>
  );
}
