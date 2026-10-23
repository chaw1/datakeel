# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The example command accepts explicit reproducible dataset sizes and paths."""

from pathlib import Path

import pytest

from datakeel.sample_evidence.models import SampleGold
from examples.generate import main


def test_cli_when_output_and_size_supplied_writes_gold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify the documented module entrypoint writes the requested dataset."""
    monkeypatch.setattr("sys.argv", ["generate", "--samples", "20", "--output", str(tmp_path)])
    main()
    gold = SampleGold.model_validate_json((tmp_path / "gold.json").read_bytes())
    assert gold.sample_count == 20


def test_cli_when_size_nonpositive_rejects_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify invalid counts fail before creating a dataset."""
    monkeypatch.setattr("sys.argv", ["generate", "--samples", "0"])
    with pytest.raises(SystemExit, match="2"):
        main()
