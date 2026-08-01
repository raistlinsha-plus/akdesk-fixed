from __future__ import annotations

import sqlite3
from contextlib import contextmanager

import pytest

from app.database import Database
from app.models import (
    EvidenceBasketCommit,
    EvidenceBasketCreate,
    ResearchEntryCreate,
    ResearchEvidenceCreate,
    ResearchProjectCreate,
    ResearchProjectUpdate,
    ResearchTopicComponent,
    ResearchTopicTemplateCreate,
    ResearchTopicUpdate,
)
from app.topics import RESEARCH_TOPIC_TEMPLATES, create_topic_from_template, topic_markdown


def test_schema_1201_and_topic_lifecycle_preserve_existing_projects(tmp_path) -> None:
    path = tmp_path / "topic-upgrade.db"
    database = Database(path)
    project = database.add_research_project(
        ResearchProjectCreate(title="升级前利率项目")
    )

    topic = create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(
            template_id="sino_us_rates",
            project_ids=[project.id],
        ),
    )

    assert topic.research_object.object_type == "rates_theme"
    assert topic.projects[0].id == project.id
    assert {item.component_type for item in topic.components} >= {
        "market_history",
        "fred_chart",
        "project_summary",
    }

    updated = database.update_research_topic(
        topic.id,
        ResearchTopicUpdate(
            status="review",
            tags=["中美利率", "复盘"],
            project_ids=[project.id],
            components=topic.components[:2],
        ),
    )
    assert updated is not None
    assert updated.status == "review"
    assert updated.tags == ["中美利率", "复盘"]
    assert len(updated.components) == 2
    bundle = database.project_bundle(project.id)
    assert bundle is not None
    assert bundle["research_objects"][0]["object_key"] == "sino-us-rates"
    imported = database.import_project_bundle(bundle)
    imported_bundle = database.project_bundle(imported.id)
    assert imported_bundle is not None
    assert imported_bundle["research_objects"][0]["name"] == "中美利率联动"

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1600
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 900"
        ).fetchone()[0] == 1
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "research_objects",
        "research_topics",
        "research_topic_projects",
        "research_project_objects",
        "research_evidence_objects",
        "research_evidence_basket",
    } <= tables
    assert database.get_research_project(project.id) is not None


def test_schema_1201_migrates_an_existing_schema_800_database(tmp_path) -> None:
    path = tmp_path / "schema-800.db"
    database = Database(path)
    project = database.add_research_project(
        ResearchProjectCreate(title="v0.8.2 既有项目")
    )
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        for table in (
            "research_evidence_basket",
            "research_evidence_objects",
            "research_project_objects",
            "research_topic_projects",
            "research_topics",
            "research_objects",
        ):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("DELETE FROM schema_migrations WHERE version = 900")
        connection.execute("PRAGMA user_version=800")

    upgraded = Database(path)

    assert upgraded.get_research_project(project.id).title == "v0.8.2 既有项目"  # type: ignore[union-attr]
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1600
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 900"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM research_topics"
        ).fetchone()[0] == 0


def test_evidence_basket_commit_links_object_and_builds_cross_source_timeline(
    tmp_path,
) -> None:
    database = Database(tmp_path / "basket.db")
    project = database.add_research_project(
        ResearchProjectCreate(
            title="中美利率",
            question="美债实际利率如何影响中国长端？",
            hypothesis="实际利率上行会提高全球久期资产折现率。",
            next_review_date="2026-07-31",
        )
    )
    topic = create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(
            template_id="sino_us_rates",
            project_ids=[project.id],
        ),
    )
    fred = database.add_evidence_basket(
        EvidenceBasketCreate(
            evidence_type="chart",
            title="DGS10 / DFII10",
            source_summary="FRED · DGS10, DFII10",
            payload={
                "schema_version": 2,
                "storage_mode": "reference_only",
                "provider": "FRED",
                "series": [
                    {"series_id": "DGS10", "name": "美国国债 10Y"},
                    {"series_id": "DFII10", "name": "美国实际利率 10Y"},
                ],
                "transform": "level",
            },
            observation_start="2021-01-01",
            observation_end="2026-07-16",
            origin_page="chart-lab",
            topic_id=topic.id,
        )
    )
    market = database.add_evidence_basket(
        EvidenceBasketCreate(
            evidence_type="snapshot",
            title="中国固收市场快照",
            source_summary="中国货币网 · 2 项可信市场信号",
            payload={
                "snapshot_type": "market_brief",
                "signals": [{"id": "curve-10y", "title": "中国 10Y"}],
            },
            observation_end="2026-07-16",
            origin_page="research-desk",
            topic_id=topic.id,
        )
    )

    saved = database.commit_evidence_basket(
        EvidenceBasketCommit(
            project_id=project.id,
            item_ids=[fred.id, market.id],
            topic_id=topic.id,
        )
    )

    assert len(saved) == 2
    assert database.list_evidence_basket() == []
    timeline = database.topic_timeline(topic.id)
    assert {item["event_type"] for item in timeline} >= {
        "fred_reference",
        "market_snapshot",
        "project_created",
    }
    with sqlite3.connect(database.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM research_evidence_objects"
        ).fetchone()[0] == 2


