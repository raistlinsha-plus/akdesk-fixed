import importlib
import sys
import time
from datetime import datetime

from fastapi.testclient import TestClient

from app import demo_data
from app.models import Dataset, SourceMeta


def test_api_lifespan_report_archive_and_health(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AKDESK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AKDESK_DEMO", "1")
    monkeypatch.setenv("AKDESK_NO_BROWSER", "1")
    sys.modules.pop("app.main", None)
    main = importlib.import_module("app.main")

    with TestClient(main.app) as client:
        assert client.get("/api/v1/health").status_code == 200
        missing_api = client.get("/api/v1/does-not-exist")
        assert missing_api.status_code == 404
        assert missing_api.headers["content-type"].startswith("application/json")
        assert missing_api.json()["detail"] == "API 路径不存在"
        connectors = client.get("/api/v1/connectors").json()
        assert {item["id"] for item in connectors["connectors"]} == {
            "akshare",
            "fred",
            "world_bank",
            "gdelt",
        }
        assert all("api_key" not in item for item in connectors["connectors"])
        info = client.get("/api/v1/info").json()
        descriptors = info["runtime"]["file_descriptors"]
        assert descriptors["open"] is None or descriptors["open"] >= 0
        assert descriptors["soft_limit"] is None or descriptors["soft_limit"] > 0
        fx_pairs = client.get("/api/v1/fx/pairs")
        assert fx_pairs.status_code == 200
        assert fx_pairs.json()["data"][0]["code"] == "EURUSD"
        fx_reference = client.get("/api/v1/fx/rmb-reference")
        assert fx_reference.status_code == 200
        assert fx_reference.json()["data"][0]["code"] == "USDCNY"
        fx_history = client.get(
            "/api/v1/history"
            "?adapter=fx_rmb_reference&metric=mid&series=USDCNY&days=45"
        )
        assert fx_history.status_code == 200
        assert fx_history.json()["adapter"] == "fx_rmb_reference"
        report_response = client.get("/api/v1/research/daily-report")
        assert report_response.status_code == 200
        report = report_response.json()
        assert report["report_date"]
        assert report["confidence"]["level"] == "low"
        assert report["data_health"]["available"] == 0

        archive = client.get("/api/v1/research/daily-reports").json()
        assert archive[0]["report_date"] == report["report_date"]

        invalid = client.get("/api/v1/research/daily-report?date=bad-date")
        assert invalid.status_code == 422

        catalog = client.get("/api/v1/macro/catalog").json()
        assert any(item["series_id"] == "DGS10" for item in catalog)
        integrations = client.get("/api/v1/settings/integrations").json()
        assert "configured" in integrations["fred"]
        assert integrations["aihubmix"]["model"] == "deepseek-v4-flash-think"
        assert "api_key" not in str(integrations["aihubmix"])
        main.aihubmix_secret_store._keychain_loaded = True
        main.aihubmix_secret_store._cached_key = "sk-" + "A1" * 20
        main.ai_assistant_service.credential_changed()
        main.ai_assistant_service._request_override = lambda payload, _key: {
            "choices": [{"message": {"content": f"测试回答：{payload['model']}"}}],
            "usage": {"total_tokens": 42},
        }
        assert client.post(
            "/api/v1/ai/assistant",
            json={
                "scenario": "help",
                "question": "我该从哪里开始？",
                "current_page": "dashboard",
                "confirm_external_processing": False,
            },
        ).status_code == 428
        ai_answer = client.post(
            "/api/v1/ai/assistant",
            json={
                "scenario": "help",
                "question": "我该从哪里开始？",
                "current_page": "dashboard",
                "confirm_external_processing": True,
            },
        )
        assert ai_answer.status_code == 200
        assert ai_answer.json()["model"] == "deepseek-v4-flash-think"
        assert ai_answer.json()["persisted"] is False
        runtime_settings = client.patch(
            "/api/v1/ai/runtime",
            json={
                "daily_call_limit": 20,
                "daily_token_limit": 100_000,
                "page_insights": {
                    "market": {"enabled": True, "trigger": "manual"},
                    "project": {"enabled": False, "trigger": "manual"},
                    "credit": {"enabled": False, "trigger": "manual"},
                    "topic": {"enabled": False, "trigger": "manual"},
                },
            },
        )
        assert runtime_settings.status_code == 200
        insight_before = client.get("/api/v1/ai/insights/market").json()
        assert insight_before["status"] == "never_generated"
        assert insight_before["can_generate"] is True
        assert client.post(
            "/api/v1/ai/insights/market",
            json={
                "trigger_reason": "manual",
                "confirm_external_processing": False,
            },
        ).status_code == 428
        insight_start = client.post(
            "/api/v1/ai/insights/market",
            json={
                "trigger_reason": "manual",
                "confirm_external_processing": True,
            },
        )
        assert insight_start.status_code == 200
        assert insight_start.json()["status"] == "generating"
        insight_after = insight_start.json()
        for _ in range(30):
            insight_after = client.get("/api/v1/ai/insights/market").json()
            if insight_after["status"] == "ready":
                break
            time.sleep(0.01)
        assert insight_after["status"] == "ready"
        assert insight_after["summary"].startswith("测试回答")
        macro_search = client.get("/api/v1/search?q=DGS10").json()
        assert macro_search[0]["object_type"] == "macro"
        assert {item["id"] for item in client.get("/api/v1/research/templates").json()} >= {
            "rates_direction",
            "macro_release",
            "credit_observation",
        }
        empty_candidates = client.get("/api/v1/credit/candidates").json()
        assert empty_candidates["candidates"] == []
        assert empty_candidates["candidate_source"]["eligible"] is False

        project_response = client.post(
            "/api/v1/research/projects",
            json={"title": "测试研究项目", "question": "利率如何变化？"},
        )
        assert project_response.status_code == 200
        project = project_response.json()
        assert project["status"] == "draft"
        assert client.get("/api/v1/research/overview").json()["projects"]["total"] == 1
        assert {
            item["id"]
            for item in client.get("/api/v1/research/topic-templates").json()
        } >= {"china_rates", "sino_us_rates", "rmb_rates"}
        topic_response = client.post(
            "/api/v1/research/topics/from-template",
            json={"template_id": "sino_us_rates", "project_ids": [project["id"]]},
        )
        assert topic_response.status_code == 200
        topic = topic_response.json()
        assert topic["research_object"]["object_type"] == "rates_theme"
        assert topic["projects"][0]["id"] == project["id"]
        filtered_topics = client.get(
            "/api/v1/research/topics?q=中美利率&status=active&limit=50"
        )
        assert filtered_topics.status_code == 200
        assert [item["id"] for item in filtered_topics.json()] == [topic["id"]]
        workspace = client.get(
            f"/api/v1/research/topics/{topic['id']}/workspace"
        )
        assert workspace.status_code == 200
        assert workspace.json()["topic"]["id"] == topic["id"]
        assert workspace.json()["project_summaries"][0]["project_id"] == project["id"]
        topic_search = client.get("/api/v1/search?q=中美利率").json()
        assert topic_search[0]["object_type"] == "topic"
        assert topic_search[0]["page"] == "topics"
        basket_response = client.post(
            "/api/v1/research/evidence-basket",
            json={
                "evidence_type": "chart",
                "title": "DGS10 引用",
                "source_summary": "FRED · DGS10",
                "payload": {
                    "storage_mode": "reference_only",
                    "provider": "FRED",
                    "series": [{"series_id": "DGS10"}],
                    "transform": "level",
                },
                "origin_page": "chart-lab",
                "topic_id": topic["id"],
            },
        )
        assert basket_response.status_code == 200
        committed = client.post(
            "/api/v1/research/evidence-basket/commit",
            json={
                "project_id": project["id"],
                "item_ids": [basket_response.json()["id"]],
                "topic_id": topic["id"],
            },
        )
        assert committed.status_code == 200
        assert client.get("/api/v1/research/evidence-basket").json() == []
        temporary_basket = client.post(
            "/api/v1/research/evidence-basket",
            json={
                "evidence_type": "snapshot",
                "title": "待清理市场证据",
                "source_summary": "AKShare · test",
                "payload": {"snapshot_type": "test"},
                "origin_page": "research-desk",
            },
        ).json()
        filtered_basket = client.get(
            "/api/v1/research/evidence-basket?source=akshare&origin_page=research-desk"
        ).json()
        assert [item["id"] for item in filtered_basket] == [temporary_basket["id"]]
        assert client.post(
            "/api/v1/research/evidence-basket/batch-delete",
            json={"item_ids": [temporary_basket["id"]]},
        ).json()["deleted"] == 1
        assert client.get(
            f"/api/v1/research/projects/{project['id']}/summary"
        ).json()["supporting_evidence"][0]["title"] == "DGS10 引用"
        assert {
            item["event_type"]
            for item in client.get(
                f"/api/v1/research/topics/{topic['id']}/timeline"
            ).json()
        } >= {"fred_reference", "project_created"}
        timeline_page = client.get(
            f"/api/v1/research/topics/{topic['id']}/timeline?limit=1&paged=true"
        ).json()
        assert timeline_page["total"] >= 2
        assert len(timeline_page["items"]) == 1
        assert timeline_page["has_more"] is True
        assert client.get(
            f"/api/v1/research/topics/{topic['id']}/timeline?paged=true&before_id=evidence-1"
        ).status_code == 422
        assert client.patch(
            f"/api/v1/research/topics/{topic['id']}",
            json={"status": "review"},
        ).json()["status"] == "review"
        topic_export = client.get(
            f"/api/v1/research/topics/{topic['id']}/export"
        )
        assert topic_export.status_code == 200
        assert "中美利率联动专题" in topic_export.text

        template_payload = {
            "template_id": "macro_release",
            "object_type": "macro",
            "object_id": "CPIAUCSL",
            "object_name": "美国 CPI",
            "source": "FRED",
        }
        template_project = client.post(
            "/api/v1/research/projects/from-template", json=template_payload
        )
        duplicate_project = client.post(
            "/api/v1/research/projects/from-template", json=template_payload
        )
        assert template_project.status_code == 200
        assert duplicate_project.json()["id"] == template_project.json()["id"]
        assert len(client.get("/api/v1/research/projects").json()) == 2

        issuer_project = client.post(
            "/api/v1/research/projects/from-template",
            json={
                "template_id": "credit_observation",
                "object_type": "issuer",
                "object_id": "测试发行人",
                "object_name": "测试发行人",
                "source": "信用观察 R2",
            },
        )
        assert issuer_project.status_code == 200
        assert "issuer" in issuer_project.json()["tags"]
        assert client.post(
            "/api/v1/research/projects/from-template",
            json={
                "template_id": "credit_observation",
                "object_type": "issuer",
                "object_id": "测试发行人",
                "object_name": "测试发行人",
            },
        ).json()["id"] == issuer_project.json()["id"]
        issuer_topic = client.post(
            "/api/v1/research/topics/from-issuer-events",
            json={
                "issuer": "测试发行人",
                "project_id": issuer_project.json()["id"],
            },
        )
        assert issuer_topic.status_code == 200
        assert issuer_topic.json()["research_object"]["object_type"] == "issuer"
        assert {
            item["component_type"] for item in issuer_topic.json()["components"]
        } >= {"event_radar", "project_summary"}
        assert client.post(
            "/api/v1/research/topics/from-issuer-events",
            json={"issuer": "测试发行人"},
        ).json()["id"] == issuer_topic.json()["id"]

        main.gdelt_service._request_override = lambda _params: {
            "articles": [
                {
                    "url": "https://example.com/issuer-event",
                    "title": "Issuer event",
                    "domain": "example.com",
                    "seendate": "20260723T101500Z",
                    "language": "English",
                    "sourcecountry": "United Kingdom",
                }
            ]
        }
        gdelt = client.get(
            "/api/v1/gdelt/events?query=issuer%20event&days=7&limit=5"
        )
        assert gdelt.status_code == 200
        assert gdelt.json()["data"]["verification_status"] == "unverified_clue"

        entry = client.post(
            f"/api/v1/research/projects/{template_project.json()['id']}/entries",
            json={"entry_type": "task", "title": "核对观测期", "content": "检查频率"},
        )
        assert entry.status_code == 200
        changed_entry = client.patch(
            f"/api/v1/research/entries/{entry.json()['id']}", json={"status": "done"}
        )
        assert changed_entry.json()["status"] == "done"

        unsafe_fred = client.post(
            f"/api/v1/research/projects/{template_project.json()['id']}/evidence",
            json={
                "evidence_type": "chart",
                "title": "不合规官方快照",
                "source_summary": "宏观来源 · FRED",
                "payload": {
                    "storage_mode": "reference_only",
                    "provider": "fred",
                    "series": [{"series_id": "CPIAUCSL", "actual_value": 321.0}],
                },
            },
        )
        assert unsafe_fred.status_code == 422

        settings = client.patch(
            "/api/v1/research/signal-settings",
            json={
                "funding_change_bp": 1.5,
                "curve_change_bp": 1.2,
                "curve_spread_bp": 25,
                "futures_change_pct": 0.2,
                "bond_change_bp": 2.5,
            },
        )
        assert settings.status_code == 200
        assert client.get("/api/v1/research/signal-settings").json()["curve_spread_bp"] == 25

        def world_bank_request(path: str, params: dict):
            if path == "/indicator/NY.GDP.MKTP.KD.ZG":
                return [
                    {"page": 1, "pages": 1, "total": 1},
                    [{
                        "id": "NY.GDP.MKTP.KD.ZG",
                        "name": "GDP growth (annual %)",
                        "unit": "",
                        "source": {"id": "2", "value": "World Development Indicators"},
                        "sourceNote": "Annual GDP growth.",
                        "sourceOrganization": "World Bank national accounts data",
                    }],
                ]
            if path == "/country/CHN;USA":
                return [
                    {"page": 1, "pages": 1, "total": 2},
                    [
                        {
                            "id": "CHN", "iso2Code": "CN", "name": "China",
                            "region": {"id": "EAS", "value": "East Asia & Pacific"},
                            "incomeLevel": {"id": "UMC", "value": "Upper middle income"},
                        },
                        {
                            "id": "USA", "iso2Code": "US", "name": "United States",
                            "region": {"id": "NAC", "value": "North America"},
                            "incomeLevel": {"id": "HIC", "value": "High income"},
                        },
                    ],
                ]
            if path == "/country/CHN;USA/indicator/NY.GDP.MKTP.KD.ZG":
                return [
                    {
                        "page": 1, "pages": 1, "total": 4,
                        "lastupdated": "2026-07-13",
                    },
                    [
                        {"countryiso3code": "CHN", "date": "2025", "value": 5.0, "decimal": 1},
                        {"countryiso3code": "USA", "date": "2025", "value": 2.0, "decimal": 1},
                        {"countryiso3code": "CHN", "date": "2024", "value": 4.8, "decimal": 1},
                        {"countryiso3code": "USA", "date": "2024", "value": 2.8, "decimal": 1},
                    ],
                ]
            raise AssertionError((path, params))

        main.world_bank_service._request_override = world_bank_request
        sovereign_catalog = client.get("/api/v1/sovereign/catalog")
        assert sovereign_catalog.status_code == 200
        assert len(sovereign_catalog.json()["indicators"]) == 10
        sovereign = client.get(
            "/api/v1/sovereign/compare"
            "?countries=CHN,USA&indicator=NY.GDP.MKTP.KD.ZG"
            "&start_year=2024&end_year=2025&view=level"
        )
        assert sovereign.status_code == 200
        assert sovereign.json()["data"]["latest_comparable_year"] == 2025
        assert sovereign.json()["data"]["coverage"]["ratio"] == 1
        sovereign_evidence = client.post(
            f"/api/v1/research/projects/{project['id']}/sovereign-snapshot",
            json={
                "country_codes": ["CHN", "USA"],
                "indicator_id": "NY.GDP.MKTP.KD.ZG",
                "start_year": 2024,
                "end_year": 2025,
                "view": "level",
                "note": "比较中美增长",
            },
        )
        assert sovereign_evidence.status_code == 200
        assert (
            sovereign_evidence.json()["payload"]["snapshot_type"]
            == "world_bank_sovereign_comparison"
        )
        assert sovereign_evidence.json()["payload"]["captured_at"]
        assert sovereign_evidence.json()["payload"]["source_fetched_at"]
        assert main.database.world_bank_stats()["points"] == 4

        for adapter, data in {
            "money_rates": demo_data.money_rates(),
            "yield_curves": demo_data.yield_curves(),
            "spot_bonds": demo_data.spot_bonds(),
            "treasury_futures": demo_data.futures(),
        }.items():
            main.service.cache.set(
                adapter,
                Dataset(
                    data=data,
                    meta=SourceMeta(
                        source="API 测试源",
                        observation_time="2026-07-15",
                        fetched_at=datetime.now(),
                        data_state="live",
                    ),
                ),
                3_600,
            )
        brief = client.get("/api/v1/research/market-brief").json()
        assert brief["snapshot_eligible"] is True
        signal_ids = brief["eligible_signal_ids"][:2]
        snapshot = client.post(
            f"/api/v1/research/projects/{project['id']}/market-snapshot",
            json={"signal_ids": signal_ids, "note": "记录今日市场变化"},
        )
        assert snapshot.status_code == 200
        assert snapshot.json()["payload"]["snapshot_type"] == "market_brief"
        assert len(snapshot.json()["payload"]["signals"]) == 2
        restored = client.get(
            f"/api/v1/research/projects/{project['id']}"
        ).json()
        assert {event["event_type"] for event in restored["activity"]} >= {
            "created",
            "evidence_added",
        }

        watch = client.post(
            "/api/v1/watchlists",
            json={"object_type": "bond", "object_id": "240011", "name": "24附息国债11"},
        )
        assert watch.status_code == 200
        enriched = client.get("/api/v1/watchlists/enriched").json()
        assert enriched[0]["quote_status"] == "available"
        assert client.patch(
            f"/api/v1/watchlists/{watch.json()['id']}", json={"group_name": "重点跟踪"}
        ).json()["group_name"] == "重点跟踪"

        candidate_response = client.get("/api/v1/credit/candidates")
        assert candidate_response.status_code == 200
        assert candidate_response.json()["candidate_source"]["eligible"] is True
        credit = client.post(
            "/api/v1/credit/observations",
            json={
                "bond_code": "TEST001",
                "bond_name": "测试信用债",
                "issuer": "测试发行人",
                "maturity_date": "2031-07-15",
                "rating": "AAA",
                "rating_date": "2026-07-14",
                "yield_pct": 2.3,
                "yield_observation_date": "2026-07-15",
                "benchmark_tenor": "5Y",
                "benchmark_yield_pct": 1.8,
                "benchmark_observation_date": "2026-07-15",
                "source_note": "测试核验源",
            },
        )
        assert credit.status_code == 200
        assert client.get("/api/v1/credit/observations").json()["eligible"] == 1
        assert client.patch(
            f"/api/v1/credit/observations/{credit.json()['id']}",
            json={"rating": "AA+", "next_review_date": "2020-01-01"},
        ).json()["rating"] == "AA+"
        credit_workspace = client.get("/api/v1/credit/workspace")
        assert credit_workspace.status_code == 200
        assert credit_workspace.json()["summary"]["issuers"] == 1
        signal = credit_workspace.json()["signals"][0]
        signal_confirmation = client.post(
            f"/api/v1/credit/signals/{signal['id']}/confirm",
            json={
                "note": "接口回归确认",
                "project_id": template_project.json()["id"],
            },
        )
        assert signal_confirmation.json()["note"] == "接口回归确认"
        assert signal_confirmation.json()["research_entry_id"] is not None
        linked_project = client.get(
            f"/api/v1/research/projects/{template_project.json()['id']}"
        ).json()
        assert any(
            entry["title"].startswith("信用信号确认：")
            for entry in linked_project["entries"]
        )
        portfolio = client.post(
            "/api/v1/credit/portfolios",
            json={
                "name": "接口信用组合",
                "observation_ids": [credit.json()["id"]],
            },
        )
        assert portfolio.status_code == 200
        assert portfolio.json()["observation_ids"] == [credit.json()["id"]]
        assert client.get("/api/v1/credit/import/template").status_code == 200
        assert client.get("/api/v1/credit/export?scope=history").status_code == 200
        import_content = (
            "债券代码,债券名称,发行人\n"
            "IMPORT001,批量导入中票,批量导入主体\n"
        ).encode()
        preview = client.post(
            "/api/v1/credit/import?filename=credit.csv",
            content=import_content,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert preview.status_code == 200
        assert preview.json()["valid_rows"] == 1
        committed = client.post(
            "/api/v1/credit/import?filename=credit.csv&commit=true",
            content=import_content,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert committed.status_code == 200
        assert committed.json()["observations"] == 1

        review = client.post(
            "/api/v1/release-reviews",
            json={
                "title": "美国 CPI 发布复盘",
                "series_id": "CPIAUCSL",
                "release_name": "美国 CPI",
                "release_date": "2026-07-15",
                "observation_period": "2026-06-01",
                "expected_value": 321.0,
                "expected_unit": "Index",
                "project_id": template_project.json()["id"],
            },
        )
        assert review.status_code == 200
        assert client.patch(
            f"/api/v1/release-reviews/{review.json()['id']}",
            json={"project_id": 999999},
        ).status_code == 422
        edited_review = client.patch(
            f"/api/v1/release-reviews/{review.json()['id']}",
            json={"title": "美国 CPI 发布复盘（修订）", "series_id": "DGS10"},
        )
        assert edited_review.json()["series_id"] == "DGS10"

        main.macro_service.series = lambda series_id, years, refresh: Dataset(
            data={
                "observations": [{
                    "date": "2026-06-01",
                    "value": 4.25,
                    "realtime_start": "2026-07-15",
                    "realtime_end": "9999-12-31",
                }]
            },
            meta=SourceMeta(
                source="FRED",
                observation_time="2026-06-01",
                fetched_at=datetime.now(),
            ),
        )
        evaluated = client.get(
            f"/api/v1/release-reviews/{review.json()['id']}/evaluate"
        )
        assert evaluated.status_code == 200
        assert evaluated.json()["actual"]["persisted"] is False
        marked = client.post(
            f"/api/v1/release-reviews/{review.json()['id']}/mark-reviewed",
            json={"realtime_start": "2026-07-15"},
        )
        assert marked.status_code == 200

        weekly = client.get("/api/v1/research/weekly-report?end=2026-07-15")
        assert weekly.status_code == 200
        weekly_markdown = client.get(
            "/api/v1/research/weekly-report?end=2026-07-15&format=markdown"
        )
        assert weekly_markdown.status_code == 200
        assert "AKDesk 每周研究复盘" in weekly_markdown.text
        assert "下次复盘" in weekly_markdown.text

        exported = client.get(
            f"/api/v1/research/projects/{template_project.json()['id']}/export"
        )
        assert exported.status_code == 200
        imported = client.post("/api/v1/research/import", json=exported.json())
        assert imported.status_code == 200
        assert imported.json()["title"].endswith("（导入）")

        backup = client.get("/api/v1/research/backup")
        assert backup.status_code == 200 and backup.content.startswith(b"SQLite format 3")
        automatic_backup = client.post("/api/v1/research/backup/auto")
        assert automatic_backup.status_code == 200
        assert automatic_backup.json()["created"] is True
        backup_status = client.get("/api/v1/research/backups")
        assert backup_status.status_code == 200
        assert backup_status.json()["latest"]["name"].startswith("auto-research-")
        restored_backup = client.post(
            "/api/v1/research/backup/restore",
            content=backup.content,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert restored_backup.status_code == 200
        assert main.database.macro_stats()["points"] == 0
        assert main.database.world_bank_stats()["points"] == 4
