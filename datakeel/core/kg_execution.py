# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen extraction plans, progress reports and disposable cache boundaries."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, cast

from pydantic import Field, model_validator

from datakeel.core.evidence_models import ContentRevision
from datakeel.core.harness_pricing import ModelPrice
from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
from datakeel.core.kg_models import Recording, TextBlock
from datakeel.core.kg_product import ProductExtraction, SchemaProposal
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument


class KGDocument(BoundaryModel):
    """Keep validated NFC source content inside the authorized worker boundary."""

    asset_ref: AssetRef
    filename: str
    text: str
    content_revision: ContentRevision
    blocks: tuple[TextBlock, ...]


class KGBlockFingerprint(BoundaryModel):
    """Bind a normalized block without putting its text in a consent payload."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    content_hash: ContentRevision


class KGDocumentFingerprint(BoundaryModel):
    """Bind a file revision and all chunk coordinates without copying source content."""

    asset_ref: AssetRef
    filename: str
    content_revision: ContentRevision
    blocks: tuple[KGBlockFingerprint, ...]

    @classmethod
    def from_document(cls, document: KGDocument) -> "KGDocumentFingerprint":
        """Reduce a decoded source to the exact fields required for later verification."""
        return cls(
            asset_ref=document.asset_ref,
            filename=document.filename,
            content_revision=document.content_revision,
            blocks=tuple(
                KGBlockFingerprint(start=b.start, end=b.end, content_hash=b.content_hash)
                for b in document.blocks
            ),
        )


class KGInputs(BoundaryModel):
    """Carry verified source and recording content only after worker authorization."""

    documents: tuple[KGDocument, ...]
    recording: Recording | None = None


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
    documents: tuple[KGDocumentFingerprint, ...]
    estimate: KGEstimate
    recording_hash: str | None = None
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
    ignored_top_level_keys: int = Field(default=0, ge=0)
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
    documents: tuple[KGDocument, ...] = ()
    budget_tokens: int = Field(ge=0)
    max_cost_usd: Decimal = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def separate_legacy_content(cls, value: object) -> object:
        """Keep existing run history readable while removing legacy content from preparation."""
        candidate = cast("dict[str, object]", value)
        if not isinstance(value, dict) or not isinstance(candidate.get("prepared"), dict):
            return cast("object", value)
        data = JsonDocument.model_validate(value).root
        prepared = data.get("prepared")
        if not isinstance(prepared, dict) or "recording" not in prepared:
            return cast("object", value)
        sources = prepared.get("documents")
        if not isinstance(sources, list):
            return cast("object", value)
        documents = tuple(KGDocument.model_validate(item) for item in sources)
        prepared = dict(prepared)
        prepared.pop("recording")
        profile = prepared.get("profile")
        if isinstance(profile, dict):
            parameters = profile.get("request_parameters")
            if isinstance(parameters, dict) and "num_ctx" in parameters:
                profile = {
                    **profile,
                    "request_parameters": {k: v for k, v in parameters.items() if k != "num_ctx"},
                }
                prepared["profile"] = profile
        prepared["documents"] = [
            KGDocumentFingerprint.from_document(item).model_dump(mode="json") for item in documents
        ]
        return {
            **data,
            "prepared": prepared,
            "documents": [document.model_dump(mode="json") for document in documents],
        }


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