def test_basket_commit_preserves_origin_and_target_topic_objects(tmp_path) -> None:
    database = Database(tmp_path / "cross-topic-basket.db")
    project = database.add_research_project(ResearchProjectCreate(title="跨专题项目"))
    origin = create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(template_id="rmb_rates"),
    )
    target = create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(template_id="china_rates"),
    )
    basket_item = database.add_evidence_basket(
        EvidenceBasketCreate(
            evidence_type="snapshot",
            title="人民币市场快照",
            payload={"snapshot_type": "fx_reference"},
            source_summary="AKShare / BOC",
            origin_page="fx",
            topic_id=origin.id,
        )
    )

    saved = database.commit_evidence_basket(
        EvidenceBasketCommit(
            project_id=project.id,
            item_ids=[basket_item.id],
            topic_id=target.id,
        )
    )

    with sqlite3.connect(database.path) as connection:
        evidence_objects = connection.execute(
            "SELECT COUNT(*) FROM research_evidence_objects WHERE evidence_id = ?",
            (saved[0].id,),
        ).fetchone()[0]
        project_objects = connection.execute(
            "SELECT COUNT(*) FROM research_project_objects WHERE project_id = ?",
            (project.id,),
        ).fetchone()[0]
    assert evidence_objects == 2
    assert project_objects == 2
    assert database.get_research_topic(target.id).projects[0].id == project.id  # type: ignore[union-attr]


def test_topic_timeline_filters_evidence_by_research_object(tmp_path) -> None:
    database = Database(tmp_path / "object-timeline.db")
    project = database.add_research_project(ResearchProjectCreate(title="多对象项目"))
    rates_topic = create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(
            template_id="china_rates",
            project_ids=[project.id],
        ),
    )
    rmb_topic = create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(
            template_id="rmb_rates",
            project_ids=[project.id],
        ),
    )
    basket_item = database.add_evidence_basket(
        EvidenceBasketCreate(
            evidence_type="snapshot",
            title="人民币专属证据",
            payload={"snapshot_type": "fx_reference"},
            origin_page="fx",
            topic_id=rmb_topic.id,
        )
    )
    database.commit_evidence_basket(
        EvidenceBasketCommit(
            project_id=project.id,
            item_ids=[basket_item.id],
        )
    )

    rmb_titles = {item["title"] for item in database.topic_timeline(rmb_topic.id)}
    rates_titles = {item["title"] for item in database.topic_timeline(rates_topic.id)}

    assert "人民币专属证据" in rmb_titles
    assert "人民币专属证据" not in rates_titles


def test_topic_delete_cleans_only_unreferenced_research_objects(tmp_path) -> None:
    database = Database(tmp_path / "topic-delete.db")
    orphan_topic = create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(template_id="blank"),
    )
    project = database.add_research_project(ResearchProjectCreate(title="保留对象"))
    linked_topic = create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(
            template_id="china_rates",
            project_ids=[project.id],
        ),
    )

    assert database.delete_research_topic(orphan_topic.id) is True
    assert database.delete_research_topic(linked_topic.id) is True

    with sqlite3.connect(database.path) as connection:
        object_keys = {
            row[0]
            for row in connection.execute(
                "SELECT object_key FROM research_objects"
            ).fetchall()
        }
    assert orphan_topic.research_object.object_key not in object_keys
    assert linked_topic.research_object.object_key in object_keys


