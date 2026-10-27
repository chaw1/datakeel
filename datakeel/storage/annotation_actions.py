# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Apply signed annotation acceptance decisions inside the existing action transaction."""

from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.core.annotation_sampling import AnnotationAcceptanceParams, SamplingInspection
from datakeel.core.models import AssetRef, new_id, utcnow
from datakeel.ontology.models import FrozenManifest, ObjectSet, PropertyFilter
from datakeel.storage.annotation_rows import AnnotationInspectionRow
from datakeel.storage.annotation_sampling import require_inspection_plan
from datakeel.storage.object_queries import evaluate_in_session


def inspection_manifest(session: Session, params: AnnotationAcceptanceParams) -> FrozenManifest:
    """Freeze the sampled files' real versioned revisions, independent of latest dataset state."""
    sampling = require_inspection_plan(session, params)
    return evaluate_in_session(
        session,
        ObjectSet(
            dataset_id=params.dataset_id,
            version_ids=[params.version_id],
            filters=[PropertyFilter(field="id", operator="in", value=list(sampling.sample_ids))],
            limit=10000,
        ),
    )


def inspect_action(
    session: Session, plan: ActionPlan, params: AnnotationAcceptanceParams
) -> OperationResult:
    """Archive one signed decision; errors count defective units rather than error statements."""
    sampling = require_inspection_plan(session, params)
    defective = sum(check.defective for check in params.checks)
    inspection = SamplingInspection(
        id=new_id(),
        action_plan_id=plan.id,
        sampling_id=sampling.id,
        batch_id=params.batch_id,
        dataset_id=params.dataset_id,
        version_id=params.version_id,
        accepted=defective <= sampling.acceptance_number,
        defective_count=defective,
        acceptance_number=sampling.acceptance_number,
        checks=tuple(sorted(params.checks, key=lambda item: item.sample_id)),
        actor=plan.actor,
        created_at=utcnow(),
    )
    session.add(
        AnnotationInspectionRow(
            id=inspection.id,
            action_plan_id=plan.id,
            batch_id=params.batch_id,
            payload=inspection.model_dump(mode="json"),
            created_at=inspection.created_at.timestamp(),
        )
    )
    return OperationResult(
        outputs=[AssetRef(asset_type="annotation_inspection", asset_id=inspection.id)],
        details=inspection.model_dump(mode="json"),
    )
