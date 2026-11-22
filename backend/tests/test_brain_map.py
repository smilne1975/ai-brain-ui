import os
import time

from fastapi.testclient import TestClient

from backend.app import scan_replay
from backend.app.main import create_app
from backend.app.scanner import build_brain


def test_flow_links_only_matching_visible_files_and_keep_line_numbers(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_PRIVATE_FOLDERS", '["workflow/private"]')
    project = tmp_path / "workflow"
    data = project / "data"
    data.mkdir(parents=True)
    (data / "notes.txt").write_text("hello", encoding="utf-8")
    (project / "report.txt").write_text("result", encoding="utf-8")
    (project / ".env").write_text("TOKEN=do-not-export", encoding="utf-8")
    private = project / "private"
    private.mkdir()
    (private / "hidden.txt").write_text("private", encoding="utf-8")
    (project / "build.py").write_text(
        'from pathlib import Path\n'
        'value = Path("data/notes.txt").read_text()\n'
        'Path("report.txt").write_text(value)\n'
        'open("report.txt", "r+")\n'
        'open("private/hidden.txt")\n'
        'open(".env")\n'
        'open("absent.txt")\n'
        'open(variable, "w")\n', encoding="utf-8")
    brain = build_brain(tmp_path)
    rec = next(row for row in brain["files"] if row["rel"] == "build.py")
    assert "flow_hints" not in rec
    assert rec["workflow_refs"] == [
        {"file_id": f"{rec['project_id']}:data/notes.txt", "direction": "read", "line": 2},
        {"file_id": f"{rec['project_id']}:report.txt", "direction": "write", "line": 3},
    ]


def test_replay_snapshots_scope_retention_and_privacy(tmp_path, monkeypatch):
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    root = tmp_path / "root"
    root.mkdir()

    def file(project, rel, observation, kind="markdown"):
        return {"id": f"{project}:{rel}", "project_id": project, "rel": rel, "observed": observation,
                "kind": kind, "excerpt": "don't store the original"}

    first = {"scanned_at": "2026-01-01T00:00:00Z", "files": [file("a", "stable.md", ["1", 4]), file("a", "gone.md", ["1", 4]),
        file("b", "other.md", None), file("a", ".env", ["1", 2], "env")]}
    scan_replay.record(root, first)
    scan_replay.record(root, first)
    base = scan_replay.frames(root, None, None)
    assert len(base["frames"]) == 1 and base["comparison"]["before"] is None
    second = {"scanned_at": "2026-01-05T00:00:00Z", "truncated": True, "files": [file("a", "stable.md", ["2", 4]),
        file("b", "other.md", ["1", 4]), file("b", "new.md", ["3", 4])]}
    scan_replay.record(root, second)
    frame = scan_replay.frames(root, None, None)["comparison"]
    assert frame["incomplete"] is True
    assert [(row["id"], row["state"]) for row in frame["changes"]] == [
        ("b:new.md", "added"), ("a:stable.md", "changed"), ("a:gone.md", "unlisted")]
    assert all(row["project_id"] == "a" for row in scan_replay.frames(root, frame["id"], "a")["comparison"]["changes"])
    assert scan_replay.frames(tmp_path, None, None)["frames"] == []
    monkeypatch.setattr(scan_replay, "KEEP", 2)
    scan_replay.record(root, first)
    assert len(scan_replay.frames(root, None, None)["frames"]) == 2
    monkeypatch.setenv("BRAIN_PRIVATE_FOLDERS", '["private"]')
    scan_replay.record(root, second)
    assert scan_replay.frames(root, None, None)["disabled"] is True
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS")
    assert scan_replay.frames(root, None, None)["comparison"]["after"] == first["scanned_at"]


def test_http_replay_uses_actual_completed_scans(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    note = root / "note.md"
    note.write_text("# Before", encoding="utf-8")
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    monkeypatch.setenv("BRAIN_ROOT", str(root))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")

    def ready(client):
        for _ in range(120):
            if client.get("/api/health").json()["phase"] == "ready":
                return
            time.sleep(.025)
        raise AssertionError("scan did not become ready")

    with TestClient(create_app()) as client:
        ready(client)
        assert client.get("/api/scan-replay").json()["comparison"]["before"] is None
        old = note.stat().st_mtime_ns
        note.write_text("# After!", encoding="utf-8")
        os.utime(note, ns=(old, old + 50_000_000))
        assert client.post("/api/rescan").status_code == 202
        ready(client)
        frame = client.get("/api/scan-replay").json()["comparison"]
        assert [(row["rel"], row["state"]) for row in frame["changes"]] == [("note.md", "changed")]
        assert client.get("/api/scan-replay?frame=9999").status_code == 404
