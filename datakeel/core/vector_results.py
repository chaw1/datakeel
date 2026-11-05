# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Replayable F32 vector products and separate global comparison cache entries."""

import hashlib
import math
import struct
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from datakeel.core.models import AssetRef, BoundaryModel
from datakeel.core.vector_models import Digest, VectorAttempt, VectorCounts, vector_hash


class CosineMeasurement(BoundaryModel):
    """Record direct cosine similarity and the independent candidate threshold."""

    type: Literal["cosine_duplicate"] = "cosine_duplicate"
    similarity: float = Field(ge=-1, le=1, allow_inf_nan=False)
    threshold: float = Field(ge=-1, le=1, allow_inf_nan=False)


VectorMeasurement = Annotated[CosineMeasurement, Field(discriminator="type")]


class VectorNodeReport(BoundaryModel):
    """Distinguish invented fake usage and contract status from real quality or latency."""

    mode: Literal["fake"] = "fake"
    fake_version: Literal["we-e2-fake-v1"] = "we-e2-fake-v1"
    real_quality: Literal["not_tested"] = "not_tested"
    status: Literal["success", "partial_success", "failed"]
    reason: str | None = None
    counts: VectorCounts
    canonical_hash: Digest | None = None
    cache_hits: int = Field(default=0, ge=0)
    # Internal publication accounting; failed cache hits remain failures in the public totals.
    eligible_cache_hits: int = Field(default=0, ge=0, exclude=True)
    fake_requests: int = Field(default=0, ge=0)
    fake_usage: int = Field(default=0, ge=0)
    fake_cost_nanos: int = Field(default=0, ge=0)


class VectorTaskReport(BoundaryModel):
    """Expose terminal or pending status without representing a failed run as an empty success."""

    mode: Literal["fake"] = "fake"
    status: Literal["pending", "success", "partial_success", "failed", "cancelled"]
    reason: str | None = None
    nodes: tuple[VectorNodeReport, ...] = ()
    attempts: tuple[VectorAttempt, ...] = ()


class VectorInputStatus(BoundaryModel):
    """Expose a source's typed failure and synthetic provenance without substituting a vector."""

    mode: Literal["fake"] = "fake"
    fake_version: Literal["we-e2-fake-v1"] = "we-e2-fake-v1"
    status: Literal["eligible", "input_failed"]
    reason: str | None = None


class VectorSample(BoundaryModel):
    """Retain source bytes, input failures and F32 output without substitute vectors."""

    subject: AssetRef
    content_revision: Digest
    embedding_key: Digest
    vector: tuple[float, ...] = ()
    f32le_sha256: Digest | None = None
    prefix_only: Literal[False] = False
    warning: None = None
    failure: str | None = None
    temporary: bool = False

    @field_validator("vector")
    @classmethod
    def round_f32(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        """Use identical canonical F32 values for cosine, serialization and hashing."""
        try:
            return struct.unpack(f"<{len(value)}f", struct.pack(f"<{len(value)}f", *value))
        except (OverflowError, struct.error) as error:
            msg = "invalid_f32_embedding"
            raise ValueError(msg) from error

    @model_validator(mode="after")
    def finite(self) -> Self:
        """Require valid nonzero F32 output or an explicit failure, exclusively."""
        if self.failure is not None:
            valid = not self.vector
        else:
            try:
                rounded = struct.unpack(f"<{len(self.vector)}f", self.f32_bytes())
            except (OverflowError, struct.error) as error:
                msg = "invalid_f32_embedding"
                raise ValueError(msg) from error
            valid = bool(rounded) and any(rounded) and all(map(math.isfinite, rounded))
        if not valid or (
            self.f32le_sha256 is not None
            and self.f32le_sha256 != hashlib.sha256(self.f32_bytes()).hexdigest()
        ):
            msg = "nonfinite_zero_or_failed_vector"
            raise ValueError(msg)
        return self

    def f32_bytes(self) -> bytes:
        """Encode exactly the F32 little-endian bytes used in computation hashes."""
        return struct.pack(f"<{len(self.vector)}f", *self.vector)

    def canonical(self) -> str:
        """Include original content even when different originals yield equal vectors."""
        return vector_hash(
            {
                "asset": self.subject.model_dump(mode="json"),
                "content": self.content_revision,
                "key": self.embedding_key,
                "f32le": self.f32_bytes().hex(),
                "failure": self.failure,
                "temporary": self.temporary,
            }
        )


class VectorPair(BoundaryModel):
    """Record one canonical i<j pair, never a transitive relationship."""

    left: str
    right: str
    measurement: CosineMeasurement


class VectorCacheProduct(BoundaryModel):
    """Separate cache namespaces and retain immutable recorded outputs for rebuild."""

    key: Digest
    mode: Literal["fake", "recording", "real"] = "fake"
    implementation: str = "we-e2-fake-v1"
    contract: Literal["we-e2-cache-v1"] = "we-e2-cache-v1"
    kind: Literal["embedding", "global"]
    samples: tuple[VectorSample, ...]
    pairs: tuple[VectorPair, ...] = ()

    @model_validator(mode="after")
    def cacheable(self) -> Self:
        """Never cache temporary failures or create peer-dependent embedding entries."""
        if any(sample.temporary for sample in self.samples) or (
            self.kind == "embedding" and (len(self.samples) != 1 or self.pairs)
        ):
            msg = "uncacheable_vector_product"
            raise ValueError(msg)
        return self
