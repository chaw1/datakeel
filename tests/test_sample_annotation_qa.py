# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated annotation fixtures preserve their stated errors and deterministic repair history."""

from pathlib import Path

import pytest

from datakeel.annotation_qa import compare_rework, evaluate_annotations
from datakeel.core.annotation_models import AnnotationBatch
from datakeel.sample_annotation_qa import generate_annotation_qa_samples
from scripts.generate_annotation_qa_demo import main


def test_generated_panels_find_ten_error_types_and_measure_repair(tmp_path: Path) -> None:
    """The fictional panel exercises all declared suspicion families and one new regression."""
    samples = generate_annotation_qa_samples(tmp_path)
    result = evaluate_annotations(samples.initial)
    assert len(samples.paths) == 24
    assert {item.code for item in result.findings} == {
        "minority_label",
        "near_duplicate_conflict",
        "invalid_bbox",
        "invalid_span",
        "multilabel_conflict",
        "bbox_size_outlier",
        "bbox_aspect_outlier",
        "bbox_missing",
        "bbox_extra",
        "span_boundary_minority",
    }
    assert len(result.findings) == 19
    comparison = compare_rework(samples.initial, samples.reworked)
    assert (
        comparison.corrected_count,
        comparison.introduced_count,
        comparison.remaining_count,
        comparison.changed_records,
    ) == (19, 1, 0, 12)
    assert (
        AnnotationBatch.model_validate_json((tmp_path / "initial.json").read_text())
        == samples.initial
    )
    first_bytes = [path.read_bytes() for path in samples.paths]
    repeated = generate_annotation_qa_samples(tmp_path)
    assert repeated == samples
    assert [path.read_bytes() for path in repeated.paths] == first_bytes
    assert samples.paths[6].read_bytes() == samples.paths[7].read_bytes()


def test_generator_cli_without_database_writes_portable_panels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default invocation generates local files without opening a database."""
    monkeypatch.setattr("sys.argv", ["generate", "--output", str(tmp_path)])
    main()
    assert (tmp_path / "initial.json").is_file()
    assert (tmp_path / "reworked.json").is_file()
