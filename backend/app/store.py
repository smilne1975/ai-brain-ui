"""SQLite cache for scan documents and model summaries."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def cache_path() -> Path:
    raw = os.environ.get("BRAIN_CACHE", "").strip()
    path = Path(raw).expanduser() if raw else REPO / ".brain" / "cache.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(cache_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scans (
            root TEXT PRIMARY KEY,
            signature TEXT NOT NULL,
            brain TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm (
            cache_key TEXT PRIMARY KEY,
            text TEXT NOT NULL
        )
        """
    )
    return conn


def load_scan(root: Path, signature: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT brain FROM scans WHERE root = ? AND signature = ?", (str(root), signature)).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row[0])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def save_scan(root: Path, signature: str, brain: dict) -> None:
    payload = json.dumps(brain)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO scans (root, signature, brain, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(root) DO UPDATE SET signature = excluded.signature, brain = excluded.brain, updated_at = excluded.updated_at
            """,
            (str(root), signature, payload, now),
        )


def load_llm(cache_key: str) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT text FROM llm WHERE cache_key = ?", (cache_key,)).fetchone()
    return row[0] if row else None


def save_llm(cache_key: str, text: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO llm (cache_key, text) VALUES (?, ?) ON CONFLICT(cache_key) DO UPDATE SET text = excluded.text",
            (cache_key, text),
        )
