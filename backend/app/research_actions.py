from __future__ import annotations

from datetime import date
from typing import Any

from .database import Database


def build_research_action_drafts(
    database: Database, project_id: int
) -> list[dict[str, str]]:
    """Create inspectable action drafts without mutating the research project."""
    summary = database.project_summary(project_id)
    if summary is None:
        raise KeyError(project_id)
    drafts: list[dict[str, str]] = []
    rule_source = "固定规则 · 本地项目摘要"

    def append(
        action_type: str,
        title: str,
        content: str,
        source_reference: str,
        source: str = rule_source,
    ) -> None:
        if len(drafts) >= 4 or any(item["title"] == title for item in drafts):
            return
        drafts.append(
            {
                "action_type": action_type,
                "title": title[:160],
                "content": content[:8_000],
                "source": source,
                "source_reference": source_reference,
            }
        )

    gaps = [str(item) for item in summary.get("gaps", [])]
    if "尚无研究证据" in gaps:
        append(
            "task",
            "补充一条可追溯的核心证据",
            "明确数据来源、观测时点和支持或削弱当前假设的方向；保存前检查可信状态。",
            "project_summary.gaps: 尚无研究证据",
        )
    if "尚未记录反证" in gaps:
        append(
            "counter_evidence",
            "写下一项会推翻当前判断的条件",
            "描述可观测、可证伪的反向条件，并标记后续核验所需的数据或事件。",
            "project_summary.gaps: 尚未记录反证",
        )
    if "尚未设置下次复盘" in gaps:
        append(
            "review",
            "安排下一次观点复盘",
            "复核核心证据是否更新、反证是否触发，以及当前置信度是否仍然合理。",
            "project_summary.gaps: 尚未设置下次复盘",
        )
    review_date = str(summary.get("next_review_date") or "")
    if review_date and review_date <= date.today().isoformat():
        append(
            "review",
            "完成到期研究复盘",
            f"项目复盘日为 {review_date}；检查结论、置信度、反证与尚未完成的任务。",
            f"project_summary.next_review_date: {review_date}",
        )
    if summary.get("supporting_evidence") and not summary.get("open_tasks"):
        append(
            "task",
            "核验最新证据是否改变结论",
            "逐项检查最新证据的时点、来源与方向，并记录结论保持或调整的理由。",
            "project_summary.supporting_evidence + open_tasks",
        )

    insight = database.get_ai_insight("project", str(project_id))
    if insight and insight.get("status") == "ready" and insight.get("summary"):
        append(
            "task",
            "核对已缓存 AI 洞察中的关键缺口",
            "回到项目证据逐项核对 AI 摘要；只有经人工确认的内容才写入项目判断。",
            f"ai_insight:{insight.get('updated_at', '')}",
            source=(
                f"已缓存 AI 洞察 · {insight.get('provider') or 'provider'}"
                f"/{insight.get('model') or 'model'}"
            ),
        )

    if not drafts:
        append(
            "review",
            "做一次轻量研究健康检查",
            "核对研究问题、关键证据、反证、未完成任务和下次复盘时间。",
            "project_summary: no explicit gaps",
        )
    return drafts


def action_draft_summary(drafts: list[Any]) -> dict[str, Any]:
    return {
        "items": drafts,
        "proposed": sum(item.status == "proposed" for item in drafts),
        "accepted": sum(item.status == "accepted" for item in drafts),
        "notice": "行动建议先作为草稿保存；只有勾选并再次确认后，才会写入研究记录。",
    }

