import json
from datetime import datetime

from backend.app import activity, agent_history, scanner
from backend.app.copilot_chats import merge_chats


def test_opted_in_export_merges_scoped_sessions_and_skips_unmatched_refs(tmp_path, monkeypatch):
    design = tmp_path / "levels"
    design.mkdir()
    (design / "README.md").write_text("Levels", encoding="utf-8")
    (design / ".env").write_text("SECRET=invisible", encoding="utf-8")
    brain = scanner.build_brain(tmp_path)
    export = tmp_path / ".sessions.json"
    when = datetime.now().astimezone().isoformat()
    row = {"agent": "Local coding agent", "id": "first", "project": "levels", "title": "Checked export scope", "when": when,
           "summary": "Reviewed the CSV output", "prompt": "do not import raw prompts", "files": ["README.md", ".env", "../private.md"]}
    export.write_text(json.dumps({"sessions": [row, row, {**row, "project": "unknown"}]}), encoding="utf-8")
    monkeypatch.setenv("BRAIN_AGENT_HISTORY_FILE", str(export))
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    items, warning = agent_history.load(brain)
    assert len(items) == 1 and "1 invalid" in warning
    timeline = merge_chats(activity.build_timeline(tmp_path, brain, 7), {"enabled": True, "sessions": items})
    events = [chat for week in timeline["weeks"] for day in week["days"] for project in day["projects"] for chat in project["chats"]]
    assert events[0]["agent"] == "Local coding agent" and events[0]["prompt"] == ""
    assert [file["rel"] for file in events[0]["files"]] == ["README.md"]
    monkeypatch.setenv("BRAIN_PRIVATE_FOLDERS", '["other"]')
    assert agent_history.load(brain) == ([], None)
