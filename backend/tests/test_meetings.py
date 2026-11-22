from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.app import meetings


NOTES = """
# BIM coordination
## Decisions
- Use survey origin for IFC handover
## Actions
- Recheck riser clearance | Owner: Sam | Due: 2026-11-25
- Update the issue register
## Notes
- unapprovedprivateparagraph
```
Action: example inside a code block
```
""".lstrip("\n")


def test_draft_keeps_evidence_and_does_not_infer_owner():
    result = meetings.draft(NOTES.replace("\n", "\r\n"))
    assert result["source_id"] == meetings.draft(NOTES)["source_id"]
    decision, action, open_action = result["items"]
    assert (decision["kind"], decision["line"]) == ("decision", 3)
    assert (action["kind"], action["line"], action["owner"], action["due"]) == ("action", 5, "Sam", "2026-11-25")
    assert "Owner: Sam" in action["excerpt"]
    assert open_action["owner"] is None and open_action["due"] is None


def test_selected_meeting_items_are_local_project_scoped_and_idempotent(tmp_path, monkeypatch):
    from backend.app.main import create_app

    for name in ("coordination", "other"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text("BIM project", encoding="utf-8")
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    endpoint = "/api/meetings/coordination"
    with TestClient(create_app()) as client:
        for _ in range(100):
            if client.get("/api/health").json()["phase"] == "ready":
                break
            time.sleep(.02)
        preview = client.post(f"{endpoint}/preview", json={"notes": NOTES}).json()
        assert client.get(endpoint).json()["items"] == []
        assert not (tmp_path / ".brain" / "meetings").exists()
        payload = {"notes": NOTES, "source_name": "Coordination.md", "source_id": preview["source_id"],
                   "items": [{"line": 5, "text": "Check riser C clearance", "owner": "Sam", "due": "2026-11-25"}]}
        assert client.post(f"{endpoint}/approve", json={**payload, "notes": NOTES + "Changed"}).status_code == 400
        assert client.post(f"{endpoint}/approve", json={**payload, "items": [{"line": 999, "text": "No evidence"}]}).status_code == 400
        assert client.post(f"{endpoint}/approve", headers={"Origin": "https://example.com"}, json=payload).status_code == 403
        assert client.post(f"{endpoint}/approve", json=payload).json()["added"] == 1
        assert client.post(f"{endpoint}/approve", json=payload).json()["already_saved"] == 1
        saved = client.get(endpoint).json()["items"]
        assert len(saved) == 1 and saved[0]["text"] == "Check riser C clearance"
        assert saved[0]["source_name"] == "Coordination.md" and saved[0]["line"] == 5
        assert client.get("/api/meetings/other").json()["items"] == []
    stored = list((tmp_path / ".brain" / "meetings").glob("**/*.json"))
    assert len(stored) == 1 and "unapprovedprivateparagraph" not in stored[0].read_text(encoding="utf-8")
