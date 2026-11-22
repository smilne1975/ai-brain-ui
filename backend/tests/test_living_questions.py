from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app import ask, clips, evidence, living_questions, old_ideas, scanner


def _note(root, name, text):
    root.mkdir(exist_ok=True, parents=True)
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def test_source_families_require_a_real_link_or_exact_captured_content(tmp_path):
    def item(identifier, url, text):
        return {"id": identifier, "label": identifier, "source_url": url, "excerpt": text, "_evidence_hash": evidence.text_key(text)}

    original = "A report about local transcription records an open measurement protocol and prints the final result for others to check."
    first = item("first", "https://example.com/report?edition=2", original)
    edition = item("edition", "https://example.com/report?edition=1", "Earlier revision.")
    copy = item("copy", "https://example.net/reprint", original)
    same = item("tracking", "https://example.com/report?edition=2&utm_source=feed#overview", "Selection from the same page.")
    known = item("known", "https://notes.example/summary", "Paraphrased separate summary.")
    unrelated = item("other", "https://new.example/independent", "Another measurement.")
    settings = tmp_path / ".brain"
    settings.mkdir()
    (settings / "evidence-origins.json").write_text(json.dumps({known["source_url"]: first["source_url"]}), encoding="utf-8")
    grouped = evidence.group([known, same, first, copy, edition, unrelated], evidence.confirmed_origins(tmp_path))
    assert [row["id"] for row in grouped] == ["known", "edition", "other"]
    assert grouped[0]["confirmed_origin"] == first["source_url"] and grouped[0]["repeated_count"] == 3
    assert set(grouped[0]["evidence_basis"]) == {"same URL", "identical captured text", "user-confirmed origin"}
    assert all("_evidence_hash" not in row for row in grouped)
    only_copy = evidence.group([known], evidence.confirmed_origins(tmp_path))[0]
    assert "confirmed_origin" not in only_copy  # Out-of-scope originals never appear.


def test_living_questions_find_new_and_challenging_evidence_without_rewriting_reviewed_state(tmp_path, monkeypatch):
    root = tmp_path
    _note(root / "public", "misc.md", "An unrelated weekly plan.")
    _note(root / "other", "private-by-scope.md", "Transcription reliability failed badly in an out-of-scope trial.")
    brain = scanner.build_brain(root)
    monkeypatch.setattr(ask.semantic, "rank", lambda *a: pytest.fail("must stay local without embedding inference"))
    monkeypatch.setattr(ask, "complete", lambda *a, **k: pytest.fail("must not call a model"))
    row = living_questions.follow(root, brain, "Is transcription reliability sufficient?", ["public"], "failed badly")
    assert not row["reviewed"]["items"]
    content = "Transcription reliability improved in our benchmark after the microphone upgrade. The notes record several interviews and checked outcomes."
    _note(root / "public", "transcription.md", content)
    brain = scanner.build_brain(root)
    checked = living_questions.change(root, brain, row["id"], "check", 1)
    assert not checked["reviewed"]["items"] and checked["pending"]["changes"][0]["type"] == "new matching evidence"
    with pytest.raises(ValueError, match="changed"):
        living_questions.change(root, brain, row["id"], "accept", 1)
    reviewed = living_questions.change(root, brain, row["id"], "accept", 2)
    assert len(reviewed["reviewed"]["items"]) == 1
    _note(root / "public", "copy.md", content)
    brain = scanner.build_brain(root)
    duplicate = living_questions.change(root, brain, row["id"], "check", 3)
    assert duplicate["pending"] is None
    _note(root / "public", "followup.md", "A second transcription reliability test failed badly on multiple speakers, despite the improvement elsewhere.")
    checked = living_questions.change(root, scanner.build_brain(root), row["id"], "check", 4)
    assert [c["type"] for c in checked["pending"]["changes"]] == ["possible challenge"]
    assert checked["pending"]["changes"][0]["after"]["label"].endswith("followup.md")
    with pytest.raises(ValueError, match="after this comparison"):
        living_questions.change(root, brain, row["id"], "accept", 5)
    narrower = brain.copy()
    narrower["projects"] = [p for p in brain["projects"] if p["id"] == "other"]
    unavailable = living_questions.change(root, narrower, row["id"], "check", 5)
    assert unavailable["pending"]["candidate"] == {"items": [], "incomplete": True, "missing_scopes": 1}


