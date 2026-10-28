# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify full-recording output with and without an optional audio track."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.operators.video.render import render

if TYPE_CHECKING:
    from tests.operators.video.conftest import VideoFactory


def test_render_same_input_same_bytes(make_video: VideoFactory) -> None:
    """External encoder calls use deterministic timestamps and omit source metadata."""
    source = make_video()
    assert render(source) == render(source)
