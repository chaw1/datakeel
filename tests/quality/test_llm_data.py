# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Training signals enter measured dimensions while existing image scores stay identical."""

from datakeel.core.llm_data_models import TrainingConfig, TrainingReport
from datakeel.core.models import FileItem
from datakeel.quality import score_quality


def test_training_measured_rows_reduce_relevant_dimensions_without_changing_weights() -> None:
    """Known structural, duplicate and PII counts affect the five-dimension quality result."""
    report = TrainingReport(
        config=TrainingConfig(),
        records=10,
        valid_records=9,
        issue_counts={"format_error": 1, "exact_duplicate": 2, "pii_email": 3},
    )
    file = FileItem(
        path="fixture.jsonl",
        filename="fixture.jsonl",
        modality="text",
        size=10,
        sha256="fixture-hash",
    )
    clean = score_quality([file])
    scored = score_quality(
        [file.model_copy(update={"metadata": {"training_quality": report.model_dump(mode="json")}})]
    )
    assert scored.dimensions["completeness"].score == 90
    assert scored.dimensions["consistency"].score == 70
    assert scored.dimensions["uniqueness"].score == 80
    assert scored.config == clean.config
    assert scored.total < clean.total
    assert scored.dimensions["distribution"] == clean.dimensions["distribution"]


def test_image_scores_ignore_training_metadata_and_remain_unchanged() -> None:
    """A training report cannot accidentally alter image quality or annotation weighting."""
    image = FileItem(
        path="fixture.png",
        filename="fixture.png",
        modality="image",
        size=20,
        sha256="image-hash",
        metadata={"width": 10, "height": 10},
    )
    report = TrainingReport(config=TrainingConfig(), records=1, issue_counts={"format_error": 1})
    with_training = image.model_copy(
        update={"metadata": {**image.metadata, "training_quality": report.model_dump(mode="json")}}
    )
    assert score_quality([image]) == score_quality([with_training])


def test_empty_training_reports_have_no_division_or_score_effect() -> None:
    """An empty measured source does not create invented fractions or new score weights."""
    report = TrainingReport(config=TrainingConfig())
    file = FileItem(path="fixture.jsonl", filename="fixture.jsonl", modality="text", size=0)
    assert score_quality([file]) == score_quality(
        [file.model_copy(update={"metadata": {"training_quality": report.model_dump(mode="json")}})]
    )
