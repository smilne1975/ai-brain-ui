"""MicroStation commands.xml parsing and the Bentley pitfall checks."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.ask import answer
from backend.app.microstation import build_microstation, parse_commands_xml
from backend.app.scanner import build_brain

DEMO = Path(__file__).resolve().parents[2] / "demo-projects"
SENTINEL = "sk-demo-NOTREAL-redact-me"

TABLE = """<?xml version="1.0" encoding="utf-8"?>
<KeyinTree xmlns="http://www.bentley.com/schemas/1.0/MicroStation/AddIn/KeyinTree.xsd">
  <RootKeyinTable ID="root">
    <Keyword CommandWord="MYREPORT" SubString="myreport">
      <SubKeyinTables>
        <KeyinTable ID="myreport">
          <Keyword CommandWord="LEVELS" SubString="levels" />
          <Keyword CommandWord="OPEN" SubString="open" />
        </KeyinTable>
      </SubKeyinTables>
    </Keyword>
  </RootKeyinTable>
  <KeyinHandlers>
    <KeyinHandler Keyin="MYREPORT LEVELS" Function="levels.report_levels" />
  </KeyinHandlers>
</KeyinTree>
"""


def test_parser_builds_full_keyins_and_handlers():
    parsed = parse_commands_xml(TABLE)
    by_key = {item["keyin"]: item for item in parsed["keyins"]}
    assert parsed["error"] == ""
    assert by_key["MYREPORT LEVELS"]["handler"] == "levels.report_levels"
    assert by_key["MYREPORT LEVELS"]["module"] == "levels"
    assert by_key["MYREPORT LEVELS"]["function"] == "report_levels"
    assert by_key["MYREPORT LEVELS"]["source"] == "handler"
    assert by_key["MYREPORT OPEN"]["source"] == "tree"
    assert by_key["MYREPORT OPEN"]["handler"] == ""
    assert "MYREPORT" not in by_key


def test_parser_tolerates_malformed_xml_and_skips_dtd():
    broken = '<KeyinTree><KeyinHandler Keyin="MYREPORT LEVELS" Function="levels.report_levels"><broken'
    parsed = parse_commands_xml(broken)
    assert parsed["error"] == "malformed"
    assert parsed["keyins"][0]["keyin"] == "MYREPORT LEVELS"
    assert parsed["keyins"][0]["function"] == "report_levels"

    dtd = '<!DOCTYPE foo [<!ENTITY x "boom">]><KeyinTree><Keyword CommandWord="NOPE"/></KeyinTree>'
    blocked = parse_commands_xml(dtd)
    assert blocked["keyins"] == []
    assert blocked["error"] == "DTD skipped"

    huge = '<KeyinHandler Keyin="MYREPORT LEVELS" Function="levels.report_levels"/>' + (" " * 300_000)
    capped = parse_commands_xml(huge)
    assert capped["truncated"] is True
    assert capped["keyins"][0]["function"] == "report_levels"


def test_pitfalls_duplicate_third_party_missing_and_orphan(tmp_path: Path):
    levels = tmp_path / "levels-report"
    (levels / "tools").mkdir(parents=True)
    (levels / "levels.py").write_text(
        "import os\nimport pandas as pd\nfrom MSPyDgnPlatform import LevelCache\n\n"
        "def report_levels():\n    return pd.DataFrame()\n",
        encoding="utf-8",
    )
    (levels / "tools" / "levels.py").write_text(
        "from MSPyBentley import WString\n\ndef report_levels():\n    return WString\n",
        encoding="utf-8",
    )
    (levels / "levels.commands.xml").write_text(TABLE, encoding="utf-8")
    (levels / "drafts").mkdir()
    (levels / "drafts" / "unused.commands.xml").write_text(
        '<KeyinTree><KeyinHandlers>'
        f'<KeyinHandler Keyin="ORPHAN {SENTINEL}" Function="missing_mod.ping"/>'
        "</KeyinHandlers></KeyinTree>",
        encoding="utf-8",
    )
    other = tmp_path / "sheet-index"
    other.mkdir()
    (other / "startup.py").write_text("from MSPyMstnPlatform import PythonKeyinManager\n", encoding="utf-8")
    (other / "levels.py").write_text("from MSPyDgnView import *\n\ndef report_levels():\n    return 1\n", encoding="utf-8")

    brain = build_brain(tmp_path)
    blob = json.dumps(brain)
    assert SENTINEL not in blob
    report = build_microstation(tmp_path, brain["projects"], brain["files"])
    by_id = {item["project_id"]: item for item in report["projects"]}
    assert set(by_id) == {"levels-report", "sheet-index"}

    levels_row = by_id["levels-report"]
    levels_key = next(item for item in levels_row["keyins"] if item["keyin"] == "MYREPORT LEVELS")
    assert levels_key["found"] is True
    assert levels_key["rel"] == "levels.py"
    assert levels_key["function"] == "report_levels"
    open_key = next(item for item in levels_row["keyins"] if item["keyin"] == "MYREPORT OPEN")
    assert open_key["found"] is False
    assert "pandas" in levels_row["third_party"]
    assert "os" not in levels_row["third_party"]
    assert not any(name.lower().startswith("mspy") for name in levels_row["third_party"])

    ids = {item["id"] for item in levels_row["pitfalls"]}
    assert "duplicate-filename" in ids
    assert "missing-handler" in ids
    assert "third-party" in ids
    assert "orphan-commands" in ids
    duplicate = next(item for item in levels_row["pitfalls"] if item["id"] == "duplicate-filename")
    assert duplicate["severity"] == "red"
    assert "levels.py" in duplicate["detail"]
    assert "sheet-index" in duplicate["detail"]
    third = next(item for item in levels_row["pitfalls"] if item["id"] == "third-party")
    assert third["severity"] == "amber"
    assert "MS_PYTHON" in third["detail"]
    assert "pandas" in third["prompt"]

    graph = brain["architecture"]["projects"]["levels-report"]
    labels = {node["label"] for node in graph["nodes"]}
    kinds = {node["kind"] for node in graph["nodes"]}
    assert "MYREPORT LEVELS" in labels
    assert "report_levels" in labels
    assert "keyin" in kinds and "function" in kinds
    assert any(edge["label"] == "calls" for edge in graph["edges"])

    reply = answer(brain, "Which project has the LEVELS key-in?", None, None)
    assert "levels-report" in reply["answer"]
    assert "MYREPORT LEVELS" in reply["answer"]
    assert "levels.py:report_levels" in reply["answer"]
    assert SENTINEL not in reply["answer"]


def test_local_module_is_not_third_party(tmp_path: Path):
    folder = tmp_path / "app"
    folder.mkdir()
    (folder / "helper.py").write_text("def tidy():\n    return 1\n", encoding="utf-8")
    (folder / "run.py").write_text(
        "import helper\nimport json\nfrom MSPyECObjects import Object\n\ndef go():\n    return helper.tidy()\n",
        encoding="utf-8",
    )
    (folder / "run.commands.xml").write_text(
        '<KeyinTree><KeyinHandlers><KeyinHandler Keyin="APP GO" Function="run.go"/></KeyinHandlers></KeyinTree>',
        encoding="utf-8",
    )
    brain = build_brain(tmp_path)
    report = build_microstation(tmp_path, brain["projects"], brain["files"])
    row = report["projects"][0]
    assert row["third_party"] == []
    assert row["keyins"][0]["found"] is True
    assert row["keyins"][0]["rel"] == "run.py"
    assert not any(item["id"] == "orphan-commands" for item in row["pitfalls"])


def test_demo_microstation_api(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_ROOT", str(DEMO))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.delenv("BRAIN_DIGEST", raising=False)
    from backend.app.main import create_app

    with TestClient(create_app()) as client:
        deadline = __import__("time").time() + 20
        while __import__("time").time() < deadline:
            if client.get("/api/health").json().get("phase") == "ready":
                break
        board = client.get("/api/microstation")
        assert board.status_code == 200
        ids = {item["project_id"] for item in board.json()["projects"]}
        assert ids == {"levels-report"}
        one = client.get("/api/microstation/levels-report")
        assert one.status_code == 200
        body = one.json()
        assert any(item["keyin"] == "MYREPORT LEVELS" and item["found"] for item in body["keyins"])
        assert any(item["keyin"] == "MYREPORT EXPORT" and not item["found"] for item in body["keyins"])
        assert client.get("/api/microstation/inbox-triage").status_code == 404
        assert client.get("/api/microstation/not-a-folder").status_code == 404
        cards = client.get("/api/cards").json()
        card = next(item for item in cards["cards"] if item["project_id"] == "levels-report")
        assert card["microstation"]["keyins"]
        skill = next(item for item in client.get("/api/brain").json()["skills"] if item["id"] == "microstation-python")
        assert "levels-report" in skill["projects"]
