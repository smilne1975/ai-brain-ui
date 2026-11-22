from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app import project_records as records, scanner
from backend.app.mcp_tools import run_tool, tool_specs


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.delenv("BRAIN_PRIVATE_FOLDERS", raising=False)
    for name in ("levels", "sheets"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text(f"Approved BIM {name} procedure", encoding="utf-8")
    scanned = scanner.build_brain(tmp_path)
    return tmp_path, scanned, scanned["projects"][0], scanned["projects"][1]


def test_facts_preserve_corrections_and_changed_evidence(corpus):
    root, brain, project, other = corpus
    payload = {"kind": "fact", "title": "Export profile", "text": "Use export profile A", "state": "confirmed",
               "source_ids": ["levels:README.md"]}
    with pytest.raises(ValueError, match="supporting evidence"):
        records.save(root, brain, project, {**payload, "source_ids": []})
    with pytest.raises(ValueError, match="Quote not found"):
        records.save(root, brain, project, {**payload, "text": '> "Nonexistent wording" - README.md'})
    fact = records.save(root, brain, project, payload)
    edited = records.save(root, brain, project, {**payload, "text": "Recheck which profile is approved", "state": "unknown"}, fact["id"], 1)
    assert edited["revision"] == 2
    with pytest.raises(ValueError, match="record changed"):
        records.save(root, brain, project, payload, fact["id"], 1)
    assert records.board(root, brain, other)["items"] == []
    (root / "levels" / "README.md").write_text("BIM procedure changed", encoding="utf-8")
    board = records.board(root, brain, project)
    assert board["items"][0]["stale_sources"] == ["levels:README.md"]
    assert [row["text"] for row in board["history"]] == [edited["text"], fact["text"]]


def test_handoff_claims_are_atomic_and_ownership_is_enforced(corpus):
    root, brain, project, _ = corpus
    decision = records.save(root, brain, project, {"kind": "decision", "title": "Export setup", "text": "Use local setup",
                                                    "source_ids": ["levels:README.md"]})
    task = records.save(root, brain, project, {"kind": "handoff", "title": "Check export", "text": "No attempt completed",
        "next_step": "Open the checked IFC profile", "memory_ids": [decision["id"]]})
    assert task["memory"][0]["revision"] == 1 and task["state"] == "pending"

    def claim(actor):
        try:
            return records.transition(root, project, task["id"], "claim", actor, 1)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        winners = [row for row in pool.map(claim, ["Reviewer A", "Reviewer B"]) if row]
    assert len(winners) == 1 and winners[0]["state"] == "claimed"
    with pytest.raises(ValueError, match="only its claimant"):
        records.transition(root, project, task["id"], "complete", "Different reviewer", 2)
    done = records.transition(root, project, task["id"], "complete", winners[0]["owner"], 2)
    assert done["state"] == "completed" and done["revision"] == 3


def test_opt_in_recall_scope_budget_and_receipts(corpus, monkeypatch):
    root, brain, project, other = corpus
    monkeypatch.delenv("BRAIN_ENABLE_PROJECT_RECALL", raising=False)
    assert not any(row["name"] == "get_project_context" for row in tool_specs())
    monkeypatch.setenv("BRAIN_ENABLE_PROJECT_RECALL", "1")
    monkeypatch.setenv("BRAIN_RECALL_RECEIPTS", "1")
    first = records.save(root, brain, project, {"kind": "decision", "title": "Level procedure", "text": "BIM source-backed decision",
                                                "source_ids": ["levels:README.md"]})
    other_item = records.save(root, brain, other, {"kind": "gotcha", "title": "Private to sheets content", "text": "Independent record",
                                                    "source_ids": ["sheets:README.md"]})
    index = {"root": root, "brain": brain, "source": "memory", "scanning": False}
    reply = run_tool("get_project_context", {"project": "levels", "layer": "index", "budget": 400, "session": "testing"}, index)
    payload = json.loads(reply["text"])
    assert "text" not in payload["items"][0] and payload["items"][0]["id"] == first["id"]
    receipt = records.receipts(root, project)[0]
    assert receipt["session"] == "testing" and "not confirmed" in receipt["delivery"]
    result = run_tool("get_project_context", {"project": "levels", "layer": "detail", "budget": 500,
        "record_ids": [first["id"], other_item["id"]]}, index)
    body = json.loads(result["text"])
    assert body["omitted"]["unavailable"] == 1 and "Private to sheets content" not in result["text"]
    assert body["estimated_tokens"] <= 500
    (root / "levels" / "README.md").write_text("Evidence replaced", encoding="utf-8")
    body = json.loads(run_tool("get_project_context", {"project": "levels", "layer": "index"}, index)["text"])
    assert body["items"] == [] and body["omitted"]["stale_or_local_only"] == 1
