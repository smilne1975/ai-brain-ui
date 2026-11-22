"""Offline Ask retrieval evaluation over a fixed, synthetic corpus."""

from __future__ import annotations

import argparse
import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app import ask, scanner

SUITE = "ask-fixtures-1"
CASES = (
    ("exact IFC version", "IFC4.3", "exchange", "exchange:current.md", "Current exchange profile is IFC4.3.", "indexed"),
    ("exact key-in", "LEVELS_EXPORT", "tooling", "tooling:current.md", "Run LEVELS_EXPORT to generate the level inventory.", "indexed"),
    ("paraphrase", "allowable dimensional variation", "tooling", "tooling:tolerances.md", "Fabrication tolerances are documented here.", "indexed"),
    ("changed passage", "calibration approval", "tooling", "tooling:calibration.md", "Calibration approval now requires two reviewers.", "indexed"),
    ("excluded input", "saltwater foghorn", "tooling", "tooling:excluded/hidden.md", "", "excluded"),
    ("not indexed", "lemon luggage", "tooling", "tooling:unsupported.zip", "", "not indexed"),
    ("no evidence", "volcanic weather satellite", "tooling", None, "", "abstain"),
)
FILES = {
    "exchange/current.md": "Current exchange profile is IFC4.3.\n",
    "exchange/older.md": "Older exchange profile was IFC4.2.\n",
    "tooling/current.md": "Run LEVELS_EXPORT to generate the level inventory.\n",
    "tooling/tolerances.md": "Fabrication tolerances are documented here.\n",
    "tooling/calibration.md": "Calibration approval now requires two reviewers.\n",
    "tooling/prior.md": "An archived proposal says calibration approval needed one reviewer.\n",
    "tooling/excluded/hidden.md": "Sample only: saltwater foghorn.\n",
    "tooling/unsupported.zip": "Synthetic format-exclusion fixture: lemon luggage.\n",
}


def _write_corpus(root: Path):
    for relative, content in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@contextmanager
def _fixture_privacy():
    # This is a standalone CLI evaluated in its own process, never an app endpoint.
    key = "BRAIN_PRIVATE_FOLDERS"
    prior = os.environ.get(key)
    try:
        os.environ[key] = '["tooling/excluded"]'
        yield
    finally:
        if prior is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prior


def _cases(brain: dict, keyword_only: bool, eligible: tuple = CASES) -> list[dict]:
    indexed = {record["id"] for record in brain["files"]}
    rows = []
    for name, question, project, target, expected, condition in eligible:
        found = ask.answer(brain, question, project, None, keyword_only=keyword_only)
        hits = found.get("evidence", [])
        rank = next((position for position, item in enumerate(hits, 1)
                     if item["id"] == target and expected and expected in item.get("excerpt", "")), None)
        row = {"case": name, "status": condition, "rank": rank, "passed": False}
        if condition == "excluded":
            row["passed"] = target not in indexed and not hits
            # Never include paths, questions or snippet text in the excluded row.
        elif condition == "not indexed":
            row["passed"] = target not in indexed and not hits
        elif condition == "abstain":
            row["passed"] = not hits
        else:
            row["status"] = "retrieved" if rank else "indexed but missed" if target in indexed else "not indexed"
            row["passed"] = rank is not None
            row["expected"] = {"citation": target, "passage": expected}
        rows.append(row)
    return rows


def run(hybrid: bool = False) -> dict:
    with TemporaryDirectory(prefix="ai-brain-scorecard-") as temp:
        root = Path(temp)
        _write_corpus(root)
        with _fixture_privacy():
            keyword = _cases(scanner.build_brain(root), True)
        report = {"suite": SUITE, "keyword": keyword, "hybrid": None}
        if not hybrid:
            return report
        if not os.environ.get("BRAIN_SEMANTIC_MODEL", "").strip():
            report["hybrid_note"] = "Not run: configure a local embedding model with BRAIN_SEMANTIC_MODEL."
            return report
        # The real app disables embeddings when exclusions are enabled. Verify that path in the
        # keyword run above, then benchmark hybrid on the exact same public index without the fixture.
        (root / "tooling/excluded/hidden.md").unlink()
        prior = os.environ.pop("BRAIN_PRIVATE_FOLDERS", None)
        try:
            brain = scanner.build_brain(root)
            _, warning = ask.semantic.rank(CASES[0][1], brain["files"])
            if warning and "unavailable" in warning:
                report["hybrid_note"] = "Not run: local model unavailable; no hybrid results were measured."
                return report
            report["hybrid"] = _cases(brain, False, tuple(case for case in CASES if case[-1] != "excluded"))
            report["hybrid_note"] = "Excluded input is checked in keyword mode only, as the app disables hybrid under exclusions."
        finally:
            if prior is not None:
                os.environ["BRAIN_PRIVATE_FOLDERS"] = prior
        return report


def compare(previous: list[dict], current: list[dict]) -> list[dict]:
    by_case = {row["case"]: row for row in previous}
    changes = []
    for row in current:
        old = by_case.get(row["case"])
        if old is None or all(old.get(key) == row.get(key) for key in ("rank", "passed", "status")):
            continue
        if old["passed"] != row["passed"]:
            direction = "improved" if row["passed"] else "regressed"
        elif old["rank"] is not None and row["rank"] is not None:
            direction = "improved" if row["rank"] < old["rank"] else "regressed"
        else:
            direction = "coverage changed"
        changes.append({"case": row["case"], "change": direction, "before": old["rank"], "after": row["rank"],
                        "before_status": old["status"], "after_status": row["status"],
                        **({"citation": row["expected"]["citation"]} if row.get("expected") else {})})
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hybrid", action="store_true", help="compare an already installed local model")
    parser.add_argument("--against", type=Path, help="compare to a prior JSON scorecard from the same suite")
    options = parser.parse_args()
    report = run(options.hybrid)
    if report["hybrid"] is not None:
        report["keyword_to_hybrid"] = compare(report["keyword"], report["hybrid"])
    if options.against:
        try:
            previous = json.loads(options.against.read_text(encoding="utf-8-sig"))
            if previous.get("suite") != SUITE:
                parser.error("comparison needs a scorecard from the same fixture suite")
            report["against"] = {mode: compare(previous[mode], report[mode]) for mode in ("keyword", "hybrid")
                                 if previous.get(mode) is not None and report.get(mode) is not None}
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            parser.error(f"could not read comparison scorecard: {exc}")
    print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
