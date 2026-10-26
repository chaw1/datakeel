# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze exact assertion endpoints and apply controlled status-only review decisions."""

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datakeel.actions.catalog_parameters import CatalogActionParams
from datakeel.actions.data_asset_parameters import DataAssetActionParams
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.actions.parameters import DecideAssertionsParams, selection_for
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.evidence_models import Assertion, AssertionDecisionRequest
from datakeel.core.models import AssetRef, BoundaryModel
from datakeel.ontology.models import FrozenManifest, ObjectSet, PropertyFilter
from datakeel.storage.ask_review import question_references, question_review_digest
from datakeel.storage.catalog_action_state import catalog_manifest
from datakeel.storage.evidence_decisions import assertion_view, decide_in_session
from datakeel.storage.evidence_rows import AssertionDecisionRow, AssertionRow
from datakeel.storage.kg_image_sources import image_review_references
from datakeel.storage.object_projection import content_digest
from datakeel.storage.object_queries import evaluate_in_session


def _assertions(session: Session, params: DecideAssertionsParams) -> list[Assertion]:
    rows = list(
        session.scalars(
            select(AssertionRow)
            .where(AssertionRow.id.in_(params.assertion_ids))
            .order_by(AssertionRow.id)
            .with_for_update()
        )
    )
    if len(rows) != len(params.assertion_ids):
        msg = "An assertion decision target does not exist"
        raise NotFoundError(msg)
    if any(not row.active for row in rows):
        msg = "Invalidated assertions are read-only audit history"
        raise ConflictError(msg)
    return [assertion_view(row) for row in rows]


def _references(session: Session, assertions: list[Assertion]) -> list[AssetRef]:
    refs: dict[tuple[str, str, str], AssetRef] = {}
    for assertion in assertions:
        if assertion.subject.asset_type == "question":
            for ref in question_references(assertion):
                refs[(ref.asset_type, ref.asset_id, ref.version or "")] = ref
            continue
        targets = [assertion.subject]
        if assertion.subject.asset_type == "kg_entity":
            targets = image_review_references(session, assertion)
        if isinstance(assertion.object, AssetRef) and assertion.subject.asset_type != "kg_entity":
            targets.append(assertion.object)
        for ref in targets:
            if ref.asset_type != "file" or ref.namespace != "default" or not ref.version:
                msg = "Assertion decisions require versioned local file endpoints"
                raise ValidationError(msg)
            refs[(ref.asset_type, ref.asset_id, ref.version)] = ref
    return [refs[key] for key in sorted(refs)]


def decision_manifest(
    session: Session, params: DecideAssertionsParams, query: ObjectSet | None = None
) -> FrozenManifest:
    """Bind question facts separately while freezing only genuine file endpoints."""
    assertions = _assertions(session, params)
    questions = [item for item in assertions if item.subject.asset_type == "question"]
    refs = _references(
        session, [item for item in assertions if item.subject.asset_type != "question"]
    )
    manifest = _file_manifest(session, refs, query)
    if questions:
        manifest = manifest.model_copy(
            update={
                "state_digest": content_digest(
                    {
                        "files": manifest.state_digest,
                        "questions": question_review_digest(session, questions),
                    }
                )
            }
        )
    return manifest


def _file_manifest(
    session: Session, refs: list[AssetRef], query: ObjectSet | None
) -> FrozenManifest:
    versions = sorted({ref.version for ref in refs if ref.version is not None})
    template = query or ObjectSet()
    selection = ObjectSet.model_validate(
        {
            **template.model_dump(),
            "version_ids": versions,
            "filters": [
                PropertyFilter.model_validate(
                    {
                        "field": "id",
                        "operator": "in",
                        "value": sorted({ref.asset_id for ref in refs}),
                    }
                )
            ],
            "limit": 10000,
        }
    )
    objects = [
        item
        for version in versions
        for item in evaluate_in_session(
            session,
            selection.model_copy(
                update={
                    "version_ids": [version],
                    "filters": [
                        PropertyFilter(
                            field="id",
                            operator="in",
                            value=[ref.asset_id for ref in refs if ref.version == version],
                        )
                    ],
                }
            ),
        ).objects
    ]
    objects.sort(key=lambda item: (item.asset_ref.asset_id, item.asset_ref.version or ""))
    if {(item.asset_ref.asset_id, item.asset_ref.version) for item in objects} != {
        (ref.asset_id, ref.version) for ref in refs
    }:
        msg = "Assertion source version or endpoint is unavailable"
        raise ConflictError(msg)
    return FrozenManifest(
        query=selection,
        objects=objects,
        total_bytes=sum(item.size for item in objects),
        state_digest=content_digest(
            {
                "query": selection.model_dump(mode="json"),
                "objects": [item.model_dump(mode="json") for item in objects],
            }
        ),
    )


def action_manifest(
    session: Session, params: BoundaryModel, query: ObjectSet | None = None
) -> FrozenManifest:
    """Use exact assertion endpoints for reviews and ordinary ObjectSets for other actions."""
    if isinstance(params, CatalogActionParams | DataAssetActionParams):
        return catalog_manifest()
    if isinstance(params, DecideAssertionsParams):
        return decision_manifest(session, params, query)
    return evaluate_in_session(session, query or selection_for(params))


def decision_snapshot(session: Session, params: DecideAssertionsParams) -> str:
    """Bind reviewed status and audit sequence so intervening changes invalidate a plan."""
    sequence = dict(
        session.execute(
            select(
                AssertionDecisionRow.assertion_id,
                func.max(AssertionDecisionRow.sequence),
            )
            .where(AssertionDecisionRow.assertion_id.in_(params.assertion_ids))
            .group_by(AssertionDecisionRow.assertion_id)
        ).all()
    )
    return json.dumps(
        [
            {
                "id": assertion.id,
                "status": assertion.status,
                "audit_sequence": sequence.get(assertion.id),
                "decided_by": assertion.decided_by,
                "decided_at": assertion.decided_at.isoformat() if assertion.decided_at else None,
            }
            for assertion in _assertions(session, params)
        ],
        sort_keys=True,
        separators=(",", ":"),
    )


def decide_action(
    session: Session, plan: ActionPlan, params: DecideAssertionsParams
) -> OperationResult:
    """Apply a reversible status overlay and publish only identity/status receipt details."""
    before = _assertions(session, params)
    after = decide_in_session(
        session,
        AssertionDecisionRequest(
            assertion_ids=params.assertion_ids,
            status=params.status,
            actor=plan.actor,
            reason=params.reason,
            idempotency_key=f"action:{plan.id}",
        ),
    )
    return OperationResult(
        outputs=_references(session, after),
        details={
            "assertion_ids": list(params.assertion_ids),
            "before": {value.id: value.status for value in before},
            "after": {value.id: value.status for value in after},
        },
    )
