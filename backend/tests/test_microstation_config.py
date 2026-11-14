"""MicroStation cfg, ucf, and pcf parsing, faults, and the read-only API."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.mcp_tools import run_tool, tool_specs
from backend.app.microstation_config import evaluate_config
from backend.app.scanner import build_brain
from backend.app import store

DEMO = Path(__file__).resolve().parents[2] / "demo-projects"
SENTINEL = "sk-demo-NOTREAL-redact-me"


def _var(report: dict, name: str) -> dict:
    return next(item for item in report["variables"] if item["name"] == name)


def test_operators_levels_conditionals_locks_and_includes(tmp_path: Path):
    root = tmp_path / "cfg"
    (root / "bits").mkdir(parents=True)
    (root / "low.cfg").write_text("%level Organization\nMS_DEF = from-org/\n", encoding="utf-8")
    (root / "part.cfg").write_text("MS_ROLE = role/\n", encoding="utf-8")
    (root / "hidden.cfg").write_text("MS_HIDDEN = secret-hidden\n", encoding="utf-8")
    (root / "bits" / "one.cfg").write_text("MS_BIT = one\n", encoding="utf-8")
    (root / ".env").write_text(f"OPENAI_API_KEY={SENTINEL}\nMS_FROM_ENV = loaded\n", encoding="utf-8")
    main = root / "main.cfg"
    main.write_text(
        "\n".join(
            [
                "%level WorkSet",
                "PHASE = Draft",
                "LATE = ${PHASE}",
                "LAZY = $(PHASE)",
                "PHASE = Final",
                "MS_RFDIR = A/",
                "MS_RFDIR > B/",
                "MS_RFDIR < C/",
                "MS_BACKUP = kept/",
                "%lock MS_BACKUP",
                "MS_BACKUP > nope/",
                "MS_DEF = first/",
                "MS_DEF : second/",
                "%include part.cfg level Role",
                "%include bits/*.cfg",
                "%include $(MISSING)",
                "%include absent.cfg",
                "%include .env",
                "%include C:/Users/Stu/outside.cfg",
                '%if $(PHASE)=="Final"',
                "MS_SEEDFILES = seed/",
                "%elif defined (MS_RFDIR)",
                "MS_SEEDFILES = alt/",
                "%else",
                "MS_SEEDFILES = C:/seed",
                "%endif",
                "%if 1",
                "%if 0",
                "MS_NEST = inner",
                "%else",
                "MS_NEST = mid",
                "%endif",
                "%else",
                "MS_NEST = outer",
                "%endif",
                "%if 0",
                "%include hidden.cfg",
                "%else",
                "MS_SHOWN = yes",
                "%endif",
                "%ifdef _USTN_WORKSETROOT",
                "MS_IFDEF = no",
                "%else",
                "MS_IFDEF = yes",
                "%endif",
                "%ifndef NOT_A_VAR",
                "MS_IFNDEF = yes",
                "%endif",
                '%if $(PHASE)=="Draft"',
                "MS_ELIF = draft",
                '%elif $(PHASE)=="Final"',
                "MS_ELIF = final",
                "%else",
                "MS_ELIF = other",
                "%endif",
                "MS_ADDINPATH = C:/Users/Stu/AppData/addins",
                "_USTN_WORKSETROOT = dgn",
                "",
            ]
        ),
        encoding="utf-8",
    )
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    stamps = {path: path.stat().st_mtime_ns for path in before}
    report = evaluate_config(root, [(root / "low.cfg", "Organization"), (main, "WorkSet")])
    assert {path: path.read_bytes() for path in before} == before
    assert {path: path.stat().st_mtime_ns for path in stamps} == stamps

    assert _var(report, "LATE")["value"] == "Draft"
    assert _var(report, "LAZY")["value"] == "Final"
    assert _var(report, "MS_RFDIR")["value"] == "C/;A/;B/"
    assert _var(report, "MS_DEF")["value"] == "first/"
    assert _var(report, "MS_DEF")["level"] == "WorkSet"
    assert _var(report, "MS_BACKUP")["value"] == "kept/"
    assert _var(report, "MS_BACKUP")["locked"] is True
    assert _var(report, "MS_ROLE")["value"] == "role/"
    assert _var(report, "MS_ROLE")["level"] == "Role"
    assert _var(report, "MS_ROLE")["file"].endswith("part.cfg")
    assert _var(report, "MS_BIT")["value"] == "one"
    assert _var(report, "MS_SEEDFILES")["value"] == "seed/"
    assert _var(report, "MS_NEST")["value"] == "mid"
    assert _var(report, "MS_SHOWN")["value"] == "yes"
    assert _var(report, "MS_IFDEF")["value"] == "yes"
    assert _var(report, "MS_IFNDEF")["value"] == "yes"
    assert _var(report, "MS_ELIF")["value"] == "final"
    assert "MS_HIDDEN" not in {item["name"] for item in report["variables"]}
    assert "MS_FROM_ENV" not in {item["name"] for item in report["variables"]}
    blob = json.dumps(report)
    assert SENTINEL not in blob
    assert "secret-hidden" not in blob
    ids = {item["id"] for item in report["faults"]}
    assert "locked-override" in ids
    assert "missing-include" in ids
    assert "unresolved-include" in ids
    assert "hard-coded-user" in ids
    assert "missing-slash" in ids
    locked = next(item for item in report["faults"] if item["id"] == "locked-override")
    assert locked["variable"] == "MS_BACKUP"
    assert "main.cfg" in locked["file"]
    user = next(item for item in report["faults"] if item["id"] == "hard-coded-user")
    assert user["variable"] == "MS_ADDINPATH"
    slash = [item["variable"] for item in report["faults"] if item["id"] == "missing-slash"]
    assert "MS_ADDINPATH" in slash
    assert "_USTN_WORKSETROOT" in slash


def test_escaped_include_is_not_read(tmp_path: Path):
    project = tmp_path / "job"
    folder = project / "WorkSets" / "Span"
    folder.mkdir(parents=True)
    outside = tmp_path.parent / f"outside-{tmp_path.name}.cfg"
    outside.write_text("MS_OUTSIDE = SHOULD_NOT_LOAD\n", encoding="utf-8")
    relative = Path(__import__("os").path.relpath(outside, folder))
    cfg = folder / "Span.cfg"
    cfg.write_text(
        "\n".join(
            [
                "%level WorkSet",
                "_USTN_WORKSETNAME = Span",
                f'%include "{relative.as_posix()}"',
                "MS_DEF = local/",
                "",
            ]
        ),
        encoding="utf-8",
    )
    try:
        brain = build_brain(tmp_path)
    finally:
        outside.unlink(missing_ok=True)
    blob = json.dumps(brain)
    assert "SHOULD_NOT_LOAD" not in blob
    report = next(item["microstation_config"] for item in brain["projects"] if item["id"] == "job")
    unit = next(item for item in report["units"] if item["kind"] == "workset")
    assert any(item["id"] == "unresolved-include" for item in unit["faults"])
    assert _var(unit, "MS_DEF")["value"] == "local/"


def test_workset_map_faults_scripts_and_pcf(tmp_path: Path):
    job = tmp_path / "bridge-job"
    org = job / "Configuration" / "Organization"
    ws = job / "Configuration" / "WorkSpaces" / "Civil"
    span = ws / "WorkSets" / "Span"
    (org).mkdir(parents=True)
    (ws / "Standards").mkdir(parents=True)
    span.mkdir(parents=True)
    (job / "Configuration" / "Users").mkdir(parents=True)
    (job / "legacy").mkdir()
    (span / "mdlapps").mkdir()
    (org / "org.cfg").write_text(
        "\n".join(
            [
                "%level Organization",
                "PHASE = Draft",
                "LATE = ${PHASE}",
                "LAZY = $(PHASE)",
                "PHASE = Final",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (ws / "Civil.cfg").write_text(
        "\n".join(
            [
                "%level WorkSpace",
                "_USTN_WORKSPACENAME = Civil",
                "_USTN_WORKSPACEROOT = Configuration/WorkSpaces/Civil/",
                "%include $(_USTN_WORKSPACEROOT)Standards/paths.cfg level WorkSpace",
                "MS_RFDIR = $(_USTN_WORKSPACEROOT)refs/",
                "%lock MS_RFDIR",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (ws / "Standards" / "paths.cfg").write_text("MS_PLTCFG = $(_USTN_WORKSPACEROOT)plot/\n", encoding="utf-8")
    (span / "extra.cfg").write_text(
        "\n".join(
            [
                "MS_DGNLIBLIST > $(_USTN_WORKSETROOT)extras/*.dgnlib",
                "MS_RFDIR = C:/locked/nope/",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (span / "skip.cfg").write_text("MS_SKIPPED = yes\n", encoding="utf-8")
    (span / "Span.cfg").write_text(
        "\n".join(
            [
                "%level WorkSet",
                "_USTN_WORKSETNAME = Span",
                "_USTN_WORKSETROOT = Configuration/WorkSpaces/Civil/WorkSets/Span/",
                "%include $(MISSING_FILE)",
                "%include no-such.cfg",
                '%if $(PHASE)=="Final"',
                "MS_SEEDFILES = $(_USTN_WORKSETROOT)seed/",
                "%else",
                "%include skip.cfg",
                "%endif",
                "%if defined(_USTN_WORKSETROOT)",
                "MS_DEF = $(_USTN_WORKSETROOT)dgn/",
                "MS_DGNLIBLIST = $(_USTN_WORKSETROOT)dgnlib/*.dgnlib",
                "MS_ADDINPATH = $(_USTN_WORKSETROOT)mdlapps/",
                "%endif",
                "MS_CELL < lead/",
                "%include extra.cfg level Role",
                "",
            ]
        ),
        encoding="utf-8",
    )
    # Organization sets MS_CELL with ':' so a later ':' must not replace it.
    (org / "org.cfg").write_text(
        (org / "org.cfg").read_text(encoding="utf-8") + "MS_CELL : $(_USTN_WORKSETROOT)cell/\n",
        encoding="utf-8",
    )
    (job / "Configuration" / "Users" / "stu.ucf").write_text(
        "%level User\nMS_CELL : should-not-replace/\nMS_DEF = C:/Users/Stu/Documents/dgn\n",
        encoding="utf-8",
    )
    (job / "legacy" / "Old.pcf").write_text(
        "\n".join(
            [
                "%level Project",
                "_USTN_PROJECTNAME = Old",
                "_USTN_PROJECTDATA = C:/Users/Stu/Projects/Old/",
                "MS_DEF = C:/Users/Stu/Projects/Old/dgn",
                f"MS_NOTE = {SENTINEL}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (job / "span_tool.py").write_text(
        "\n".join(
            [
                "import os",
                "from MSPyBentley import ConfigurationManager",
                "",
                "def ping():",
                '    os.environ.get("LATE")',
                '    os.environ.get("LAZY")',
                '    os.environ.get("MS_CELL")',
                '    ConfigurationManager.GetVariable("MS_PLTCFG")',
                '    os.environ["MS_RFDIR"] = "C:/Users/Stu/nope"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (span / "mdlapps" / "span_addin.py").write_text(
        "from MSPyBentley import ConfigurationManager\n\ndef load():\n    return ConfigurationManager.GetVariable('MS_ADDINPATH')\n",
        encoding="utf-8",
    )
    cfg_bytes = {path: path.read_bytes() for path in job.rglob("*") if path.suffix.lower() in {".cfg", ".ucf", ".pcf"}}
    brain = build_brain(tmp_path)
    assert {path: path.read_bytes() for path in cfg_bytes} == cfg_bytes
    blob = json.dumps(brain)
    assert SENTINEL not in blob
    report = next(item["microstation_config"] for item in brain["projects"] if item["id"] == "bridge-job")
    assert "MS_SKIPPED" not in json.dumps(report)
    by_kind = {}
    for unit in report["units"]:
        by_kind.setdefault(unit["kind"], []).append(unit)
    assert {item["name"] for item in by_kind["workspace"]} == {"Civil"}
    span_unit = next(item for item in by_kind["workset"] if item["name"] == "Span")
    assert span_unit["workspace"] == "Civil"
    assert _var(span_unit, "LATE")["value"] == "Draft"
    assert _var(span_unit, "LAZY")["value"] == "Final"
    assert _var(span_unit, "MS_CELL")["value"].startswith("lead/;")
    assert _var(span_unit, "MS_CELL")["value"].endswith("cell/")
    assert "should-not-replace" not in _var(span_unit, "MS_CELL")["value"]
    assert _var(span_unit, "MS_RFDIR")["locked"] is True
    assert _var(span_unit, "MS_RFDIR")["value"].endswith("refs/")
    assert _var(span_unit, "MS_RFDIR")["level"] == "WorkSpace"
    assert _var(span_unit, "MS_SEEDFILES")["value"].endswith("seed/")
    assert "extras/*.dgnlib" in _var(span_unit, "MS_DGNLIBLIST")["value"]
    assert _var(span_unit, "MS_DGNLIBLIST")["level"] == "Role"
    assert _var(span_unit, "MS_DEF")["value"] == "C:/Users/Stu/Documents/dgn"
    assert _var(span_unit, "MS_DEF")["level"] == "User"
    assert _var(span_unit, "MS_PLTCFG")["level"] == "WorkSpace"
    refs = {item["rel"] for item in _var(span_unit, "MS_RFDIR")["references"]}
    assert "span_tool.py" in refs
    addin_refs = _var(span_unit, "MS_ADDINPATH")["references"]
    assert any(item["kind"] == "addin" and item["rel"].endswith("span_addin.py") for item in addin_refs)
    fault_ids = {item["id"] for item in span_unit["faults"]}
    assert {"locked-override", "missing-include", "unresolved-include", "hard-coded-user", "missing-slash"} <= fault_ids
    assert any(item["id"] == "locked-override" and item["file"].endswith("extra.cfg") for item in span_unit["faults"])
    assert any(item["id"] == "locked-override" and item["file"] == "span_tool.py" for item in span_unit["faults"])
    assert any(item["id"] == "missing-include" and "no-such.cfg" in item["detail"] for item in span_unit["faults"])
    assert any(item["id"] == "unresolved-include" and "MISSING_FILE" in item["detail"] for item in span_unit["faults"])
    pcf = next(item for item in by_kind["pcf"] if item["name"] == "Old")
    pcf_ids = {item["id"] for item in pcf["faults"]}
    assert "pcf-upgrade" in pcf_ids
    assert "hard-coded-user" in pcf_ids
    assert "missing-slash" in pcf_ids
    assert "WORKSET" in next(item["detail"] for item in pcf["faults"] if item["id"] == "pcf-upgrade")
    assert all(item["prompt"] for item in span_unit["faults"])


def test_config_api_and_mcp_tool(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_ROOT", str(DEMO))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.setenv("BRAIN_MCP_DEMO", "0")
    monkeypatch.delenv("BRAIN_DIGEST", raising=False)
    from backend.app.main import create_app

    with TestClient(create_app()) as client:
        deadline = __import__("time").time() + 20
        while __import__("time").time() < deadline:
            if client.get("/api/health").json().get("phase") == "ready":
                break
        board = client.get("/api/microstation/config")
        assert board.status_code == 200
        body = board.json()
        assert SENTINEL not in json.dumps(body)
        project = next(item for item in body["projects"] if item["project_id"] == "levels-report")
        river = next(item for item in project["units"] if item["name"] == "River" and item["kind"] == "workset")
        assert river["workspace"] == "Bridge"
        assert _var(river, "MS_DEF")["level"] == "User"
        assert _var(river, "MS_DEF")["value"] == "C:/Users/Stu/Documents/dgn"
        assert _var(river, "MS_RFDIR")["locked"] is True
        assert _var(river, "MS_RFDIR")["level"] == "WorkSpace"
        assert _var(river, "_USTN_WORKSETROOT")["value"].endswith("/")
        assert _var(river, "MS_SEEDFILES")["value"].endswith("seed/")
        assert any(item["rel"] == "levels.py" for item in _var(river, "MS_DEF")["references"])
        assert any(item["kind"] == "addin" for item in _var(river, "MS_ADDINPATH")["references"])
        fault_ids = {item["id"] for item in river["faults"]}
        assert {"missing-slash", "hard-coded-user", "locked-override", "missing-include", "unresolved-include"} <= fault_ids
        old = next(item for item in project["units"] if item["kind"] == "pcf")
        assert old["name"] == "OldJob"
        assert any(item["id"] == "pcf-upgrade" for item in old["faults"])
        one = client.get("/api/microstation/config/levels-report")
        assert one.status_code == 200
        assert any(item["name"] == "River" for item in one.json()["units"])
        assert client.get("/api/microstation/config/not-a-folder").status_code == 404
        assert client.get("/api/microstation/config/inbox-triage").status_code == 404

    brain = build_brain(DEMO)
    store.save_scan(DEMO, "sig", brain)
    index = {"root": DEMO, "brain": brain, "scanning": False, "source": "memory", "updated_at": brain["scanned_at"]}
    specs = {tool["name"]: tool for tool in tool_specs()}
    assert specs["get_microstation_config"]["annotations"]["readOnlyHint"] is True
    called = run_tool("get_microstation_config", {"project": "levels-report", "workset": "River"}, index)
    assert called["is_error"] is False
    assert called["bytes"] <= 20_000
    assert "MS_RFDIR" in called["text"]
    assert "locked" in called["text"].lower() or '"locked": true' in called["text"]
    assert SENTINEL not in called["text"]
    missing = run_tool("get_microstation_config", {"project": "missing-folder"}, index)
    assert "No project" in missing["text"]


def test_mcp_config_answer_stays_capped(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_MCP_DEMO", "0")
    monkeypatch.setattr("backend.app.mcp_tools.MAX_BYTES", 180)
    project = tmp_path / "notes"
    project.mkdir()
    (project / "WorkSet.cfg").write_text("MS_DEF = " + ("p/" * 400) + "\n", encoding="utf-8")
    brain = build_brain(tmp_path)
    index = {"root": tmp_path, "brain": brain, "scanning": False, "source": "memory", "updated_at": None}
    called = run_tool("get_microstation_config", {}, index)
    assert called["truncated"] is True
    assert called["text"].endswith("[truncated to 20 KB]")
    assert len(called["text"].encode("utf-8")) <= 20_000
