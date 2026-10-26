# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Scripted and content-addressed adapters never construct model clients."""

from collections import deque

from datakeel.core.errors import ValidationError
from datakeel.core.transcription_errors import TranscriptionUnavailableError
from datakeel.core.transcription_models import (
    ImageInput,
    TranscriptionMode,
    TranscriptionRecording,
    TranscriptionResult,
)
from datakeel.transcription.coordinates import decode_coordinates


class ReplayTranscriber:
    """Replay by original image hash, independently of the requesting profile name."""

    def __init__(
        self,
        recording: TranscriptionRecording,
        mode: TranscriptionMode = "ocr",
        ocr_model: str = "rapidocr-3.10.0-defaults",
    ) -> None:
        """Index validated records and retain the recorded model attribution."""
        self.recording, self.mode, self.ocr_model = recording, mode, ocr_model
        self.records = {record.image_hash: record for record in recording.records}

    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        """Return even recorded failures so the shared quality gate can reproduce them."""
        record = self.records.get(image.image_hash)
        if record is None:
            message = "No transcription recording for this image content hash"
            raise TranscriptionUnavailableError(message, reason="recording_missing")
        if (record.width, record.height) != (image.width, image.height):
            message = "Transcription recording dimensions do not match the corrected image"
            raise ValidationError(message)
        data = record.model_dump(exclude={"image_hash", "raw_output"})
        data.update(model=record.model or self.recording.model, mode=mode or self.mode)
        if (mode or self.mode) == "ocr" and record.backend == "vlm":
            visual_geometry = self.recording.prompt_version == "image-transcription-v2"
            reference = record.ocr_reference
            data.update(
                text=(reference.text if reference else "")
                if visual_geometry
                else "\n".join(line.text for line in record.lines),
                lines=() if visual_geometry else record.lines,
                backend="ocr",
                model=self.ocr_model,
                finish_reason="stop",
                error=None,
                quality_issues=(),
                input_tokens=0,
                output_tokens=0,
            )
        if (mode or self.mode) == "vlm" and record.backend == "ocr":
            message = "This recording has no visual-model transcription for vlm mode"
            raise TranscriptionUnavailableError(message, reason="mode_mismatch")
        if (
            (mode or self.mode) == "vlm"
            and self.recording.prompt_version == "image-transcription-v2"
            and (
                record.raw_output is not None
                or (not record.lines and record.text.lstrip().startswith("{"))
            )
        ):
            space = self.recording.coordinate_space
            located = decode_coordinates(
                record.raw_output if record.raw_output is not None else record.text,
                image.width,
                image.height,
                space,
            )
            data.update(**located.model_dump(), coordinate_space=space)
        return TranscriptionResult.model_validate(data)


class FakeTranscriber:
    """Yield explicit scripted responses or a stable generated fixture paragraph."""

    def __init__(self, results: tuple[TranscriptionResult, ...] = ()) -> None:
        """Keep the supplied immutable script in invocation order."""
        self.results = deque(results)

    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        """Allow failure scripts without presenting them as observed model behavior."""
        if self.results:
            return self.results.popleft()
        return TranscriptionResult(
            text="Alice works for Example Labs.",
            width=image.width,
            height=image.height,
            backend="fake",
            model="scripted",
            mode=mode or "ocr",
        )
