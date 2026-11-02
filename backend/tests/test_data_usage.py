import importlib
import sys

from fastapi.testclient import TestClient


def test_fred_responses_are_not_http_cached_and_catalog_separates_rights(tmp_path, monkeypatch):
    monkeypatch.setenv("AKDESK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AKDESK_DEMO", "1")
    monkeypatch.setenv("AKDESK_NO_BROWSER", "1")
    monkeypatch.delenv("AKDESK_FRED_API_KEY", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    sys.modules.pop("app.main", None)
    main = importlib.import_module("app.main")
    with TestClient(main.app) as client:
        response = client.get("/api/v1/macro/catalog")
        assert response.status_code == 200
        assert "no-store" in response.headers["cache-control"]
        assert client.get("/api/v1/macro/unknown").headers["pragma"] == "no-cache"
        assert "no-store" in client.get("/api/v1/release-reviews/0/evaluate").headers["cache-control"]
        catalog = client.get("/api/v1/connectors").json()
        sources = {item["id"]: item for item in catalog["connectors"]}
        assert sources["akshare"]["name"] == "Python AKShare"
        assert "LICENSE" in sources["akshare"]["license_url"]
        assert "introduction" in sources["akshare"]["terms_url"]
        assert "质量校验不是授权校验" in sources["akshare"]["persistence_notice"]
        assert "不导出数值" in sources["fred"]["persistence_notice"]
        assert "public-licenses" in sources["world_bank"]["terms_url"]
        assert "2026-11-02" in catalog["policy"]
