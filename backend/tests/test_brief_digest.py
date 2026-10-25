"""Handoff briefs and digests stay local, and .env values stay out."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.brief import build_brief, build_briefs, save_handoff
from backend.app.digest import build_digest, export_digest, write_scheduled
from backend.app.scanner import build_brain

DEMO = Path(__file__).resolve().parents[2] / "demo-projects"
SENTINEL = "sk-demo-NOTREAL-redact-me"
NOW = datetime(2026, 10, 25, 15, tzinfo=timezone.utc)


def _stamp(path: Path, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# note\n", encoding="utf-8")
    moment = when.timestamp()
    os.utime(path, (moment, moment))


def _folder(root: Path, name: str, filename: str, body: str, when: datetime) -> None:
    path = root / name / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _stamp(path, when)


def test_brief_uses_chat_todo_decision_and_run_command(tmp_path: Path, monkeypatch):
    _folder(
        tmp_path,
        "inbox-triage",
        "triage.py",
        "def triage():\n    return 'billing'\n",
        NOW - timedelta(hours=2),
    )
    _folder(
        tmp_path,
        "inbox-triage",
        "TODOS.md",
        "# later\n\n- TODO: stop hard-coding the model name\n- FIXME: the retry loop resends the request\n",
        NOW - timedelta(hours=1),
    )
    _folder(
        tmp_path,
        "inbox-triage",
        "decisions.md",
        "# decisions\n\n- Labels stay action, waiting, or noise.\n- Slack export stays a draft.\n",
        NOW - timedelta(days=1),
    )
    _folder(
        tmp_path,
        "inbox-triage",
        "README.md",
        "# inbox\n\nRun `python triage.py samples/threads.md`.\n",
        NOW - timedelta(days=2),
    )
    _folder(tmp_path, "inbox-triage", ".env", f"OPENAI_API_KEY={SENTINEL}\n", NOW)
    user = tmp_path / "User"
    store = user / "workspaceStorage" / "hash"
    (store / "chatSessions").mkdir(parents=True)
    (store / "workspace.json").write_text(json.dumps({"folder": "inbox-triage"}), encoding="utf-8")
    (store / "chatSessions" / "one.json").write_text(
        json.dumps(
            {
                "sessionId": "inbox-chat",
                "creationDate": int((NOW - timedelta(hours=3)).timestamp() * 1000),
                "requests": [
                    {
                        "message": {"text": f"Update triage.py and never print {SENTINEL}"},
                        "timestamp": int((NOW - timedelta(hours=3)).timestamp() * 1000),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BRAIN_COPILOT_CHATS_ROOT", str(user))
    monkeypatch.delenv("BRAIN_BRIEF_LLM", raising=False)
    from backend.app.copilot_chats import load_chats

    brain = build_brain(tmp_path)
    chats = load_chats(tmp_path, brain)
    brief = build_brief(tmp_path, brain, "inbox-triage", chats, NOW)
    blob = json.dumps(brief)
    assert SENTINEL not in blob
    assert "Stu was last asking Copilot" in brief["last_doing"]
    assert "triage.py" in brief["last_doing"]
    assert any("action, waiting, or noise" in item for item in brief["decisions"])
    assert brief["fixme_count"] >= 1
    assert "retry loop" in brief["next_step"]
    assert "python triage.py" in brief["run_command"]
    assert "Pick up where I left off: inbox-triage" in brief["copy_text"]
    assert any(item["rel"] == "triage.py" for item in brief["key_files"])
    assert not (tmp_path / "inbox-triage" / "BRAIN_HANDOFF.md").exists()
    saved = save_handoff(tmp_path, brain, "inbox-triage", chats, NOW)
    text = Path(saved["path"]).read_text(encoding="utf-8")
    assert text.startswith("# Pick up where I left off")
    assert SENTINEL not in text
    assert saved["name"] == "BRAIN_HANDOFF.md"


def test_brief_llm_is_opt_in(tmp_path: Path, monkeypatch):
    _folder(tmp_path, "alpha", "notes.md", "# alpha\n\n- TODO: finish the note\n", NOW)
    monkeypatch.setenv("BRAIN_COPILOT_CHATS_ROOT", str(tmp_path / "empty-chats"))
    monkeypatch.delenv("BRAIN_BRIEF_LLM", raising=False)
    calls = []

    def fake_complete(provider, system, user, max_tokens=700, timeout=None):
        calls.append(user)
        assert SENTINEL not in user
        return json.dumps({"alpha": {"last_doing": "Stu was editing the note.", "decisions": [], "next_step": "Finish the note."}})

    monkeypatch.setattr("backend.app.brief.complete", fake_complete)
    monkeypatch.setattr("backend.app.brief.resolve_provider", lambda: {"name": "openai", "model": "test"})
    brain = build_brain(tmp_path)
    quiet = build_briefs(tmp_path, brain, {"sessions": []}, NOW)
    assert calls == []
    assert quiet["briefs"][0]["source"] == "heuristic"
    monkeypatch.setenv("BRAIN_BRIEF_LLM", "1")
    narrated = build_briefs(tmp_path, brain, {"sessions": []}, NOW)
    assert calls
    assert narrated["briefs"][0]["source"] == "model"
    assert "editing the note" in narrated["briefs"][0]["last_doing"]


def test_digest_windows_and_quiet_projects(tmp_path: Path, monkeypatch):
    _folder(tmp_path, "live", "notes.md", "# live\n\n- TODO: ship the note\n", NOW - timedelta(hours=4))
    _folder(tmp_path, "fading", "old.md", "# fading\n\n- FIXME: the index drifted\n", NOW - timedelta(days=8))
    _folder(tmp_path, "shelf", "dust.md", "# shelf\n\n- TODO: decide whether to keep this\n", NOW - timedelta(days=32))
    monkeypatch.setenv("BRAIN_COPILOT_CHATS_ROOT", str(tmp_path / "no-chats"))
    monkeypatch.delenv("BRAIN_DIGEST_LLM", raising=False)
    brain = build_brain(tmp_path)
    week = build_digest(tmp_path, brain, "week", {"sessions": []}, NOW)
    blob = json.dumps(week)
    assert SENTINEL not in blob
    touched = {item["project_id"] for item in week["touched"]}
    assert "live" in touched
    assert "fading" not in touched
    assert {item["project_id"] for item in week["newly_stale"]} == {"fading"}
    assert {item["project_id"] for item in week["newly_abandoned"]} == {"shelf"}
    assert week["todos"]["open"] >= 3
    assert week["todos"]["fixmes"] >= 1
    assert any(item["project_id"] == "fading" for item in week["focus"])
    assert "Newly stale" in week["markdown"]
    assert "fading" in week["markdown"]
    day = build_digest(tmp_path, brain, "day", {"sessions": []}, NOW)
    assert "live" in {item["project_id"] for item in day["touched"]}
    assert day["newly_stale"] == []
    saved = export_digest(tmp_path, brain, "week", {"sessions": []}, NOW)
    path = Path(saved["saved_path"])
    assert path.parent.name == "digests"
    assert path.parent.parent.name == ".brain"
    assert "AI Brain digest" in path.read_text(encoding="utf-8")
    assert not (tmp_path / "live" / "BRAIN_HANDOFF.md").exists()


def test_scheduled_digest_respects_the_flag(tmp_path: Path, monkeypatch):
    _folder(tmp_path, "live", "notes.md", "# live\n\nA note.\n", NOW)
    brain = build_brain(tmp_path)
    monkeypatch.delenv("BRAIN_DIGEST", raising=False)
    assert write_scheduled(tmp_path, brain, NOW) is None
    assert not (tmp_path / ".brain" / "digests").exists()
    monkeypatch.setenv("BRAIN_DIGEST", "weekly")
    monkeypatch.setenv("BRAIN_COPILOT_CHATS", "0")
    first = write_scheduled(tmp_path, brain, NOW)
    assert first is not None
    assert first.name.startswith("week-")
    assert write_scheduled(tmp_path, brain, NOW) is None


def test_demo_brief_and_digest_api(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_ROOT", str(DEMO))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.delenv("BRAIN_COPILOT_CHATS_ROOT", raising=False)
    monkeypatch.delenv("BRAIN_BRIEF_LLM", raising=False)
    monkeypatch.delenv("BRAIN_DIGEST", raising=False)
    from backend.app.main import create_app

    with TestClient(create_app()) as client:
        deadline = __import__("time").time() + 20
        while __import__("time").time() < deadline:
            if client.get("/api/health").json().get("phase") == "ready":
                break
        briefs = client.get("/api/briefs")
        assert briefs.status_code == 200
        board = briefs.json()
        blob = json.dumps(board)
        assert SENTINEL not in blob
        inbox = next(item for item in board["briefs"] if item["project_id"] == "inbox-triage")
        assert "asking Copilot" in inbox["last_doing"]
        assert "triage.py" in inbox["last_doing"]
        assert inbox["next_step"]
        assert inbox["copy_text"]
        one = client.get("/api/brief/inbox-triage")
        assert one.status_code == 200
        assert one.json()["project_id"] == "inbox-triage"
        missing = client.get("/api/brief/not-a-folder")
        assert missing.status_code == 404
        assert not (DEMO / "inbox-triage" / "BRAIN_HANDOFF.md").exists()
        digest = client.get("/api/digest", params={"period": "week"})
        assert digest.status_code == 200
        body = digest.json()
        assert body["period"] == "week"
        assert "markdown" in body
        assert SENTINEL not in json.dumps(body)
        bad = client.get("/api/digest", params={"period": "year"})
        assert bad.status_code == 400
