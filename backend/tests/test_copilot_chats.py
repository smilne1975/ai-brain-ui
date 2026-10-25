"""Copilot chat logs: several on-disk shapes, matched locally, secrets redacted."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.copilot_chats import load_chats, merge_chats
from backend.app.activity import build_timeline
from backend.app.scanner import build_brain

DEMO = Path(__file__).resolve().parents[2] / "demo-projects"
SENTINEL = "sk-demo-NOTREAL-redact-me"


def _project(root: Path, name: str, filename: str, body: str) -> None:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).write_text(body, encoding="utf-8")


def _ms(when: datetime) -> int:
    return int(when.timestamp() * 1000)


def test_jsonl_windows_uri_and_redact(tmp_path: Path, monkeypatch):
    _project(tmp_path, "inbox-triage", "triage.py", "def triage():\n    return 'billing'\n")
    user = tmp_path / "User"
    store = user / "workspaceStorage" / "hash1"
    (store / "chatSessions").mkdir(parents=True)
    (store / "workspace.json").write_text(
        json.dumps({"folder": "file:///c%3A/Users/me/Documents/inbox-triage"}),
        encoding="utf-8",
    )
    when = datetime.now().astimezone() - timedelta(hours=3)
    initial = {
        "version": 3,
        "creationDate": _ms(when),
        "sessionId": "s1",
        "requests": [
            {"message": {"text": "Please change triage.py"}, "timestamp": _ms(when)}
        ],
    }
    follow = {
        "message": {"text": f"ignore OPENAI_API_KEY={SENTINEL}"},
        "timestamp": _ms(when + timedelta(minutes=5)),
    }
    (store / "chatSessions" / "chat.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"kind": 0, "v": initial}),
                json.dumps({"kind": 2, "k": ["requests"], "v": follow}),
            ]
        ),
        encoding="utf-8",
    )
    (store / "chatSessions" / "broken.json").write_text("{ not json", encoding="utf-8")
    monkeypatch.setenv("BRAIN_COPILOT_CHATS_ROOT", str(user))
    monkeypatch.delenv("BRAIN_COPILOT_LLM", raising=False)
    brain = build_brain(tmp_path)
    payload = load_chats(tmp_path, brain)
    blob = json.dumps(payload)
    assert SENTINEL not in blob
    assert "[redacted" in blob
    assert payload["enabled"] is True
    assert payload["source"] == "override"
    matched = [item for item in payload["sessions"] if item["project_id"] == "inbox-triage"]
    assert len(matched) == 1
    assert matched[0]["source"] == "chatSessions"
    assert "triage.py" in matched[0]["prompt"]
    assert matched[0]["summary_source"] == "heuristic"
    assert any(item["file_id"] == "inbox-triage:triage.py" for item in matched[0]["files"])
    assert len(matched[0]["prompts"]) == 2


def test_legacy_transcript_editing_sqlite_and_global(tmp_path: Path, monkeypatch):
    _project(tmp_path, "agent-scratchpad", "agent.py", "def route_turn():\n    return None\n")
    _project(tmp_path, "local-vision-lab", "label_folder.py", "import PIL\n")
    _project(tmp_path, "meeting-notes-rag", "query.py", "def search():\n    return []\n")
    _project(tmp_path, "prompt-vault", "untitled.md", "# empty\n")
    user = tmp_path / "Code - Insiders" / "User"
    when = datetime.now().astimezone() - timedelta(days=1)

    agent = user / "workspaceStorage" / "agent"
    (agent / "chatSessions").mkdir(parents=True)
    (agent / "workspace.json").write_text(json.dumps({"folder": "file:///Users/me/code/agent-scratchpad"}), encoding="utf-8")
    (agent / "chatSessions" / "old.json").write_text(
        json.dumps(
            {
                "sessionId": "agent-1",
                "creationDate": _ms(when),
                "requests": [{"message": {"text": "Explain agent.py"}, "timestamp": _ms(when)}],
            }
        ),
        encoding="utf-8",
    )

    vision = user / "workspaceStorage" / "vision"
    (vision / "GitHub.copilot-chat" / "transcripts").mkdir(parents=True)
    (vision / "workspace.json").write_text(json.dumps({"workspace": "file:///tmp/local-vision-lab.code-workspace"}), encoding="utf-8")
    (vision / "GitHub.copilot-chat" / "transcripts" / "run.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"type": "session.start", "id": "vision-1", "timestamp": when.isoformat(), "cwd": "local-vision-lab"}),
                json.dumps({"type": "user.message", "timestamp": when.isoformat(), "message": {"content": "Fix label_folder.py"}}),
                json.dumps({"type": "assistant.turn_end", "timestamp": when.isoformat()}),
            ]
        ),
        encoding="utf-8",
    )

    notes = user / "workspaceStorage" / "notes"
    notes.mkdir(parents=True)
    (notes / "workspace.json").write_text(json.dumps({"folder": str(tmp_path / "meeting-notes-rag")}), encoding="utf-8")
    db = notes / "state.vscdb"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
    conn.execute(
        "INSERT INTO ItemTable VALUES (?, ?)",
        (
            "memento/interactive-session",
            json.dumps(
                [
                    {
                        "sessionId": "notes-1",
                        "creationDate": _ms(when),
                        "requests": [{"message": {"text": "Open query.py"}, "timestamp": _ms(when)}],
                    }
                ]
            ),
        ),
    )
    conn.commit()
    conn.close()
    (notes / "chatEditingSessions" / "empty").mkdir(parents=True)
    (notes / "chatEditingSessions" / "empty" / "state.json").write_bytes(b"")

    vault = user / "workspaceStorage" / "vault"
    (vault / "chatEditingSessions" / "edit1").mkdir(parents=True)
    (vault / "workspace.json").write_text(json.dumps({"folder": "prompt-vault"}), encoding="utf-8")
    (vault / "chatEditingSessions" / "edit1" / "state.json").write_text(
        json.dumps({"recentSnapshot": {"entries": [{"resource": {"fsPath": "untitled.md"}}]}}),
        encoding="utf-8",
    )

    (user / "globalStorage" / "emptyWindowChatSessions").mkdir(parents=True)
    (user / "globalStorage" / "emptyWindowChatSessions" / "loose.jsonl").write_text(
        json.dumps({"type": "user.message", "id": "global-1", "timestamp": when.isoformat(), "message": {"text": "Where is agent.py?"}})
        + "\n",
        encoding="utf-8",
    )
    (notes / "state.vscdb.corrupt").write_text("nope", encoding="utf-8")

    monkeypatch.setenv("BRAIN_COPILOT_CHATS_ROOT", str(user))
    brain = build_brain(tmp_path)
    payload = load_chats(tmp_path, brain)
    by_project: dict[str, list[str]] = {}
    for session in payload["sessions"]:
        by_project.setdefault(session["project_id"] or "", []).append(session["source"])
    assert "chatSessions" in by_project["agent-scratchpad"]
    assert "transcript" in by_project["local-vision-lab"]
    assert "state.vscdb" in by_project["meeting-notes-rag"]
    assert "chatEditingSessions" in by_project["prompt-vault"]
    assert "globalStorage" in by_project["agent-scratchpad"]
    assert all(session["summary_source"] == "heuristic" for session in payload["sessions"])


def test_parent_folder_does_not_attach_to_every_project(tmp_path: Path, monkeypatch):
    _project(tmp_path, "alpha", "alpha_only.py", "x = 1\n")
    _project(tmp_path, "beta", "beta_only.py", "y = 2\n")
    user = tmp_path / "User"
    store = user / "workspaceStorage" / "parent"
    (store / "chatSessions").mkdir(parents=True)
    (store / "workspace.json").write_text(json.dumps({"folder": str(tmp_path)}), encoding="utf-8")
    when = datetime.now().astimezone()
    (store / "chatSessions" / "one.json").write_text(
        json.dumps(
            {
                "sessionId": "only-alpha",
                "creationDate": _ms(when),
                "requests": [{"message": {"text": "Edit alpha_only.py"}, "timestamp": _ms(when)}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BRAIN_COPILOT_CHATS_ROOT", str(user))
    brain = build_brain(tmp_path)
    payload = load_chats(tmp_path, brain)
    assert [session["project_id"] for session in payload["sessions"]] == ["alpha"]


def test_disabled_and_override_skip_samples(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_COPILOT_CHATS", "0")
    brain = build_brain(DEMO)
    off = load_chats(DEMO, brain)
    assert off["enabled"] is False
    assert off["sessions"] == []

    monkeypatch.setenv("BRAIN_COPILOT_CHATS", "1")
    monkeypatch.setenv("BRAIN_COPILOT_CHATS_ROOT", str(tmp_path))
    overridden = load_chats(DEMO, brain)
    assert overridden["enabled"] is True
    assert overridden["sessions"] == []
    assert overridden["roots"] == [] or all("fixtures" not in path for path in overridden["roots"])


def test_llm_only_when_opted_in(tmp_path: Path, monkeypatch):
    _project(tmp_path, "alpha", "alpha_only.py", "x = 1\n")
    user = tmp_path / "User"
    store = user / "workspaceStorage" / "hash"
    (store / "chatSessions").mkdir(parents=True)
    (store / "workspace.json").write_text(json.dumps({"folder": "alpha"}), encoding="utf-8")
    when = datetime.now().astimezone()
    (store / "chatSessions" / "one.json").write_text(
        json.dumps(
            {
                "sessionId": "alpha-chat",
                "creationDate": _ms(when),
                "requests": [{"message": {"text": f"Edit alpha_only.py but never reveal {SENTINEL}"}, "timestamp": _ms(when)}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BRAIN_COPILOT_CHATS_ROOT", str(user))
    monkeypatch.delenv("BRAIN_COPILOT_LLM", raising=False)
    calls = []

    def fake_complete(provider, system, user_text, max_tokens=700, timeout=None):
        calls.append(user_text)
        assert SENTINEL not in user_text
        assert SENTINEL not in system
        return json.dumps({"alpha-chat": "Asked to edit the alpha script."})

    monkeypatch.setattr("backend.app.copilot_chats.complete", fake_complete)
    monkeypatch.setattr(
        "backend.app.copilot_chats.resolve_provider",
        lambda: {"name": "openai", "model": "test"},
    )
    brain = build_brain(tmp_path)
    quiet = load_chats(tmp_path, brain)
    assert calls == []
    assert quiet["llm"] is False
    assert quiet["sessions"][0]["summary_source"] == "heuristic"

    monkeypatch.setenv("BRAIN_COPILOT_LLM", "1")
    narrated = load_chats(tmp_path, brain)
    assert calls
    assert SENTINEL not in json.dumps(narrated)
    assert narrated["sessions"][0]["summary"] == "Asked to edit the alpha script."
    assert narrated["sessions"][0]["summary_source"] == "model"
    assert narrated["llm"] is True

    monkeypatch.setattr("backend.app.copilot_chats.resolve_provider", lambda: None)
    calls.clear()
    no_key = load_chats(tmp_path, brain)
    assert calls == []
    assert no_key["sessions"][0]["summary_source"] == "heuristic"


def test_timeline_merge_keeps_file_summary(tmp_path: Path, monkeypatch):
    _project(tmp_path, "alpha", "alpha_only.py", "# alpha\n\nA small script.\n")
    user = tmp_path / "User"
    store = user / "workspaceStorage" / "hash"
    (store / "chatSessions").mkdir(parents=True)
    (store / "workspace.json").write_text(json.dumps({"folder": str(tmp_path / "alpha")}), encoding="utf-8")
    when = datetime.now().astimezone() - timedelta(hours=1)
    (store / "chatSessions" / "one.json").write_text(
        json.dumps(
            {
                "sessionId": "alpha-chat",
                "creationDate": _ms(when),
                "requests": [{"message": {"text": "Why is alpha_only.py unfinished?"}, "timestamp": _ms(when)}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BRAIN_COPILOT_CHATS_ROOT", str(user))
    brain = build_brain(tmp_path)
    timeline = build_timeline(tmp_path, brain, 7)
    before = json.dumps(timeline)
    merged = merge_chats(timeline, load_chats(tmp_path, brain))
    blob = json.dumps(merged)
    assert "alpha_only.py" in blob
    assert "Why is alpha_only.py unfinished?" in blob
    found = False
    for week in merged["weeks"]:
        for day in week["days"]:
            for project in day["projects"]:
                if project["project_id"] != "alpha":
                    continue
                if project.get("chats"):
                    found = True
                    if project["files"]:
                        assert project["summary"] in before
    assert found


def test_demo_chats_api(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_ROOT", str(DEMO))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.delenv("BRAIN_COPILOT_CHATS_ROOT", raising=False)
    monkeypatch.delenv("BRAIN_COPILOT_LLM", raising=False)
    monkeypatch.setenv("BRAIN_COPILOT_CHATS", "1")
    from backend.app.main import create_app

    with TestClient(create_app()) as client:
        deadline_ready(client)
        chats = client.get("/api/chats")
        assert chats.status_code == 200
        body = chats.json()
        blob = json.dumps(body)
        assert SENTINEL not in blob
        assert body["enabled"] is True
        by_id = {}
        for session in body["sessions"]:
            by_id.setdefault(session["project_id"], []).append(session)
        assert "inbox-triage" in by_id
        inbox = next(item for item in by_id["inbox-triage"] if item["id"] == "inbox-label-threads")
        assert "triage.py" in inbox["prompt"]
        assert inbox["summary"]
        assert any(item["name"] == "triage.py" for item in inbox["files"])
        assert "github-pr-digest" in by_id
        timeline = client.get("/api/timeline", params={"days": 7})
        assert timeline.status_code == 200
        tl = json.dumps(timeline.json())
        assert "billing threads" in tl
        assert SENTINEL not in tl


def deadline_ready(client: TestClient) -> None:
    import time

    deadline = time.time() + 20
    while time.time() < deadline:
        health = client.get("/api/health").json()
        if health.get("phase") == "ready":
            return
        time.sleep(0.05)
    raise AssertionError("scan did not finish")
