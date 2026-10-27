# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Align shared audio with overlap-normalized FFT cross-correlation."""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from datakeel.core.errors import ValidationError
from datakeel.core.media_alignment import MediaAlignment
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, Params, annotate, summarize
from datakeel.operators.media.tools import decode_audio, probe_file

_SAMPLE_RATE = 16000
_MILLISECONDS = 1000
_MIN_ENERGY = 1e-12
_MIN_RECORDINGS = 2


class AlignParams(Params):
    """Bound the lag search and require distinct, strongly matching signals."""

    max_offset_seconds: float = Field(default=30.0, gt=0, le=300)
    min_overlap_ms: int = Field(default=500, ge=100, le=60000)
    min_correlation: float = Field(default=0.55, gt=0, le=1)
    max_secondary_ratio: float = Field(default=0.9, gt=0, lt=1)
    max_analysis_seconds: float = Field(default=120.0, ge=1, le=600)


def _energy(signal: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.concatenate((np.zeros(1), np.cumsum(signal * signal)))


def _normalized_correlation(
    reference: NDArray[np.float64], candidate: NDArray[np.float64], params: AlignParams
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    length = reference.size + candidate.size - 1
    fft_length = 1 << (length - 1).bit_length()
    spectrum = np.fft.rfft(candidate, n=fft_length) * np.conj(np.fft.rfft(reference, n=fft_length))
    circular = np.fft.irfft(spectrum, n=fft_length)
    correlation = np.concatenate((circular[-reference.size + 1 :], circular[: candidate.size]))
    lags = np.arange(-reference.size + 1, candidate.size, dtype=np.int64)
    reference_start = np.maximum(0, -lags)
    candidate_start = np.maximum(0, lags)
    overlap = np.minimum(reference.size - reference_start, candidate.size - candidate_start)
    reference_energy = _energy(reference)
    candidate_energy = _energy(candidate)
    denominator = np.sqrt(
        (reference_energy[reference_start + overlap] - reference_energy[reference_start])
        * (candidate_energy[candidate_start + overlap] - candidate_energy[candidate_start])
    )
    minimum_overlap = params.min_overlap_ms * _SAMPLE_RATE // _MILLISECONDS
    valid = (
        (overlap >= minimum_overlap)
        & (np.abs(lags) <= params.max_offset_seconds * _SAMPLE_RATE)
        & (denominator > _MIN_ENERGY)
    )
    scores = np.abs(correlation[valid]) / denominator[valid]
    return lags[valid], np.minimum(1.0, scores)


def _estimate(
    reference: NDArray[np.float64],
    candidate: NDArray[np.float64],
    reference_file_id: str,
    params: AlignParams,
) -> MediaAlignment:
    if min(reference.size, candidate.size) == 0:
        return MediaAlignment(reference_file_id=reference_file_id, reason="silence")
    reference = reference - float(np.mean(reference))
    candidate = candidate - float(np.mean(candidate))
    if (
        min(float(np.mean(reference * reference)), float(np.mean(candidate * candidate)))
        < _MIN_ENERGY
    ):
        return MediaAlignment(reference_file_id=reference_file_id, reason="silence")
    lags, scores = _normalized_correlation(reference, candidate, params)
    if not scores.size:
        return MediaAlignment(reference_file_id=reference_file_id, reason="no_common_signal")
    best = int(np.argmax(scores))
    peak = float(scores[best])
    # Ignore the main peak's local lobe, then reject similarly plausible distant lags.
    distant = np.abs(lags - lags[best]) > int(0.04 * _SAMPLE_RATE)
    secondary = float(np.max(scores[distant])) if np.any(distant) else 0.0
    ratio = secondary / max(peak, _MIN_ENERGY)
    reason = "no_common_signal" if peak < params.min_correlation else "ambiguous"
    if peak < params.min_correlation or ratio >= params.max_secondary_ratio:
        return MediaAlignment(reference_file_id=reference_file_id, reason=reason)
    return MediaAlignment(
        reference_file_id=reference_file_id,
        offset_ms=round(int(lags[best]) * _MILLISECONDS / _SAMPLE_RATE, 3),
        confidence=round(peak * (1.0 - ratio), 6),
        aligned=True,
        reason="matched",
    )


def estimate_alignment(
    reference: NDArray[np.float64],
    candidate: NDArray[np.float64],
    reference_file_id: str,
    params: AlignParams,
) -> MediaAlignment:
    """Return a distinct shared-signal lag or an explicit unalignable result.

    The waveform and its first difference are both examined. Differencing whitens
    the signal, so a dominant low-frequency hum or rumble no longer makes the true lag
    look periodic; the plain waveform keeps the best signal-to-noise ratio when hiss
    dominates the high band. Each must pass the same correlation and ambiguity checks
    on its own, and the more confident success is reported.
    """
    sample_limit = int(params.max_analysis_seconds * _SAMPLE_RATE)
    reference = reference[:sample_limit]
    candidate = candidate[:sample_limit]
    plain = _estimate(reference, candidate, reference_file_id, params)
    whitened = _estimate(np.diff(reference), np.diff(candidate), reference_file_id, params)
    successes = [result for result in (plain, whitened) if result.aligned]
    return max(successes, key=lambda result: result.confidence) if successes else plain


def execute(files: list[FileItem], _output_dir: Path, params: AlignParams) -> OperatorResult:
    """Annotate each audio or video recording relative to the first input."""
    if len(files) < _MIN_RECORDINGS or any(
        file.modality not in {"audio", "video"} for file in files
    ):
        msg = "media.align requires at least two audio or video recordings with audio tracks"
        raise ValidationError(msg)
    reference = (
        decode_audio(
            files[0], sample_rate=_SAMPLE_RATE, max_duration_seconds=params.max_analysis_seconds
        )
        if probe_file(files[0]).audio_tracks
        else np.zeros(0, dtype=np.float64)
    )
    output: list[FileItem] = []
    for index, file in enumerate(files):
        has_audio = bool(probe_file(file).audio_tracks)
        alignment = (
            MediaAlignment(
                reference_file_id=files[0].id,
                offset_ms=0.0,
                confidence=1.0,
                aligned=True,
                reason="reference",
            )
            if index == 0 and reference.size and np.any(reference)
            else estimate_alignment(
                reference,
                decode_audio(
                    file, sample_rate=_SAMPLE_RATE, max_duration_seconds=params.max_analysis_seconds
                ),
                files[0].id,
                params,
            )
            if has_audio
            else MediaAlignment(reference_file_id=files[0].id, reason="missing_audio")
        )
        output.append(annotate(file, media_alignment=alignment.model_dump(mode="json")))
    return summarize(files, output)


OPERATOR = Operator("media.align", "any", "alignment", AlignParams, execute)
