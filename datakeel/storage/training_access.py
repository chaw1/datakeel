# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Apply native data-asset grants before disclosing saved or newly measured training facts."""

from sqlalchemy.orm import Session

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError
from datakeel.core.models import AssetRef
from datakeel.core.training_governance import TrainingEvaluation
from datakeel.storage.data_asset_access import require_access_in_session
from datakeel.storage.training_rows import TrainingEvaluationRow


def training_refs(dataset_id: str, version_id: str, files: tuple[str, ...]) -> tuple[AssetRef, ...]:
    """Identify both dataset-wide and independently protected version-owned files."""
    return (
        AssetRef(asset_id=dataset_id, version=version_id),
        *(AssetRef(asset_type="file", asset_id=file, version=version_id) for file in files),
    )


def authorize_training(
    session: Session,
    refs: tuple[AssetRef, ...],
    evaluation_ids: tuple[str, ...] = (),
    access: AccessContext | None = None,
) -> None:
    """Check evaluation-source grants as well as source-dataset grants before any file read."""
    resolved = (*refs, *evaluation_source_refs(session, evaluation_ids))
    require_access_in_session(
        session,
        resolved,
        access or AccessContext(actor="local", entry="ask", scope="query"),
    )


def evaluation_source_refs(
    session: Session, evaluation_ids: tuple[str, ...]
) -> tuple[AssetRef, ...]:
    """Resolve version-pinned evaluation provenance for both initial reads and cached replays."""
    resolved: list[AssetRef] = []
    for identifier in evaluation_ids:
        row = session.get(TrainingEvaluationRow, identifier)
        if row is None:
            msg = "Registered training evaluation not found"
            raise NotFoundError(msg)
        value = TrainingEvaluation.model_validate(row.payload)
        resolved.extend(training_refs(value.source_dataset_id, value.version_id, value.file_ids))
    return tuple(resolved)
