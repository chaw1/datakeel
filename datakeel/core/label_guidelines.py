# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Annotation guidelines and drafting provenance carried by a label set version."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel


class GuidelineExample(BoundaryModel):
    """Point at one real sample that shows (positive) or does not show (negative) a label."""

    sample_id: str = Field(min_length=1, max_length=200)
    kind: Literal["positive", "negative"]
    note: str = Field(default="", max_length=500)


class LabelGuideline(BoundaryModel):
    """How to annotate one label, with examples that cite sample identities."""

    label_id: str = Field(min_length=1)
    text_zh: str = Field(default="", max_length=4000)
    text_en: str = Field(default="", max_length=4000)
    examples: tuple[GuidelineExample, ...] = Field(default=(), max_length=40)


class LabelGuidelines(BoundaryModel):
    """Written annotation guidelines for a whole label set version."""

    overview_zh: str = Field(default="", max_length=8000)
    overview_en: str = Field(default="", max_length=8000)
    rules: tuple[LabelGuideline, ...] = Field(default=(), max_length=500)


class DraftSource(BoundaryModel):
    """Which standard, annotations, samples and model produced a drafted version."""

    standard_codes: tuple[str, ...] = ()
    label_set_ids: tuple[str, ...] = ()
    annotation_dataset_ids: tuple[str, ...] = ()
    dataset_id: str | None = None
    version_id: str | None = None
    sample_ids: tuple[str, ...] = ()
    profile: str = "offline"
    model: str = "offline-rules"
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    plan_id: str | None = None
    drafted_at: datetime | None = None
    dropped_examples: int = Field(default=0, ge=0)
    # Why each standard code became labels or an attribute, in the draft's language.
    notes: tuple[str, ...] = Field(default_factory=tuple[str, ...], max_length=50)
