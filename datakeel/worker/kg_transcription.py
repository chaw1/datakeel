# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Turn authorized image documents into immutable text assets before ordinary extraction."""

from contextlib import ExitStack

from datakeel.core.errors import BudgetError, ConflictError, ValidationError
from datakeel.core.kg_execution import KGBlockFailure, KGDocument, KGInputs, KGJob, KGLeaseFence
from datakeel.core.kg_images import TranscriptionObservation
from datakeel.core.transcription_auto import OCRReference
from datakeel.core.transcription_errors import TranscriptionFailure, TranscriptionUnavailableError
from datakeel.core.transcription_models import ImageInput, TranscriptionProfile, TranscriptionResult
from datakeel.kg.text import chunk_text, decode_text
from datakeel.storage.kg_image_preparation import transcript_ref
from datakeel.storage.transcription_pricing import transcription_external
from datakeel.storage.transcription_store import (
    cached_transcription,
    save_transcript_documents,
    save_transcription,
)
from datakeel.transcription.auto_adapter import AutoTranscriber
from datakeel.transcription.cache import cache_key
from datakeel.transcription.factory import create_transcriber
from datakeel.transcription.loader import read_recording
from datakeel.transcription.quality import TranscriberAdapter, checked_transcribe
from datakeel.worker.queue import DatabaseQueue, Lease
from datakeel.worker.transcription_consent import authorize_image_transfer
from datakeel.worker.transcription_metering import MeteredTranscriber


