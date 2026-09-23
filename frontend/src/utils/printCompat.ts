/**
 * 打印兼容模式（compat）工具：为 window.print() 临时注入打印优化样式。
 * 仅兼容模式使用；标准模式完全不走这里，保持原行为不变（回滚保障）。
 */
import type { GlobalPrintPrefs } from "@/lib/globalPrintPrefs";

/** 注入样式节点的 id，用于打印后移除 */
export const COMPAT_PRINT_STYLE_ID = "grade-buddy-compat-print-style";

/** 隐藏打印操作栏的定位 class（加在 ExamGenPage 打印按钮所在的操作栏上） */
export const COMPAT_PRINT_TOOLBAR_CLASS = "print-action-bar";

/** 兼容模式下注入的样式内容；页边距取 prefs.marginMm（0~50，默认 5） */
export function buildCompatPrintStyles(
  prefs?: Partial<GlobalPrintPrefs>,
): string {
  const raw = prefs?.marginMm;
  const marginMm = Number.isFinite(raw) ? Math.trunc(Number(raw)) : 5;
  const clamped = Math.min(50, Math.max(0, marginMm));
  return `
@page { margin: ${clamped}mm; }
@media print {
  html, body { transform: none !important; }
  body {
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif !important;
  }
  * {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
  .${COMPAT_PRINT_TOOLBAR_CLASS} { display: none !important; }
}
`;
}

export function applyCompatPrintStyles(
  prefs?: Partial<GlobalPrintPrefs>,
): void {
  removeCompatPrintStyles();
  const style = document.createElement("style");
  style.id = COMPAT_PRINT_STYLE_ID;
  style.textContent = buildCompatPrintStyles(prefs);
  document.head.appendChild(style);
}

export function removeCompatPrintStyles(): void {
  document.getElementById(COMPAT_PRINT_STYLE_ID)?.remove();
}

/**
 * 包装打印调用：注入样式 → 执行打印 → 移除样式。
 * Chrome/Edge/Firefox 下 window.print() 同步阻塞，finally 即可清理；
 * 再挂一个 afterprint 兜底（幂等），覆盖 print() 非阻塞返回的浏览器。
 */
export function withCompatPrint(
  printFn: () => void,
  prefs?: Partial<GlobalPrintPrefs>,
): void {
  applyCompatPrintStyles(prefs);
  try {
    printFn();
  } finally {
    removeCompatPrintStyles();
    window.addEventListener("afterprint", () => removeCompatPrintStyles(), {
      once: true,
    });
  }
}
