# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate typed assertion predicates and direct-neighbor split conditions."""

from datakeel.core.evidence_models import Assertion, EvidenceValue
from datakeel.core.models import AssetRef
from datakeel.ontology.models import AssertionFilter, FrozenObject, ObjectSet
from datakeel.storage.evidence_snapshot import EvidenceSnapshot, identity


def matching_assertion(assertion: Assertion, rule: AssertionFilter) -> bool:
    """Apply predicate, concept, three-state, review, and measured-confidence constraints."""
    if assertion.predicate != rule.predicate or assertion.status not in rule.status:
        return False
    if rule.min_confidence is not None and (
        assertion.confidence is None or assertion.confidence < rule.min_confidence
    ):
        return False
    if isinstance(assertion.object, EvidenceValue):
        return (rule.concept is None or assertion.object.concept == rule.concept) and (
            rule.value is None or assertion.object.value == rule.value
        )
    return rule.concept is None and rule.value is None


def neighbor(assertion: Assertion, ref: AssetRef) -> AssetRef | None:
    """Expand one stored canonical duplicate assertion from either endpoint."""
    if assertion.predicate != "near_duplicate_of" or not isinstance(assertion.object, AssetRef):
        return None
    return assertion.object if identity(assertion.subject) == identity(ref) else assertion.subject


def object_split(value: FrozenObject) -> str | None:
    """Read the imported split property without interpreting paths or gold data."""
    metadata = value.properties.get("metadata")
    split = metadata.get("split") if isinstance(metadata, dict) else None
    return split if isinstance(split, str) else None


def select_evidence(
    objects: list[FrozenObject], query: ObjectSet, snapshot: EvidenceSnapshot
) -> list[FrozenObject]:
    """Resolve evidence filters before a controlled action freezes its exact object set."""
    splits = {
        **snapshot.splits,
        **{identity(value.asset_ref): object_split(value) for value in objects},
    }
    result: list[FrozenObject] = []
    for value in objects:
        if query.split is not None and object_split(value) != query.split:
            continue
        observations = snapshot.observations(value.asset_ref).assertions
        if any(
            any(matching_assertion(item, rule) for item in observations)
            != (rule.operator == "exists")
            for rule in query.assertion_filters
        ):
            continue
        if query.has_near_duplicate_in is not None and not any(
            item.status in {"candidate", "accepted"}
            and (other := neighbor(item, value.asset_ref)) is not None
            and splits.get(identity(other)) == query.has_near_duplicate_in
            for item in observations
        ):
            continue
        result.append(value)
    return result
