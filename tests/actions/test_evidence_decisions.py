# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Controlled status-only reviews freeze exact endpoints and retain reversible audit history."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.actions.models import ActionContext, ActionPlan, ExecuteRequest
from datakeel.actions.parameters import DecideAssertionsParams
from datakeel.actions.receipts import receipt
from datakeel.actions.registry import action_definition
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import (
    AuthorizationError,
    ConflictError,
    ExecutionError,
    NotFoundError,
    ValidationError,
)
from datakeel.core.evidence_cache import (
    EvidenceCacheEntry,
    EvidenceCacheKey,
    EvidenceInput,
    KnowledgeBundle,
)
from datakeel.core.evidence_models import (
    Assertion,
    AssertionDecisionRequest,
    EvidenceAnchor,
    EvidenceValue,
    ExtractorRef,
)
from datakeel.core.models import AssetRef, JsonDocument, LineageEvent, new_id
from datakeel.storage.database import VersionRow
from datakeel.storage.evidence_decisions import decide_assertions, list_decisions
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.evidence_store import list_assertions, record_extraction

if TYPE_CHECKING:
    from datakeel.core.evidence_models import AssertionStatus
    from datakeel.storage.database import Database
    from tests.actions.conftest import DatasetFixture


def source_refs(db: Database, dataset: DatasetFixture) -> list[AssetRef]:
    """Resolve real generated manifest identities for synthetic extraction observations."""
    with db.session() as session:
        version = session.scalar(select(VersionRow).where(VersionRow.dataset_id == dataset[0].id))
        assert version is not None
        return sorted(
            [
                AssetRef(asset_type="file", asset_id=file.id, version=version.id)
                for file in dataset[1]
            ],
            key=lambda ref: ref.asset_id,
        )


def publish_assertion(
    db: Database, ref: AssetRef, *, other: AssetRef | None = None, version: str = "1"
) -> Assertion:
    """Produce a test observation through the authoritative extraction publication path."""
    identifier = new_id()
    extractor = ExtractorRef(
        id="evidence.near_duplicate" if other else "evidence.image_phash", version=version
    )
    refs = [ref, other] if other else [ref]
    assertion = Assertion(
        subject=ref,
        predicate="near_duplicate_of" if other else "corrupt",
        object=other or EvidenceValue(value="absent"),
        anchors=tuple(EvidenceAnchor(asset_ref=value, content_revision="a" * 64) for value in refs),
        extractor=extractor,
        producer_event_id=identifier,
        run_id=identifier,
        distance=2 if other else None,
    )
    key = EvidenceCacheKey(
        inputs=(EvidenceInput(role="image", content_revision="a" * 64),),
        extractor=extractor,
        lexicon_hash="b" * 64,
        near_duplicate_hash="c" * 64,
    )
    record_extraction(
        db,
        LineageEvent(
            event_id=identifier,
            idempotency_key=identifier,
            operator=extractor.id,
            event_type="COMPLETE",
            inputs=refs,
            outputs=[AssetRef(asset_type="knowledge_bundle", asset_id=identifier, version="1")],
            params={"run_id": identifier},
        ),
        KnowledgeBundle(
            run_id=identifier,
            assertions=(assertion,),
            cache_entries=(
                EvidenceCacheEntry(
                    subject=ref,
                    key=key,
                    assertion_ids=(assertion.id,),
                ),
            ),
        ),
    )
    return assertion


def prepare_decision(
    db: Database,
    identifiers: tuple[str, ...],
    status: AssertionStatus = "accepted",
    context: ActionContext | None = None,
) -> ActionPlan:
    """Prepare the exact typed decision without embedding extractor content in the action."""
    return prepare_action(
        db,
        "decide_assertions",
        JsonDocument.model_validate(
            DecideAssertionsParams(assertion_ids=identifiers, status=status).model_dump(mode="json")
        ),
        context=context,
    )


