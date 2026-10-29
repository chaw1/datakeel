# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Media scoring preserves signal deductions, source durations and report evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.media_models import MediaInterval, MediaProbe, MediaStep
from datakeel.core.models import FileItem
from datakeel.operators.audio import probe, vad
from datakeel.operators.media.tools import run_tool
from datakeel.quality import score_quality
from datakeel.quality.media import interval_duration, summarize_media
from datakeel.quality.report import build_report

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import JsonValue


def _file(identifier: str, duration_ms: int = 1000, **metadata: JsonValue) -> FileItem:
    return FileItem(
        id=identifier,
        path=f"unopened/{identifier}.wav",
        filename=f"{identifier}.wav",
        size=120,
        sha256=identifier,
        modality="audio",
        metadata={
            "media_probe": MediaProbe(duration_ms=duration_ms).model_dump(mode="json"),
            **metadata,
        },
    )


def test_interval_union_bounds_and_overlap_do_not_double_deduct() -> None:
    """Cap source ranges and merge overlapping black, freeze and silence intervals."""
    spans = [
        MediaInterval(code="black", start_ms=0, end_ms=200),
        MediaInterval(code="freeze", start_ms=100, end_ms=500),
        MediaInterval(code="audio_silence", start_ms=400, end_ms=1200),
        MediaInterval(code="outside", start_ms=1500, end_ms=2000),
    ]
    assert interval_duration(spans, 1000) == 1000
    assert interval_duration(list(reversed(spans)), 1000) == 1000
    assert interval_duration(spans[:2], 1000) == 500
    assert interval_duration([], 1000) == interval_duration(spans, 0) == 0


def test_media_summary_separates_original_duration_clips_and_duplicate_files() -> None:
    """Count each duplicate clip once while retaining its full interval distribution."""
    original = _file(
        "source",
        4000,
        media_issues=[{"code": "audio_silence", "start_ms": 0, "end_ms": 500}],
    )
    step = MediaStep(
        operator="video.segment",
        source_file_id=original.id,
        parameters={"window_ms": 1000},
        parameters_digest="digest",
        start_ms=500,
        end_ms=1500,
    )
    clip = _file(
        "clip",
        1000,
        source_file_id=original.id,
        source_asset_id=original.id,
        media_history=[step.model_dump(mode="json")],
        media_issues=[
            {"code": "audio_duplicate", "start_ms": 0, "end_ms": 400},
            {"code": "video_duplicate", "start_ms": 400, "end_ms": 1000},
        ],
    )
    summary = summarize_media([original, clip])
    assert summary is not None
    assert summary.original_duration_ms == 4000
    assert summary.effective_duration_ms == 0
    assert summary.clip_count == summary.duplicate_count == 1
    assert len(summary.files) == 2
    assert summary.files[1].effective_duration_ms == 1000
    assert summary.files[1].dimensions["uniqueness"] == 0
    assert summary.issue_distribution == {
        "audio_duplicate": 1,
        "audio_silence": 1,
        "video_duplicate": 1,
    }


def test_measured_media_deducts_five_dimension_scores_with_specific_reasons() -> None:
    """Feed signal evidence into existing scoring without reading raw recordings."""
    file = _file(
        "measured",
        media_issues=[
            {"code": "black", "start_ms": 0, "end_ms": 200},
            {"code": "audio_silence", "start_ms": 100, "end_ms": 500},
            {"code": "audio_loudness", "start_ms": 0, "end_ms": 1000},
        ],
        audio_metrics={"integrated_lufs": -33.0},
    )
    measured = score_quality([file])
    assert measured.media is not None
    assert measured.dimensions["completeness"].score == 50
    assert measured.dimensions["consistency"].score == 70
    assert measured.dimensions["uniqueness"].score == 100
    assert measured.dimensions["annotation"].included is False
    assert measured.total == pytest.approx(75.33, abs=0.01)
    score = measured.media.files[0]
    assert score.effective_duration_ms == 500
    assert score.total == measured.total
    assert score.reasons == [
        "black: 0-200 ms",
        "audio_silence: 100-500 ms",
        "audio_loudness: 0-1000 ms",
    ]
    assert "media" in measured.dimensions["completeness"].details


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        ({"integrated_lufs": -16.0, "target_lufs": -16.0}, 100),
        ({"integrated_lufs": -16.0, "target_lufs": -23.0}, 79),
        ({"integrated_lufs": -70.0}, 0),
        ({"loudness_deviation_lu": 2.0}, 94),
        ({"loudness_measurable": False}, 0),
        ({}, 100),
    ],
)
def test_loudness_score_uses_measured_target_and_unmeasurable_state(
    metrics: dict[str, JsonValue], expected: float
) -> None:
    """Honor normalization targets and distinguish missing data from measured silence."""
    summary = summarize_media([_file("audio", audio_metrics=metrics)])
    assert summary is not None
    assert summary.files[0].dimensions["consistency"] == expected


def test_unmeasured_media_does_not_change_nonmedia_scores_or_report() -> None:
    """Keep the established text and image quality path unchanged without a probe."""
    text = FileItem(
        id="text",
        path="unopened/text",
        filename="sample.txt",
        size=120,
        sha256="unique",
        modality="text",
    )
    score = score_quality([text])
    assert score.media is None
    assert score.total == 100
    assert summarize_media([text]) is None
    report = build_report({"name": "Generated corpus"}, score)
    assert len(report.chapters) == 6
    assert all(chapter.title != "音视频 / Audio and video" for chapter in report.chapters)


