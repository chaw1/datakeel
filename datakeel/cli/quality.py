# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate YAML contracts, prepare reviewable imports and read monitored quality."""

import argparse
import json
from pathlib import Path

from rich.console import Console

from datakeel.actions.models import ActionPlan, ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.cli.parsers import CommandGroup
from datakeel.core.models import JsonDocument
from datakeel.quality.dq_contracts import load_contract
from datakeel.storage.database import Database
from datakeel.storage.dq_reads import read_rules
from datakeel.storage.dq_views import read_report, read_rule_views


def register_parser(commands: CommandGroup) -> None:
    """Add quality validation, approved import preparation, execution and reporting commands."""
    quality = commands.add_parser("quality")
    subcommands = quality.add_subparsers(dest="quality_command", required=True)
    for command in ("validate", "import"):
        entry = subcommands.add_parser(command)
        entry.add_argument("path", type=Path)
    subcommands.add_parser("list")
    run = subcommands.add_parser("run")
    run.add_argument("rule_id")
    report = subcommands.add_parser("report")
    report.add_argument("--source-id")
    report.add_argument("--table")
    report.add_argument("--schema-name")


def prepare_import(db: Database, path: Path) -> tuple[ActionPlan, ...]:
    """Prepare all YAML definitions for human review, never granting approval implicitly."""
    contract = load_contract(path)
    existing = {rule.id: rule for rule in read_rules(db)}
    plans: list[ActionPlan] = []
    for rule in contract.rules:
        params = JsonDocument({"rule": rule.model_dump(mode="json")})
        prior = existing.get(rule.id)
        if prior is not None:
            params = JsonDocument({**params.root, "expected_revision": prior.revision})
        plans.append(
            prepare_action(
                db,
                "update_quality_rule" if prior else "create_quality_rule",
                params,
            )
        )
    return tuple(plans)


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Return JSON observations and prepared plans without opening any model connection."""
    if args.quality_command == "validate":
        payload = load_contract(args.path).model_dump(mode="json")
    elif args.quality_command == "import":
        payload = {
            "plans": [plan.model_dump(mode="json") for plan in prepare_import(db, args.path)],
            "next_step": "Review and approve each frozen plan in the Approvals page.",
        }
    elif args.quality_command == "run":
        plan = prepare_action(db, "run_quality_rule", JsonDocument({"rule_id": args.rule_id}))
        payload = execute_plan(
            db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest)
        ).model_dump(mode="json")
    elif args.quality_command == "report":
        payload = read_report(db, args.source_id, args.table, args.schema_name).model_dump(
            mode="json"
        )
    else:
        payload = {"items": [view.model_dump(mode="json") for view in read_rule_views(db)]}
    Console().print(
        json.dumps(payload, ensure_ascii=False, indent=2),
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
