# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The enterprise fixture preserves source hashes and runs only recorded extraction."""

from pathlib import Path

import pytest

from datakeel.core.errors import ExecutionError
from datakeel.core.kg_eval_models import KGCaseSuite
from datakeel.core.kg_queries import KGQuery
from datakeel.harness.enterprise_kg import (
    check_enterprise_extraction,
    enterprise_document_path,
    extract_enterprise_documents,
    import_enterprise_documents,
    seed_enterprise_kg,
)
from datakeel.kg.loader import load_contract
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_files
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_queries import query_kg
from datakeel.storage.kg_store import list_runs


def test_enterprise_replay_preserves_exact_source_and_recording_attribution(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All six passages complete without any real provider settings or source suffixes."""

    def forbidden() -> None:
        pytest.fail("Offline extraction attempted to read provider credentials")

    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", forbidden)
    fixture = seed_enterprise_kg(db, tmp_path)
    suite = load_contract(enterprise_document_path(), KGCaseSuite)
    assert len(list_files(db, fixture.dataset_id)) == 6
    for case in suite.cases:
        assert (tmp_path / "documents" / f"{case.id}.txt").read_text() == case.text
    graph = query_kg(db, KGQuery(dataset_id=fixture.dataset_id, limit=500))
    # One repeated triple has combined evidence when all passages share a dataset.
    assert len([item for item in graph.relations if item.assertion.predicate != "kg.same_as"]) == 44
    assert {item.model for item in graph.relations} == {"deepseek-flash"}
    assert all(item.cost_usd == 0 for item in list_traces(db))
    repeated = import_enterprise_documents(db, tmp_path / "documents")
    assert repeated == fixture
    extract_enterprise_documents(db, fixture)
    runs = list_runs(db, fixture.dataset_id, fixture.version_id)
    assert len(runs) == 2
    assert runs[0].report.cached == 6


def test_enterprise_fixture_reports_incomplete_extraction(db: Database, tmp_path: Path) -> None:
    """A missing worker report must not masquerade as a valid evaluation fixture."""
    fixture = import_enterprise_documents(db, tmp_path)
    with pytest.raises(ExecutionError, match="did not complete"):
        check_enterprise_extraction(db, fixture, "missing-task")
