# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent count-based contract metrics, without sklearn or inferred semantic gold."""

from collections import Counter
from math import comb, fsum, log

from scripts.we_e5.models import BackendResult, NumericInput, Quality, Score


def score[Item](predicted: set[Item], expected: set[Item]) -> Score:
    """Use 1 for a completely empty match, otherwise 0 for an undefined denominator."""
    matched = len(predicted & expected)
    precision = matched / len(predicted) if predicted else float(not expected)
    recall = matched / len(expected) if expected else float(not predicted)
    return Score(
        precision=precision,
        recall=recall,
        f1=2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        true_positive=matched,
        predicted=len(predicted),
        expected=len(expected),
    )


def clustering(gold: tuple[int, ...], predicted: tuple[int, ...]) -> tuple[float, float]:
    """Compute ARI and arithmetic NMI; each noise point is its own singleton cluster."""
    if len(gold) != len(predicted):
        msg = "cluster_gold_length_mismatch"
        raise ValueError(msg)
    left = tuple(str(v) if v >= 0 else f"noise-{i}" for i, v in enumerate(gold))
    right = tuple(str(v) if v >= 0 else f"noise-{i}" for i, v in enumerate(predicted))
    table = Counter(zip(left, right, strict=True))
    rows, columns = Counter(left), Counter(right)
    count = len(gold)
    if count <= 1:
        return 1.0, 1.0
    same = sum(comb(v, 2) for v in table.values())
    a, b = (sum(comb(v, 2) for v in group.values()) for group in (rows, columns))
    expected = a * b / comb(count, 2)
    maximum = (a + b) / 2
    ari = (same - expected) / (maximum - expected) if maximum != expected else 1.0
    mutual = fsum(
        v / count * log(v * count / (rows[r] * columns[c])) for (r, c), v in table.items()
    )
    entropy_left, entropy_right = (
        -fsum(v / count * log(v / count) for v in group.values()) for group in (rows, columns)
    )
    entropy = (entropy_left + entropy_right) / 2
    return ari, mutual / entropy if entropy else 1.0


def quality(case: NumericInput, result: BackendResult) -> Quality:
    """Score only supplied synthetic gold; every unsupported dimension stays not_available."""
    unavailable = "not_available"
    removal = pair = noise = gap = unavailable
    survival = exactly = ari = nmi = unavailable
    if case.duplicate_gold is not None:
        groups: dict[str, list[str]] = {}
        if len(case.duplicate_gold) != len(case.targets):
            msg = "duplicate_gold_length_mismatch"
            raise ValueError(msg)
        for identity, label in zip(case.targets, case.duplicate_gold, strict=True):
            groups.setdefault(label, []).append(identity)
        removals = {item for members in groups.values() for item in sorted(members)[1:]}
        removal = score(set(result.removed), removals)
        expected_pairs = {
            (a, b) for members in groups.values() for a in members for b in members if a < b
        }
        pair = score(set(result.pairs), expected_pairs)
        survivors = [len(set(members) - set(result.removed)) for members in groups.values()]
        survival = sum(v > 0 for v in survivors) / len(survivors) if survivors else 1.0
        exactly = sum(v == 1 for v in survivors) / len(survivors) if survivors else 1.0
    if case.cluster_gold is not None:
        ari, nmi = clustering(case.cluster_gold, result.labels)
        expected_noise: set[str] = (
            set()
            if len(case.targets) < case.min_samples
            else {
                t for t, label in zip(case.targets, case.cluster_gold, strict=True) if label == -1
            }
        )
        noise = score(set(result.noise), expected_noise)
    if case.gap_gold is not None:
        gap = score({t for t, _ in result.gaps}, set(case.gap_gold))
    return Quality(
        gold_kind="synthetic_contract_only"
        if any(v is not None for v in (case.duplicate_gold, case.cluster_gold, case.gap_gold))
        else unavailable,
        removal=removal,
        survival=survival,
        exactly_one=exactly,
        direct_pair=pair,
        ari=ari,
        nmi=nmi,
        noise=noise,
        gap=gap,
    )
