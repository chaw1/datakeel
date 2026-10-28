# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Quality summaries distinguish missing evidence and preserve rule-only datasets."""

from typing import Literal

import pytest

from datakeel.core.dq_models import DqResult, DqRule
from datakeel.core.dq_monitor import DqCompletion
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.dq_jobs import schedule_rule
from datakeel.storage.dq_store import upsert_rule
from datakeel.storage.dq_views import read_report, read_rule_views, read_summary
from datakeel.storage.governance_service import (
    QualityInput,
    dataset_quality_summaries,
    get_quality,
    get_report,
    save_quality,
)
from datakeel.worker.queue import DatabaseQueue
from tests.storage.test_dq_store import definition


def _persist_rule(
    db: Database,
    rule: DqRule,
    status: Literal["passed", "failed", "error", "baseline_insufficient"] | None = None,
) -> None:
    with db.session() as session:
        upsert_rule(session, rule, None, "reviewer")
        if status is None:
            session.commit()
            return
        run = schedule_rule(session, rule.id, "generated-observation")
        session.commit()
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease is not None
    assert queue.finish(
        lease,
        [],
        [],
        evidence=DqCompletion(run_id=run.id, result=DqResult(rule_id=rule.id, status=status)),
    )


def test_summary_weights_verdicts_and_excludes_unmeasured_and_disabled(db: Database) -> None:
    """Errors fail closed while missing baselines and pending rules do not earn points."""
    _persist_rule(db, definition("passed"), "passed")
    _persist_rule(db, definition("warning").model_copy(update={"severity": "warn"}), "failed")
    _persist_rule(db, definition("error"), "error")
    _persist_rule(db, definition("baseline"), "baseline_insufficient")
    _persist_rule(db, definition("pending"))
    _persist_rule(db, definition("disabled"))
    with db.session() as session:
        upsert_rule(
            session, definition("disabled").model_copy(update={"enabled": False}), 1, "reviewer"
        )
        session.commit()
    summary = read_summary(db)
    assert summary.total == 5
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.errors == 1
    assert summary.baseline_insufficient == 1
    assert summary.pending == 1
    assert summary.score == 40
    assert summary.open_issues == 2
    assert read_summary(db, source_id="unknown").score is None
    assert read_rule_views(db, source_id="sample", table="other") == ()
    assert read_rule_views(db, schema_name="other") == ()
    assert "Database quality: 40.0/100" in read_report(db).body


@pytest.mark.parametrize("status", [None, "baseline_insufficient"])
def test_unmeasured_rules_preserve_existing_file_score(
    db: Database,
    status: Literal["baseline_insufficient"] | None,
) -> None:
    """Attaching a pending or cold-start rule exposes its state without changing a score."""
    dataset = import_paths(db, "Unmeasured generated dataset", [])
    original = get_quality(db, dataset.id)
    rule = definition().model_copy(update={"dataset_id": dataset.id})
    _persist_rule(db, rule, status)
    current = get_quality(db, dataset.id)
    assert current.total == original.total
    assert current.dimensions == original.dimensions
    assert current.rules is not None
    assert current.rules.score is None
    assert current.rules.total == 1
    assert current.rules.pending == int(status is None)
    assert current.rules.baseline_insufficient == int(status == "baseline_insufficient")


@pytest.mark.parametrize(
    ("status", "score", "grade"),
    [("passed", 100, "excellent"), ("failed", 0, "poor"), ("error", 0, "poor")],
)
def test_rule_only_dataset_score_reaches_reports_lists_and_saved_configuration(
    db: Database,
    status: Literal["passed", "failed", "error"],
    score: float,
    grade: str,
) -> None:
    """A table-only dataset gives measured rules full weight in every quality response."""
    dataset = import_paths(db, "Generated table quality", [])
    rule = definition().model_copy(update={"dataset_id": dataset.id})
    _persist_rule(db, rule, status)
    measured = get_quality(db, dataset.id)
    assert measured.file_count == 0
    assert measured.total == score
    assert measured.grade == grade
    assert measured.dimensions["database_rules"].weight == 100
    assert all(
        value.weight == 0 for key, value in measured.dimensions.items() if key != "database_rules"
    )
    assert len(measured.issues) == int(status != "passed")
    assert f"{rule.id}: {status}" in get_report(db, dataset.id).baseline
    assert dataset_quality_summaries(db)[0].quality_score == score
    saved = save_quality(db, dataset.id, QualityInput())
    assert saved.total == measured.total
    assert saved.rules == measured.rules
    assert saved.dimensions["database_rules"] == measured.dimensions["database_rules"]
