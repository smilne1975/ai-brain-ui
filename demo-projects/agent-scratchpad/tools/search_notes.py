"""Look through meeting-notes-rag markdown without starting that project."""

from __future__ import annotations

from pathlib import Path


def search_notes(query: str) -> list[str]:
    root = Path(__file__).resolve().parents[2] / "meeting-notes-rag" / "notes"
    if not root.exists():
        return []
    words = [w for w in query.lower().split() if len(w) > 3]
    hits = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if any(word in text.lower() for word in words):
            hits.append(f"{path.name}: {text.strip().splitlines()[0]}")
    return hits[:5]
