# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Register and resolve explicitly selected evaluation snapshots without external content."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError
from datakeel.core.llm_data_governance import TrainingEvaluation, TrainingEvaluationRequest
from datakeel.core.models import AssetRef, FileItem, new_id, utcnow
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import require_dataset
from datakeel.storage.llm_data_access import authorize_training, training_refs
from datakeel.storage.llm_data_rows import TrainingEvaluationRow
from datakeel.storage.llm_data_sources import source_files, source_version


def register_evaluation(
    db: Database,
    dataset_id: str,
    request: TrainingEvaluationRequest,
    *,
    access: AccessContext | None = None,
) -> TrainingEvaluation:
    """Pin user-owned uploaded files to an immutable evaluation registration."""
    with db.session() as session:
        require_dataset(session, dataset_id)
        version = source_version(session, request.source_dataset_id, request.version_id)
        files = source_files(session, version, request.file_ids, evaluation=True)
        authorize_training(
            session,
            training_refs(request.source_dataset_id, version.id, tuple(item.id for item in files)),
            access=access,
        )
        result = TrainingEvaluation(
            id=new_id(),
            dataset_id=dataset_id,
            name=request.name,
            source_dataset_id=request.source_dataset_id,
            version_id=version.id,
            file_ids=tuple(item.id for item in files),
            created_at=utcnow(),
        )
        session.add(
            TrainingEvaluationRow(
                id=result.id, dataset_id=dataset_id, payload=result.model_dump(mode="json")
            )
        )
        session.commit()
        return result


def list_evaluations(
    db: Database, dataset_id: str, *, access: AccessContext | None = None
) -> tuple[TrainingEvaluation, ...]:
    """List only evaluation registrations owned by the requested governance dataset."""
    with db.session() as session:
        require_dataset(session, dataset_id)
        result = tuple(
            TrainingEvaluation.model_validate(row.payload)
            for row in session.scalars(
                select(TrainingEvaluationRow)
                .where(TrainingEvaluationRow.dataset_id == dataset_id)
                .order_by(TrainingEvaluationRow.id)
            )
        )
        authorize_training(
            session, (AssetRef(asset_id=dataset_id),), tuple(value.id for value in result), access
        )
        session.commit()
        return result


def evaluation_files(
    session: Session, dataset_id: str, identifiers: tuple[str, ...]
) -> tuple[FileItem, ...]:
    """Resolve registered version references again so deleted sources cannot be reused."""
    files: dict[str, FileItem] = {}
    for identifier in sorted(set(identifiers)):
        row = session.get(TrainingEvaluationRow, identifier)
        if row is None or row.dataset_id != dataset_id:
            msg = "Registered training evaluation not found"
            raise NotFoundError(msg)
        evaluation = TrainingEvaluation.model_validate(row.payload)
        version = source_version(session, evaluation.source_dataset_id, evaluation.version_id)
        for item in source_files(session, version, evaluation.file_ids, evaluation=True):
            files[item.id] = item
    return tuple(files.values())
