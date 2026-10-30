# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Graph extraction, transcription and the workbench share one upright pixel frame."""

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from datakeel.core.models import FileItem
from datakeel.operators.image.helpers import decode
from datakeel.storage.image_geometry import read_geometry, upright_bytes
from datakeel.transcription.images import normalize_image


@pytest.mark.parametrize("orientation", range(1, 9))
def test_extraction_transcription_and_workbench_see_identical_upright_pixels(
    tmp_path: Path, orientation: int
) -> None:
    """Coordinates from graph or transcription regions are valid on the workbench canvas."""
    path = tmp_path / f"o{orientation}.png"
    image = Image.new("RGB", (30, 20), (20, 120, 220))
    image.paste((230, 20, 20), (2, 3, 9, 7))
    exif = Image.Exif()
    exif[274] = orientation
    image.save(path, exif=exif)
    geometry = read_geometry(path)
    assert geometry is not None
    served = upright_bytes(path)
    canvas = Image.open(io.BytesIO(served)) if served is not None else Image.open(path)
    transcribed = normalize_image(path.read_bytes())
    assert (transcribed.width, transcribed.height) == (geometry.width, geometry.height)
    assert canvas.size == (geometry.width, geometry.height)
    expected = np.asarray(canvas.convert("RGB"))
    assert np.array_equal(np.asarray(Image.open(io.BytesIO(transcribed.png))), expected)
    operator = decode(FileItem(id="x", filename=path.name, path=str(path), modality="image"))
    assert np.array_equal(operator, expected)
