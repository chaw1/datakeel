# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compose cache identities from complete extraction semantics."""

import hashlib
import json

from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.kg_cache import KGCacheKey
from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
from datakeel.core.kg_models import TextBlock
from datakeel.core.models import BoundaryModel
from datakeel.kg.prompt import PROMPT_VERSION


def content_hash(model: BoundaryModel) -> str:
    """Hash validated model content in a canonical field order."""
    return hashlib.sha256(
        json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_cache_key(
    block: TextBlock,
    schema: KGSchema,
    profile: ExtractionProfile,
    extractor: ExtractorRef,
    recording_hash: str | None = None,
) -> KGCacheKey:
    """Bind content to schema, prompt, model, parameters, chunking and replay bytes."""
    configuration = profile.model_dump(mode="json", exclude={"id", "recording", "api_key_env"})
    configuration["model"] = profile.model
    configuration["recording_hash"] = recording_hash
    profile_hash = hashlib.sha256(
        json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return KGCacheKey(
        text_hash=block.content_hash,
        schema_hash=content_hash(schema),
        prompt_version=PROMPT_VERSION
        if profile.prompt_version == "text-kg-v3"
        else profile.prompt_version,
        profile_hash=profile_hash,
        chunk_size=profile.chunk_size,
        chunk_overlap=profile.chunk_overlap,
        extractor=extractor,
    )


def extraction_identity(
    schema: KGSchema, profile: ExtractionProfile, recording_hash: str | None = None
) -> ExtractorRef:
    """Version provenance by all semantic inputs so schema changes invalidate old claims."""
    base = ExtractorRef(id="evidence.kg", version="1")
    key = build_cache_key(TextBlock(text="", start=0, end=0), schema, profile, base, recording_hash)
    return base.model_copy(update={"version": f"1:{key.digest()}"})
