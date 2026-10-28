# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Answer read-only training-quality questions with saved or freshly measured facts."""

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import ValidationError
from datakeel.core.llm_data_models import TrainingReport
from datakeel.core.training_governance import TrainingQualityQuery
from datakeel.llm_data import analyze_sources
from datakeel.storage.database import Database
from datakeel.storage.training_access import authorize_training, training_refs
from datakeel.storage.training_sources import fresh_sources, source_files, source_version
from datakeel.storage.training_store import version_training_report


def read_training_quality(
    db: Database, query: TrainingQualityQuery, *, access: AccessContext | None = None
) -> TrainingReport:
    """Return measured record-level issues without creating reports, versions or actions."""
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
            session.commit()
            return saved[0]
        if not files:
            msg = "The selected dataset version has no training JSONL files"
            raise ValidationError(msg)
        with fresh_sources(files) as sources:
            report = analyze_sources(sources)
        session.commit()
        return report
