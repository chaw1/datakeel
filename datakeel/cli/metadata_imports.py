# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Import local dbt artifacts and offline or configured live Airflow metadata."""

import argparse
from pathlib import Path

from pydantic import ValidationError as ModelValidationError
from rich.console import Console

from datakeel.catalog.importers.airflow_rest import connection_from_settings
from datakeel.catalog.metadata_service import import_airflow, import_airflow_api, import_dbt
from datakeel.cli.parsers import CommandGroup
from datakeel.core.errors import DatakeelError
from datakeel.core.metadata_imports import AirflowImportRequest, AirflowSource, DbtImportRequest
from datakeel.core.models import JsonDocument
from datakeel.core.settings import get_settings
from datakeel.storage.database import Database


def register_parser(commands: CommandGroup) -> None:
    """Register content import commands with local file arguments."""
    group = commands.add_parser("import")
    subcommands = group.add_subparsers(dest="import_kind", required=True)
    dbt = subcommands.add_parser("dbt")
    dbt.add_argument("--source-id", required=True)
    dbt.add_argument("--name", default="dbt")
    dbt.add_argument("--manifest", required=True, type=Path)
    dbt.add_argument("--catalog", type=Path)
    dbt.add_argument("--run-results", type=Path)
    airflow = subcommands.add_parser("airflow")
    airflow.add_argument("--source-id", required=True)
    airflow.add_argument("--name", default="Airflow")
    origin = airflow.add_mutually_exclusive_group(required=True)
    origin.add_argument("--file", type=Path)
    origin.add_argument("--api", action="store_true")
    airflow.add_argument("--dag", action="append", default=[])


def _read(path: Path) -> JsonDocument:
    return JsonDocument.model_validate_json(path.read_text(encoding="utf-8"))


def _optional(path: Path | None) -> JsonDocument | None:
    return _read(path) if path else None


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Decode artifacts, publish a typed import, and print its machine-readable summary."""
    console = Console()
    try:
        if args.import_kind == "dbt":
            report = import_dbt(
                db,
                DbtImportRequest(
                    source_id=args.source_id,
                    name=args.name,
                    manifest=_read(args.manifest),
                    catalog=_optional(args.catalog),
                    run_results=_optional(args.run_results),
                ),
            )
        elif args.api:
            report = import_airflow_api(
                db,
                AirflowSource(source_id=args.source_id, name=args.name, dag_ids=tuple(args.dag)),
                connection_from_settings(get_settings()),
            )
        else:
            report = import_airflow(
                db,
                AirflowImportRequest(
                    source_id=args.source_id, name=args.name, document=_read(args.file)
                ),
            )
    except (OSError, UnicodeError, ModelValidationError, DatakeelError, ValueError) as error:
        console.print(f"Import failed: {error}", markup=False, highlight=False)
        raise SystemExit(1) from error
    console.print(report.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True)
