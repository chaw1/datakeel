# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent expected routes and observed automatic image evaluation measurements."""

from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel
from datakeel.core.transcription_auto import AutoReason


class ImageRouteResult(BoundaryModel):
    """Retain an observed route without using the expected route to choose a backend."""

    case_id: str
    expected_route: Literal["ocr", "vlm"] | None = None
    route: Literal["ocr", "vlm"] | None
    reasons: tuple[AutoReason, ...] = ()
    external: bool = False


class ImageAutoMetrics(BoundaryModel):
    """Score actual routing, outbound calls and product extraction on labelled images."""

    cases: int = Field(ge=0)
    labelled_cases: int = Field(ge=0)
    route_correct: int = Field(ge=0)
    route_accuracy: float | None = Field(default=None, ge=0, le=1)
    external_images: int = Field(ge=0)
    external_ratio: float = Field(ge=0, le=1)
    vlm_images: int = Field(ge=0)
    vlm_ratio: float = Field(ge=0, le=1)
    extraction_f1: float = Field(ge=0, le=1)
    routes: tuple[ImageRouteResult, ...]
