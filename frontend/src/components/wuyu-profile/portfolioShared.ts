/**
 * 五育成长画像域共享常量与工具。
 * 维度顺序、雷达配色、档位徽标映射。
 */
import type { WuyuDimension } from "@/services/wuyuApi";

/** 五育维度顺序（雷达图/卡片遍历用），含 AI 素养维度 */
export const DIMENSIONS: WuyuDimension[] = [
  "moral",
  "intellectual",
  "physical",
  "aesthetic",
  "labor",
  "ai_literacy",
];

/** 维度 → i18n key（wuyu.dim.xxx） */
export const DIMENSION_LABEL_KEY: Record<WuyuDimension, string> = {
  moral: "wuyu.dim.moral",
  intellectual: "wuyu.dim.intellectual",
  physical: "wuyu.dim.physical",
  aesthetic: "wuyu.dim.aesthetic",
  labor: "wuyu.dim.labor",
  ai_literacy: "wuyu.dim.ai_literacy",
};

/** 维度 → 主题色（雷达描边/填充、指标卡图标） */
export const DIMENSION_COLORS: Record<WuyuDimension, string> = {
  moral: "#f59e0b", // amber-500
  intellectual: "#3b82f6", // blue-500
  physical: "#22c55e", // green-500
  aesthetic: "#ec4899", // pink-500
  labor: "#8b5cf6", // violet-500
  ai_literacy: "#06b6d4", // cyan-500
};

/** 五档 → Badge variant */
export function tierVariant(
  tier: string | null | undefined,
): "default" | "secondary" | "destructive" | "outline" {
  switch (tier) {
    case "A+":
    case "A":
      return "default";
    case "B":
      return "secondary";
    case "C":
      return "outline";
    case "D":
      return "destructive";
    default:
      return "outline";
  }
}

/** 把后端数值安全转为 number（null/undefined → 0） */
export function toNum(v: number | string | null | undefined): number {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

/** 格式化日期（兼容 ISO 字符串 / 空值） */
export function formatDateTime(v?: string | null): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return d.toLocaleString();
}

/** 学期正则：2025-2026-1 */
export const TERM_PATTERN = /^\d{4}-\d{4}-[12]$/;
