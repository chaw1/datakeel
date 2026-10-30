# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Inputs a label-set draft may read and the checked outcome it produces."""

from typing import Literal

from pydantic import Field

from datakeel.core.label_guidelines import LabelGuidelines
from datakeel.core.models import BoundaryModel
from datakeel.core.production_catalog_models import ProductionLabel


class CategorySource(BoundaryModel):
    """One category from a data standard code list or an existing vocabulary."""

    key: str
    name_zh: str
    name_en: str = ""
    parent_key: str | None = None
    description: str = ""
    origin: Literal["standard", "annotation"] = "standard"


class AttributeSource(BoundaryModel):
    """A standard field that becomes an attribute rather than a category."""

    key: str
    name_zh: str
    name_en: str
    data_type: str = "text"
    options: tuple[tuple[str, str, str], ...] = ()
    required: bool = False
    # The category subtree this property belongs to; None puts it on every label.
    scope: str | None = None


class SampleSource(BoundaryModel):
    """One sampled file with what the model may see of it."""

    id: str
    filename: str
    modality: str = "unknown"
    text: str = ""
    image_data_url: str | None = None
    labels: tuple[str, ...] = ()


class DraftInputs(BoundaryModel):
    """Everything one draft reads, gathered and bounded before any model call."""

    name: str
    topic: str = ""
    language: Literal["zh", "en"] = "zh"
    categories: tuple[CategorySource, ...] = ()
    attributes: tuple[AttributeSource, ...] = ()
    samples: tuple[SampleSource, ...] = ()


class DraftOutcome(BoundaryModel):
    """A checked label tree and guidelines, with usage of the model that wrote them."""

    labels: tuple[ProductionLabel, ...] = Field(min_length=1)
    guidelines: LabelGuidelines
    model: str = "offline-rules"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0
    dropped_examples: int = 0
