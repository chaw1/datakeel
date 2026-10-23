# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Inspect model configuration and run frozen routing evaluations without provider calls."""

import argparse
import json
from pathlib import Path

from rich.console import Console

from datakeel.cli.parsers import CommandGroup
from datakeel.routing.config import validate_config
from datakeel.routing.evaluation import evaluate_routes


def register_parser(commands: CommandGroup) -> None:
    """Extend the public command grammar with local routing inspection commands."""
    routing = commands.add_parser("routing")
    subcommands = routing.add_subparsers(dest="routing_command", required=True)
    validate = subcommands.add_parser("validate")
    validate.add_argument("path", nargs="?", type=Path)
    evaluation = commands.add_parser("eval-route")
    evaluation.add_argument("--json", dest="json_output", action="store_true")


def dispatch(args: argparse.Namespace) -> None:
    """Return nonzero on configuration or benchmark errors with located diagnostics."""
    console = Console()
    if args.command == "routing":
        errors = validate_config(args.path)
        console.print(
            "\n".join(errors) if errors else "Model routing configuration is valid.", markup=False
        )
        if errors:
            raise SystemExit(1)
        return
    result = evaluate_routes()
    payload = {**result.model_dump(mode="json"), "accuracy": result.accuracy}
    if args.json_output:
        console.print(json.dumps(payload, ensure_ascii=False, indent=2), markup=False)
    else:
        console.print(
            f"Routing accuracy: {result.accuracy:.0%} "
            f"({result.intent_correct}/{result.intent_total} intents, "
            f"{result.tier_correct}/{result.tier_total} tiers)"
        )
        for name, suite in result.intent_suites.items():
            console.print(f"{name}: {suite.correct}/{suite.total}", markup=False)
        for label, matrix in (
            ("Workflow", result.workflow_confusion),
            ("Branch", result.branch_confusion),
            ("Tier", result.tier_confusion),
        ):
            console.print(
                f"{label} confusion matrix: {json.dumps(matrix, ensure_ascii=False)}", markup=False
            )
        for failure in result.failures:
            console.print(failure, markup=False)
    if result.failures:
        raise SystemExit(1)
