# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Convert extensible stored metadata into explicit media boundary models."""

from typing import Any

from datakeel.core.media_models import MediaFileView


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
