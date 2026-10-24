# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The graph demo retains recorded, scripted and failed extraction evidence together."""

import socket

import pytest

from datakeel.cli.kg_demo import check_demo, demo_reports, seed_kg_demo
from datakeel.core.errors import ExecutionError
from datakeel.core.kg_queries import KGQuery
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_datasets, list_files
from datakeel.storage.kg_queries import explain_relation, query_kg
from datakeel.worker.runner import run_worker


def test_recorded_and_scripted_demo_share_one_visible_graph_without_network(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partial replay does not hide successful graph data or the independent long documents."""

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("Offline graph demonstration attempted network or credential access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", forbidden)
    seed = seed_kg_demo(db)
    assert len(list_files(db, seed.dataset_id)) == 28
    assert list_datasets(db)[0].metadata["kg_samples"] is True
    with pytest.raises(ExecutionError, match="did not finish"):
        check_demo(db, seed)
    run_worker(db, once=True)
    check_demo(db, seed)
    reports = {run.profile_id: run for run in demo_reports(db, seed)}
    replay, scripted = reports["replay-demo"], reports["fake-long"]
    assert replay.status == "partial"
    assert replay.report.documents == 25
    assert replay.report.failed == 1
    assert replay.report.failures[0].reason == "truncated"
    assert replay.report.proposals
    assert scripted.status == "completed"
    assert scripted.report.documents == 3
    assert scripted.report.blocks > 3
    assert scripted.extractor == "fake"
    assert scripted.model == "scripted-long-v1"
    graph = query_kg(db, KGQuery(dataset_id=seed.dataset_id, version_id=seed.version_id, limit=500))
    assert {relation.model for relation in graph.relations} == {replay.model, scripted.model}
    vivo = next(relation for relation in graph.relations if relation.tail.name == "Vivo")
    assert vivo.assertion.verification == "needs_review"
    assert "tail" in explain_relation(db, vivo.assertion.id).summary
    assert sum(run.report.input_tokens + run.report.output_tokens for run in reports.values()) == 0
    assert all(run.report.cost_usd == 0 for run in reports.values())


def test_demo_rerun_reuses_source_dataset_and_cached_successful_blocks(db: Database) -> None:
    """Re-extracting retries the deliberate failure while avoiding every successful replay call."""
    initial = seed_kg_demo(db)
    run_worker(db, once=True)
    repeated = seed_kg_demo(db)
    run_worker(db, once=True)
    assert initial.dataset_id == repeated.dataset_id
    assert initial.version_id == repeated.version_id
    assert len(list_datasets(db)) == 1
    assert len(list_files(db, repeated.dataset_id)) == 28
    reports = demo_reports(db, repeated)
    assert len(reports) == 2
    assert all(run.report.cached > 0 for run in reports)
    assert sum(run.report.failed for run in reports) == 1
