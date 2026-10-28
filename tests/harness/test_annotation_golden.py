# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Annotation goldens read real saved metrics and approval history without a model."""

import socket
from pathlib import Path

import pytest

from datakeel.harness.annotation_cases import seed_annotation_qa_demo
from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case
from datakeel.storage.annotation_store import get_annotation_quality
from datakeel.storage.database import Database
from scripts.annotation_qa_mutations import ANNOTATION_QA_MUTATIONS
from scripts.generate_annotation_qa_demo import main
from scripts.mutate import run_mutation


def test_annotation_golden_reads_saved_three_reviewer_measurements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No golden setup, calculation or read may reach an external model or network."""

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("Annotation golden attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    case = next(item for item in load_cases() if item.id == "44-annotation-quality")
    result = run_case(case, "fake")
    assert result.passed, result.failures


def test_demo_import_reuses_saved_revisions_and_signed_inspection(
    db: Database, tmp_path: Path
) -> None:
    """Rerunning the demo preserves immutable batch IDs and a single approval history."""
    first = seed_annotation_qa_demo(db, tmp_path)
    second = seed_annotation_qa_demo(db, tmp_path)
    assert second == first
    overview = get_annotation_quality(db, first.dataset_id, first.version_id)
    assert len(overview.batches) == 2
    assert len(overview.inspections) == 1
    inspection = overview.inspections[0]
    plan = overview.sampling_plans[0]
    assert (plan.code_letter, plan.effective_code_letter, plan.sample_size) == ("C", "D", 8)
    assert (inspection.accepted, inspection.defective_count, inspection.acceptance_number) == (
        False,
        2,
        1,
    )
    comparison = overview.batches[0].comparison
    assert comparison is not None
    assert (comparison.inspection_defects, comparison.inspection_defects_changed) == (2, 2)


def test_generator_cli_imports_only_explicit_local_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The standalone command performs the same import and controlled approval as the demo."""
    path = tmp_path / "local" / "demo.db"
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate",
            "--output",
            str(tmp_path / "samples"),
            "--database",
            str(path),
        ],
    )
    main()
    assert path.is_file()


def test_annotation_golden_rejects_erased_real_measurements() -> None:
    """A tool that conceals the saved report fails its existing measured golden contract."""
    result = run_mutation(ANNOTATION_QA_MUTATIONS[0])
    assert result.killed
    assert "44-annotation-quality" in result.failures
