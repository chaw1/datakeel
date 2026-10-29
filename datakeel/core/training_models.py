# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Version-owned reproducible training partitions and measured leakage evidence."""

import math
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import BoundaryModel, FileItem

type SplitName = Literal["train", "val", "test"]
type LeakageKind = Literal["exact", "image", "text", "group"]


class SplitRatios(BoundaryModel):
    """Select two or three nonempty partitions with normalized finite proportions."""

    train: float = Field(default=0.8, gt=0, le=1, allow_inf_nan=False)
    val: float = Field(default=0.1, ge=0, le=1, allow_inf_nan=False)
    test: float = Field(default=0.1, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def normalized(self) -> Self:
        """Reject ambiguous totals instead of silently changing requested proportions."""
        if not math.isclose(self.train + self.val + self.test, 1, abs_tol=1e-9):
            message = "Training split ratios must sum to one"
            raise ValueError(message)
        if self.val == 0 and self.test == 0:
            message = "Training splits require at least two positive ratios"
            raise ValueError(message)
        return self


class SplitRequest(BoundaryModel):
    """Freeze the complete versioned partition policy, including comparison thresholds."""

    name: str = Field(min_length=1, max_length=200, pattern=r"\S")
    ratios: SplitRatios = Field(default_factory=SplitRatios)
    seed: int = 42
    stratify: bool = Field(
        default=True,
        description="Use every label in iterative multilabel stratification.",
    )
    group_field: str | None = Field(default=None, min_length=1, max_length=200)
    avoid_leakage: bool = True
    image_threshold: int = Field(default=8, ge=0, le=64)
    text_threshold: int = Field(
        default=3, ge=0, le=64, description="Maximum 64-bit text simhash Hamming distance."
    )
    source: Literal["generated", "directory"] = "generated"


class TrainingSample(BoundaryModel):
    """Carry materialized local facts internally; never use this model as an HTTP response."""

    file: FileItem
    annotations: tuple[AnnotationRecord, ...] = ()
    labels: tuple[str, ...] = ()
    group: str | None = None
    image_hash: int | None = Field(default=None, ge=0, lt=1 << 64)
    image_uniform: bool = False
    image_color: tuple[int, int, int] | None = None
    text_hash: int | None = Field(
        default=None,
        ge=0,
        lt=1 << 64,
        description="64-bit simhash of normalized text; absent for empty normalized content.",
    )


class SplitMember(BoundaryModel):
    """Freeze assignment, original content identity and annotation revision together."""

    sample_id: str
    split: SplitName
    labels: tuple[str, ...] = ()
    annotations: tuple[AnnotationRecord, ...] = ()
    sha256: str


class LabelCount(BoundaryModel):
    """Count samples carrying a category, counting each category once per sample."""

    label: str
    count: int = Field(ge=0)


class SplitDistribution(BoundaryModel):
    """Report membership and multilabel category prevalence for one partition."""

    split: SplitName
    count: int = Field(ge=0)
    labels: tuple[LabelCount, ...] = ()


class SplitSet(BoundaryModel):
    """Expose an immutable named partition belonging to exactly one source version."""

    id: str
    dataset_id: str
    version_id: str
    request: SplitRequest
    members: tuple[SplitMember, ...]
    distributions: tuple[SplitDistribution, ...]
    created_at: AwareDatetime
    algorithm_version: str = "1.0"


class LeakagePair(BoundaryModel):
    """Describe one direct cross-partition match and the measured signal distance."""

    kind: LeakageKind
    left_id: str
    right_id: str
    left_split: SplitName
    right_split: SplitName
    distance: int = Field(ge=0, le=64)
    detail: str


class LeakageReport(BoundaryModel):
    """Return direct pair evidence without merging transitive neighbors into false pairs."""

    split_set_id: str
    dataset_id: str
    version_id: str
    sample_count: int = Field(ge=0)
    checked_signals: tuple[LeakageKind, ...] = ("exact", "image", "text", "group")
    pairs: tuple[LeakagePair, ...]


class SplitComparison(BoundaryModel):
    """Compare two immutable partition memberships from the same source version."""

    left_id: str
    right_id: str
    changed_sample_ids: tuple[str, ...]
    left: tuple[SplitDistribution, ...]
    right: tuple[SplitDistribution, ...]
