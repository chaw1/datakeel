# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed scoring responses reject extra fields and reassignment."""

import pytest
from pydantic import ValidationError

from datakeel.quality.models import ChapterView


def test_chapter_frozen_fields_reject_changes() -> None:
    """Verify chapter frozen fields reject changes."""
    chapter = ChapterView(title="Evidence", body="Generated fixture")
    with pytest.raises(ValidationError, match="frozen"):
        chapter.title = "Changed"