def test_decision_action_is_automatic_reversible_and_immutable(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """Review and restore candidate status without changing any original observation payload."""
    assertion = publish_assertion(db, source_refs(db, dataset)[0])
    with db.session() as session:
        row = session.get(AssertionRow, assertion.id)
        assert row is not None
        original = row.payload
    plan = prepare_decision(db, (assertion.id, assertion.id))
    assert not plan.requires_approval
    assert plan.canonical_params["assertion_ids"] == [assertion.id]
    assert action_definition("decide_assertions").inverse_of == "decide_assertions"
    request = ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    run = execute_plan(db, plan.id, request)
    assert run.status == "SUCCEEDED"
    assert execute_plan(db, plan.id, request) == run
    assert len(list_decisions(db)) == 1
    assert run.receipt is not None
    assert set(run.receipt.quality["details"]) == {"assertion_ids", "before", "after"}
    assert "anchors" not in run.receipt.model_dump_json()
    for status in ("rejected", "candidate"):
        reversal = prepare_decision(db, (assertion.id,), status)
        execute_plan(db, reversal.id, ExecuteRequest(plan_digest=reversal.plan_digest))
    assert list_assertions(db)[0].status == "candidate"
    assert len(list_decisions(db)) == 3
    with db.session() as session:
        row = session.get(AssertionRow, assertion.id)
        assert row is not None
        assert row.payload == original


def test_near_duplicate_decision_freezes_both_exact_source_versions(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """Avoid a version/id cross product while freezing and receipting both semantic endpoints."""
    refs = source_refs(db, dataset)
    with db.session() as session:
        original = session.get(VersionRow, refs[0].version)
        assert original is not None
        newer = VersionRow(dataset_id=dataset[0].id, manifest=original.manifest)
        session.add(newer)
        session.flush()
        right = refs[1].model_copy(update={"version": newer.id})
        session.commit()
    assertion = publish_assertion(db, refs[0], other=right)
    plan = prepare_decision(db, (assertion.id,))
    expected = {(refs[0].asset_id, refs[0].version), (right.asset_id, right.version)}
    assert {
        (value.asset_ref.asset_id, value.asset_ref.version) for value in plan.manifest.objects
    } == expected
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert run.receipt is not None
    assert {
        (ref.asset_id, ref.version) for ref in run.receipt.outputs if ref.asset_type == "file"
    } == expected


def test_decision_scope_and_intervening_status_changes_are_enforced(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """Deny missing privileges and reject stale plans after another accepted review."""
    assertion = publish_assertion(db, source_refs(db, dataset)[0])
    with pytest.raises(AuthorizationError, match="evidence:write"):
        prepare_decision(db, (assertion.id,), context=ActionContext(scopes=["files:write"]))
    stale = prepare_decision(db, (assertion.id,))
    fresh = prepare_decision(
        db, (assertion.id,), "rejected", ActionContext(scopes=["evidence:write"])
    )
    execute_plan(db, fresh.id, ExecuteRequest(plan_digest=fresh.plan_digest))
    with pytest.raises(ConflictError, match="state changed"):
        execute_plan(db, stale.id, ExecuteRequest(plan_digest=stale.plan_digest))
    assert list_assertions(db)[0].status == "rejected"
    assert len(list_decisions(db)) == 1


def test_invalidated_unknown_and_unavailable_source_assertions_are_rejected(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """Keep superseded evidence read-only and require exact real source manifests."""
    ref = source_refs(db, dataset)[0]
    old = publish_assertion(db, ref)
    publish_assertion(db, ref, version="2")
    with pytest.raises(ConflictError, match="Invalidated"):
        prepare_decision(db, (old.id,))
    with pytest.raises(NotFoundError, match="does not exist"):
        prepare_decision(db, ("unknown",))
    unavailable = publish_assertion(db, ref.model_copy(update={"version": "missing-version"}))
    with pytest.raises(ConflictError, match="source version"):
        prepare_decision(db, (unavailable.id,))
    untyped = publish_assertion(db, ref.model_copy(update={"asset_type": "dataset"}))
    with pytest.raises(ValidationError, match="file endpoints"):
        prepare_decision(db, (untyped.id,))


def test_decision_mutation_rolls_back_when_receipt_publication_fails(
    db: Database,
    dataset: DatasetFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Roll back status and decision audit together when the action cannot complete."""
    assertion = publish_assertion(db, source_refs(db, dataset)[0])
    plan = prepare_decision(db, (assertion.id,))

    def failed_receipt(
        prepared: ActionPlan,
        run_id: str,
        outputs: list[AssetRef],
        *,
        error: str | None = None,
    ) -> LineageEvent:
        if error is None:
            msg = "fixture receipt failure"
            raise ExecutionError(msg)
        return receipt(prepared, run_id, outputs, error=error)

    monkeypatch.setattr("datakeel.storage.action_execution.receipt", failed_receipt)
    with pytest.raises(ExecutionError, match="fixture receipt failure"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert list_assertions(db)[0].status == "candidate"
    assert not list_decisions(db)


def test_decision_plan_rejects_invalidation_after_preparation(
    db: Database,
    dataset: DatasetFixture,
) -> None:
    """Never review or reactivate an assertion superseded while its plan was pending."""
    ref = source_refs(db, dataset)[0]
    old = publish_assertion(db, ref)
    plan = prepare_decision(db, (old.id,))
    publish_assertion(db, ref, version="new")
    with pytest.raises(ConflictError, match="Invalidated"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    with pytest.raises(ConflictError, match="Invalidated"):
        decide_assertions(
            db,
            AssertionDecisionRequest(
                assertion_ids=(old.id,),
                status="accepted",
                actor="local",
                idempotency_key="direct",
            ),
        )
    assert all(
        value.status == "candidate" for value in list_assertions(db, include_invalidated=True)
    )
    assert [decision.action for decision in list_decisions(db)] == ["invalidate"]
