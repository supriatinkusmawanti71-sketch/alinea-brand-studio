import io
from zipfile import ZipFile

from fastapi.testclient import TestClient

from apps.api.app.main import app


def test_live_health() -> None:
    response = TestClient(app).get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_development_environment_uses_fake_models(monkeypatch) -> None:
    from apps.api.app.config import get_settings

    # Environment variables override the developer's local .env, keeping this
    # test independent of whichever provider is configured on the machine.
    monkeypatch.setenv("TEXT_MODEL_PROVIDER", "fake")
    monkeypatch.setenv("IMAGE_MODEL_PROVIDER", "fake")
    get_settings.cache_clear()
    try:
        response = TestClient(app).get("/api/v1/dev/environment")

        assert response.status_code == 200
        assert response.json()["text_model_provider"] == "fake"
        assert response.json()["image_model_provider"] == "fake"
    finally:
        get_settings.cache_clear()


def test_development_demo_flow_exposes_project_state_contract() -> None:
    response = TestClient(app).get("/api/v1/dev/demo-flow")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["id"] == "demo-project-001"
    assert payload["current_stage"] == "LOGO"
    assert payload["stage_runs"]["DIRECTIONS"]["status"] == "SUCCEEDED"
    assert payload["stage_runs"]["LOGO"]["status"] == "QUEUED"
    first_direction = payload["versions"]["DIRECTIONS"]["output"]["directions"][0]
    assert first_direction["id"] == "direction-001"
    assert payload["decisions"][0]["action"] == "SELECT_VERSION"
    assert payload["task"]["status"] == "WAITING_USER"
    assert len(payload["result"]["items"]) == 3


def test_development_completed_demo_exports_are_available() -> None:
    client = TestClient(app)

    flow_response = client.get("/api/v1/dev/demo-completed-flow")
    manifest_response = client.get("/api/v1/dev/demo-proposal-manifest")
    markdown_response = client.get("/api/v1/dev/demo-proposal.md")
    zip_response = client.get("/api/v1/dev/demo-proposal.zip")

    assert flow_response.status_code == 200
    assert flow_response.json()["project"]["status"] == "COMPLETED"
    assert flow_response.json()["current_stage"] == "PROPOSAL"

    assert manifest_response.status_code == 200
    manifest_payload = manifest_response.json()
    assert manifest_payload["project_id"] == "demo-completed-project-001"
    assert manifest_payload["title"] == "演示完成品牌 品牌概念提案"
    assert len(manifest_payload["asset_refs"]) == 4

    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert markdown_response.headers["content-disposition"] == (
        'attachment; filename="demo-proposal.md"'
    )
    assert "# 演示完成品牌 品牌说明" in markdown_response.text

    assert zip_response.status_code == 200
    assert zip_response.headers["content-type"].startswith("application/zip")
    assert zip_response.headers["content-disposition"] == (
        'attachment; filename="demo-proposal.zip"'
    )
    with ZipFile(io.BytesIO(zip_response.content)) as bundle:
        assert bundle.namelist() == ["品牌说明.md", "proposal-manifest.json"]
