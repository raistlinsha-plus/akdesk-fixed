import { ExternalLink, FolderPlus, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { apiPost } from "../api";
import type { ResearchProject, ResearchTemplate } from "../types";

export function CreateProjectButton({
  objectType,
  objectId,
  objectName,
  source,
  observationTime,
  question,
  templateId,
  onCreated,
}: {
  objectType?: "bond" | "future" | "convertible" | "macro" | "fx" | "issuer";
  objectId?: string | null;
  objectName?: string | null;
  source?: string | null;
  observationTime?: string | null;
  question?: string;
  templateId?: ResearchTemplate["id"];
  onCreated?: (project: ResearchProject) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [createdProject, setCreatedProject] = useState<ResearchProject | null>(null);
  const inferredTemplate: ResearchTemplate["id"] = templateId || (
    objectType === "convertible"
      ? "convertible_event"
      : objectType === "macro"
        ? "macro_release"
        : "rates_direction"
  );

  async function create() {
    setSaving(true);
    setMessage(null);
    try {
      const project = await apiPost<ResearchProject>("/research/projects/from-template", {
        template_id: inferredTemplate,
        object_type: objectType,
        object_id: objectId || null,
        object_name: objectName || null,
        source: source || null,
        observation_time: observationTime || null,
        question: question || null,
      });
      setCreatedProject(project);
      setMessage("已关联");
      onCreated?.(project);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "立项失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <span className="quick-project-action">
      {createdProject ? (
        <button
          className="text-button compact"
          onClick={() => { window.location.hash = `#/projects?q=${createdProject.id}`; }}
          title={`打开“${createdProject.title}”`}
        >
          <ExternalLink size={13} /> 打开项目
        </button>
      ) : (
        <button className="icon-button" onClick={create} disabled={saving} title="一键创建研究项目" aria-label={`为${objectName || objectId || "当前对象"}创建研究项目`}>
          {saving ? <LoaderCircle className="spin" size={14} /> : <FolderPlus size={14} />}
        </button>
      )}
      {message ? <small role="status">{message}</small> : null}
    </span>
  );
}
