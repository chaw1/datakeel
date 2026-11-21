# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate, execute and inspect deterministic workflows from the CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import JsonValue, TypeAdapter
from rich.console import Console

from datakeel.core.agent_models import ResumeInput
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument, new_id
from datakeel.core.settings import get_settings
from datakeel.core.workflow_models import WorkflowRun, WorkflowStart, WorkflowStatus
from datakeel.runtime.workflow_service import recover_runs, resume_workflow, start_workflow
from datakeel.storage.database import Database
from datakeel.storage.identity_sessions import require_session_actor, session_actor
from datakeel.storage.workflow_recovery import list_audit
from datakeel.storage.workflow_store import get_run, list_runs
from datakeel.versioning import require_current
from datakeel.workflows.loader import list_workflows, validate_workflow

if TYPE_CHECKING:
    import argparse

    from datakeel.cli.parsers import CommandGroup

JSON_VALUE = TypeAdapter(JsonValue)
_STATUSES: tuple[WorkflowStatus, ...] = (
    "PENDING",
    "RUNNING",
    "PAUSED",
    "SUCCEEDED",
    "FAILED",
    "INTERRUPTED",
)


def register_parser(commands: CommandGroup) -> None:
    """Add the workflow grammar without expanding the main parser."""
    group = commands.add_parser("workflow")
    subcommands = group.add_subparsers(dest="workflow_command", required=True)
    listed = subcommands.add_parser("list")
    listed.add_argument("--json", action="store_true", dest="json_output")
    validate = subcommands.add_parser("validate")
    validate.add_argument("file", type=Path)
    validate.add_argument("--json", action="store_true", dest="json_output")
    run = subcommands.add_parser("run")
    run.add_argument("id")
    run.add_argument("--input", action="append", default=[])
    run.add_argument("--idempotency-key")
    run.add_argument("--actor", default="local")
    run.add_argument("--json", action="store_true", dest="json_output")
    resume = subcommands.add_parser("resume")
    resume.add_argument("id")
    resume.add_argument("--plan", required=True)
    resume.add_argument("--idempotency-key")
    resume.add_argument("--actor", default="local")
    resume.add_argument("--json", action="store_true", dest="json_output")
    runs = subcommands.add_parser("runs")
    runs.add_argument("--workflow")
    runs.add_argument("--status", choices=list(_STATUSES))
    runs.add_argument("--limit", type=int, default=20)
    runs.add_argument("--actor", default="local")
    runs.add_argument("--json", action="store_true", dest="json_output")
    show = subcommands.add_parser("show")
    show.add_argument("id")
    show.add_argument("--audit", action="store_true")
    show.add_argument("--actor", default="local")
    show.add_argument("--json", action="store_true", dest="json_output")


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


def _prepare_db() -> Database:
    db = Database()
    if db.sqlite:
        require_current(db)
    recover_runs(db)
    return db


def _print_json(console: Console, payload: object) -> None:
    console.print(
        json.dumps(payload, ensure_ascii=False, indent=2),
        markup=False,
        highlight=False,
        soft_wrap=True,
    )


def _report(run: WorkflowRun, console: Console, *, json_output: bool = False) -> None:
    if json_output:
        _print_json(console, run.model_dump(mode="json"))
        if run.status in {"FAILED", "INTERRUPTED"}:
            raise SystemExit(1)
        return
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
    actor = getattr(args, "actor", "local")
    json_output = bool(getattr(args, "json_output", False))
    db = _prepare_db()
    key = args.idempotency_key or new_id()
    stream = (
        start_workflow(
            db,
            args.id,
            WorkflowStart(inputs=inputs(args.input), idempotency_key=key),
            actor=actor,
        )
        if args.workflow_command == "run"
        else resume_workflow(
            db, args.id, ResumeInput(plan_id=args.plan, idempotency_key=key), actor=actor
        )
    )
    try:
        for event in stream:
            if event.event == "done":
                _report(event.run, console, json_output=json_output)
    finally:
        stream.close()
        db.engine.dispose()


def _list_runs(args: argparse.Namespace, console: Console) -> None:
    if args.limit < 1:
        msg = "Workflow run limit must be at least 1"
        raise ValidationError(msg)
    db = _prepare_db()
    try:
        items = [
            item
            for item in list_runs(db)
            if session_actor(db, item.id) == args.actor
            and (args.workflow is None or item.workflow_id == args.workflow)
            and (args.status is None or item.status == args.status)
        ][: args.limit]
    finally:
        db.engine.dispose()
    if args.json_output:
        _print_json(console, [item.model_dump(mode="json") for item in items])
        return
    for item in items:
        console.print(
            f"{item.id}  {item.workflow_id}  {item.status}  {item.created_at.isoformat()}",
            markup=False,
        )


def _show_run(args: argparse.Namespace, console: Console) -> None:
    db = _prepare_db()
    try:
        require_session_actor(db, args.id, args.actor)
        run = get_run(db, args.id)
        audits = list_audit(db, args.id) if args.audit else []
    finally:
        db.engine.dispose()
    if args.json_output:
        payload = (
            {
                "run": run.model_dump(mode="json"),
                "audit": [a.model_dump(mode="json") for a in audits],
            }
            if args.audit
            else run.model_dump(mode="json")
        )
        _print_json(console, payload)
        return
    console.print(f"run={run.id} workflow={run.workflow_id} status={run.status}", markup=False)
    if run.pending_plan_id:
        console.print(f"plan={run.pending_plan_id}", markup=False)
        console.print(
            f"datakeel workflow resume {run.id} --plan {run.pending_plan_id}", markup=False
        )
    if run.error:
        console.print(f"error={run.error}", markup=False)
    for step in run.steps:
        detail = f" plan={step.plan_id}" if step.plan_id else ""
        failure = f" error={step.error}" if step.error else ""
        console.print(f"  [{step.status}] {step.id} ({step.type}){detail}{failure}", markup=False)
    for entry in audits:
        plan_note = f" plan={entry.plan_id}" if entry.plan_id else ""
        console.print(f"  audit={entry.kind}{plan_note} reason={entry.reason}", markup=False)


def dispatch(args: argparse.Namespace) -> None:
    """Print contracts, validation diagnostics, run history or durable workflow execution."""
    console = Console()
    json_output = bool(getattr(args, "json_output", False))
    if args.workflow_command == "list":
        definitions = list_workflows()
        if json_output:
            _print_json(console, [item.model_dump(mode="json") for item in definitions])
        else:
            for definition in definitions:
                console.print(f"{definition.id}: {definition.name}", markup=False)
    elif args.workflow_command == "validate":
        errors = validate_workflow(args.file)
        if json_output:
            _print_json(console, {"valid": not errors, "errors": errors})
        else:
            console.print(
                "\n".join(errors) if errors else "Workflow definition is valid.", markup=False
            )
        if errors:
            raise SystemExit(1)
    elif args.workflow_command == "runs":
        _list_runs(args, console)
    elif args.workflow_command == "show":
        _show_run(args, console)
    else:
        _run(args, console)
