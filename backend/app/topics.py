from __future__ import annotations

import json
import hashlib
from datetime import datetime
from typing import Any

from .database import Database
from .models import (
    IssuerEventTopicCreate,
    ResearchTopicCreate,
    ResearchTopicComponent,
    ResearchTopicItem,
    ResearchTopicTemplateCreate,
    ResearchTopicUpdate,
)


def _component(
    component_id: str,
    component_type: str,
    title: str,
    order: int,
    **config: Any,
) -> dict[str, Any]:
    return {
        "id": component_id,
        "component_type": component_type,
        "title": title,
        "order": order,
        "config": config,
    }


current_year = datetime.now().year

RESEARCH_TOPIC_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "china_rates",
        "name": "中国利率方向",
        "description": "把资金、曲线、国债期货和相关研究项目放在同一专题中。",
        "title": "中国利率方向专题",
        "question": "资金、供给和基本面预期如何共同影响中国长端利率？",
        "object_type": "rates_theme",
        "object_key": "china-rates",
        "object_name": "中国利率",
        "tags": ["中国利率", "久期", "固收"],
        "components": [
            _component("market", "market_pulse", "当前市场脉搏", 10),
            _component(
                "curve",
                "market_history",
                "中国国债期限结构",
                20,
                adapter="yield_curves",
                metric="yield",
                series=["1Y", "5Y", "10Y", "30Y"],
                days=120,
                unit="%",
            ),
            _component("summary", "project_summary", "关联项目摘要", 30),
            _component("evidence", "recent_evidence", "最近证据", 40),
        ],
    },
    {
        "id": "sino_us_rates",
        "name": "中美利率联动",
        "description": "同时观察中国长端利率、美债名义与实际利率。",
        "title": "中美利率联动专题",
        "question": "美债名义与实际利率变化如何影响中国长端利率定价？",
        "object_type": "rates_theme",
        "object_key": "sino-us-rates",
        "object_name": "中美利率联动",
        "tags": ["中美利率", "实际利率", "跨市场"],
        "components": [
            _component(
                "china-10y",
                "market_history",
                "中国国债 10Y",
                10,
                adapter="yield_curves",
                metric="yield",
                series=["10Y"],
                days=180,
                unit="%",
            ),
            _component(
                "us-rates",
                "fred_chart",
                "美国名义与实际利率",
                20,
                series=["DGS10", "DFII10", "T10YIE"],
                years=5,
                transform="level",
            ),
            _component("summary", "project_summary", "关联项目摘要", 30),
            _component("evidence", "recent_evidence", "最近证据", 40),
        ],
    },
    {
        "id": "rmb_rates",
        "name": "人民币汇率与利率",
        "description": "观察人民币中间价、中国长端利率和美国利率的共同变化。",
        "title": "人民币汇率与中国利率专题",
        "question": "人民币汇率变化是否正在改变中国利率与跨境资金预期？",
        "object_type": "macro_theme",
        "object_key": "rmb-rates",
        "object_name": "人民币汇率与中国利率",
        "tags": ["人民币", "外汇", "中国利率"],
        "components": [
            _component(
                "rmb",
                "market_history",
                "人民币参考价",
                10,
                adapter="fx_rmb_reference",
                metric="mid",
                series=["USDCNY", "EURCNY", "JPYCNY"],
                days=120,
                unit="CNY",
            ),
            _component(
                "china-10y",
                "market_history",
                "中国国债 10Y",
                20,
                adapter="yield_curves",
                metric="yield",
                series=["10Y"],
                days=120,
                unit="%",
            ),
            _component(
                "us-10y",
                "fred_chart",
                "美国 10Y 利率",
                30,
                series=["DGS10"],
                years=5,
                transform="level",
            ),
            _component("summary", "project_summary", "关联项目摘要", 40),
        ],
    },
    {
        "id": "global_inflation",
        "name": "全球通胀与实际利率",
        "description": "连接 FRED 通胀、实际利率与 World Bank 跨国通胀数据。",
        "title": "全球通胀与实际利率专题",
        "question": "通胀趋势与实际利率如何改变主要经济体的利率环境？",
        "object_type": "macro_theme",
        "object_key": "global-inflation",
        "object_name": "全球通胀与实际利率",
        "tags": ["通胀", "实际利率", "全球宏观"],
        "components": [
            _component(
                "us-inflation",
                "fred_chart",
                "美国 CPI 与核心 CPI",
                10,
                series=["CPIAUCSL", "CPILFESL"],
                years=10,
                transform="yoy",
            ),
            _component(
                "real-rates",
                "fred_chart",
                "美国实际利率与通胀预期",
                15,
                series=["DFII10", "T10YIE"],
                years=10,
                transform="level",
            ),
            _component(
                "global-cpi",
                "sovereign_compare",
                "主要经济体通胀",
                20,
                countries=["CHN", "USA", "JPN", "DEU"],
                indicator="FP.CPI.TOTL.ZG",
                start_year=current_year - 10,
                end_year=current_year,
                view="level",
            ),
            _component("summary", "project_summary", "关联项目摘要", 30),
            _component("evidence", "recent_evidence", "最近证据", 40),
        ],
    },
    {
        "id": "blank",
        "name": "空白专题",
        "description": "创建一个只有项目摘要和时间线的自定义专题。",
        "title": "新专题研究",
        "question": "这个专题希望持续验证什么？",
        "object_type": "macro_theme",
        "object_key": "",
        "object_name": "自定义专题",
        "tags": [],
        "components": [
            _component("summary", "project_summary", "关联项目摘要", 10),
            _component("evidence", "recent_evidence", "最近证据", 20),
        ],
    },
]


