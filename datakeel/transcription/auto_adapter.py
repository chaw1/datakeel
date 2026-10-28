# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve automatic routes locally before any visual request or budget reservation."""

from collections.abc import Callable

from datakeel.core.transcription_auto import AutoRouteDecision, AutoRoutingConfig, OCRReference
from datakeel.core.transcription_errors import TranscriptionFailure, TranscriptionUnavailableError
from datakeel.core.transcription_models import ImageInput, TranscriptionMode, TranscriptionResult
from datakeel.transcription.auto import decide_auto_route
from datakeel.transcription.coordinates import check_coordinates
from datakeel.transcription.quality import TranscriberAdapter, checked_transcribe


class AutoTranscriber:
    """Retain a local reference and dispatch only images selected by the frozen rules."""

    def __init__(
        self,
        adapter: TranscriberAdapter,
        config: AutoRoutingConfig,
        seed: Callable[[ImageInput, TranscriptionResult], None] | None = None,
        *,
        coordinate_min_median_iou: float = 0.3,
    ) -> None:
        """Use the same offline or visual adapter for the explicitly selected final route."""
        self.adapter, self.config, self.seed = adapter, config, seed
        self.coordinate_min_median_iou = coordinate_min_median_iou
        self.image_hash: str | None = None
        self.ocr: TranscriptionResult | None = None
        self.decision: AutoRouteDecision | None = None

    def resolve(self, image: ImageInput) -> AutoRouteDecision:
        """Run local OCR once and preserve failures as routing signals, never silent success."""
        if self.image_hash == image.image_hash and self.decision is not None:
            return self.decision
        try:
            ocr = checked_transcribe(self.adapter, image, "ocr")
        except (TranscriptionFailure, TranscriptionUnavailableError, TimeoutError) as error:
            ocr = (
                error.result
                if isinstance(error, TranscriptionFailure)
                else TranscriptionResult(
                    text="", width=image.width, height=image.height, backend="ocr", error=str(error)
                )
            )
        if self.seed is not None:
            self.seed(image, ocr)
        self.image_hash, self.ocr = image.image_hash, ocr
        self.decision = decide_auto_route(image, ocr, self.config)
        return self.decision

    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        """Return final text for extraction and the independent OCR text for human comparison."""
        if mode is not None and mode != "auto":
            return self.adapter.transcribe(image, mode)
        decision = self.resolve(image)
        try:
            result = self.ocr if decision.route == "ocr" else self.adapter.transcribe(image, "vlm")
        except TranscriptionFailure as error:
            error.result = self._complete(error.result, decision)
            raise
        if result is None:
            message = "Automatic transcription has no OCR result"
            raise ValueError(message)
        if decision.route == "vlm" and self.ocr is not None:
            result = check_coordinates(result, self.ocr, self.coordinate_min_median_iou)
        return self._complete(result, decision)

    def _complete(
        self, result: TranscriptionResult, decision: AutoRouteDecision
    ) -> TranscriptionResult:
        return result.model_copy(
            update={
                "mode": decision.route,
                "auto_decision": decision,
                "ocr_reference": OCRReference(text=self.ocr.text, error=self.ocr.error)
                if self.ocr is not None and decision.route == "vlm"
                else None,
            }
        )
