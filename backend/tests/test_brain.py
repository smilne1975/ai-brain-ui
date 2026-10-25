"""Scanner guarantees: demo corpus shape, and secrets never leave the process."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.ask import answer
from backend.app.redact import redact
from backend.app.scanner import HUGE_FILE_BYTES, _ATTR_OFFLINE, blocked_by_attrs, build_brain

DEMO = Path(__file__).resolve().parents[2] / "demo-projects"
SENTINEL = "sk-demo-NOTREAL-redact-me"
SLACK_SENTINEL = "https://hooks.slack.com/services/T000/B000/FAKEVALUE"
GHP_SENTINEL = "ghp_demoNOTreal0000"


def test_redact_strips_secret_shapes():
    raw = f'OPENAI_API_KEY={SENTINEL}\nurl={SLACK_SENTINEL}\ntoken={GHP_SENTINEL}\n'
    cleaned = redact(raw)
    assert SENTINEL not in cleaned
    assert "FAKEVALUE" not in cleaned
    assert GHP_SENTINEL not in cleaned
    assert "OPENAI_API_KEY=" in cleaned


def test_env_and_source_secrets_never_enter_the_brain(tmp_path: Path):
    project = tmp_path / "leak"
    project.mkdir()
    (project / ".env").write_text(
        f"OPENAI_API_KEY={SENTINEL}\nSLACK_WEBHOOK_URL={SLACK_SENTINEL}\n",
        encoding="utf-8",
    )
    (project / "notes.py").write_text(
        f'# copilot pasted this once\nkey = "{SENTINEL}"\n# {GHP_SENTINEL}\n',
        encoding="utf-8",
    )
    brain = build_brain(project)
    blob = json.dumps(brain)
    assert SENTINEL not in blob
    assert "FAKEVALUE" not in blob
    assert "NOTREAL" not in blob
    assert GHP_SENTINEL not in blob
    assert "OPENAI_API_KEY" in blob
    assert "[redacted" in blob


def test_demo_corpus_map():
    brain = build_brain(DEMO)
    blob = json.dumps(brain)
    for secret in (
        "demo-only-not-a-real-credential",
        "demo-rag-openai-not-real",
        "demo-agent-openai-not-real",
        "demo-github-token-not-real",
        "demo-slack-token-not-real",
        "example.invalid/slack-webhook-demo",
    ):
        assert secret not in blob

    names = {project["name"] for project in brain["projects"]}
    assert names == {
        "inbox-triage",
        "meeting-notes-rag",
        "github-pr-digest",
        "prompt-vault",
        "local-vision-lab",
        "agent-scratchpad",
    }
    skill_ids = {skill["id"] for skill in brain["skills"]}
    for required in ("openai-api", "rag", "chunking", "embeddings", "routing", "slack", "github", "vision", "prompt-craft", "tool-use", "copilot"):
        assert required in skill_ids

    status = {item["id"]: item["status"] for item in brain["connections"]}
    assert status["openai"] == "connected"
    assert status["github"] == "connected"
    assert status["slack"] == "connected"
    assert status["ollama"] == "referenced"
    assert status["anthropic"] == "referenced"
    assert status["chroma"] == "referenced"
    assert status["notion"] == "absent"
    assert status["postgres"] == "absent"

    vision = next(project for project in brain["projects"] if project["id"] == "local-vision-lab")
    assert vision["stats"]["env_keys"] == []
    openai = next(item for item in brain["connections"] if item["id"] == "openai")
    vision_hits = [item for item in openai["evidence"] if item["project_id"] == "local-vision-lab"]
    assert vision_hits
    assert all(not item["how"].startswith("env key") for item in vision_hits)
    assert "local-vision-lab" not in openai["live_projects"]
    assert "inbox-triage" in openai["live_projects"]

    graph = brain["architecture"]["projects"]["agent-scratchpad"]
    kinds = {node["kind"] for node in graph["nodes"]}
    assert {"decision", "tool", "store", "service"} <= kinds
    labels = {edge["label"] for edge in graph["edges"]}
    assert "imports" in labels

    mentions = [edge for edge in brain["architecture"]["corpus"]["edges"] if edge["label"] == "mentions"]
    assert mentions

    inbox = next(project for project in brain["projects"] if project["id"] == "inbox-triage")
    assert "OPENAI_API_KEY" in inbox["stats"]["env_keys"]
    assert "triage.py" in inbox["entries"]


def test_heuristic_answers_do_not_leak_demo_secrets():
    brain = build_brain(DEMO)
    reply = answer(brain, "What does inbox-triage actually do?", None, None)
    assert reply["provider"] == "heuristic"
    assert "inbox" in reply["answer"].lower()
    assert "demo-only-not-a-real-credential" not in reply["answer"]

    wired = answer(brain, "How is agent-scratchpad wired?", None, None)
    assert "route_turn" in wired["answer"]

    unfinished = answer(brain, "What is still unfinished?", None, None)
    assert "TODO" in unfinished["answer"] or "FIXME" in unfinished["answer"]

    folders = answer(brain, "Which folders talk to OpenAI?", None, None)
    assert "inbox-triage" in folders["answer"]
    assert "connected" in folders["answer"].lower()


def test_skips_caches_binaries_and_per_project_cap(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.app.scanner.PER_PROJECT", 2)
    monkeypatch.setattr("backend.app.scanner.MAX_FILES", 50)
    project = tmp_path / "notes"
    project.mkdir()
    (project / "keep.md").write_text("# keep this note\n", encoding="utf-8")
    (project / "also.md").write_text("# second note\n", encoding="utf-8")
    (project / "third.md").write_text("# THIRD_NOTE_SHOULD_BE_CAPPED\n", encoding="utf-8")
    nested = project / "node_modules" / "pkg"
    nested.mkdir(parents=True)
    (nested / "left.py").write_text("UNIQUE_NODE_MARKER = True\n", encoding="utf-8")
    (project / "Node_Modules").mkdir()
    (project / "Node_Modules" / "also.py").write_text("UNIQUE_NODE_CASE = True\n", encoding="utf-8")
    upload = project / ".tmp.driveupload"
    upload.mkdir()
    (upload / "cloud.md").write_text("UNIQUE_ONEDRIVE_MARKER\n", encoding="utf-8")
    (project / "sheet.docx").write_text("UNIQUE_DOCX_MARKER\n", encoding="utf-8")
    brain = build_brain(project)
    blob = json.dumps(brain)
    assert "UNIQUE_NODE_MARKER" not in blob
    assert "UNIQUE_NODE_CASE" not in blob
    assert "UNIQUE_ONEDRIVE_MARKER" not in blob
    assert "UNIQUE_DOCX_MARKER" not in blob
    assert "THIRD_NOTE_SHOULD_BE_CAPPED" not in blob
    names = {item["name"] for item in brain["files"]}
    assert names == {"keep.md", "also.md"}
    assert brain["truncated"] is True
    assert blocked_by_attrs(_ATTR_OFFLINE, 12) is True
    assert blocked_by_attrs(0, HUGE_FILE_BYTES + 1) is True
    assert blocked_by_attrs(0, 100) is False


def _wait_ready(client: TestClient, timeout: float = 20) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get("/api/health").json()
        if last["phase"] == "ready" and last["ok"]:
            return last
        if last["phase"] == "error":
            raise AssertionError(last)
        time.sleep(0.05)
    raise AssertionError(last)


def test_startup_returns_before_the_scan_finishes(tmp_path: Path, monkeypatch):
    docs = tmp_path / "Documents"
    project = docs / "alpha"
    project.mkdir(parents=True)
    (project / "notes.md").write_text("# local notes\n", encoding="utf-8")
    monkeypatch.setenv("BRAIN_ROOT", str(docs))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    gate = threading.Event()
    import backend.app.engine as engine_module

    real = engine_module.build_brain

    def slow(root, progress=None):
        if progress:
            progress({"message": "Reading alpha", "files": 1, "projects": 0, "current": str(project / "notes.md")})
        gate.wait(5)
        return real(root, progress)

    monkeypatch.setattr(engine_module, "build_brain", slow)
    from backend.app.main import create_app

    with TestClient(create_app()) as client:
        try:
            deadline = time.time() + 3
            early = None
            while time.time() < deadline:
                early = client.get("/api/health").json()
                if early["phase"] == "scanning" and (
                    "alpha" in (early.get("message") or "") or "notes.md" in (early.get("current") or "")
                ):
                    break
                time.sleep(0.05)
            assert early is not None
            assert early["phase"] == "scanning"
            assert early["ok"] is False
            assert Path(early["root"]) == docs.resolve()
            assert "alpha" in (early.get("message") or "") or "notes.md" in (early.get("current") or "")
            missing = client.get("/api/brain")
            assert missing.status_code == 503
            assert client.get("/api/timeline").status_code == 503
            assert client.get("/api/cards").status_code == 503
            assert client.get("/api/chats").status_code == 503
            assert client.get("/api/briefs").status_code == 503
            assert client.get("/api/brief/alpha").status_code == 503
            assert client.get("/api/digest").status_code == 503
        finally:
            gate.set()
        ready = _wait_ready(client)
        assert ready["projects"] == 1
        assert Path(ready["root"]) == docs.resolve()


def test_api_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_ROOT", str(DEMO))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    from backend.app.main import create_app

    with TestClient(create_app()) as client:
        health = _wait_ready(client)
        assert health["ok"] is True
        assert "demo-projects" in health["root"]
        brain = client.get("/api/brain").json()
        blob = json.dumps(brain)
        assert "demo-only-not-a-real-credential" not in blob
        assert "OPENAI_API_KEY" in blob
        asked = client.post("/api/ask", json={"question": "What does inbox-triage actually do?"})
        assert asked.status_code == 200
        body = asked.json()
        assert "inbox" in body["answer"].lower()
        assert "demo-only-not-a-real-credential" not in body["answer"]
        env_file = next(item for item in brain["files"] if item["name"] == ".env" and item["project_id"] == "inbox-triage")
        payload = client.get("/api/file", params={"file_id": env_file["id"]}).json()
        assert payload["env_keys"] == ["OPENAI_API_KEY"]
        assert "demo-only-not-a-real-credential" not in json.dumps(payload)
        rescanned = client.post("/api/rescan")
        assert rescanned.status_code == 202
        assert rescanned.json()["phase"] in {"scanning", "ready"}
        assert "demo-projects" in rescanned.json()["root"]
        again = _wait_ready(client)
        assert again["projects"] == 6
