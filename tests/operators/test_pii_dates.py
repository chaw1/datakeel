# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Protect date and time evidence while retaining phone redaction."""

from pathlib import Path

import pytest

from datakeel.operators import REGISTRY
from tests.operators.factories import FileFactory


@pytest.mark.parametrize("value", ["2026-10-24", "2026/10/24", "10:30:00"])
def test_redaction_preserves_dates_and_times(
    value: str, make_file: FileFactory, output_dir: Path
) -> None:
    """Dates and times survive the actual text operator unchanged."""
    text = f"Observed at {value}."
    result = REGISTRY["text.pii_redact"].run([make_file(text)], output_dir)
    assert Path(result.files[0].path).read_text() == text
    assert result.quality["redactions"] == 0


@pytest.mark.parametrize("value", ["+1 (415) 555-0132", "415-555-0132", "13800138000"])
def test_redaction_still_removes_phone_formats(
    value: str, make_file: FileFactory, output_dir: Path
) -> None:
    """International, local and compact phone numbers remain protected."""
    result = REGISTRY["text.pii_redact"].run([make_file(f"Call {value}.")], output_dir)
    assert Path(result.files[0].path).read_text() == "Call [REDACTED]."
    assert result.quality["redactions"] == 1
