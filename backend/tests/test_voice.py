from __future__ import annotations

import io
import json
import time
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import voice


def _wav() -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16_000)
        writer.writeframes(b"\x05\x00\xfb\xff" * 8000)
    return out.getvalue()


def test_voice_review_links_audio_and_never_uses_cloud(tmp_path, monkeypatch):
    from backend.app.main import create_app

    for folder in ("site", "other"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "README.md").write_text("BIM project", encoding="utf-8")
    audio = _wav()
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path))
    monkeypatch.setenv("BRAIN_CACHE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("BRAIN_DISABLE_WATCH", "1")
    monkeypatch.setenv("BRAIN_DISABLE_LLM", "1")
    monkeypatch.setenv("UNRELATED_SECRET", "not-for-the-transcriber")
    monkeypatch.delenv("BRAIN_WHISPER_EXE", raising=False)
    monkeypatch.delenv("BRAIN_WHISPER_MODEL", raising=False)
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    endpoint = "/api/voice-notes/site"
    header = {"Content-Type": "audio/wav"}
    with TestClient(create_app()) as client:
        for _ in range(100):
            if client.get("/api/health").json()["phase"] == "ready":
                break
            time.sleep(.02)
        assert not client.get(endpoint).json()["available"]
        assert client.post(f"{endpoint}/preview", content=audio, headers=header).status_code == 409
        executable = tmp_path / "whisper-cli.exe"
        model = tmp_path / "model.bin"
        executable.touch()
        model.touch()
        monkeypatch.setenv("BRAIN_WHISPER_EXE", str(executable))
        monkeypatch.setenv("BRAIN_WHISPER_MODEL", str(model))
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            assert args[0] == str(executable) and args[args.index("-m") + 1] == str(model)
            assert "UNRELATED_SECRET" not in kw["env"]
            assert Path(args[args.index("-f") + 1]).read_bytes() == audio
            report = Path(args[args.index("-of") + 1]).with_suffix(".json")
            report.write_text(json.dumps({"transcription": [
                {"offsets": {"from": 0, "to": 400}, "text": "Action: check the riser clearance."},
                {"offsets": {"from": 400, "to": 1000}, "text": "Unapproved observation."},
            ]}), encoding="utf-8")

        monkeypatch.setattr(voice.subprocess, "run", fake_run)
        assert client.post(f"{endpoint}/preview", content=b"bad wav", headers=header).status_code == 400
        res = client.post(f"{endpoint}/preview?filename=walkthrough.wav", content=audio, headers=header)
        assert res.status_code == 200 and len(calls) == 1
        draft = res.json()
        identifier = draft["id"]
        assert draft["items"][0]["kind"] == "action" and draft["items"][0]["end_ms"] == 400
        assert not Path(calls[0][calls[0].index("-f") + 1]).exists()
        assert client.get(endpoint).json()["items"] == []
        route = f"{endpoint}/{identifier}"
        assert client.get(f"{route}/audio").status_code == 404
        body = {"items": [{"segment": 0, "kind": "action", "text": "Check riser C clearance."}]}
        assert client.post(f"/api/voice-notes/other/{identifier}/approve", json=body).status_code == 409
        approved = client.post(f"{route}/approve", json=body).json()
        assert len(approved["items"]) == 1 and approved["items"][0]["text"] == "Check riser C clearance."
        assert client.get(f"{route}/audio").content == audio
        assert client.get(f"/api/voice-notes/other/{identifier}/audio").status_code == 404
        assert client.post(f"{route}/approve", json=body).status_code == 409
        assert "Unapproved observation" not in client.get(endpoint).text
