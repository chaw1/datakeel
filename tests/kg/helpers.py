# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Small typed graph fixtures for query and projection tests."""

import hashlib
from decimal import Decimal

from datakeel.core.evidence_models import Assertion, ExtractorRef
from datakeel.core.harness_pricing import ModelPrice
from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation, KGSchema
from datakeel.core.kg_execution import (
    KGDocument,
    KGDocumentFingerprint,
    KGEstimate,
    KGJob,
    KGPrepared,
    KGRun,
)
from datakeel.core.kg_models import RawExtraction
from datakeel.core.kg_product import KGSource, ProductExtraction
from datakeel.core.models import AssetRef, LineageEvent, utcnow
from datakeel.kg.assembly import assemble_extraction
from datakeel.kg.identity import assertion_identity
from datakeel.kg.loader import get_profile, get_schema
from datakeel.kg.text import chunk_text
from datakeel.storage.database import Database
from datakeel.storage.events import append_event
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.kg_rows import KGRunRow


def graph_product(
    name: str = "Acme", file_id: str = "document", *, missing: bool = False
) -> tuple[ProductExtraction, KGSource]:
    """Extract one factual organization/tool pair plus an optional hallucinated endpoint."""
    text = f"{name} uses Widget."
    source = KGSource(
        dataset_id="dataset",
        dataset_version_id="version",
        file=AssetRef(asset_type="file", asset_id=file_id, version="version"),
        text=text,
        content_revision=hashlib.sha256(text.encode()).hexdigest(),
        extractor=ExtractorRef(id="evidence.kg", version="test"),
    )
    raw = RawExtraction(
        entities=(
            ExtractedEntity(name=name, type="organization"),
            ExtractedEntity(name="Vivo" if missing else "Widget", type="system"),
        ),
        relations=(
            ExtractedRelation(
                head=name, relation="uses", tail="Vivo" if missing else "Widget", evidence=text
            ),
        ),
    )
    return assemble_extraction(raw, get_schema(), source), source


def assertions_for(
    product: ProductExtraction, event_id: str = "event", run_id: str = "run"
) -> tuple[Assertion, ...]:
    """Bind pure observations to deterministic assertion identities for tests."""
    return tuple(
        Assertion(
            **draft.model_dump(),
            id=assertion_identity(draft),
            producer_event_id=event_id,
            run_id=run_id,
        )
        for draft in product.drafts
    )


def _job(source: KGSource, schema: KGSchema) -> KGJob:
    run_id = f"run-{source.file.asset_id}"
    run = KGRun(
        id=run_id,
        dataset_id=source.dataset_id,
        version_id=source.dataset_version_id,
        schema_id=schema.id,
        profile_id="fake",
        model="fixture-model",
        extractor="fake",
        status="completed",
        created_at=utcnow(),
        task_id=f"task-{run_id}",
    )
    document = KGDocument(
        asset_ref=source.file,
        filename=f"{source.file.asset_id}.txt",
        text=source.text,
        content_revision=source.content_revision,
        blocks=chunk_text(source.text, 12000),
    )
    return KGJob(
        run=run,
        documents=(document,),
        prepared=KGPrepared(
            schema_definition=schema,
            profile=get_profile("fake"),
            documents=(KGDocumentFingerprint.from_document(document),),
            external=False,
            accounting_price=ModelPrice(
                model="fixture-model",
                provider="fake",
                input=Decimal(0),
                output=Decimal(0),
                cache_read=Decimal(0),
                cache_write=Decimal(0),
                source="fixture",
            ),
            accounting_price_version="fixture",
            estimate=KGEstimate(
                target_host=None,
                model="fixture-model",
                documents=1,
                blocks=1,
                input_tokens=0,
                max_output_tokens=4096,
            ),
        ),
        budget_tokens=10000,
        max_cost_usd=Decimal(1),
    )


def seed_graph(
    db: Database, product: ProductExtraction, source: KGSource, *, schema: KGSchema | None = None
) -> tuple[Assertion, ...]:
    """Seed frozen jobs and evidence projections; publication is tested independently."""
    schema = schema or get_schema()
    job = _job(source, schema)
    run = job.run
    run_id, event_id = run.id, f"event-{source.file.asset_id}"
    assertions = assertions_for(product, event_id, run_id)
    event = LineageEvent(
        event_id=event_id,
        idempotency_key=event_id,
        event_type="COMPLETE",
        operator="evidence.kg",
        inputs=[source.file],
        outputs=[entity.asset_ref for entity in product.entities],
        params={
            "run_id": run_id,
            "kg_dataset_id": source.dataset_id,
            "kg_version_id": source.dataset_version_id,
            "kg_model": run.model,
            "kg_extractor": run.extractor,
            "kg_profile_id": "fake",
            "kg_schema": schema.model_dump(mode="json"),
            "kg_entities": [entity.model_dump(mode="json") for entity in product.entities],
        },
    )
    _persist(db, job, event, assertions)
    return assertions


def _persist(
    db: Database, job: KGJob, event: LineageEvent, assertions: tuple[Assertion, ...]
) -> None:
    run = job.run
    with db.session() as session:
        append_event(session, event)
        session.add(
            KGRunRow(
                id=run.id,
                dataset_id=run.dataset_id,
                version_id=run.version_id,
                task_id=run.task_id,
                created_at=run.created_at.timestamp(),
                payload=job.model_dump(mode="json"),
            )
        )
        for assertion in assertions:
            session.add(
                AssertionRow(
                    id=assertion.id,
                    subject_id=assertion.subject.asset_id,
                    predicate=assertion.predicate,
                    producer_event_id=event.event_id,
                    payload=assertion.model_dump(mode="json"),
                    status=assertion.status,
                    active=True,
                    verification=assertion.verification,
                    verification_detail=assertion.verification_detail.model_dump(mode="json")
                    if assertion.verification_detail
                    else None,
                )
            )
        session.commit()
