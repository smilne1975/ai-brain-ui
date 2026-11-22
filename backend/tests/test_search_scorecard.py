import json

from backend.app import search_scorecard, semantic


def test_scorecard_distinguishes_index_misses_excluded_and_no_evidence(monkeypatch):
    monkeypatch.setenv("BRAIN_PRIVATE_FOLDERS", '["outside-the-fixture"]')
    report = search_scorecard.run()
    rows = {row["case"]: row for row in report["keyword"]}
    assert rows["exact IFC version"]["rank"] == 1
    assert rows["exact key-in"]["rank"] == 1
    assert rows["changed passage"]["rank"] is not None
    assert rows["paraphrase"]["status"] == "indexed but missed"
    assert rows["not indexed"]["status"] == "not indexed" and rows["not indexed"]["passed"]
    assert rows["excluded input"]["status"] == "excluded" and rows["excluded input"]["passed"]
    assert rows["no evidence"]["status"] == "abstain" and rows["no evidence"]["passed"]
    assert "hidden.md" not in json.dumps(report) and "foghorn" not in json.dumps(report)
    assert search_scorecard.os.environ["BRAIN_PRIVATE_FOLDERS"] == '["outside-the-fixture"]'


def test_scorecard_names_rank_regression_and_citation(monkeypatch):
    before = search_scorecard.run()["keyword"]
    real_answer = search_scorecard.ask.answer

    def demote(*args, **kwargs):
        result = real_answer(*args, **kwargs)
        if args[1] == "IFC4.3":
            result["evidence"].insert(0, {"id": "exchange:older.md", "excerpt": "Unrelated revision."})
        return result

    monkeypatch.setattr(search_scorecard.ask, "answer", demote)
    changes = search_scorecard.compare(before, search_scorecard.run()["keyword"])
    assert changes == [{"case": "exact IFC version", "change": "regressed", "before": 1, "after": 2,
                        "before_status": "retrieved", "after_status": "retrieved", "citation": "exchange:current.md"}]


def test_hybrid_scorecard_measures_local_ranking_or_reports_unavailable(tmp_path, monkeypatch):
    monkeypatch.delenv("BRAIN_SEMANTIC_MODEL", raising=False)
    assert search_scorecard.run(hybrid=True)["hybrid"] is None
    monkeypatch.setenv("BRAIN_SEMANTIC_MODEL", str(tmp_path))

    class FixtureEncoder:
        max_seq_length = 512

        def encode(self, texts, **kwargs):
            return [[1, 0] if "tolerances" in text or "variation" in text else [0, 0] for text in texts]

    monkeypatch.setattr(semantic, "_load", lambda path: FixtureEncoder())
    report = search_scorecard.run(hybrid=True)
    changes = search_scorecard.compare(report["keyword"], report["hybrid"])
    assert changes == [{"case": "paraphrase", "change": "improved", "before": None, "after": 1,
                        "before_status": "indexed but missed", "after_status": "retrieved", "citation": "tooling:tolerances.md"}]
