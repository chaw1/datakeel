# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The synthetic comparison catches every planted failure and no clean-table failures."""

from pathlib import Path

from datakeel.core.models import JsonDocument
from datakeel.harness.standard_cases import seed_standard_demo
from datakeel.sample_standards import DEMO_VIOLATIONS
from datakeel.storage.database import Database
from datakeel.storage.standard_store import history
from tests.standards_support import approved_change


def test_demo_catches_exact_planted_failures_and_preserves_clean_table(
    db: Database, tmp_path: Path
) -> None:
    """Keep expected rule counts independent of the implementation's check summaries."""
    report = seed_standard_demo(db, tmp_path / "sources")
    dirty = {
        check.column_id.rsplit("/", 1)[-1]: {item.rule: item.count for item in check.violations}
        for check in report.checks
        if "dirty_customers" in check.column_id and check.violations
    }
    assert dirty == DEMO_VIOLATIONS
    assert all(
        not check.violations and check.fully_checked
        for check in report.checks
        if "clean_customers" in check.column_id
    )
    assert report.coverage.overall.total_columns == 18
    assert report.coverage.overall.mapped_columns == 16
    assert report.coverage.overall.compliant_columns == 9
    assert report.coverage.owners[0].key == "Demo steward"
    assert all(not item.values for item in report.profiles)
    assert "contact@example.org" not in report.model_dump_json()


def test_demo_replay_does_not_add_mappings_or_overwrite_changed_definitions(
    db: Database, tmp_path: Path
) -> None:
    """Repeated local demo setup reuses both source files and the confirmed revision."""
    first = seed_standard_demo(db, tmp_path / "sources")
    revision = history(db).revisions[-1].revision
    second = seed_standard_demo(db, tmp_path / "sources")
    assert second == first
    assert history(db).revisions[-1].revision == revision


def test_demo_resumes_partial_mapping_setup_and_preserves_manual_reassignment(
    db: Database, tmp_path: Path
) -> None:
    """A single confirmed column is insufficient evidence that setup finished."""
    seed_standard_demo(db, tmp_path / "sources")
    approved_change(db, "rollback_standards", JsonDocument({"revision": 2}))
    approved_change(
        db,
        "confirm_standard_mapping",
        JsonDocument(
            {
                "mapping": {
                    "column_id": "standards_demo/main/clean_customers/customer_id",
                    "standard_code": "record_id",
                }
            }
        ),
    )
    report = seed_standard_demo(db, tmp_path / "sources")
    assert len(report.mappings) == 16
    manual = next(
        item
        for item in report.mappings
        if item.column_id == "standards_demo/main/clean_customers/customer_id"
    )
    assert manual.standard_code == "record_id"
