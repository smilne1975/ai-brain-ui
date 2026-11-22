"""Conservative grouping of citations; a source group does not certify independence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

def text_key(text: str) -> str | None:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode()).hexdigest() if len(normalized) >= 80 else None


def canonical_url(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 2048 or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        p = urlsplit(value)
        if p.scheme not in {"http", "https"} or not p.hostname or p.username is not None or p.password is not None:
            return None
        query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True, max_num_fields=100)
                           if not k.casefold().startswith("utm_") and k.casefold() not in {"fbclid", "gclid"}])
        return urlunsplit((p.scheme, p.netloc.casefold(), p.path or "/", query, ""))
    except ValueError:
        return None


def confirmed_origins(root: Path) -> dict[str, str]:
    from backend.app.scanner import _blocked_file

    path = root.resolve() / ".brain" / "evidence-origins.json"
    try:
        if path.resolve() != path or _blocked_file(path) or path.stat().st_size > 64_000:
            return {}
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            return {}
        return {source: origin for input_url, original_url in list(doc.items())[:500]
                if (source := canonical_url(input_url)) and (origin := canonical_url(original_url)) and source != origin}
    except (OSError, RuntimeError, ValueError):
        return {}


def group(ranked: list[dict], origins: dict[str, str] | None = None, limit: int = 6) -> list[dict]:
    """Keep the best match per confirmed origin and expose alternatives explicitly."""
    if not ranked:
        return []
    roots = list(range(len(ranked)))
    reasons = [set() for _ in ranked]

    def find(i: int) -> int:
        while roots[i] != i:
            roots[i] = roots[roots[i]]
            i = roots[i]
        return i

    def union(a: int, b: int, basis: str) -> None:
        a, b = find(a), find(b)
        best, other = min(a, b), max(a, b)
        roots[other] = best
        reasons[best].update(reasons[other] | {basis})

    urls: dict[str, int] = {}
    hashes: dict[str, int] = {}
    for i, item in enumerate(ranked):
        if url := canonical_url(item.get("source_url")):
            if url in urls:
                union(i, urls[url], "same URL")
            else:
                urls[url] = i
        if fingerprint := item.get("_evidence_hash"):
            if fingerprint in hashes:
                union(i, hashes[fingerprint], "identical captured text")
            else:
                hashes[fingerprint] = i

    lineage: dict[int, str] = {}
    for url, i in urls.items():
        end, visited = url, set()
        while end in (origins or {}) and end not in visited:
            visited.add(end)
            end = origins[end]
        # A cycle, or an origin unavailable in the scoped hits, never promotes a URL.
        if end != url and end not in visited and end in urls:
            union(i, urls[end], "user-confirmed origin")
            lineage[i] = end

    grouped: dict[int, list[dict]] = {}
    for i, item in enumerate(ranked):
        grouped.setdefault(find(i), []).append({k: v for k, v in item.items() if not k.startswith("_")})
    original_by_group: dict[int, set[str]] = {}
    for i, url in lineage.items():
        original_by_group.setdefault(find(i), set()).add(url)
    output = []
    for i, items in list(grouped.items())[:limit]:
        lead = dict(items[0])
        if len(items) > 1:
            lead.update(evidence_basis=sorted(reasons[i]), repeated_count=len(items) - 1, repeated_sources=items[1:6])
            urls_in_family = original_by_group.get(i, set())
            if len(urls_in_family) == 1:
                lead["confirmed_origin"] = next(iter(urls_in_family))
        output.append(lead)
    return output
