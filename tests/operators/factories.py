# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Precise callable contracts for generated operator fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datakeel.core.models import FileItem


class FileFactory(Protocol):
    """Create an isolated file with explicit content, name, and modality."""

    def __call__(
        self, content: bytes | str, filename: str = "sample.txt", modality: str = "text"
    ) -> FileItem:
        """Materialize content and return its typed file identity."""
        ...


class ImageFactory(Protocol):
    """Create generated PNG content with a chosen pixel shape and value."""

    def __call__(
        self, width: int = 160, height: int = 80, value: int = 128, channels: int = 3
    ) -> FileItem:
        """Materialize a deterministic RGB or RGBA fixture."""
        ...
