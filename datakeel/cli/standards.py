# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Inspect standards and execute explicit reversible edits through frozen action plans."""

import argparse
import json
from pathlib import Path

from pydantic import JsonValue
from rich.console import Console

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, get_plan, prepare_action
from datakeel.cli.parsers import CommandGroup
from datakeel.core.models import JsonDocument
from datakeel.harness.standard_cases import seed_standard_demo
from datakeel.standards.loader import contract_schema, dump_contract, load_contract
from datakeel.storage import standard_queries, standard_store
from datakeel.storage.database import Database, data_dir


def register_parser(commands: CommandGroup) -> None:
    """Add standards inspection, YAML import/export, confirmation and rollback commands."""
    group = commands.add_parser("standards")
    sub = group.add_subparsers(dest="standards_command", required=True)
    for name in ("list", "code-lists"):
        query = sub.add_parser(name)
        query.add_argument("--search", default="")
        query.add_argument("--status", choices=["draft", "active", "deprecated"])
    for name in ("history", "suggestions", "profiles", "mappings", "schema"):
        sub.add_parser(name)
    for name in ("check", "coverage"):
        report = sub.add_parser(name)
        report.add_argument("--table")
    export = sub.add_parser("export")
    export.add_argument("--output", type=Path)
    imported = sub.add_parser("import")
    imported.add_argument("file", type=Path)
    imported.add_argument("--dry-run", action="store_true")
    imported.add_argument("--approve", action="store_true")
    confirm = sub.add_parser("confirm")
    confirm.add_argument("column")
    confirm.add_argument("standard")
    confirm.add_argument("--dry-run", action="store_true")
    confirm.add_argument("--approve", action="store_true")
    rollback = sub.add_parser("rollback")
    rollback.add_argument("revision", type=int)
    rollback.add_argument("--dry-run", action="store_true")
    rollback.add_argument("--approve", action="store_true")
    approval = sub.add_parser("approve")
    approval.add_argument("plan")
    approval.add_argument("--reject", action="store_true")
    approval.add_argument("--reason", default="Explicit CLI decision")
    execution = sub.add_parser("execute")
    execution.add_argument("plan")
    demo = sub.add_parser("demo")
    demo.add_argument("--directory", type=Path)


def _mutation(db: Database, args: argparse.Namespace) -> str:
    if args.standards_command == "import":
        action = "import_standards"
        params = JsonDocument({"contract": load_contract(args.file).model_dump(mode="json")})
    elif args.standards_command == "confirm":
        action = "confirm_standard_mapping"
        params = JsonDocument(
            {"mapping": {"column_id": args.column, "standard_code": args.standard}}
        )
    else:
        action = "rollback_standards"
        params = JsonDocument({"revision": args.revision})
    plan = prepare_action(db, action, params)
    if args.dry_run or not args.approve:
        return plan.model_dump_json(indent=2)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    return execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest)).model_dump_json(
        indent=2
    )


def _read(db: Database, args: argparse.Namespace) -> JsonValue:
    command = args.standards_command
    if command == "list":
        return [
            item.model_dump(mode="json")
            for item in standard_store.list_standards(db, args.search, args.status)
        ]
    if command == "code-lists":
        return [
            item.model_dump(mode="json")
            for item in standard_store.list_code_lists(db, args.search, args.status)
        ]
    if command == "history":
        return standard_store.history(db).model_dump(mode="json")
    if command == "schema":
        return contract_schema().root
    if command in {"check", "coverage"}:
        report = standard_queries.standards_report(db, args.table)
        return (
            report.coverage.model_dump(mode="json")
            if command == "coverage"
            else report.model_dump(mode="json")
        )
    items = {
        "profiles": standard_queries.list_profiles,
        "suggestions": standard_queries.suggestions,
        "mappings": standard_store.list_mappings,
    }[command](db)
    return [item.model_dump(mode="json") for item in items]


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Print typed JSON evidence or portable YAML; edits always create controlled receipts."""
    if args.standards_command in {"import", "confirm", "rollback"}:
        encoded = _mutation(db, args)
    elif args.standards_command in {"approve", "execute"}:
        encoded = _decision(db, args)
    elif args.standards_command == "demo":
        encoded = seed_standard_demo(
            db, args.directory or data_dir() / "standards-demo"
        ).model_dump_json(indent=2)
    elif args.standards_command == "export":
        encoded = dump_contract(standard_store.get_contract(db))
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
            return
    else:
        encoded = json.dumps(_read(db, args), ensure_ascii=False, indent=2)
    Console().print(encoded, markup=False, highlight=False, soft_wrap=True)


def _decision(db: Database, args: argparse.Namespace) -> str:
    plan = get_plan(db, args.plan)
    if args.standards_command == "approve":
        return approve_plan(
            db,
            plan.id,
            ApprovalDecision(
                approve=not args.reject, plan_digest=plan.plan_digest, reason=args.reason
            ),
        ).model_dump_json(indent=2)
    return execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest)).model_dump_json(
        indent=2
    )
