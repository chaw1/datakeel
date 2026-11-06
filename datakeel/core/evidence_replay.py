# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed declaration of replay fact sources and their composite durable watermark."""

from typing import Literal

from datakeel.core.models import BoundaryModel
from datakeel.core.vector_models import Digest, vector_hash


class EvidenceWatermark(BoundaryModel):
    """Bind immutable extraction facts and append-only decisions as separate sources."""

    bundles: Digest
    decisions: Digest

    def digest(self) -> str:
        """Combine both source watermarks without using a clock or a projection cache."""
        return vector_hash(self.model_dump(mode="json"))


class EvidenceProjector(BoundaryModel):
    """Declare the rebuild contract without changing the persistence schema registry."""

    name: Literal["evidence"] = "evidence"
    version: Literal["1.3"] = "1.3"
    fact_sources: tuple[str, ...] = (
        "lineage_events:COMPLETE:knowledge_bundle",
        "assertion_decisions",
    )
    outputs: tuple[str, ...] = ("assertions", "evidence_cache", "vector_cache")
    network: Literal[False] = False


EVIDENCE_PROJECTOR = EvidenceProjector()
