# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze training and evaluation file ownership together in the approved source manifest."""

from sqlalchemy.orm import Session

from datakeel.actions.training_parameters import CleanTrainingParams
from datakeel.core.errors import NotFoundError
from datakeel.core.training_governance import TrainingEvaluation
from datakeel.ontology.models import FrozenManifest, FrozenObject, ObjectSet, PropertyFilter
from datakeel.storage.object_projection import content_digest
from datakeel.storage.object_queries import evaluate_in_session
from datakeel.storage.training_rows import TrainingEvaluationRow
from datakeel.storage.training_sources import source_version
from datakeel.storage.training_store import require_training_run


def training_manifest(session: Session, params: CleanTrainingParams) -> FrozenManifest:
    """Include every evaluation source so approval and replay preserve native asset grants."""
    row = require_training_run(session, params.run_id)
    source = source_version(session, row.dataset_id, row.version_id)
    selections = [
        (row.dataset_id, row.version_id, tuple(str(item["id"]) for item in source.manifest))
    ]
    for identifier in row.evaluation_ids:
        evaluation_row = session.get(TrainingEvaluationRow, identifier)
        if evaluation_row is None or evaluation_row.dataset_id != row.dataset_id:
            msg = "Registered training evaluation not found"
            raise NotFoundError(msg)
        evaluation = TrainingEvaluation.model_validate(evaluation_row.payload)
        selections.append(
            (evaluation.source_dataset_id, evaluation.version_id, evaluation.file_ids)
        )
    objects: dict[tuple[str, str], FrozenObject] = {}
    query = ObjectSet(dataset_id=row.dataset_id, limit=10000)
    for dataset_id, version_id, identifiers in selections:
        selected = evaluate_in_session(
            session,
            ObjectSet(
                dataset_id=dataset_id,
                version_ids=[version_id],
                limit=10000,
                filters=[PropertyFilter(field="id", operator="in", value=list(identifiers))],
            ),
        )
        for item in selected.objects:
            objects[(item.asset_ref.asset_id, item.asset_ref.version or "")] = item
    values = [objects[key] for key in sorted(objects)]
    return FrozenManifest(
        query=query,
        objects=values,
        total_bytes=sum(item.size for item in values),
        state_digest=content_digest([item.model_dump(mode="json") for item in values]),
    )