def test_report_media_section_contains_aggregates_and_reasons_without_raw_signal() -> None:
    """Publish durations and issue explanations without copying bytes or private paths."""
    file = _file(
        "recording",
        2000,
        raw_media_bytes="RAW_SIGNAL_SENTINEL",
        media_issues=[{"code": "audio_clipping", "start_ms": 200, "end_ms": 600}],
    )
    report = build_report({"name": "Generated recording"}, score_quality([file]))
    assert len(report.chapters) == 7
    chapter = report.chapters[-1]
    assert chapter.title == "音视频 / Audio and video"
    assert "Original duration: 2000 ms" in chapter.body
    assert "effective duration: 1600 ms" in chapter.body
    assert "audio_clipping: 200-600 ms" in chapter.body
    assert "RAW_SIGNAL_SENTINEL" not in report.body
    assert file.path not in report.body


def test_zero_duration_media_has_no_signal_credit() -> None:
    """A probed empty recording cannot receive perfect completeness."""
    summary = summarize_media([_file("empty", 0)])
    assert summary is not None
    assert summary.files[0].effective_duration_ms == 0
    assert summary.files[0].dimensions["completeness"] == 0


def test_effective_duration_unions_overlapping_leaf_clips_and_retains_other_sources() -> None:
    """Choose final clips per source while preserving unrelated unprocessed recordings."""
    original = _file("root", 4000)
    untouched = _file("other", 2000)
    step = MediaStep(
        operator="video.segment",
        source_file_id="root",
        parameters={},
        parameters_digest="digest",
        start_ms=0,
        end_ms=2000,
    )
    first = _file(
        "first",
        2000,
        source_asset_id="root",
        source_file_id="root",
        source_start_ms=0,
        source_end_ms=2000,
        media_history=[step.model_dump(mode="json")],
    )
    second = _file(
        "second",
        2000,
        source_asset_id="root",
        source_file_id="root",
        source_start_ms=1000,
        source_end_ms=3000,
        media_history=[step.model_dump(mode="json")],
    )
    summary = summarize_media([original, untouched, first, second])
    assert summary is not None
    assert summary.original_duration_ms == 6000
    assert summary.effective_duration_ms == 5000
    assert summary.clip_count == 2


def test_duplicate_count_uses_windows_instead_of_one_flag_per_recording() -> None:
    """An inspected recording with two repeated segments contributes two removals."""
    file = _file(
        "duplicates",
        3000,
        video_metrics={"duplicate_segments": [{}, {}]},
        media_issues=[{"code": "video_duplicate", "start_ms": 1000, "end_ms": 3000}],
    )
    summary = summarize_media([file])
    assert summary is not None
    assert summary.duplicate_count == 2
    assert summary.effective_duration_ms == 1000


def test_analysis_history_self_identity_does_not_hide_real_leaf_audio(tmp_path: Path) -> None:
    """Keep measured audio effective after real probe and activity steps reference its own ID."""
    content = run_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=617:sample_rate=16000:duration=0.5",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            "pipe:1",
        ]
    )
    path = tmp_path / "generated.wav"
    path.write_bytes(content)
    source = _file("self-analysis", 500).model_copy(
        update={"path": str(path), "size": len(content)}
    )
    probed = probe.OPERATOR.run([source], tmp_path / "probe").files
    measured = vad.OPERATOR.run(probed, tmp_path / "vad").files[0]
    history = measured.metadata["media_history"]
    assert [step["operator"] for step in history] == ["audio.probe", "audio.vad"]
    assert all(step["source_file_id"] == measured.id for step in history)
    summary = summarize_media([measured])
    assert summary is not None
    assert summary.original_duration_ms == summary.effective_duration_ms == 500


@pytest.mark.parametrize("marked_index", [0, 1])
def test_exact_and_media_duplicate_evidence_does_not_double_deduct(marked_index: int) -> None:
    """One repeated content hash remains one duplicate regardless of which copy is marked."""
    files = [_file("first"), _file("second")]
    files[1] = files[1].model_copy(update={"sha256": files[0].sha256})
    files[marked_index].metadata["media_issues"] = [
        {"code": "audio_duplicate", "start_ms": 0, "end_ms": 1000}
    ]
    result = score_quality(files)
    assert result.dimensions["uniqueness"].score == 50
    assert result.dimensions["uniqueness"].details["media_duplicate_files"] == [
        files[marked_index].id
    ]


def test_media_duplicate_with_distinct_hash_deducts_once_and_missing_hash_has_no_credit() -> None:
    """Approximate matching adds evidence beyond exact hashes without crediting unknown hashes."""
    first = _file("original")
    duplicate = _file(
        "encoded-copy", media_issues=[{"code": "audio_duplicate", "start_ms": 0, "end_ms": 1000}]
    )
    assert score_quality([first, duplicate]).dimensions["uniqueness"].score == 50
    missing = first.model_copy(update={"sha256": ""})
    assert score_quality([missing, duplicate]).dimensions["uniqueness"].score == 0


@pytest.mark.parametrize("failure", ["empty", "corrupt", "undersized"])
def test_base_incomplete_media_does_not_repeat_signal_deduction(failure: str) -> None:
    """One already-incomplete recording cannot remove another recording's quality credit."""
    bad = _file(
        "bad",
        0 if failure == "empty" else 1000,
        media_issues=[{"code": "black", "start_ms": 0, "end_ms": 500}],
    )
    if failure == "undersized":
        bad = bad.model_copy(update={"size": 0})
    else:
        bad.metadata[failure] = True
    valid = _file("valid")
    result = score_quality([bad, valid])
    assert result.dimensions["completeness"].score == 50
