# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Plan one sentence offline, then read, confirm or resume its action chain as a person."""

import argparse

from rich.console import Console

from datakeel.cli.parsers import CommandGroup
from datakeel.core.intent_models import PageContext
from datakeel.intents.chains import advance_chain
from datakeel.intents.planner import PlannerTurn, plan_turn
from datakeel.storage.database import Database
from datakeel.storage.intent_chains import get_chain


def register_parser(commands: CommandGroup) -> None:
    """Expose planning with rules and the human confirmation of stored chains."""
    group = commands.add_parser("intents")
    subcommands = group.add_subparsers(dest="intents_command", required=True)
    plan = subcommands.add_parser("plan")
    plan.add_argument("text")
    for name in ("dataset", "version", "project", "package"):
        plan.add_argument(f"--{name}")
    plan.add_argument("--actor", default="local")
    for command in ("show", "run"):
        sub = subcommands.add_parser(command)
        sub.add_argument("chain_id")
        sub.add_argument("--actor", default="local")


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Print JSON; ``run`` confirms, continues after a signature or resumes after a failure."""
    console = Console(soft_wrap=True)
    if args.intents_command == "plan":
        context = PageContext(
            dataset_id=args.dataset,
            version_id=args.version,
            project_id=args.project,
            package_id=args.package,
        )
        result = plan_turn(db, PlannerTurn(text=args.text, actor=args.actor, context=context))
        console.print(result.model_dump_json(indent=2) if result else "null", markup=False)
        return
    chain = (
        get_chain(db, args.chain_id, actor=args.actor)
        if args.intents_command == "show"
        else advance_chain(db, args.chain_id, args.actor)
    )
    console.print(chain.model_dump_json(indent=2), markup=False)
    if chain.status == "failed":
        raise SystemExit(1)
