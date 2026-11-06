# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Signed fake set execution using only generated local files and isolated databases."""

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import func, select

from datakeel.actions.parameters import PipelineParams
from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.core.models import LineageEvent
from datakeel.core.vector_models import FrozenVectorNode, VectorError
from datakeel.dataset_store.rows import EventRow
from datakeel.evidence.vector_payload import PreparedWire
from datakeel.evidence.vector_transport import FakeReply, FakeVectorTransport
from datakeel.pipeline.models import Node, Pipeline
from datakeel.storage.database import Database
from datakeel.storage.evidence_decisions import decide_assertions
from datakeel.storage.evidence_projection import projection_hash, rebuild_evidence
from datakeel.storage.evidence_store import list_assertions, validated_bundle
from datakeel.storage.vector_rows import VectorCacheRow
from tests.evidence.vector_helpers import vector_dataset, vector_prepare, vector_run


def set_pipeline(operator: str, params: dict[str, object] | None = None) -> Pipeline:
    """Compose an ordinary explicit embedding/set DAG with generated parameters."""
    return Pipeline(
        nodes=[
            Node(id="embed", operator="evidence.vector_embed", inputs={"files": "$input.files"}),
            Node(id="set", operator=operator, inputs={"files": "embed.files"}, params=params or {}),
        ],
        outputs=["set.files"],
        max_workers=1,
    )


@pytest.mark.parametrize("operator", ["evidence.semantic_cluster", "evidence.semantic_outlier"])
def test_sets_cold_hot_rebuild_reference_only(
    db: Database, tmp_path: Path, operator: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Density products use signed fake execution and offline rebuild."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    pipeline = set_pipeline(operator, {"eps": 0.0, "min_samples": 2})
    cold = vector_run(db, dataset, pipeline)
    assert cold.state == "COMPLETED", cold.error
    hot = vector_run(db, dataset, pipeline)
    assert hot.state == "COMPLETED", hot.error
    assert hot.vector
    assert hot.vector.attempts == ()
    before = projection_hash(db)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("rebuild constructed transport")

    monkeypatch.setattr(
        "datakeel.evidence.vector_transport.FakeVectorTransport.__init__", forbidden
    )
    assert rebuild_evidence(db).after_hash == before
    if operator.endswith("outlier"):
        assert len(list_assertions(db)) == 3
    else:
        assert list_assertions(db) == []


def test_gap_freezes_full_reference_union_hot_and_all_sources(db: Database, tmp_path: Path) -> None:
    """A display limit of one cannot truncate R or its authorization/review closure."""
    target = vector_dataset(db, tmp_path / "target", (b"target-one", b"target-two"))
    reference = vector_dataset(
        db, tmp_path / "reference", (b"reference-one", b"reference-two", b"reference-three")
    )
    pipeline = set_pipeline(
        "evidence.coverage_gap",
        {"reference": {"dataset_id": reference, "limit": 1}, "threshold": 1.0},
    )
    plan = vector_prepare(db, target, pipeline)
    prepared = PipelineParams.model_validate(plan.canonical_params).vector_prepared
    assert prepared
    assert prepared.selections[0].scope
    assert len(prepared.selections[0].scope.references) == 3
    assert len(prepared.nodes[0].inputs) == 5
    cold = vector_run(db, target, pipeline)
    assert cold.state == "COMPLETED", cold.error
    assert cold.vector
    assert len(cold.vector.attempts) == 5
    assert cold.vector.nodes[-1].counts.input == 2
    facts = list_assertions(db)
    assert len(facts) == 2
    assert all(f.status == "candidate" for f in facts)
    assert all(len(f.anchors) == 2 for f in facts)
    hot = vector_run(db, target, pipeline)
    assert hot.state == "COMPLETED", hot.error
    assert hot.vector
    assert hot.vector.attempts == ()
    before = projection_hash(db)
    assert rebuild_evidence(db).after_hash == before
    decide_assertions(
        db,
        AssertionDecisionRequest(
            assertion_ids=(list_assertions(db)[0].id,),
            status="accepted",
            actor="reviewer",
            idempotency_key="review-gap",
        ),
    )
    reviewed = projection_hash(db)
    assert reviewed != before
    assert rebuild_evidence(db).after_hash == reviewed
    with db.session() as session:
        event = next(
            LineageEvent.model_validate(r.payload)
            for r in session.scalars(select(EventRow))
            if r.payload.get("operator") == "evidence.coverage_gap"
        )
    assert len(validated_bundle(event).vector_scope.references) == 3


@pytest.mark.parametrize("contents", [(), (b"\xff", b"ref")])
def test_gap_invalid_reference_discards_new_pending_keeps_audit(
    db: Database, tmp_path: Path, contents: tuple[bytes, ...]
) -> None:
    """Late reference failure discards embeddings and candidates, retaining settled attempts."""
    target = vector_dataset(db, tmp_path / "target")
    # An empty R is expressed by a filter over an existing generated dataset.
    reference = vector_dataset(db, tmp_path / "reference", contents or (b"ref",))
    query: dict[str, object] = {"dataset_id": reference}
    if not contents:
        query["filters"] = [{"field": "id", "value": "does-not-exist"}]
    task = vector_run(db, target, set_pipeline("evidence.coverage_gap", {"reference": query}))
    assert task.state == "FAILED", task.error
    assert task.vector
    assert task.vector.reason in {
        "vector_reference_empty",
        "vector_reference_failed",
    }
    assert task.vector.attempts
    assert list_assertions(db) == []
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(VectorCacheRow)) == 0


