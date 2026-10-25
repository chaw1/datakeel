# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The image demo keeps pixel evidence, unlocated candidates and scripted failures visible."""

import socket

import pytest

from datakeel.cli.image_kg_demo import seed_image_kg_demo
from datakeel.cli.kg_demo import check_demo, demo_reports
from datakeel.core.kg_queries import KGQuery
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_datasets, list_files
from datakeel.storage.kg_queries import explain_relation, query_kg
from datakeel.worker.runner import run_worker


def test_image_demo_replays_without_network_and_retains_review_and_failure_evidence(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise real jobs, sources and status without a model service or credential read."""

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("Offline image demo attempted a network connection or credential read")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", forbidden)
    monkeypatch.setattr("datakeel.transcription.factory.get_settings", forbidden)
    seed = seed_image_kg_demo(db)
    assert len(list_files(db, seed.dataset_id)) == 11
    assert list_datasets(db)[0].metadata["image_kg_samples"] is True
    run_worker(db, once=True)
    check_demo(db, seed)
    reports = demo_reports(db, seed)
    assert any(run.report.transcription_failed == 1 for run in reports)
    failures = [item for run in reports for item in run.report.transcriptions if item.error]
    assert len(failures) == 1
    assert "scripted" in failures[0].filename
    assert failures[0].error == "truncated"
    graph = query_kg(db, KGQuery(dataset_id=seed.dataset_id, version_id=seed.version_id, limit=500))
    assert graph.relations
    assert all(relation.assertion.status == "candidate" for relation in graph.relations)
    assert any(relation.image_located is False for relation in graph.relations)
    located = next(relation for relation in graph.relations if relation.image_located)
    sources = explain_relation(db, located.assertion.id).sources
    assert any(source.image_url and source.width and source.height for source in sources)
    assert any(
        source.asset_ref.asset_type == "image_transcript" and source.text for source in sources
    )


def test_image_demo_reuses_dataset_and_successful_transcriptions(db: Database) -> None:
    """Repeat only the intentional failure while keeping successful model calls at zero."""
    first = seed_image_kg_demo(db)
    run_worker(db, once=True)
    repeated = seed_image_kg_demo(db)
    run_worker(db, once=True)
    check_demo(db, repeated)
    assert first.dataset_id == repeated.dataset_id
    assert first.version_id == repeated.version_id
    assert len(list_datasets(db)) == 1
    reports = demo_reports(db, repeated)
    successes = [item for run in reports for item in run.report.transcriptions if not item.error]
    assert len(successes) == 10
    assert all(item.cached for item in successes)