def create_topic_from_template(
    database: Database, request: ResearchTopicTemplateCreate
) -> ResearchTopicItem:
    template = next(
        item for item in RESEARCH_TOPIC_TEMPLATES if item["id"] == request.template_id
    )
    object_key = template["object_key"] or (
        "custom-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
    )
    payload = ResearchTopicCreate(
        title=request.title or template["title"],
        question=template["question"],
        description=template["description"],
        object_type=template["object_type"],
        object_key=object_key,
        object_name=request.title or template["object_name"],
        object_description=template["description"],
        tags=template["tags"],
        components=template["components"],
        project_ids=request.project_ids,
    )
    return database.add_research_topic(payload)


def create_or_get_issuer_event_topic(
    database: Database, request: IssuerEventTopicCreate
) -> ResearchTopicItem:
    issuer = request.issuer
    object_key = "issuer-" + hashlib.sha256(issuer.encode()).hexdigest()[:20]
    component = ResearchTopicComponent(
        id="issuer-events",
        component_type="event_radar",
        title=f"{issuer}事件线索",
        order=10,
        config={"query": f'"{issuer}"', "days": 30, "limit": 20, "sort": "datedesc"},
    )
    for topic in database.list_research_topics(query=issuer, limit=500):
        if (
            topic.research_object.object_type == "issuer"
            and topic.research_object.object_key == object_key
        ):
            project_ids = [item.id for item in topic.projects]
            if request.project_id and request.project_id not in project_ids:
                project_ids.append(request.project_id)
            components = list(topic.components)
            if not any(item.component_type == "event_radar" for item in components):
                components.insert(0, component)
            if project_ids != [item.id for item in topic.projects] or components != list(
                topic.components
            ):
                updated = database.update_research_topic(
                    topic.id,
                    ResearchTopicUpdate(
                        project_ids=project_ids,
                        components=components,
                    ),
                )
                if updated is not None:
                    return updated
            return topic
    return database.add_research_topic(
        ResearchTopicCreate(
            title=f"{issuer}事件观察",
            question=f"哪些经原文核验的外部事件可能改变对{issuer}的信用观察？",
            description=(
                "按需检索 GDELT 新闻元数据，先作为待核验线索进入证据篮，"
                "再由研究项目记录核验与观点变化。"
            ),
            object_type="issuer",
            object_key=object_key,
            object_name=issuer,
            object_description="信用观察发行人事件专题",
            tags=["发行人", "信用观察", "事件线索"],
            components=[
                component,
                ResearchTopicComponent(
                    id="summary",
                    component_type="project_summary",
                    title="关联项目摘要",
                    order=20,
                ),
                ResearchTopicComponent(
                    id="evidence",
                    component_type="recent_evidence",
                    title="最近证据",
                    order=30,
                ),
            ],
            project_ids=[request.project_id] if request.project_id else [],
        )
    )


def topic_markdown(database: Database, topic: ResearchTopicItem) -> str:
    timeline = database.topic_timeline(topic.id, limit=None)
    summaries = [
        summary
        for project in topic.projects
        if (summary := database.project_summary(project.id)) is not None
    ]
    lines = [
        f"# {topic.title}",
        "",
        f"> 导出时间：{datetime.now().isoformat(timespec='seconds')}",
        f"> 研究对象：{topic.research_object.name}（{topic.research_object.object_type}）",
        f"> 时间线记录：{len(timeline)} 条（完整历史）",
        "",
        "## 研究问题",
        "",
        topic.question or "—",
        "",
        "## 专题说明",
        "",
        topic.description or "—",
        "",
        "## 专题视图",
        "",
    ]
    for component in topic.components:
        lines.append(
            f"- {component.title} · {component.component_type} · 配置 "
            f"`{json.dumps(component.config, ensure_ascii=False, sort_keys=True)}`"
        )
    lines.extend(["", "## 关联项目摘要", ""])
    for summary in summaries:
        lines.extend(
            [
                f"### {summary['title']}",
                "",
                f"- 状态：{summary['status']}",
                f"- 置信度：{summary['confidence']}",
                f"- 当前问题：{summary['question'] or '—'}",
                f"- 当前假设：{summary['hypothesis'] or '—'}",
                f"- 当前结论：{summary['conclusion'] or '—'}",
                f"- 支持证据：{len(summary['supporting_evidence'])} 项",
                f"- 反证：{len(summary['counter_evidence'])} 项",
                f"- 未完成任务：{len(summary['open_tasks'])} 项",
                f"- 下次复盘：{summary['next_review_date'] or '—'}",
                "",
            ]
        )
    lines.extend(["## 跨源时间线", ""])
    for item in timeline:
        lines.append(
            f"- {item['event_time']} · {item['event_type']} · "
            f"{item['project_title']} · {item['title']}"
        )
    lines.extend(
        [
            "",
            "## 数据边界",
            "",
            "- FRED 专题组件只保存序列与变换配置，导出不包含请求级观测值。",
            "- World Bank 与市场证据以本地保存时的来源、日期和许可信息为准。",
            "- GDELT 专题组件只缓存事件元数据；标题与链接是待核验线索，不是事实确认或风险评分。",
            "- 结构化摘要由固定规则整理，不生成自动投资结论。",
            "",
            "> 仅供个人研究参考，不构成投资建议。",
            "",
        ]
    )
    return "\n".join(lines)
