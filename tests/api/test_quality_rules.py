# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Monitor API reads the same persisted observations used by workers and reports."""

from pathlib import Path

from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_datasets
from datakeel.storage.governance_service import get_quality, get_report
from datakeel.worker.runner import run_worker
from tests.dq_support import execute_action, generated_rule, save_rule


def test_quality_reads_show_failure_history_and_pending_after_edit(
    db: Database, tmp_path: Path
) -> None:
    """A changed definition has no inherited verdict but historical results remain readable."""
    rule = generated_rule(db, tmp_path)
    save_rule(db, rule)
    with TestClient(create_app(db)) as client:
        assert client.get("/api/quality/summary").json()["pending"] == 1
        assert client.get("/api/quality/rules?table=missing").json() == []
        run = execute_action(db, "run_quality_rule", JsonDocument({"rule_id": rule.id}))
        assert run.task_id is not None
        run_worker(db, once=True)
        view = client.get(f"/api/quality/rules/{rule.id}").json()
        assert view["latest_result"]["status"] == "failed"
        assert (
            client.get("/api/quality/summary?source_id=orders-test&table=orders").json()["score"]
            == 0
        )
        assert len(client.get("/api/quality/issues").json()) == 1
        report_body = client.get("/api/quality/report").json()["body"]
        assert "orders-positive (orders): failed" in report_body
        execute_action(
            db,
            "update_quality_rule",
            JsonDocument({"rule": rule.model_dump(mode="json"), "expected_revision": 1}),
        )
        assert client.get(f"/api/quality/rules/{rule.id}").json()["latest_result"] is None
        assert len(client.get(f"/api/quality/rules/{rule.id}/results").json()) == 1
        assert len(client.get(f"/api/quality/rules/{rule.id}/history").json()) == 2
        assert client.get("/api/quality/rules/missing").status_code == 404
        assert client.get(f"/api/quality/rules/{rule.id}/results?limit=1001").status_code == 422
    assert not list_datasets(db)


def test_quality_score_and_report_use_associated_rule_evidence(
    db: Database, tmp_path: Path
) -> None:
    """Failing database evidence contributes half the score of a populated file dataset."""
    document = tmp_path / "healthy.txt"
    document.write_text("Generated healthy example")
    dataset = import_paths(db, "Generated quality association", [document])
    original = get_quality(db, dataset.id)
    rule = generated_rule(db, tmp_path).model_copy(update={"dataset_id": dataset.id})
    save_rule(db, rule)
    pending = get_quality(db, dataset.id)
    assert pending.total == original.total
    assert pending.rules is not None
    assert pending.rules.pending == 1
    execute_action(db, "run_quality_rule", JsonDocument({"rule_id": rule.id}))
    run_worker(db, once=True)
    measured = get_quality(db, dataset.id)
    assert measured.total == original.total / 2
    assert measured.dimensions["database_rules"].score == 0
    assert measured.rules is not None
    assert measured.rules.failed == 1
    assert "orders-positive: failed" in get_report(db, dataset.id).baseline
    assert [value.id for value in list_datasets(db)] == [dataset.id]
