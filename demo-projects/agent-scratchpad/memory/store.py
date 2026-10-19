"""JSON memory. I tried sqlite3 for an afternoon and went back to a file I can diff."""

from __future__ import annotations

import json
from pathlib import Path


class Memory:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def add(self, note: str) -> None:
        rows = json.loads(self.path.read_text(encoding="utf-8"))
        rows.append(note)
        self.path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def recent(self, limit: int = 8) -> list[str]:
        rows = json.loads(self.path.read_text(encoding="utf-8"))
        return [str(item) for item in rows[-limit:]]
