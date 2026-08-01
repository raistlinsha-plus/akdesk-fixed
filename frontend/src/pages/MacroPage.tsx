import { lazy, Suspense, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  KeyRound,
  LoaderCircle,
  RefreshCcw,
  Search,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { apiDelete, apiGet, apiPost } from "../api";
import {
  ErrorState,
  LoadingState,
  Panel,
  SourceFooter,
  WatchButton,
  formatNumber,
} from "../components/UI";
import type {
  Dataset,
  FredIntegrationStatus,
  MacroCatalogItem,
  MacroSeriesData,
} from "../types";
import { shanghaiDate } from "../researchUtils";
import { PageHeading } from "./MarketPages";

const LineChart = lazy(() =>
  import("../components/Charts").then((module) => ({ default: module.LineChart })),
);

const TOPICS = ["", "美国利率", "通胀与实际利率", "就业与增长", "政策与流动性"];

export function MacroPage({
  initialQuery,
  navigate,
}: {
  initialQuery?: string;
  navigate: (page: string, query?: string) => void;
}) {
  const [catalog, setCatalog] = useState<MacroCatalogItem[]>([]);
  const [settings, setSettings] = useState<FredIntegrationStatus | null>(null);
  const [query, setQuery] = useState("");
  const [topic, setTopic] = useState("");
  const [selected, setSelected] = useState(initialQuery || "DGS10");
  const [detail, setDetail] = useState<Dataset<MacroSeriesData> | null>(null);
  const [years, setYears] = useState(5);
  const [detailNonce, setDetailNonce] = useState(0);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [savingKey, setSavingKey] = useState(false);
  const [testingKey, setTestingKey] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [releases, setReleases] = useState<Dataset<Array<{ date: string; release_id?: number; name: string }>> | null>(null);
  const [releaseLoading, setReleaseLoading] = useState(false);
  const [releaseError, setReleaseError] = useState<string | null>(null);

  function loadBase() {
    setLoading(true);
    setError(null);
    Promise.all([
      apiGet<MacroCatalogItem[]>("/macro/catalog"),
      apiGet<{ fred: FredIntegrationStatus }>("/settings/integrations"),
    ])
      .then(([items, integration]) => {
        setCatalog(items);
        setSettings(integration.fred);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "宏观目录加载失败"),
      )
      .finally(() => setLoading(false));
  }

  useEffect(loadBase, []);

  useEffect(() => {
    if (!settings?.verified) {
      setReleases(null);
      setReleaseError(null);
      return;
    }
    setReleaseLoading(true);
    setReleaseError(null);
    apiGet<Dataset<Array<{ date: string; release_id?: number; name: string }>>>("/macro/releases")
      .then(setReleases)
      .catch((reason: unknown) => {
        setReleases(null);
        setReleaseError(reason instanceof Error ? reason.message : "FRED 发布日历加载失败");
      })
      .finally(() => setReleaseLoading(false));
  }, [settings?.verified]);

  useEffect(() => {
    if (!selected || !settings?.verified) {
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }
    let active = true;
    setDetailLoading(true);
    setDetailError(null);
    apiGet<Dataset<MacroSeriesData>>(`/macro/series/${encodeURIComponent(selected)}?years=${years}&refresh=${detailNonce > 0 ? "true" : "false"}`)
      .then((value) => {
        if (active) setDetail(value);
      })
      .catch((reason: unknown) => {
        if (active) {
          setDetail(null);
          setDetailError(reason instanceof Error ? reason.message : "宏观序列加载失败");
        }
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => {
      active = false;
    };
  }, [detailNonce, selected, settings?.verified, years]);

  const visibleCatalog = useMemo(() => {
    const term = query.trim().toLowerCase();
    return catalog.filter((item) => {
      const matchesTopic = !topic || item.topic === topic;
      const haystack = `${item.series_id} ${item.title} ${item.title_zh} ${item.topic}`.toLowerCase();
      return matchesTopic && (!term || haystack.includes(term));
    });
  }, [catalog, query, topic]);

  async function saveKey(event: FormEvent) {
    event.preventDefault();
    const key = apiKey.trim().toLowerCase();
    if (!key) return;
    setSavingKey(true);
    setError(null);
    setStatusMessage(null);
    try {
      const result = await apiPost<FredIntegrationStatus>("/settings/integrations/fred", {
        api_key: key,
      });
      setSettings(result);
      setApiKey("");
      setStatusMessage("FRED 连接验证成功，Key 已保存至 macOS Keychain");
      setSelected((current) => current || "DGS10");
      setDetailNonce((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "FRED 配置失败");
    } finally {
      setSavingKey(false);
    }
  }

  async function verifyKey() {
    setTestingKey(true);
    setError(null);
    setStatusMessage(null);
    try {
      await apiPost("/settings/integrations/fred/test");
      const integration = await apiGet<{ fred: FredIntegrationStatus }>("/settings/integrations");
      setSettings(integration.fred);
      setStatusMessage("FRED 连接验证成功");
      setDetailNonce((value) => value + 1);
    } catch (reason) {
      const integration = await apiGet<{ fred: FredIntegrationStatus }>("/settings/integrations").catch(() => null);
      if (integration) setSettings(integration.fred);
      setError(reason instanceof Error ? reason.message : "FRED 连接验证失败");
    } finally {
      setTestingKey(false);
    }
  }

  async function removeKey() {
    setError(null);
    setStatusMessage(null);
    try {
      await apiDelete("/settings/integrations/fred");
      const integration = await apiGet<{ fred: FredIntegrationStatus }>("/settings/integrations");
      setSettings(integration.fred);
      setStatusMessage(
        integration.fred.configured
          ? "当前仍由环境变量提供 API Key"
          : "Keychain 中的 FRED API Key 已删除",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "FRED 配置删除失败");
    }
  }

  const observations = detail?.data.observations ?? [];
  const latest = [...observations].reverse().find((item) => item.value !== null);
  const upcomingReleases = releases?.data.filter((item) => item.date >= shanghaiDate()).slice(0, 20) ?? [];
  const connectionTitle = !settings?.configured
    ? "配置个人 FRED API Key"
    : settings.verified
      ? "FRED 已验证连接"
      : settings.verification_state === "failed"
        ? "FRED 验证失败"
        : "FRED Key 已保存，待验证";

  return (
    <div className="page-stack macro-page">
      <PageHeading
        eyebrow="GLOBAL MACRO"
        title="美国宏观与利率"
        description="FRED 精选指标、数据版本与研究入口"
      />

      <section className={`integration-card ${settings?.verified ? "connected" : ""}`}>
        <div className="integration-copy">
          {settings?.verified ? <ShieldCheck size={23} /> : <KeyRound size={23} />}
          <div>
            <span className="eyebrow">FRED INTEGRATION</span>
            <h2>{connectionTitle}</h2>
            <p>
              {settings?.configured
                ? `凭据来源：${settings.credential_source === "keychain" ? "macOS Keychain" : "环境变量"}。Key 不会写入数据库、日志或导出文件；观测值按请求获取且不落盘。`
                : "从 FRED 免费申请 32 位 API Key，应用会先验证连接，成功后才保存到本机 Keychain。未配置时仍可浏览精选目录。"}
            </p>
          </div>
        </div>
        {settings?.configured ? (
          <div className="panel-button-row">
            {!settings.verified ? (
              <button className="secondary-button" onClick={verifyKey} disabled={testingKey}>
                {testingKey ? <LoaderCircle className="spin" size={14} /> : <RefreshCcw size={14} />} 验证连接
              </button>
            ) : null}
            <button className="secondary-button danger-text" onClick={removeKey}>
              <Trash2 size={14} /> 移除 Keychain 凭据
            </button>
          </div>
        ) : (
          <form className="fred-key-form" onSubmit={saveKey}>
            <label>
              <span className="sr-only">FRED API Key</span>
              <input
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="32 位 FRED API Key"
                minLength={32}
                maxLength={32}
                autoComplete="off"
                required
              />
            </label>
            <button className="primary-button" disabled={savingKey}>
              {savingKey ? <LoaderCircle className="spin" size={14} /> : <KeyRound size={14} />}
              保存并验证
            </button>
          </form>
        )}
      </section>
      {statusMessage ? <p className="inline-status" role="status">{statusMessage}</p> : null}
      {settings ? (
        <p className="provider-notice">
          {settings.notice} {settings.storage_notice} <a href={settings.terms_url} target="_blank" rel="noreferrer">查看完整使用条款 <ExternalLink size={11} /></a>
        </p>
      ) : null}
      {error ? <ErrorState message={error} /> : null}

      <div className="macro-layout">
        <Panel title="精选指标目录" eyebrow="CURATED SERIES" className="macro-catalog-panel">
          <div className="macro-filter-bar">
            <label>
              <Search size={14} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索代码或指标" />
            </label>
            <select value={topic} onChange={(event) => setTopic(event.target.value)} aria-label="指标主题">
              {TOPICS.map((item) => <option value={item} key={item || "all"}>{item || "全部主题"}</option>)}
            </select>
          </div>
          {loading ? <LoadingState /> : null}
          <div className="macro-catalog-list">
            {visibleCatalog.map((item) => (
              <button
                key={item.series_id}
                className={selected === item.series_id ? "active" : undefined}
                onClick={() => setSelected(item.series_id)}
              >
                <span className="macro-series-code">{item.series_id}</span>
                <div><strong>{item.title_zh}</strong><small>{item.topic} · {item.frequency}</small></div>
                <ArrowRight size={13} aria-label="按需获取" />
              </button>
            ))}
          </div>
        </Panel>

        <Panel
          title={detail?.data.series.title_zh || selected || "指标详情"}
          eyebrow="SERIES DETAIL"
          className="macro-detail-panel"
          action={
            selected ? (
              <div className="panel-button-row">
                <WatchButton objectType="macro" objectId={selected} name={detail?.data.series.title_zh || selected} />
                <button className="secondary-button" onClick={() => navigate("chart-lab", selected)}>
                  进入研究室 <ArrowRight size={13} />
                </button>
              </div>
            ) : null
          }
        >
          <div className="macro-detail-toolbar">
            <label>区间
              <select value={years} onChange={(event) => setYears(Number(event.target.value))}>
                <option value={1}>1 年</option><option value={5}>5 年</option><option value={10}>10 年</option><option value={20}>20 年</option>
              </select>
            </label>
            <button className="icon-button" onClick={() => setDetailNonce((value) => value + 1)} title="重新请求 FRED 官方数据" aria-label="重新请求 FRED 官方数据">
              <RefreshCcw size={14} />
            </button>
          </div>
          {detailLoading ? <LoadingState /> : null}
          {detailError ? <ErrorState message={detailError} /> : null}
          {detail ? (
            <>
              <div className="macro-series-summary">
                <div><span>最新值</span><strong>{formatNumber(latest?.value, 3)}</strong></div>
                <div><span>观察期</span><strong>{latest?.date || "—"}</strong></div>
                <div><span>频率</span><strong>{detail.data.series.frequency || "—"}</strong></div>
                <div><span>单位</span><strong>{detail.data.series.units || "—"}</strong></div>
              </div>
              <Suspense fallback={<div className="chart-loading skeleton" style={{ height: 300 }} />}>
                <LineChart
                  categories={observations.map((item) => item.date)}
                  series={[{ name: detail.data.series.title_zh, values: observations.map((item) => item.value) }]}
                  height={300}
                  unit={detail.data.series.units === "Percent" || detail.data.series.units === "%" ? "%" : ""}
                />
              </Suspense>
              <div className="macro-metadata-grid">
                <div><span>季调</span><strong>{detail.data.series.seasonal_adjustment || "未说明"}</strong></div>
                <div><span>数据版本</span><strong>{latest?.realtime_start || "—"}</strong></div>
                <div><span>官方更新</span><strong>{detail.data.series.last_updated || "—"}</strong></div>
                <div><span>原始来源</span><strong>{detail.data.series.source_organization || "见 FRED 序列说明"}</strong></div>
                <div><span>本地存储</span><strong>观测值不落盘</strong></div>
              </div>
              {detail.data.series.notes ? <p className="method-note">{detail.data.series.notes}</p> : null}
              <SourceFooter meta={detail.meta} />
            </>
          ) : null}
        </Panel>
      </div>

      {settings?.verified ? (
        <Panel title="宏观数据发布日历" eyebrow="FRED RELEASES">
          {releaseLoading ? <LoadingState label="正在读取 FRED 发布日历" /> : null}
          {releaseError ? <ErrorState message={releaseError} /> : null}
          {upcomingReleases.length ? (
            <div className="macro-release-list">
              {upcomingReleases.map((item, index) => (
                <article key={`${item.date}-${item.release_id || index}`}>
                  <span>{item.date}</span><strong>{item.name}</strong>
                </article>
              ))}
            </div>
          ) : !releaseLoading && !releaseError ? (
            <div className="empty-state compact-empty"><CheckCircle2 size={24} /><strong>当前窗口暂无发布记录</strong></div>
          ) : null}
          <p className="method-note">发布日期来自数据提供方计划，不代表该时刻 FRED 已完成数据更新。</p>
          <SourceFooter meta={releases?.meta} />
        </Panel>
      ) : null}
    </div>
  );
}
