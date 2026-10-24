# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent content cache identity for graph extraction."""

import hashlib
import json

from datakeel.core.evidence_models import ContentRevision, ExtractorRef
from datakeel.core.models import BoundaryModel


class KGCacheKey(BoundaryModel):
    """Include all extraction inputs and omit mutable document paths."""

    text_hash: ContentRevision
    schema_hash: ContentRevision
    prompt_version: str
    profile_hash: ContentRevision
    chunk_size: int
    chunk_overlap: int
    extractor: ExtractorRef

    def digest(self) -> str:
        """Hash the canonical JSON representation for stable storage lookup."""
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
