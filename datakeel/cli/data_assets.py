# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Inspect asset cards and execute explicit controlled publication and grant plans."""

import argparse
from pathlib import Path
from typing import Literal

from rich.console import Console

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.assets.service import get_asset_card, search_market
from datakeel.cli.parsers import CommandGroup
from datakeel.core.data_asset_models import AssetApplicationInput, AssetMarketQuery, AssetUsageQuery
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.data_asset_grants import list_applications, list_grants, submit_application
from datakeel.storage.data_asset_store import asset_history
from datakeel.storage.database import Database

ACTIONS = (
    "create_data_asset",
    "update_data_asset",
    "publish_data_asset",
    "withdraw_data_asset",
    "decide_asset_application",
    "revoke_asset_grant",
)


def register_parser(commands: CommandGroup) -> None:
    """Register asset reads and explicit prepare, approval and execution commands."""
    group = commands.add_parser("data-assets")
    subcommands = group.add_subparsers(dest="asset_command", required=True)
    market = subcommands.add_parser("list")
    market.add_argument("--search", default="")
    market.add_argument("--include-unpublished", action="store_true")
    market.add_argument(
        "--sort",
        choices=["popular", "freshness", "quality", "downstream", "name"],
        default="popular",
    )
    for command in ("show", "history"):
        subcommands.add_parser(command).add_argument("id")
    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("action", choices=ACTIONS)
    prepare.add_argument("file", type=Path)
    prepare.add_argument("--actor", default="local")
    for command in ("approve", "reject", "execute"):
        sub = subcommands.add_parser(command)
        sub.add_argument("id")
        sub.add_argument("--digest", required=True)
        sub.add_argument("--actor", default="local")
    apply = subcommands.add_parser("apply")
    apply.add_argument("file", type=Path)
    apply.add_argument("--applicant", default="local-user")
    grants = subcommands.add_parser("grants")
    grants.add_argument("--asset-id")
    grants.add_argument("--subject")
    requests = subcommands.add_parser("applications")
    requests.add_argument("--asset-id")
    requests.add_argument("--applicant")
    audit = subcommands.add_parser("audit")
    audit.add_argument("--asset-id")
    audit.add_argument("--actor")


def _control(db: Database, args: argparse.Namespace) -> BoundaryModel:
    if args.asset_command == "prepare":
        return service.prepare_action(
            db,
            args.action,
            JsonDocument.model_validate_json(args.file.read_text(encoding="utf-8")),
            ActionContext(actor=args.actor),
        )
    if args.asset_command in {"approve", "reject"}:
        return service.approve_plan(
            db,
            args.id,
            ApprovalDecision(
                approve=args.asset_command == "approve", plan_digest=args.digest, actor=args.actor
            ),
        )
    return service.execute_plan(
        db, args.id, ExecuteRequest(plan_digest=args.digest, actor=args.actor)
    )


def _read(db: Database, args: argparse.Namespace) -> BoundaryModel | tuple[BoundaryModel, ...]:
    if args.asset_command == "list":
        status: Literal["published"] | None = None if args.include_unpublished else "published"
        return search_market(
            db, AssetMarketQuery(search=args.search, status=status, sort=args.sort)
        )
    if args.asset_command == "show":
        return get_asset_card(db, args.id)
    if args.asset_command == "history":
        return asset_history(db, args.id)
    if args.asset_command == "applications":
        return list_applications(db, args.asset_id, args.applicant)
    if args.asset_command == "grants":
        return list_grants(db, args.asset_id, args.subject)
    return list_usage(db, AssetUsageQuery(asset_id=args.asset_id, actor=args.actor))


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Print frozen JSON results without bypassing approval or request validation."""
    if args.asset_command in {"prepare", "approve", "reject", "execute"}:
        result = _control(db, args)
    elif args.asset_command == "apply":
        result = submit_application(
            db,
            AssetApplicationInput.model_validate_json(args.file.read_text(encoding="utf-8")),
            args.applicant,
        )
    else:
        result = _read(db, args)
    console = Console()
    if isinstance(result, tuple):
        for value in result:
            console.print(value.model_dump_json(), markup=False, highlight=False, soft_wrap=True)
    else:
        console.print(result.model_dump_json(), markup=False, highlight=False, soft_wrap=True)
