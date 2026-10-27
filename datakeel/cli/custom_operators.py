# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Submit and review custom operators without executing submitted code on the host."""

import argparse
import json
from pathlib import Path

from rich.console import Console

from datakeel.actions import service
from datakeel.actions.custom_runs import schedule_custom_run
from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.cli.parsers import CommandGroup
from datakeel.core.custom_operators import CustomOperatorSubmission
from datakeel.core.custom_requests import RunCustomOperatorRequest
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.storage import custom_store
from datakeel.storage.database import Database


def register_parser(commands: CommandGroup) -> None:
    """Register explicit submission, review, approval and task scheduling commands."""
    group = commands.add_parser("custom-operator")
    children = group.add_subparsers(dest="custom_command", required=True)
    submit = children.add_parser("submit")
    submit.add_argument("file", type=Path)
    submit.add_argument("--name", required=True)
    submit.add_argument("--modality", choices=["any", "text", "image"], default="any")
    children.add_parser("list")
    children.add_parser("runs")
    review = children.add_parser("review")
    review.add_argument("plan_id")
    approve = children.add_parser("approve")
    approve.add_argument("plan_id")
    approve.add_argument("--digest", required=True)
    approve.add_argument("--reject", action="store_true")
    approve.add_argument("--reason", default="Local code review")
    show = children.add_parser("show")
    show.add_argument("code_hash")
    show.add_argument("--name")
    run = children.add_parser("run")
    run.add_argument("code_hash")
    run.add_argument("--name")
    run.add_argument("--dataset", required=True)
    run.add_argument("--version")
    run.add_argument("--params", default="{}")


def _approve(db: Database, args: argparse.Namespace) -> BoundaryModel:
    plan = service.get_plan(db, args.plan_id)
    if args.reject or plan.status not in {"APPROVED", "EXECUTED"}:
        plan = service.approve_plan(
            db,
            args.plan_id,
            ApprovalDecision(
                approve=not args.reject,
                plan_digest=args.digest,
                reason=args.reason,
            ),
        )
    if args.reject:
        return plan
    return service.execute_plan(
        db,
        plan.id,
        ExecuteRequest(plan_digest=args.digest, operation_id=plan.operation_id),
    )


def _command(db: Database, args: argparse.Namespace) -> BoundaryModel | list[BoundaryModel]:
    if args.custom_command == "submit":
        submission = CustomOperatorSubmission(
            name=args.name, code=args.file.read_text(encoding="utf-8"), modality=args.modality
        )
        return service.prepare_action(
            db, "submit_custom_operator", JsonDocument(submission.model_dump(mode="json"))
        )
    if args.custom_command in {"list", "runs"}:
        return (
            list(custom_store.list_custom_operators(db))
            if args.custom_command == "list"
            else list(custom_store.list_custom_runs(db))
        )
    if args.custom_command == "review":
        return service.get_plan(db, args.plan_id)
    if args.custom_command == "approve":
        return _approve(db, args)
    if args.custom_command == "show":
        return custom_store.get_custom_operator(db, args.code_hash, args.name)
    return schedule_custom_run(
        db,
        args.code_hash,
        RunCustomOperatorRequest(
            dataset_id=args.dataset,
            version_id=args.version,
            params=JsonDocument.model_validate_json(args.params).root,
            name=args.name,
        ),
    )


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Print complete reviewable JSON; approval always requires the displayed digest."""
    result = _command(db, args)
    document = (
        [item.model_dump(mode="json") for item in result]
        if isinstance(result, list)
        else result.model_dump(mode="json")
    )
    Console().print(
        json.dumps(document, ensure_ascii=False, indent=2),
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
