"""Review-gated pages, cited answers, cross-project evidence and skill drafts."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import knowledge
from backend.app.ask import answer
from backend.app.scanner import build_brain


@pytest.fixture
def corpus(tmp_path: Path):
    for name, text in (("levels", "# Level export\n\nExport CAD levels to CSV."),
                       ("sheets", "# Sheet export\n\nExport Revit sheets to CSV.")):
        project = tmp_path / name
        project.mkdir()
        (project / "README.md").write_text(text, encoding="utf-8")
    return tmp_path, build_brain(tmp_path)


def test_reviewed_pages_keep_versions_and_flag_changed_sources(corpus):
    root, brain = corpus
    draft = knowledge.preview(root, brain, "levels")
    assert draft["sources"] and "Export CAD levels" in draft["content"]
    assert knowledge.pages(root, brain) == []
    page = knowledge.approve(root, brain, "levels", draft["content"], draft["current_revision"])
    assert page["revision"]
    assert not knowledge.lint(root, brain)
    with pytest.raises(ValueError, match="changed"):
        knowledge.approve(root, brain, "levels", draft["content"], draft["current_revision"])
    source = root / "levels" / "README.md"
    source.write_text("# Level export\n\nExport a different format.", encoding="utf-8")
    with pytest.raises(ValueError, match="Source files changed"):
        knowledge.approve(root, brain, "levels", draft["content"], page["revision"],
                          {item["id"]: item["sha256"] for item in draft["sources"]})
    assert knowledge.pages(root, brain)[0]["stale_sources"]
    assert knowledge.lint(root, brain)[0]["kind"] == "stale_source"
    newer = knowledge.preview(root, build_brain(root), "levels")
    knowledge.approve(root, brain, "levels", newer["content"], page["revision"])
    assert len(knowledge.pages(root, brain)[0]["revisions"]) == 2
    assert len(list((root / ".brain" / "knowledge" / "levels").glob("*.md"))) == 2


def test_topic_pages_are_distinct_and_health_checks_quotes(corpus):
    root, brain = corpus
    source_id = next(rec["id"] for rec in brain["files"] if rec["project_id"] == "levels")
    draft = knowledge.preview(root, brain, "levels", "CSV export", [source_id])
    content = draft["content"] + '> "Bush invented hypertext" - README.md\n[[missing topic]]\n'
    knowledge.approve(root, brain, "levels", content, None,
                      {src["id"]: src["sha256"] for src in draft["sources"]}, "CSV export", [source_id])
    original = knowledge.preview(root, brain, "levels")
    knowledge.approve(root, brain, "levels", original["content"], None)
    assert {page["page_id"] for page in knowledge.pages(root, brain)} == {"levels", "levels~csv-export"}
    kinds = {finding["kind"] for finding in knowledge.lint(root, brain)}
    assert {"unverified_quote", "broken_link", "orphan"} <= kinds


def test_cross_project_evidence_and_no_unsupported_claims(corpus):
    root, brain = corpus
    reply = answer(brain, "Which projects export CSV?", None, None)
    assert {item["project_id"] for item in reply["evidence"]} == {"levels", "sheets"}
    assert all(item["excerpt"] for item in reply["evidence"])
    scoped = answer(brain, "Which projects export CSV?", None, None, project_ids=["levels"])
    assert {item["project_id"] for item in scoped["evidence"]} == {"levels"}
    unrelated = answer(brain, "quasar zebralight", None, None)
    assert unrelated["evidence"] == []
    assert "no supporting" in unrelated["answer"]


def test_scoped_service_does_not_claim_other_project_connection():
    demo = Path(__file__).resolve().parents[2] / "demo-projects"
    brain = build_brain(demo)
    result = answer(brain, "Which projects use OpenAI?", None, None, project_ids=["local-vision-lab"])
    assert "connected" not in result["answer"].casefold()
    assert all(cite["project_id"] == "local-vision-lab" for cite in result["citations"])


def test_answer_and_skill_do_not_overwrite(corpus):
    root, brain = corpus
    sid = next(rec["id"] for rec in brain["files"] if rec["project_id"] == "levels")
    other_sid = next(rec["id"] for rec in brain["files"] if rec["project_id"] == "sheets")
    saved = knowledge.save_answer(root, brain, "levels", "Export notes", "A sourced answer", [sid, other_sid])
    assert not saved["stale_sources"]
    assert {item["project_id"] for item in saved["sources"]} == {"levels", "sheets"}
    assert not knowledge.answers(root, brain)[0]["stale_sources"]
    from backend.app.ask import answer
    found = answer(brain, "sourced answer", None, None, saved_answers=knowledge.answers(root, brain))
    assert any(item["kind"] == "answer" for item in found["evidence"])
    with pytest.raises(FileExistsError):
        knowledge.save_answer(root, brain, "levels", "Export notes", "Different", [sid])
    skill = knowledge.save_skill(root, brain, "levels", "Export levels", "Use for exporting levels", "1. Review the project")
    assert "SKILL.md" in skill["path"]
    with pytest.raises(FileExistsError):
        knowledge.save_skill(root, brain, "levels", "Export levels", "Again", "2. Overwrite")


def test_knowledge_api(tmp_path: Path, monkeypatch):
    project = tmp_path / "levels"
    project.mkdir()
    (project / "README.md").write_text("# Levels\n\nExport CAD levels.", encoding="utf-8")
    (project / "other.md").write_text("# Other\n\nUnrelated notes.", encoding="utf-8")
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    from backend.app.main import create_app
    import time
    with TestClient(create_app()) as client:
        for _ in range(200):
            if client.get("/api/health").json()["phase"] == "ready":
                break
            time.sleep(.05)
        draft = client.get("/api/knowledge/levels/preview")
        assert draft.status_code == 200
        assert client.get("/api/knowledge/missing/preview").status_code == 404
        initial = client.get("/api/knowledge").json()
        assert not initial["pages"]
        res = client.post("/api/knowledge/levels/approve", json={"content": draft.json()["content"],
            "expected_revision": None, "expected_sources": {item["id"]: item["sha256"] for item in draft.json()["sources"]}})
        assert res.status_code == 200
        assert client.get("/api/knowledge").json()["pages"]
        sid = draft.json()["sources"][0]["id"]
        assert len(draft.json()["sources"]) == 2
        topic = client.get("/api/knowledge/levels/preview", params={"topic": "CAD levels", "source_ids": sid})
        assert topic.status_code == 200 and topic.json()["page_id"] == "levels~cad-levels"
        assert [item["id"] for item in topic.json()["sources"]] == [sid]
        topic_saved = client.post("/api/knowledge/levels/approve", json={"content": topic.json()["content"],
            "expected_revision": None, "topic": "CAD levels", "source_ids": [sid],
            "expected_sources": {item["id"]: item["sha256"] for item in topic.json()["sources"]}})
        assert topic_saved.status_code == 200
        assert len(client.get("/api/knowledge").json()["pages"]) == 2
        selected = client.post("/api/ask", json={"question": "CAD levels", "project_ids": ["levels"]})
        assert selected.status_code == 200 and selected.json()["scope"] == ["levels"]
        saved = client.post("/api/answers", json={"project_id": "levels", "title": "What levels?", "answer": "Export CAD levels.", "source_ids": [sid]})
        assert saved.status_code == 200
        assert client.get("/api/knowledge").json()["answers"]
        blocked = client.post("/api/answers", headers={"Origin": "https://example.com"},
                              json={"project_id": "levels", "title": "Foreign", "answer": "No", "source_ids": [sid]})
        assert blocked.status_code == 403
