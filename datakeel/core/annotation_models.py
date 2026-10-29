# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen annotation review inputs, deterministic metrics and repair evidence."""

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from datakeel.core.models import BoundaryModel


class AnnotationBox(BoundaryModel):
    """Preserve an xyxy box, including invalid coordinates for rule review."""

    category: str
    x1: float = Field(allow_inf_nan=False)
    y1: float = Field(allow_inf_nan=False)
    x2: float = Field(allow_inf_nan=False)
    y2: float = Field(allow_inf_nan=False)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class AnnotationSpan(BoundaryModel):
    """Preserve a half-open character span for agreement and boundary review."""

    category: str
    start: int
    end: int
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class AnnotationPoint(BoundaryModel):
    """Keep one finite source-image pixel coordinate in a polygon."""

    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class AnnotationPolygon(BoundaryModel):
    """Preserve a closed polygon without duplicating its first vertex at the end."""

    category: str
    points: tuple[AnnotationPoint, ...] = Field(min_length=3)
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class AnnotationRecord(BoundaryModel):
    """Describe one annotator's work; None is missing and an empty tuple is reviewed empty."""

    sample_id: str = Field(min_length=1)
    annotator_id: str = Field(min_length=1)
    labels: tuple[str, ...] | None = None
    boxes: tuple[AnnotationBox, ...] | None = None
    spans: tuple[AnnotationSpan, ...] | None = None
    polygons: tuple[AnnotationPolygon, ...] | None = None
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    text_length: int | None = Field(default=None, ge=0)
    image_width: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    image_height: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class NearDuplicatePair(BoundaryModel):
    """Identify a reviewed or computed near-duplicate relation, not a proven error."""

    sample_id: str = Field(min_length=1)
    other_sample_id: str = Field(min_length=1)
    similarity: float = Field(default=1, ge=0, le=1)


