# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""JSON diagnostics preserve readable messages and omit arbitrary record extras."""

import json
import logging
import sys
from datetime import UTC, datetime

import pytest

from datakeel.core.logging import JsonFormatter, configure_logging


def test_json_formatter_when_message_formatted_returns_bounded_utc_record() -> None:
    """Verify json formatter when message formatted returns bounded utc record."""
    record = logging.LogRecord("dataset", logging.WARNING, "test.py", 1, "结果 %s", ("ok",), None)
    record.private_payload = "must not leak"
    rendered = json.loads(JsonFormatter().format(record))
    assert rendered == {
        "timestamp": rendered["timestamp"],
        "level": "WARNING",
        "logger": "dataset",
        "message": "结果 ok",
    }
    assert datetime.fromisoformat(rendered["timestamp"]).tzinfo is UTC


def test_configure_logging_when_level_set_installs_json_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify configure logging when level set installs json handler."""
    configured = {}

    def capture(**kwargs: object) -> None:
        """Provide the capture test fixture."""
        configured.update(kwargs)

    monkeypatch.setenv("DATAKEEL_LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(logging, "basicConfig", capture)
    configure_logging()
    assert configured["level"] == "DEBUG"
    assert configured["force"] is True
    assert isinstance(configured["handlers"][0].formatter, JsonFormatter)


def test_json_formatter_when_safe_execution_context_present_retains_only_allowlisted_keys() -> None:
    """Verify json formatter when safe execution context present retains only allowlisted keys."""
    record = logging.LogRecord("worker", logging.INFO, "test.py", 1, "committed", (), None)
    record.shard_id = "shard-one"
    record.task_id = "task-one"
    record.committed = True
    record.private_payload = "private"
    rendered = json.loads(JsonFormatter().format(record))
    assert rendered["shard_id"] == "shard-one"
    assert rendered["task_id"] == "task-one"
    assert rendered["committed"] is True
    assert "private_payload" not in rendered


def test_formatter_when_exception_logged_retains_the_failure_traceback() -> None:
    """Verify formatter when exception logged retains the failure traceback."""

    def fail() -> None:
        """Provide the fail test fixture."""
        msg = "generated diagnostic failure"
        raise RuntimeError(msg)

    try:
        fail()
    except RuntimeError:
        record = logging.LogRecord("test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    result = json.loads(JsonFormatter().format(record))
    assert "RuntimeError: generated diagnostic failure" in result["exception"]
