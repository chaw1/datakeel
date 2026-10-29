# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public media projections behave identically across model construction paths."""

from __future__ import annotations

import warnings

import pytest
from pydantic import ValidationError

from datakeel.storage.views import FileView


@pytest.mark.parametrize("direct", [True, False])
def test_media_projection_populates_both_constructor_paths_without_warnings(
    *, direct: bool
) -> None:
    """Direct constructors and parsed API records expose the same typed measurements."""
    values = {
        "id": "generated-audio",
        "filename": "generated.wav",
        "sha256": "generated",
        "size": 100,
        "modality": "audio",
        "metadata": {"media_probe": {"duration_ms": 1000}},
    }
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        file = (
            FileView(
                id="generated-audio",
                filename="generated.wav",
                sha256="generated",
                size=100,
                modality="audio",
                metadata={"media_probe": {"duration_ms": 1000}},
            )
            if direct
            else FileView.model_validate(values)
        )
    assert file.media is not None
    assert file.media.probe.duration_ms == 1000
    assert not caught


def test_media_projection_without_metadata_remains_optional() -> None:
    """Plain source files retain their existing optional measurement boundary."""
    file = FileView(
        id="source", filename="source.wav", sha256="generated", size=1, modality="audio"
    )
    assert file.media is None
    assert FileView.model_validate(file) == file


def test_media_projection_invalid_metadata_raises_model_error() -> None:
    """Invalid file metadata is rejected by validation rather than crashing the adapter."""
    with pytest.raises(ValidationError, match="valid dictionary"):
        FileView.model_validate(
            {
                "id": "source",
                "filename": "source.wav",
                "sha256": "generated",
                "size": 1,
                "modality": "audio",
                "metadata": None,
            }
        )
