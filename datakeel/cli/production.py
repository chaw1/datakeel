# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prepare, inspect, approve and execute production workflows from a local terminal."""

import argparse
from pathlib import Path

from rich.console import Console

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.cli.parsers import CommandGroup
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.ontology.functions import invoke_function
from datakeel.storage.database import Database


def register_parser(commands: CommandGroup) -> None:
    """Expose explicit preparation and human decisions with no implicit approval."""
    group = commands.add_parser("production")
    subcommands = group.add_subparsers(dest="production_command", required=True)
    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("action")
    prepare.add_argument("file", type=Path)
    prepare.add_argument("--actor", default="local")
    prepare.add_argument("--scopes", nargs="+", default=["*"])
    for command in ("approve", "reject", "execute", "plan"):
        sub = subcommands.add_parser(command)
        sub.add_argument("id")
        sub.add_argument("--actor", default="local")
        if command != "plan":
            sub.add_argument("--digest", required=True)
    read = subcommands.add_parser("read")
    read.add_argument("function")
    read.add_argument("file", type=Path)
    read.add_argument("--actor", default="local")
    subcommands.add_parser("demo")


def _control(db: Database, args: argparse.Namespace) -> BoundaryModel:
    if args.production_command == "prepare":
        return service.prepare_action(
            db,
            args.action,
            JsonDocument.model_validate_json(args.file.read_text(encoding="utf-8")),
            ActionContext(actor=args.actor, scopes=args.scopes),
        )
    if args.production_command in {"approve", "reject"}:
        return service.approve_plan(
            db,
            args.id,
            ApprovalDecision(
                approve=args.production_command == "approve",
                plan_digest=args.digest,
                actor=args.actor,
            ),
        )
    if args.production_command == "plan":
        return service.get_plan(db, args.id)
    return service.execute_plan(
        db, args.id, ExecuteRequest(plan_digest=args.digest, actor=args.actor)
    )


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Print stable JSON plans, read functions and receipts for shell automation."""
    if args.production_command == "read":
        result = invoke_function(
            db,
            args.function,
            JsonDocument.model_validate_json(args.file.read_text(encoding="utf-8")),
            access=AccessContext(actor=args.actor, entry="ask", scope="query"),
        )
    elif args.production_command == "demo":
        from datakeel.cli.production_demo import seed_production_demo  # noqa: PLC0415

        result = seed_production_demo(db)
    else:
        result = _control(db, args)
    Console().print(result.model_dump_json(), markup=False, highlight=False, soft_wrap=True)
