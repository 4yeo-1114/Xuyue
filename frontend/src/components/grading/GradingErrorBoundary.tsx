import { Component, type ErrorInfo, type ReactNode } from "react";
import { useLocale } from "@/contexts/LocaleContext";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

function DefaultGradingErrorFallback() {
  const { t } = useLocale();
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded border border-dashed bg-muted/30 p-4 text-center text-sm text-muted-foreground min-h-[100px]">
      <span>{t("grading.preview.loadFailed")}</span>
    </div>
  );
}

/** 捕获子组件抛出的错误，避免整页白屏 */
export class GradingErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return <DefaultGradingErrorFallback />;
    }
    return this.props.children;
  }
}
