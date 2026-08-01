import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { CircleDollarSign, Search } from "lucide-react";
import { apiGet } from "../api";
import {
  ChangeValue,
  ErrorState,
  formatNumber,
  LoadingState,
  Panel,
  SourceFooter,
  WarningBanner,
  WatchButton,
} from "../components/UI";
import { useDataset } from "../components/useDataset";
import {
  filterFxPairs,
  fxQuoteDigits,
  fxReferenceLabel,
} from "../fxUtils";
import type {
  FxPairQuote,
  FxRmbReference,
  HistoryResponse,
} from "../types";
import { PageHeading } from "./MarketPages";

const LineChart = lazy(() =>
  import("../components/Charts").then((module) => ({
    default: module.LineChart,
  })),
);

export function ForexPage({
  refreshSeed,
  initialQuery = "",
}: {
  refreshSeed: number;
  initialQuery?: string;
}) {
  const pairs = useDataset<FxPairQuote[]>("/fx/pairs", refreshSeed);
  const references = useDataset<FxRmbReference[]>(
    "/fx/rmb-reference",
    refreshSeed,
  );
  const [query, setQuery] = useState(initialQuery);
  const [selectedReference, setSelectedReference] = useState("USDCNY");
  const [history, setHistory] = useState<HistoryResponse | null>(null);

  useEffect(() => {
    setQuery(initialQuery);
    const rows = references.dataset?.data ?? [];
    if (rows.some((item) => item.code === initialQuery)) {
      setSelectedReference(initialQuery);
    } else if (
      rows.length &&
      !rows.some((item) => item.code === selectedReference)
    ) {
      setSelectedReference(rows[0].code);
    }
  }, [initialQuery, references.dataset, selectedReference]);

  useEffect(() => {
    if (!references.dataset?.data.length) return;
    const codes = references.dataset.data.map((item) => item.code).join(",");
    let active = true;
    apiGet<HistoryResponse>(
      `/history?adapter=fx_rmb_reference&metric=mid&series=${encodeURIComponent(codes)}&days=45`,
    )
      .then((result) => {
        if (active) setHistory(result);
      })
      .catch(() => {
        if (active) setHistory(null);
      });
    return () => {
      active = false;
    };
  }, [references.dataset?.meta.fetched_at]);

  const visiblePairs = useMemo(
    () => filterFxPairs(pairs.dataset?.data ?? [], query),
    [pairs.dataset?.data, query],
  );
  const reference = references.dataset?.data.find(
    (item) => item.code === selectedReference,
  );
  const historySeries = history?.series.filter(
    (item) => item.key === selectedReference,
  );

  return (
    <div className="page-stack">
      <PageHeading
        eyebrow="GLOBAL FX"
        title="外汇市场"
        description="人民币日频参考价与全球主要外币对即时询价的独立观察"
      />

      {references.loading ? <LoadingState label="正在读取人民币汇率参考" /> : null}
      {references.error ? <ErrorState message={references.error} /> : null}
      {references.dataset ? (
        <>
          <WarningBanner meta={references.dataset.meta} />
          <div className="metrics-grid fx-reference-grid">
            {references.dataset.data.slice(0, 5).map((item) => (
              <article className="metric-card tall" key={item.code}>
                <span>{item.name}</span>
                <strong>{formatNumber(item.mid, item.code === "JPYCNY" ? 4 : 5)}</strong>
                <ChangeValue value={item.change_pct} suffix="%" />
                <small>{fxReferenceLabel(item)} · {item.observation_date}</small>
              </article>
            ))}
          </div>
        </>
      ) : null}

      <div className="two-column fx-layout">
        <Panel
          title="人民币参考价历史"
          eyebrow="RMB REFERENCE"
          action={
            references.dataset ? (
              <select
                className="compact-select"
                aria-label="人民币参考币种"
                value={selectedReference}
                onChange={(event) => setSelectedReference(event.target.value)}
              >
                {references.dataset.data.map((item) => (
                  <option value={item.code} key={item.code}>
                    {item.name}
                  </option>
                ))}
              </select>
            ) : null
          }
        >
          {reference ? (
            <>
              <div className="fx-reference-detail">
                <div>
                  <span>央行中间价</span>
                  <strong>{formatNumber(reference.mid, reference.code === "JPYCNY" ? 4 : 5)}</strong>
                </div>
                <div>
                  <span>中行现汇买价</span>
                  <strong>{formatNumber(reference.bid, reference.code === "JPYCNY" ? 4 : 5)}</strong>
                </div>
                <div>
                  <span>中行汇卖价</span>
                  <strong>{formatNumber(reference.ask, reference.code === "JPYCNY" ? 4 : 5)}</strong>
                </div>
              </div>
              {history?.dates.length && historySeries?.length ? (
                <Suspense
                  fallback={<div className="chart-loading skeleton" style={{ height: 280 }} />}
                >
                  <LineChart
                    categories={history.dates}
                    series={historySeries}
                    height={280}
                    unit=" CNY"
                  />
                </Suspense>
              ) : (
                <div className="empty-state compact-empty">
                  <strong>正在积累本地参考价历史</strong>
                  <p>首次成功读取后会保存最近公开日频序列。</p>
                </div>
              )}
              <SourceFooter meta={references.dataset?.meta} />
            </>
          ) : (
            <LoadingState />
          )}
        </Panel>

        <Panel title="数据边界" eyebrow="MARKET NOTE">
          <div className="fx-boundary-note">
            <CircleDollarSign size={24} />
            <strong>用于市场观察，不是可成交报价</strong>
            <p>
              人民币参考价是日频数据；全球外币对是银行间最新询价快照，
              源未提供可信观测时点，因此不会触发自动提醒，也不应作为交易执行价格。
            </p>
            <ul>
              <li>两条数据链路分别缓存和展示健康状态。</li>
              <li>即时询价可搜索、加入自选并关联研究项目。</li>
              <li>异常、过期和演示数据继续显示明确标识。</li>
            </ul>
          </div>
        </Panel>
      </div>

      <Panel
        title="全球外币对即时询价"
        eyebrow="INTERBANK QUOTE"
        action={
          <label className="table-search">
            <Search size={14} />
            <input
              aria-label="筛选外币对"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="代码或名称"
            />
          </label>
        }
      >
        {pairs.loading ? <LoadingState label="正在读取全球外币对" /> : null}
        {pairs.error ? <ErrorState message={pairs.error} /> : null}
        {pairs.dataset ? (
          <>
            <WarningBanner meta={pairs.dataset.meta} />
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>货币对</th>
                    <th className="num">买报价</th>
                    <th className="num">卖报价</th>
                    <th className="num">中间值</th>
                    <th className="num">点差</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visiblePairs.map((item) => {
                    const digits = fxQuoteDigits(item.code);
                    return (
                      <tr key={item.code}>
                        <td>
                          <strong>{item.name}</strong>
                          <small>{item.pair}</small>
                        </td>
                        <td className="num mono">{formatNumber(item.bid, digits)}</td>
                        <td className="num mono">{formatNumber(item.ask, digits)}</td>
                        <td className="num mono">{formatNumber(item.mid, digits)}</td>
                        <td className="num mono">{formatNumber(item.spread_pips, 2)} pips</td>
                        <td>
                          <WatchButton
                            objectType="fx"
                            objectId={item.code}
                            name={item.name}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {!visiblePairs.length ? (
              <div className="empty-state compact-empty">
                <strong>没有匹配的货币对</strong>
                <p>可以尝试 USD、JPY 或中文名称。</p>
              </div>
            ) : null}
            <SourceFooter meta={pairs.dataset.meta} />
          </>
        ) : null}
      </Panel>
    </div>
  );
}
