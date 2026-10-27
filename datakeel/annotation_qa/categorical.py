# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Nominal agreement estimates implemented directly from published definitions."""

from collections import Counter
from collections.abc import Sequence

import numpy as np

from datakeel.core.annotation_models import AgreementValue

type Nominal = str | int | tuple[str, ...]
type Rating = Nominal | None


def _estimate(observed: float, expected: float, count: int) -> AgreementValue:
    if expected >= 1:
        return AgreementValue(
            value=None,
            observed_agreement=observed,
            sample_count=count,
            reason="No expected disagreement: the chance-corrected estimate is undefined",
        )
    return AgreementValue(
        value=float((observed - expected) / (1 - expected)),
        observed_agreement=observed,
        sample_count=count,
    )


def cohen_kappa(left: Sequence[Rating], right: Sequence[Rating]) -> AgreementValue:
    """Compute Cohen's nominal kappa on paired nonmissing observations.

    Categories may be full multilabel tuples; their order must be canonicalized by
    the caller. A single observed category is explicitly undefined, not perfect.
    """
    if len(left) != len(right):
        message = "Cohen ratings must have equal lengths"
        raise ValueError(message)
    paired = [(a, b) for a, b in zip(left, right, strict=True) if a is not None and b is not None]
    count = len(paired)
    if not count:
        return AgreementValue(value=None, reason="No paired ratings")
    left_counts = Counter(a for a, _ in paired)
    right_counts = Counter(b for _, b in paired)
    observed = float(np.mean([a == b for a, b in paired]))
    expected = sum(n * right_counts[label] for label, n in left_counts.items()) / count**2
    return _estimate(observed, expected, count)


def _counts(rows: Sequence[Sequence[Nominal]]) -> np.ndarray[tuple[int, int], np.dtype[np.float64]]:
    categories = list(dict.fromkeys(value for row in rows for value in row))
    return np.asarray(
        [[Counter(row)[category] for category in categories] for row in rows], dtype=np.float64
    )


def fleiss_kappa(ratings: Sequence[Sequence[Rating]]) -> AgreementValue:
    """Compute Fleiss kappa with equal numbers of nonmissing ratings per unit.

    Rows are units. Completely missing rows are excluded. Unequal panel sizes
    produce an explicit undefined result; Krippendorff alpha handles that case.
    """
    rows = [[value for value in row if value is not None] for row in ratings]
    rows = [row for row in rows if row]
    sizes = {len(row) for row in rows}
    if not rows or len(sizes) != 1 or min(sizes) < 2:  # noqa: PLR2004  # Agreement needs two ratings.
        return AgreementValue(
            value=None,
            sample_count=len(rows),
            reason="Fleiss kappa requires a constant panel size of at least two",
        )
    counts = _counts(rows)
    panel = len(rows[0])
    observed = float(np.mean((np.sum(counts**2, axis=1) - panel) / (panel * (panel - 1))))
    proportions = np.sum(counts, axis=0) / (len(rows) * panel)
    expected = float(np.sum(proportions**2))
    return _estimate(observed, expected, len(rows))


def krippendorff_alpha(ratings: Sequence[Sequence[Rating]]) -> AgreementValue:
    """Compute nominal alpha using pairable-unit coincidence weights.

    Missing ratings and units with fewer than two observations contribute no
    coincidences, including no category marginals. Expected disagreement uses
    sampling without replacement, including its finite-sample correction.
    """
    rows = [[value for value in row if value is not None] for row in ratings]
    rows = [row for row in rows if len(row) > 1]
    if not rows:
        return AgreementValue(value=None, reason="No pairable units")
    counts = _counts(rows)
    sizes = np.sum(counts, axis=1)
    total = float(np.sum(sizes))
    disagreement = float(np.sum((sizes**2 - np.sum(counts**2, axis=1)) / (sizes - 1))) / total
    marginals = np.sum(counts, axis=0)
    expected = float((total**2 - np.sum(marginals**2)) / (total * (total - 1)))
    return _estimate(1 - disagreement, 1 - expected, len(rows))
