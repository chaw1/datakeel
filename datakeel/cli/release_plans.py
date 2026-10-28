# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prepare, approve and execute large release and version plans with an explicit budget."""

import argparse
from pathlib import Path

from rich.console import Console

from datakeel.actions import service
from datakeel.actions.budget import LARGE_BUDGET_ACTIONS, BudgetRequest, requested_context
from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.cli.parsers import CommandGroup
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.storage.database import Database


def register_parser(commands: CommandGroup) -> None:
    """Register `release-plan prepare|approve|reject|execute`."""
    group = commands.add_parser("release-plan")
    subcommands = group.add_subparsers(dest="release_plan_command", required=True)
    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("action", choices=sorted(LARGE_BUDGET_ACTIONS))
    prepare.add_argument("file", type=Path)
    prepare.add_argument("--max-objects", type=int)
    prepare.add_argument("--max-bytes", type=int)
    prepare.add_argument("--actor", default="local")
    for command in ("approve", "reject", "execute"):
        sub = subcommands.add_parser(command)
        sub.add_argument("id")
        sub.add_argument("--digest", required=True)
        sub.add_argument("--actor", default="local")


def _run(db: Database, args: argparse.Namespace) -> BoundaryModel:
    if args.release_plan_command == "prepare":
        budget = BudgetRequest(max_objects=args.max_objects, max_bytes=args.max_bytes)
        return service.prepare_action(
            db,
            args.action,
            JsonDocument.model_validate_json(args.file.read_text(encoding="utf-8")),
            requested_context(args.action, budget, ActionContext(actor=args.actor)),
        )
    if args.release_plan_command in {"approve", "reject"}:
        return service.approve_plan(
            db,
            args.id,
            ApprovalDecision(
                approve=args.release_plan_command == "approve",
                plan_digest=args.digest,
                actor=args.actor,
            ),
        )
    return service.execute_plan(
        db, args.id, ExecuteRequest(plan_digest=args.digest, actor=args.actor)
    )


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Print the frozen plan or run; the budget is visible in the plan before approval."""
    result = _run(db, args)
    Console().print(result.model_dump_json(), markup=False, highlight=False, soft_wrap=True)
