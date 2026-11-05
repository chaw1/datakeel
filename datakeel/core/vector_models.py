# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen fake vector plans, accounting limits and explicit execution identities."""

import hashlib
import json
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, field_validator, model_validator

from datakeel.core.errors import ExecutionError
from datakeel.core.models import BoundaryModel
from datakeel.core.settings import get_settings

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
VECTOR_OPERATORS = frozenset({"evidence.vector_embed", "evidence.semantic_duplicate"})


def vector_hash(value: object) -> str:
    """Hash canonical JSON without timestamps, locations or nonfinite numbers."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


class VectorCounts(BoundaryModel):
    """Account for all inputs identically during cold, hot and recovery runs."""

    input: int = Field(ge=0)
    eligible: int = Field(ge=0)
    failed: int = Field(ge=0)
    truncated: Literal[0] = 0

    @model_validator(mode="after")
    def complete(self) -> Self:
        """Keep unknown or failed inputs distinct from valid empty comparisons."""
        if self.failed + self.eligible != self.input:
            msg = "vector_count_mismatch"
            raise ValueError(msg)
        return self


class VectorError(ExecutionError):
    """Expose a safe typed reason without request bodies or provider messages."""

    def __init__(self, reason: str, counts: VectorCounts | None = None) -> None:
        """Retain only a stable reason suitable for tasks and action receipts."""
        self.reason = reason
        self.counts = counts
        super().__init__(reason)


def require_local_vector_objects() -> None:
    """Refuse remote object materialization before constructing any storage client."""
    if get_settings().s3_bucket is not None:
        msg = "vector_fake_requires_local_objects"
        raise VectorError(msg)


class VectorPolicy(BoundaryModel):
    """Freeze invented CNY accounting units, never provider prices or real consent."""

    currency: Literal["CNY"] = "CNY"
    price_version: Literal["fake-price-v1"] = "fake-price-v1"
    nanos_per_token: int = Field(default=1, ge=0, strict=True)
    image_tokens: int = Field(default=100, gt=0, strict=True)
    max_requests: int = Field(default=5000, ge=0, strict=True)
    max_cost_nanos: int = Field(default=100000000, ge=0, strict=True)
    real_budget_cny: Literal[0] = 0
    real_egress_enabled: Literal[False] = False


class EmbedParams(BoundaryModel):
    """Allow only the versioned fake contract and a frozen reserved HTTPS URL."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    mode: Literal["fake"] = "fake"
    fake_version: Literal["we-e2-fake-v1"] = "we-e2-fake-v1"
    contract: Literal["we-e1-v1"] = "we-e1-v1"
    endpoint: str = "https://embedding.example.invalid/v1/embeddings"
    modality: Literal["text", "image"] = "text"
    dimensions: Literal[64, 128, 256, 512, 768, 1024, 1536, 2048] = 64
    tokenizer: Literal["fake-codepoint-v1"] = "fake-codepoint-v1"
    policy: VectorPolicy = Field(default_factory=VectorPolicy)

    @field_validator("endpoint")
    @classmethod
    def reserved_https(cls, value: str) -> str:
        """Reject credentials, query strings, fragments and nonfixture destinations."""
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.hostname.endswith((".invalid", ".test"))
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not parsed.path.endswith("/embeddings")
            or parsed.port is not None
        ):
            msg = "fake_endpoint_required"
            raise ValueError(msg)
        return value


class DuplicateParams(BoundaryModel):
    """Bound exact direct-pair comparisons without connected-component closure."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)
    threshold: float = Field(default=0.9, ge=-1, le=1)
    max_samples: int = Field(default=5000, ge=1, le=5000)
    max_candidate_pairs: int = Field(default=250000, ge=0, le=250000)


class FrozenPayload(BoundaryModel):
    """Bind one possible branch input to original bytes and final request bytes."""

    asset_id: str
    content_revision: Digest
    payload_hash: Digest | None = None
    body_hash: Digest | None = None
    preprocessing: str
    token_bound: int = Field(ge=0)
    failure: str | None = None
    cache_key: Digest


class FrozenVectorNode(BoundaryModel):
    """Freeze all possible conditional inputs, including inactive branches."""

    node_id: str
    params: EmbedParams
    inputs: tuple[FrozenPayload, ...]
    actual_asset_ids: tuple[str, ...]


class FrozenVectorSelection(BoundaryModel):
    """Bind exact branch membership and its embedding source for one set computation."""

    node_id: str
    embedding_node: str
    actual_asset_ids: tuple[str, ...]


class VectorPrepared(BoundaryModel):
    """Bind complete resolved DAG, endpoints, payloads and worst fake reservation."""

    contract: Literal["we-e2-plan-v1"] = "we-e2-plan-v1"
    dag_hash: Digest
    nodes: tuple[FrozenVectorNode, ...]
    selections: tuple[FrozenVectorSelection, ...]
    worst_requests: int
    worst_cost_nanos: int


class VectorPermit(BoundaryModel):
    """Identify the consumed approval and live fenced worker at every send."""

    plan_id: str
    plan_digest: Digest
    run_id: str
    task_id: str
    shard_id: str
    owner: str
    version_id: str = Field(min_length=1)


class VectorAttempt(BoundaryModel):
    """Expose durable accounting without leaking storage rows or raw payloads."""

    id: str
    state: Literal["RESERVED", "SENDING", "UNKNOWN", "SETTLED", "REFUNDED"]
    token_bound: int
    reserved_nanos: int
    usage: int | None = None
    response_id: str | None = None
    reason: str | None = None
