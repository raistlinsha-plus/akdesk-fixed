import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  BellRing,
  CheckCheck,
  CirclePause,
  CirclePlay,
  LoaderCircle,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api";
import { trapFocus } from "../focus";
import type { AlertItem, AlertTriggerItem, WatchlistItem } from "../types";
import { useWatchlist } from "./WatchlistContext";
import { classNames, formatDateTime } from "./UI";

const METRICS = {
  bond: [
    ["yield", "收益率"],
    ["price", "净价"],
    ["change_bp", "变动 BP"],
  ],
  future: [
    ["price", "期货价格"],
    ["change_pct", "涨跌幅"],
    ["volume", "成交量"],
    ["open_interest", "持仓量"],
  ],
  convertible: [
    ["price", "转债价格"],
    ["change_pct", "涨跌幅"],
    ["premium_pct", "转股溢价率"],
    ["double_low", "双低值"],
    ["ytm_pct", "到期收益率"],
  ],
} as const;

const METRIC_LABELS = Object.fromEntries(
  Object.values(METRICS).flat().map(([value, label]) => [value, label]),
);

const METRIC_UNITS: Record<string, string> = {
  yield: "%",
  change_bp: "BP",
  change_pct: "%",
  premium_pct: "%",
  ytm_pct: "%",
  price: "价格",
  double_low: "双低值",
  volume: "手",
  open_interest: "手",
};

type AlertableWatchItem = WatchlistItem & {
  object_type: keyof typeof METRICS;
};

function isAlertableWatchItem(item: WatchlistItem): item is AlertableWatchItem {
  return item.object_type in METRICS;
}

interface AlertPreview {
  available: boolean;
  matched: boolean;
  value: number | null;
  message: string;
  observation_time?: string | null;
  source?: string;
}

