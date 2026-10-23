# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run the deterministic, evidence-backed question pipeline from the local CLI."""

from rich.console import Console

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.models import utcnow
from datakeel.storage.database import Database


def ask(db: Database, question: str, reference_instant: str | None = None) -> None:
    """Print the same persisted answer contract returned by the HTTP and MCP entry points."""
    request = AskRequest.model_validate(
        {"question": question, "reference_instant": reference_instant or utcnow()}
    )
    answer = ask_data(db, request)
    Console().print(answer.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True)
