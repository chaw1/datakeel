# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cloud prelabel configuration, run accounting, IoU accuracy, confidence tiers and AI review."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, JsonValue, field_validator

from datakeel.core.models import BoundaryModel

ConfidenceTier = Literal["high", "medium", "low"]
ObjectKind = Literal["label_set", "box", "polygon", "span"]
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
_RESERVED_REQUEST_KEYS = frozenset(
    {"model", "messages", "max_tokens", "stream", "n", "api_key", "authorization"}
)


class CloudModelConfig(BoundaryModel):
    """Describe an OpenAI-compatible vision endpoint without ever holding its credential.

    Prices are per 1,000 tokens in the model's currency. ``credential_env`` names the
    environment variable that holds the key; the key itself is read only at call time.
    """

    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    credential_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,99}$")
    credential_source: Literal["env", "keychain"] = "env"
    input_price: float = Field(ge=0, allow_inf_nan=False)
    output_price: float = Field(ge=0, allow_inf_nan=False)
    coordinate_space: Literal["normalized_1000", "pixel"] = "normalized_1000"
    token_patch: int = Field(default=32, ge=1, le=256)
    max_image_side: int = Field(default=1280, ge=64, le=8192)
    prompt_tokens: int = Field(default=330, ge=0, le=100000)
    expected_output_tokens: int = Field(default=160, ge=1, le=32768)
    max_output_tokens: int = Field(default=2048, ge=16, le=32768)
    timeout_seconds: float = Field(default=60, gt=0, le=600)
    cross_check: bool = True
    confidence_source: Literal["self", "cross_check", "combined"] = "combined"
    request_parameters: dict[str, JsonValue] = Field(
        default_factory=lambda: {"enable_thinking": False}
    )

    @field_validator("base_url")
    @classmethod
    def safe_endpoint(cls, value: str) -> str:
        """Require HTTPS (plain HTTP only on loopback) and keep secrets out of the URL."""
        parts = urlsplit(value)
        secure = parts.scheme == "https" or (
            parts.scheme == "http" and (parts.hostname or "") in _LOOPBACK
        )
        if not secure or not parts.hostname or parts.username or parts.password:
            message = "Cloud endpoints must be https (http only on loopback) without credentials"
            raise ValueError(message)
        if parts.query or parts.fragment:
            message = "Cloud endpoints must not carry query strings or fragments"
            raise ValueError(message)
        return value.rstrip("/")

    @field_validator("request_parameters")
    @classmethod
    def no_reserved_keys(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """Keep request size, model identity and credentials under Datakeel's control."""
        reserved = sorted(_RESERVED_REQUEST_KEYS & {key.lower() for key in value})
        if reserved:
            message = f"request_parameters may not set {', '.join(reserved)}"
            raise ValueError(message)
        return value


class PrelabelCall(BoundaryModel):
    """Account for one provider request: tokens, cost and outcome, never its content."""

    sample_id: str
    view: Literal["primary", "mirrored"] = "primary"
    outcome: Literal["ok", "failed"]
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost: float = Field(default=0, ge=0, allow_inf_nan=False)
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)


class PrelabelDrop(BoundaryModel):
    """Explain one model object that was discarded instead of written."""

    sample_id: str
    reason: Literal["out_of_bounds", "degenerate", "unknown_label", "malformed"]
    detail: str = Field(default="", max_length=500)


class PrelabelStop(BoundaryModel):
    """Say where a budget-capped run stopped and what it had spent."""

    reason: Literal["budget"] = "budget"
    before_sample_id: str
    completed_images: int = Field(ge=0)
    remaining_images: int = Field(ge=0)
    spent: float = Field(ge=0, allow_inf_nan=False)
    budget: float = Field(ge=0, allow_inf_nan=False)
    next_image_estimate: float = Field(ge=0, allow_inf_nan=False)


class PrelabelEstimate(BoundaryModel):
    """Freeze the pre-execution cost estimate shown on the plan."""

    images: int = Field(ge=0)
    already_done: int = Field(default=0, ge=0)
    human_edited: int = Field(default=0, ge=0)
    calls_per_image: int = Field(default=1, ge=1)
    input_tokens_per_image: int = Field(default=0, ge=0)
    output_tokens_per_image: int = Field(default=0, ge=0)
    per_image: float = Field(ge=0, allow_inf_nan=False)
    total: float = Field(ge=0, allow_inf_nan=False)
    upper_bound: float = Field(ge=0, allow_inf_nan=False)
    currency: str
    observed_calls: int = Field(default=0, ge=0)


