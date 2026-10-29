"""MCP tools stay read-only, redacted, capped, and logged."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.mcp_rpc import dispatch
from backend.app.mcp_tools import cap_text, doctor_report, load_index, run_tool, tool_specs, usage_report
from backend.app.scanner import build_brain
from backend.app import store

DEMO = Path(__file__).resolve().parents[2] / "demo-projects"
REPO = Path(__file__).resolve().parents[2]
SENTINEL = "sk-demo-NOTREAL-redact-me"


def _index(root: Path) -> dict:
    brain = build_brain(root)
    store.save_scan(root, "test-sig", brain)
    return load_index(root)


def test_tools_redact_and_do_not_scan(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_MCP_DEMO", "0")
    project = tmp_path / "inbox"
    project.mkdir()
    (project / ".env").write_text(f"OPENAI_API_KEY={SENTINEL}\n", encoding="utf-8")
    (project / "triage.py").write_text(
        f'def triage():\n    """Sort the inbox."""\n    key = "{SENTINEL}"\n    return key\n',
        encoding="utf-8",
    )
    index = _index(tmp_path)
    found = run_tool("search_projects", {"query": "triage inbox", "limit": 5}, index)
    assert found["is_error"] is False
    assert "triage.py" in found["text"]
    assert SENTINEL not in found["text"]
    assert "[redacted" in found["text"]
    explained = run_tool("explain_file", {"path": "inbox/.env"}, index)
    assert "OPENAI_API_KEY" in explained["text"]
    assert SENTINEL not in explained["text"]
    assert "Key names only" in explained["text"]
    listing = json.loads(run_tool("list_projects", {}, index)["text"])
    assert listing["projects"][0]["project"] == "inbox"
    missing = run_tool("get_brief", {"project": "missing"}, index)
    assert "No project" in missing["text"]


def test_size_cap_and_usage_log(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_MCP_DEMO", "0")
    text, truncated = cap_text("x" * 25000)
    assert truncated is True
    assert text.endswith("[truncated to 20 KB]")
    assert len(text.encode("utf-8")) <= 20_000
    secret, _ = cap_text(f"prefix {SENTINEL} " + ("y" * 100))
    assert SENTINEL not in secret

    monkeypatch.setattr("backend.app.mcp_tools.MAX_BYTES", 180)
    project = tmp_path / "notes"
    project.mkdir()
    (project / "long.py").write_text("def run():\n    return 'notes'\n", encoding="utf-8")
    index = _index(tmp_path)
    index["brain"]["files"][0]["excerpt"] = "notes about the folder " + SENTINEL
    called = run_tool("search_projects", {"query": "notes", "limit": 3}, index)
    assert called["truncated"] is True
    assert "[truncated to 20 KB]" in called["text"]
    assert SENTINEL not in called["text"]
    log_path = tmp_path / ".brain" / "mcp_usage.jsonl"
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["tool"] == "search_projects"
    assert rows[-1]["truncated"] is True
    assert SENTINEL not in rows[-1]["args"]
    assert "bytes" in rows[-1] and "ms" in rows[-1]


def test_doctor_and_jsonrpc(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_MCP_DEMO", "0")
    empty = doctor_report(tmp_path)
    by_id = {item["id"]: item for item in empty["checks"]}
    assert by_id["index"]["status"] == "fail"
    assert by_id["python"]["status"] == "pass"
    assert by_id["server"]["status"] == "pass"
    assert "brain_mcp" in empty["snippet"]
    assert str(tmp_path) in empty["snippet"] or "BRAIN_ROOT" in empty["snippet"]
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in tool_specs())

    project = tmp_path / "lab"
    project.mkdir()
    (project / "readme.md").write_text("A lab note about routing.\n", encoding="utf-8")
    brain = build_brain(tmp_path)
    store.save_scan(tmp_path, "sig", brain)
    ready = doctor_report(tmp_path)
    ready_by = {item["id"]: item for item in ready["checks"]}
    assert ready_by["index"]["status"] == "pass"
    assert ready_by["registered"]["status"] == "warn"

    listed = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, tmp_path)
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert {"search_projects", "get_brief", "get_timeline", "explain_file", "list_projects"} <= names
    called = dispatch(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_projects", "arguments": {}}},
        tmp_path,
    )
    assert called["result"]["isError"] is False
    assert "lab" in called["result"]["content"][0]["text"]
    resource = dispatch(
        {"jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": {"uri": "brain://digest/latest"}},
        tmp_path,
    )
    assert "AI Brain digest" in resource["result"]["contents"][0]["text"]
    report = usage_report(tmp_path)
    assert report["counts"]
    assert any(item["tool"] == "list_projects" and item["count"] >= 1 for item in report["counts"])


def test_stdio_and_demo_usage(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "demo-cache.sqlite"))
    monkeypatch.setenv("BRAIN_ROOT", str(DEMO))
    monkeypatch.delenv("BRAIN_MCP_DEMO", raising=False)
    usage = usage_report(DEMO)
    assert usage["demo"] is True
    assert usage["link"]["state"] == "sample"
    assert any(item["tool"] == "search_projects" and item["count"] >= 1 for item in usage["counts"])

    env = dict(**{key: value for key, value in __import__("os").environ.items()})
    env["BRAIN_ROOT"] = str(tmp_path)
    env["BRAIN_CACHE"] = str(tmp_path / "stdio-cache.sqlite")
    env["BRAIN_MCP_DEMO"] = "0"
    env["PYTHONPATH"] = str(REPO)
    message = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {}}) + "\n"
    message += json.dumps({"jsonrpc": "2.0", "id": 8, "method": "tools/list"}) + "\n"
    proc = subprocess.run(
        [sys.executable, "-m", "brain_mcp"],
        input=message,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert lines[0]["result"]["serverInfo"]["name"] == "AI Brain"
    assert any(tool["annotations"]["readOnlyHint"] is True for tool in lines[1]["result"]["tools"])


def test_http_mcp_and_doctor_api(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_ROOT", str(DEMO))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.delenv("BRAIN_MCP_DEMO", raising=False)
    monkeypatch.delenv("BRAIN_DIGEST", raising=False)
    from backend.app.main import create_app

    with TestClient(create_app()) as client:
        deadline = __import__("time").time() + 20
        while __import__("time").time() < deadline:
            if client.get("/api/health").json().get("phase") == "ready":
                break
        usage = client.get("/api/mcp/usage")
        assert usage.status_code == 200
        assert usage.json()["link"]["state"] == "sample"
        doctor = client.get("/api/mcp/doctor")
        assert doctor.status_code == 200
        checks = {item["id"]: item["status"] for item in doctor.json()["checks"]}
        assert checks["index"] == "pass"
        assert checks["server"] == "pass"
        listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert listed.status_code == 200
        body = listed.json()["result"]["tools"]
        assert body[0]["annotations"]["readOnlyHint"] is True
        called = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "search_projects", "arguments": {"query": "LEVELS key-in", "limit": 5}},
            },
        )
        text = called.json()["result"]["content"][0]["text"]
        assert "levels" in text.lower()
        assert "demo-only-not-a-real-credential" not in text
