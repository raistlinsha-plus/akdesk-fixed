import { useEffect, useState } from "react";
import {
  CheckCircle2,
  CircleDashed,
  DatabaseZap,
  ExternalLink,
  KeyRound,
  RefreshCcw,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { apiGet, apiPost } from "../api";
import {
  classNames,
  formatDateTime,
  LoadingState,
  Panel,
} from "../components/UI";
import type { ConnectorCatalog, ConnectorItem, HealthItem } from "../types";
import { researchAvailability } from "../healthStatus";
import { startVisibilityPolling } from "../visibilityPolling";

const stateCopy = {
  healthy: { label: "健康", icon: CheckCircle2 },
  cached: { label: "缓存可用", icon: DatabaseZap },
  degraded: { label: "降级", icon: TriangleAlert },
  unavailable: { label: "不可用", icon: XCircle },
  not_checked: { label: "未检查", icon: CircleDashed },
};

const researchCopy = {
  ready: { label: "当前已验证", state: "healthy" as const },
  limited: { label: "可信缓存可参考", state: "degraded" as const },
  blocked: { label: "禁止沉淀为证据", state: "unavailable" as const },
  unchecked: { label: "尚未验证", state: "not_checked" as const },
};

interface RuntimeInfo {
  runtime: {
    process_id: number;
    uptime_seconds: number;
    threads: number;
    file_descriptors: {
      open: number | null;
      soft_limit: number | null;
      hard_limit: number | null;
      utilization_percent: number | null;
    };
  };
}

export function HealthPage() {
  const [items, setItems] = useState<HealthItem[]>([]);
  const [connectors, setConnectors] = useState<ConnectorCatalog | null>(null);
  const [runtime, setRuntime] = useState<RuntimeInfo["runtime"] | null>(null);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load(silent = false) {
    if (!silent) setLoading(true);
    setError(null);
    Promise.all([
      apiGet<HealthItem[]>("/sources/health"),
      apiGet<RuntimeInfo>("/info"),
      apiGet<ConnectorCatalog>("/connectors"),
    ])
      .then(([healthItems, info, connectorCatalog]) => {
        setItems(healthItems);
        setRuntime(info.runtime);
        setConnectors(connectorCatalog);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "状态读取失败"),
      )
      .finally(() => {
        if (!silent) setLoading(false);
      });
  }

  useEffect(() => {
    load();
    return startVisibilityPolling(() => load(true), 15_000);
  }, []);

  async function clearCache() {
    if (
      !window.confirm(
        "确认清空中国行情、World Bank 低频缓存与 GDELT 事件元数据缓存？研究项目、研究证据、自选、提醒、触发历史和日报归档不会被删除；FRED 观测值本来就不会持久化。",
      )
    ) {
      return;
    }
    try {
      await apiPost("/cache/clear");
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "缓存清理失败");
    }
  }

  async function retry(adapter: string) {
    setRetrying(adapter);
    setError(null);
    try {
      await apiPost("/sources/" + adapter + "/retry");
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "数据源重试失败");
    } finally {
      setRetrying(null);
    }
  }

  const healthy = items.filter((item) => item.state === "healthy").length;
  const cached = items.filter((item) => item.state === "cached").length;
  const degraded = items.filter((item) => item.state === "degraded").length;
  const unavailable = items.filter(
    (item) => item.state === "unavailable",
  ).length;
  const research = researchAvailability(items);

  return (
    <div className="page-stack">
      <header className="page-heading">
        <div>
          <span className="eyebrow">DATA OPERATIONS</span>
          <h1>数据健康中心</h1>
          <p>每个数字都能追溯来源、时间和当前可用状态</p>
        </div>
        <button className="secondary-button" onClick={() => load()}>
          <RefreshCcw size={15} />
          同步状态
        </button>
      </header>

      <div className="health-summary">
        <Summary label="当前已验证" value={research.ready} state="healthy" />
        <Summary label="可信缓存可参考" value={research.limited} state="degraded" />
        <Summary label="禁止沉淀为证据" value={research.blocked} state="unavailable" />
        <Summary label="尚未验证" value={research.unchecked} state="not_checked" />
      </div>

      <p className="health-meaning-note">
        “连接”说明本次能否访问数据源；“研究”说明当前数据能否进入证据链。可信缓存可以展示和参考，只有完成当前验证且质量可信的数据才标记为“当前已验证”。
      </p>

      <p className="health-connection-note">
        连接状态独立统计：健康 {healthy} · 缓存 {cached} · 降级 {degraded} · 不可用 {unavailable} · 未检查 {items.length - healthy - cached - degraded - unavailable}
      </p>

      {runtime ? (
        <p className="health-connection-note">
          本机运行：PID {runtime.process_id} · 已运行 {formatUptime(runtime.uptime_seconds)} · {runtime.threads} 个线程 · 文件句柄 {runtime.file_descriptors.open ?? "—"}/{runtime.file_descriptors.soft_limit ?? "不限"}
          {runtime.file_descriptors.utilization_percent === null ? "" : `（${runtime.file_descriptors.utilization_percent}%）`}
        </p>
      ) : null}

      <Panel title="外部数据连接器" eyebrow="ACCESS · STORAGE · LICENSE">
        {loading ? <LoadingState /> : null}
        {!loading && connectors ? (
          <>
            <div className="connector-grid">
              {connectors.connectors.map((connector) => (
                <ConnectorCard connector={connector} key={connector.id} />
              ))}
            </div>
            <p className="method-note">{connectors.policy}</p>
          </>
        ) : null}
      </Panel>

      <Panel
        title="数据适配器"
        eyebrow="SOURCE ADAPTERS"
        action={
          <button className="text-button" onClick={clearCache}>
            <DatabaseZap size={14} /> 清空缓存
          </button>
        }
      >
        {loading ? <LoadingState /> : null}
        {!loading ? (
          <div className="source-list">
            {items.map((item) => {
              const copy = stateCopy[item.state];
              const researchState = researchCopy[item.research_status];
              const Icon = copy.icon;
              return (
                <article className="source-item" key={item.adapter}>
                  <div className={classNames("source-state", item.state)}>
                    <Icon size={18} />
                  </div>
                  <div className="source-copy">
                    <div>
                      <strong>{item.label}</strong>
                      <span className={classNames("status-pill", item.state)}>
                        {item.refreshing ? "刷新中" : `连接·${copy.label}`}
                      </span>
                      <span className={classNames("status-pill", researchState.state)}>
                        研究·{researchState.label}
                      </span>
                      <button
                        className="source-retry"
                        onClick={() => retry(item.adapter)}
                        disabled={retrying === item.adapter}
                      >
                        <RefreshCcw className={retrying === item.adapter ? "spin" : undefined} size={12} />
                        重试
                      </button>
                    </div>
                    <small>
                      {item.adapter} · {executionLabel(item.execution_mode)}
                      {item.circuit_state === "open" ? ` · 熔断至 ${formatDateTime(item.next_retry_at)}` : null}
                      {item.circuit_state === "half_open" ? " · 探测恢复中" : null}
                    </small>
                    {item.message ? <p>{item.message}</p> : null}
                  </div>
                  <dl>
                    <div>
                      <dt>数据时间</dt>
                      <dd>{item.observation_time || (item.research_status === "blocked" ? "无可信观测时间" : "—")}</dd>
                    </div>
                    <div>
                      <dt>可信等级</dt>
                      <dd>{trustLabel(item.trust_level)}</dd>
                    </div>
                    <div>
                      <dt>缓存</dt>
                      <dd>
                        {item.cache_persisted
                          ? formatAge(item.cache_age_seconds)
                          : "无持久缓存"}
                      </dd>
                    </div>
                    <div>
                      <dt>{item.circuit_state === "open" ? "恢复探测" : "下次检查"}</dt>
                      <dd>{formatDateTime(item.circuit_state === "open" ? item.next_retry_at : item.next_refresh_at)}</dd>
                    </div>
                  </dl>
                  <details className="source-more">
                    <summary>查看质量与运行详情</summary>
                    <dl>
                      <div><dt>市场状态</dt><dd>{item.market_status_label}</dd></div>
                      <div><dt>质量评分</dt><dd title={item.quality_issues.join("；")}>{item.quality_score ?? "—"}</dd></div>
                      <div><dt>异常隔离</dt><dd>{item.suspicious_rows} 条</dd></div>
                      <div><dt>最近成功</dt><dd>{formatDateTime(item.last_success_at)}</dd></div>
                      <div><dt>记录数</dt><dd>{item.rows}</dd></div>
                      <div><dt>耗时</dt><dd>{item.latency_ms === null || item.latency_ms === undefined ? "—" : item.latency_ms + "ms"}</dd></div>
                      <div><dt>连续失败</dt><dd>{item.consecutive_failures} 次</dd></div>
                      <div>
                        <dt>故障熔断</dt>
                        <dd>{item.circuit_state === "closed" ? "关闭" : item.circuit_state === "open" ? "已开启" : "恢复探测"}</dd>
                      </div>
                    </dl>
                    {item.quality_issues.length ? <p>{item.quality_issues.join("；")}</p> : null}
                  </details>
                </article>
              );
            })}
          </div>
        ) : null}
      </Panel>

      {error ? <div className="warning-banner" role="alert"><TriangleAlert size={16} /><span>{error}</span></div> : null}

      <div className="compliance-note">
        <TriangleAlert size={17} />
        <div>
          <strong>公开数据边界</strong>
          <p>
            AKShare、FRED、World Bank 与 GDELT 数据仅供研究参考；FRED 观测值按请求获取且不落盘，World Bank 数据按 CC BY 4.0 署名持久缓存，GDELT 只缓存事件元数据且必须打开原文核验。本终端不会把缓存、降级、演示数据或媒体线索伪装成交易级实时行情与事实结论。
          </p>
        </div>
      </div>
    </div>
  );
}

