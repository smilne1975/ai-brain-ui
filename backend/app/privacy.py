"""Startup-only, fail-closed scan exclusions for confidential project folders."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PureWindowsPath


def _key(part: str) -> str:
    return part.casefold() if os.name == "nt" else part


@dataclass(frozen=True)
class Policy:
    token: str | None = None
    prefixes: tuple[tuple[str, ...], ...] = ()
    invalid: bool = False

    def excludes(self, relative: Path) -> bool:
        parts = tuple(map(_key, relative.parts))
        return self.invalid or any(parts[:len(prefix)] == prefix for prefix in self.prefixes)


def active() -> bool:
    # Even malformed configuration disables model calls and other broad readers.
    return "BRAIN_PRIVATE_FOLDERS" in os.environ


def policy(root: Path) -> Policy:
    return _parse(root, os.environ.get("BRAIN_PRIVATE_FOLDERS"))


@lru_cache(maxsize=32)
def _parse(root: Path, raw: str | None) -> Policy:
    if raw is None:
        return Policy()
    try:
        items = json.loads(raw)
        if not isinstance(items, list) or not items or len(items) > 256:
            raise ValueError
        prefixes = set()
        for item in items:
            if not isinstance(item, str) or not item or any(ord(char) < 32 for char in item):
                raise ValueError
            path = PureWindowsPath(item)
            if path.anchor or not path.parts or any(part in {"..", "."} or part.rstrip(" .") != part or ":" in part for part in path.parts):
                raise ValueError
            parts = tuple(map(_key, path.parts))
            real = root.joinpath(*path.parts).resolve().relative_to(root)
            if not real.parts:
                raise ValueError
            prefixes.update((parts, tuple(map(_key, real.parts))))
    except (ValueError, OSError, RuntimeError):
        return Policy(token="invalid", invalid=True)
    ordered = tuple(sorted(prefixes))
    token = hashlib.sha256(json.dumps(ordered).encode()).hexdigest()
    return Policy(token=token, prefixes=ordered)
