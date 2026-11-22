from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from backend.app import project_records
from brain_mcp import session_start


def test_hook_sends_only_whitelisted_metadata_to_loopback(monkeypatch):
    sent = []
    class Connection:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("127.0.0.1", 8741, 2)

        def request(self, method, path, body, headers):
            sent.append((method, path, json.loads(body)))

        def getresponse(self):
            return self

        def read(self, size):
            return b'{"additionalContext":"Reviewed context"}'

        def close(self):
            pass

        status = 200

    monkeypatch.setattr(session_start.http.client, "HTTPConnection", Connection)
    assert session_start.request_context({"source": "new", "cwd": "C:/project", "sessionId": "one", "initialPrompt": "private"},
                                         "design") == {"additionalContext": "Reviewed context"}
    assert sent[0][2] == {"cwd": "C:/project", "session": "one"}
    assert session_start.request_context({"source": [], "cwd": "C:/project"}, "design") == {}
    assert session_start.request_context({"source": "new", "cwd": "C:/project"}, "../other") == {}


def test_hook_backend_checks_opt_in_exact_workspace_and_records_uncertain_receipt(tmp_path, monkeypatch):
    from backend.app.main import create_app

    design = tmp_path / "design"
    design.mkdir()
    (design / "README.md").write_text("BIM design handover", encoding="utf-8")
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.setenv("BRAIN_ENABLE_PROJECT_RECALL", "1")
    monkeypatch.setenv("BRAIN_RECALL_RECEIPTS", "1")
    monkeypatch.delenv("BRAIN_AUTO_RECALL_PROJECTS", raising=False)
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    with TestClient(create_app()) as client:
        for _ in range(100):
            if client.get("/api/health").json()["phase"] == "ready":
                break
            time.sleep(.02)
        endpoint = "/api/project-records/design/session-start"
        assert client.post(endpoint, json={"cwd": str(design)}).json() == {}
        monkeypatch.setenv("BRAIN_AUTO_RECALL_PROJECTS", '["design"]')
        assert client.post(endpoint, json={"cwd": str(tmp_path)}).json() == {}
        result = client.post(endpoint, json={"cwd": str(design), "session": "new chat"}).json()
        assert json.loads(result["additionalContext"])["project"] == "design"
        receipts = project_records.receipts(tmp_path, {"rel": "design"})
        assert receipts[0]["integration"] == "Copilot sessionStart" and "not confirmed" in receipts[0]["delivery"]
