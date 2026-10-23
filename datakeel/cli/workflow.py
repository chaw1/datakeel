# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Inspect and validate explicit deterministic workflow contracts."""

import argparse
from pathlib import Path

from rich.console import Console

from datakeel.cli.parsers import CommandGroup
from datakeel.workflows.loader import list_workflows, validate_workflow


def register_parser(commands: CommandGroup) -> None:
    """Add the workflow command group without expanding the main parser."""
    group = commands.add_parser("workflow")
    subcommands = group.add_subparsers(dest="workflow_command", required=True)
    subcommands.add_parser("list")
    validate = subcommands.add_parser("validate")
    validate.add_argument("file", type=Path)


def dispatch(args: argparse.Namespace) -> None:
    """Print validated definitions or actionable file and step validation errors."""
    console = Console()
    if args.workflow_command == "list":
        for definition in list_workflows():
            console.print(f"{definition.id}: {definition.name}", markup=False)
        return
    errors = validate_workflow(args.file)
    console.print("\n".join(errors) if errors else "Workflow definition is valid.", markup=False)
    if errors:
        raise SystemExit(1)
