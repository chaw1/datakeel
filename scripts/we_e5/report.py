# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measured numerical comparison with explicit floating boundary disagreements."""

import hashlib
from time import perf_counter

from datakeel.core.models import BoundaryModel
from datakeel.core.vector_results import VectorSample
from scripts.we_e5.metrics import quality
from scripts.we_e5.models import BackendResult, NumericInput, Quality, RecordedFacts
from scripts.we_e5.numeric import (
    decisions,
    f64_scores,
    faiss_scores,
    float_differences,
    normalized,
    production_result,
)


class NumericReport(BoundaryModel):
    """Keep both branches and raw differences; never collapse disagreement into a pass rate."""

    recorded_worker: RecordedFacts | None = None
    worker_f64_differences: tuple[str, ...] = ()
    worker_faiss_differences: tuple[str, ...] = ()
    input: NumericInput
    normalized_f32_hashes: tuple[str, ...]
    f64: BackendResult
    faiss: BackendResult
    f64_quality: Quality
    faiss_quality: Quality
    float_error: dict[str, float | int]
    decision_differences: tuple[str, ...]
    f64_wall_seconds: float
    faiss_wall_seconds: float
    normalization_wall_seconds: float
    real_spend_cny: int = 0
    fake_usage: int = 0
    fake_price: int = 0
    semantic_quality: str = "not_tested"
    cloud_latency: str = "not_tested"


def compare(case: NumericInput) -> NumericReport:
    """Time each exact branch separately, over a single shared F32 normalization boundary."""
    started = perf_counter()
    samples = normalized(case)
    normalization_seconds = perf_counter() - started
    started = perf_counter()
    f64 = f64_scores(samples)
    product = production_result(samples, f64, case)
    f64_seconds = perf_counter() - started
    started = perf_counter()
    raw_faiss = faiss_scores(samples)
    # Production cosine has a closed range. Preserve raw F32 values in float_error below.
    faiss = tuple(tuple(max(-1.0, min(1.0, v)) for v in row) for row in raw_faiss)
    candidate = decisions(samples, faiss, case)
    faiss_seconds = perf_counter() - started
    return NumericReport(
        input=case,
        normalized_f32_hashes=tuple(_hash(sample) for sample in samples),
        f64=product,
        faiss=candidate,
        f64_quality=quality(case, product),
        faiss_quality=quality(case, candidate),
        float_error=float_differences(f64, raw_faiss),
        decision_differences=tuple(
            key
            for key in BackendResult.model_fields
            if getattr(product, key) != getattr(candidate, key)
        ),
        f64_wall_seconds=f64_seconds,
        faiss_wall_seconds=faiss_seconds,
        normalization_wall_seconds=normalization_seconds,
    )


def _hash(sample: VectorSample) -> str:
    return hashlib.sha256(sample.f32_bytes()).hexdigest()


def worker_comparison(report: NumericReport, facts: RecordedFacts) -> NumericReport:
    """Report normalization-induced decision differences from the original committed F64 facts."""

    def differences(result: BackendResult) -> tuple[str, ...]:
        clusters = tuple(
            sorted(
                {
                    tuple(
                        t
                        for t, group in zip(report.input.targets, result.labels, strict=True)
                        if group == label
                    )
                    for label in set(result.labels)
                    if label >= 0
                }
            )
        )
        derived = RecordedFacts(
            pairs=result.pairs, clusters=clusters, noise=result.noise, gaps=result.gaps
        )
        return tuple(
            key
            for key in RecordedFacts.model_fields
            if getattr(derived, key) != getattr(facts, key)
        )

    return report.model_copy(
        update={
            "recorded_worker": facts,
            "worker_f64_differences": differences(report.f64),
            "worker_faiss_differences": differences(report.faiss),
        }
    )