function ConnectorCard({ connector }: { connector: ConnectorItem }) {
  const copy = stateCopy[connector.state];
  const researchState = researchCopy[connector.research_status];
  const Icon = copy.icon;
  const credential =
    connector.access_mode === "public"
      ? "无需凭据"
      : connector.credential_configured
        ? connector.credential_source === "keychain"
          ? "Keychain 已配置"
          : "环境变量已配置"
        : "需要用户 API Key";
  return (
    <article className="connector-card">
      <header>
        <div className={classNames("source-state", connector.state)}>
          <Icon size={17} />
        </div>
        <div>
          <strong>{connector.name}</strong>
          <small>{connector.capabilities.join(" · ")}</small>
        </div>
      </header>
      <div className="connector-status-row">
        <span className={classNames("status-pill", connector.state)}>
          连接·{copy.label}
        </span>
        <span className={classNames("status-pill", researchState.state)}>
          研究·{researchState.label}
        </span>
      </div>
      <dl>
        <div>
          <dt><KeyRound size={12} /> 访问</dt>
          <dd>{credential}</dd>
        </div>
        <div>
          <dt>本地保存</dt>
          <dd>{storageLabel(connector.storage_mode)}</dd>
        </div>
        <div>
          <dt>缓存记录</dt>
          <dd>{connector.cache_rows || "—"}</dd>
        </div>
        <div>
          <dt>最近成功</dt>
          <dd>{formatDateTime(connector.last_success_at)}</dd>
        </div>
      </dl>
      <details>
        <summary>查看许可、缓存与使用边界</summary>
        <p>{connector.persistence_notice}</p>
        <p>{connector.quota_notice}</p>
        <p>{connector.boundary_notice}</p>
        <div className="connector-links">
          <a href={connector.docs_url} target="_blank" rel="noreferrer">
            接口文档 <ExternalLink size={12} />
          </a>
          <a href={connector.license_url} target="_blank" rel="noreferrer">
            {connector.license_name} <ExternalLink size={12} />
          </a>
        </div>
        <small>署名：{connector.attribution}</small>
      </details>
    </article>
  );
}

