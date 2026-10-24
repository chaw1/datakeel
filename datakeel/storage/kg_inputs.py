# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rehydrate signed graph fingerprints before any extraction request can be made."""

from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.kg_execution import KGDocumentFingerprint, KGInputs, KGJob, KGLeaseFence
from datakeel.storage.database import Database
from datakeel.storage.kg_preparation import read_documents, read_recording
from datakeel.storage.kg_rows import KGRunRow
from datakeel.storage.kg_store import owned


def restore_inputs(db: Database, job: KGJob, fence: KGLeaseFence) -> KGInputs:
    """Verify every source and recording before persisting authorized source snapshots."""
    prepared = job.prepared
    params = RunKGExtractionParams(
        dataset_id=job.run.dataset_id,
        version_id=job.run.version_id,
        file_ids=tuple(document.asset_ref.asset_id for document in prepared.documents),
    )
    with db.session() as session:
        try:
            documents = read_documents(session, params, prepared.profile)
            recording_hash, recording = read_recording(prepared.profile)
        except (OSError, ValidationError) as error:
            msg = "Graph approved inputs could not be restored or no longer match their manifest"
            raise ValidationError(msg) from error
    fingerprints = tuple(KGDocumentFingerprint.from_document(item) for item in documents)
    if fingerprints != prepared.documents or recording_hash != prepared.recording_hash:
        msg = "Graph approved input fingerprints changed: source, blocks or recording"
        raise ValidationError(msg)
    with db.session() as session:
        db.lock_writes(session)
        if not owned(session, fence):
            msg = "Graph worker lease was lost before input verification"
            raise ConflictError(msg)
        row = session.get(KGRunRow, job.run.id)
        if row is None or row.task_id != fence.task_id:
            msg = "Graph run does not belong to the worker task"
            raise ValidationError(msg)
        current = KGJob.model_validate(row.payload)
        row.payload = current.model_copy(update={"documents": documents}).model_dump(mode="json")
        session.commit()
    return KGInputs(documents=documents, recording=recording)
