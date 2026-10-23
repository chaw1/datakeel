# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""ObjectSet evidence extensions preserve legacy frozen selection serialization."""

import json

import pytest

from datakeel.evidence.query_models import EvidenceQuery
from datakeel.ontology.models import AssertionFilter, FrozenManifest, ObjectSet
from datakeel.storage.object_projection import content_digest


def test_object_set_when_legacy_schema_round_trips_preserves_exact_digest() -> None:
    """Verify nested manifests serialize the pre-extension query field set unchanged."""
    original = ObjectSet(schema_version="1.0").model_dump(mode="json")
    assert set(original).isdisjoint({"assertion_filters", "split", "has_near_duplicate_in"})
    manifest = FrozenManifest(
        query=ObjectSet.model_validate(original), objects=[], state_digest="old", total_bytes=0
    )
    restored = FrozenManifest.model_validate_json(manifest.model_dump_json())
    assert restored.query.model_dump(mode="json") == original
    assert content_digest(restored.query.model_dump(mode="json")) == content_digest(original)


@pytest.mark.parametrize(
    "values",
    [
        {"split": "val"},
        {"has_near_duplicate_in": "train"},
        {"assertion_filters": [{"predicate": "mentions"}]},
    ],
)
def test_object_set_when_legacy_schema_receives_evidence_filter_rejects(
    values: dict[str, object],
) -> None:
    """Verify unsupported new predicates cannot disappear during legacy serialization."""
    with pytest.raises(ValueError, match=r"schema_version 1\.1"):
        ObjectSet.model_validate({"schema_version": "1.0", **values})


def test_object_set_when_new_schema_defaults_omitted_round_trips() -> None:
    """Verify omission of empty extension fields preserves current default behavior."""
    original = ObjectSet()
    encoded = original.model_dump_json()
    assert json.loads(encoded)["schema_version"] == "1.1"
    assert ObjectSet.model_validate_json(encoded) == original
    assert original.assertion_filters == []
    assert original.split is None


@pytest.mark.parametrize(
    "values",
    [
        {"status": ["candidate", "candidate"]},
        {"predicate": "near_duplicate_of", "value": "present"},
    ],
)
def test_assertion_filter_when_invalid_operand_rejects(values: dict[str, object]) -> None:
    """Verify review-state lists and asset relationship operands remain unambiguous."""
    with pytest.raises(ValueError, match=r"unique|asset relationships"):
        AssertionFilter.model_validate({"predicate": "mentions", **values})


def test_evidence_selection_when_non_file_object_rejects() -> None:
    """Verify evidence-specific views cannot silently return unrelated object types."""
    with pytest.raises(ValueError, match="file"):
        ObjectSet(object_type="dataset", split="val")
    with pytest.raises(ValueError, match="file"):
        EvidenceQuery(object_type="dataset")
