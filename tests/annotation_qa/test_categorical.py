# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Published numerical agreement examples and undefined/missing boundaries."""

import pytest
from pydantic import ValidationError

from datakeel.annotation_qa import evaluate_annotations
from datakeel.annotation_qa.categorical import cohen_kappa, fleiss_kappa, krippendorff_alpha
from datakeel.core.annotation_models import AnnotationBatch, AnnotationRecord


def test_cohen_author_numerical_example() -> None:
    """Cohen's 1986 Citation Classic: Po=.95, Pe=.82, kappa=.72 rounded.

    https://garfield.library.upenn.edu/classics1986/A1986AXF2600001.pdf
    The author's marginal prevalences are .1/.9 for each rater; 200 units
    realize those prevalences and .95 agreement with integer cell counts.
    """
    left = [1] * 20 + [0] * 180
    right = [1] * 15 + [0] * 5 + [1] * 5 + [0] * 175
    result = cohen_kappa(left, right)
    assert result.value == pytest.approx(13 / 18)
    assert result.observed_agreement == pytest.approx(0.95)


def test_fleiss_published_ten_subject_example() -> None:
    """Xie et al. (2017), Table 1: ten units, fourteen raters, kappa=.210.

    https://doi.org/10.20319/lijhls.2017.32.115, pp. 12-13.
    The displayed rounded answer is .210; full precision is checked below.
    """
    counts = [
        [0, 0, 0, 0, 14],
        [0, 2, 6, 4, 2],
        [0, 0, 3, 5, 6],
        [0, 3, 9, 2, 0],
        [2, 2, 8, 1, 1],
        [7, 7, 0, 0, 0],
        [3, 2, 6, 3, 0],
        [2, 5, 3, 2, 2],
        [6, 5, 2, 1, 0],
        [0, 2, 2, 3, 7],
    ]
    ratings = [[label for label, count in enumerate(row) for _ in range(count)] for row in counts]
    assert fleiss_kappa(ratings).value == pytest.approx(0.20993070442195522)


def test_alpha_krippendorff_missing_data_example() -> None:
    """Krippendorff (2011, updated 2013), section C, pp. 4-5: alpha=.743.

    https://www.asc.upenn.edu/krippendorffs-alpha-reliability links the author PDF.
    Its 4x12 example has seven missing ratings and one excluded singleton.
    """
    observers = [
        [1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None],
        [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3],
        [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None],
        [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None],
    ]
    result = krippendorff_alpha(list(zip(*observers, strict=True)))
    assert result.value == pytest.approx(0.743421052631579)
    assert result.sample_count == 11


@pytest.mark.parametrize("ratings", [[], [[None]], [["a"]], [[None, None]]])
def test_insufficient_ratings_are_explicitly_undefined(ratings: list[list[str | None]]) -> None:
    """Undefined values serialize as null rather than NaN or fabricated reliability."""
    assert fleiss_kappa(ratings).value is None
    assert krippendorff_alpha(ratings).value is None


def test_agreement_degenerate_and_negative_boundaries() -> None:
    """All-same marginals are undefined; diverse agreement is one; opposition is negative."""
    assert cohen_kappa(["a"], ["a"]).value is None
    assert cohen_kappa([], []).reason == "No paired ratings"
    assert cohen_kappa(["a", "b"], ["a", "b"]).value == 1
    assert cohen_kappa(["a", "b"], ["b", "a"]).value == -1
    assert fleiss_kappa([["a", "a"], ["b", "b"]]).value == 1
    assert fleiss_kappa([["a", "b"], ["b", "a"]]).value == -1
    assert krippendorff_alpha([["a", "a"], ["b", "b"]]).value == 1
    assert krippendorff_alpha([["a", "b"], ["b", "a"]]).value == pytest.approx(-0.5)
    assert krippendorff_alpha([["a", "a"]]).value is None


