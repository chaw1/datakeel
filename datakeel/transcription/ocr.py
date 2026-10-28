# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Load the optional CPU OCR engine only when a real transcription needs line geometry."""

from importlib import import_module
from io import BytesIO
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from datakeel.core.errors import ValidationError
from datakeel.core.transcription_errors import TranscriptionUnavailableError
from datakeel.core.transcription_models import (
    ImageInput,
    OCRLine,
    TranscriptionMode,
    TranscriptionResult,
)


class _OCROutput(Protocol):
    boxes: NDArray[np.float32] | None
    txts: tuple[str, ...] | None
    scores: tuple[float, ...] | None


class _OCREngine(Protocol):
    def __call__(self, image: NDArray[np.uint8]) -> _OCROutput: ...


class _OCRModule(Protocol):
    def RapidOCR(self) -> _OCREngine: ...  # noqa: N802  # Upstream factory spelling.


class _ONNXModule(Protocol):
    def disable_telemetry_events(self) -> None: ...


def quadrilateral_box(
    points: tuple[tuple[float, float], ...],
) -> tuple[float, float, float, float]:
    """Take an enclosing rectangle for rotated text, preserving original pixel coordinates."""
    if len(points) != 4:  # noqa: PLR2004  # A quadrilateral has exactly four corners.
        message = "OCR line must have four corners"
        raise ValidationError(message)
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


class RapidOCRTranscriber:
    """Use the pinned package's bundled default models without importing it offline."""

    def __init__(self, model: str = "rapidocr-3.10.0-defaults") -> None:
        """Defer optional imports and engine construction until the first image."""
        self.model = model
        self.engine: _OCREngine | None = None

    def _initialize(self) -> _OCREngine:
        if self.engine is None:
            try:
                runtime = cast("_ONNXModule", import_module("onnxruntime"))
                runtime.disable_telemetry_events()
                module = cast("_OCRModule", import_module("rapidocr"))
                self.engine = module.RapidOCR()
            except ImportError as error:
                message = (
                    "Image OCR requires user-installed packages: "
                    "pip install rapidocr==3.10.0 onnxruntime"
                )
                raise TranscriptionUnavailableError(message, reason="ocr_not_installed") from error
        return self.engine

    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        """Return text in original OCR line order together with enclosing rectangles."""
        if mode == "vlm":
            message = "RapidOCR supports only ocr mode"
            raise ValidationError(message)
        try:
            return self._transcribe(image)
        except TranscriptionUnavailableError:
            raise
        except Exception as error:
            message = "Local OCR engine failed"
            raise TranscriptionUnavailableError(message, reason="provider_error") from error

    def _transcribe(self, image: ImageInput) -> TranscriptionResult:
        with Image.open(BytesIO(image.png)) as source:
            rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
            pixels = np.ascontiguousarray(rgb[:, :, ::-1])
        result = self._initialize()(pixels)
        lines: tuple[OCRLine, ...] = ()
        if result.boxes is not None and result.txts is not None and result.scores is not None:
            lines = tuple(
                OCRLine(
                    text=text,
                    bbox=quadrilateral_box(tuple((float(x), float(y)) for x, y in box)),
                    confidence=float(score),
                )
                for box, text, score in zip(result.boxes, result.txts, result.scores, strict=True)
            )
        return TranscriptionResult(
            text="\n".join(line.text for line in lines),
            lines=lines,
            width=image.width,
            height=image.height,
            backend="ocr",
            model=self.model,
        )
