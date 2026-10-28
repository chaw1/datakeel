# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic signal deductions and recording/clip report aggregates."""

from collections import Counter, defaultdict
from typing import Any

from datakeel.core.media_metadata import media_failure, media_metadata
from datakeel.core.media_models import (
    MediaFailure,
    MediaFileScore,
    MediaFileView,
    MediaInterval,
    MediaSummary,
)
from datakeel.core.models import FileItem


def interval_duration(intervals: list[MediaInterval], duration_ms: int) -> int:
    """Measure the union of bounded issue ranges without double counting overlaps."""
    end = 0
    total = 0
    for interval in sorted(intervals, key=lambda item: item.start_ms):
        start = min(duration_ms, max(end, interval.start_ms))
        stop = min(duration_ms, interval.end_ms)
        total += max(0, stop - start)
        end = max(end, stop)
    return total


def _loudness_penalty(media: MediaFileView) -> float:
    if media.metrics.get("loudness_measurable") is False:
        return 100.0
    deviation = media.metrics.get("loudness_deviation_lu")
    if isinstance(deviation, int | float):
        return min(100.0, abs(float(deviation)) * 3)
    loudness = media.metrics.get("integrated_lufs")
    target = media.metrics.get("target_lufs", -23)
    if isinstance(loudness, int | float) and isinstance(target, int | float):
        return min(100.0, abs(float(loudness) - float(target)) * 3)
    return 0.0


def _score(file: FileItem, media: MediaFileView) -> MediaFileScore:
    duration = media.probe.duration_ms
    invalid = [
        issue
        for issue in media.issues
        if issue.code not in {"audio_loudness", "audio_duplicate", "video_duplicate"}
    ]
    effective = duration - interval_duration(invalid, duration)
    # A truncated file is scored against the duration its header promised.
    expected = max(duration, media.probe.declared_duration_ms or 0)
    signal = round(100 * effective / expected, 2) if expected else 0.0
    duplicate = any("duplicate" in issue.code for issue in media.issues)
    dimensions = {
        "completeness": signal,
        "consistency": round(100 - _loudness_penalty(media), 2),
        "uniqueness": 0.0 if duplicate else 100.0,
        "annotation": 0.0,
        "distribution": 100.0,
    }
    weights = {"completeness": 25, "consistency": 20, "uniqueness": 15, "distribution": 15}
    total = round(sum(dimensions[key] * weight for key, weight in weights.items()) / 75, 2)
    return MediaFileScore(
        file_id=file.id,
        filename=file.filename,
        duration_ms=duration,
        effective_duration_ms=effective,
        dimensions=dimensions,
        total=total,
        reasons=[f"{issue.code}: {issue.start_ms}-{issue.end_ms} ms" for issue in media.issues],
        **_loudness(media),
    )


def _loudness(media: MediaFileView) -> dict[str, Any]:
    """Carry measured loudness and the accepted range it was judged against."""
    metrics = media.metrics
    low, high = metrics.get("acceptable_min_lufs"), metrics.get("acceptable_max_lufs")
    tolerance = metrics.get("loudness_tolerance_lu")
    loudness = metrics.get("integrated_lufs")
    return {
        "loudness_lufs": float(loudness) if isinstance(loudness, int | float) else None,
        "accepted_lufs": (
            (float(low), float(high))
            if isinstance(low, int | float) and isinstance(high, int | float)
            else None
        ),
        "loudness_tolerance_lu": (float(tolerance) if isinstance(tolerance, int | float) else None),
    }


def _file_line(score: MediaFileScore) -> str:
    line = f"- {score.filename}: {score.total}/100; " + "; ".join(score.reasons)
    if score.loudness_lufs is not None and score.accepted_lufs is not None:
        low, high = score.accepted_lufs
        line += (
            f"; loudness {score.loudness_lufs} LUFS (accepted {low}..{high} LUFS "
            f"+/- {score.loudness_tolerance_lu} LU)"
        )
    return line


