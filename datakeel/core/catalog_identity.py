# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Stable metadata IDs preserve source spelling while escaping path delimiters."""

from urllib.parse import quote, unquote


def catalog_id(*segments: str) -> str:
    """Percent-encode each segment independently so slashes and whitespace are safe."""
    return "/".join(quote(segment, safe="") for segment in segments)


def catalog_segments(asset_id: str) -> tuple[str, ...]:
    """Decode individual segments without confusing escaped slashes with separators."""
    return tuple(unquote(segment) for segment in asset_id.split("/"))
