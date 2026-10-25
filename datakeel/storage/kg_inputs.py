# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rehydrate signed graph fingerprints before any extraction request can be made."""

from pathlib import Path

from sqlalchemy.orm import Session

from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.kg_execution import (
    KGDocument,
    KGDocumentFingerprint,
    KGInputs,
    KGJob,
    KGLeaseFence,
)
from datakeel.core.kg_images import KGImageInput
from datakeel.core.models import FileItem
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.datasets import materialize_files
from datakeel.storage.kg_preparation import read_documents, read_recording
from datakeel.storage.kg_rows import KGRunRow
from datakeel.storage.kg_store import owned
from datakeel.transcription.images import normalize_image
from datakeel.transcription.loader import read_recording as read_transcription_recording


def restore_inputs(db: Database, job: KGJob, fence: KGLeaseFence) -> KGInputs:
    """Verify every source and recording before persisting authorized source snapshots."""
    prepared = job.prepared
    params = RunKGExtractionParams(
        dataset_id=job.run.dataset_id,
        version_id=job.run.version_id,
        file_ids=tuple(document.asset_ref.asset_id for document in prepared.documents),
        mode_overrides={
            document.asset_ref.asset_id: document.image.mode
            for document in prepared.documents
            if document.image is not None
        },
    )
    with db.session() as session:
        try:
            documents = read_documents(
                session, params, prepared.profile, prepared.transcription_profile
            )
            recording_hash, recording = read_recording(prepared.profile)
            transcription_hash = None
            if prepared.transcription_profile:
                transcription_hash, _ = read_transcription_recording(prepared.transcription_profile)
            images = _read_images(session, job, documents)
        except (OSError, ValidationError) as error:
            msg = "Graph approved inputs could not be restored or no longer match their manifest"
            raise ValidationError(msg) from error
    fingerprints = tuple(KGDocumentFingerprint.from_document(item) for item in documents)
    if (
        fingerprints != prepared.documents
        or recording_hash != prepared.recording_hash
        or transcription_hash != prepared.transcription_recording_hash
    ):
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
    return KGInputs(documents=documents, recording=recording, images=images)


def _read_images(
    session: Session, job: KGJob, documents: tuple[KGDocument, ...]
) -> tuple[KGImageInput, ...]:
    identifiers = {
        document.asset_ref.asset_id: document.content_revision
        for document in documents
        if document.image
    }
    if not identifiers:
        return ()
    version = session.get(VersionRow, job.run.version_id)
    if version is None:
        msg = "Image source version was not found"
        raise ValidationError(msg)
    files = [
        FileItem.model_validate(value) for value in version.manifest if value["id"] in identifiers
    ]
    result = tuple(
        KGImageInput(file_id=file.id, image=normalize_image(Path(file.path).read_bytes()))
        for file in materialize_files(files)
    )
    if any(value.image.image_hash != identifiers[value.file_id] for value in result):
        msg = "Image content changed during source restoration"
        raise ValidationError(msg)
    return result
