# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit image evaluation settings shared by the CLI and injected test callers."""

from pathlib import Path

from datakeel.core.models import BoundaryModel


class ImageEvaluationRequest(BoundaryModel):
    """Keep extraction and transcription selections distinct for offline and live evaluation."""

    profile: str = "replay-image-flash"
    transcription_profile: str = "replay-image-demo"
    schema_id: str = "business-knowledge"
    cases: Path | None = None
