# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Strict, immutable development-manifest and provenance boundaries."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
CONTRACT = "we-e1-v1"


class Boundary(BaseModel):
    """Reject undeclared fields and mutation at all E1 boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class EvidenceFile(Boundary):
    """Identify locally retained upstream evidence, never an invented assertion."""

    path: str
    sha256: Digest


class PublicRow(Boundary):
    """Pin a selected original row or Commons file and its grouping identities."""

    stable_id: str
    revision: str
    original_sha256: Digest
    original_file: EvidenceFile
    semantic_group: str
    near_duplicate_cluster: str
    transformation_family: str
    attribution: str
    license_id: str
    license_url: str | None
    metadata: EvidenceFile


class RowMetadata(Boundary):
    """Normalize upstream metadata while retaining the hash-bound original response."""

    stable_id: str
    revision: str
    license_id: str
    license_url: str | None
    attribution: str
    author: str
    original_url: str
    raw_upstream: EvidenceFile
    dataset_revision: str | None = None
    config: str | None = None
    wikidata_id: str | None = None
    version_id: str | None = None
    split: str | None = None
    row_index: int | None = None
    pageid: int | None = None
    revid: int | None = None
    imageinfo: tuple[JsonValue, ...] = ()
    extmetadata: dict[str, JsonValue] = Field(default_factory=dict)
    license_short_name: str | None = None
    upstream_license_url: str | None = None


class Source(Boundary):
    """Keep absent public provenance blocked rather than replacing it with fake data."""

    source_id: Literal["wiki40b-style", "wikimedia-commons"]
    planned_url: str
    status: Literal["blocked", "frozen"]
    revision: str | None = None
    rows: tuple[PublicRow, ...] = ()
    license_evidence: tuple[EvidenceFile, ...] = ()
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_provenance(self) -> Self:
        """Reject a freeze claim without actual rows and upstream license evidence."""
        complete = bool(self.revision and self.rows and self.license_evidence)
        if self.status == "frozen" and (not complete or self.blockers):
            msg = "frozen source requires revision, rows and license evidence"
            raise ValueError(msg)
        if self.status == "blocked" and not self.blockers:
            msg = "blocked source requires an explicit reason"
            raise ValueError(msg)
        return self


class SourceRegistry(Boundary):
    """Describe public development candidates, with no holdout identifiers."""

    contract_version: Literal["we-e1-v1"]
    # Acquisition history only; this flag never enables network access in the verifier.
    network_performed: bool
    sources: tuple[Source, ...]

    @model_validator(mode="after")
    def require_both_sources(self) -> Self:
        """Require each planned modality exactly once."""
        if sorted(s.source_id for s in self.sources) != ["wiki40b-style", "wikimedia-commons"]:
            msg = "both public sources must be declared exactly once"
            raise ValueError(msg)
        return self


class Asset(Boundary):
    """Describe a small, generated contract fixture with explicit fake provenance."""

    asset_id: str
    modality: Literal["text", "image"]
    source_kind: Literal["synthetic_contract_only"]
    stable_source_id: str
    original_group: str
    near_duplicate_cluster: str
    transformation_family: str
    variant: str
    original_sha256: Digest
    content_sha256: Digest
    content_base64: str
    split: Literal["dev_tune", "dev_validation"]


class Manifest(Boundary):
    """Freeze fake development fixtures separately from unavailable public baselines."""

    contract_version: Literal["we-e1-v1"]
    generator_version: Literal["we-e1-generator-v1"]
    seed: Literal["we-e1-development-v1"]
    purpose: Literal["contracts_only_not_encoder_quality"]
    public_baseline_frozen: Literal[False]
    pillow_version: str
    assets: tuple[Asset, ...]


class SearchSpace(Boundary):
    """Freeze a finite development-only grid, without selecting tuned parameters."""

    contract_version: Literal["we-e1-v1"]
    duplicate_threshold: tuple[float, ...]
    dbscan_eps: tuple[float, ...]
    min_samples: tuple[Annotated[int, Field(ge=2)], ...]
    gap_threshold: tuple[float, ...]
    text_dimensions: tuple[int, ...]
    max_samples: Literal[5000]
    max_candidate_pairs: Literal[250000]
    max_reference_comparisons: Literal[250000]
    selected_parameters: None
    selection_rule: Literal["development_only_freeze_before_single_independent_campaign"]

    @model_validator(mode="after")
    def validate_grid(self) -> Self:
        """Reject empty, repeated, nonfinite or out-of-domain candidate values."""
        for values, upper in (
            (self.duplicate_threshold, 1),
            (self.gap_threshold, 1),
            (self.dbscan_eps, 2),
        ):
            if not values or len(values) != len(set(values)):
                msg = "grid must be nonempty and unique"
                raise ValueError(msg)
            if not all(0 < value <= upper for value in values):
                msg = "grid value outside domain"
                raise ValueError(msg)
        if not self.min_samples or len(set(self.min_samples)) != len(self.min_samples):
            msg = "min_samples must be nonempty and unique"
            raise ValueError(msg)
        if self.text_dimensions != (64, 128, 256, 512, 768, 1024, 1536, 2048):
            msg = "text dimension grid differs from the W-E contract"
            raise ValueError(msg)
        return self
