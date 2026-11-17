# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen fake vector plans, accounting limits and explicit execution identities."""

import hashlib
import ipaddress
import json
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, model_validator

from datakeel.core.errors import ExecutionError
from datakeel.core.models import AssetRef, BoundaryModel, FileItem
from datakeel.core.settings import get_settings

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
VectorMode = Literal["fake", "real"]
VectorImpl = Literal["we-e2-fake-v1", "we-cloud-http-v1"]
EmbeddingModel = Literal[
    "text-embedding-v4",
    "text-embedding-v3",
    "text-embedding-3-small",
    "text-embedding-3-large",
    "multimodal-embedding-v1",
]
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_RESERVED_SUFFIXES = (".invalid", ".test", ".example", ".localhost")
VECTOR_OPERATORS = frozenset(
    {
        "evidence.vector_embed",
        "evidence.semantic_duplicate",
        "evidence.semantic_cluster",
        "evidence.semantic_outlier",
        "evidence.coverage_gap",
    }
)


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
    """Freeze CNY nano-accounting bounds and explicit cloud egress consent."""

    currency: Literal["CNY"] = "CNY"
    price_version: Literal["fake-price-v1", "cloud-price-v1"] = "fake-price-v1"
    nanos_per_token: int = Field(default=1, ge=0, strict=True)
    image_tokens: int = Field(default=100, gt=0, strict=True)
    max_requests: int = Field(default=5000, ge=0, strict=True)
    max_cost_nanos: int = Field(default=100000000, ge=0, strict=True)
    real_budget_cny: (
        Annotated[int, Field(ge=0, strict=True)]
        | Annotated[float, Field(ge=0, strict=True, allow_inf_nan=False)]
    ) = 0
    real_egress_enabled: Annotated[bool, Field(strict=True)] = False


def _valid_real_endpoint(scheme: str, host: str) -> bool:
    if host in _LOOPBACK_HOSTS:
        return scheme in {"http", "https"}
    if scheme != "https" or host.endswith(_RESERVED_SUFFIXES):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


class EmbedParams(BoundaryModel):
    """Bind either the deterministic fake contract or an explicit cloud HTTP embedding profile."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    mode: VectorMode = "fake"
    fake_version: VectorImpl = "we-e2-fake-v1"
    contract: Literal["we-e1-v1"] = "we-e1-v1"
    endpoint: str = "https://embedding.example.invalid/v1/embeddings"
    modality: Literal["text", "image"] = "text"
    dimensions: Literal[64, 128, 256, 512, 768, 1024, 1536, 2048] = 64
    tokenizer: Literal["fake-codepoint-v1", "utf8-byte-bound-v1"] = "fake-codepoint-v1"
    model: EmbeddingModel | None = Field(default=None, exclude_if=lambda value: value is None)
    credential_env: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{1,127}$",
        exclude_if=lambda value: value is None,
    )
    policy: VectorPolicy = Field(default_factory=VectorPolicy)

    def effective_model(self) -> EmbeddingModel:
        """Resolve the wire model identifier without altering fake-mode defaults."""
        if self.model is not None:
            return self.model
        return "text-embedding-v4" if self.modality == "text" else "multimodal-embedding-v1"

    @model_validator(mode="after")
    def mode_and_endpoint_contract(self) -> Self:
        """Keep fake mode isolated and require explicit consent and bounds for real mode."""
        parsed = urlsplit(self.endpoint)
        host = (parsed.hostname or "").lower()
        clean_url = bool(
            host
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.path.endswith("/embeddings")
        )
        if self.mode == "fake":
            if (
                not clean_url
                or parsed.scheme != "https"
                or not host.endswith((".invalid", ".test"))
                or parsed.port is not None
            ):
                msg = "fake_endpoint_required"
                raise ValueError(msg)
            if (
                self.fake_version != "we-e2-fake-v1"
                or self.tokenizer != "fake-codepoint-v1"
                or self.model is not None
                or self.credential_env is not None
                or self.policy.real_egress_enabled
                or self.policy.real_budget_cny != 0
                or self.policy.price_version != "fake-price-v1"
            ):
                msg = "fake_mode_forbids_real_settings"
                raise ValueError(msg)
            return self
        if not clean_url or not _valid_real_endpoint(parsed.scheme, host):
            msg = "real_endpoint_invalid"
            raise ValueError(msg)
        if host not in _LOOPBACK_HOSTS and self.credential_env is None:
            msg = "real_endpoint_requires_credential_env"
            raise ValueError(msg)
        if (
            self.fake_version != "we-cloud-http-v1"
            or self.tokenizer != "utf8-byte-bound-v1"
            or self.model is None
            or (self.model == "multimodal-embedding-v1") != (self.modality == "image")
        ):
            msg = "real_embedding_profile_invalid"
            raise ValueError(msg)
        if (
            not self.policy.real_egress_enabled
            or self.policy.price_version != "cloud-price-v1"
            or self.policy.real_budget_cny <= 0
            or round(self.policy.real_budget_cny * 1_000_000_000) != self.policy.max_cost_nanos
        ):
            msg = "real_budget_policy_invalid"
            raise ValueError(msg)
        return self


class DuplicateParams(BoundaryModel):
    """Bound exact direct-pair comparisons without connected-component closure."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)
    threshold: float = Field(default=0.9, ge=-1, le=1)
    max_samples: int = Field(default=5000, ge=1, le=5000)
    max_candidate_pairs: int = Field(default=250000, ge=0, le=250000)


class ClusterParams(DuplicateParams):
    """Bound exact precomputed cosine-distance DBSCAN, including self in density."""

    eps: float = Field(default=0.1, ge=0, le=2)
    min_samples: int = Field(default=5, ge=1, le=5000, strict=True)


class VectorMember(BoundaryModel):
    """Freeze versioned identity, source revision, state and original byte hash."""

    subject: AssetRef
    revision: str
    state_revision: int = 0
    content_revision: Digest


class VectorScope(BoundaryModel):
    """Keep complete target and reference closures independently of a query limit."""

    targets: tuple[VectorMember, ...]
    references: tuple[VectorMember, ...]
    target_digest: Digest | None = None
    reference_digest: Digest | None = None

    @model_validator(mode="after")
    def summaries(self) -> Self:
        """Derive immutable summaries once and reject tampered or unordered closures."""
        for name, members in (
            ("target_digest", self.targets),
            ("reference_digest", self.references),
        ):
            ids = tuple(m.subject.asset_id for m in members)
            if ids != tuple(sorted(set(ids))) or any(
                m.subject.asset_type != "file" or not m.subject.version for m in members
            ):
                msg = "vector_scope_requires_sorted_versioned_files"
                raise ValueError(msg)
            digest = vector_hash([m.model_dump(mode="json") for m in members])
            if getattr(self, name) not in (None, digest):
                msg = "vector_scope_summary_mismatch"
                raise ValueError(msg)
            object.__setattr__(self, name, digest)
        return self

    def digest(self) -> str:
        """Bind all memberships and revisions, including references never chosen as nearest."""
        return vector_hash(self.model_dump(mode="json"))


class VectorReferenceSet(BoundaryModel):
    """Pass resolved reference files and frozen source facts through a typed internal port."""

    node_id: str
    files: tuple[FileItem, ...]
    members: tuple[VectorMember, ...]


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
    subject: AssetRef | None = Field(default=None, exclude_if=lambda value: value is None)


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
    scope: VectorScope | None = Field(default=None, exclude_if=lambda value: value is None)


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
