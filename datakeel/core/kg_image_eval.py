# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validated synthetic and external image benchmark cases."""

from typing import Literal

from pydantic import Field

from datakeel.core.kg_eval_models import KGCase
from datakeel.core.models import BoundaryModel


class KGImageCase(KGCase):
    """Bind independent labels to a relative image and optional byte-level provenance."""

    text: str = ""
    group: Literal["A_clean", "A_scan", "B"] = "B"
    image: str = Field(min_length=1)
    image_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    expected_route: Literal["ocr", "vlm"] | None = None


class KGImageSuite(BoundaryModel):
    """Describe an image directory with a cases.yaml label manifest."""

    id: str = Field(min_length=1)
    version: str = "1.0"
    cases: tuple[KGImageCase, ...] = Field(min_length=1)
