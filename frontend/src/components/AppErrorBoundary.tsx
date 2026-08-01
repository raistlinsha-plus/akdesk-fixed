import { Component, type ErrorInfo, type ReactNode } from "react";
import { RefreshCcw, ShieldAlert } from "lucide-react";

interface AppErrorBoundaryProps {
  children: ReactNode;
  onReload?: () => void;
}

interface AppErrorBoundaryState {
  failed: boolean;
}

export class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("AKDesk interface failed", error, info.componentStack);
  }

  private reload = () => {
    if (this.props.onReload) {
      this.props.onReload();
      return;
    }
    window.location.reload();
  };

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="fatal-error" role="alert" aria-labelledby="fatal-error-title">
        <ShieldAlert size={32} />
        <div>
          <span className="eyebrow">LOCAL RECOVERY</span>
          <h1 id="fatal-error-title">界面加载遇到问题</h1>
          <p>本地研究数据没有被删除。请重新加载界面；如果问题持续，再到数据健康页检查服务状态。</p>
          <button type="button" className="primary-button" onClick={this.reload}>
            <RefreshCcw size={15} /> 重新加载界面
          </button>
        </div>
      </main>
    );
  }
}
