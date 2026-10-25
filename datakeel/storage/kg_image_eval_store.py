# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist evaluation candidates in an isolated fact store before scoring their projection."""

from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.evidence_models import Assertion
from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_product import ProductExtraction
from datakeel.core.models import AssetRef, LineageEvent, new_id
from datakeel.kg.identity import assertion_identity, merge_drafts
from datakeel.storage.database import Database
from datakeel.storage.events import append_event
from datakeel.storage.evidence_store import project_bundle, read_assertions, validated_bundle


def store_evaluation_product(
    db: Database, product: ProductExtraction, schema: KGSchema
) -> tuple[Assertion, ...]:
    """Use production validation and projection with no configured object-store access."""
    identifier = new_id()
    drafts = merge_drafts(product.drafts)
    sources = {
        anchor.asset_ref.model_dump_json(): anchor.asset_ref
        for draft in drafts
        for anchor in draft.anchors
    }
    event = LineageEvent(
        event_id=identifier,
        idempotency_key=f"image-evaluation:{identifier}",
        event_type="COMPLETE",
        operator="evidence.kg",
        source_module="kg",
        source_ref=identifier,
        inputs=list(sources.values()),
        outputs=[
            *(entity.asset_ref for entity in product.entities),
            AssetRef(asset_type="knowledge_bundle", asset_id=identifier, version="1.0"),
        ],
        params={"run_id": identifier, "kg_schema": schema.model_dump(mode="json")},
    )
    bundle = KnowledgeBundle(
        run_id=identifier,
        assertions=tuple(
            Assertion(
                **draft.model_dump(),
                id=assertion_identity(draft),
                producer_event_id=identifier,
                run_id=identifier,
                created_at=event.occurred_at,
            )
            for draft in drafts
        ),
    )
    with db.session() as session:
        db.lock_writes(session)
        validated_bundle(event, bundle)
        append_event(session, event)
        project_bundle(session, event, bundle)
        session.commit()
        return tuple(item for item in read_assertions(session) if item.run_id == identifier)
