# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Failed, truncated and loudness-judged recordings are summarized explicitly."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.media_models import MediaProbe
from datakeel.core.models import FileItem
from datakeel.quality.media import media_chapter, summarize_media

if TYPE_CHECKING:
    from pydantic import JsonValue


def _file(identifier: str, probe: MediaProbe | None = None, **metadata: JsonValue) -> FileItem:
    measured: dict[str, JsonValue] = (
        {"media_probe": probe.model_dump(mode="json")} if probe is not None else {}
    )
    return FileItem(
        id=identifier,
        path=f"unopened/{identifier}.wav",
        filename=f"{identifier}.wav",
        size=120,
        sha256=identifier,
        modality="audio",
        metadata={**measured, **metadata},
    )


_FAILURE: dict[str, JsonValue] = {"operator": "audio.probe", "reason": "ExecutionError: bad"}


def test_failed_recording_is_listed_not_scored() -> None:
    """A failed recording appears as a failure while the healthy one is scored."""
    summary = summarize_media(
        [
            _file("good", MediaProbe(duration_ms=1000)),
            _file("bad", MediaProbe(duration_ms=1000), media_failure=_FAILURE),
        ]
    )
    assert summary is not None
    assert summary.partial
    assert [score.file_id for score in summary.files] == ["good"]
    assert [(item.file_id, item.operator) for item in summary.failures] == [("bad", "audio.probe")]
    assert summary.original_duration_ms == 1000
    body = media_chapter(summary)["body"]
    assert body.startswith("Partially completed / 部分完成: 1 recording(s) failed.")
    assert "- failed / 处理失败 bad.wav (audio.probe): ExecutionError: bad" in body


def test_only_failures_are_reported_without_partial_completion() -> None:
    """With nothing processed the summary still lists the failures, not a partial result."""
    summary = summarize_media([_file("bad", media_failure=_FAILURE)])
    assert summary is not None
    assert not summary.partial
    assert summary.files == []
    assert [item.reason for item in summary.failures] == ["ExecutionError: bad"]
    assert "Partially completed" not in media_chapter(summary)["body"]


def test_clean_summary_has_no_failures() -> None:
    """A run without failures is neither partial nor carries an empty failure note."""
    summary = summarize_media([_file("good", MediaProbe(duration_ms=1000))])
    assert summary is not None
    assert (summary.partial, summary.failures) == (False, [])
    assert "处理失败" not in media_chapter(summary)["body"]


def test_truncated_recording_completeness_uses_declared_duration() -> None:
    """Half of a promised recording is half complete even though all of it is readable."""
    probe = MediaProbe(duration_ms=2000, declared_duration_ms=4000)
    issue: dict[str, JsonValue] = {
        "code": "truncated_file",
        "start_ms": 2000,
        "end_ms": 4000,
        "severity": "critical",
    }
    summary = summarize_media([_file("cut", probe, media_issues=[issue])])
    assert summary is not None
    score = summary.files[0]
    assert score.dimensions["completeness"] == 50.0
    assert score.effective_duration_ms == 2000
    assert summary.issue_distribution == {"truncated_file": 1}
    assert score.reasons == ["truncated_file: 2000-4000 ms"]
