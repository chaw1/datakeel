# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep per-image routing, preserved-source attribution and safe failures visible end to end."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, NoReturn

import httpx
import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan
from datakeel.core.kg_queries import KGQuery
from datakeel.core.transcription_models import TranscriptionProfile
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_queries import explain_relation, query_kg
from datakeel.storage.kg_store import get_job
from datakeel.transcription.adapters import FakeTranscriber
from datakeel.transcription.factory import create_transcriber
from datakeel.transcription.images import normalize_image
from datakeel.transcription.transport import request_transcription
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import (
    image_dataset,
    install_transcriber,
    prepare_image,
    transcript,
    use_profile,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from datakeel.storage.database import Database
    from datakeel.transcription.quality import TranscriberAdapter


def _visual_profile() -> TranscriptionProfile:
    return TranscriptionProfile(
        id="visual-fixture",
        backend="vlm",
        mode="vlm",
        model="visual-first",
        base_url="https://vision.example/v1",
    )


def _forbidden(*_args: object, **_kwargs: object) -> NoReturn:
    pytest.fail("This generated fixture must not read credentials or contact a provider")


def test_ocr_override_uses_actual_attribution_without_visual_trace(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An OCR override traverses the real visual router without credentials or remote billing."""
    dataset = image_dataset(db, tmp_path)
    profile = use_profile(monkeypatch, _visual_profile())
    ocr = transcript().model_copy(update={"backend": "ocr", "model": "fixture-ocr"})
    engine = FakeTranscriber((ocr,))
    monkeypatch.setattr("datakeel.transcription.factory.get_settings", _forbidden)

    @contextmanager
    def factory(*_args: object, **_kwargs: object) -> Generator[TranscriberAdapter]:
        with (
            httpx.Client(transport=httpx.MockTransport(_forbidden), trust_env=False) as client,
            create_transcriber(profile, client=client, ocr=engine) as adapter,
        ):
            yield adapter

    monkeypatch.setattr("datakeel.worker.kg_transcription.create_transcriber", factory)
    install_adapter(monkeypatch, (pair_result(),))
    plan = prepare_image(db, dataset, mode_overrides={dataset.files[0].id: "ocr"})
    assert not plan.requires_approval
    run = execute_graph(db, plan)
    assert run.status == "completed"
    assert not engine.results
    observation = run.report.transcriptions[0]
    assert (observation.backend, observation.mode, observation.model) == (
        "ocr",
        "ocr",
        "fixture-ocr",
    )
    assert all(trace.call_type != "transcription" for trace in list_traces(db, run.id))
    relation = query_kg(db, KGQuery()).relations[0]
    assert (relation.transcriber, relation.transcription_model) == ("ocr", "fixture-ocr")
    assert relation.transcription_profile_id == profile.id
    explanation = explain_relation(db, relation.assertion.id)
    assert all(source.transcriber == "ocr" for source in explanation.sources)
    assert all(source.transcription_model == "fixture-ocr" for source in explanation.sources)


def test_partial_reextraction_preserves_mixed_relation_source_attribution(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A merged relation retains the untouched visual model while replacing only its OCR source."""
    dataset = image_dataset(db, tmp_path, count=2)
    profile = use_profile(monkeypatch, _visual_profile())
    install_transcriber(
        monkeypatch,
        (
            transcript().model_copy(update={"backend": "ocr", "model": "fixture-ocr"}),
            transcript().model_copy(
                update={"backend": "vlm", "mode": "vlm", "model": "visual-first"}
            ),
        ),
    )
    install_adapter(monkeypatch, (pair_result(),))
    plan = prepare_image(db, dataset, mode_overrides={dataset.files[0].id: "ocr"})
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    first = execute_graph(db, plan)
    original = query_kg(db, KGQuery()).relations[0]
    assert original.transcriber == "ocr, vlm"
    assert original.transcription_model == "fixture-ocr, visual-first"
    preserved = get_job(db, first.id).documents[1].asset_ref
    removed = get_job(db, first.id).documents[0].asset_ref
    use_profile(monkeypatch, profile.model_copy(update={"model": "visual-second"}))
    install_transcriber(
        monkeypatch,
        (
            transcript().model_copy(
                update={"backend": "vlm", "mode": "vlm", "model": "visual-second"}
            ),
        ),
    )
    plan = prepare_image(db, dataset, file_ids=[dataset.files[0].id])
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    second = execute_graph(db, plan)
    assert second.status == "completed"
    current = query_kg(db, KGQuery()).relations[0]
    refs = tuple(anchor.asset_ref for anchor in current.assertion.anchors)
    assert preserved in refs
    assert removed not in refs
    assert current.assertion.id != original.assertion.id
    assert current.transcriber == "vlm"
    assert current.transcription_model == "visual-first, visual-second"
    assert explain_relation(db, current.assertion.id).relation == current


def test_free_tier_failure_preserves_safe_report_message_and_provider_category(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quota diagnostics survive worker publication while arbitrary provider-body text does not."""
    dataset = image_dataset(db, tmp_path, count=2)
    profile = use_profile(monkeypatch, _visual_profile())
    monkeypatch.setattr("datakeel.transcription.factory.get_settings", _forbidden)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": "AllocationQuota.FreeTierOnly",
                    "message": "provider-body-must-stay-private",
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client:
        failure = request_transcription(
            profile,
            normalize_image((tmp_path / "image-0.png").read_bytes()),
            transcript(),
            client,
            "",
        )
    install_transcriber(monkeypatch, (failure, transcript()))
    extraction = install_adapter(monkeypatch, (pair_result(),))
    plan = prepare_image(db, dataset)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_graph(db, plan)
    assert len(requests) == 1
    assert run.status == "partial"
    assert run.report.failures[0].reason == "transcription:provider_quota_exhausted"
    assert run.report.transcriptions[0].error == "服务商额度不足"
    assert run.report.transcriptions[0].status == "failed"
    assert "provider-body-must-stay-private" not in run.model_dump_json()
    assert "AllocationQuota.FreeTierOnly" not in run.model_dump_json()
    assert extraction.calls == 1
    assert len(query_kg(db, KGQuery()).relations) == 1
