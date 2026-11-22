from __future__ import annotations

import io
import json
from pathlib import PurePosixPath
from zipfile import ZipFile

import pytest

from backend.app import knowledge, obsidian, scanner


def test_obsidian_package_relinks_notes_and_canvas_paths_without_copying_sources(tmp_path):
    project_dir = tmp_path / "levels"
    project_dir.mkdir()
    source = project_dir / "README.md"
    source.write_text("# Export levels\n\nUse the selected IFC profile.", encoding="utf-8")
    (project_dir / ".env").write_text("BRAIN_PLACEHOLDER_SECRET=not-in-export\n", encoding="utf-8")
    brain = scanner.build_brain(tmp_path)
    project = brain["projects"][0]
    note = knowledge.preview(tmp_path, brain, project["id"], "IFC profile")
    knowledge.approve(tmp_path, brain, project["id"], note["content"], None, topic=note["topic"])
    main = knowledge.preview(tmp_path, brain, project["id"], "Handover")
    knowledge.approve(tmp_path, brain, project["id"], main["content"] + "[[IFC profile|Procedure]]\n[[Outside vault]]\n", None, topic=main["topic"])
    preview = obsidian.preview(tmp_path, brain, project)
    assert preview["unresolved_count"] == 1
    name, data = obsidian.archive(tmp_path, brain, project, preview["export_id"], preview["token"])
    assert name == f"{preview['folder']}.zip"
    with ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        assert sorted(names) == preview["paths"]
        map_path = f"{preview['folder']}/Project Map.canvas"
        canvas = json.loads(archive.read(map_path))
        node_ids = {node["id"] for node in canvas["nodes"]}
        assert len(node_ids) == len(canvas["nodes"])
        assert all(edge["fromNode"] in node_ids and edge["toNode"] in node_ids for edge in canvas["edges"])
        assert all(node["file"] in names for node in canvas["nodes"] if node["type"] == "file")
        docs = {PurePosixPath(path).name: archive.read(path).decode() for path in names if "/pages/" in path}
        handover = next(text for text in docs.values() if text.startswith("# Handover"))
        linked_path = next(path for path, text in docs.items() if text.startswith("# IFC profile"))
        assert f"[Procedure]({linked_path})" in handover and "Outside vault (unresolved link)" in handover
        assert all("not-in-export" not in archive.read(path).decode() for path in names)
        assert not any(path.endswith(("/README.md", "/.env")) for path in names)
    source.write_text("# New settings", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        obsidian.archive(tmp_path, brain, project, preview["export_id"], preview["token"])
