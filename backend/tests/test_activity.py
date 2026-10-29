"""Timeline and project cards: dates, git subjects, run hints, and no env values."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.activity import build_cards, build_timeline, narrate_cards, narrate_timeline
from backend.app.scanner import build_brain
from backend.tests.test_brain import DEMO, SENTINEL, _wait_ready

NOW = datetime(2026, 10, 24, 15, 0, tzinfo=datetime.now().astimezone().tzinfo)


def _touch(path: Path, when: datetime) -> None:
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


def _git(cwd: Path, *args: str, env: dict | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env)


def _commit(cwd: Path, message: str, when: datetime) -> None:
    stamp = when.strftime("%Y-%m-%d %H:%M:%S %z")
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = stamp
    env["GIT_COMMITTER_DATE"] = stamp
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-m", message, env=env)


def _init_repo(path: Path) -> None:
    _git(path, "init")
    _git(path, "config", "user.email", "brain-test@example.com")
    _git(path, "config", "user.name", "Brain Test")


def _write(path: Path, text: str, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _touch(path, when)


def test_timeline_groups_mtimes_and_keeps_env_values_out(tmp_path: Path):
    project = tmp_path / "box"
    _write(project / "notes.md", "# box\n\nA box of notes.\n", NOW - timedelta(hours=2))
    _write(project / "old.md", "# older\n\nLeft alone.\n", NOW - timedelta(days=20))
    _write(project / ".env", f"OPENAI_API_KEY={SENTINEL}\n", NOW - timedelta(hours=1))
    brain = build_brain(tmp_path)
    today = build_timeline(tmp_path, brain, 1, now=NOW)
    week = build_timeline(tmp_path, brain, 7, now=NOW)
    month = build_timeline(tmp_path, brain, 30, now=NOW)
    blob = json.dumps({"today": today, "week": week, "month": month})
    assert SENTINEL not in blob
    assert "sk-" not in blob

    def names(payload: dict) -> set[str]:
        found = set()
        for week_row in payload["weeks"]:
            for day in week_row["days"]:
                for proj in day["projects"]:
                    found.update(item["rel"] for item in proj["files"])
        return found

    assert ".env" in names(today)
    assert "notes.md" in names(today)
    assert "old.md" not in names(today)
    assert "old.md" not in names(week)
    assert "old.md" in names(month)
    env_notes = [
        item["note"]
        for week_row in today["weeks"]
        for day in week_row["days"]
        for proj in day["projects"]
        for item in proj["files"]
        if item["rel"] == ".env"
    ]
    assert env_notes
    assert all("not read" in note.lower() for note in env_notes)
    assert all(SENTINEL not in note for note in env_notes)


def test_timeline_uses_project_git_and_ignores_a_parent_repo(tmp_path: Path):
    _init_repo(tmp_path)
    plain = tmp_path / "plain"
    _write(plain / "notes.md", "# plain\n\nJust notes.\n", NOW - timedelta(hours=3))
    _commit(tmp_path, "parent commit should not leak", NOW - timedelta(hours=3))

    widget = tmp_path / "widget"
    _write(
        widget / "main.py",
        '"""Say hello from the widget."""\nimport argparse\n\n'
        "def main():\n    parser = argparse.ArgumentParser()\n    parser.parse_args()\n\n"
        'if __name__ == "__main__":\n    main()\n',
        NOW - timedelta(hours=1),
    )
    _init_repo(widget)
    _commit(widget, f"Sketch the hello command {SENTINEL}", NOW - timedelta(hours=1))

    brain = build_brain(tmp_path)
    payload = build_timeline(tmp_path, brain, 7, now=NOW)
    blob = json.dumps(payload)
    assert SENTINEL not in blob
    assert "[redacted-key]" in blob
    by_name = {}
    for week in payload["weeks"]:
        for day in week["days"]:
            for proj in day["projects"]:
                by_name.setdefault(proj["name"], []).append(proj)
    assert "parent commit should not leak" not in blob
    widget_rows = by_name["widget"]
    subjects = [commit["subject"] for row in widget_rows for commit in row["commits"]]
    assert any("Sketch the hello command" in subject for subject in subjects)
    assert any(item["via"] in {"git", "both"} for row in widget_rows for item in row["files"])
    plain_rows = by_name.get("plain", [])
    assert all(not row["commits"] for row in plain_rows)


def test_cards_status_entry_and_unfinished(tmp_path: Path):
    live = tmp_path / "live"
    _write(
        live / "app.py",
        '"""Serve the live widget."""\nimport argparse\nfrom PIL import Image\n\n'
        "def main():\n    Image.new('RGB', (1, 1))\n    argparse.ArgumentParser().parse_args()\n\n"
        'if __name__ == "__main__":\n    main()\n',
        NOW - timedelta(days=1),
    )
    _write(live / "README.md", "# live\n\nA widget that draws one pixel.\n\nRun `python app.py`.\n", NOW - timedelta(days=1))
    _write(live / "scratch - copy.py", "# scratch\nprint('nope')\n", NOW - timedelta(days=1))
    _write(live / "empty.md", "", NOW - timedelta(days=1))
    _write(live / "TODO.md", "TODO: finish the pixel\nFIXME: handle missing files\n", NOW - timedelta(days=1))

    quiet = tmp_path / "quiet"
    _write(quiet / "notes.md", "# quiet\n\nA pile of notes with no runner.\n", NOW - timedelta(days=40))

    node = tmp_path / "nodebox"
    _write(
        node / "package.json",
        json.dumps({"name": "nodebox", "scripts": {"start": "node index.js", "dev": "node --watch index.js"}}),
        NOW - timedelta(days=12),
    )
    _write(node / "index.js", "console.log('half done')\n", NOW - timedelta(days=12))
    _write(node / "README.md", "# nodebox\n\nCleans copied text.\n", NOW - timedelta(days=12))

    brain = build_brain(tmp_path)
    cards = {card["name"]: card for card in build_cards(tmp_path, brain, now=NOW)["cards"]}
    assert cards["live"]["activity"] == "active"
    assert cards["live"]["run"] == "runs"
    assert cards["live"]["entry"]["how"] == "python app.py"
    assert cards["live"]["entry"]["path"] == "app.py"
    assert "pillow" in cards["live"]["unfinished"]["missing_requirements"]
    assert any("scratch" in rel for rel in cards["live"]["unfinished"]["stubs"])
    assert "empty.md" in cards["live"]["unfinished"]["empty"]
    assert cards["live"]["unfinished"]["todos"] >= 1
    assert cards["live"]["unfinished"]["fixmes"] >= 1
    assert cards["live"]["blurb"].lower().startswith("a widget")
    langs = {item["name"]: item["count"] for item in cards["live"]["languages"]}
    assert langs["Python"] >= 1
    assert cards["live"]["files"] >= 4

    assert cards["quiet"]["activity"] == "abandoned"
    assert cards["quiet"]["run"] == "unknown"
    assert cards["quiet"]["entry"] is None

    assert cards["nodebox"]["activity"] == "stale"
    assert cards["nodebox"]["run"] == "runs"
    assert cards["nodebox"]["entry"]["how"] == "npm start"


def test_narration_upgrades_text_without_reading_env_values(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    project = tmp_path / "box"
    _write(project / "notes.md", "# box\n\nA box of notes.\n", NOW - timedelta(hours=1))
    _write(project / ".env", f"OPENAI_API_KEY={SENTINEL}\n", NOW - timedelta(minutes=30))
    brain = build_brain(tmp_path)
    seen: list[str] = []

    def fake_complete(provider, system, user, max_tokens=700, timeout=None):
        seen.append(user)
        assert SENTINEL not in user
        assert SENTINEL not in system
        if "what changed" in user:
            return json.dumps({f"box@{NOW.date().isoformat()}": "Saved the box notes."})
        return json.dumps({"box": "This folder keeps a box of notes."})

    monkeypatch.setattr("backend.app.activity.complete", fake_complete)
    provider = {"name": "openai", "display": "OpenAI", "style": "openai", "model": "test", "base": "http://invalid", "key": "test"}
    timeline = narrate_timeline(provider, build_timeline(tmp_path, brain, 1, now=NOW))
    cards = narrate_cards(provider, build_cards(tmp_path, brain, now=NOW))
    assert timeline["source"] == "model"
    summary = timeline["weeks"][0]["days"][0]["projects"][0]["summary"]
    assert "Saved the box notes" in summary
    assert cards["cards"][0]["blurb_source"] == "model"
    assert "box of notes" in cards["cards"][0]["blurb"].lower()
    blob = json.dumps({"timeline": timeline, "cards": cards, "seen": seen})
    assert SENTINEL not in blob


def test_scan_cap_keeps_unread_files_out_of_the_timeline(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.app.scanner.PER_PROJECT", 1)
    project = tmp_path / "notes"
    _write(project / "a.md", "# keep\n\nKeep this note.\n", NOW - timedelta(hours=1))
    _write(project / "b.md", "# drop\n\nUNIQUE_TIMELINE_CAPPED\n", NOW - timedelta(hours=1))
    brain = build_brain(project)
    payload = build_timeline(project, brain, 7, now=NOW)
    blob = json.dumps(payload)
    assert "UNIQUE_TIMELINE_CAPPED" not in blob
    assert "a.md" in blob


def test_demo_timeline_and_cards_api(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_ROOT", str(DEMO))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    from backend.app.main import create_app

    with TestClient(create_app()) as client:
        _wait_ready(client)
        timeline = client.get("/api/timeline", params={"days": 7})
        assert timeline.status_code == 200
        body = timeline.json()
        assert body["window_days"] == 7
        assert body["label"] == "7 days"
        assert "weeks" in body
        cards = client.get("/api/cards")
        assert cards.status_code == 200
        board = cards.json()
        by_id = {card["project_id"]: card for card in board["cards"]}
        assert set(by_id) == {
            "inbox-triage",
            "meeting-notes-rag",
            "github-pr-digest",
            "prompt-vault",
            "local-vision-lab",
            "agent-scratchpad",
            "levels-report",
        }
        assert by_id["inbox-triage"]["run"] == "runs"
        assert "triage.py" in by_id["inbox-triage"]["entry"]["how"]
        assert by_id["agent-scratchpad"]["run"] == "runs"
        assert "agent.py" in by_id["agent-scratchpad"]["entry"]["how"]
        assert "digest.py" in by_id["github-pr-digest"]["entry"]["how"]
        levels = by_id["levels-report"]["microstation"]
        assert levels["keyins"]
        assert any(item["keyin"] == "MYREPORT LEVELS" for item in levels["keyins"])
        assert "query.py" in by_id["meeting-notes-rag"]["entry"]["how"]
        assert "label_folder.py" in by_id["local-vision-lab"]["entry"]["how"]
        assert by_id["prompt-vault"]["run"] == "unknown"
        assert "pillow" in by_id["local-vision-lab"]["unfinished"]["missing_requirements"]
        assert "chromadb" in by_id["meeting-notes-rag"]["unfinished"]["missing_requirements"]
        assert by_id["inbox-triage"]["unfinished"]["todos"] >= 1
        assert by_id["prompt-vault"]["unfinished"]["empty"]
        assert all(card["blurb"] for card in board["cards"])
        assert all(card["files"] > 0 for card in board["cards"])
        blob = json.dumps({"timeline": body, "cards": board})
        for secret in (
            "demo-only-not-a-real-credential",
            "demo-rag-openai-not-real",
            "demo-agent-openai-not-real",
            "demo-github-token-not-real",
            "demo-slack-token-not-real",
            "example.invalid/slack-webhook-demo",
        ):
            assert secret not in blob
        assert time.time() > 0
