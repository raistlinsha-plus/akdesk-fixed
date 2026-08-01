import { useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Check,
  CloudOff,
  Database,
  LoaderCircle,
  Star,
} from "lucide-react";
import { useWatchlist } from "./WatchlistContext";
import type { SourceMeta } from "../types";

export function classNames(
  ...items: Array<string | false | null | undefined>
): string {
  return items.filter(Boolean).join(" ");
}

export function formatNumber(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface PanelProps {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Panel({
  title,
  eyebrow,
  action,
  children,
  className,
}: PanelProps) {
  return (
    <section className={classNames("panel", className)}>
      <header className="panel-header">
        <div>
          {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
          <h2>{title}</h2>
        </div>
        {action ? <div className="panel-action">{action}</div> : null}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function ChangeValue({
  value,
  suffix = " BP",
}: {
  value: number | null | undefined;
  suffix?: string;
}) {
  if (value === null || value === undefined) {
    return <span className="muted">—</span>;
  }
  const positive = value > 0;
  const negative = value < 0;
  return (
    <span
      className={classNames(
        "change",
        positive && "rise",
        negative && "fall",
      )}
    >
      {positive ? "+" : ""}
      {formatNumber(value, 2)}
      {suffix}
    </span>
  );
}

export function SourceFooter({ meta }: { meta?: SourceMeta | null }) {
  if (!meta) return null;
  const stateCopy = {
    live: "实时更新",
    latest: meta.market_status_label.includes("年度")
      ? "最新年度"
      : meta.market_status === "daily"
        ? "最新日频"
        : "最新快照",
    cached: "本地缓存",
    stale: "缓存过期",
    demo: "演示数据",
  }[meta.data_state];
  const trustCopy = {
    trusted: "可信",
    partial: "部分可用",
    suspicious: "含异常",
    unavailable: "不可用于研究",
  }[meta.trust_level];
  return (
    <footer className="source-footer">
      <div className="source-main">
        <Database size={13} />
        <span>{meta.source}</span>
        <span className={classNames("tag", meta.market_status === "trading" && "healthy-tag")}>
          {meta.market_status_label}
        </span>
        <span className={classNames("tag", meta.demo && "warning", meta.stale && "muted-tag")}>
          {stateCopy}
        </span>
        <span className={classNames("tag", meta.quality_score < 80 && "warning")}>
          质量 {meta.quality_score}
        </span>
        <span className={classNames("tag", meta.trust_level !== "trusted" && "warning")}>
          {trustCopy}
        </span>
      </div>
      <span title={meta.fetched_at}>
        观测 {meta.observation_time || "源未提供"} · 抓取 {formatDateTime(meta.fetched_at)}
      </span>
    </footer>
  );
}

export function LoadingState({ label = "正在读取数据" }: { label?: string }) {
  return (
    <div className="state-block">
      <LoaderCircle className="spin" size={20} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="state-block error">
      <CloudOff size={20} />
      <div>
        <strong>暂时无法完成</strong>
        <p>{message}</p>
        <div className="state-recovery">
          <span>可先重试当前操作；如果是行情或连接问题，请查看数据源诊断。</span>
          <a href="#/health">打开数据健康</a>
        </div>
      </div>
    </div>
  );
}

export function WarningBanner({ meta }: { meta?: SourceMeta | null }) {
  const message = meta?.warnings[0] ?? meta?.quality_issues[0];
  if (!message) return null;
  return (
    <div className="warning-banner">
      <AlertTriangle size={16} />
      <span>{message}</span>
    </div>
  );
}

export function WatchButton({
  objectType,
  objectId,
  name,
}: {
  objectType: string;
  objectId: string;
  name: string;
}) {
  const { isSaved, isBusy, toggle } = useWatchlist();
  const [failed, setFailed] = useState(false);
  const saved = isSaved(objectType, objectId);
  const busy = isBusy(objectType, objectId);

  async function handleToggle() {
    setFailed(false);
    try {
      await toggle(objectType, objectId, name);
    } catch {
      setFailed(true);
    }
  }

  return (
    <button
      type="button"
      className={classNames("icon-button", saved && "active", failed && "danger")}
      onClick={handleToggle}
      disabled={busy}
      aria-label={saved ? "移出自选" : "加入自选"}
      title={failed ? "操作失败，请重试" : saved ? "移出自选" : "加入自选"}
    >
      {busy ? <LoaderCircle className="spin" size={15} /> : saved ? <Check size={15} /> : <Star size={15} />}
    </button>
  );
}
