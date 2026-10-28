# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Multi-select conflicts and singleton categories from batch statistics."""

from typing import Literal

from datakeel.annotation_qa.labels import multiselect_findings, rare_category_findings
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationRecord,
)


def _batch(
    labels: list[tuple[str, ...]],
    mode: Literal["auto", "single", "multi"] = "auto",
    groups: tuple[tuple[str, ...], ...] = (),
) -> AnnotationBatch:
    return AnnotationBatch(
        annotations=tuple(
            AnnotationRecord(sample_id=f"s{index}", annotator_id="a", labels=value)
            for index, value in enumerate(labels)
        ),
        label_mode=mode,
        exclusive_label_groups=groups,
    )


def _flagged(batch: AnnotationBatch) -> list[str]:
    return [item.sample_id for item in multiselect_findings(batch)]


def test_declared_group_and_declared_single_mode_flag_small_batches() -> None:
    """Declarations apply even where statistics have too few records."""
    assert _flagged(_batch([("x", "y"), ("x",)], groups=(("x", "y"),))) == ["s0"]
    assert _flagged(_batch([("x", "z"), ("x",)], mode="single")) == ["s0"]
    assert _flagged(_batch([("x", "z"), ("x",)])) == []


def test_single_select_behaviour_is_inferred_at_one_percent() -> None:
    """One multi-label record among 100 labelled records is a conflict; two are not."""
    single = [("cat",), ("dog",), ("bird",)] * 33
    assert _flagged(_batch([("cat", "dog"), *single[:99]])) == ["s0"]
    assert _flagged(_batch([("cat", "dog"), ("cat", "dog"), *single[:98]])) == []
    assert _flagged(_batch([("cat", "dog"), *single[:99]], mode="multi")) == []


def test_rare_cooccurrence_of_frequent_labels_is_a_conflict() -> None:
    """Day and night never co-occur except once, although independence predicts many."""
    labels = [("day", "car") if index % 2 else ("night", "car", "person") for index in range(120)]
    labels += [("day", "person")] * 20
    labels.append(("day", "night", "car"))
    findings = multiselect_findings(_batch(labels, mode="multi"))
    assert [item.sample_id for item in findings] == ["s140"]
    assert any("day+night co-occur in 1/141" in line for line in findings[0].evidence)


def test_frequent_independent_label_pairs_are_not_conflicts() -> None:
    """Pairs that co-occur often are ordinary multi-label annotations."""
    labels = [("a", "b"), ("a",), ("b",), ("a", "b", "c")] * 20
    assert _flagged(_batch(labels)) == []


def test_singleton_label_box_and_span_categories_need_a_population() -> None:
    """A category used once among at least 50 is a probable typo; small batches are exempt."""
    records = [
        AnnotationRecord(
            sample_id=f"s{index}",
            annotator_id="a",
            labels=("dog",) if index else ("dgo",),
            boxes=(
                AnnotationBox(category="car" if index != 3 else "cra", x1=0, y1=0, x2=10, y2=10),
            ),
        )
        for index in range(50)
    ]
    findings = rare_category_findings(AnnotationBatch(annotations=tuple(records)))
    assert sorted((item.sample_id, item.evidence[0]) for item in findings) == [
        ("s0", "label='dgo'; occurrences=1/50"),
        ("s3", "box='cra'; occurrences=1/50"),
    ]
    assert rare_category_findings(AnnotationBatch(annotations=tuple(records[:49]))) == ()
