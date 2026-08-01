import { useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  CircleDashed,
  ListChecks,
} from "lucide-react";
import {
  guideProgress,
  type ExperienceTask,
} from "../experienceGuide";

export function GettingStartedGuide({
  mode,
  tasks,
  onNavigate,
}: {
  mode: "market" | "research";
  tasks: ExperienceTask[];
  onNavigate: (page: string) => void;
}) {
  const storageKey = `akdesk:v0.12.2:guide-collapsed:${mode}`;
  const [collapsed, setCollapsed] = useState(
    () => window.localStorage.getItem(storageKey) === "true",
  );
  const progress = guideProgress(tasks);

  function setGuideCollapsed(value: boolean) {
    setCollapsed(value);
    window.localStorage.setItem(storageKey, String(value));
  }

  if (collapsed) {
    return (
      <button
        type="button"
        className="experience-guide-reopen"
        onClick={() => setGuideCollapsed(false)}
      >
        <ListChecks size={16} />
        <span>{mode === "market" ? "今日市场待办" : "投研快速开始"}</span>
        <strong>{progress.completed}/{progress.total}</strong>
        <ChevronDown size={15} />
      </button>
    );
  }

  return (
    <section className={`experience-guide ${mode}`} aria-labelledby={`${mode}-experience-guide-title`}>
      <header>
        <div>
          <span className="eyebrow">{mode === "market" ? "TODAY'S CHECKLIST" : "GETTING STARTED"}</span>
          <h2 id={`${mode}-experience-guide-title`}>
            {mode === "market" ? "今天先看什么" : "从研究问题走到可复盘结论"}
          </h2>
          <p>
            {mode === "market"
              ? "按数据状态、自选、专业模块和复盘四步建立日常使用路径。"
              : "按项目、专题、证据和复盘四步完成第一次投研闭环。"}
          </p>
        </div>
        <div className="experience-guide-progress">
          <strong>{progress.completed}/{progress.total}</strong>
          <span>已完成</span>
          <button type="button" className="text-button" onClick={() => setGuideCollapsed(true)}>收起</button>
        </div>
      </header>
      <div className="experience-guide-bar" aria-hidden="true">
        <span style={{ width: `${progress.percent}%` }} />
      </div>
      <div className="experience-guide-tasks">
        {tasks.map((task) => {
          const Icon = task.status === "done"
            ? CheckCircle2
            : task.status === "attention"
              ? CircleAlert
              : CircleDashed;
          return (
            <article className={task.status} key={task.id}>
              <Icon size={18} />
              <div>
                <strong>{task.title}</strong>
                <p>{task.description}</p>
                <button type="button" className="text-button" onClick={() => onNavigate(task.page)}>
                  {task.action} <ArrowRight size={13} />
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
