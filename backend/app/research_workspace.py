from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .database import Database
from .models import (
    ResearchEntryCreate,
    ResearchProjectCreate,
    ResearchProjectItem,
    ResearchProjectTemplateCreate,
)


RESEARCH_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "blank",
        "name": "空白研究",
        "description": "从一个自定义、可验证的问题开始。",
        "title": "新研究项目",
        "question": "希望验证什么？",
        "hypothesis": "",
        "horizon": "",
        "tags": [],
    },
    {
        "id": "rates_direction",
        "name": "中国利率方向",
        "description": "结合资金、曲线、期货和现券验证利率方向。",
        "title": "中国利率方向观察",
        "question": "未来 1–3 个月长端利率的主要驱动是什么？",
        "hypothesis": "资金、基本面预期与供给共同决定利率方向。",
        "horizon": "未来 1–3 个月",
        "tags": ["中国利率", "久期"],
    },
    {
        "id": "macro_release",
        "name": "宏观数据发布",
        "description": "记录发布前预期、实际偏差和市场窗口。",
        "title": "宏观数据发布复盘",
        "question": "本次数据相对预期的偏差如何影响利率定价？",
        "hypothesis": "超预期方向会先影响政策和增长预期，再传导至利率。",
        "horizon": "发布前后 10 个交易日",
        "tags": ["宏观发布", "事件复盘"],
    },
    {
        "id": "convertible_event",
        "name": "可转债事件",
        "description": "跟踪价格、溢价、双低、YTM 与条款事件。",
        "title": "可转债事件观察",
        "question": "事件是否改变转债的下行保护或向上弹性？",
        "hypothesis": "正股、估值与条款变化共同影响风险收益。",
        "horizon": "未来 1–4 周",
        "tags": ["可转债", "事件"],
    },
    {
        "id": "credit_observation",
        "name": "信用观察",
        "description": "先校验覆盖字段，再做机械利差试算。",
        "title": "信用债覆盖与利差观察",
        "question": "主体、评级、期限和基准是否足以支持可信利差观察？",
        "hypothesis": "只有日期与期限严格匹配后，利差才有比较意义。",
        "horizon": "未来 1–3 个月",
        "tags": ["信用观察", "覆盖率"],
    },
    {
        "id": "sovereign_comparison",
        "name": "主权基本面比较",
        "description": "比较多个经济体的增长、财政、外部平衡与结构变量。",
        "title": "全球主权基本面比较",
        "question": "所选经济体的增长、财政与外部脆弱性有何结构性差异？",
        "hypothesis": "只有在同一指标、同一年度且缺失值边界清晰时，跨国比较才具有解释意义。",
        "horizon": "过去 10–20 年结构变化",
        "tags": ["全球宏观", "主权比较", "World Bank"],
    },
]


def create_project_from_template(
    database: Database, request: ResearchProjectTemplateCreate
) -> ResearchProjectItem:
    template = next(
        item for item in RESEARCH_TEMPLATES if item["id"] == request.template_id
    )
    object_id = (request.object_id or "").strip()
    object_type = (request.object_type or "research").strip()
    if object_id:
        existing = database.find_research_project_by_origin(
            request.template_id, object_type, object_id
        )
        if existing is not None and existing.status != "archived":
            return existing
    name = (request.object_name or request.object_id or "").strip()
    title = f"{name} · {template['title']}" if name else template["title"]
    question = request.question or template["question"]
    tags = list(template["tags"])
    if request.object_type:
        tags.append(request.object_type)
    project = database.add_research_project(
        ResearchProjectCreate(
            title=title,
            question=question,
            hypothesis=template["hypothesis"],
            horizon=template["horizon"],
            tags=list(dict.fromkeys(tags)),
            next_review_date=(date.today() + timedelta(days=7)).isoformat(),
        )
    )
    if object_id:
        database.set_research_project_origin(
            project.id, request.template_id, object_type, object_id
        )
    context = [
        request.context_note.strip(),
        f"对象：{name}" if name else "",
        f"标识：{request.object_id}" if request.object_id else "",
        f"来源：{request.source}" if request.source else "",
        f"观测时间：{request.observation_time}" if request.observation_time else "",
    ]
    content = "\n".join(item for item in context if item)
    if content:
        database.add_research_entry(
            project.id,
            ResearchEntryCreate(
                entry_type="note",
                title="立项上下文",
                content=content,
            ),
        )
    saved = database.get_research_project(project.id)
    if saved is None:
        raise RuntimeError("模板项目创建失败")
    return saved


