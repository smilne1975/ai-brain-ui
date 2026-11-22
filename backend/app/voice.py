"""Local-only, review-gated WAV transcription using an installed whisper.cpp CLI."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, Semaphore, Timer
from uuid import uuid4

from backend.app.redact import redact

MAX_BYTES = 24 * 1024 * 1024
MAX_SECONDS = 120
_ID = re.compile(r"[0-9a-f]{32}")
_LOCK = Lock()
_RUNNING = Semaphore(1)
_PENDING: dict[str, dict] = {}


def _configured() -> tuple[Path, Path] | None:
    paths = tuple(Path(os.getenv(key, "")).expanduser() for key in ("BRAIN_WHISPER_EXE", "BRAIN_WHISPER_MODEL"))
    if not all(path.is_absolute() and not path.drive.startswith("\\\\") and path.is_file() for path in paths):
        return None
    if os.name == "nt" and paths[0].suffix.casefold() != ".exe":
        return None
    return paths[0], paths[1]


def available() -> bool:
    return _configured() is not None


def _duration(audio: bytes) -> int:
    if len(audio) > MAX_BYTES:
        raise ValueError("File exceeds the 24 MiB audio limit")
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            channels, width, rate, count = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()
            if channels not in (1, 2) or width != 2 or not (8_000 <= rate <= 48_000 and 0 < count <= rate * MAX_SECONDS):
                raise ValueError("Use a 16-bit PCM WAV file of at most two minutes (8–48 kHz, mono or stereo)")
            frames = wav.readframes(count)
            if len(frames) != count * channels * width:
                raise ValueError("The WAV audio is incomplete")
            if not any(frames):
                raise ValueError("The WAV file contains silence")
            return (count * 1000) // rate
    except (wave.Error, EOFError) as exc:
        raise ValueError("A valid 16-bit PCM WAV file is required") from exc


def _segments(raw: dict, duration_ms: int) -> list[dict]:
    output = []
    for row in raw.get("transcription", [])[:160]:
        if not isinstance(row, dict) or not isinstance(row.get("text"), str) or not isinstance(row.get("offsets"), dict):
            continue
        start, end = row["offsets"].get("from"), row["offsets"].get("to")
        text = redact(" ".join(row["text"].split()))[:600]
        if not (type(start) is int and type(end) is int and 0 <= start < min(end, duration_ms) and text):
            continue
        if re.fullmatch(r"\[[^\]]+\]", text):  # non-speech label
            continue
        action = re.match(r"(?:action(?: item)?|todo|to-do)\s*[:.,-]\s*(.+)", text, re.I)
        output.append({"segment": len(output), "start_ms": start, "end_ms": min(end, duration_ms),
                       "excerpt": text, "text": action[1] if action else text,
                       "kind": "action" if action else "observation"})
    return output


def _transcribe(executable: Path, model: Path, audio: bytes, duration_ms: int) -> list[dict]:
    with TemporaryDirectory(prefix="ai-brain-voice-") as temporary:
        directory = Path(temporary)
        wav, output = directory / "input.wav", directory / "transcript"
        wav.write_bytes(audio)
        env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG") if key in os.environ}
        env["PATH"] = str(executable.parent) + os.pathsep + os.defpath
        try:
            subprocess.run([str(executable), "-m", str(model), "-f", str(wav), "-oj", "-of", str(output),
                            "-t", "2", "-l", "en", "-ng", "-sns", "-nf"],
                           cwd=directory, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True, timeout=180)
            report = output.with_suffix(".json")
            if not report.is_file() or report.stat().st_size > 1_000_000:
                raise ValueError("The local transcriber did not return a readable transcript")
            parsed = json.loads(report.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict) or not isinstance(parsed.get("transcription"), list):
                raise ValueError("Unexpected local transcript format")
            return _segments(parsed, duration_ms)
        except (OSError, UnicodeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            raise ValueError("Local transcription failed or timed out; no cloud fallback was used") from exc


def _scope(root: Path, project: dict) -> tuple[Path, str]:
    return root.resolve(), project["rel"]


def _folder(root: Path, project: dict) -> Path:
    scope = hashlib.sha256(project["rel"].encode()).hexdigest()[:24]
    result = root.resolve() / ".brain" / "voice-notes" / scope
    if result.resolve() != result:
        raise ValueError("Voice-note storage cannot use a linked directory")
    return result


def _expire(identifier: str) -> None:
    with _LOCK:
        _PENDING.pop(identifier, None)


def draft(root: Path, project: dict, audio: bytes, filename: str) -> dict:
    configured = _configured()
    if not configured:
        raise ValueError("Local speech recognition is not configured; no cloud fallback is available")
    if not _RUNNING.acquire(blocking=False):
        raise ValueError("Another local transcription is in progress")
    try:
        duration_ms = _duration(audio)
        items = _transcribe(*configured, audio, duration_ms)
        if not items:
            raise ValueError("No clear speech was found in the recording")
        identifier = uuid4().hex
        name = redact(re.split(r"[/\\]", filename)[-1])[:160] or "Voice memo.wav"
        with _LOCK:
            if len(_PENDING) >= 4:
                raise ValueError("Too many voice memos are awaiting review; cancel one or wait for it to expire")
            _PENDING[identifier] = {"scope": _scope(root, project), "items": items, "audio": audio,
                                    "filename": name, "expires": time.monotonic() + 900}
        timer = Timer(900, _expire, args=(identifier,))
        timer.daemon = True
        timer.start()
        return {"id": identifier, "filename": name, "items": items}
    finally:
        _RUNNING.release()


def discard(root: Path, project: dict, identifier: str) -> None:
    with _LOCK:
        pending = _PENDING.get(identifier)
        if pending and pending["scope"] == _scope(root, project):
            _PENDING.pop(identifier)


def approve(root: Path, project: dict, identifier: str, selected: list[dict]) -> dict:
    if not _ID.fullmatch(identifier):
        raise ValueError("Invalid voice-note draft")
    with _LOCK:
        pending = _PENDING.get(identifier)
        if not pending or pending["scope"] != _scope(root, project) or pending["expires"] < time.monotonic():
            raise ValueError("This draft expired or could not be found; transcribe it again")
        candidates = {item["segment"]: item for item in pending["items"]}
        approved = []
        used = set()
        for edit in selected:
            segment = edit["segment"]
            text = redact(" ".join(edit["text"].split()))[:600]
            if segment not in candidates or segment in used or not text:
                raise ValueError("Each approved note must match a different transcript segment and have text")
            approved.append({**candidates[segment], "text": text, "kind": edit["kind"]})
            used.add(segment)
        home = _folder(root, project)
        if home.is_dir() and sum(1 for path in home.iterdir() if _ID.fullmatch(path.name)) >= 100:
            raise ValueError("This project has reached its limit of 100 stored voice memos")
        home.mkdir(parents=True, exist_ok=True)
        folder = home / identifier
        temporary = home / f".pending-{identifier}"
        temporary.mkdir()
        row = {"id": identifier, "filename": pending["filename"], "items": approved,
               "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            (temporary / "original.wav").write_bytes(pending["audio"])
            (temporary / "notes.json").write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
            temporary.rename(folder)
        finally:
            if temporary.is_dir():
                for name in ("original.wav", "notes.json"):
                    (temporary / name).unlink(missing_ok=True)
                temporary.rmdir()
        _PENDING.pop(identifier)
    return row


def audio_path(root: Path, project: dict, identifier: str) -> Path:
    if not _ID.fullmatch(identifier):
        raise FileNotFoundError
    path = _folder(root, project) / identifier / "original.wav"
    if path.resolve() != path or not path.is_file():
        raise FileNotFoundError
    return path


def items(root: Path, project: dict) -> list[dict]:
    result = []
    for path in _folder(root, project).glob("*/notes.json"):
        if not _ID.fullmatch(path.parent.name) or path.resolve() != path:
            continue
        try:
            if path.stat().st_size <= 200_000:
                record = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(record, dict) and record.get("id") == path.parent.name and isinstance(record.get("items"), list):
                    result.append(record)
        except (OSError, UnicodeError, ValueError):
            continue
    return sorted(result, key=lambda row: row.get("approved_at", ""), reverse=True)[:100]
