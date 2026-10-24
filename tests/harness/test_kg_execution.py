# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Production graph evaluation runs real filtering, grounding, and cross-block merging."""

from pathlib import Path

import pytest
import yaml

from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation
from datakeel.core.kg_eval_models import KGCase
from datakeel.core.kg_models import ExtractionResult, RawExtraction
from datakeel.kg.extractors import FakeExtractor, ReplayExtractor
from datakeel.kg.loader import contracts_path, get_profile, get_schema
from datakeel.kg_eval.execution import execute_case
from datakeel.kg_eval.projection import raw_relations
from datakeel.kg_eval.service import evaluate_kg


def _raw() -> RawExtraction:
    return RawExtraction(
        entities=(
            ExtractedEntity(name="Alice", type="person"),
            ExtractedEntity(name="Atlas", type="system"),
        ),
        relations=(
            ExtractedRelation(
                head="Alice", relation="owns", tail="Atlas", evidence="Alice owns Atlas."
            ),
        ),
    )


def _cases(path: Path, text: str = "Alice owns Atlas.") -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "id": "external",
                "cases": [
                    {
                        "id": "test",
                        "lang": "en",
                        "text": text,
                        "entities": [
                            {"name": "Alice", "type": "person"},
                            {"name": "Atlas", "type": "system"},
                        ],
                        "relations": [{"head": "Alice", "relation": "owns", "tail": "Atlas"}],
                    }
                ],
            }
        )
    )
    return path


@pytest.mark.parametrize(
    ("profile_name", "precision", "recall", "f1", "traps", "blocked"),
    [("replay-demo", 0.92, 0.83, 0.87, 3, 9), ("replay-flash", 0.99, 0.99, 0.99, 0, 1)],
)
def test_replay_product_path_passes_thresholds_and_explains_exclusions(
    profile_name: str, precision: float, recall: float, f1: float, traps: int, blocked: int
) -> None:
    """Score actual candidate drafts after the shared product assembly and merge functions."""
    profile = get_profile(profile_name)
    assert profile.recording
    extractor = ReplayExtractor.from_path(contracts_path() / profile.recording)
    report = evaluate_kg(profile, get_schema(), extractor)
    assert report.product.all.relation_strict.p >= precision
    assert report.product.all.relation_strict.r >= recall
    assert report.product.all.relation_strict.f1 >= f1
    assert report.product.all.trap_hits == traps
    assert len(report.blocked_relations) == blocked
    assert all(
        item.reason in {"domain_range", "endpoint_ambiguous"} for item in report.blocked_relations
    )
    assert report.cost_usd == report.input_tokens == report.output_tokens == 0
    assert extractor.calls == 24


def test_external_long_case_merges_overlapping_product_candidates(tmp_path: Path) -> None:
    """Repeating a relation in separate blocks adds evidence without multiplying triples."""
    path = _cases(tmp_path / "cases.yaml", "Alice owns Atlas. Alice owns Atlas.")
    profile = get_profile("fake").model_copy(update={"chunk_size": 20, "chunk_overlap": 0})
    adapter = FakeExtractor((ExtractionResult(output=_raw()),) * 2)
    report = evaluate_kg(profile, get_schema(), adapter, path)
    assert adapter.calls == 2
    assert report.recording.all.pred_relations == 2
    assert report.product.all.pred_relations == 1
    assert report.product.all.relation_strict.f1 == 1
    assert report.product.verified.relation_strict.f1 == 1


def test_failed_blocks_retain_exact_source_offsets(tmp_path: Path) -> None:
    """Failures identify individual chunks so the saved evaluation can locate every omission."""
    text = "Alice owns Atlas. Alice owns Atlas. Alice owns Atlas."
    path = _cases(tmp_path / "cases.yaml", text)
    profile = get_profile("fake").model_copy(update={"chunk_size": 20, "chunk_overlap": 0})
    adapter = FakeExtractor(("parse_failure", "provider_error", "truncated"))
    report = evaluate_kg(profile, get_schema(), adapter, path)
    assert [(item.case_id, item.start, item.end, item.reason) for item in report.failures] == [
        ("test", 0, 18, "parse_failure"),
        ("test", 18, 36, "provider_error"),
        ("test", 36, 53, "truncated"),
    ]


