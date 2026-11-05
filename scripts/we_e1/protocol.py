# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate local fake wire examples; this module has no transport or credentials."""

from __future__ import annotations

import math
import struct
from typing import Annotated, Literal

from pydantic import Field, model_validator

from scripts.we_e1.models import Boundary, Digest
from scripts.we_e1.preprocess import BATCH_LIMIT, ContractError, Prepared, sha256


class TextRequest(Boundary):
    """Freeze the text compatibility subset described by W-E, for fake use only."""

    model: Literal["text-embedding-v4"]
    input: Annotated[
        tuple[Annotated[str, Field(min_length=1)], ...],
        Field(min_length=1, max_length=BATCH_LIMIT),
    ]
    dimensions: Literal[64, 128, 256, 512, 768, 1024, 1536, 2048]
    encoding_format: Literal["float"]


class ImageInput(Boundary):
    """An internal experimental shape, with no asserted provider compatibility."""

    image: Annotated[str, Field(pattern=r"^data:image/png;base64,")]


class ImageRequest(Boundary):
    """Separate the image experiment from the official-compatible text subset."""

    model: Literal["multimodal-embedding-v1"]
    input: Annotated[tuple[ImageInput, ...], Field(min_length=1, max_length=BATCH_LIMIT)]


class Usage(Boundary):
    """Only total_tokens is assumed at the response boundary."""

    total_tokens: Annotated[int, Field(ge=0)]


class Embedding(Boundary):
    """Bind one finite nonzero embedding to a local batch index."""

    object: Literal["embedding"]
    index: Annotated[int, Field(ge=0)]
    embedding: Annotated[tuple[float, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def finite_nonzero(self) -> Embedding:
        """Forbid NaN, infinity, F32 overflow and vectors rounding entirely to zero."""
        try:
            packed = struct.pack(f"<{len(self.embedding)}f", *self.embedding)
        except (OverflowError, struct.error) as error:
            msg = "invalid_f32_embedding"
            raise ValueError(msg) from error
        rounded = struct.unpack(f"<{len(self.embedding)}f", packed)
        if not all(math.isfinite(value) for value in rounded) or not any(rounded):
            msg = "nonfinite_or_zero_embedding"
            raise ValueError(msg)
        return self


class Response(Boundary):
    """Require id, model, indexed embeddings and usage without invented fields."""

    id: Annotated[str, Field(min_length=1)]
    object: Literal["list"]
    model: Literal["text-embedding-v4", "multimodal-embedding-v1"]
    data: tuple[Embedding, ...]
    usage: Usage


class Mapping(Boundary):
    """Record local payload identity; no server-side body hash is claimed."""

    index: int
    payload_sha256: Digest
    vector_f32le_sha256: Digest


class WireExample(Boundary):
    """Freeze a complete fake envelope with real egress independently disabled."""

    mode: Literal["fake"]
    fake_implementation_version: Literal["we-e1-fake-v1"]
    url: Literal["https://embedding.example.invalid/v1/embeddings"]
    method: Literal["POST"]
    real_egress_enabled: Literal[False]
    real_budget_cny: Literal[0]
    text_request: TextRequest
    text_prepared: Prepared
    text_response: Response
    image_request: ImageRequest
    image_prepared: Prepared
    image_response: Response
    image_compatibility: Literal["experimental_internal_fake_only"]
    token_bound: Literal["fake-codepoint-v1_not_provider_compatible"]


def validate_response(
    response: Response, request: TextRequest | ImageRequest, payload_hashes: tuple[str, ...]
) -> tuple[Mapping, ...]:
    """Validate model, cardinality, permutation and dimensions before canonical bytes."""
    count = len(request.input)
    if response.model != request.model:
        msg = "response_model_mismatch"
        raise ContractError(msg)
    if len(response.data) != count or len(payload_hashes) != count:
        msg = "response_count_mismatch"
        raise ContractError(msg)
    if sorted(item.index for item in response.data) != list(range(count)):
        msg = "response_index_mismatch"
        raise ContractError(msg)
    dimension = request.dimensions if isinstance(request, TextRequest) else 1024
    if any(len(item.embedding) != dimension for item in response.data):
        msg = "response_dimension_mismatch"
        raise ContractError(msg)
    return tuple(
        Mapping(
            index=item.index,
            payload_sha256=payload_hashes[item.index],
            vector_f32le_sha256=sha256(struct.pack(f"<{dimension}f", *item.embedding)),
        )
        for item in sorted(response.data, key=lambda entry: entry.index)
    )
