# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Locate repeated video at any time offset and optionally keep only unique ranges."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from datakeel.core.media_models import MediaInterval
from datakeel.core.models import FileItem, JsonDocument, Record
from datakeel.operators.base import Operator, OperatorResult, Params, annotate, summarize
from datakeel.operators.media.tools import media_artifact
from datakeel.operators.video.render import render
from datakeel.operators.video.sequence import (
    Match,
    Sequence,
    decode_sequence,
    find_match,
    frame_matches,
    motion_step,
)

if TYPE_CHECKING:
    from pathlib import Path


class DedupParams(Params):
    """Search repeated windows frame by frame and extend each match to its real extent.

    Repeats lasting at least 1.5 windows are located wherever they start. Frames
    match when the thumbnail differs little on average (``max_spatial_difference``)
    and nowhere by much (``max_local_difference``, so a changed clock digit or a
    subject elsewhere in a static scene is not a match), and when the picture
    changes the same way; windows of static picture are never reported.
    """

    window_ms: int = Field(default=2000, ge=500, le=60000)
    sample_fps: float = Field(default=30.0, ge=1, le=60)
    max_hamming: float = Field(default=6.0, ge=0, le=32)
    max_brightness_difference: float = Field(default=16.0, ge=0, le=255)
    max_spatial_difference: float = Field(default=2.0, ge=0, le=255)
    max_local_difference: float = Field(default=32.0, ge=0, le=255)
    minimum_clip_ms: int = Field(default=250, ge=0)
    remove: bool = False


class DuplicateWindow(Record):
    """Locate a repeated interval and the first matching source interval."""

    start_ms: int
    end_ms: int
    source_file_id: str
    source_start_ms: int
    source_end_ms: int


def _positions(count: int, window: int) -> list[int]:
    step = max(1, window // 2)
    return sorted({*range(0, count - window + 1, step), count - window})


def _extend(candidate: Sequence, match: Match, floor: int, params: DedupParams) -> Match:
    delta = match.prior.times[match.prior_first] - candidate.times[match.first]
    same_file = match.prior.file_id == candidate.file_id
    first, stop = match.first, match.stop
    while first > floor and (not same_file or match.prior_last < first - 1):
        target = candidate.times[first - 1] + delta
        if target < 0 or not frame_matches(candidate, first - 1, match.prior, target, params):
            break
        first -= 1
    stop = _extend_forward(candidate, match.prior, (first, stop), delta, params)
    # The last frames' motion reaches past the repeat, so they are matched by appearance.
    stop = _extend_forward(
        candidate, match.prior, (first, stop), delta, params, limit=motion_step(candidate.frame_ms)
    )
    prior_first = round((candidate.times[first] + delta) / match.prior.frame_ms)
    prior_last = round((candidate.times[stop - 1] + delta) / match.prior.frame_ms)
    return Match(match.prior, first, stop, prior_first, prior_last)


def _extend_forward(
    candidate: Sequence,
    prior: Sequence,
    span: tuple[int, int],
    delta: float,
    params: DedupParams,
    *,
    limit: int | None = None,
) -> int:
    """Extend a match frame by frame; with ``limit``, by appearance for at most that many."""
    first, stop = span
    end = len(candidate.times) if limit is None else min(len(candidate.times), stop + limit)
    same_file = prior.file_id == candidate.file_id
    while stop < end:
        target = candidate.times[stop] + delta
        mapped = round(target / prior.frame_ms)
        if mapped >= len(prior.times) or (same_file and mapped >= first):
            break
        if not frame_matches(candidate, stop, prior, target, params, motion=limit is None):
            break
        stop += 1
    return stop


def _duplicates(
    candidate: Sequence, earlier: list[Sequence], params: DedupParams
) -> list[DuplicateWindow]:
    count = len(candidate.times)
    window = min(count, max(1, round(params.window_ms / candidate.frame_ms)))
    result: list[DuplicateWindow] = []
    covered = 0
    for start in _positions(count, window):
        if start < covered:
            continue
        priors = [(prior, len(prior.times)) for prior in earlier] + [(candidate, start)]
        match = find_match(candidate, (start, start + window), priors, params)
        if match is None:
            continue
        match = _extend(candidate, match, covered, params)
        covered = match.stop
        result.append(_window(candidate, match))
    return result


def _window(candidate: Sequence, match: Match) -> DuplicateWindow:
    prior = match.prior
    end_ms = round(candidate.times[match.stop - 1] + candidate.frame_ms)
    source_end_ms = round(prior.times[match.prior_last] + prior.frame_ms)
    return DuplicateWindow(
        start_ms=round(candidate.times[match.first]),
        end_ms=min(candidate.duration_ms, end_ms),
        source_file_id=prior.file_id,
        source_start_ms=round(prior.times[match.prior_first]),
        source_end_ms=min(prior.duration_ms, source_end_ms),
    )


def _mark(file: FileItem, duplicates: list[DuplicateWindow], duration_ms: int) -> FileItem:
    duplicate_ms = sum(item.end_ms - item.start_ms for item in duplicates)
    metrics = JsonDocument.model_validate(file.metadata.get("video_metrics", {})).root
    metrics.update(
        {
            "duplicate_duration_ms": duplicate_ms,
            "duplicate_ratio": duplicate_ms / max(1, duration_ms),
            "duplicate_segments": [item.model_dump(mode="json") for item in duplicates],
        }
    )
    previous = [
        issue
        for issue in file.metadata.get("media_issues", [])
        if issue.get("code") != "video_duplicate"
    ]
    issues = [
        MediaInterval(
            code="video_duplicate", start_ms=item.start_ms, end_ms=item.end_ms, severity="info"
        ).model_dump(mode="json")
        for item in duplicates
    ]
    return annotate(file, video_metrics=metrics, media_issues=[*previous, *issues])


def _unique_ranges(duplicates: list[DuplicateWindow], duration_ms: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for item in sorted(duplicates, key=lambda value: value.start_ms):
        if item.start_ms > cursor:
            ranges.append((cursor, item.start_ms))
        cursor = max(cursor, item.end_ms)
    if duration_ms > cursor:
        ranges.append((cursor, duration_ms))
    return ranges


def execute(files: list[FileItem], output_dir: Path, params: DedupParams) -> OperatorResult:
    """Mark repeated ranges with their first source, optionally keeping unique ranges only."""
    output: list[FileItem] = []
    earlier: list[Sequence] = []
    duplicate_count = 0
    for file in files:
        sequence = decode_sequence(file, params.sample_fps)
        duplicates = _duplicates(sequence, earlier, params)
        earlier.append(sequence)
        duplicate_count += len(duplicates)
        marked = _mark(file, duplicates, sequence.duration_ms)
        if not params.remove or not duplicates:
            output.append(marked)
            continue
        output.extend(
            media_artifact(
                marked,
                output_dir,
                render(marked, start_ms=start_ms, end_ms=end_ms),
                "mp4",
                "video.dedup",
                params,
                start_ms=start_ms,
                end_ms=end_ms,
            )
            for start_ms, end_ms in _unique_ranges(duplicates, sequence.duration_ms)
            if end_ms - start_ms >= params.minimum_clip_ms
        )
    result = summarize(files, output)
    result.quality["duplicate_segment_count"] = duplicate_count
    return result


OPERATOR = Operator("video.dedup", "video", "deduplication", DedupParams, execute)