def test_project_import_validates_and_restores_evidence_object_links(tmp_path) -> None:
    database = Database(tmp_path / "project-import-objects.db")
    project = database.add_research_project(ResearchProjectCreate(title="出口项目"))
    create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(
            template_id="sino_us_rates",
            project_ids=[project.id],
        ),
    )
    database.add_research_evidence(
        project.id,
        ResearchEvidenceCreate(
            evidence_type="snapshot",
            title="利率快照",
            payload={"snapshot_type": "rates"},
        ),
    )
    bundle = database.project_bundle(project.id)
    assert bundle is not None

    imported = database.import_project_bundle(bundle)
    with sqlite3.connect(database.path) as connection:
        imported_links = connection.execute(
            """
            SELECT COUNT(*)
            FROM research_evidence_objects AS link
            JOIN research_evidence AS evidence ON evidence.id = link.evidence_id
            WHERE evidence.project_id = ?
            """,
            (imported.id,),
        ).fetchone()[0]
        before_invalid = connection.execute(
            "SELECT COUNT(*) FROM research_projects"
        ).fetchone()[0]
    assert imported_links == 1

    invalid = dict(bundle)
    invalid["research_objects"] = [
        {**bundle["research_objects"][0], "object_type": "unsupported"}
    ]
    with pytest.raises(ValueError, match="不支持的研究对象类型"):
        database.import_project_bundle(invalid)
    with sqlite3.connect(database.path) as connection:
        after_invalid = connection.execute(
            "SELECT COUNT(*) FROM research_projects"
        ).fetchone()[0]
    assert after_invalid == before_invalid


def test_project_summary_is_rule_based_and_exposes_gaps(tmp_path) -> None:
    database = Database(tmp_path / "summary.db")
    project = database.add_research_project(
        ResearchProjectCreate(
            title="人民币与利率",
            question="汇率是否正在约束利率？",
            hypothesis="汇率压力会改变宽松预期。",
        )
    )
    database.add_research_evidence(
        project.id,
        ResearchEvidenceCreate(
            evidence_type="snapshot",
            title="人民币参考价",
            source_summary="AKShare / BOC",
            payload={"snapshot_type": "fx_reference"},
        ),
    )
    database.add_research_entry(
        project.id,
        ResearchEntryCreate(
            entry_type="counter_evidence",
            title="国内资金仍宽松",
            content="资金价格尚未显示明显约束。",
        ),
    )
    database.add_research_entry(
        project.id,
        ResearchEntryCreate(
            entry_type="task",
            title="核对外汇结售汇数据",
            due_date="2026-07-25",
        ),
    )
    database.update_research_project(
        project.id,
        ResearchProjectUpdate(
            confidence=65,
            conclusion="汇率约束存在，但尚未成为利率的主导变量。",
        ),
    )

    summary = database.project_summary(project.id)

    assert summary is not None
    assert summary["confidence"] == 65
    assert len(summary["supporting_evidence"]) == 1
    assert len(summary["counter_evidence"]) == 1
    assert len(summary["open_tasks"]) == 1
    assert len(summary["recent_conclusion_changes"]) == 1
    assert summary["gaps"] == ["尚未设置下次复盘"]
    assert "固定规则" in summary["notice"]


def test_topic_and_basket_validation_boundaries(tmp_path) -> None:
    database = Database(tmp_path / "boundaries.db")
    assert {item["id"] for item in RESEARCH_TOPIC_TEMPLATES} == {
        "china_rates",
        "sino_us_rates",
        "rmb_rates",
        "global_inflation",
        "blank",
    }
    with pytest.raises(ValueError, match="关联的研究项目不存在"):
        create_topic_from_template(
            database,
            ResearchTopicTemplateCreate(
                template_id="china_rates",
                project_ids=[999],
            ),
        )


def test_topic_workspace_aggregates_detail_timeline_and_summaries(tmp_path) -> None:
    database = Database(tmp_path / "topic-workspace.db")
    project = database.add_research_project(
        ResearchProjectCreate(title="聚合专题项目", question="利率是否转向？")
    )
    topic = create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(
            template_id="china_rates",
            project_ids=[project.id],
        ),
    )

    workspace = database.topic_workspace(topic.id, timeline_limit=20)

    assert workspace is not None
    assert workspace["topic"].id == topic.id
    assert workspace["project_summaries"][0]["project_id"] == project.id
    assert workspace["timeline"][0]["event_type"] == "project_created"
    assert workspace["timeline_total"] == 1
    assert workspace["timeline_has_more"] is False
    assert workspace["generated_at"]
    assert database.topic_workspace(999999) is None


