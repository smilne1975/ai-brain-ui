from backend.app import ask, scanner


def test_scan_reports_bounded_reasons_without_treating_skips_as_evidence(tmp_path, monkeypatch):
    monkeypatch.delenv("BRAIN_INDEX_PDF", raising=False)
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    monkeypatch.setattr(scanner, "MAX_FILE_BYTES", 96)
    (tmp_path / "plan.pdf").write_bytes(b"not indexed unless optional PDF mode is enabled")
    (tmp_path / "notes.md").write_text("BIM clearance notes\n" * 10, encoding="utf-8")
    (tmp_path / "binary.data").write_bytes(b"\0binary")
    (tmp_path / "unreadable.md").write_text("content", encoding="utf-8")
    original = scanner._scan_file
    monkeypatch.setattr(scanner, "_scan_file", lambda pid, root, path: None if path.name == "unreadable.md" else original(pid, root, path))
    brain = scanner.build_brain(tmp_path)
    coverage = brain["coverage"]
    assert coverage["counts"] == {"skipped": 2, "unreadable": 1, "partial": 1}
    issues = {item["rel"]: item for item in coverage["issues"]}
    assert issues["plan.pdf"]["status"] == "skipped"
    assert issues["binary.data"]["reason"] == "Binary data has no searchable text"
    assert issues["notes.md"]["status"] == "partial"
    assert issues["unreadable.md"]["status"] == "unreadable"
    assert not {rec["rel"] for rec in brain["files"]} & {"unreadable.md", "plan.pdf"}
    assert ask.answer(brain, "binary.data", None, None)["evidence"] == []
