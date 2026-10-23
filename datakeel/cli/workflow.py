# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate and explicitly run deterministic workflows with visible signed pause instructions."""

import argparse
import json
from pathlib import Path

from pydantic import JsonValue, TypeAdapter
from rich.console import Console

from datakeel.cli.parsers import CommandGroup
from datakeel.core.agent_models import ResumeInput
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument, new_id
from datakeel.core.settings import get_settings
from datakeel.core.workflow_models import WorkflowRun, WorkflowStart
from datakeel.runtime.workflow_service import recover_runs, resume_workflow, start_workflow
from datakeel.storage.database import Database
from datakeel.workflows.loader import list_workflows, validate_workflow

JSON_VALUE = TypeAdapter(JsonValue)


def register_parser(commands: CommandGroup) -> None:
    """Add the workflow grammar without expanding the main parser."""
    group = commands.add_parser("workflow")
    subcommands = group.add_subparsers(dest="workflow_command", required=True)
    subcommands.add_parser("list")
    validate = subcommands.add_parser("validate")
    validate.add_argument("file", type=Path)
    run = subcommands.add_parser("run")
    run.add_argument("id")
    run.add_argument("--input", action="append", default=[])
    run.add_argument("--idempotency-key")
    resume = subcommands.add_parser("resume")
    resume.add_argument("id")
    resume.add_argument("--plan", required=True)
    resume.add_argument("--idempotency-key")


def inputs(values: list[str]) -> JsonDocument:
    """Parse k=v pairs, retaining strings and validating structured JSON input values."""
    result: dict[str, JsonValue] = {}
    for item in values:
        key, separator, value = item.partition("=")
        if not key or not separator or key in result:
            msg = "Workflow inputs require unique k=v pairs"
            raise ValidationError(msg)
        try:
            result[key] = JSON_VALUE.validate_python(json.loads(value))
        except json.JSONDecodeError:
            result[key] = value
    return JsonDocument(result)


def _report(run: WorkflowRun, console: Console) -> None:
    console.print(f"run={run.id} status={run.status}", markup=False)
    if run.status == "PAUSED":
        console.print(f"plan={run.pending_plan_id}", markup=False)
        console.print(
            f"{get_settings().base_url}/#/approvals?plan={run.pending_plan_id}", markup=False
        )
        console.print(
            f"datakeel workflow resume {run.id} --plan {run.pending_plan_id}", markup=False
        )
    elif run.status in {"FAILED", "INTERRUPTED"}:
        console.print(run.error or run.status, markup=False)
        raise SystemExit(1)
    else:
        for step in run.steps:
            if step.type == "output" and step.status == "SUCCEEDED":
                console.print(json.dumps(step.output, ensure_ascii=False), markup=False)


def _run(args: argparse.Namespace, console: Console) -> None:
    db = Database()
    db.migrate()
    recover_runs(db)
    key = args.idempotency_key or new_id()
    stream = (
        start_workflow(db, args.id, WorkflowStart(inputs=inputs(args.input), idempotency_key=key))
        if args.workflow_command == "run"
        else resume_workflow(db, args.id, ResumeInput(plan_id=args.plan, idempotency_key=key))
    )
    try:
        for event in stream:
            if event.event == "done":
                _report(event.run, console)
    finally:
        stream.close()
        db.engine.dispose()


def dispatch(args: argparse.Namespace) -> None:
    """Print contracts, located validation errors or durable workflow execution results."""
    console = Console()
    if args.workflow_command == "list":
        for definition in list_workflows():
            console.print(f"{definition.id}: {definition.name}", markup=False)
    elif args.workflow_command == "validate":
        errors = validate_workflow(args.file)
        console.print(
            "\n".join(errors) if errors else "Workflow definition is valid.", markup=False
        )
        if errors:
            raise SystemExit(1)
    else:
        _run(args, console)