def test_original_evidence_collapses_reposts_in_ask_and_respects_the_scope(tmp_path):
    original = "Transcription reliability was tested on a small community recording, with a separate second test still needed."
    _note(tmp_path / "public", "original.md", original)
    _note(tmp_path / "other", "unrelated.md", "An independent evaluation of transcription reliability.")
    brain = scanner.build_brain(tmp_path)
    project = next(p for p in brain["projects"] if p["id"] == "public")
    markdown = f"---\nurl: https://example.com/reprint\n---\n{original}"
    preview = clips.preview(markdown, "reprint.md")
    clip, _ = clips.import_clip(tmp_path, project, markdown, "reprint.md", preview["id"])
    reply = ask.answer(brain, "transcription reliability", "public", None, web_clips=[{**clip, "project_id": "public"}])
    assert len(reply["evidence"]) == 1 and reply["evidence"][0]["repeated_count"] == 1
    assert reply["evidence"][0]["evidence_basis"] == ["identical captured text"]
    assert "unrelated" not in str(reply["evidence"])


def test_old_connection_has_two_passages_and_feedback_is_local(tmp_path):
    now = datetime.now(timezone.utc)
    _note(tmp_path / "public", "current.md", "Design a subscription cancellation checklist with the renewal reminder and billing date.")
    earlier = _note(tmp_path / "public", "older.md", "The subscription cancellation checklist failed when we relied on an emailed renewal reminder.")
    other = _note(tmp_path / "neighbor", "other.md", "Our subscription cancellation checklist worked after a billing reminder was added.")
    for path in (earlier, other):
        timestamp = (now - timedelta(days=65)).timestamp()
        os.utime(path, (timestamp, timestamp))
    brain = scanner.build_brain(tmp_path)
    scope = living_questions.scope_for(brain, ["public"])
    question = "How should I design a subscription cancellation checklist?"
    result = old_ideas.suggest(tmp_path, brain, question, scope, at=now)
    assert result["relation"] == "earlier dead end"
    assert result["older"]["label"] == "public/older.md" and "failed" in result["older"]["excerpt"]
    assert result["current"]["label"] == "public/current.md"
    assert not old_ideas.suggest(tmp_path, brain, "What is the weather?", scope, at=now)
    old_ideas.remember(tmp_path, result, "keep")
    assert old_ideas.kept(tmp_path, brain)[0]["id"] == result["id"]
    assert not old_ideas.suggest(tmp_path, brain, question, scope, at=now)


def test_question_endpoints_are_off_in_private_mode_and_reject_cross_site_writes(tmp_path, monkeypatch):
    from backend.app.main import create_app

    _note(tmp_path / "public", "note.md", "Check local backup restore steps.")
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    with TestClient(create_app()) as client:
        for _ in range(100):
            if client.get("/api/health").json()["phase"] == "ready":
                break
            time.sleep(.02)
        body = {"question": "How do local backups work?", "project_ids": ["public"]}
        assert client.post("/api/living-questions", json=body, headers={"Origin": "https://third-party.example"}).status_code == 403
        assert client.post("/api/living-questions", json={**body, "project_ids": ["missing"]}).status_code == 409
        assert client.post("/api/living-questions", json=body).status_code == 200
        assert len(client.get("/api/living-questions").json()["items"]) == 1
        monkeypatch.setenv("BRAIN_PRIVATE_FOLDERS", '["anything"]')
        assert client.get("/api/living-questions").status_code == 403
        assert client.post("/api/old-ideas/preview", json=body).status_code == 403
