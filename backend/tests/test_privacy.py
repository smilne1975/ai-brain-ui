from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from backend.app import scanner, store
from backend.app.llm import resolve_provider
from backend.app.mcp_tools import load_index


def test_exclusions_precede_index_and_signature(tmp_path, monkeypatch):
    (tmp_path / "Public" / "nested-private").mkdir(parents=True)
    (tmp_path / "Private Client").mkdir()
    (tmp_path / "Public" / "design.md").write_text("BIM design clearance", encoding="utf-8")
    (tmp_path / "Public" / "BRAIN_HANDOFF.md").write_text("privatehistorysentinel", encoding="utf-8")
    private = tmp_path / "Public" / "nested-private" / "classified.md"
    private.write_text("privatenestedsentinel", encoding="utf-8")
    (tmp_path / "Private Client" / "client.md").write_text("privateclientsentinel", encoding="utf-8")
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "scan.sqlite"))
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    old = scanner.build_brain(tmp_path)
    store.save_scan(tmp_path, scanner.signature(tmp_path), old)
    assert load_index(tmp_path)["brain"]

    monkeypatch.setenv("BRAIN_PRIVATE_FOLDERS", json.dumps(["Private Client", "Public/nested-private"]))
    assert load_index(tmp_path)["brain"] is None
    assert resolve_provider() is None
    signature = scanner.signature(tmp_path)
    private.write_text("replacementprivatesentinel", encoding="utf-8")
    assert scanner.signature(tmp_path) == signature
    brain = scanner.build_brain(tmp_path)
    assert brain["stats"]["projects"] == brain["stats"]["files"] == 1
    assert brain["coverage"]["counts"] == {"skipped": 0, "unreadable": 0, "partial": 0}
    assert brain["files"][0]["rel"] == "design.md"
    assert not any(word in json.dumps(brain) for word in ("sentinel", "Private Client", "nested-private", "classified.md"))
    excluded = next(rec for rec in old["files"] if rec["name"] == "classified.md")
    assert scanner._resolve_under_root(tmp_path, excluded) is None


def test_invalid_rules_fail_closed(tmp_path, monkeypatch):
    (tmp_path / "secret.md").write_text("not available", encoding="utf-8")
    for raw in ('["../sibling"]', '["C:/Projects"]', '[]', 'not json'):
        monkeypatch.setenv("BRAIN_PRIVATE_FOLDERS", raw)
        result = scanner.build_brain(tmp_path)
        assert result["private_policy"] == "invalid"
        assert not result["files"] and not result["projects"]


def test_private_folders_across_http_search_sharing_and_old_outputs(tmp_path, monkeypatch):
    from backend.app.main import create_app

    for name in ("Public", "Private"):
        (tmp_path / name).mkdir()
    (tmp_path / "Public" / "design.md").write_text("BIM clearance for risers", encoding="utf-8")
    (tmp_path / "Private" / "secret.md").write_text("proprietaryquasarsentinel", encoding="utf-8")
    stale = tmp_path / ".brain" / "answers" / "public"
    stale.mkdir(parents=True)
    (stale / "old.md").write_text("# Prior answer\nproprietaryquasarsentinel", encoding="utf-8")
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "scan.sqlite"))
    monkeypatch.setenv("BRAIN_PRIVATE_FOLDERS", '["Private"]')
    monkeypatch.setenv("BRAIN_COPILOT_CHATS", "1")
    with TestClient(create_app()) as client:
        for _ in range(100):
            if client.get("/api/health").json()["phase"] == "ready":
                break
            time.sleep(.02)
        scan = client.get("/api/brain").json()
        assert scan["privacy"] == "active"
        assert "private_policy" not in scan and "signature" not in scan
        assert scan["stats"]["projects"] == 1 and scan["stats"]["files"] == 1
        assert "Private" not in json.dumps(scan)
        for endpoint in ("/api/timeline", "/api/briefs", "/api/cards", "/api/digest", "/api/knowledge", "/api/chats"):
            response = client.get(endpoint)
            assert response.status_code == 200 and "proprietaryquasarsentinel" not in response.text
        assert client.get("/api/chats").json()["sessions"] == []
        assert client.get("/api/file", params={"file_id": "private:secret.md"}).status_code == 404
        reply = client.post("/api/ask", json={"question": "proprietaryquasarsentinel"}).json()
        assert reply["evidence"] == [] and reply["citations"] == []
        assert client.post("/api/ask", json={"question": "clearance for risers"}).json()["evidence"]
        assert client.post("/api/digest/export").status_code == 403
        assert client.post("/api/brief/public/handoff").status_code == 403
        result = client.post("/mcp", json={"id": 1, "method": "tools/call", "params": {"name": "list_projects"}}).json()
        assert "Agent sharing is unavailable" in result["error"]["message"]
        assert (stale / "old.md").exists()
