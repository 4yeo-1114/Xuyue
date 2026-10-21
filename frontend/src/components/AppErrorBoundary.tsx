import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * 全局错误边界：任何未捕获的渲染异常不再把整页打成白屏。
 * 1020 白屏机理排查：改码热更推送的中间态/运行时异常会把 React 整树卸载，
 * 且 vite hmr.overlay 被关 → 用户只见纯白、看不到任何原因。这里兜底渲染
 * 错误说明 + 刷新按钮（不依赖 i18n/上下文，挂在 Provider 外层也要能用）。
 */
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 留控制台线索，方便排查是哪次改动引入的
    console.error("[AppErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-background p-6">
          <div className="max-w-lg w-full rounded-lg border border-dashed bg-muted/30 p-6 text-center space-y-4">
            <div className="text-base font-medium">页面出错了，已阻止白屏</div>
            <div className="text-sm text-muted-foreground whitespace-pre-wrap break-all text-left max-h-40 overflow-auto">
              {this.state.error?.message || String(this.state.error)}
            </div>
            <div className="text-xs text-muted-foreground">
              刚改过代码的话：这是热更新推送瞬间的报错，刷新页面即可恢复。
            </div>
            <button
              type="button"
              className="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90"
              onClick={() => window.location.reload()}
            >
              刷新页面
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
