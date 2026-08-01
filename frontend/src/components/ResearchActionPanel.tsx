import { useEffect, useState } from "react";
import {
  CheckCheck,
  ListTodo,
  LoaderCircle,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { apiGet, apiPost } from "../api";
import type {
  ResearchActionDraft,
  ResearchActionDraftResponse,
} from "../types";
import { classNames, formatDateTime } from "./UI";

const actionCopy = {
  task: "任务",
  counter_evidence: "反证",
  review: "复盘",
};

export function ResearchActionPanel({
  projectId,
  revision,
  onProjectChanged,
}: {
  projectId: number;
  revision: string;
  onProjectChanged: () => void;
}) {
  const [result, setResult] = useState<ResearchActionDraftResponse | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load() {
    apiGet<ResearchActionDraftResponse>(
      `/research/projects/${projectId}/action-drafts`,
    )
      .then(setResult)
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "行动建议读取失败"));
  }

  useEffect(() => {
    setSelected([]);
    setError(null);
    load();
  }, [projectId, revision]);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const next = await apiPost<ResearchActionDraftResponse>(
        `/research/projects/${projectId}/action-drafts/generate`,
      );
      setResult(next);
      setSelected(next.items.filter((item) => item.status === "proposed").map((item) => item.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "行动建议生成失败");
    } finally {
      setBusy(false);
    }
  }

  async function accept() {
    if (!selected.length) return;
    if (!window.confirm(`确认把选中的 ${selected.length} 条建议写入研究记录？写入后仍可在这里撤销。`)) return;
    setBusy(true);
    setError(null);
    try {
      const next = await apiPost<ResearchActionDraftResponse>(
        `/research/projects/${projectId}/action-drafts/accept`,
        { draft_ids: selected, confirm: true },
      );
      setResult(next);
      setSelected([]);
      onProjectChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "行动建议采纳失败");
    } finally {
      setBusy(false);
    }
  }

  async function undo(draft: ResearchActionDraft) {
    if (!window.confirm(`撤销“${draft.title}”并删除对应研究记录？`)) return;
    setBusy(true);
    setError(null);
    try {
      const next = await apiPost<ResearchActionDraftResponse>(
        `/research/projects/${projectId}/action-drafts/${draft.id}/undo`,
      );
      setResult(next);
      onProjectChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "行动建议撤销失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="research-action-panel">
      <header>
        <div>
          <span className="eyebrow">RESEARCH ACTIONS · EXPLICIT WRITE</span>
          <h2>研究行动助手</h2>
          <p>从本地项目缺口与已缓存洞察生成草稿；不会自动改结论，也不会未经确认写入。</p>
        </div>
        <button className="secondary-button" onClick={generate} disabled={busy}>
          {busy ? <LoaderCircle className="spin" size={14} /> : <Sparkles size={14} />}
          {result?.items.length ? "重新整理建议" : "生成行动建议"}
        </button>
      </header>
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {result?.items.length ? (
        <>
          <div className="research-action-list">
            {result.items.map((draft) => (
              <article className={classNames("research-action-item", draft.status)} key={draft.id}>
                <label>
                  {draft.status === "proposed" ? (
                    <input
                      type="checkbox"
                      checked={selected.includes(draft.id)}
                      onChange={(event) => setSelected((current) =>
                        event.target.checked
                          ? [...current, draft.id]
                          : current.filter((id) => id !== draft.id))}
                    />
                  ) : <CheckCheck size={16} />}
                  <span>{actionCopy[draft.action_type]}</span>
                </label>
                <div>
                  <strong>{draft.title}</strong>
                  <p>{draft.content}</p>
                  <small title={draft.source_reference}>
                    来源：{draft.source} · {formatDateTime(draft.updated_at)}
                  </small>
                </div>
                {draft.status === "accepted" ? (
                  <button className="text-button danger-text" onClick={() => undo(draft)} disabled={busy}>
                    <RotateCcw size={13} /> 撤销写入
                  </button>
                ) : draft.status === "undone" ? <span className="muted">已撤销</span> : null}
              </article>
            ))}
          </div>
          <footer>
            <span><ListTodo size={14} /> {result.notice}</span>
            <button className="primary-button" onClick={accept} disabled={busy || !selected.length}>
              <CheckCheck size={14} /> 确认写入 {selected.length ? `(${selected.length})` : ""}
            </button>
          </footer>
        </>
      ) : (
        <div className="research-action-empty">
          <ListTodo size={19} />
          <span>尚未生成建议。建议仅基于可见项目字段与已缓存摘要。</span>
        </div>
      )}
    </section>
  );
}