def test_gap_comparison_capacity_checked_before_approval(db: Database, tmp_path: Path) -> None:
    """Whole T-minus-R by R comparisons are checked without top-k reduction."""
    target = vector_dataset(db, tmp_path / "target")
    reference = vector_dataset(db, tmp_path / "reference", (b"r1", b"r2"))
    with pytest.raises(VectorError, match="capacity"):
        vector_prepare(
            db,
            target,
            set_pipeline(
                "evidence.coverage_gap",
                {"reference": {"dataset_id": reference}, "max_reference_comparisons": 5},
            ),
        )


def test_outlier_insufficient_preserves_typed_task_reason(db: Database, tmp_path: Path) -> None:
    """A completed small population is insufficient evidence, never a corruption or noise claim."""
    dataset = vector_dataset(db, tmp_path / "inputs", (b"one",))
    task = vector_run(db, dataset, set_pipeline("evidence.semantic_outlier"))
    assert task.state == "COMPLETED"
    assert task.vector
    assert task.vector.status == "insufficient"
    assert task.vector.reason == "vector_insufficient_samples"
    assert task.vector.nodes[-1].status == "insufficient"
    assert list_assertions(db) == []


def test_outlier_temporary_target_partial_then_recovery_then_hot(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Temporary target failures publish other candidates and are retried only by a new approval."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    pipeline = set_pipeline("evidence.semantic_outlier", {"eps": 0.0, "min_samples": 2})
    original = FakeVectorTransport._respond  # noqa: SLF001  # Inject a synthetic provider fault.
    active = True

    def respond(self: FakeVectorTransport, node: FrozenVectorNode, wire: PreparedWire) -> FakeReply:
        return (
            FakeReply(status=503, body=b"")
            if active and wire.frozen.content_revision == hashlib.sha256(b"two").hexdigest()
            else original(self, node, wire)
        )

    monkeypatch.setattr(FakeVectorTransport, "_respond", respond)
    cold = vector_run(db, dataset, pipeline)
    assert cold.state == "COMPLETED", cold.error
    assert cold.partial
    assert cold.vector
    assert cold.vector.nodes[-1].counts.failed == 1
    assert len(list_assertions(db)) == 2
    active = False
    recovered = vector_run(db, dataset, pipeline)
    assert recovered.state == "COMPLETED", recovered.error
    assert recovered.vector
    assert len(recovered.vector.attempts) == 1
    assert len(list_assertions(db)) == 3
    hot = vector_run(db, dataset, pipeline)
    assert hot.vector
    assert hot.vector.attempts == ()
    assert hot.vector.nodes[-1].counts.failed == 0