class OutlierPolicy(BoundaryModel):
    """Tune the robust size, aspect-ratio and span-length outlier rules of one batch.

    Defaults: modified z above 3.5 (above 5 when another annotator drew a matching
    item), at least 4x area or 3x aspect-ratio / span-length deviation from the
    category median, cohorts of at least ten items, and a cohort where more than
    10% would be flagged is treated as multimodal and skipped.
    """

    modified_z: float = Field(default=3.5, gt=0, allow_inf_nan=False)
    corroborated_z: float = Field(default=5.0, gt=0, allow_inf_nan=False)
    area_factor: float = Field(default=4.0, gt=1, allow_inf_nan=False)
    aspect_factor: float = Field(default=3.0, gt=1, allow_inf_nan=False)
    span_length_factor: float = Field(default=3.0, gt=1, allow_inf_nan=False)
    min_cohort: int = Field(default=10, ge=3)
    max_flagged_share: float = Field(default=0.1, gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def corroboration_is_stricter(self) -> "OutlierPolicy":
        """Keep corroborated geometry at least as hard to flag as uncorroborated geometry."""
        if self.corroborated_z < self.modified_z:
            message = "corroborated_z must be at least modified_z"
            raise ValueError(message)
        return self


class AnnotationBatch(BoundaryModel):
    """Freeze distinct sample/annotator records and review policy.

    ``label_mode`` declares whether one sample may carry several labels; ``auto``
    infers single-select behaviour from the batch itself. ``outlier_policy`` belongs
    to the frozen batch, so its digest and every rework comparison bind the thresholds.
    """

    annotations: tuple[AnnotationRecord, ...]
    near_duplicates: tuple[NearDuplicatePair, ...] = ()
    exclusive_label_groups: tuple[tuple[str, ...], ...] = ()
    iou_threshold: float = Field(default=0.5, gt=0, le=1)
    label_mode: Literal["auto", "single", "multi"] = "auto"
    outlier_policy: OutlierPolicy = Field(default_factory=OutlierPolicy)

    @model_validator(mode="after")
    def unique_annotations(self) -> "AnnotationBatch":
        """Reject duplicate identities instead of silently replacing ratings."""
        identities = [(item.sample_id, item.annotator_id) for item in self.annotations]
        if len(identities) != len(set(identities)):
            message = "Each sample/annotator identity must appear only once"
            raise ValueError(message)
        return self


class AgreementValue(BoundaryModel):
    """Represent an estimate or an explicit undefined estimate without NaN."""

    value: float | None
    observed_agreement: float | None = None
    sample_count: int = 0
    reason: str | None = None


class ClassConfusion(BoundaryModel):
    """Expose a per-label binary confusion matrix with the left annotator as reference."""

    category: str
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int


class ClassificationPair(BoundaryModel):
    """Report Cohen kappa over complete nominal label sets and per-class membership.

    ``matrix[i][j]`` counts samples that annotator_a put in ``categories[i]`` and
    annotator_b put in ``categories[j]``; a multilabel set is one category joined
    with ``+`` and a reviewed empty set is ``(empty)``.
    """

    annotator_a: str
    annotator_b: str
    cohen_kappa: AgreementValue
    confusion: tuple[ClassConfusion, ...] = ()
    categories: tuple[str, ...] = ()
    matrix: tuple[tuple[int, ...], ...] = ()


class ClassificationAgreement(BoundaryModel):
    """Report nominal label-set agreement; Fleiss uses equal-sized rating panels."""

    pairs: tuple[ClassificationPair, ...] = ()
    fleiss_kappa: AgreementValue
    krippendorff_alpha: AgreementValue


class BoxAgreement(BoundaryModel):
    """Summarize descending-IoU greedy one-to-one matches across shared samples."""

    annotator_a: str
    annotator_b: str
    sample_count: int
    box_count_a: int
    box_count_b: int
    matched_count: int
    match_rate: float | None
    mean_iou: float | None
    category_agreement: float | None


class SpanAgreement(BoundaryModel):
    """Summarize exact and positive-overlap maximum-cardinality matching F1."""

    annotator_a: str
    annotator_b: str
    sample_count: int
    span_count_a: int
    span_count_b: int
    exact_matches: int
    overlap_matches: int
    exact_f1: float | None
    overlap_f1: float | None


FindingCode = Literal[
    "minority_label",
    "near_duplicate_conflict",
    "bbox_size_outlier",
    "bbox_aspect_outlier",
    "invalid_bbox",
    "multilabel_conflict",
    "invalid_span",
    "bbox_category_minority",
    "bbox_missing",
    "bbox_extra",
    "duplicate_bbox",
    "span_category_minority",
    "span_boundary_minority",
    "span_missing",
    "span_extra",
    "duplicate_span",
    "span_length_outlier",
    "rare_category",
]


class AnnotationFinding(BoundaryModel):
    """Provide a stable repair identity and human-readable evidence for a suspicion."""

    finding_id: str
    sample_id: str
    annotator_id: str
    code: FindingCode
    reason: str
    evidence: tuple[str, ...]
    related_sample_ids: tuple[str, ...] = ()


class AnnotationQAResult(BoundaryModel):
    """Bundle deterministic metrics and review candidates for one frozen batch."""

    classification: ClassificationAgreement
    boxes: tuple[BoxAgreement, ...] = ()
    spans: tuple[SpanAgreement, ...] = ()
    findings: tuple[AnnotationFinding, ...] = ()
    sample_count: int
    annotator_count: int


class ReworkComparison(BoundaryModel):
    """Compare rule findings only on preserved sample/annotator review identities.

    Record counts compare sample/annotator records directly. Inspection counts
    cover units that an approved inspection of the original batch marked
    defective, and how many of those units have any changed record after rework.
    """

    before_count: int
    after_count: int
    corrected_count: int
    introduced_count: int
    remaining_count: int
    unassessed_count: int
    changed_records: int = 0
    unchanged_records: int = 0
    added_records: int = 0
    removed_records: int = 0
    inspection_defects: int = 0
    inspection_defects_changed: int = 0
    corrected: tuple[AnnotationFinding, ...] = ()
    introduced: tuple[AnnotationFinding, ...] = ()
    remaining: tuple[AnnotationFinding, ...] = ()
    unassessed: tuple[AnnotationFinding, ...] = ()
