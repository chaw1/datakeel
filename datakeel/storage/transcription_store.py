# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish transcript snapshots only for the current authorized worker lease."""

from sqlalchemy import text

from datakeel.core.errors import ValidationError
from datakeel.core.kg_execution import KGJob, KGLeaseFence
from datakeel.core.transcription_models import TranscriptionResult
from datakeel.storage.database import Database
from datakeel.storage.kg_rows import KGRunRow
from datakeel.storage.kg_store import owned
from datakeel.storage.transcription_rows import TranscriptionRow
from datakeel.transcription.quality import quality_issues


def cached_transcription(db: Database, key: str) -> TranscriptionResult | None:
    """Read only previously validated complete transcription output."""
    with db.session() as session:
        row = session.get(TranscriptionRow, key)
        return TranscriptionResult.model_validate(row.payload) if row else None


def save_transcription(
    db: Database, fence: KGLeaseFence, key: str, result: TranscriptionResult
) -> bool:
    """Fence successful transcript storage against cancelled or superseded work."""
    if quality_issues(result):
        msg = "Failed transcription cannot enter the successful transcript cache"
        raise ValidationError(msg)
    with db.session() as session:
        db.lock_writes(session)
        if not owned(session, fence):
            return False
        if not db.sqlite:
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"transcription:{key}"},
            )
        if session.get(TranscriptionRow, key) is None:
            session.add(TranscriptionRow(key=key, payload=result.model_dump(mode="json")))
        session.commit()
        return True


def save_transcript_documents(db: Database, fence: KGLeaseFence, job: KGJob) -> bool:
    """Freeze derived source text in the run before graph publication consumes it."""
    with db.session() as session:
        db.lock_writes(session)
        if not owned(session, fence):
            return False
        row = session.get(KGRunRow, job.run.id)
        if row is None or row.task_id != fence.task_id:
            msg = "Transcription run does not belong to the worker task"
            raise ValidationError(msg)
        current = KGJob.model_validate(row.payload)
        row.payload = current.model_copy(
            update={
                "documents": job.documents,
                "run": current.run.model_copy(update={"report": job.run.report}),
            }
        ).model_dump(mode="json")
        session.commit()
        return True
