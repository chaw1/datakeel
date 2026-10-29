# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Answer read-only training-quality questions with saved or freshly measured facts."""

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import ValidationError
from datakeel.core.llm_data_governance import TrainingQualityQuery, TrainingQualityResult
from datakeel.core.llm_data_models import TrainingReport
from datakeel.llm_data import analyze_sources
from datakeel.storage.database import Database
from datakeel.storage.llm_data_access import (
    authorize_training,
    evaluation_source_refs,
    training_refs,
)
from datakeel.storage.llm_data_sources import fresh_sources, source_files, source_version
from datakeel.storage.llm_data_store import version_training_report


def read_training_quality(
    db: Database, query: TrainingQualityQuery, *, access: AccessContext | None = None
) -> TrainingReport:
    """Return measured record-level issues without creating reports, versions or actions."""
    return read_training_result(db, query, access=access).report


def read_training_result(
    db: Database, query: TrainingQualityQuery, *, access: AccessContext | None = None
) -> TrainingQualityResult:
    """Bind report and source references before another version or analysis can become latest."""
    with db.session() as session:
        version = source_version(session, query.dataset_id, query.version_id)
        files = source_files(session, version, ())
        authorize_training(
            session,
            training_refs(query.dataset_id, version.id, tuple(item.id for item in files)),
            access=access,
        )
        saved = version_training_report(session, query.dataset_id, version.id)
        if saved is not None:
            authorize_training(session, (), tuple(saved[1].evaluation_ids), access)
            refs = (
                *training_refs(query.dataset_id, version.id, tuple(saved[1].file_ids)),
                *evaluation_source_refs(session, tuple(saved[1].evaluation_ids)),
            )
            session.commit()
            return TrainingQualityResult(report=saved[0], asset_refs=refs)
        if not files:
            msg = "The selected dataset version has no training JSONL files"
            raise ValidationError(msg)
        with fresh_sources(files) as sources:
            report = analyze_sources(sources)
        session.commit()
        return TrainingQualityResult(
            report=report,
            asset_refs=training_refs(
                query.dataset_id, version.id, tuple(item.id for item in files)
            ),
        )
