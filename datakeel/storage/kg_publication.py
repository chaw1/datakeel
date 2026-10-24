# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish graph observations and source-scoped replacement audits inside a lease fence."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from datakeel.core.errors import ConflictError
from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import Assertion, AssertionDecision
from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_execution import KGCompletion, KGJob
from datakeel.core.kg_product import KGEntity, ProductExtraction
from datakeel.core.kg_registry import register_kg_schema
from datakeel.core.models import AssetRef, LineageEvent, new_id
from datakeel.kg.aliases import refresh_reviewed_aliases, same_as_drafts
from datakeel.kg.cache import extraction_identity
from datakeel.kg.identity import assertion_identity, merge_drafts
from datakeel.kg.retention import preserve_unselected
from datakeel.storage.events import all_events
from datakeel.storage.evidence_decisions import append_decision, assertion_view
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.evidence_store import record_extraction_in_session
from datakeel.storage.kg_provenance import prior_bundle_inputs
from datakeel.storage.kg_reviews import inherit_reviews
from datakeel.storage.kg_rows import KGRunRow


def _prior_graph(
    session: Session, job: KGJob
) -> tuple[tuple[KGEntity, ...], tuple[Assertion, ...]]:
    entities: dict[str, KGEntity] = {}
    for event in sorted(all_events(session), key=lambda item: (item.occurred_at, item.event_id)):
        if "kg_schema" in event.params:
            register_kg_schema(KGSchema.model_validate(event.params["kg_schema"]))
        if (event.params.get("kg_dataset_id"), event.params.get("kg_version_id")) != (
            job.run.dataset_id,
            job.run.version_id,
        ):
            continue
        for value in event.params.get("kg_entities", []):
            entity = KGEntity.model_validate(value)
            entities[entity.asset_ref.asset_id] = entity
    rows = session.scalars(
        select(AssertionRow)
        .where(AssertionRow.active.is_(True), AssertionRow.predicate.like("kg.%"))
        .with_for_update()
    )
    assertions = tuple(
        assertion
        for row in rows
        if (assertion := assertion_view(row)).subject.asset_id in entities
        and assertion.subject.version == job.run.version_id
    )
    return tuple(entities.values()), assertions


def _products(
    job: KGJob, completion: KGCompletion, entities: tuple[KGEntity, ...], old: tuple[Assertion, ...]
) -> ProductExtraction:
    preserved = preserve_unselected(old, set(completion.replace_file_ids))
    reviewed = preserve_unselected(
        tuple(
            item for item in old if item.predicate == "kg.same_as" and item.status != "candidate"
        ),
        set(),
    )
    existing_pairs = {
        _alias_pair(draft) for draft in (*preserved, *reviewed) if draft.predicate == "kg.same_as"
    }
    incoming = tuple(
        draft
        for draft in completion.products.drafts
        if draft.predicate != "kg.same_as" or _alias_pair(draft) not in existing_pairs
    )
    drafts = merge_drafts((*preserved, *reviewed, *incoming))
    mentioned = {draft.subject.asset_id for draft in drafts if draft.predicate == "kg.mentions"}
    drafts = tuple(
        draft
        for draft in drafts
        if draft.predicate != "kg.same_as"
        or (
            draft.subject.asset_id in mentioned
            and isinstance(draft.object, AssetRef)
            and draft.object.asset_id in mentioned
        )
    )
    labels = {
        entity.asset_ref.asset_id: entity
        for entity in (*entities, *completion.products.entities)
        if entity.asset_ref.asset_id in mentioned
    }
    selected = tuple(labels[key] for key in sorted(labels))
    prepared = job.prepared
    extractor = extraction_identity(
        prepared.schema_definition, prepared.profile, prepared.recording_hash
    )
    aliases = same_as_drafts(selected, drafts, prepared.schema_definition, extractor)
    return ProductExtraction(
        entities=selected,
        drafts=merge_drafts((*refresh_reviewed_aliases(drafts, reviewed), *aliases)),
        proposals=completion.products.proposals,
    )


def _alias_pair(draft: ObservationDraft) -> tuple[str, ...]:
    return (
        tuple(sorted((draft.subject.asset_id, draft.object.asset_id)))
        if isinstance(draft.object, AssetRef)
        else ()
    )


