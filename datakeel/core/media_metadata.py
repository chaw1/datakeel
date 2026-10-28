# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Convert extensible stored metadata into explicit media boundary models."""

from typing import Any, cast

from datakeel.core.media_models import MediaFailure, MediaFileView

FAILURE_KEY = "media_failure"


def media_failure(file_id: str, filename: str, metadata: dict[str, Any]) -> MediaFailure | None:
    """Read the failure an isolated media operator recorded on a recording, if any."""
    failure: object = metadata.get(FAILURE_KEY)
    if not isinstance(failure, dict) or not failure:
        return None
    record = cast("dict[str, Any]", failure)
    return MediaFailure(
        file_id=file_id,
        filename=filename,
        operator=str(record.get("operator", "")),
        reason=str(record.get("reason", "")),
    )


def media_metadata(metadata: dict[str, Any]) -> MediaFileView | None:
    """Read operator-generated measurements without decoding or filesystem access."""
    if not metadata.get("media_probe"):
        return None
    return MediaFileView.model_validate(
        {
            "probe": metadata["media_probe"],
            "alignment": metadata.get("media_alignment"),
            "issues": metadata.get("media_issues", []),
            "history": metadata.get("media_history", []),
            "source_asset_id": metadata.get("source_asset_id"),
            "source_file_id": metadata.get("source_file_id"),
            "source_start_ms": metadata.get("source_start_ms", metadata.get("start_ms", 0)),
            "source_end_ms": metadata.get("source_end_ms", metadata.get("end_ms")),
            "metrics": {**metadata.get("video_metrics", {}), **metadata.get("audio_metrics", {})},
        }
    )
