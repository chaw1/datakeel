# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed relative reference selection, kept outside the dependency-free core."""

from pydantic import Field

from datakeel.core.vector_models import DuplicateParams
from datakeel.ontology.models import ObjectSet


class CoverageParams(DuplicateParams):
    """Resolve an entire file ObjectSet; its display limit never truncates references."""

    reference: ObjectSet
    max_reference_comparisons: int = Field(default=250000, ge=0, le=250000)
