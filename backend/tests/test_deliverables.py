from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient


def test_deliverable_freezes_evidence_and_reviews_do_not_modify_export(tmp_path, monkeypatch):
    from backend.app.main import create_app

    folder = tmp_path / "levels"
    folder.mkdir()
    src = folder / "README.md"
    src.write_text("# Level export\n\nUse the IFC handover setting.", encoding="utf-8")
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    endpoint = "/api/deliverables/levels"
    with TestClient(create_app()) as client:
        for _ in range(100):
            if client.get("/api/health").json()["phase"] == "ready":
                break
            time.sleep(.02)
        draft = client.get("/api/knowledge/levels/preview").json()
        approved = client.post("/api/knowledge/levels/approve", json={"content": draft["content"],
            "expected_revision": None, "expected_sources": {item["id"]: item["sha256"] for item in draft["sources"]}}).json()
        body = {"title": "IFC handover", "content": "Use the approved export setup.", "page_ids": ["levels"]}
        preview = client.post(f"{endpoint}/preview", json=body).json()
        assert preview["pages"][0]["revision"] == approved["revision"] and preview["pages"][0]["sources"]
        assert client.get(endpoint).json()["items"] == []
        assert client.post(f"{endpoint}/export", json={**body, "content": "Changed after preview", "token": preview["token"]}).status_code == 409
        saved = client.post(f"{endpoint}/export", json={**body, "token": preview["token"]}).json()
        path = Path(saved["artifact_path"])
        original = path.read_bytes()
        assert b"Use the approved" in original
        assert client.get(endpoint).json()["items"][0]["status"] == "current"
        src.write_text("# Changed settings", encoding="utf-8")
        row = client.get(endpoint).json()["items"][0]
        assert row["status"] == "needs review"
        assert [(entry["kind"], entry["label"]) for entry in row["changes"]] == [("source", "README.md")]
        ack = f"{endpoint}/{row['id']}/acknowledge"
        assert client.post(ack, json={"snapshot": "0" * 64}).status_code == 409
        result = client.post(ack, json={"snapshot": row["snapshot"]}).json()
        assert result["status"] == "reviewed" and len(result["reviews"]) == 1
        assert path.read_bytes() == original
        assert result["pages"] == saved["pages"]
        src.write_text("# Further changes", encoding="utf-8")
        assert client.get(endpoint).json()["items"][0]["status"] == "needs review"
