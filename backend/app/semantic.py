"""Optional hybrid search using an explicitly installed, local embedding model."""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from threading import Lock

from backend.app.privacy import active as private_folders_active

_LOCK = Lock()
_MODEL = None
_MODEL_PATH: str | None = None
_INDEX_KEY: str | None = None
_VECTORS = None
_DOC_CAP = 128


def _load(path: Path):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(str(path), device="cpu", local_files_only=True, trust_remote_code=False,
                               model_kwargs={"use_safetensors": True}, truncate_dim=None)


def rank(question: str, records: list[dict]) -> tuple[dict[str, float], str | None]:
    global _MODEL, _MODEL_PATH, _INDEX_KEY, _VECTORS
    val = os.getenv("BRAIN_SEMANTIC_MODEL", "").strip()
    if private_folders_active() or not val:
        return {}, None
    path = Path(val).expanduser()
    if not path.is_absolute() or path.drive.startswith("\\\\") or not path.is_dir() or path.resolve() != path:
        return {}, "Local hybrid search unavailable: choose an absolute local model directory"
    candidates = [rec for rec in records if not rec.get("env_class") and rec.get("kind") not in {"binary", "pdf"}
                  and (rec.get("excerpt") or "").strip()]
    if not candidates:
        return {}, None
    # Round-robin across selected projects so a large folder cannot crowd out every smaller folder.
    groups: dict[str, list[dict]] = {}
    for rec in candidates:
        groups.setdefault(rec["project_id"], []).append(rec)
    selected = []
    for offset in range(_DOC_CAP):
        for group in groups.values():
            if offset < len(group):
                selected.append(group[offset])
            if len(selected) >= _DOC_CAP:
                break
        if len(selected) >= _DOC_CAP or offset + 1 >= max(map(len, groups.values())):
            break
    text = [f"{rec['rel']}\n{rec['excerpt']}"[:1000] for rec in selected]
    digest = hashlib.sha256("\0".join(text).encode()).hexdigest()
    try:
        with _LOCK:
            if _MODEL is None or _MODEL_PATH != str(path):
                model = _load(path)
                model.max_seq_length = min(256, model.max_seq_length)
                _MODEL, _MODEL_PATH, _INDEX_KEY, _VECTORS = model, str(path), None, None
            options = {"normalize_embeddings": True, "show_progress_bar": False, "batch_size": 16}
            if _INDEX_KEY != digest:
                _VECTORS = _MODEL.encode(text, **options)
                _INDEX_KEY = digest
            needle = _MODEL.encode([question[:800]], **options)[0]
            similarities = [sum(float(a) * float(b) for a, b in zip(needle, vector)) for vector in _VECTORS]
    except Exception:
        return {}, "Local hybrid search unavailable; using keyword search only"
    results = {rec["id"]: score for rec, score in zip(selected, similarities) if math.isfinite(score) and score >= 0.42}
    return results, (f"Local hybrid ranking used the first {_DOC_CAP} of {len(candidates)} eligible files" if len(selected) < len(candidates) else None)
