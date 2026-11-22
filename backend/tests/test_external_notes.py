from __future__ import annotations

import json

import pytest

from backend.app import ask, external_notes, scanner


def test_external_note_folders_are_opt_in_read_only_and_local(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    for folder in ("levels", "sheets"):
        (root / folder).mkdir(parents=True)
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "Design.md"
    note.write_text("1. Survey origin\nCheck the prismwall clearance before issuing elevations.", encoding="utf-8")
    (vault / "raw.one").write_bytes(b"not a text export")
    brain = scanner.build_brain(root)
    monkeypatch.delenv("BRAIN_NOTES_ROOTS", raising=False)
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    assert external_notes.collect(brain["projects"]) == ([], [])
    monkeypatch.setenv("BRAIN_NOTES_ROOTS", json.dumps({"levels": [{"path": str(vault), "label": "Vault", "kind": "obsidian"}]}))
    found, warnings = external_notes.collect(brain["projects"])
    assert len(found) == 1 and "1 skipped" in warnings[0]
    monkeypatch.setattr(ask, "complete", lambda *_args, **_kwargs: pytest.fail("Do not send external note excerpts to a model"))
    result = ask.answer(brain, "prismwall clearance", None, {"display": "test"}, external_notes=found)
    assert result["local_only_evidence"] and result["evidence"][0]["label"] == "levels/Vault/Design.md"
    assert not ask.answer(brain, "prismwall", "sheets", None, external_notes=found)["evidence"]
    assert "prismwall" in note.read_text(encoding="utf-8")
    monkeypatch.setenv("BRAIN_PRIVATE_FOLDERS", '["not-shared"]')
    assert external_notes.collect(brain["projects"]) == ([], [])
