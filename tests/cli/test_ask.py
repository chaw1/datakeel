# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The local question command shares persisted refusal and injected-time behavior."""

import json
import sys
from pathlib import Path

import pytest

from datakeel.cli import main, parser


def test_question_cli_persists_explicit_time_and_safe_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty catalog returns a structured refusal without producing SQL or values."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path))
    monkeypatch.delenv("DATAKEEL_DATABASE_URL", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["datakeel", "ask", "客户满意度", "--reference-instant", "2026-10-01T00:00:00Z"],
    )
    main()
    value = json.loads(capsys.readouterr().out)
    assert value["status"] == "unanswerable"
    assert value["reference_instant"] == "2026-10-01T00:00:00Z"
    assert value["sql"] is None
    assert value["result"] is None
    assert value["assertion_ids"]
    assert parser().parse_args(["ask", "零售额"]).reference_instant is None
