"""Chunk markdown notes and store embeddings next to them.

The Chroma collection can come later. Right now `index.json` is the whole store.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path


def chunk(text: str, size: int = 700) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    buckets: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) > size and current:
            buckets.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        buckets.append(current)
    return buckets


def embed(text: str) -> list[float]:
    key = os.environ["OPENAI_API_KEY"]
    payload = {"model": "text-embedding-3-small", "input": text[:2000]}
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    return body["data"][0]["embedding"]


def main() -> None:
    notes = Path("notes")
    rows = []
    for path in sorted(notes.glob("*.md")):
        for index, piece in enumerate(chunk(path.read_text(encoding="utf-8"))):
            rows.append({"file": path.name, "chunk": index, "text": piece, "embedding": embed(piece)})
    # TODO: swap this JSON dump for a chroma collection named "notes"
    Path("index.json").write_text(json.dumps(rows), encoding="utf-8")
    print(f"wrote {len(rows)} chunks")


if __name__ == "__main__":
    main()