def _event(job: KGJob, products: ProductExtraction, prior_inputs: list[AssetRef]) -> LineageEvent:
    sources = {
        document.asset_ref.model_dump_json(): document.asset_ref
        for document in job.prepared.documents
    }
    sources.update(
        {
            anchor.asset_ref.model_dump_json(): anchor.asset_ref
            for draft in products.drafts
            for anchor in draft.anchors
        }
    )
    identifier = new_id()
    return LineageEvent(
        event_id=identifier,
        idempotency_key=f"kg:{job.run.id}",
        event_type="COMPLETE",
        operator="evidence.kg",
        source_module="kg",
        source_ref=job.run.id,
        inputs=[sources[key] for key in sorted(sources)] + prior_inputs,
        outputs=[
            *(entity.asset_ref for entity in products.entities),
            AssetRef(asset_type="knowledge_bundle", asset_id=identifier, version="1.0"),
        ],
        params={
            "run_id": job.run.id,
            "kg_dataset_id": job.run.dataset_id,
            "kg_version_id": job.run.version_id,
            "kg_model": job.run.model,
            "kg_extractor": job.run.extractor,
            "kg_profile_id": job.run.profile_id,
            "kg_schema": job.prepared.schema_definition.model_dump(mode="json"),
            "kg_entities": [entity.model_dump(mode="json") for entity in products.entities],
        },
    )


def _new_assertions(
    session: Session, event: LineageEvent, drafts: tuple[ObservationDraft, ...]
) -> tuple[Assertion, ...]:
    identities = {assertion_identity(draft): draft for draft in drafts}
    existing = set(session.scalars(select(AssertionRow.id).where(AssertionRow.id.in_(identities))))
    return tuple(
        Assertion(
            **draft.model_dump(),
            id=identifier,
            producer_event_id=event.event_id,
            run_id=str(event.params["run_id"]),
            created_at=event.occurred_at,
        )
        for identifier, draft in sorted(identities.items())
        if identifier not in existing
    )


def _replacement_audit(
    session: Session,
    event: LineageEvent,
    old: tuple[Assertion, ...],
    drafts: tuple[ObservationDraft, ...],
) -> None:
    current = {assertion_identity(draft) for draft in drafts}
    for assertion in old:
        if assertion.id not in current:
            append_decision(
                session,
                AssertionDecision(
                    assertion_id=assertion.id,
                    action="invalidate",
                    previous_status=assertion.status,
                    status=assertion.status,
                    actor=event.operator,
                    reason="graph_source_or_configuration_replaced",
                    producer_event_id=event.event_id,
                    occurred_at=event.occurred_at,
                ),
                f"kg-invalidate:{event.event_id}:{assertion.id}",
            )
    for row in session.scalars(
        select(AssertionRow).where(AssertionRow.id.in_(current), AssertionRow.active.is_(False))
    ):
        assertion = assertion_view(row)
        append_decision(
            session,
            AssertionDecision(
                assertion_id=assertion.id,
                action="reactivate",
                previous_status=assertion.status,
                status=assertion.status,
                actor=event.operator,
                reason="exact_content_reobserved",
                producer_event_id=event.event_id,
                occurred_at=event.occurred_at,
            ),
            f"kg-reactivate:{event.event_id}:{assertion.id}",
        )


def publish_completion(session: Session, completion: KGCompletion, task_id: str) -> None:
    """Bind facts, replacement audits and the report to the caller's fenced transaction."""
    row = session.get(KGRunRow, completion.run.id, with_for_update=True)
    if row is None or row.task_id != task_id:
        msg = "Graph completion does not belong to the fenced worker task"
        raise ConflictError(msg)
    job = KGJob.model_validate(row.payload)
    if (completion.run.dataset_id, completion.run.version_id) != (
        job.run.dataset_id,
        job.run.version_id,
    ):
        msg = "Graph completion changed its frozen dataset scope"
        raise ConflictError(msg)
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
            {"scope": f"kg-publish:{job.run.dataset_id}:{job.run.version_id}"},
        )
    entities, old = _prior_graph(session, job)
    products = _products(job, completion, entities, old)
    current = {assertion_identity(draft) for draft in products.drafts}
    reused = tuple(
        assertion_view(item)
        for item in session.scalars(select(AssertionRow).where(AssertionRow.id.in_(current)))
    )
    event = _event(job, products, prior_bundle_inputs(session, (*old, *reused)))
    bundle = KnowledgeBundle(
        run_id=job.run.id, assertions=_new_assertions(session, event, products.drafts)
    )
    record_extraction_in_session(session, event, bundle)
    _replacement_audit(session, event, old, products.drafts)
    inherit_reviews(session, event, current)
    row.payload = job.model_copy(update={"run": completion.run}).model_dump(mode="json")
