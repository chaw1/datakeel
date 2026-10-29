# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed offline image prediction parsing inputs and partial-success outputs."""

from pydantic import Field

from datakeel.core.models import BoundaryModel
from datakeel.core.production_catalog_models import ParsedPrediction, PredictionFailure


class PredictionSample(BoundaryModel):
    """Bind an immutable task sample to its original filename and image dimensions."""

    id: str
    filename: str
    width: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    height: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class PredictionParseResult(BoundaryModel):
    """Return independent successes and failures from one uploaded source document."""

    predictions: tuple[ParsedPrediction, ...] = ()
    failures: tuple[PredictionFailure, ...] = ()
