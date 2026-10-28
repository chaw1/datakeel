# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen and fingerprintable policy for local OCR-to-vision routing."""

from typing import Literal

from pydantic import Field

from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel

AutoReason = Literal[
    "low_confidence",
    "structure_diagram",
    "struck_or_greyed_rows",
    "sparse_text",
    "ocr_failed",
    "clean_text",
]


class AutoRoutingConfig(BoundaryModel):
    """Keep every numerical routing threshold in the signed transcription profile.

    Image analysis is bounded by downsampling, never by source filename or identity.
    Ratios use OCR line heights so the same signals survive image resizing.
    Document padding bounds the sparse-text denominator around OCR content; contrast
    rejects surrounding dark scenery. Grey-row comparisons require aligned nearby
    rows and abrupt local background changes; strike limits reject thick or extended
    background lines.
    """

    version: Literal["auto-v1", "auto-v2"] = "auto-v2"
    min_mean_confidence: float = Field(default=0.85, ge=0, le=1, allow_inf_nan=False)
    analysis_max_side: int = Field(default=1200, ge=64, le=4096)
    max_connector_neighbors: int = Field(default=12, ge=2, le=1024)
    dark_pixel_threshold: int = Field(default=160, ge=0, le=255)
    connector_min_height_ratio: float = Field(default=1.5, gt=0, allow_inf_nan=False)
    connector_min_coverage: float = Field(default=0.72, gt=0, le=1, allow_inf_nan=False)
    connector_tolerance_ratio: float = Field(default=0.12, ge=0, le=1, allow_inf_nan=False)
    connector_projection_margin_ratio: float = Field(default=0.5, ge=0, le=2, allow_inf_nan=False)
    text_mask_padding_ratio: float = Field(default=0.08, ge=0, le=1, allow_inf_nan=False)
    strike_min_width_ratio: float = Field(default=0.75, gt=0, le=1, allow_inf_nan=False)
    strike_vertical_margin: float = Field(default=0.25, ge=0, lt=0.5, allow_inf_nan=False)
    strike_max_thickness_ratio: float = Field(default=0.2, gt=0, lt=1, allow_inf_nan=False)
    strike_max_extension_ratio: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)
    grey_min_brightness: int = Field(default=100, ge=0, le=255)
    grey_max_brightness: int = Field(default=235, ge=0, le=255)
    grey_min_contrast: int = Field(default=15, ge=0, le=255)
    grey_min_text_brightness: int = Field(default=110, ge=0, le=255)
    grey_min_row_fraction: float = Field(default=0.6, gt=0, le=1, allow_inf_nan=False)
    grey_context_height_ratio: float = Field(default=0.5, gt=0, allow_inf_nan=False)
    grey_alignment_height_ratio: float = Field(default=1, ge=0, le=4, allow_inf_nan=False)
    grey_max_line_height_ratio: float = Field(default=1.6, ge=1, allow_inf_nan=False)
    grey_max_neighbor_height_ratio: float = Field(default=8, gt=0, allow_inf_nan=False)
    grey_background_step_height_ratio: float = Field(default=0.2, gt=0, le=1, allow_inf_nan=False)
    grey_min_edge_concentration: float = Field(default=0.75, gt=0, le=1, allow_inf_nan=False)
    grey_edge_probe_height_ratio: float = Field(default=0.05, gt=0, le=1, allow_inf_nan=False)
    background_percentile: float = Field(default=90, ge=0, le=100, allow_inf_nan=False)
    sparse_max_characters: int = Field(default=16, ge=1)
    min_text_area_ratio: float = Field(default=0.003, ge=0, le=1, allow_inf_nan=False)
    document_analysis_max_side: int = Field(default=256, ge=64, le=1200)
    document_padding_height_ratio: float = Field(default=3, ge=0, allow_inf_nan=False)
    document_min_contrast: int = Field(default=25, ge=0, le=255)
    document_min_component_area_ratio: float = Field(default=0.5, gt=0, le=1, allow_inf_nan=False)
    max_box_area_per_character: float = Field(default=2, gt=0, allow_inf_nan=False)
    max_unmatched_ink_fraction: float = Field(default=0.85, ge=0, le=1, allow_inf_nan=False)


class AutoRouteDecision(BoundaryModel):
    """Explain the final route using deterministic, language-independent reason codes."""

    route: Literal["ocr", "vlm"]
    reasons: tuple[AutoReason, ...]
    version: Literal["auto-v1", "auto-v2"] = "auto-v2"


class OCRReference(BoundaryModel):
    """Keep the local attempt for human comparison without feeding it to extraction."""

    text: str
    error: str | None = None


def require_current_auto_policy(config: AutoRoutingConfig, *, automatic: bool = True) -> None:
    """Permit historical reads and explicit routes while rejecting obsolete auto execution."""
    if automatic and config.version != "auto-v2":
        message = "Automatic transcription requires auto-v2; prepare and approve a new plan"
        raise ValidationError(message)
