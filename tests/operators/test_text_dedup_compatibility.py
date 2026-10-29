# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve established document deduplication independently of training record rules."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.operators import REGISTRY
from datakeel.pipeline import run_pipeline
from datakeel.quality.scoring import score_quality
from datakeel.sample import generate_samples

if TYPE_CHECKING:
    from pathlib import Path

    from tests.operators.factories import FileFactory


def test_exact_only_preserves_punctuation_and_width_but_folds_case_and_whitespace(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Document exact identity ignores case/spacing without adopting training normalization."""
    files = [
        make_file("Alpha beta."),
        make_file(" ALPHA\t beta.\n"),
        make_file("Alpha beta!"),
        make_file("\uff21\uff4c\uff50\uff48\uff41 beta."),
        make_file(" "),
        make_file("\n\t"),
    ]
    result = REGISTRY["text.dedup"].run(files, output_dir, {"approximate": False})
    assert result.files == [files[index] for index in (0, 2, 3, 4)]
    assert result.quality["issues"] == [
        {"file_id": files[index].id, "code": "text_duplicate", "severity": "info"}
        for index in (1, 5)
    ]


def test_approximate_documents_use_token_sets_regardless_of_word_order(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Reordered words remain approximate duplicates under the existing Jaccard contract."""
    files = [make_file("alpha beta gamma delta"), make_file("delta gamma beta alpha")]
    result = REGISTRY["text.dedup"].run(files, output_dir)
    assert result.files == files[:1]
    assert result.quality["removed_count"] == 1


@pytest.mark.parametrize(("threshold", "retained"), [(0.5, 1), (2 / 3, 1), (0.667, 2), (1, 2)])
def test_approximate_documents_include_the_configured_jaccard_boundary(
    make_file: FileFactory, output_dir: Path, threshold: float, retained: int
) -> None:
    """Two shared tokens out of three count as a duplicate at the inclusive boundary."""
    files = [make_file("alpha beta"), make_file("alpha beta gamma")]
    result = REGISTRY["text.dedup"].run(files, output_dir, {"threshold": threshold})
    assert result.files == files[:retained]


def test_approximate_documents_only_compare_against_retained_representatives(
    make_file: FileFactory, output_dir: Path
) -> None:
    """An already removed bridge cannot make a distinct later document disappear."""
    files = [make_file("alpha beta"), make_file("alpha beta gamma"), make_file("beta gamma")]
    result = REGISTRY["text.dedup"].run(files, output_dir, {"threshold": 0.6})
    assert result.files == [files[0], files[2]]
    assert result.quality["issues"] == [
        {"file_id": files[1].id, "code": "text_duplicate", "severity": "info"}
    ]


def test_generated_notes_preserve_baseline_files_pipeline_and_quality(tmp_path: Path) -> None:
    """The real generated demo keeps every distinct observation and its original quality."""
    files = [
        FileItem(
            path=str(path),
            filename=path.name,
            modality="image" if path.suffix == ".png" else "text",
            size=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in generate_samples(tmp_path / "input")
    ]
    texts = [file for file in files if file.modality == "text"]
    direct = REGISTRY["text.dedup"].run(texts, tmp_path / "direct")
    assert direct.files == texts[:199]
    assert direct.quality["removed_count"] == 1
    assert direct.quality["issues"] == [
        {"file_id": texts[199].id, "code": "text_duplicate", "severity": "info"}
    ]
    events = []
    output = run_pipeline(files, tmp_path / "pipeline", on_event=events.append)
    text_output = [file for file in output if file.modality == "text"]
    assert [file.filename for file in text_output] == [file.filename for file in texts[:198]]
    assert len(output) == 398
    dedup_event = next(event for event in events if event.operator == "text.dedup")
    assert (dedup_event.input_count, dedup_event.output_count) == (198, 198)
    assert dedup_event.quality["removed_count"] == 0
    assert all("training_quality" not in file.metadata for file in output)
    quality = score_quality(output)
    assert quality.total == 100
    assert {name: dimension.score for name, dimension in quality.dimensions.items()} == {
        "completeness": 100,
        "consistency": 100,
        "uniqueness": 100,
        "annotation": 0,
        "distribution": 100,
    }