def _valid_source_ranges(media: MediaFileView) -> list[MediaInterval]:
    duration = media.probe.duration_ms
    if media.source_end_ms is not None:
        duration = min(duration, max(0, media.source_end_ms - media.source_start_ms))
    invalid = sorted(
        (issue for issue in media.issues if issue.code != "audio_loudness"),
        key=lambda issue: issue.start_ms,
    )
    ranges: list[MediaInterval] = []
    cursor = 0
    for issue in [*invalid, MediaInterval(code="end", start_ms=duration, end_ms=duration)]:
        stop = min(duration, issue.start_ms)
        if stop > cursor:
            ranges.append(
                MediaInterval(
                    code="effective",
                    start_ms=media.source_start_ms + cursor,
                    end_ms=media.source_start_ms + stop,
                )
            )
        cursor = max(cursor, min(duration, issue.end_ms))
    return ranges


def _effective_duration(measured: list[tuple[FileItem, MediaFileView | None]]) -> int:
    parents = {
        step.source_file_id
        for file, media in measured
        if media is not None
        for step in media.history
        if step.source_file_id != file.id
    }
    ranges: dict[str, list[MediaInterval]] = defaultdict(list)
    for file, media in measured:
        if media is None or file.id in parents:
            continue
        root = media.source_asset_id or media.source_file_id or file.id
        ranges[root].extend(_valid_source_ranges(media))
    return sum(
        interval_duration(intervals, max((span.end_ms for span in intervals), default=0))
        for intervals in ranges.values()
    )


def summarize_media(files: list[FileItem]) -> MediaSummary | None:
    """Report measured originals and clips with per-file five-dimension deductions.

    Recordings that failed are listed with their operator and reason, not scored.
    """
    failures = [
        failure
        for file in files
        if (failure := media_failure(file.id, file.filename, file.metadata)) is not None
    ]
    failed = {failure.file_id for failure in failures}
    measured = [(file, media_metadata(file.metadata)) for file in files if file.id not in failed]
    scores: list[MediaFileScore] = []
    originals: list[MediaFileScore] = []
    distribution: Counter[str] = Counter()
    clips = 0
    duplicates = 0
    for file, media in measured:
        if media is None:
            continue
        score = _score(file, media)
        scores.append(score)
        distribution.update(issue.code for issue in media.issues)
        if any(step.operator == "video.segment" for step in media.history):
            clips += 1
        if media.source_file_id is None:
            originals.append(score)
        windows = media.metrics.get("duplicate_segments")
        duplicates += (
            len(windows)
            if isinstance(windows, list)
            else int(any("duplicate" in issue.code for issue in media.issues))
        )
    if not scores and not failures:
        return None
    return MediaSummary(
        original_duration_ms=sum(score.duration_ms for score in originals),
        effective_duration_ms=_effective_duration(measured),
        clip_count=clips,
        duplicate_count=duplicates,
        issue_distribution=dict(sorted(distribution.items())),
        files=scores,
        failures=failures,
        partial=bool(failures and scores),
    )


def _failure_lines(failures: list[MediaFailure]) -> str:
    return "".join(
        f"- failed / 处理失败 {item.filename} ({item.operator}): {item.reason}\n"
        for item in failures
    )


def media_chapter(summary: MediaSummary) -> dict[str, str]:
    """Describe measured durations and issue counts without embedding media bytes."""
    outcome = (
        f"Partially completed / 部分完成: {len(summary.failures)} recording(s) failed.\n"
        if summary.partial
        else ""
    )
    return {
        "title": "音视频 / Audio and video",
        "body": (
            outcome
            + _failure_lines(summary.failures)
            + f"Original duration: {summary.original_duration_ms} ms; "
            f"effective duration: {summary.effective_duration_ms} ms; "
            f"clips: {summary.clip_count}; duplicates: {summary.duplicate_count}.\n"
            + "\n".join(f"- {code}: {count}" for code, count in summary.issue_distribution.items())
            + "\n"
            + "\n".join(_file_line(file) for file in summary.files)
        ),
    }
