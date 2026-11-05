# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fake vector cold/hot execution, original anchors and atomic publication."""

from pathlib import Path

from datakeel.storage.database import Database
from datakeel.storage.evidence_runs import extraction_report
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.vector_budget import list_vector_attempts
from tests.evidence.vector_helpers import vector_dataset, vector_run


def test_vector_cold_hot_zero_transport_and_original_anchors(db: Database, tmp_path: Path) -> None:
    """A hot run reuses embeddings and global comparisons while retaining exact original anchors."""
    dataset_id = vector_dataset(db, tmp_path / "inputs")
    cold = vector_run(db, dataset_id)
    assert cold.state == "COMPLETED", cold.error
    assert len(list_vector_attempts(db, cold.id)) == 3
    assertions = list_assertions(db)
    assert len(assertions) == 3
    assert all(item.predicate == "semantic_duplicate_of" for item in assertions)
    assert all(item.measurement is not None and len(item.anchors) == 2 for item in assertions)
    assert all(item.status == "candidate" for item in assertions)
    hot = vector_run(db, dataset_id)
    assert hot.state == "COMPLETED", hot.error
    assert list_vector_attempts(db, hot.id) == ()
    report = extraction_report(db, hot.id)
    assert all(item.vector is not None and item.vector.cache_hits == 3 for item in report.operators)
