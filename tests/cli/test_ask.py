# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The local question command shares persisted refusal and injected-time behavior."""

import json
import sys
from pathlib import Path

import pytest

from datakeel.cli import main, parser
from datakeel.cli.ask import ask
from datakeel.core.ask_models import AskAnswer
from datakeel.storage.database import Database
from tests.enterprise_support import enterprise_fixture


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


def test_question_cli_emits_chart_and_continues_returned_conversation(
    db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A copied conversation flag reaches the shared engine and preserves JSON chart data."""
    enterprise_fixture(db, tmp_path / "enterprise")
    ask(db, "上个季度华东区零售额是多少", "2026-10-01T00:00:00Z")
    first = AskAnswer.model_validate_json(capsys.readouterr().out)
    assert first.conversation_id is not None
    assert first.chart is not None
    arguments = parser().parse_args(
        [
            "ask",
            "那华南呢",
            "--conversation-id",
            first.conversation_id,
            "--reference-instant",
            "2026-10-01T00:00:00Z",
        ]
    )
    ask(db, arguments.question, arguments.reference_instant, arguments.conversation_id)
    follow = AskAnswer.model_validate_json(capsys.readouterr().out)
    ask(db, "上个季度华南区零售额是多少", "2026-10-01T00:00:00Z")
    equivalent = AskAnswer.model_validate_json(capsys.readouterr().out)
    assert follow.conversation_id == first.conversation_id
    assert follow.result == equivalent.result
    assert follow.interpreted_question
    assert follow.chart is not None
