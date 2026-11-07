# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen offline workload and evidence contracts; no product configuration changes."""

from typing import Literal, Self

from pydantic import Field, model_validator

from datakeel.core.models import BoundaryModel

MAX_SAMPLES = 5000
MAX_COMPARISONS = 250000


class Workload(BoundaryModel):
    """Declare every generated workload choice before any measured execution."""

    contract: Literal["we-e5-v1"] = "we-e5-v1"
    seed: int = 20261107
    fixture_created_at: Literal[0] = 0
    assets: int = Field(default=24, ge=4, le=5000)
    dimensions: Literal[64, 128, 256, 512, 768, 1024, 1536, 2048] = 64
    prefix: int = Field(default=64, ge=1)
    duplicate_group_size: int = Field(default=3, ge=2)
    noise_assets: int = Field(default=3, ge=0)
    reference_groups: int = Field(default=2, ge=1)
    duplicate_threshold: float = Field(default=0.98, ge=-1, le=1, allow_inf_nan=False)
    eps: float = Field(default=0.02, ge=0, le=2, allow_inf_nan=False)
    min_samples: int = Field(default=2, ge=1, le=5000)
    gap_threshold: float = Field(default=0.98, ge=-1, le=1, allow_inf_nan=False)
    repetitions: int = Field(default=3, ge=1, le=20)
    order: Literal["asset_id_ascending"] = "asset_id_ascending"
    phases: tuple[Literal["cold", "hot", "incremental"], ...] = ("cold", "hot", "incremental")
    workers: Literal[1] = 1
    prefix_policy: Literal["numeric_coordinates_only_worker_text_is_unmodified"] = (
        "numeric_coordinates_only_worker_text_is_unmodified"
    )
    incremental_policy: Literal["replace_target_00000_only_new_source_version"] = (
        "replace_target_00000_only_new_source_version"
    )

    @model_validator(mode="after")
    def bounded(self) -> Self:
        """Refuse workloads outside the existing complete-comparison capacity contract."""
        groups = (self.assets - self.noise_assets) // self.duplicate_group_size
        if (
            self.assets + self.reference_groups > MAX_SAMPLES
            or self.assets * (self.assets - 1) // 2 > MAX_COMPARISONS
            or self.assets * self.reference_groups > MAX_COMPARISONS
            or self.noise_assets >= self.assets
            or self.reference_groups > groups
            or self.prefix > self.dimensions
            or self.phases != ("cold", "hot", "incremental")
        ):
            msg = "invalid_or_over_capacity_workload"
            raise ValueError(msg)
        return self


class Point(BoundaryModel):
    """Carry one generated vector, with stable public synthetic identity."""

    asset_id: str
    values: tuple[float, ...]


class NumericInput(BoundaryModel):
    """Accept only explicitly supplied generated points, never discover input directories."""

    points: tuple[Point, ...]
    targets: tuple[str, ...]
    references: tuple[str, ...]
    prefix: int
    threshold: float = Field(ge=-1, le=1, allow_inf_nan=False)
    eps: float = Field(ge=0, le=2, allow_inf_nan=False)
    min_samples: int = Field(ge=1, le=5000)
    gap_threshold: float = Field(ge=-1, le=1, allow_inf_nan=False)
    duplicate_gold: tuple[str, ...] | None = None
    cluster_gold: tuple[int, ...] | None = None
    gap_gold: tuple[str, ...] | None = None

    @model_validator(mode="after")
    def ordered_scope(self) -> Self:
        """Bind gold alignment to a stable, duplicate-free target and reference enumeration."""
        for ids in (self.targets, self.references):
            if ids != tuple(sorted(set(ids))):
                msg = "scope_requires_sorted_unique_asset_ids"
                raise ValueError(msg)
        if self.gap_gold is not None and not self.references:
            msg = "gap_gold_requires_reference_support"
            raise ValueError(msg)
        return self


class BackendResult(BoundaryModel):
    """Retain exact decisions, including greedy representative and nearest-reference ties."""

    pairs: tuple[tuple[str, str], ...]
    removed: tuple[str, ...]
    representatives: tuple[tuple[str, str], ...]
    labels: tuple[int, ...]
    noise: tuple[str, ...]
    gaps: tuple[tuple[str, str], ...]
    reduction: float


class Score(BoundaryModel):
    """Keep denominators beside precision/recall/F1, including empty-set conventions."""

    precision: float
    recall: float
    f1: float
    true_positive: int
    predicted: int
    expected: int


class Quality(BoundaryModel):
    """Separate synthetic contract metrics from unmeasured encoder quality."""

    gold_kind: Literal["synthetic_contract_only", "not_available"]
    removal: Score | Literal["not_available"]
    survival: float | Literal["not_available"]
    exactly_one: float | Literal["not_available"]
    direct_pair: Score | Literal["not_available"]
    ari: float | Literal["not_available"]
    nmi: float | Literal["not_available"]
    noise: Score | Literal["not_available"]
    gap: Score | Literal["not_available"]


class RecordedFacts(BoundaryModel):
    """Read committed direct facts without UUIDs, human overlays or synthesized transitive edges."""

    pairs: tuple[tuple[str, str], ...]
    clusters: tuple[tuple[str, ...], ...]
    noise: tuple[str, ...]
    gaps: tuple[tuple[str, str], ...]
