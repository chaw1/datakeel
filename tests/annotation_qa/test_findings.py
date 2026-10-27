# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated review scenarios, false-positive checks and repair/export regressions."""

import csv
import io
import json
from math import exp

import numpy as np
import pytest

from datakeel.annotation_qa import (
    compare_rework,
    export_rework_csv,
    export_rework_json,
    find_suspicions,
)
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationRecord,
    AnnotationSpan,
    NearDuplicatePair,
)


def _record(
    sample: str, annotator: str = "a", labels: tuple[str, ...] = ("yes",)
) -> AnnotationRecord:
    return AnnotationRecord(sample_id=sample, annotator_id=annotator, labels=labels)


def _box(width: float = 10, height: float = 10) -> tuple[AnnotationBox, ...]:
    return (AnnotationBox(category="item", x1=0, y1=0, x2=width, y2=height),)


def _dirty_batch() -> AnnotationBatch:
    records = [
        _record("minority", "a"),
        _record("minority", "b"),
        _record("minority", "c", ("no",)),
        _record("near-a"),
        _record("near-b", labels=("no",)),
        _record("multi", labels=("yes", "no")),
        _record("bad-span").model_copy(
            update={"spans": (AnnotationSpan(category="item", start=-1, end=3),), "text_length": 2}
        ),
        _record("bad-box").model_copy(update={"boxes": _box(-1)}),
        _record("large").model_copy(update={"boxes": _box(100, 100)}),
        _record("thin").model_copy(update={"boxes": _box(100, 1)}),
    ]
    records.extend(
        _record(f"normal-{index}").model_copy(update={"boxes": _box()}) for index in range(20)
    )
    return AnnotationBatch(
        annotations=tuple(records),
        near_duplicates=(NearDuplicatePair(sample_id="near-a", other_sample_id="near-b"),),
        exclusive_label_groups=(("yes", "no"),),
    )


def test_all_seven_injected_rule_types_are_discovered() -> None:
    """Each injected issue yields a reason, evidence, and an independent stable identity."""
    findings = find_suspicions(_dirty_batch())
    assert {item.code for item in findings} == {
        "minority_label",
        "near_duplicate_conflict",
        "bbox_size_outlier",
        "bbox_aspect_outlier",
        "invalid_bbox",
        "multilabel_conflict",
        "invalid_span",
    }
    assert all(item.reason and item.evidence for item in findings)
    assert len({item.finding_id for item in findings}) == len(findings)
    minority = [item for item in findings if item.code == "minority_label"]
    assert [(item.sample_id, item.annotator_id) for item in minority] == [("minority", "c")]


def test_generated_clean_data_false_positive_rate_below_two_percent() -> None:
    """One thousand lognormal boxes and unanimous varied labels have a conservative flag rate."""
    rng = np.random.default_rng(2026)
    records: list[AnnotationRecord] = []
    for index in range(1000):
        width, height = exp(float(rng.normal(3, 0.15))), exp(float(rng.normal(3, 0.15)))
        records.extend(
            _record(f"clean-{index}", annotator, ("yes" if index % 2 else "no",)).model_copy(
                update={"boxes": _box(width, height)}
            )
            for annotator in ("a", "b", "c")
        )
    findings = find_suspicions(AnnotationBatch(annotations=tuple(records)))
    assert len({item.sample_id for item in findings}) / 1000 <= 0.02


def test_ties_two_raters_missing_labels_and_unknown_pairs_do_not_guess_a_label() -> None:
    """Rules require sufficient evidence and do not treat absent labels as a dissenting vote."""
    batch = AnnotationBatch(
        annotations=(
            _record("tie", "a"),
            _record("tie", "b", ("no",)),
            _record("tie", "c", ("maybe",)),
            _record("two", "a"),
            _record("two", "b", ("no",)),
            _record("two", "c").model_copy(update={"labels": None}),
        ),
        near_duplicates=(
            NearDuplicatePair(sample_id="tie", other_sample_id="two"),
            NearDuplicatePair(sample_id="absent", other_sample_id="two"),
            NearDuplicatePair(sample_id="two", other_sample_id="two"),
        ),
    )
    assert find_suspicions(batch) == ()


def test_box_and_span_declared_boundaries_and_small_cohorts() -> None:
    """Out-of-bounds annotations are reviewable even in a cohort too small for statistics."""
    record = _record("s").model_copy(
        update={
            "boxes": _box(),
            "image_width": 5,
            "image_height": 5,
            "text_length": 4,
            "spans": (
                AnnotationSpan(category="item", start=0, end=5),
                AnnotationSpan(category="item", start=2, end=2),
            ),
        }
    )
    findings = find_suspicions(AnnotationBatch(annotations=(record,)))
    assert [item.code for item in findings].count("invalid_span") == 2
    assert [item.code for item in findings].count("invalid_bbox") == 1


