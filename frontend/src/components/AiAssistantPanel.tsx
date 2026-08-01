import {
  Bot,
  CheckCircle2,
  Clipboard,
  ExternalLink,
  KeyRound,
  LoaderCircle,
  Settings2,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiDelete, apiGet, apiPatch, apiPost } from "../api";
import type { AiAssistantOpenDetail } from "../aiBridge";
import {
  AI_QUESTION_SUGGESTIONS,
  AI_SCENARIO_LABELS,
  aiContextPreview,
  buildAiAssistantRequest,
  type AiScenario,
} from "../aiAssistant";
import { trapFocus } from "../focus";
import type { ResearchProject } from "../types";
import { AiAnswerText } from "./AiAnswerText";
import { classNames, formatDateTime } from "./UI";

interface AiStatus {
  provider: "AIHubMix";
  configured: boolean;
  verified: boolean;
  verification_state: "not_configured" | "unverified" | "verified";
  credential_source: "environment" | "keychain" | "none" | string;
  model: string;
  model_label: string;
  endpoint: string;
  last_verified_at?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  storage_mode: string;
  key_storage: string;
  terms_url: string;
  privacy_url: string;
  data_notice: string;
  persistence_notice: string;
  runtime: AiRuntimeStatus;
}

type AiInsightContext = "market" | "project" | "credit" | "topic";
type AiInsightTrigger = "manual" | "data_change" | "daily";

interface AiRuntimeSettings {
  daily_call_limit: number;
  daily_token_limit: number;
  page_insights: Record<
    AiInsightContext,
    { enabled: boolean; trigger: AiInsightTrigger }
  >;
}

interface AiRuntimeStatus {
  settings: AiRuntimeSettings;
  usage: {
    usage_date: string;
    calls: number;
    total_tokens: number;
    calls_remaining: number;
    tokens_remaining: number;
    limit_reached: boolean;
  };
  task_state: "idle" | "queued" | "running";
  active_requests: number;
  queue_depth: number;
  concurrency_limit: number;
  persistence: {
    usage: string;
    insights: string;
    excluded: string;
  };
}

interface AiAssistantResponse {
  answer: string;
  provider: string;
  model: string;
  model_label: string;
  scenario: AiScenario;
  generated_at: string;
  usage: {
    prompt_tokens?: number | null;
    completion_tokens?: number | null;
    total_tokens?: number | null;
  };
  context_summary: string[];
  persisted: false;
  disclaimer: string;
}

