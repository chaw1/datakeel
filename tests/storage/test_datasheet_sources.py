# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated evidence and image graph facts preserve exact version and human decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.cli.image_kg_demo import seed_image_kg_demo
from datakeel.core.evidence_models import AssertionDecision, AssertionDecisionRequest
from datakeel.datasheets.templates import build_template
from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.sample_evidence import generate_samples
from datakeel.storage.database import VersionRow
from datakeel.storage.datasheet_facts import extract_facts
from datakeel.storage.evidence_decisions import append_decision, decide_assertions
from datakeel.storage.evidence_import import import_evidence_samples, source_manifest
from datakeel.storage.evidence_store import list_assertions
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def test_evidence_facts_include_review_and_exclude_other_manifest_versions(
    db: Database, tmp_path: Path
) -> None:
    """Use real offline paired extraction and retain accepted/rejected/invalidation provenance."""
    directory = tmp_path / "paired"
    generate_samples(directory, 20)
    dataset = import_evidence_samples(db, "Generated paired evidence", directory)
    version_id, _ = source_manifest(db, dataset.id)
    DatabaseQueue(db).submit(dataset.id, "datasheet-evidence", evidence_pipeline())
    run_worker(db, once=True)
    observation = list_assertions(db)[0]
    decide_assertions(
        db,
        AssertionDecisionRequest(
            assertion_ids=(observation.id,),
            status="accepted",
            actor="Fixture reviewer",
            reason="Source checked",
            idempotency_key="datasheet-review",
        ),
    )
    with db.session() as session:
        append_decision(
            session,
            AssertionDecision(
                assertion_id=observation.id,
                action="invalidate",
                previous_status="accepted",
                status="accepted",
                actor="Fixture reviewer",
                reason="Source replaced",
            ),
            "datasheet-invalidate",
        )
        session.commit()
    with db.session() as session:
        facts = extract_facts(session, dataset.id, version_id)
        replacement = VersionRow(dataset_id=dataset.id, manifest=[], created_at=9999999999)
        session.add(replacement)
        session.flush()
        unrelated = extract_facts(session, dataset.id, replacement.id)
    values = {fact.field: fact.value for fact in facts}
    assert values["assertions.count"]
    assert values["assertions.inactive_count"] == 1
    assert values["assertions.predicate_counts"]
    decisions = [fact.value for fact in facts if fact.source_type == "assertion_decision"]
    assert len(decisions) == 2
    assert any(isinstance(value, dict) and value["action"] == "accept" for value in decisions)
    assert not any(fact.source_type == "version_assertions" for fact in unrelated)
    assert len(build_template(facts).sections) == 7
    assert not any(fact.field == "kg.entities" for fact in facts)


def test_image_graph_demo_exports_recorded_entities_and_review_counts_without_clients(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read the shipped image replay facts without reading any provider credentials."""

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        msg = "Offline documentation must not construct a provider client"
        raise AssertionError(msg)

    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", forbidden)
    monkeypatch.setattr("datakeel.transcription.factory.get_settings", forbidden)
    seed = seed_image_kg_demo(db)
    run_worker(db, once=True)
    with db.session() as session:
        facts = extract_facts(session, seed.dataset_id, seed.version_id)
    values = {fact.field: fact.value for fact in facts}
    assert values["manifest.file_count"] == 11
    assert values["kg.entities"]
    assert values["kg.relation_count"]
    assert values["assertions.verification_counts"]
    assert len(build_template(facts).sections) == 7
    assert not any("image-kg-samples" in str(fact.value) for fact in facts)