def test_missing_ratings_do_not_pollute_alpha_marginals() -> None:
    """Singleton categories cannot alter alpha's coincidence marginals."""
    baseline = [["a", "b"], ["a", "a"]]
    assert krippendorff_alpha([*baseline, ["unpaired", None]]) == krippendorff_alpha(baseline)
    assert cohen_kappa(["a", None, "b"], ["a", "a", "b"]).sample_count == 2
    assert fleiss_kappa([["a", "b"], ["a", None]]).value is None
    with pytest.raises(ValueError, match="equal lengths"):
        cohen_kappa(["a"], [])


def test_multilabel_order_empty_and_binary_confusion() -> None:
    """Full label sets are nominal categories; empty is reviewed and None is missing."""
    batch = AnnotationBatch(
        annotations=(
            AnnotationRecord(sample_id="s1", annotator_id="a", labels=("x", "y")),
            AnnotationRecord(sample_id="s1", annotator_id="b", labels=("y", "x", "x")),
            AnnotationRecord(sample_id="s2", annotator_id="a", labels=()),
            AnnotationRecord(sample_id="s2", annotator_id="b", labels=("x",)),
            AnnotationRecord(sample_id="s3", annotator_id="a", labels=None),
            AnnotationRecord(sample_id="s3", annotator_id="b", labels=("x",)),
        )
    )
    result = evaluate_annotations(batch)
    pair = result.classification.pairs[0]
    assert pair.cohen_kappa.value == pytest.approx(1 / 3)
    assert pair.cohen_kappa.sample_count == 2
    x = next(item for item in pair.confusion if item.category == "x")
    assert (x.true_positive, x.false_positive, x.false_negative, x.true_negative) == (1, 1, 0, 0)
    assert (result.sample_count, result.annotator_count) == (3, 2)


def test_batch_duplicate_identity_rejected_and_empty_supported() -> None:
    """Do not overwrite multiple records for one sample and annotator."""
    item = AnnotationRecord(sample_id="s1", annotator_id="a")
    with pytest.raises(ValidationError, match="only once"):
        AnnotationBatch(annotations=(item, item))
    assert evaluate_annotations(AnnotationBatch(annotations=())).findings == ()


def test_extreme_prevalence_still_has_defined_kappa() -> None:
    """Chance agreement near one does not erase a mathematically defined coefficient."""
    ratings = ["common"] * 200_000 + ["rare"]
    assert cohen_kappa(ratings, ratings).value == 1


def test_cohen_textbook_two_by_two_example_and_nominal_confusion_matrix() -> None:
    """Fifty proposals: yes/yes 20, yes/no 5, no/yes 10, no/no 15; Po=.7, Pe=.5, kappa=.4.

    Worked example in the Wikipedia article "Cohen's kappa" (section "Simple
    example"); the same table is used in many introductory statistics texts.
    """
    left = ["yes"] * 25 + ["no"] * 25
    right = ["yes"] * 20 + ["no"] * 5 + ["yes"] * 10 + ["no"] * 15
    result = cohen_kappa(left, right)
    assert result.value == pytest.approx(0.4)
    assert result.observed_agreement == pytest.approx(0.7)
    batch = AnnotationBatch(
        annotations=tuple(
            AnnotationRecord(sample_id=f"s{index}", annotator_id=name, labels=(label,))
            for name, labels in (("a", left), ("b", right))
            for index, label in enumerate(labels)
        )
    )
    pair = evaluate_annotations(batch).classification.pairs[0]
    assert pair.categories == ("no", "yes")
    assert pair.matrix == ((15, 10), (5, 20))
    assert pair.cohen_kappa.value == pytest.approx(0.4)


def test_confusion_matrix_names_multilabel_and_empty_sets() -> None:
    """Label sets are single nominal categories, including a reviewed empty set."""
    batch = AnnotationBatch(
        annotations=(
            AnnotationRecord(sample_id="s1", annotator_id="a", labels=("y", "x")),
            AnnotationRecord(sample_id="s1", annotator_id="b", labels=()),
        )
    )
    pair = evaluate_annotations(batch).classification.pairs[0]
    assert pair.categories == ("(empty)", "x+y")
    assert pair.matrix == ((0, 0), (1, 0))
