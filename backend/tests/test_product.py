import time

from fastapi.testclient import TestClient

from backend.app import scanner, store
from backend.app.main import create_app
from backend.app.mcp_tools import load_index, run_tool, tool_specs


def test_standalone_is_neutral_and_cannot_reuse_cad_cache(tmp_path, monkeypatch):
    root = tmp_path / "notes"
    project = root / "Research"
    project.mkdir(parents=True)
    (project / "visitor.md").write_text("Visitors requested a quiet reading hour.", encoding="utf-8")
    (project / "legacy.py").write_text("from MSPyBentley import WString\n", encoding="utf-8")
    (project / "WorkSet.cfg").write_text("MS_DEF = drawings/\n", encoding="utf-8")
    monkeypatch.setenv("BRAIN_ROOT", str(root))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "scans.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.setenv("BRAIN_COPILOT_CHATS", "0")
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    monkeypatch.setenv("BRAIN_LEGACY_CAD", "1")
    signed_cad = scanner.signature(root)
    cad = scanner.build_brain(root)
    assert cad["legacy_cad"] and cad["projects"][0]["microstation_config"]
    assert "get_microstation_config" in {spec["name"] for spec in tool_specs()}
    store.save_scan(root, signed_cad, cad)
    assert load_index(root)["brain"]["legacy_cad"]

    monkeypatch.delenv("BRAIN_LEGACY_CAD", raising=False)
    assert scanner.signature(root) != signed_cad
    assert load_index(root)["brain"] is None
    assert "get_microstation_config" not in {spec["name"] for spec in tool_specs()}

    with TestClient(create_app()) as client:
        for _ in range(150):
            if client.get("/api/health").json()["phase"] == "ready":
                break
            time.sleep(.02)
        brain = client.get("/api/brain").json()
        assert brain["legacy_cad"] is False and not brain["config_index"]
        assert "microstation" not in brain["projects"][0]
        assert not {"keyin", "workspace", "workset", "variable"} & {node["kind"] for node in brain["architecture"]["projects"]["research"]["nodes"]}
        assert "microstation-python" not in {skill["id"] for skill in brain["skills"]}
        assert client.get("/api/microstation/config").status_code == 404
        assert client.get("/api/microstation/research").status_code == 404
        assert run_tool("get_microstation_config", {}, load_index(root))["is_error"]
        answer = client.post("/api/ask", json={"question": "quiet reading hour", "project_id": "research"}).json()
        assert any("quiet reading hour" in item["excerpt"] for item in answer["evidence"])

    monkeypatch.setenv("BRAIN_LEGACY_CAD", "1")
    assert load_index(root)["brain"] is None


def test_private_folders_override_legacy_cad_opt_in(tmp_path, monkeypatch):
    (tmp_path / "source.py").write_text("from MSPyBentley import WString\n", encoding="utf-8")
    monkeypatch.setenv("BRAIN_PRIVATE_FOLDERS", '["confidential"]')
    monkeypatch.setenv("BRAIN_LEGACY_CAD", "1")
    brain = scanner.build_brain(tmp_path)
    assert brain["legacy_cad"] is False
    assert "microstation-python" not in {skill["id"] for skill in brain["skills"]}
    assert "get_microstation_config" not in {spec["name"] for spec in tool_specs()}
