# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cross-version peer filters use full provenance rather than the currently visible page."""

from datakeel.core.evidence_models import Assertion, EvidenceAnchor, ExtractorRef
from datakeel.core.models import AssetRef
from datakeel.ontology.models import AssertionFilter, FrozenObject, ObjectSet
from datakeel.storage.evidence_filters import matching_assertion, select_evidence
from datakeel.storage.evidence_snapshot import EvidenceObservations, EvidenceSnapshot, identity


def test_near_filter_when_peer_outside_selected_version_uses_full_split_index() -> None:
    """Verify incoming canonical pairs remain usable outside a view's version scope."""
    train = AssetRef(asset_type="file", asset_id="a-train", version="train-version")
    val = AssetRef(asset_type="file", asset_id="z-val", version="val-version")
    pair = Assertion(
        subject=train,
        predicate="near_duplicate_of",
        object=val,
        distance=6,
        anchors=(
            EvidenceAnchor(asset_ref=train, content_revision="a" * 64),
            EvidenceAnchor(asset_ref=val, content_revision="b" * 64),
        ),
        extractor=ExtractorRef(id="evidence.near_duplicate", version="1.0"),
        run_id="run",
        producer_event_id="event",
    )
    snapshot = EvidenceSnapshot(
        subjects={identity(val): EvidenceObservations(assertions=(pair,))},
        splits={identity(train): "train"},
    )
    value = FrozenObject(
        asset_ref=val, revision="revision", properties={"metadata": {"split": "val"}}
    )
    query = ObjectSet(version_ids=["val-version"], split="val", has_near_duplicate_in="train")
    assert select_evidence([value], query, snapshot) == [value]
    assert matching_assertion(pair, AssertionFilter(predicate="near_duplicate_of"))
