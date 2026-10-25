# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image provenance, cache reuse, replacement and failure checks through the real worker."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.api.app import create_app
from datakeel.core.evidence_models import ImageRegion, TextSpan
from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation
from datakeel.core.kg_models import ExtractionResult, RawExtraction
from datakeel.core.kg_queries import KGQuery
from datakeel.core.models import JsonDocument
from datakeel.core.transcription_models import TranscriptionProfile
from datakeel.storage.database import VersionRow
from datakeel.storage.evidence_decisions import list_decisions
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_queries import explain_relation, query_kg
from datakeel.storage.kg_store import get_job
from datakeel.storage.transcription_rows import TranscriptionRow
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import (
    image_dataset,
    install_transcriber,
    prepare_image,
    transcript,
    use_profile,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_image_run_reuses_transcript_and_extraction_and_rebuilds_exactly(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Candidates keep separate versioned image/text anchors, and cached reruns make no calls."""
    dataset = image_dataset(db, tmp_path)
    use_profile(monkeypatch)
    transcriber = install_transcriber(monkeypatch, (transcript(),))
    extraction = install_adapter(monkeypatch, (pair_result(),))
    plan = prepare_image(db, dataset)
    assert len(transcriber.results) == 1
    first = execute_graph(db, plan)
    assert first.status == "completed"
    relation = query_kg(db, KGQuery()).relations[0]
    assert relation.assertion.status == "candidate"
    assert relation.image_located is True
    images = [a for a in relation.assertion.anchors if isinstance(a.selector, ImageRegion)]
    spans = [a for a in relation.assertion.anchors if isinstance(a.selector, TextSpan)]
    assert len(images) == 1
    assert len(spans) == 3
    assert images[0].asset_ref.version == dataset.files[0].sha256
    assert {a.asset_ref.asset_type for a in spans} == {"image_transcript"}
    explanation = explain_relation(db, relation.assertion.id)
    assert len(explanation.sources) == 2
    with TestClient(create_app(db)) as client:
        image = next(source for source in explanation.sources if source.image_url)
        response = client.get(image.image_url or "")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        for source in explanation.sources:
            response = client.get(
                f"/api/kg/sources/{source.asset_ref.asset_id}",
                params={
                    "version_id": source.asset_ref.version,
                },
            )
            assert response.status_code == 200
    original = list_assertions(db)
    assert rebuild_evidence(db).matches
    assert original == list_assertions(db)
    second = execute_graph(db, prepare_image(db, dataset))
    assert second.report.model_calls == 0
    assert second.report.cached == 1
    assert second.report.transcriptions[0].cached
    assert extraction.calls == 1
    assert not transcriber.results


@pytest.mark.parametrize("failure", ["empty", "truncated", "repeated", "timeout"])
def test_transcription_quality_failure_is_partial_and_never_cached(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Every quality outcome has a failed block and does not silently produce graph facts."""
    dataset = image_dataset(db, tmp_path, count=2)
    use_profile(monkeypatch)
    changes = {
        "empty": {"text": ""},
        "truncated": {"finish_reason": "length"},
        "repeated": {"text": "Repeated line\n" * 3, "mode": "vlm"},
        "timeout": {"error": "timeout"},
    }
    install_transcriber(
        monkeypatch, (transcript().model_copy(update=changes[failure]), transcript())
    )
    extractor = install_adapter(monkeypatch, (pair_result(),))
    run = execute_graph(db, prepare_image(db, dataset))
    assert run.status == "partial"
    assert run.report.transcription_failed == 1
    assert run.report.failures[0].reason == f"transcription:{failure}"
    assert run.report.partial_documents == (dataset.files[0].id,)
    assert run.report.transcriptions[0].status == "failed"
    assert extractor.calls == 1
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptionRow)) == 1


def test_changed_transcriber_invalidates_old_transcript_and_preserves_review(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new profile creates a new source asset without reopening a human-confirmed fact."""
    dataset = image_dataset(db, tmp_path)
    profile = use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(), transcript()))
    extraction = install_adapter(monkeypatch, (pair_result(),))
    execute_graph(db, prepare_image(db, dataset))
    old = query_kg(db, KGQuery()).relations[0].assertion
    decision = prepare_action(
        db,
        "decide_assertions",
        JsonDocument.model_validate({"assertion_ids": [old.id], "status": "accepted"}),
    )
    execute_plan(db, decision.id, ExecuteRequest(plan_digest=decision.plan_digest))
    use_profile(monkeypatch, profile.model_copy(update={"model": "scripted-v2"}))
    run = execute_graph(db, prepare_image(db, dataset))
    current = query_kg(db, KGQuery()).relations[0].assertion
    assert old.id != current.id
    assert current.status == "accepted"
    assert extraction.calls == 1
    assert run.report.cached == 1
    assert any(d.action == "invalidate" for d in list_decisions(db, old.id))
    assert rebuild_evidence(db).matches


def test_unlocated_relation_keeps_original_image_and_structured_reason(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing OCR geometry never fabricates a frame or hides the original image."""
    dataset = image_dataset(db, tmp_path)
    use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript().model_copy(update={"lines": ()}),))
    install_adapter(monkeypatch, (pair_result(),))
    run = execute_graph(db, prepare_image(db, dataset))
    relation = query_kg(db, KGQuery()).relations[0]
    assert relation.assertion.verification == "needs_review"
    assert relation.image_located is False
    assert relation.assertion.verification_detail is not None
    assert {issue.code for issue in relation.assertion.verification_detail.issues} == {
        "image_unlocated"
    }
    assert run.report.unlocated_relations == 1
    assert any(source.image_url for source in explain_relation(db, relation.assertion.id).sources)