def test_topic_timeline_paginates_without_truncating_export(tmp_path) -> None:
    database = Database(tmp_path / "topic-timeline-page.db")
    project = database.add_research_project(
        ResearchProjectCreate(title="长期专题项目")
    )
    topic = create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(
            template_id="china_rates",
            project_ids=[project.id],
        ),
    )
    for index in range(225):
        database.add_research_entry(
            project.id,
            ResearchEntryCreate(title=f"长期记录 {index:03d}"),
        )

    first = database.topic_timeline_page(topic.id, limit=100)
    second = database.topic_timeline_page(
        topic.id,
        limit=100,
        before_time=first["next_cursor"]["event_time"],
        before_id=first["next_cursor"]["id"],
    )
    last = database.topic_timeline_page(
        topic.id,
        limit=100,
        before_time=second["next_cursor"]["event_time"],
        before_id=second["next_cursor"]["id"],
    )

    assert first["total"] == 226
    assert len(first["items"]) == 100
    assert first["has_more"] is True
    assert len(second["items"]) == 100
    assert second["next_cursor"] is not None
    assert len(last["items"]) == 26
    assert last["has_more"] is False
    assert last["next_cursor"] is None
    assert len({item["id"] for item in [*first["items"], *second["items"], *last["items"]]}) == 226

    exported = topic_markdown(database, topic)
    assert "时间线记录：226 条（完整历史）" in exported
    assert "长期记录 000" in exported
    assert "长期记录 224" in exported


def test_evidence_basket_filters_and_batch_delete(tmp_path) -> None:
    database = Database(tmp_path / "basket-filter.db")
    topic = create_topic_from_template(
        database,
        ResearchTopicTemplateCreate(template_id="sino_us_rates"),
    )
    fred = database.add_evidence_basket(
        EvidenceBasketCreate(
            evidence_type="chart",
            title="FRED 利率",
            payload={
                "storage_mode": "reference_only",
                "provider": "FRED",
                "series": [{"series_id": "DGS10"}],
            },
            source_summary="FRED · DGS10",
            origin_page="chart-lab",
            topic_id=topic.id,
        )
    )
    unassigned = database.add_evidence_basket(
        EvidenceBasketCreate(
            evidence_type="snapshot",
            title="市场快照",
            payload={"snapshot_type": "market_brief"},
            source_summary="AKShare · Chinamoney",
            origin_page="research-desk",
        )
    )

    assert [
        item.id
        for item in database.list_evidence_basket(
            topic_id=topic.id,
            include_unassigned=False,
        )
    ] == [fred.id]
    assert [
        item.id for item in database.list_evidence_basket(source="fred")
    ] == [fred.id]
    assert [
        item.id
        for item in database.list_evidence_basket(origin_page="research-desk")
    ] == [unassigned.id]
    assert database.list_evidence_basket(date_from="2099-01-01") == []

    assert database.delete_evidence_basket_items([fred.id, unassigned.id, fred.id]) == 2
    assert database.list_evidence_basket() == []


def test_topic_component_configs_are_normalized_and_bounded() -> None:
    fred = ResearchTopicComponent(
        id="fred",
        component_type="fred_chart",
        title="FRED",
        config={"series": ["dgs10", "DGS10"], "years": 5, "transform": "level"},
    )
    assert fred.config["series"] == ["DGS10"]

    with pytest.raises(ValueError, match="FRED 组件序列必须为列表"):
        ResearchTopicComponent(
            id="bad-fred",
            component_type="fred_chart",
            title="错误 FRED",
            config={"series": "DGS10", "years": 5, "transform": "level"},
        )

    with pytest.raises(ValueError, match="2–8 个三位经济体代码"):
        ResearchTopicComponent(
            id="world",
            component_type="sovereign_compare",
            title="主权",
            config={
                "countries": ["CHN"],
                "indicator": "NY.GDP.MKTP.KD.ZG",
                "start_year": 2020,
                "end_year": 2026,
            },
        )
    with pytest.raises(ValueError, match="不得包含观测值"):
        EvidenceBasketCreate(
            evidence_type="chart",
            title="不安全 FRED 证据",
            source_summary="FRED · DGS10",
            payload={
                "storage_mode": "reference_only",
                "provider": "FRED",
                "values": [4.2],
            },
            origin_page="chart-lab",
        )


def test_topic_library_scales_to_50_items_with_one_connection(tmp_path) -> None:
    database = Database(tmp_path / "topic-scale.db")
    created = [
        create_topic_from_template(
            database,
            ResearchTopicTemplateCreate(
                template_id="blank",
                title=f"规模专题 {index:02d}",
            ),
        )
        for index in range(50)
    ]
    database.update_research_topic(
        created[12].id,
        ResearchTopicUpdate(status="review"),
    )

    connection_count = 0
    original_connect = database._connect

    @contextmanager
    def counted_connect():
        nonlocal connection_count
        connection_count += 1
        with original_connect() as connection:
            yield connection

    database._connect = counted_connect  # type: ignore[method-assign]
    topics = database.list_research_topics(limit=100)

    assert len(topics) == 50
    assert connection_count == 1
    assert database.list_research_topics(query="规模专题 12")[0].id == created[12].id
    assert database.list_research_topics(status="review")[0].id == created[12].id
