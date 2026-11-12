# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Production schema anchors must reach the frozen DDL used by empty SQLite fixtures."""

from pathlib import Path

import pytest

from scripts.mutate import _copy_source, evaluate_image_test
from scripts.production_mutations import PRODUCTION_MUTATIONS


@pytest.mark.parametrize(
    ("name", "old_before", "old_after", "assertion"),
    [
        (
            "production-revision-append-only",
            'for table in ("production_revisions", "production_reviews"):',
            'for table in ("production_reviews",):',
            "Revision UPDATE and DELETE must be rejected by the database",
        ),
        (
            "production-exclusive-assignment",
            '"stage",\n            unique=True,',
            '"stage",\n            unique=False,',
            "The database must reject a duplicate active assignment",
        ),
    ],
)
def test_frozen_schema_anchor_kills_when_old_row_anchor_survives(
    tmp_path: Path, name: str, old_before: str, old_after: str, assertion: str
) -> None:
    """Measure green control, ineffective old target and new call assertion in isolated copies."""
    mutation = next(item for item in PRODUCTION_MUTATIONS if item.name == name)
    assert mutation.path == "versioning/sqlite_b3.json"
    assert mutation.source_root == "datakeel"
    assert mutation.runner == "pytest"
    _copy_source(tmp_path)
    baseline = evaluate_image_test(tmp_path, mutation.case)
    assert (baseline.exit_code, baseline.passed, baseline.total) == (0, 1, 1)
    rows = tmp_path / "datakeel/storage/production_rows.py"
    original = rows.read_text()
    assert original.count(old_before) == 1
    rows.write_text(original.replace(old_before, old_after))
    try:
        obsolete = evaluate_image_test(tmp_path, mutation.case)
        assert (obsolete.exit_code, obsolete.passed, obsolete.total) == (0, 1, 1)
    finally:
        rows.write_text(original)
    frozen = tmp_path / "datakeel" / mutation.path
    original = frozen.read_text()
    assert original.count(mutation.before) == 1
    frozen.write_text(original.replace(mutation.before, mutation.after))
    measured = evaluate_image_test(tmp_path, mutation.case)
    assert (measured.exit_code, measured.passed, measured.total) == (1, 0, 1)
    assert set(measured.failures) == {mutation.case}
    assert assertion in measured.failures[mutation.case][0]
