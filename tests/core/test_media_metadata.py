# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed stored-media projections preserve measurements and source coordinates."""

import pytest
from pydantic import ValidationError

from datakeel.core.media_alignment import MediaAlignment
from datakeel.core.media_metadata import media_metadata
from datakeel.core.media_models import MediaFileView, MediaInterval, MediaProbe, MediaStep


@pytest.mark.parametrize(
    "metadata", [{}, {"media_probe": {}}, {"audio_metrics": {"silence_ratio": 1}}]
)
def test_metadata_without_probe_returns_no_media_view(metadata: dict[str, object]) -> None:
    """Legacy metadata remains a non-media projection without invented measurements."""
    assert media_metadata(metadata) is None


def test_probe_only_projection_supplies_optional_defaults() -> None:
    """Expose unavailable dimensions as absent or zero rather than guessed properties."""
    projected = media_metadata({"media_probe": {"duration_ms": 0}})
    assert projected is not None
    assert projected.probe.duration_ms == projected.probe.width == projected.probe.audio_tracks == 0
    assert projected.alignment is None
    assert projected.issues == projected.history == []
    assert projected.metrics == {}
    assert projected.source_start_ms == 0
    assert projected.source_end_ms is projected.source_file_id is projected.source_asset_id is None


def test_projection_preserves_alignment_history_and_explicit_source_range() -> None:
    """Return frozen boundary models with root-relative ranges and merged quality facts."""
    step = MediaStep(
        operator="video.segment",
        parameters={"window_ms": 2000},
        parameters_digest="digest",
        source_file_id="immediate",
        start_ms=250,
        end_ms=2250,
    )
    alignment = MediaAlignment(
        reference_file_id="reference",
        offset_ms=500.0,
        confidence=0.99,
        aligned=True,
        reason="matched",
    )
    projected = media_metadata(
        {
            "media_probe": MediaProbe(duration_ms=2000, width=320, height=240).model_dump(),
            "media_alignment": alignment.model_dump(),
            "media_issues": [{"code": "black", "start_ms": 0, "end_ms": 200}],
            "media_history": [step.model_dump()],
            "source_file_id": "immediate",
            "source_asset_id": "original",
            "start_ms": 250,
            "end_ms": 2250,
            "source_start_ms": 1250,
            "source_end_ms": 3250,
            "video_metrics": {"black_ratio": 0.1},
            "audio_metrics": {"silence_ratio": 0.25},
        }
    )
    assert isinstance(projected, MediaFileView)
    assert projected.alignment == alignment
    assert projected.history == [step]
    assert projected.source_file_id == "immediate"
    assert projected.source_asset_id == "original"
    assert (projected.source_start_ms, projected.source_end_ms) == (1250, 3250)
    assert projected.metrics == {"black_ratio": 0.1, "silence_ratio": 0.25}
    assert projected.issues == [MediaInterval(code="black", start_ms=0, end_ms=200)]
    with pytest.raises(ValidationError, match="frozen"):
        projected.source_start_ms = 0


def test_projection_uses_immediate_range_for_legacy_artifacts() -> None:
    """Keep existing start/end metadata usable when root-relative coordinates are absent."""
    projected = media_metadata(
        {"media_probe": {"duration_ms": 800}, "start_ms": 200, "end_ms": 1000}
    )
    assert projected is not None
    assert (projected.source_start_ms, projected.source_end_ms) == (200, 1000)


def test_projection_retains_unalignable_result_without_fabricating_zero_offset() -> None:
    """A low-confidence recording must retain null offset in JSON and typed views."""
    projected = media_metadata(
        {
            "media_probe": {"duration_ms": 1000},
            "media_alignment": {
                "reference_file_id": "reference",
                "confidence": 0.1,
                "reason": "no_common_signal",
            },
        }
    )
    assert projected is not None
    assert projected.alignment is not None
    assert projected.alignment.offset_ms is None
    assert projected.alignment.aligned is False
    assert projected.model_dump(mode="json")["alignment"]["offset_ms"] is None


