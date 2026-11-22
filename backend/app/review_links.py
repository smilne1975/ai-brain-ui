"""Conservative, local suggestions for project Markdown, never vault edits."""

import hashlib
import re
from collections import defaultdict
from itertools import combinations

from backend.app import project_records

WORDS = re.compile(r"\b[a-z][a-z0-9-]{5,}\b", re.I)
COMMON = set("before between change check different example follow important information instead local markdown notes project related review should source update version where which within without".split())
WIKI = re.compile(r"\[\[([^]|#]+)(?:[^]]*)\]\]")
MARKDOWN = re.compile(r"\]\(<?([^\s)>]+)")


def candidates(brain, project):
    pid = project["id"]
    notes = sorted((row for row in brain["files"] if row["project_id"] == pid and not row.get("env_class")
                    and row["rel"].lower().endswith((".md", ".markdown")) and row.get("excerpt")), key=lambda row: row["rel"])
    rows = notes[:250]
    by_id = {row["id"]: row for row in rows}
    graph = brain.get("architecture", {}).get("projects", {}).get(pid, {})
    nodes = {node["id"]: node.get("file_id") for node in graph.get("nodes", [])}
    linked = {frozenset((nodes.get(edge["source"]), nodes.get(edge["target"]))) for edge in graph.get("edges", [])}
    targets = {row["id"]: {value.casefold().replace("\\", "/").split("#", 1)[0].removesuffix(".md")
                          for value in WIKI.findall(row["excerpt"]) + MARKDOWN.findall(row["excerpt"])} for row in rows}
    terms = defaultdict(dict)
    for row in rows:
        for line in row["excerpt"].splitlines():
            line = line.strip()[:360]
            if not line or line.startswith(("#", "```")):
                continue
            for term in set(WORDS.findall(line.casefold())) - COMMON:
                terms[term].setdefault(row["id"], line)
    pairs = defaultdict(list)
    for term, matches in sorted(terms.items()):
        if 2 <= len(matches) <= 6:
            for left, right in combinations(sorted(matches), 2):
                pairs[left, right].append((term, matches[left], matches[right]))
    ranked = []
    for (left, right), evidence in pairs.items():
        if frozenset((left, right)) in linked:
            continue
        a, b = by_id[left], by_id[right]
        if any(any(value == path or value.endswith('/' + path) for value in targets[src["id"]])
               for src, dst in ((a, b), (b, a)) for path in
               (dst["rel"].casefold().removesuffix(".md"), dst["rel"].rsplit("/", 1)[-1].casefold().removesuffix(".md"))):
            continue
        groups = defaultdict(list)
        for term, first, second in evidence:
            if first.casefold() != second.casefold():
                groups[first, second].append(term)
        if not groups:
            continue
        (first, second), shared = max(groups.items(), key=lambda entry: (len(entry[1]), entry[0]))
        if len(shared) < 2:
            continue
        identifier = hashlib.sha256(f"{a['rel']}\0{b['rel']}\0{first}\0{second}".encode()).hexdigest()
        ranked.append((len(shared), {"id": identifier, "reason": "Shared terms: " + ", ".join(shared[:4]),
                                    "ends": [{"id": row["id"], "label": row["rel"], "excerpt": line}
                                             for row, line in ((a, first), (b, second))]}))
    return [item for _, item in sorted(ranked, key=lambda row: (-row[0], row[1]["id"]))], len(rows) < len(notes)


def listing(root, brain, project):
    rows, capped = candidates(brain, project)
    with project_records._db(root) as db:
        states = dict(db.execute("SELECT id, state FROM link_reviews WHERE project=?", (project["rel"],))) if (
            db is not None and db.execute("SELECT 1 FROM sqlite_master WHERE name='link_reviews'").fetchone()) else {}
    pending = [{**row, "state": "suggested"} for row in rows if row["id"] not in states]
    kept = [{**row, "state": "kept"} for row in rows if states.get(row["id"]) == "kept"]
    return {"suggested": pending[:25], "kept": kept, "limited": capped or len(pending) > 25,
            "unavailable_kept": sum(value == "kept" for value in states.values()) - len(kept)}


def review(root, brain, project, identifier, state):
    current, _ = candidates(brain, project)
    if identifier not in {row["id"] for row in current}:
        raise ValueError("The source passages changed or are unavailable. Run the check again.")
    with project_records._db(root, True) as db:
        db.execute("INSERT OR REPLACE INTO link_reviews VALUES (?,?,?)", (project["rel"], identifier, state))
    return listing(root, brain, project)