function storageLabel(mode: ConnectorItem["storage_mode"]): string {
  return {
    persistent_cache: "许可署名缓存",
    request_scoped: "请求级，不落盘",
    mixed_upstream_cache: "质量门后缓存",
    metadata_cache: "仅元数据缓存",
  }[mode];
}

function executionLabel(mode: HealthItem["execution_mode"]): string {
  return {
    isolated_process: "隔离进程",
    in_process_http: "线程池网络请求",
    local_demo: "本地演示",
  }[mode];
}

function formatAge(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return "已持久化";
  if (seconds < 60) return seconds + " 秒前";
  if (seconds < 3600) return Math.floor(seconds / 60) + " 分钟前";
  if (seconds < 86_400) return Math.floor(seconds / 3600) + " 小时前";
  return Math.floor(seconds / 86_400) + " 天前";
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} 小时`;
  return `${Math.floor(seconds / 86_400)} 天`;
}

function trustLabel(level: HealthItem["trust_level"]): string {
  return {
    trusted: "可信",
    partial: "部分可用",
    suspicious: "含异常隔离",
    unavailable: "不可用于研究",
  }[level];
}

function Summary({
  label,
  value,
  state,
}: {
  label: string;
  value: number;
  state: keyof typeof stateCopy;
}) {
  const Icon = stateCopy[state].icon;
  return (
    <article className={classNames("health-card", state)}>
      <Icon size={19} />
      <div>
        <strong>{value}</strong>
        <span>{label}</span>
      </div>
    </article>
  );
}
