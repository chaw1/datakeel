# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for conftest."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image

from datakeel.core.models import FileItem

if TYPE_CHECKING:
    from pathlib import Path

    from tests.operators.factories import FileFactory, ImageFactory


@pytest.fixture
def make_file(tmp_path: Path) -> FileFactory:
    """Provide the make file test fixture."""

    def make(
        content: bytes | str, filename: str = "sample.txt", modality: str = "text"
    ) -> FileItem:
        """Provide the make test fixture."""
        path = tmp_path / f"{len(list(tmp_path.iterdir()))}-{filename}"
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        return FileItem(
            path=str(path), filename=filename, size=path.stat().st_size, modality=modality
        )

    return make


@pytest.fixture
def make_image(make_file: FileFactory) -> ImageFactory:
    """Provide the make image test fixture."""

    def make(width: int = 160, height: int = 80, value: int = 128, channels: int = 3) -> FileItem:
        """Provide the make test fixture."""
        image = np.full((height, width, channels), value, dtype=np.uint8)
        buffer = BytesIO()
        Image.fromarray(image).save(buffer, format="PNG")
        return make_file(buffer.getvalue(), "sample.png", "image")

    return make


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Provide the output dir test fixture."""
    return tmp_path / "output"