class ImageTranscription:
    """Keep failures visible and reuse complete transcripts without constructing providers."""

    def __init__(self, queue: DatabaseQueue, lease: Lease, job: KGJob, stack: ExitStack) -> None:
        """Bind transcription writes and future text sources to the worker's exact fence."""
        self.queue, self.lease, self.job, self.stack = queue, lease, job, stack
        self.fence = KGLeaseFence(task_id=lease.task_id, shard_id=lease.shard_id, owner=lease.owner)
        self.adapter: TranscriberAdapter | None = None
        self.observations: list[TranscriptionObservation] = []
        self.failures: list[KGBlockFailure] = []
        self.external_files: set[str] = set()
        self.current_image: ImageInput | None = None

    def _adapter(self, profile: TranscriptionProfile, document: KGDocument) -> TranscriberAdapter:
        if self.adapter is None:
            recording_hash, recording = read_recording(profile)
            if recording_hash != self.job.prepared.transcription_recording_hash:
                msg = "Approved transcription recording changed before execution"
                raise ValidationError(msg)
            automatic = any(
                item.image and item.image.mode == "auto" for item in self.job.prepared.documents
            )
            selected = profile.model_copy(update={"mode": "auto"}) if automatic else profile
            if not automatic and document.image is not None:
                selected = profile.model_copy(update={"mode": document.image.mode})
            self.adapter = self.stack.enter_context(
                create_transcriber(selected, recording=recording)
            )

        def before_request() -> bool:
            if document.image is None:
                return False
            image = self.current_image
            if image is None:
                return False
            authorize_image_transfer(self.job, document, image)
            if transcription_external(profile):
                self.external_files.add(document.image.asset_ref.asset_id)
            return self.queue.heartbeat(self.lease)

        return MeteredTranscriber(self.queue.db, self.job, self.adapter, before_request)

    def _result(
        self, document: KGDocument, image: ImageInput | None
    ) -> tuple[TranscriptionResult, bool]:
        if image is None:
            msg = "Image could not be decoded"
            raise TranscriptionUnavailableError(msg, reason="image_decode_error")
        profile, source = self.job.prepared.transcription_profile, document.image
        if profile is None or source is None:
            msg = "Image transcription requires a prepared profile and image"
            raise ValueError(msg)
        key = cache_key(
            image.image_hash, profile, self.job.prepared.transcription_recording_hash, source.mode
        )
        cached = cached_transcription(self.queue.db, key)
        if cached is not None:
            return cached, True
        if not self.queue.heartbeat(self.lease):
            msg = "Graph worker lease was lost before transcription"
            raise ConflictError(msg)
        self.current_image = image
        result = checked_transcribe(self._adapter(profile, document), image, source.mode)
        if (result.width, result.height) != (source.width, source.height):
            msg = "Transcription coordinates do not match the corrected image"
            raise ValidationError(msg)
        if not save_transcription(self.queue.db, self.fence, key, result):
            msg = "Graph worker lease was lost before transcript publication"
            raise ConflictError(msg)
        return result, False

    def _document(self, document: KGDocument, image: ImageInput | None) -> KGDocument | None:
        source = document.image
        if source is None:
            return document
        observation = TranscriptionObservation(
            file_id=source.asset_ref.asset_id,
            filename=document.filename,
            backend=source.backend,
            model=source.model,
            mode=source.mode,
        )
        try:
            result, cached = self._result(document, image)
        except (
            TranscriptionFailure,
            TranscriptionUnavailableError,
            BudgetError,
            TimeoutError,
        ) as error:
            if (
                image is not None
                and source.mode == "auto"
                and isinstance(self.adapter, AutoTranscriber)
                and self.adapter.image_hash == image.image_hash
                and self.adapter.decision is not None
            ):
                observation = observation.model_copy(
                    update={
                        "mode": self.adapter.decision.route,
                        "reasons": self.adapter.decision.reasons,
                        "ocr_reference": OCRReference(
                            text=self.adapter.ocr.text, error=self.adapter.ocr.error
                        )
                        if self.adapter.ocr is not None and self.adapter.decision.route == "vlm"
                        else None,
                    }
                )
            self._failed(observation, error)
            return None
        self.observations.append(
            observation.model_copy(
                update={
                    "cached": cached,
                    "model": result.model,
                    "mode": result.mode,
                    "reasons": result.auto_decision.reasons if result.auto_decision else (),
                    "ocr_reference": result.ocr_reference,
                    "quality_issues": result.quality_issues,
                    "ignored_field_count": result.ignored_field_count,
                    "external": observation.file_id in self.external_files,
                    "backend": source.backend
                    if source.backend in {"replay", "fake"}
                    else result.backend,
                }
            )
        )
        return self._derived(document, result)

    def _failed(
        self,
        observation: TranscriptionObservation,
        error: TranscriptionFailure | TranscriptionUnavailableError | BudgetError | TimeoutError,
    ) -> None:
        reason = (
            error.reason
            if isinstance(error, (TranscriptionFailure, TranscriptionUnavailableError))
            else ("budget_exceeded" if isinstance(error, BudgetError) else "timeout")
        )
        attempted = not isinstance(error, BudgetError)
        if not attempted:
            self.external_files.discard(observation.file_id)
        self.failures.append(
            KGBlockFailure(
                file_id=observation.file_id,
                filename=observation.filename,
                start=0,
                end=0,
                reason=f"transcription:{reason}",
                attempted=attempted,
            )
        )
        self.observations.append(
            observation.model_copy(
                update={
                    "status": "failed" if attempted else "unexecuted",
                    "external": observation.file_id in self.external_files,
                    "error": (error.result.error or reason)
                    if isinstance(error, TranscriptionFailure)
                    else str(error)
                    if isinstance(error, TranscriptionUnavailableError)
                    else reason,
                    "quality_issues": error.result.quality_issues
                    if isinstance(error, TranscriptionFailure)
                    else (),
                    "ignored_field_count": error.result.ignored_field_count
                    if isinstance(error, TranscriptionFailure)
                    else 0,
                }
            )
        )

    def _derived(self, document: KGDocument, result: TranscriptionResult) -> KGDocument:
        source = document.image
        if source is None:
            return document
        text = decode_text(result.text.encode("utf-8"))
        ref = transcript_ref(source, text)
        return document.model_copy(
            update={
                "asset_ref": ref,
                "text": text,
                "content_revision": ref.version,
                "blocks": chunk_text(
                    text,
                    self.job.prepared.profile.chunk_size,
                    self.job.prepared.profile.chunk_overlap,
                ),
                "image": source.model_copy(
                    update={
                        "lines": result.lines,
                        "backend": result.backend,
                        "model": result.model,
                        "mode": result.mode,
                    }
                ),
            }
        )

    def run(self, inputs: KGInputs) -> KGJob:
        """Persist successful derived sources and retain one explicit report row per image."""
        images = {value.file_id: value.image for value in inputs.images}
        documents: list[KGDocument] = []
        for document in inputs.documents:
            if document.image is None:
                documents.append(document)
            elif (
                derived := self._document(document, images.get(document.asset_ref.asset_id))
            ) is not None:
                documents.append(derived)
        report = self.job.run.report.model_copy(
            update={
                "transcriptions": tuple(self.observations),
                "failures": tuple(self.failures),
                "transcription_failed": len(self.failures),
                "transcription_external_images": len(self.external_files),
            }
        )
        job = self.job.model_copy(
            update={
                "documents": tuple(documents),
                "run": self.job.run.model_copy(update={"report": report}),
            }
        )
        if not save_transcript_documents(self.queue.db, self.fence, job):
            msg = "Graph worker lease was lost before derived source publication"
            raise ConflictError(msg)
        return job
