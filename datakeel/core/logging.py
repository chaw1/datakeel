# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Structured standard-library logging without secrets or payload dumps."""

import json
import logging

from datakeel.core.models import utcnow
from datakeel.core.settings import get_settings


class JsonFormatter(logging.Formatter):
    """Encode one bounded diagnostic record per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Render stable metadata and a caller-supplied safe message."""
        return json.dumps(
            {
                "timestamp": utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                **({"exception": self.formatException(record.exc_info)} if record.exc_info else {}),
                **{
                    key: record.__dict__[key]
                    for key in (
                        "shard_id",
                        "task_id",
                        "committed",
                        "action_id",
                        "session_id",
                        "elapsed_ms",
                        "run_state",
                    )
                    if key in record.__dict__
                },
            },
            ensure_ascii=False,
        )


def configure_logging() -> None:
    """Install the same JSON format for API, workers and CLI diagnostics."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=get_settings().log_level, handlers=[handler], force=True)


def warn_unsafe_subprocess() -> None:
    """Disclose an unsafe development override when an application role starts."""
    if get_settings().sandbox_allow_subprocess:
        logging.getLogger(__name__).warning(
            "UNSAFE subprocess backend enabled: trusted local development only; "
            "platform-submitted code requires the container backend"
        )
