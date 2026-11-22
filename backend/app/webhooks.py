"""An explicitly confirmed, narrowly scoped n8n event handoff."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

_LOCK = Lock()
_SECRET = secrets.token_bytes(32)
_ID = re.compile(r"[0-9a-f]{32}")
KINDS = {"test", "ifc_handover_ready", "knowledge_reviewed"}


def _encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _config(project: dict) -> dict | None:
    try:
        configs = json.loads(os.getenv("BRAIN_N8N_PROJECTS", "{}"))
        row = configs.get(project["rel"]) if isinstance(configs, dict) else None
        if not isinstance(row, dict):
            return None
        endpoint, key = row.get("url"), row.get("project_key")
        token = os.environ.get(row.get("token_env", ""), "")
        if (not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,39}", key)
                or not isinstance(endpoint, str) or len(endpoint) > 1024 or not token or len(token) > 1024
                or any(char.isspace() or not 33 <= ord(char) <= 126 for char in token)
                or any(char.isspace() or ord(char) < 32 or char == "\\" for char in endpoint)):
            return None
        parts = urlsplit(endpoint)
        port = parts.port
        loopback = parts.hostname in {"localhost", "127.0.0.1", "::1"}
        if (not parts.hostname or parts.username is not None or parts.password is not None or parts.query or parts.fragment
                or not parts.path or parts.path == "/" or not (parts.scheme == "https" or parts.scheme == "http" and loopback)):
            return None
        hostname = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
        origin = f"{parts.scheme}://{hostname}{f':{port}' if port else ''}"
        return {"url": endpoint, "origin": origin, "project_key": key, "token": token,
                "destination_key": hashlib.sha256(_encoded([endpoint, key])).hexdigest()}
    except (ValueError, TypeError):
        return None


def _required(project: dict) -> dict:
    if not (config := _config(project)):
        raise ValueError("An authenticated n8n destination is not configured for this project")
    return config


def _signature(payload: dict, expires: int, config: dict, project: dict) -> str:
    msg = _encoded([payload, expires, config["destination_key"], project["rel"]])
    return hmac.digest(_SECRET, msg, "sha256").hex()


def _directory(root: Path, project: dict) -> Path:
    scope = hashlib.sha256(project["rel"].encode()).hexdigest()[:24]
    result = root.resolve() / ".brain" / "n8n-events" / scope
    if result.resolve() != result:
        raise ValueError("Webhook storage cannot use a linked directory")
    return result


def _read(path: Path) -> dict | None:
    try:
        if path.is_symlink() or path.stat().st_size > 32_000:
            return None
        row = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(row, dict) or row.get("id") != path.stem or not isinstance(row.get("attempts"), list):
            return None
        payload = row.get("payload")
        if (row.get("status") not in {"delivery unknown", "accepted", "rejected"} or not isinstance(payload, dict)
                or set(payload) != {"id", "type", "project_key", "created_at"} or payload["id"] != path.stem
                or any(not isinstance(value, str) for value in payload.values()) or payload["type"] not in KINDS):
            return None
        return row
    except (OSError, ValueError):
        return None


def _save(path: Path, row: dict) -> None:
    if path.is_symlink():
        raise ValueError("Webhook storage cannot use a linked file")
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        try:
            json.dump(row, handle, ensure_ascii=False)
            handle.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def preview(project: dict, kind: str) -> dict:
    config = _required(project)
    if kind not in KINDS:
        raise ValueError("Unsupported project event")
    payload = {"id": uuid4().hex, "type": kind, "project_key": config["project_key"], "created_at": _now()}
    expires = int(time.time()) + 900
    return {"payload": payload, "destination": config["origin"], "expires": expires,
            "confirmation": _signature(payload, expires, config, project)}


def list_events(root: Path, project: dict) -> dict:
    config = _config(project)
    events = []
    for path in _directory(root, project).glob("*.json"):
        if _ID.fullmatch(path.stem) and (row := _read(path)):
            events.append(_public(row))
    events.sort(key=lambda row: row["payload"]["created_at"], reverse=True)
    return {"enabled": config is not None, "destination": config["origin"] if config else None, "events": events[:100]}


def _public(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "destination_key"}


def send(root: Path, project: dict, payload: dict, expires: int, confirmation: str) -> dict:
    config = _required(project)
    if not (_ID.fullmatch(payload["id"]) and payload["type"] in KINDS and payload["project_key"] == config["project_key"]
            and time.time() <= expires and hmac.compare_digest(confirmation, _signature(payload, expires, config, project))):
        raise ValueError("The confirmation expired or the event changed; preview it again")
    path = _directory(root, project) / f"{payload['id']}.json"
    with _LOCK:
        if path.exists():
            raise ValueError("This event was already submitted; check its delivery record")
        if sum(1 for _ in path.parent.glob("*.json")) >= 500:
            raise ValueError("This project has reached its limit of 500 webhook records")
        row = {"id": payload["id"], "payload": payload, "destination": config["origin"],
               "destination_key": config["destination_key"], "attempts": []}
        return _attempt(path, row, config)


def retry(root: Path, project: dict, event_id: str) -> dict:
    config = _required(project)
    if not _ID.fullmatch(event_id):
        raise KeyError(event_id)
    path = _directory(root, project) / f"{event_id}.json"
    with _LOCK:
        row = _read(path)
        if not row:
            raise KeyError(event_id)
        if (row.get("destination_key") != config["destination_key"] or row["status"] == "accepted"
                or row["payload"]["project_key"] != config["project_key"] or len(row["attempts"]) >= 5):
            raise ValueError("This event cannot be retried with the current settings")
        return _attempt(path, row, config)


def _attempt(path: Path, row: dict, config: dict) -> dict:
    attempt = {"at": _now(), "status": "delivery unknown", "http_status": None}
    row["attempts"].append(attempt)
    row["status"] = attempt["status"]
    _save(path, row)
    try:
        attempt["http_status"] = _post(config, row["payload"])
        attempt["status"] = "accepted" if 200 <= attempt["http_status"] < 300 else "rejected"
    except httpx.HTTPError:
        pass  # The workflow might have received the event; never retry automatically.
    row["status"] = attempt["status"]
    _save(path, row)
    return _public(row)


def _post(config: dict, payload: dict) -> int:
    with httpx.Client(timeout=6, follow_redirects=False, trust_env=False) as client:
        with client.stream("POST", config["url"], json=payload, headers={
            "Authorization": "Bearer " + config["token"], "Idempotency-Key": payload["id"],
        }) as response:
            return response.status_code
