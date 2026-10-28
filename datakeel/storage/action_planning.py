# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prepare canonical plans and enforce frozen-target authorization policies."""

from datetime import timedelta

from sqlalchemy.orm import Session

from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.actions.models import ActionContext, ActionImpact, ActionPlan
from datakeel.actions.parameters import (
    DecideAssertionsParams,
    ExportParams,
    PipelineParams,
    VersionParams,
    parse_params,
)
from datakeel.actions.policy import authorize, digest, plan_digest
from datakeel.actions.references import parameter_refs
from datakeel.actions.registry import action_definition
from datakeel.actions.release_parameters import PublishReleaseParams
from datakeel.core.custom_operators import SubmitCustomOperatorParams
from datakeel.core.custom_review import prepare_submission
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.models import BoundaryModel, JsonDocument, new_id, utcnow
from datakeel.ontology.models import FrozenManifest
from datakeel.pipeline import default_pipeline
from datakeel.pipeline.sharding import validate_shards
from datakeel.storage.action_rows import ActionPlanRow
from datakeel.storage.action_selection import require_unique_file_sources
from datakeel.storage.action_snapshot import snapshot_digest
from datakeel.storage.action_store import audit
from datakeel.storage.action_targets import current_manifest
from datakeel.storage.catalog_action_state import catalog_impact, prepare_catalog_params
from datakeel.storage.custom_validation import validate_custom_pipeline
from datakeel.storage.database import Database
from datakeel.storage.evidence_actions import action_manifest
from datakeel.storage.kg_preparation import prepare_kg_params
from datakeel.storage.release_actions import publication_impact


def _impact_count(session: Session, params: BoundaryModel, manifest: FrozenManifest) -> int:
    if isinstance(params, SubmitCustomOperatorParams):
        return 1
    if isinstance(params, PublishReleaseParams):
        return publication_impact(manifest)
    count = catalog_impact(session, params, manifest)
    return (
        max(count, len(params.assertion_ids))
        if isinstance(params, DecideAssertionsParams)
        else count
    )


def verify_plan(session: Session, plan: ActionPlan, expected_digest: str, actor: str) -> None:
    """Revalidate parameters, plan integrity, and the entire current matching set."""
    if expected_digest != plan.plan_digest or plan_digest(plan) != plan.plan_digest:
        msg = "Action plan_digest does not match the frozen plan"
        raise ConflictError(msg)
    authorize(plan, actor)
    verify_target_state(session, plan)


def verify_target_state(session: Session, plan: ActionPlan) -> None:
    """Recheck a consumed plan's frozen content without expiring accepted work."""
    if plan_digest(plan) != plan.plan_digest:
        msg = "Accepted action plan_digest was modified"
        raise ConflictError(msg)
    params = parse_params(plan.action_type, JsonDocument(plan.canonical_params))
    current = current_manifest(session, plan, params)
    if snapshot_digest(session, params, current) != plan.state_digest or current.truncated:
        msg = "Action target state changed after preparation"
        raise ConflictError(msg)


def _prepare_params(session: Session, action_type: str, params: JsonDocument) -> BoundaryModel:
    parsed = prepare_catalog_params(session, parse_params(action_type, params))
    if isinstance(parsed, SubmitCustomOperatorParams):
        parsed = prepare_submission(parsed)
    if isinstance(parsed, RunKGExtractionParams):
        parsed = prepare_kg_params(session, parsed)
    if isinstance(parsed, PipelineParams) and parsed.pipeline is None:
        parsed = parsed.model_copy(update={"pipeline": default_pipeline()})
    if isinstance(parsed, PipelineParams):
        validate_custom_pipeline(session, parsed.pipeline)
        validate_shards(parsed.pipeline, parsed.shards)
    if isinstance(parsed, ExportParams):
        destination = parsed.destination or f"{new_id()}.{parsed.format}.json"
        from_path = destination.replace("\\", "/")
        if "/" in from_path or from_path in {".", ".."}:
            msg = "Export destination must be a filename under the exports directory"
            raise ValidationError(msg)
        parsed = parsed.model_copy(update={"destination": destination})
    return parsed


def _new_plan(
    action_type: str, params: JsonDocument, context: ActionContext, session: Session
) -> ActionPlan:
    definition = action_definition(action_type)
    parsed = _prepare_params(session, action_type, params)
    manifest = action_manifest(session, parsed)
    if isinstance(parsed, VersionParams | PipelineParams | ExportParams | RunKGExtractionParams):
        require_unique_file_sources(manifest)
    kg = parsed.prepared if isinstance(parsed, RunKGExtractionParams) else None
    external = action_type == "export_dataset" or bool(kg and kg.external)
    created = utcnow()
    plan = ActionPlan.model_validate(
        {
            "id": new_id(),
            "operation_id": new_id(),
            "action_type": action_type,
            "canonical_params": parsed.model_dump(mode="json"),
            "manifest": manifest,
            "plan_digest": "",
            "target_digest": digest(
                [
                    ref.model_dump(mode="json")
                    for ref in [
                        *[item.asset_ref for item in manifest.objects],
                        *parameter_refs(parsed),
                    ]
                ]
            ),
            "state_digest": snapshot_digest(session, parsed, manifest),
            "created_at": created,
            "expires_at": created + timedelta(seconds=context.ttl_seconds),
            "reversible": definition.reversible,
            "external": external,
            "impact": ActionImpact(
                object_count=_impact_count(session, parsed, manifest),
                total_bytes=(
                    len(parsed.code.encode())
                    if isinstance(parsed, SubmitCustomOperatorParams)
                    else manifest.total_bytes
                ),
                external=external,
                kg_estimate=kg.estimate if kg else None,
                transcription_estimate=kg.transcription_estimate if kg else None,
            ),
            "actor": context.actor,
            "agent_id": context.agent_id,
            "session_id": context.session_id,
            "context": context,
        }
    )
    return plan.model_copy(update={"plan_digest": plan_digest(plan)})


def prepare_action(
    db: Database, action_type: str, params: JsonDocument, context: ActionContext | None = None
) -> ActionPlan:
    """Freeze a selected target set and persist the exact reviewable action plan."""
    with db.session() as session:
        db.lock_writes(session)
        plan = _new_plan(action_type, params, context or ActionContext(), session)
        authorize(plan, plan.actor)
        session.add(
            ActionPlanRow(id=plan.id, action_type=action_type, payload=plan.model_dump(mode="json"))
        )
        session.flush()
        audit(session, plan, "PREPARE", "SUCCEEDED")
        session.commit()
        return plan