def test_partial_failures_do_not_hide_successful_blocks(tmp_path: Path) -> None:
    """Persist visible failure counts while scoring the candidate from the completed block."""
    path = _cases(tmp_path / "cases.yaml", "Alice owns Atlas. Alice owns Atlas. Alice owns Atlas.")
    profile = get_profile("fake").model_copy(update={"chunk_size": 20, "chunk_overlap": 0})
    adapter = FakeExtractor(
        (
            ExtractionResult(output=_raw()),
            "parse_failure",
            ExtractionResult(output=_raw(), finish_reason="length"),
        )
    )
    report = evaluate_kg(profile, get_schema(), adapter, path)
    assert report.product.all.failed_blocks == 2
    assert report.product.all.errors == 1
    assert report.product.all.relation_strict.f1 == 1


def test_fresh_provider_path_records_usage_and_unknown_cost(tmp_path: Path) -> None:
    """Exercise the explicit real-provider evaluation branch with a scripted transport boundary."""
    path = _cases(tmp_path / "cases.yaml")
    profile = get_profile("cloud")
    adapter = FakeExtractor((ExtractionResult(output=_raw(), input_tokens=100, output_tokens=20),))
    report = evaluate_kg(profile, get_schema(), adapter, path)
    assert report.product.all.relation_strict.f1 == 1
    assert (report.input_tokens, report.output_tokens, report.cost_usd) == (100, 20, None)


def test_unknown_schema_and_ungrounded_names_stay_visible() -> None:
    """Reject invalid vocabulary but keep a hallucinated endpoint candidate for review."""
    raw = _raw().model_copy(
        update={
            "relations": (
                ExtractedRelation(
                    head="Alice", relation="invented", tail="Atlas", evidence="Alice owns Atlas."
                ),
                ExtractedRelation(
                    head="Vivo", relation="owns", tail="Atlas", evidence="Alice owns Atlas."
                ),
            ),
            "entities": (*_raw().entities, ExtractedEntity(name="Vivo", type="person")),
        }
    )
    case = KGCase(id="test", lang="en", text="Alice owns Atlas.", entities=(), relations=())
    result = execute_case(
        case, get_profile("fake"), get_schema(), FakeExtractor((ExtractionResult(output=raw),))
    )
    assert len(result.blocked) == 1
    assert result.blocked[0].reason == "unknown_relation"
    assert result.product.relations[0].verification == "needs_review"


def test_fresh_evidence_location_handles_normalization_and_missing_quote() -> None:
    """Keep the independent raw scorer coordinate mapping separate from production grounding."""
    raw = _raw()
    relation = raw_relations(raw, "ALICE  owns Atlas.")[0]
    assert (relation.ev_start, relation.ev_end) == (0, 18)
    assert raw_relations(raw, "Different text")[0].ev_start is None
    empty = raw.model_copy(
        update={"relations": (raw.relations[0].model_copy(update={"evidence": ""}),)}
    )
    assert raw_relations(empty, "Alice owns Atlas.")[0].ev_start is None


def test_external_combining_text_uses_nfc_offsets_for_fresh_and_product_scores(
    tmp_path: Path,
) -> None:
    """A combining character before evidence cannot corrupt later source span measurements."""
    path = _cases(tmp_path / "cases.yaml", "Cafe\u0301 is nearby. Alice owns Atlas.")
    report = evaluate_kg(
        get_profile("fake"), get_schema(), FakeExtractor((ExtractionResult(output=_raw()),)), path
    )
    assert report.recording.all.evidence_located == 1
    assert report.recording.verified.relation_strict.f1 == 1
    assert report.product.all.evidence_located == 1
    assert report.product.verified.relation_strict.f1 == 1
