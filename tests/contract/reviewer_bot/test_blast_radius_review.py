import json
from pathlib import Path


def _load_review() -> dict:
    return json.loads(
        Path("tests/fixtures/equivalence/blast_radius/review.json").read_text(encoding="utf-8")
    )


def test_final_blast_radius_review_uses_semantic_row_schema():
    review = _load_review()

    assert set(review) == {
        "harness_id",
        "locality_budgets",
        "representative_changes",
        "hotspot_budgets",
    }
    assert review["harness_id"] == "F3 blast radius review"
    assert set(review["locality_budgets"]) == {
        "ordinary policy change",
        "support or execution change",
        "runtime or protocol change",
        "orchestration or transaction change",
    }


def test_final_blast_radius_review_covers_full_canonical_row_universe():
    review = _load_review()

    assert [row["id"] for row in review["representative_changes"]] == [
        f"RC{number}" for number in range(1, 24)
    ]
    assert [row["id"] for row in review["hotspot_budgets"]] == [
        f"HB{number}" for number in range(1, 10)
    ]


def test_final_blast_radius_review_rows_keep_semantic_fields_only():
    review = _load_review()

    representative_keys = {
        "id",
        "change",
        "change_class",
        "semantic_owner",
        "allowed_production_categories",
        "allowed_proof_families",
        "hotspot_ids",
        "supporting_evidence_files",
        "source_predicates",
    }
    hotspot_keys = {
        "id",
        "dominant_owner",
        "allowed_cross_boundary_callers",
        "allowed_reasons_to_change",
        "source_predicates",
    }

    assert all(set(row) == representative_keys for row in review["representative_changes"])
    assert all(set(row) == hotspot_keys for row in review["hotspot_budgets"])
    assert all(row["source_predicates"] for row in review["representative_changes"])
    assert all(row["source_predicates"] for row in review["hotspot_budgets"])


def test_final_blast_radius_review_no_longer_freezes_exact_file_inventories():
    fixture_text = Path("tests/fixtures/equivalence/blast_radius/review.json").read_text(encoding="utf-8")

    assert "expected_files" not in fixture_text
    assert "semantic_inventory_entries" not in fixture_text
