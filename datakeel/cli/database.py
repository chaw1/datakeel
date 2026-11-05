# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Early-dispatched, JSON-only database maintenance commands."""

import argparse
import sys
from pathlib import Path
from typing import NoReturn

from pydantic import ValidationError as ModelError
from rich.console import Console

from datakeel.cli.parsers import CommandGroup
from datakeel.core.errors import ValidationError
from datakeel.core.settings import get_settings
from datakeel.versioning import database_path
from datakeel.versioning.campaign import status, upgrade
from datakeel.versioning.location import MaintenanceLocation
from datakeel.versioning.models import DatabaseStatus
from datakeel.versioning.recovery import restore_package
from datakeel.versioning.registry import registry


class CommandParser(argparse.ArgumentParser):
    """Preserve ordinary CLI usage, with stable JSON parameter errors for maintenance."""

    def error(self, message: str) -> NoReturn:
        """Emit a typed maintenance error without diagnostic noise on stdout."""
        if len(sys.argv) > 1 and sys.argv[1] in {"db", "migrate"}:
            emit(DatabaseStatus(state="invalid", error=message, exit_code=2))
        super().error(message)


def add_upgrade_options(parser: argparse.ArgumentParser) -> None:
    """Share the exact upgrade grammar with the legacy migrate alias."""
    parser.add_argument("--to", type=int)
    parser.add_argument("--backup-manifest", type=Path)
    parser.add_argument("--json", action="store_true", help="JSON is always emitted")


def register(commands: CommandGroup) -> None:
    """Register forward-only maintenance and isolated recovery."""
    add_upgrade_options(commands.add_parser("migrate"))
    subcommands = commands.add_parser("db").add_subparsers(dest="db_command", required=True)
    subcommands.add_parser("status").add_argument("--json", action="store_true")
    add_upgrade_options(subcommands.add_parser("upgrade"))
    restore = subcommands.add_parser("restore")
    restore.add_argument("--manifest", type=Path, required=True)
    restore.add_argument("--home", type=Path, required=True)


def emit(report: DatabaseStatus) -> NoReturn:
    """Write one unwrapped JSON document and use the documented exit classification."""
    Console(width=100000).print(
        report.model_dump_json(), markup=False, highlight=False, soft_wrap=True
    )
    raise SystemExit(report.exit_code)


def dispatch(args: argparse.Namespace) -> NoReturn:
    """Run before logging, routing configuration or ordinary database initialization."""
    try:
        if args.command == "db" and args.db_command == "restore":
            restore_package(args.manifest, args.home)
            emit(DatabaseStatus(state="isolated"))
        if args.command == "db" and args.db_command == "status":
            location = MaintenanceLocation()
            emit(status(location.path(), location.home, registry()))
        settings = get_settings()
        path = database_path()
        versions = registry()
        report = upgrade(path, settings, versions, to=args.to, manifest=args.backup_manifest)
    except (OSError, ValidationError, ModelError, ValueError) as error:
        restore = args.command == "db" and args.db_command == "restore"
        report = DatabaseStatus(state="invalid", error=str(error), exit_code=4 if restore else 3)
    emit(report)
