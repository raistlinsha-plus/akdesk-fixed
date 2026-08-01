import {
  LoaderCircle,
  LockKeyhole,
  MessageCircleMore,
  RefreshCcw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiDelete, apiGet, apiPost } from "../api";
import { openAiAssistant } from "../aiBridge";
import {
  AI_INSIGHT_STATUS_LABELS,
  AI_INSIGHT_TRIGGER_LABELS,
  aiInsightPath,
  shouldAutoGenerate,
  type AiInsightContext,
  type AiInsightResponse,
  type AiInsightTrigger,
} from "../aiInsights";
import { AiAnswerText } from "./AiAnswerText";
import { classNames, formatDateTime } from "./UI";

const scenarioByContext = {
  market: "market",
  project: "research",
  credit: "research",
  topic: "research",
} as const;

const followUpByContext = {
  market: "基于当前页面洞察，哪些不确定性最值得继续验证？",
  project: "基于当前项目洞察，帮我把下一步验证拆成可执行清单。",
  credit: "基于当前信用观察洞察，哪些信号需要优先人工复核？",
  topic: "基于当前专题综述，把下一步跨源核验拆成可执行清单。",
};

export function AiInsightCard({
  contextType,
  projectId,
  topicId,
  title,
  description,
  revision,
}: {
  contextType: AiInsightContext;
  projectId?: number | null;
  topicId?: number | null;
  title: string;
  description: string;
  revision?: string | number | null;
}) {
  const [insight, setInsight] = useState<AiInsightResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const attemptedFingerprint = useRef<string | null>(null);
  const path = aiInsightPath(contextType, projectId, topicId);

  async function generate(
    triggerReason: AiInsightTrigger = "manual",
    force = false,
  ) {
    setSubmitting(true);
    setError(null);
    try {
      const next = await apiPost<AiInsightResponse>(path, {
        project_id: contextType === "project" ? projectId : null,
        topic_id: contextType === "topic" ? topicId : null,
        trigger_reason: triggerReason,
        force,
        confirm_external_processing: true,
      });
      setInsight(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AI 页面洞察生成失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function load(allowAuto = true) {
    setError(null);
    try {
      const next = await apiGet<AiInsightResponse>(path);
      setInsight(next);
      if (
        allowAuto &&
        shouldAutoGenerate(next, attemptedFingerprint.current)
      ) {
        attemptedFingerprint.current = next.context_fingerprint;
        await generate(next.policy.trigger);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AI 页面洞察状态加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    attemptedFingerprint.current = null;
    setInsight(null);
    setLoading(true);
    void load();
  }, [contextType, path, revision]);

  useEffect(() => {
    const polling = Boolean(insight && insight.job_state !== "idle");
    if (!polling) return;
    const timer = window.setInterval(() => void load(false), 1_500);
    return () => window.clearInterval(timer);
  }, [Boolean(insight && insight.job_state !== "idle"), path]);

  function manageSettings() {
    openAiAssistant({
      scenario: scenarioByContext[contextType],
      projectId,
      focusRuntimeSettings: true,
    });
  }

  function continueAsking() {
    openAiAssistant({
      scenario: scenarioByContext[contextType],
      projectId,
      question: followUpByContext[contextType],
    });
  }

  async function clearInsight() {
    if (!window.confirm("清除本机缓存的这条 AI 最终摘要？该操作不会删除任何业务数据。")) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiDelete(path);
      await load(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "AI 页面洞察清除失败");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading && !insight) {
    return (
      <section className="ai-insight-card is-loading" aria-label={title}>
        <LoaderCircle className="spin" size={18} />
        <div><strong>正在读取 AI 洞察状态</strong><p>页面规则与数据不受影响。</p></div>
      </section>
    );
  }

  if (!insight) {
    return (
      <section className="ai-insight-card is-error" aria-label={title}>
        <TriangleAlert size={18} />
        <div><strong>AI 洞察暂不可用</strong><p>{error}</p></div>
        <button className="secondary-button" type="button" onClick={() => void load()}>
          重试
        </button>
      </section>
    );
  }

  const generating = insight.job_state !== "idle" || insight.status === "generating";
  const hasSummary = Boolean(insight.summary.trim());
  const moduleUsage =
    insight.usage.by_context?.[`${contextType}_insight`] ??
    insight.usage.by_context?.[contextType];

  return (
    <section
      className={classNames(
        "ai-insight-card",
        `status-${insight.status}`,
        !insight.policy.enabled && "is-locked",
      )}
      aria-labelledby={`ai-insight-title-${contextType}`}
    >
      <header>
        <div className="ai-insight-heading">
          <span className="ai-insight-icon">
            {insight.policy.enabled ? <Sparkles size={17} /> : <LockKeyhole size={17} />}
          </span>
          <div>
            <span className="eyebrow">PAGE INSIGHT · BYOK</span>
            <h2 id={`ai-insight-title-${contextType}`}>{title}</h2>
            <p>{description}</p>
          </div>
        </div>
        <div className="ai-insight-state">
          <span className={classNames("tag", insight.status)}>
            {generating ? "生成中" : AI_INSIGHT_STATUS_LABELS[insight.status]}
          </span>
          {insight.policy.enabled ? (
            <small>{AI_INSIGHT_TRIGGER_LABELS[insight.policy.trigger]}</small>
          ) : null}
        </div>
      </header>

      {!insight.policy.enabled ? (
        <div className="ai-insight-locked">
          <div>
            <strong>本页 AI 洞察默认关闭</strong>
            <p>开启后才会把下方预览中的裁剪摘要提交给 AIHubMix；原有页面功能完全不依赖 AI。</p>
          </div>
          <button className="secondary-button" type="button" onClick={manageSettings}>
            <Settings2 size={14} /> 管理权限
          </button>
        </div>
      ) : (
        <>
          {hasSummary ? (
            <div className="ai-insight-answer" aria-live="polite">
              {generating ? (
                <div className="ai-insight-refreshing">
                  <LoaderCircle className="spin" size={14} />
                  正在更新；更新完成前继续显示上次摘要
                </div>
              ) : null}
              <AiAnswerText text={insight.summary} />
            </div>
          ) : (
            <div className="ai-insight-empty">
              {generating ? (
                <LoaderCircle className="spin" size={20} />
              ) : (
                <ShieldCheck size={20} />
              )}
              <div>
                <strong>{generating ? "正在生成本页洞察" : "尚未生成本页洞察"}</strong>
                <p>生成不会修改行情、项目、信用记录或研究结论。</p>
              </div>
            </div>
          )}

          {insight.status === "failed" && insight.last_error ? (
            <p className="ai-insight-error" role="alert">{insight.last_error}</p>
          ) : null}
          {error ? <p className="ai-insight-error" role="alert">{error}</p> : null}

          <footer>
            <div className="ai-insight-meta">
              {insight.generated_at ? <span>生成于 {formatDateTime(insight.generated_at)}</span> : null}
              <span>{insight.model_label}</span>
              {moduleUsage ? (
                <span>本模块今日 {moduleUsage.calls} 次 / {moduleUsage.total_tokens.toLocaleString()} tokens</span>
              ) : null}
              <span>今日剩余 {insight.usage.calls_remaining} 次</span>
            </div>
            <div className="ai-insight-actions">
              <button
                className="secondary-button"
                type="button"
                disabled={submitting || generating || !insight.can_generate}
                onClick={() => void generate("manual", hasSummary)}
              >
                {submitting || generating ? (
                  <LoaderCircle className="spin" size={14} />
                ) : (
                  <RefreshCcw size={14} />
                )}
                {hasSummary
                  ? "刷新洞察"
                  : insight.status === "failed"
                    ? "重试生成"
                    : "生成洞察"}
              </button>
              {hasSummary ? (
                <button className="text-button" type="button" onClick={continueAsking}>
                  <MessageCircleMore size={14} /> 继续追问
                </button>
              ) : null}
              {hasSummary ? (
                <button
                  className="text-button danger-text"
                  type="button"
                  disabled={submitting || generating}
                  onClick={() => void clearInsight()}
                >
                  <Trash2 size={13} /> 清除摘要
                </button>
              ) : null}
              <button className="text-button" type="button" onClick={manageSettings}>
                <Settings2 size={13} /> 设置
              </button>
            </div>
          </footer>
        </>
      )}

      <details className="ai-insight-preview">
        <summary>发送范围与本地保存</summary>
        <ul>{insight.context_summary.map((item) => <li key={item}>{item}</li>)}</ul>
        <p>{insight.persistence_notice}</p>
      </details>
    </section>
  );
}