@pytest.mark.parametrize(
    "metadata",
    [
        {"media_probe": {"duration_ms": -1}},
        {"media_probe": {"duration_ms": 1, "invented": 2}},
        {
            "media_probe": {"duration_ms": 1},
            "media_issues": [{"code": "black", "start_ms": -1, "end_ms": 0}],
        },
        {
            "media_probe": {"duration_ms": 1},
            "media_alignment": {"reference_file_id": "ref", "reason": "matched", "confidence": 1.1},
        },
    ],
)
def test_projection_rejects_invalid_boundary_measurements(metadata: dict[str, object]) -> None:
    """Stored metadata must satisfy the same strict schema as live tool output."""
    with pytest.raises(ValidationError, match="validation error"):
        media_metadata(metadata)


def test_interval_rejects_reversed_range_and_accepts_empty_boundary() -> None:
    """Reject impossible time ranges without excluding a zero-length endpoint marker."""
    with pytest.raises(ValueError, match="must not precede"):
        MediaInterval(code="black", start_ms=2, end_ms=1)
    assert MediaInterval(code="boundary", start_ms=2, end_ms=2).end_ms == 2


def test_transform_step_rejects_reversed_range_and_allows_unknown_end() -> None:
    """Keep an unknown source end distinct from an impossible source interval."""
    values = {
        "operator": "audio.trim_silence",
        "parameters": {},
        "parameters_digest": "digest",
        "source_file_id": "source",
        "start_ms": 500,
    }
    with pytest.raises(ValueError, match="must not precede"):
        MediaStep.model_validate({**values, "end_ms": 100})
    assert MediaStep.model_validate(values).end_ms is None


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"aligned": True, "offset_ms": None, "reason": "matched"}, "require an offset"),
        ({"aligned": False, "offset_ms": 0.0, "reason": "silence"}, "forbid one"),
        ({"aligned": True, "offset_ms": 2.0, "reason": "ambiguous"}, "reason must agree"),
        ({"aligned": True, "offset_ms": 2.0, "reason": "reference"}, "zero offset"),
    ],
)
def test_alignment_rejects_contradictory_success_and_failure(
    values: dict[str, object], message: str
) -> None:
    """Do not let invalid stored success claims become zero or fabricated offsets."""
    with pytest.raises(ValueError, match=message):
        MediaAlignment.model_validate({"reference_file_id": "reference", **values})


@pytest.mark.parametrize("field", ["width", "height", "audio_tracks", "sample_rate", "channels"])
def test_probe_rejects_negative_stream_properties(field: str) -> None:
    """Only absent zero values or measured nonnegative stream dimensions cross the boundary."""
    with pytest.raises(ValidationError, match="greater than or equal"):
        MediaProbe.model_validate({"duration_ms": 1000, field: -1})


@pytest.mark.parametrize("rate", [-1.0, float("nan"), float("inf"), float("-inf")])
def test_probe_rejects_nonfinite_or_negative_frame_rates(rate: float) -> None:
    """Prevent invalid numeric frame rates from leaking into JSON or timing calculations."""
    with pytest.raises(ValidationError, match=r"finite|greater than or equal"):
        MediaProbe(duration_ms=1000, frame_rate=rate)


@pytest.mark.parametrize(
    "coordinates",
    [
        {"source_start_ms": -1},
        {"source_end_ms": -1},
        {"source_start_ms": 1000, "source_end_ms": 500},
    ],
)
def test_projection_rejects_negative_or_reversed_source_ranges(coordinates: dict[str, int]) -> None:
    """Keep displayed root-relative provenance bounded and ordered like transform history."""
    with pytest.raises(ValueError, match=r"greater than or equal|must not precede"):
        media_metadata({"media_probe": {"duration_ms": 1000}, **coordinates})
