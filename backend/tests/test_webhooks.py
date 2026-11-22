from __future__ import annotations

import json

import httpx
import pytest

from backend.app import webhooks


def _configured(monkeypatch, path="handover"):
    monkeypatch.setenv("BRAIN_N8N_PROJECTS", json.dumps({"Design": {
        "url": f"https://automation.example/webhook/{path}", "project_key": "ifc-test", "token_env": "BRAIN_TEST_HOOK_TOKEN"}}))
    monkeypatch.setenv("BRAIN_TEST_HOOK_TOKEN", "test-authentication-not-a-real-secret")


def test_preview_is_offline_and_send_records_only_the_reviewed_payload(tmp_path, monkeypatch):
    project = {"id": "design", "rel": "Design"}
    monkeypatch.delenv("BRAIN_N8N_PROJECTS", raising=False)
    assert not webhooks.list_events(tmp_path, project)["enabled"]
    _configured(monkeypatch)
    called = []

    def fake_post(config, payload):
        called.append((config["url"], payload))
        if len(called) == 1:
            raise httpx.ReadTimeout("unknown delivery")
        return 202

    monkeypatch.setattr(webhooks, "_post", fake_post)
    draft = webhooks.preview(project, "ifc_handover_ready")
    assert not called and not (tmp_path / ".brain").exists()
    assert set(draft["payload"]) == {"id", "type", "project_key", "created_at"}
    assert draft["destination"] == "https://automation.example"
    with pytest.raises(ValueError, match="changed"):
        webhooks.send(tmp_path, project, {**draft["payload"], "type": "test"}, draft["expires"], draft["confirmation"])
    assert not called
    result = webhooks.send(tmp_path, project, draft["payload"], draft["expires"], draft["confirmation"])
    assert result["status"] == "delivery unknown"
    _configured(monkeypatch, "different-workflow")
    with pytest.raises(ValueError, match="cannot be retried"):
        webhooks.retry(tmp_path, project, result["id"])
    _configured(monkeypatch)
    retried = webhooks.retry(tmp_path, project, result["id"])
    assert retried["status"] == "accepted" and len(retried["attempts"]) == 2
    assert called[0] == called[1]
    with pytest.raises(ValueError, match="already submitted"):
        webhooks.send(tmp_path, project, draft["payload"], draft["expires"], draft["confirmation"])
    with pytest.raises(ValueError, match="cannot be retried"):
        webhooks.retry(tmp_path, project, result["id"])
    stored = next((tmp_path / ".brain").glob("**/*.json")).read_text(encoding="utf-8")
    assert "test-authentication" not in stored and "/webhook/" not in stored


def test_transport_does_not_follow_redirects_or_emit_credentials_in_payload(monkeypatch):
    attempted = []
    def handler(request):
        attempted.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example/"})
    client = httpx.Client
    monkeypatch.setattr(webhooks.httpx, "Client", lambda **options: client(**options, transport=httpx.MockTransport(handler)))
    payload = {"id": "e123", "type": "test", "project_key": "test", "created_at": "timestamp"}
    assert webhooks._post({"url": "https://automation.example/", "token": "test-token"}, payload) == 302
    assert len(attempted) == 1 and attempted[0].headers["idempotency-key"] == "e123"
    assert attempted[0].headers["authorization"] == "Bearer test-token"
    assert json.loads(attempted[0].content) == payload