def test_rework_counts_corrections_remaining_and_introduced_errors() -> None:
    """Repair changes only finding identities, while exporting preserves all evidence."""
    before = _dirty_batch()
    records = tuple(
        item.model_copy(update={"labels": ("yes",)}) if item.sample_id == "multi" else item
        for item in before.annotations
    )
    new = _record("new").model_copy(
        update={"spans": (AnnotationSpan(category="item", start=3, end=1),)}
    )
    after = before.model_copy(update={"annotations": (*records, new)})
    comparison = compare_rework(before, after)
    assert comparison.corrected_count == 1
    assert comparison.introduced_count == 1
    assert comparison.remaining_count == comparison.before_count - 1
    assert comparison.unassessed_count == 0
    assert comparison.corrected[0].sample_id == "multi"
    rows = list(csv.DictReader(io.StringIO(export_rework_csv(comparison.corrected))))
    assert rows[0]["sample_id"] == "multi"
    exported = json.loads(export_rework_json(comparison.introduced))
    assert exported[0]["sample_id"] == "new"


def test_removed_record_or_missing_modality_cannot_count_as_repair() -> None:
    """Deleting an issue's sample, its peer, or its modality remains unassessed."""
    before = _dirty_batch()
    after = before.model_copy(
        update={
            "annotations": tuple(item for item in before.annotations if item.sample_id != "multi")
        }
    )
    result = compare_rework(before, after)
    assert result.unassessed_count == 1
    assert result.corrected_count == 0
    after = before.model_copy(
        update={
            "annotations": tuple(
                item.model_copy(update={"labels": None}) if item.sample_id == "multi" else item
                for item in before.annotations
            )
        }
    )
    assert compare_rework(before, after).unassessed_count == 1


def test_policy_changes_rejected_and_csv_formula_prefix_escaped() -> None:
    """Removing a rule is not repair, and opening an exported sample id cannot execute a formula."""
    before = _dirty_batch()
    with pytest.raises(ValueError, match="unchanged review policy"):
        compare_rework(before, before.model_copy(update={"exclusive_label_groups": ()}))
    malicious = _record("=1+1", labels=("yes", "no"))
    findings = find_suspicions(
        AnnotationBatch(annotations=(malicious,), exclusive_label_groups=(("yes", "no"),))
    )
    assert "'=1+1" in export_rework_csv(findings)
    assert json.loads(export_rework_json(findings))[0]["sample_id"] == "=1+1"
    assert list(csv.DictReader(io.StringIO(export_rework_csv(())))) == []


def test_same_annotator_duplicate_boxes_and_spans() -> None:
    """Near-identical boxes or identical span offsets from one annotator are reported once."""
    box = AnnotationBox(category="item", x1=0, y1=0, x2=10, y2=10)
    record = _record("dup").model_copy(
        update={
            "boxes": (
                box,
                box.model_copy(update={"x2": 10.5}),
                box.model_copy(update={"x1": 30, "x2": 40}),
            ),
            "spans": (
                AnnotationSpan(category="A", start=0, end=4),
                AnnotationSpan(category="B", start=0, end=4),
                AnnotationSpan(category="A", start=2, end=6),
            ),
        }
    )
    findings = find_suspicions(AnnotationBatch(annotations=(record,)))
    assert sorted(item.code for item in findings) == ["duplicate_bbox", "duplicate_span"]


def test_near_duplicate_uses_strict_majorities_and_flags_majority_holders() -> None:
    """A 2-of-3 majority on each side is enough; the dissenting rater is a minority instead."""
    records = [
        _record("left", "a"),
        _record("left", "b"),
        _record("left", "c", ("no",)),
        _record("right", "a", ("no",)),
        _record("right", "b", ("no",)),
        _record("right", "c", ("no",)),
    ]
    batch = AnnotationBatch(
        annotations=tuple(records),
        near_duplicates=(NearDuplicatePair(sample_id="left", other_sample_id="right"),),
    )
    duplicate = sorted(
        (item.sample_id, item.annotator_id)
        for item in find_suspicions(batch)
        if item.code == "near_duplicate_conflict"
    )
    assert duplicate == [
        ("left", "a"),
        ("left", "b"),
        ("right", "a"),
        ("right", "b"),
        ("right", "c"),
    ]


def test_rework_reports_record_level_changes() -> None:
    """Changed, unchanged, added and removed sample/annotator records are counted directly."""
    before = _dirty_batch()
    records = [
        item.model_copy(update={"labels": ("yes",)}) if item.sample_id == "multi" else item
        for item in before.annotations
        if item.sample_id != "normal-0"
    ]
    after = before.model_copy(update={"annotations": (*records, _record("extra-sample"))})
    result = compare_rework(before, after)
    total = len(before.annotations)
    assert (result.changed_records, result.added_records, result.removed_records) == (1, 1, 1)
    assert result.unchanged_records == total - 2
