"""Retrieve a note chunk for a question. Brute-force cosine, on purpose."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from indexer import embed


def retrieve(question: str, limit: int = 3) -> list[dict]:
    rows = json.loads(Path("index.json").read_text(encoding="utf-8"))
    query = embed(question)

    def score(row: dict) -> float:
        vec = row["embedding"]
        dot = sum(a * b for a, b in zip(query, vec))
        na = math.sqrt(sum(a * a for a in query)) or 1
        nb = math.sqrt(sum(b * b for b in vec)) or 1
        return dot / (na * nb)

    return sorted(rows, key=score, reverse=True)[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="Search meeting notes")
    parser.add_argument("question")
    args = parser.parse_args()
    for hit in retrieve(args.question):
        print(f"{hit['file']} #{hit['chunk']}")
        print(hit["text"][:400])
        print("---")


if __name__ == "__main__":
    main()
