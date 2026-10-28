# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run the deterministic, evidence-backed question pipeline from the local CLI."""

from rich.console import Console

from datakeel.ask.service import ask_data
from datakeel.cli.parsers import CommandGroup
from datakeel.core.ask_models import AskRequest
from datakeel.core.models import utcnow
from datakeel.storage.database import Database


def register_parser(commands: CommandGroup) -> None:
    """Add question and explicit Ask-thread flags to the command grammar."""
    question = commands.add_parser("ask")
    question.add_argument("question")
    question.add_argument("--reference-instant")
    question.add_argument("--conversation-id")


def ask(
    db: Database,
    question: str,
    reference_instant: str | None = None,
    conversation_id: str | None = None,
) -> None:
    """Print the same persisted answer contract returned by the HTTP and MCP entry points."""
    request = AskRequest.model_validate(
        {
            "question": question,
            "reference_instant": reference_instant or utcnow(),
            "conversation_id": conversation_id,
        }
    )
    answer = ask_data(db, request)
    Console().print(answer.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True)