class TierRate(BoundaryModel):
    """Measured hit rate of reviewed model objects that fall in one tier."""

    tier: ConfidenceTier
    objects: int = Field(ge=0)
    hits: int = Field(ge=0)
    rate: float | None = Field(default=None, ge=0, le=1)


class CalibrationSegment(BoundaryModel):
    """One flat piece of the isotonic confidence-to-hit-rate curve over reviewed objects."""

    low: float = Field(ge=0, le=1)
    high: float = Field(ge=0, le=1)
    objects: int = Field(ge=1)
    hits: int = Field(ge=0)
    rate: float = Field(ge=0, le=1)


class ConfidenceThresholds(BoundaryModel):
    """Effective tier thresholds and the reviewed evidence they were derived from.

    An object is high when confidence >= ``high`` and low when confidence < ``low``;
    ``None`` means that tier is not used. A task takes its lowest object tier, and a
    model draft without objects is low.
    """

    high: float | None = Field(default=None, ge=0, le=1)
    low: float | None = Field(default=None, ge=0, le=1)
    source: Literal["configured", "calibrated", "default"]
    objects: int = Field(default=0, ge=0)
    minimum_objects: int = Field(default=30, ge=1)
    notes: tuple[
        Literal["insufficient_samples", "no_high_threshold", "no_low_threshold", "low_capped"],
        ...,
    ] = ()
    tiers: tuple[TierRate, ...] = ()
    segments: tuple[CalibrationSegment, ...] = ()
    pass_through: bool = Field(
        default=True,
        description="False while defaults stand in for measured thresholds: high stays a draft.",
    )


class TaskTier(BoundaryModel):
    """Record the tier one task received when its model draft was written."""

    task_id: str
    sample_id: str
    tier: ConfidenceTier
    routed: Literal["hint", "submitted", "draft", "scratch"]
    note: Literal["", "insufficient_samples"] = ""
    revision_id: str | None = None


class IoUAccuracy(BoundaryModel):
    """Object-level precision, recall and F1 at one IoU threshold, plus all-hit tasks."""

    threshold: float = Field(gt=0, le=1)
    model_objects: int = Field(ge=0)
    human_objects: int = Field(ge=0)
    true_positives: int = Field(ge=0)
    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)
    f1: float | None = Field(default=None, ge=0, le=1)
    all_hit_tasks: int = Field(default=0, ge=0)
    all_hit_rate: float | None = Field(default=None, ge=0, le=1)


class AttributeAgreement(BoundaryModel):
    """Share of IoU >= 0.5 matched objects whose attributes are identical."""

    matched_objects: int = Field(ge=0)
    consistent_objects: int = Field(ge=0)
    rate: float | None = Field(default=None, ge=0, le=1)


class ModelSpend(BoundaryModel):
    """Total measured prelabel spend of one model on one project."""

    model_id: str
    model_name: str
    model_version: str
    currency: str
    runs: int = Field(ge=0)
    images: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost: float = Field(ge=0, allow_inf_nan=False)


class ObjectRef(BoundaryModel):
    """Point at one object of a revision so a reviewer can jump to it."""

    kind: ObjectKind
    index: int = Field(ge=0)


class RiskReason(BoundaryModel):
    """One rule hit that contributed to an AI pre-review risk score."""

    code: str = Field(min_length=1, max_length=100)
    weight: float = Field(ge=0, le=1)
    message: str = Field(max_length=2000)
    message_zh: str = Field(default="", max_length=2000)
    evidence: tuple[str, ...] = ()
    objects: tuple[ObjectRef, ...] = ()


class AIReview(BoundaryModel):
    """Immutable AI pre-review of one submitted revision and its review-sampling decision."""

    id: str
    project_id: str
    task_id: str
    revision_id: str
    round: int = Field(ge=0)
    risk: float = Field(ge=0, le=1)
    high_risk: bool
    reasons: tuple[RiskReason, ...] = ()
    sample_rate: float = Field(gt=0, le=1)
    draw: float = Field(ge=0, lt=1)
    decision: Literal["review", "exempt", "personal"]
    note: str = ""
    created_at: datetime


class PrelabelProgress(BoundaryModel):
    """Where a cloud prelabel run stands: images done and failed, money spent, last update."""

    run_id: str
    model_id: str
    model_name: str
    model_version: str
    status: Literal["running", "completed", "failed", "abandoned"]
    planned_images: int = Field(ge=0)
    completed_images: int = Field(ge=0)
    failed_images: int = Field(ge=0)
    spent: float = Field(ge=0, allow_inf_nan=False)
    budget: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str | None = None
    stopped: bool = False
    started_at: datetime
    updated_at: datetime | None = None