export function AlertsPanel({
  open,
  onClose,
  onUnreadChange,
}: {
  open: boolean;
  onClose: () => void;
  onUnreadChange: (count: number) => void;
}) {
  const { items: watchlist } = useWatchlist();
  const [rules, setRules] = useState<AlertItem[]>([]);
  const [history, setHistory] = useState<AlertTriggerItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [targetKey, setTargetKey] = useState("");
  const [metric, setMetric] = useState("yield");
  const [operator, setOperator] = useState(">");
  const [threshold, setThreshold] = useState("");
  const [maxPerDay, setMaxPerDay] = useState("3");
  const [quietEnabled, setQuietEnabled] = useState(false);
  const [quietStart, setQuietStart] = useState("22:00");
  const [quietEnd, setQuietEnd] = useState("08:00");
  const [preview, setPreview] = useState<AlertPreview | null>(null);
  const drawerRef = useRef<HTMLElement>(null);

  const alertableWatchlist = useMemo(
    () => watchlist.filter(isAlertableWatchItem),
    [watchlist],
  );

  const target = useMemo(
    () =>
      alertableWatchlist.find((item) => String(item.id) === targetKey) ??
      alertableWatchlist[0],
    [alertableWatchlist, targetKey],
  );
  const metricOptions = target ? METRICS[target.object_type] : METRICS.bond;

  useEffect(() => {
    if (!target) return;
    if (targetKey !== String(target.id)) setTargetKey(String(target.id));
    if (!metricOptions.some(([value]) => value === metric)) {
      setMetric(metricOptions[0][0]);
    }
  }, [metric, metricOptions, target, targetKey]);

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([
      apiGet<AlertItem[]>("/alerts"),
      apiGet<AlertTriggerItem[]>("/alerts/history?limit=100"),
      apiGet<{ count: number }>("/alerts/unread-count"),
    ])
      .then(([nextRules, nextHistory, unread]) => {
        setRules(nextRules);
        setHistory(nextHistory);
        onUnreadChange(unread.count);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "提醒加载失败"),
      )
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (open) {
      load();
      window.setTimeout(() => drawerRef.current?.focus(), 20);
    }
  }, [open]);

  async function createRule(event: FormEvent) {
    event.preventDefault();
    if (!target || !threshold) return;
    setSaving(true);
    setError(null);
    try {
      await apiPost<AlertItem>("/alerts", rulePayload());
      setThreshold("");
      setPreview(null);
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "提醒保存失败");
    } finally {
      setSaving(false);
    }
  }

  function rulePayload() {
    if (!target) throw new Error("请选择自选标的");
    return {
      object_type: target.object_type,
      object_id: target.object_id,
      name: target.name + " · " + (METRIC_LABELS[metric] ?? metric),
      metric,
      operator,
      threshold: Number(threshold),
      cooldown_minutes: 30,
      max_triggers_per_day: Number(maxPerDay),
      quiet_start: quietEnabled ? quietStart : null,
      quiet_end: quietEnabled ? quietEnd : null,
      enabled: true,
    };
  }

  async function previewRule() {
    if (!target || !threshold) return;
    setSaving(true);
    setError(null);
    try {
      setPreview(await apiPost<AlertPreview>("/alerts/preview", rulePayload()));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "提醒试算失败");
    } finally {
      setSaving(false);
    }
  }

  async function toggleRule(rule: AlertItem) {
    setError(null);
    try {
      const updated = await apiPatch<AlertItem>("/alerts/" + rule.id, {
        enabled: !rule.enabled,
      });
      setRules((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "提醒状态更新失败");
    }
  }

  async function deleteRule(ruleId: number) {
    setError(null);
    try {
      await apiDelete("/alerts/" + ruleId);
      setRules((current) => current.filter((item) => item.id !== ruleId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "提醒删除失败");
    }
  }

  async function markRead() {
    setError(null);
    try {
      await apiPost<{ updated: number }>("/alerts/history/read");
      setHistory((current) => current.map((item) => ({ ...item, read: true })));
      onUnreadChange(0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "提醒历史更新失败");
    }
  }

  if (!open) return null;

  return (
    <>
      <button className="drawer-scrim" onClick={onClose} aria-label="关闭提醒面板" />
      <aside
        ref={drawerRef}
        id="alert-drawer"
        className="alert-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="alert-drawer-title"
        tabIndex={-1}
        onKeyDown={(event) => trapFocus(event, drawerRef.current)}
      >
        <header className="drawer-header">
          <div>
            <span className="eyebrow">LOCAL ALERTS</span>
            <h2 id="alert-drawer-title">提醒中心</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="关闭提醒中心">
            <X size={17} />
          </button>
        </header>

        <div className="drawer-content">
          <section className="alert-section">
            <div className="drawer-section-title">
              <h3>新建提醒</h3>
              <span>仅使用健康数据，在条件首次满足或重新穿越时触发</span>
            </div>
            {alertableWatchlist.length ? (
              <form className="alert-form" onSubmit={createRule}>
                <label>
                  <span>自选标的</span>
                  <select value={targetKey} onChange={(event) => setTargetKey(event.target.value)}>
                    {alertableWatchlist.map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.name} · {item.object_id}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="alert-form-row">
                  <label>
                    <span>指标</span>
                    <select value={metric} onChange={(event) => setMetric(event.target.value)}>
                      {metricOptions.map(([value, label]) => (
                        <option value={value} key={value}>{label}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>条件</span>
                    <select value={operator} onChange={(event) => setOperator(event.target.value)}>
                      <option value=">">大于</option>
                      <option value=">=">大于等于</option>
                      <option value="<">小于</option>
                      <option value="<=">小于等于</option>
                    </select>
                  </label>
                  <label>
                    <span>阈值（{METRIC_UNITS[metric] ?? "数值"}）</span>
                    <input
                      type="number"
                      step="any"
                      required
                      value={threshold}
                      onChange={(event) => setThreshold(event.target.value)}
                    />
                  </label>
                </div>
                <div className="alert-form-row alert-policy-row">
                  <label>
                    <span>每日最多触发</span>
                    <input
                      type="number"
                      min="1"
                      max="50"
                      value={maxPerDay}
                      onChange={(event) => setMaxPerDay(event.target.value)}
                    />
                  </label>
                  <label className="quiet-toggle">
                    <span>静默时段</span>
                    <input
                      type="checkbox"
                      checked={quietEnabled}
                      onChange={(event) => setQuietEnabled(event.target.checked)}
                    />
                  </label>
                  <label>
                    <span>开始</span>
                    <input type="time" value={quietStart} disabled={!quietEnabled} onChange={(event) => setQuietStart(event.target.value)} />
                  </label>
                  <label>
                    <span>结束</span>
                    <input type="time" value={quietEnd} disabled={!quietEnabled} onChange={(event) => setQuietEnd(event.target.value)} />
                  </label>
                </div>
                {preview ? (
                  <div
                    className={classNames("alert-preview", preview.available && preview.matched && "matched")}
                    role="status"
                    aria-live="polite"
                  >
                    <strong>{preview.message}</strong>
                    <span>{preview.available ? `当前值 ${preview.value ?? "—"}` : "不会触发提醒"}</span>
                  </div>
                ) : null}
                <div className="alert-form-actions">
                  <button className="secondary-button" type="button" onClick={previewRule} disabled={saving || !threshold}>
                    试算当前值
                  </button>
                  <button className="primary-button" type="submit" disabled={saving}>
                    {saving ? <LoaderCircle className="spin" size={15} /> : <Plus size={15} />}
                    创建提醒
                  </button>
                </div>
              </form>
            ) : (
              <p className="drawer-empty">先在现券、期货或可转债页面加入自选，再创建行情提醒；宏观指标暂不支持阈值提醒。</p>
            )}
          </section>

          <section className="alert-section">
            <div className="drawer-section-title">
              <h3>提醒规则</h3>
              <span>{rules.length} 条</span>
            </div>
            {loading ? <LoaderCircle className="spin drawer-loader" size={20} /> : null}
            {!loading && !rules.length ? <p className="drawer-empty">还没有提醒规则。</p> : null}
            <div className="alert-rule-list">
              {rules.map((rule) => (
                <article className={classNames("alert-rule", !rule.enabled && "disabled")} key={rule.id}>
                  <div>
                    <strong>{rule.name}</strong>
                    <span>
                      {METRIC_LABELS[rule.metric] ?? rule.metric} {rule.operator} {rule.threshold}
                    </span>
                    <small>
                      {rule.last_evaluated_at
                        ? `最近判断 ${rule.last_value ?? "—"} · ${rule.last_matched ? "条件满足" : "条件未满足"} · ${formatDateTime(rule.last_evaluated_at)}`
                        : "等待下一次健康行情评估"}
                    </small>
                    <small>
                      每日最多 {rule.max_triggers_per_day} 次
                      {rule.quiet_start && rule.quiet_end ? ` · ${rule.quiet_start}–${rule.quiet_end} 静默` : ""}
                    </small>
                  </div>
                  <button className="icon-button" onClick={() => toggleRule(rule)} aria-label={rule.enabled ? "暂停提醒" : "启用提醒"}>
                    {rule.enabled ? <CirclePause size={15} /> : <CirclePlay size={15} />}
                  </button>
                  <button className="icon-button danger" onClick={() => deleteRule(rule.id)} aria-label="删除提醒">
                    <Trash2 size={15} />
                  </button>
                </article>
              ))}
            </div>
          </section>

          <section className="alert-section">
            <div className="drawer-section-title">
              <h3>触发历史</h3>
              <button className="text-button" onClick={markRead} disabled={!history.some((item) => !item.read)}>
                <CheckCheck size={14} /> 全部已读
              </button>
            </div>
            {!history.length ? <p className="drawer-empty">尚无触发记录。</p> : null}
            <div className="trigger-list">
              {history.map((item) => (
                <article className={classNames("trigger-item", !item.read && "unread")} key={item.id}>
                  <BellRing size={15} />
                  <div>
                    <strong>{item.name}</strong>
                    <span>触发值 {item.trigger_value} · 阈值 {item.operator} {item.threshold}</span>
                    <small>{formatDateTime(item.triggered_at)} · {item.source}</small>
                  </div>
                </article>
              ))}
            </div>
          </section>
          {error ? <p className="drawer-error" role="alert">{error}</p> : null}
        </div>
      </aside>
    </>
  );
}