export function AiAssistantPanel({
  open,
  onClose,
  currentPage,
  seed,
}: {
  open: boolean;
  onClose: () => void;
  currentPage: string;
  seed?: AiAssistantOpenDetail | null;
}) {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [runtimeDraft, setRuntimeDraft] = useState<AiRuntimeSettings | null>(null);
  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [scenario, setScenario] = useState<AiScenario>("help");
  const [projectId, setProjectId] = useState<number | null>(null);
  const [question, setQuestion] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [keyNoticeAccepted, setKeyNoticeAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [answer, setAnswer] = useState<AiAssistantResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [runtimeNotice, setRuntimeNotice] = useState<string | null>(null);
  const [runtimeOpen, setRuntimeOpen] = useState(false);
  const drawerRef = useRef<HTMLElement>(null);
  const runtimeRef = useRef<HTMLDetailsElement>(null);

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([
      apiGet<AiStatus>("/ai/status"),
      apiGet<ResearchProject[]>("/research/projects"),
    ])
      .then(([nextStatus, nextProjects]) => {
        setStatus(nextStatus);
        setRuntimeDraft(nextStatus.runtime.settings);
        setProjects(nextProjects);
        setProjectId((current) =>
          current && nextProjects.some((project) => project.id === current)
            ? current
            : nextProjects.find((project) => project.status !== "archived")?.id ??
              nextProjects[0]?.id ??
              null,
        );
        window.setTimeout(() => drawerRef.current?.focus(), 0);
        if (seed?.focusRuntimeSettings) {
          window.setTimeout(() => {
            runtimeRef.current?.scrollIntoView({ block: "start" });
            runtimeRef.current?.querySelector("summary")?.focus();
          }, 30);
        }
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "AI 助手状态加载失败"),
      )
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (open) {
      if (seed) {
        setScenario(seed.scenario);
        setQuestion(seed.question ?? "");
        setProjectId(seed.projectId ?? null);
        setRuntimeOpen(Boolean(seed.focusRuntimeSettings));
      }
      load();
      window.setTimeout(() => drawerRef.current?.focus(), 20);
    } else {
      setAnswer(null);
      setQuestion("");
      setConfirmed(false);
      setError(null);
      setCopied(false);
      setRuntimeNotice(null);
      setRuntimeOpen(false);
    }
  }, [open, seed]);

  async function saveKey(event: FormEvent) {
    event.preventDefault();
    if (!apiKey || !keyNoticeAccepted) return;
    setSaving(true);
    setError(null);
    setRuntimeNotice(null);
    try {
      const nextStatus = await apiPost<AiStatus>(
        "/settings/integrations/aihubmix",
        { api_key: apiKey },
      );
      setStatus(nextStatus);
      setApiKey("");
      setKeyNoticeAccepted(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AIHubMix Key 保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function testConnection() {
    setSaving(true);
    setError(null);
    try {
      setStatus(await apiPost<AiStatus>("/settings/integrations/aihubmix/test"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AIHubMix 连接验证失败");
    } finally {
      setSaving(false);
    }
  }

  async function deleteKey() {
    if (!window.confirm("确认从 macOS Keychain 删除 AIHubMix API Key？")) return;
    setSaving(true);
    setError(null);
    try {
      await apiDelete("/settings/integrations/aihubmix");
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AIHubMix Key 删除失败");
    } finally {
      setSaving(false);
    }
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || !confirmed) return;
    setSaving(true);
    setError(null);
    setAnswer(null);
    setCopied(false);
    try {
      const result = await apiPost<AiAssistantResponse>(
        "/ai/assistant",
        buildAiAssistantRequest({
          scenario,
          question,
          projectId,
          currentPage,
          confirmed,
        }),
        {
          timeoutMs: 85_000,
          timeoutMessage:
            "AI 请求超过 85 秒仍未完成，已停止等待；本次问答没有保存，请稍后重试。",
        },
      );
      setAnswer(result);
      const nextStatus = await apiGet<AiStatus>("/ai/status");
      setStatus(nextStatus);
      setRuntimeDraft(nextStatus.runtime.settings);
      setConfirmed(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AI 助手请求失败");
    } finally {
      setSaving(false);
    }
  }

  async function copyAnswer() {
    if (!answer) return;
    await navigator.clipboard.writeText(answer.answer);
    setCopied(true);
  }

  async function saveRuntimeSettings() {
    if (!runtimeDraft) return;
    setSaving(true);
    setError(null);
    setRuntimeNotice(null);
    try {
      const runtime = await apiPatch<AiRuntimeStatus>("/ai/runtime", runtimeDraft);
      setRuntimeDraft(runtime.settings);
      setStatus((current) => (current ? { ...current, runtime } : current));
      setRuntimeNotice("AI 运行设置已保存。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AI 运行设置保存失败");
    } finally {
      setSaving(false);
    }
  }

  if (!open) return null;
  const preview = aiContextPreview(scenario, Boolean(projectId));

  return (
    <>
      <button className="drawer-scrim" onClick={onClose} aria-label="关闭 AI 助手" />
      <aside
        ref={drawerRef}
        id="ai-assistant-drawer"
        className="alert-drawer ai-assistant-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ai-assistant-title"
        tabIndex={-1}
        onKeyDown={(event) => trapFocus(event, drawerRef.current)}
      >
        <header className="drawer-header">
          <div>
            <span className="eyebrow">BYOK · CONTROLLED</span>
            <h2 id="ai-assistant-title">AI 研究助手</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="关闭 AI 助手">
            <X size={17} />
          </button>
        </header>

        <div className="drawer-content ai-assistant-content">
          {loading ? <div className="ai-loading"><LoaderCircle className="spin" size={18} /> 正在读取配置</div> : null}

          {status ? (
            <section className="ai-provider-card">
              <div>
                <span className={classNames("ai-provider-icon", status.verified && "verified")}><Bot size={18} /></span>
                <div>
                  <strong>{status.model_label}</strong>
                  <small>{status.provider} · {status.model}</small>
                </div>
              </div>
              <span className={classNames("tag", status.verified ? "healthy-tag" : "warning")}>
                {status.verified ? "已验证" : status.configured ? "待验证" : "未配置"}
              </span>
              <p>{status.persistence_notice}</p>
              <div className="ai-provider-links">
                <a href={status.terms_url} target="_blank" rel="noreferrer">服务条款 <ExternalLink size={11} /></a>
                <a href={status.privacy_url} target="_blank" rel="noreferrer">隐私说明 <ExternalLink size={11} /></a>
              </div>
            </section>
          ) : null}

          {status && !status.configured ? (
            <section className="ai-setup-card">
              <div className="drawer-section-title">
                <h3>配置个人 API Key</h3>
                <KeyRound size={16} />
              </div>
              <p>Key 验证成功后只保存到 macOS Keychain；AKDesk 不显示、导出或写入数据库。</p>
              <form onSubmit={saveKey}>
                <label>
                  <span>AIHubMix API Key</span>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    placeholder="sk-…"
                    autoComplete="new-password"
                    required
                  />
                </label>
                <label className="ai-consent">
                  <input type="checkbox" checked={keyNoticeAccepted} onChange={(event) => setKeyNoticeAccepted(event.target.checked)} />
                  <span>我理解调用会产生第三方费用，并受 AIHubMix 与底层模型提供方条款约束。</span>
                </label>
                <button className="primary-button" disabled={saving || !apiKey || !keyNoticeAccepted}>
                  {saving ? <LoaderCircle className="spin" size={14} /> : <ShieldCheck size={14} />}
                  验证并保存
                </button>
              </form>
            </section>
          ) : null}

          {status?.configured ? (
            <>
              <section className="ai-scenario-card">
                <div className="ai-scenario-tabs" role="tablist" aria-label="AI 助手场景">
                  {(Object.keys(AI_SCENARIO_LABELS) as AiScenario[]).map((item) => (
                    <button
                      type="button"
                      role="tab"
                      aria-selected={scenario === item}
                      className={scenario === item ? "active" : undefined}
                      onClick={() => {
                        setScenario(item);
                        setAnswer(null);
                        setConfirmed(false);
                      }}
                      key={item}
                    >
                      {AI_SCENARIO_LABELS[item]}
                    </button>
                  ))}
                </div>

                <form className="ai-question-form" onSubmit={ask}>
                  {scenario === "research" ? (
                    <label>
                      <span>研究项目</span>
                      <select value={projectId ?? ""} onChange={(event) => setProjectId(event.target.value ? Number(event.target.value) : null)}>
                        <option value="">仅使用项目概览</option>
                        {projects.map((project) => <option value={project.id} key={project.id}>{project.title}</option>)}
                      </select>
                    </label>
                  ) : null}

                  <div className="ai-question-suggestions">
                    {AI_QUESTION_SUGGESTIONS[scenario].map((suggestion) => (
                      <button type="button" onClick={() => setQuestion(suggestion)} key={suggestion}>{suggestion}</button>
                    ))}
                  </div>

                  <label>
                    <span>你想让助手帮助什么？</span>
                    <textarea
                      value={question}
                      onChange={(event) => setQuestion(event.target.value)}
                      maxLength={1200}
                      placeholder="AI 只会基于发送前预览中的本地上下文回答…"
                      required
                    />
                    <small>{question.length}/1200</small>
                  </label>

                  <details className="ai-context-preview" open>
                    <summary>发送前预览</summary>
                    <ul>{preview.map((item) => <li key={item}>{item}</li>)}</ul>
                    <p>不会发送 API Key、SQLite 文件、附件正文、新闻正文或完整行情表。</p>
                  </details>

                  <label className="ai-consent">
                    <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                    <span>我确认将本次问题和以上裁剪上下文发送给 AIHubMix。</span>
                  </label>

                  <button className="primary-button ai-send-button" disabled={saving || !question.trim() || !confirmed}>
                    {saving ? <LoaderCircle className="spin" size={15} /> : <Send size={15} />}
                    {saving ? "正在生成，请勿重复提交" : "发送给 AI 助手"}
                  </button>
                </form>
              </section>

              {answer ? (
                <section className="ai-answer-card" aria-live="polite">
                  <header>
                    <div><Sparkles size={16} /><strong>{AI_SCENARIO_LABELS[answer.scenario]}回答</strong></div>
                    <button className="text-button" onClick={copyAnswer}><Clipboard size={13} /> {copied ? "已复制" : "复制"}</button>
                  </header>
                  <AiAnswerText text={answer.answer} />
                  <footer>
                    <span>{answer.model_label}</span>
                    <span>{formatDateTime(answer.generated_at)}</span>
                    {answer.usage.total_tokens != null ? <span>{answer.usage.total_tokens} tokens</span> : null}
                  </footer>
                  <p>{answer.disclaimer}</p>
                </section>
              ) : null}

              {runtimeDraft && status.runtime ? (
                <details
                  ref={runtimeRef}
                  className="ai-key-maintenance ai-runtime-settings"
                  open={runtimeOpen}
                  onToggle={(event) => setRuntimeOpen(event.currentTarget.open)}
                >
                  <summary><Settings2 size={14} /> 预算与页面洞察</summary>
                  <div>
                    <div className="ai-runtime-usage">
                      <span>
                        今日调用
                        <strong>{status.runtime.usage.calls}/{runtimeDraft.daily_call_limit}</strong>
                      </span>
                      <span>
                        今日 tokens
                        <strong>{status.runtime.usage.total_tokens.toLocaleString()}/{runtimeDraft.daily_token_limit.toLocaleString()}</strong>
                      </span>
                      <span>
                        任务状态
                        <strong>
                          {status.runtime.task_state === "running"
                            ? "生成中"
                            : status.runtime.task_state === "queued"
                              ? `排队 ${status.runtime.queue_depth}`
                              : "空闲"}
                        </strong>
                      </span>
                    </div>
                    <div className="ai-budget-fields">
                      <label>
                        <span>每日调用上限</span>
                        <input
                          type="number"
                          min={1}
                          max={200}
                          value={runtimeDraft.daily_call_limit}
                          onChange={(event) =>
                            setRuntimeDraft({
                              ...runtimeDraft,
                              daily_call_limit: Number(event.target.value),
                            })
                          }
                        />
                      </label>
                      <label>
                        <span>每日 token 预算</span>
                        <input
                          type="number"
                          min={1000}
                          max={2000000}
                          step={1000}
                          value={runtimeDraft.daily_token_limit}
                          onChange={(event) =>
                            setRuntimeDraft({
                              ...runtimeDraft,
                              daily_token_limit: Number(event.target.value),
                            })
                          }
                        />
                      </label>
                    </div>
                    <fieldset className="ai-insight-policies">
                      <legend>页面洞察授权</legend>
                      {([
                        ["market", "今日市场"],
                        ["project", "研究项目"],
                        ["credit", "信用观察"],
                        ["topic", "专题综述"],
                      ] as const).map(([context, label]) => {
                        const policy = runtimeDraft.page_insights[context];
                        return (
                          <div key={context}>
                            <label className="ai-insight-toggle">
                              <input
                                type="checkbox"
                                checked={policy.enabled}
                                onChange={(event) =>
                                  setRuntimeDraft({
                                    ...runtimeDraft,
                                    page_insights: {
                                      ...runtimeDraft.page_insights,
                                      [context]: {
                                        ...policy,
                                        enabled: event.target.checked,
                                      },
                                    },
                                  })
                                }
                              />
                              <span>{label}</span>
                            </label>
                            <select
                              aria-label={`${label}触发方式`}
                              value={policy.trigger}
                              disabled={!policy.enabled}
                              onChange={(event) =>
                                setRuntimeDraft({
                                  ...runtimeDraft,
                                  page_insights: {
                                    ...runtimeDraft.page_insights,
                                    [context]: {
                                      ...policy,
                                      trigger: event.target.value as AiInsightTrigger,
                                    },
                                  },
                                })
                              }
                            >
                              <option value="manual">仅手动</option>
                              <option value="data_change">数据变化后</option>
                              <option value="daily">每日首次打开</option>
                            </select>
                          </div>
                        );
                      })}
                    </fieldset>
                    <p>{status.runtime.persistence.excluded}</p>
                    {runtimeNotice ? (
                      <p className="ai-runtime-notice" role="status">
                        {runtimeNotice}
                      </p>
                    ) : null}
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={saveRuntimeSettings}
                      disabled={saving}
                    >
                      保存运行设置
                    </button>
                  </div>
                </details>
              ) : null}

              <details className="ai-key-maintenance">
                <summary>连接与密钥管理</summary>
                <div>
                  <span>凭据来源：{status.credential_source === "keychain" ? "macOS Keychain" : "环境变量"}</span>
                  {status.last_verified_at ? <small>最近验证 {formatDateTime(status.last_verified_at)}</small> : null}
                  <button className="secondary-button" type="button" onClick={testConnection} disabled={saving}>
                    <CheckCircle2 size={13} /> 测试连接
                  </button>
                  {status.credential_source === "keychain" ? (
                    <button className="text-button danger-text" type="button" onClick={deleteKey} disabled={saving}>
                      <Trash2 size={13} /> 删除 Key
                    </button>
                  ) : null}
                </div>
              </details>
            </>
          ) : null}

          {error ? (
            <div className="drawer-error ai-recovery-error" role="alert">
              <p>{error}</p>
              {!status ? (
                <button className="secondary-button" type="button" onClick={load}>
                  重新连接本地服务
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </aside>
    </>
  );
}
