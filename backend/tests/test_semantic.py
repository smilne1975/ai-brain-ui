from backend.app import ask, scanner, semantic


def test_hybrid_benchmark_recalls_a_paraphrase_and_preserves_exact_bim_versions(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    for folder, text in (("schedule", "Fabrication tolerances are documented here."),
                         ("correct", "Handover model requirements for IFC4.3."),
                         ("older", "Handover model requirements for IFC4.2.")):
        (root / folder).mkdir(parents=True)
        (root / folder / "README.md").write_text(text, encoding="utf-8")
    brain = scanner.build_brain(root)
    monkeypatch.delenv("BRAIN_SEMANTIC_MODEL", raising=False)
    assert not ask.answer(brain, "allowable dimensional variation", None, None)["evidence"]
    model = tmp_path / "model"
    model.mkdir()
    monkeypatch.setenv("BRAIN_SEMANTIC_MODEL", str(model))

    class FixtureEncoder:
        max_seq_length = 512
        def encode(self, texts, **kwargs):
            return [[1, 0, 0] if "tolerances" in text or "variation" in text else
                    [0, 1, 0] if "4.2" in text or text == "IFC4.3" else [0, 0, 1] for text in texts]

    monkeypatch.setattr(semantic, "_load", lambda path: FixtureEncoder())
    natural = ask.answer(brain, "allowable dimensional variation", None, None)
    assert natural["evidence"][0]["project_id"] == "schedule" and natural["evidence"][0]["semantic"]
    ifc = ask.answer(brain, "IFC4.3", None, None)
    assert [hit["project_id"] for hit in ifc["evidence"]] == ["correct"]
    assert not ask.answer(brain, "allowable dimensional variation", "older", None)["evidence"]