def project_markdown(project: ResearchProjectItem) -> str:
    lines = [
        f"# {project.title}",
        "",
        f"> 导出时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 研究问题",
        "",
        project.question or "—",
        "",
        "## 初始假设",
        "",
        project.hypothesis or "—",
        "",
        "## 当前状态",
        "",
        f"- 状态：{project.status}",
        f"- 置信度：{project.confidence}",
        f"- 研究期限：{project.horizon or '—'}",
        f"- 下次复盘：{project.next_review_date or '—'}",
        f"- 标签：{'、'.join(project.tags) or '—'}",
        "",
        "## 当前结论与风险点",
        "",
        project.conclusion or "—",
        "",
        "## 研究日志",
        "",
    ]
    for item in reversed(project.entries):
        lines.extend(
            [
                f"### [{item.entry_type}] {item.title}",
                "",
                f"- 状态：{item.status}",
                f"- 到期：{item.due_date or '—'}",
                f"- 时间：{item.updated_at.isoformat(timespec='seconds')}",
                "",
                item.content or "—",
                "",
            ]
        )
    lines.extend(["## 研究证据", ""])
    for item in project.evidence:
        lines.extend(
            [
                f"### {item.title}",
                "",
                f"- 类型：{item.evidence_type}",
                f"- 来源：{item.source_summary or '—'}",
                f"- 区间：{item.observation_start or '—'} 至 {item.observation_end or '—'}",
                f"- 保存时间：{item.created_at.isoformat(timespec='seconds')}",
                f"- 保存方式：{item.payload.get('storage_mode', '本地快照')}",
                "",
            ]
        )
    lines.extend(
        [
            "## 数据边界",
            "",
            "FRED 证据仅包含序列、来源、区间与变换引用，不包含观测值。",
            "",
        ]
    )
    return "\n".join(lines)


def weekly_report(database: Database, end_date: date | None = None) -> dict[str, Any]:
    end = end_date or date.today()
    start = end - timedelta(days=6)
    workspace = database.weekly_workspace_stats(start.isoformat(), end.isoformat())
    entries = workspace["entries"]
    projects = workspace["projects"]
    conclusion_updates = [
        item
        for item in projects
        if item.get("conclusion")
        and start.isoformat() <= str(item.get("updated_at", ""))[:10] <= end.isoformat()
    ]
    next_reviews = sorted(
        [item for item in projects if item.get("next_review_date")],
        key=lambda item: (item["next_review_date"], item["title"]),
    )
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "active_projects": len(projects),
            "projects_updated": len(
                {
                    item["project_id"]
                    for item in workspace["activity"]
                    if item.get("project_id") is not None
                }
            ),
            "notes": sum(item["entry_type"] == "note" for item in entries),
            "counter_evidence": sum(
                item["entry_type"] == "counter_evidence" for item in entries
            ),
            "tasks_done": sum(
                item["entry_type"] == "task" and item["status"] == "done"
                for item in entries
            ),
            "tasks_open": sum(
                item["entry_type"] == "task" and item["status"] == "open"
                for item in entries
            ),
            "release_reviews": len(workspace["release_reviews"]),
        },
        "due_projects": [
            item
            for item in projects
            if item.get("next_review_date") and item["next_review_date"] <= end.isoformat()
        ],
        "conclusion_updates": conclusion_updates,
        "next_reviews": next_reviews[:20],
        **workspace,
        "notice": "周报汇总本地研究活动，不生成自动投资结论。",
    }


def weekly_report_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"# AKDesk 每周研究复盘 · {report['start_date']} 至 {report['end_date']}",
        "",
        f"- 活跃项目：{summary['active_projects']}",
        f"- 本周有更新项目：{summary['projects_updated']}",
        f"- 研究笔记：{summary['notes']}",
        f"- 新增反证：{summary['counter_evidence']}",
        f"- 完成任务：{summary['tasks_done']}",
        f"- 未完成任务：{summary['tasks_open']}",
        f"- 发布复盘：{summary['release_reviews']}",
        "",
        "## 待复盘项目",
        "",
    ]
    for item in report["due_projects"]:
        lines.append(
            f"- {item['title']} · 置信度 {item['confidence']} · 复盘 {item['next_review_date']}"
        )
    lines.extend(["", "## 本周研究活动", ""])
    for item in report["activity"][:50]:
        lines.append(
            f"- {item['created_at']} · {item['project_title']} · {item['summary']}"
        )
    lines.extend(["", "## 本周观点", ""])
    for item in report["conclusion_updates"]:
        lines.append(f"- {item['title']}：{item['conclusion']}")
    lines.extend(["", "## 下周待验证", ""])
    for item in report["open_tasks"]:
        due = f" · 到期 {item['due_date']}" if item.get("due_date") else ""
        lines.append(f"- {item['project_title']} · {item['title']}{due}")
    lines.extend(["", "## 下次复盘", ""])
    for item in report["next_reviews"]:
        lines.append(f"- {item['title']} · {item['next_review_date']}")
    lines.extend(["", "> 本报告仅汇总本地研究活动，不构成投资建议。", ""])
    return "\n".join(lines)
