import json
import time

from fastapi.testclient import TestClient

from backend.app import ask, clips, knowledge, living_questions, project_records, scanner
from backend.app.main import create_app


def note(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def app_for(root, monkeypatch):
    monkeypatch.setenv("BRAIN_ROOT", str(root))
    monkeypatch.setenv("BRAIN_CACHE", str(root / ".brain" / "cache.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    return TestClient(create_app())


def ready(client):
    for _ in range(150):
        if client.get("/api/health").json()["phase"] == "ready":
            return
        time.sleep(.02)
    raise AssertionError("scan did not finish")


def test_source_impact_is_read_only_and_preserves_every_recorded_dependency(tmp_path, monkeypatch):
    source = note(tmp_path, "work/input.md", "Transcription calibration improved interview precision.")
    note(tmp_path, "work/unrelated.md", "An unrelated weekly plan.")
    brain = scanner.build_brain(tmp_path)
    project = brain["projects"][0]
    for topic, ids in (("first", ["work:input.md"]), ("second", ["work:input.md"]), ("unrelated", ["work:unrelated.md"])):
        page = knowledge.preview(tmp_path, brain, "work", topic, ids)
        knowledge.approve(tmp_path, brain, "work", page["content"], page["current_revision"],
                          {row["id"]: row["sha256"] for row in page["sources"]}, topic, ids)
    project_records.save(tmp_path, brain, project, {"kind": "decision", "title": "Pick a calibration method",
        "text": "Repeat the calibration with each microphone.", "source_ids": ["work:input.md"]})
    living_questions.follow(tmp_path, brain, "Did transcription calibration improve interview precision?", ["work"], "")
    source.write_text("Transcription calibration was repeated and remains inconclusive.", encoding="utf-8")
    before = {path: path.read_bytes() for path in (tmp_path / ".brain" / "knowledge").rglob("*") if path.is_file()}
    with app_for(tmp_path, monkeypatch) as client:
        ready(client)
        response = client.get("/api/source-review/work")
        assert response.status_code == 200
        [impact] = response.json()["items"]
        assert impact["rel"] == "input.md" and impact["status"] == "changed"
        assert sorted(row["kind"] for row in impact["affected"]) == ["decision", "page", "page", "question"]
        assert next(row for row in impact["affected"] if row["kind"] == "question")["passage"].startswith("Transcription calibration improved")
        assert not any("unrelated" in row["label"].lower() for row in impact["affected"])
    assert before == {path: path.read_bytes() for path in before}
    assert "inconclusive" in source.read_text(encoding="utf-8")


def test_keep_dismiss_link_review_survives_reload_without_mutation_or_excluded_notes(tmp_path, monkeypatch):
    bodies = {
        "microphone.md": "Calibration transcription required an initial microphone measurement.",
        "followup.md": "We repeated calibration transcription with a second recording.",
        "later.md": "Another calibration transcription attempt needs timing checks.",
        "existing.md": "Calibration transcription is discussed here.\n\n[[followup]]",
        "private/classified.md": "Calibration transcription AND privateclue.",
    }
    for rel, text in bodies.items():
        note(tmp_path, f"work/{rel}", text)
    monkeypatch.setenv("BRAIN_PRIVATE_FOLDERS", json.dumps(["work/private"]))
    endpoint = "/api/link-review/work"
    with app_for(tmp_path, monkeypatch) as client:
        ready(client)
        response = client.get(endpoint)
        assert response.status_code == 200 and "privateclue" not in response.text
        candidates = response.json()["suggested"]
        assert len(candidates) >= 2 and not any({end["label"] for end in row["ends"]} == {"existing.md", "followup.md"} for row in candidates)
        keep, dismiss = (row["id"] for row in candidates[:2])
        assert client.post(f"{endpoint}/{keep}", json={"state": "kept"}, headers={"Origin": "https://example.com"}).status_code == 403
        assert client.post(f"{endpoint}/{keep}", json={"state": "kept"}).status_code == 200
        assert client.post(f"{endpoint}/{dismiss}", json={"state": "dismissed"}).status_code == 200
        assert client.get("/api/captures/work").status_code == 403
    with app_for(tmp_path, monkeypatch) as client:
        ready(client)
        result = client.get(endpoint).json()
        assert [row["id"] for row in result["kept"]] == [keep]
        assert keep not in [row["id"] for row in result["suggested"]] and dismiss not in [row["id"] for row in result["suggested"]]
    assert all((tmp_path / "work" / rel).read_text(encoding="utf-8") == text for rel, text in bodies.items())


def test_capture_queue_is_idempotent_and_only_approved_clips_enter_ask(tmp_path, monkeypatch):
    note(tmp_path, "work/README.md", "Neutral project note.")
    endpoint = "/api/captures/work"
    with app_for(tmp_path, monkeypatch) as client:
        ready(client)
        markdown = "---\nurl: https://example.com/interview\ntitle: Local interview\n---\nThe microphone logs test quartzphrasetoken today."
        body = {"kind": "clip", "text": markdown, "filename": "interview.md"}
        assert client.post(endpoint, json=body, headers={"Origin": "https://example.com"}).status_code == 403
        draft = client.post(endpoint, json=body).json()["item"]
        duplicated = client.post(endpoint, json=body).json()
        assert duplicated["status"] == "duplicate" and duplicated["item"]["id"] == draft["id"]
        assert client.post(endpoint, json={**body, "text": "not a clip"}).status_code == 400
        plain = client.post(endpoint, json={"kind": "note", "filename": "New note", "text": "lemoncapturesentinel"}).json()["item"]

        def find(query):
            return client.post("/api/ask", json={"question": query, "project_id": "work"}).json()["evidence"]

        assert not find("quartzphrasetoken")
        assert client.post(f"{endpoint}/{draft['id']}", json={"action": "approve", "tags": "recording"}).status_code == 200
        assert any(row["kind"] == "clip" for row in find("quartzphrasetoken"))
        assert client.post(endpoint, json=body).json()["existing_clip"]["id"] == clips.preview(markdown, "interview.md")["id"]
        assert client.post(f"{endpoint}/{plain['id']}", json={"action": "approve"}).status_code == 200
        assert not find("lemoncapturesentinel")
        assert client.post(f"{endpoint}/{draft['id']}", json={"action": "undo"}).status_code == 200
        assert not find("quartzphrasetoken")
        assert len(client.get(endpoint).json()["items"]) == 2


def test_saved_answer_preserves_matched_passages_but_not_unverified_copy(tmp_path):
    source = note(tmp_path, "work/calibration-plan.md", "Transcription calibration improved interview precision.")
    brain = scanner.build_brain(tmp_path)
    [hit] = ask.answer(brain, "transcription calibration", "work", None)["evidence"]
    knowledge.save_answer(tmp_path, brain, "work", "Calibration result", "Review this finding.", [hit["id"]],
                          [{"id": hit["id"], "excerpt": "Fabricated passage"}, {"id": hit["id"], "excerpt": hit["excerpt"]}])
    source.write_text("New text after review.", encoding="utf-8")
    [saved] = knowledge.answers(tmp_path, scanner.build_brain(tmp_path))
    [passage] = saved["passages"]
    assert passage["id"] == hit["id"] and passage["excerpt"] == hit["excerpt"] and passage["stale"]
    assert "ai-brain-passage" not in saved["content"]
