from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend.app import ask, clips, scanner

_CLIP = '---\ntitle: "IFC project standards"\nsource: "https://example.com/ifc"\ncreated: 2026-11-22\n---\n\nCheck the quasarclearance measurement before exporting.\n'


def test_clip_metadata_parser_rejects_nonweb_and_credentialed_urls():
    result = clips.preview(_CLIP, "clip.md")
    assert result["title"] == "IFC project standards"
    assert result["captured_at"] == "2026-11-22" and result["url"] == "https://example.com/ifc"
    for bad in ("file:///somewhere", "https://name:password@example.com/ifc", "javascript:alert(1)"):
        with pytest.raises(ValueError, match="original HTTP or HTTPS URL"):
            clips.preview(_CLIP.replace("https://example.com/ifc", bad), "clip.md")


def test_approved_clip_is_scope_bound_local_and_reversible(tmp_path, monkeypatch):
    from backend.app.main import create_app

    for name in ("coordination", "other"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text("BIM project", encoding="utf-8")
    original = tmp_path / ".input" / "saved.md"
    original.parent.mkdir()
    original.write_text(_CLIP, encoding="utf-8")
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    endpoint = "/api/web-clips/coordination"
    with TestClient(create_app()) as client:
        for _ in range(100):
            if client.get("/api/health").json()["phase"] == "ready":
                break
            time.sleep(.02)
        body = {"filename": "saved.md", "markdown": _CLIP}
        preview = client.post(f"{endpoint}/preview", json=body).json()
        query = {"question": "quasarclearance"}
        assert client.post("/api/ask", json=query).json()["evidence"] == []
        assert client.get(endpoint).json()["items"] == []
        payload = {**body, "expected_id": preview["id"]}
        assert client.post(f"{endpoint}/approve", json={**payload, "markdown": _CLIP + "changed"}).status_code == 400
        assert client.post(f"{endpoint}/approve", json=payload).json()["created"]
        assert not client.post(f"{endpoint}/approve", json=payload).json()["created"]
        assert client.get("/api/web-clips/other").json()["items"] == []
        assert client.post("/api/ask", json={**query, "project_ids": ["other"]}).json()["evidence"] == []
        hit = client.post("/api/ask", json=query).json()["evidence"][0]
        assert hit["kind"] == "clip" and hit["source_url"] == "https://example.com/ifc"
        sid = hit["id"]
        assert client.get("/api/knowledge").json()["available_clips"][0]["id"] == sid
        preview_path = "/api/knowledge/coordination/preview"
        params = {"topic": "IFC standards", "source_ids": sid}
        draft = client.get(preview_path, params=params).json()
        assert [src["id"] for src in draft["sources"]] == [sid]
        assert "https://example.com/ifc" in draft["content"]
        assert client.get("/api/knowledge/other/preview", params=params).json()["sources"] == []
        body = {"topic": draft["topic"], "source_ids": [sid], "expected_revision": None,
                "expected_sources": {sid: draft["sources"][0]["sha256"]},
                "content": draft["content"] + '> "Check the quasarclearance measurement before exporting." - https://example.com/ifc'}
        endpoint_knowledge = "/api/knowledge/coordination"
        false_quote = {**body, "content": body["content"].replace('> "Check the', '> "Never check the')}
        assert client.post(f"{endpoint_knowledge}/approve", json=false_quote).status_code == 409
        assert client.post(f"{endpoint_knowledge}/approve", json=body).status_code == 200
        state = f"{endpoint}/{preview['id']}/state"
        assert not client.post(state, json={"active": False}).json()["active"]
        assert not any(item["kind"] == "clip" for item in client.post("/api/ask", json=query).json()["evidence"])
        index = client.get("/api/knowledge").json()
        assert index["pages"][0]["stale_sources"] == [sid]
        assert index["source_impact"][0]["status"] == "clip removed or changed"
        assert client.post(state, json={"active": True}).json()["active"]
        assert client.post("/api/ask", json=query).json()["evidence"]
        assert client.get("/api/knowledge").json()["pages"][0]["stale_sources"] == []
    assert original.read_text(encoding="utf-8") == _CLIP


def test_matching_web_clip_does_not_call_configured_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "complete", lambda *_args, **_kwargs: pytest.fail("clip should stay local"))
    (tmp_path / "p").mkdir()
    brain = scanner.build_brain(tmp_path)
    clip = {**clips.preview(_CLIP, "saved.md"), "project_id": "p"}
    result = ask.answer(brain, "quasarclearance", None, {"display": "Test model"}, web_clips=[clip])
    assert result["provider"] == "heuristic" and "approved web clip" in result["answer"]
