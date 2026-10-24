# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen extraction plans, progress reports and disposable cache boundaries."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from datakeel.core.evidence_models import ContentRevision
from datakeel.core.harness_pricing import ModelPrice
from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
from datakeel.core.kg_models import Recording, TextBlock
from datakeel.core.kg_product import ProductExtraction, SchemaProposal
from datakeel.core.models import AssetRef, BoundaryModel


class KGDocument(BoundaryModel):
    """Freeze decoded NFC text and source identity before any approval is requested."""

    asset_ref: AssetRef
    filename: str
    text: str
    content_revision: ContentRevision
    blocks: tuple[TextBlock, ...]


class KGEstimate(BoundaryModel):
    """Bind visible outbound impact and its exact price snapshot to the plan digest."""

    target_host: str | None
    model: str
    documents: int = Field(ge=0)
    blocks: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    max_output_tokens: int = Field(gt=0)
    cost_upper_usd: Decimal | None = None
    price_version: str | None = None
    price: ModelPrice | None = None


class KGPrepared(BoundaryModel):
    """Capture all extraction inputs so later file or profile edits cannot change consent."""

    schema_definition: KGSchema
    profile: ExtractionProfile
    documents: tuple[KGDocument, ...]
    estimate: KGEstimate
    recording_hash: str | None = None
    recording: Recording | None = None
    accounting_price: ModelPrice
    accounting_price_version: str
    external: bool


class KGBlockFailure(BoundaryModel):
    """Explain a failed or unexecuted block using source offsets rather than silent omission."""

    file_id: str
    filename: str
    start: int
    end: int
    reason: str
    attempted: bool = True


class KGReport(BoundaryModel):
    """Summarize extraction, cache reuse, verification, billing and partial documents."""

    documents: int = 0
    blocks: int = 0
    cached: int = 0
    extracted: int = 0
    failed: int = 0
    unexecuted: int = 0
    model_calls: int = 0
    entities: int = 0
    relations: int = 0
    verified: int = 0
    needs_review: int = 0
    entities_verified: int = 0
    entities_needs_review: int = 0
    relations_verified: int = 0
    relations_needs_review: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal | None = None
    accounted_cost_usd: Decimal = Decimal(0)
    elapsed_seconds: float = 0
    error: str | None = None
    failures: tuple[KGBlockFailure, ...] = ()
    partial_documents: tuple[str, ...] = ()
    proposals: tuple[SchemaProposal, ...] = ()


class KGRun(BoundaryModel):
    """Expose one durable worker run independently of its internal frozen inputs."""

    id: str
    dataset_id: str
    version_id: str
    schema_id: str
    profile_id: str
    model: str
    extractor: str
    status: Literal["queued", "running", "completed", "partial", "budget_exceeded", "failed"]
    created_at: datetime
    completed_at: datetime | None = None
    task_id: str | None = None
    report: KGReport = Field(default_factory=KGReport)


class KGJob(BoundaryModel):
    """Carry a complete frozen worker request across the storage boundary."""

    run: KGRun
    prepared: KGPrepared
    budget_tokens: int = Field(ge=0)
    max_cost_usd: Decimal = Field(ge=0, allow_inf_nan=False)


class KGLeaseFence(BoundaryModel):
    """Identify the only worker attempt allowed to publish progress or facts."""

    task_id: str
    shard_id: str
    owner: str


class KGCompletion(BoundaryModel):
    """Publish successful block products while replacing only fully completed documents."""

    run: KGRun
    products: ProductExtraction
    replace_file_ids: tuple[str, ...] = ()


class KGMeteringConfig(BoundaryModel):
    """Separate the known tariff from the conservative unknown-price accounting envelope."""

    run_id: str
    profile: ExtractionProfile
    price: ModelPrice
    price_version: str
    known_price: bool
    budget_tokens: int = Field(default=250000, ge=0)
    max_cost_usd: Decimal = Field(default=Decimal(5), ge=0, allow_inf_nan=False)