def test_handwritten_person_mentions_and_relations_require_review(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only explicitly marked schema person types trigger the handwriting review policy."""
    dataset = image_dataset(db, tmp_path, handwriting=True)
    use_profile(monkeypatch)
    text = "Alice works for Acme."
    install_transcriber(monkeypatch, (transcript(text),))
    output = RawExtraction(
        entities=(
            ExtractedEntity(name="Alice", type="person"),
            ExtractedEntity(name="Acme", type="organization"),
        ),
        relations=(
            ExtractedRelation(head="Alice", relation="works_for", tail="Acme", evidence=text),
        ),
    )
    install_adapter(monkeypatch, (ExtractionResult(output=output),))
    run = execute_graph(db, prepare_image(db, dataset))
    assert run.status == "completed"
    values = query_kg(db, KGQuery())
    assert values.relations[0].assertion.verification == "needs_review"
    person = next(entity for entity in values.entities if entity.type == "person")
    assert all(
        mention.verification_detail
        and any(issue.code == "handwriting_name" for issue in mention.verification_detail.issues)
        for mention in person.mentions
    )
    organization = next(entity for entity in values.entities if entity.type == "organization")
    assert all(mention.verification == "verified" for mention in organization.mentions)


@pytest.mark.parametrize("width", [200, 201])
def test_unknown_visual_price_settles_observed_usage_and_cloud_trace(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    """The independent visual call is billed once and shared with the extraction budget."""
    dataset = image_dataset(db, tmp_path)
    profile = TranscriptionProfile(
        id="external-fixture",
        backend="vlm",
        mode="vlm",
        model="unpriced-fixture",
        base_url="https://vision.example/v1",
    )
    use_profile(monkeypatch, profile)
    install_transcriber(monkeypatch, (transcript().model_copy(update={"width": width}),))
    install_adapter(monkeypatch, (pair_result(),))
    plan = prepare_image(db, dataset)
    assert plan.impact.transcription_estimate is not None
    assert plan.impact.transcription_estimate.cost_upper_usd is None
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_graph(db, plan)
    assert run.status == ("completed" if width == 200 else "failed")
    traces = list_traces(db, run.id)
    visual = next(trace for trace in traces if trace.call_type == "transcription")
    assert visual.billing_status == "unknown"
    assert visual.observed_usage is not None
    assert visual.observed_usage.input_tokens == 20
    assert visual.accounted_tokens == 30
    assert run.report.cloud_calls == 1
    assert run.report.cloud_cost_usd is None
    assert run.report.cost_usd is None
    assert run.report.transcription_cost_usd is None
    if width == 200:
        assert run.report.extraction_cost_usd == sum(
            (trace.cost_usd for trace in traces if trace.call_type == "extraction"),
            start=Decimal(0),
        )
    assert get_job(db, run.id).documents[0].image is not None


def test_image_review_binds_new_manifest_when_pixels_are_shared_across_versions(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared pixels and transcript IDs must never send a new-version review to an old manifest."""
    dataset = image_dataset(db, tmp_path)
    use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(),))
    install_adapter(monkeypatch, (pair_result(),))
    execute_graph(db, prepare_image(db, dataset))
    with db.session() as session:
        original = session.get(VersionRow, dataset.version_id)
        assert original is not None
        current = VersionRow(dataset_id=dataset.dataset_id, manifest=original.manifest)
        session.add(current)
        session.flush()
        version_id = current.id
        session.commit()
    updated = dataset.model_copy(update={"version_id": version_id})
    execute_graph(db, prepare_image(db, updated))
    relation = query_kg(
        db, KGQuery(dataset_id=dataset.dataset_id, version_id=version_id)
    ).relations[0]
    plan = prepare_action(
        db,
        "decide_assertions",
        JsonDocument.model_validate(
            {
                "assertion_ids": [relation.assertion.id],
                "status": "accepted",
            }
        ),
    )
    assert {item.asset_ref.version for item in plan.manifest.objects} == {version_id}
    assert (
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest)).status
        == "SUCCEEDED"
    )
