# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Command-line entry points for the two application roles."""

import argparse
import json
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

import uvicorn
from rich.console import Console

from datakeel.cli import (
    custom_operators,
    data_assets,
    delivery,
    kg_evaluation,
    kg_image_evaluation,
    llm_data,
    media_demo,
    metadata_imports,
    quality,
    release_plans,
    routing,
    standards,
    timeseries_demo,
    training,
    workflow,
)
from datakeel.cli.ask import ask
from datakeel.cli.ask import register_parser as register_ask_parser
from datakeel.cli.ask_evaluation import evaluate_ask
from datakeel.cli.catalog import rebuild as rebuild_catalog
from datakeel.cli.demo import demo, seed_demo
from datakeel.cli.evidence import rebuild
from datakeel.cli.evidence_evaluation import evaluate_evidence
from datakeel.cli.mcp import serve
from datakeel.core.data_asset_models import AccessContext, SkippedEntries
from datakeel.core.errors import NotFoundError
from datakeel.core.harness_models import BudgetLimits
from datakeel.core.kg_image_request import ImageEvaluationRequest
from datakeel.core.logging import configure_logging
from datakeel.core.models import AssetRef
from datakeel.core.settings import get_settings
from datakeel.routing.config import load_config
from datakeel.storage.data_asset_access import skip_protected
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_datasets
from datakeel.storage.lineage_service import export_dataset, export_readable_events
from datakeel.worker.runner import run_worker

__all__ = ["main", "seed_demo"]


def parser() -> argparse.ArgumentParser:
    """Build the stable public command grammar."""
    result = argparse.ArgumentParser(prog="datakeel")
    commands = result.add_subparsers(dest="command", required=True)
    for command in ("demo", "api"):
        sub = commands.add_parser(command)
        sub.add_argument("--host", default="127.0.0.1")
        sub.add_argument("--port", default=8765, type=int)
        if command == "demo":
            sub.add_argument("--once", action="store_true", help="Process demo and exit")
            sub.add_argument(
                "--legacy-only", action="store_true", help="Run the original 400-file scenario"
            )
    worker = commands.add_parser("worker")
    worker.add_argument("--once", action="store_true", help="Drain pending work and exit")
    worker.add_argument("--queue", choices=["cpu", "io", "gpu"], default="cpu")
    commands.add_parser("migrate")
    evidence_rebuild = commands.add_parser("rebuild-evidence")
    evidence_rebuild.add_argument("--expected-hash")
    catalog_rebuild = commands.add_parser("rebuild-catalog")
    catalog_rebuild.add_argument("--expected-hash")
    mcp = commands.add_parser("mcp")
    mcp.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    mcp.add_argument("--host", default="127.0.0.1")
    mcp.add_argument("--port", type=int, default=8766)
    evaluation = commands.add_parser("eval")
    evaluation.add_argument("--provider", choices=["fake", "openai", "anthropic"], default="fake")
    evaluation.add_argument("--golden-dir", type=Path)
    evaluation.add_argument("--json", action="store_true", dest="json_output")
    evidence_evaluation = commands.add_parser("eval-evidence")
    evidence_evaluation.add_argument("--questions", type=Path)
    evidence_evaluation.add_argument("--mode", choices=["prefix", "exact"])
    evidence_evaluation.add_argument("--json", action="store_true", dest="json_output")
    ask_evaluation = commands.add_parser("eval-ask")
    ask_evaluation.add_argument("--questions", type=Path)
    ask_evaluation.add_argument("--json", action="store_true", dest="json_output")
    register_ask_parser(commands)
    export = commands.add_parser("export")
    export.add_argument("--format", choices=["openlineage", "croissant"], required=True)
    export.add_argument("--dataset")
    export.add_argument("--output", type=Path)
    for module in (
        workflow,
        routing,
        kg_evaluation,
        timeseries_demo,
        media_demo,
        llm_data,
        custom_operators,
        delivery,
        data_assets,
        standards,
        quality,
        metadata_imports,
        release_plans,
        training,
    ):
        module.register_parser(commands)
    return result


def _report_skipped(skipped: SkippedEntries | None, kind: str) -> None:
    # The exported document keeps its standard shape; skipped entries are reported on stderr.
    if skipped is not None:
        Console(stderr=True).print(
            f"Skipped {skipped.count} protected {kind}: {', '.join(skipped.ids)}. "
            f"Assets: {', '.join(skipped.assets)}. {skipped.reason}.",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )


def _export(db: Database, args: argparse.Namespace) -> None:
    if args.format == "openlineage":
        events, skipped = export_readable_events(db, args.dataset)
        _report_skipped(skipped, "events")
        result = [event.model_dump(mode="json") for event in events]
        encoded = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        identifier = args.dataset
        if identifier is None:
            # Without an explicit dataset, export the first one this operator may read.
            datasets = list_datasets(db)
            skipped = skip_protected(
                db,
                [(value.id, (AssetRef(asset_id=value.id),)) for value in datasets],
                AccessContext(actor="local-user", entry="export", scope="export"),
            )
            hidden: set[str] = set(skipped.ids) if skipped else set()
            readable = [value.id for value in datasets if value.id not in hidden]
            if not readable:
                msg = "No readable dataset found; run datakeel demo first or apply for access"
                raise NotFoundError(msg)
            _report_skipped(skipped, "datasets")
            identifier = readable[0]
        document = export_dataset(db, identifier, get_settings().base_url)
        encoded = json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        Console().print(encoded, markup=False, highlight=False, soft_wrap=True)


def main() -> None:
    """Dispatch a validated local command and configure structured diagnostics."""
    args = parser().parse_args()
    if args.command == "reconcile":
        delivery.offline_command(args)
        return
    configure_logging()
    if args.command in {"routing", "eval-route"}:
        routing.dispatch(args)
        return
    load_config()
    if args.command == "workflow":
        workflow.dispatch(args)
        return
    if args.command == "demo":
        demo(args)
        return
    if args.command == "api":
        # Register HTTP routes only when starting the HTTP server.
        from datakeel.api.app import create_app  # noqa: PLC0415

        uvicorn.run(create_app(), host=args.host, port=args.port)
        return
    db = Database()
    db.migrate()
    _database_command(db, args)


# Feature command groups that own their own dispatch over the initialized fact store.
_MODULE_COMMANDS: dict[str, Callable[[Database, argparse.Namespace], None]] = {
    "timeseries-demo": timeseries_demo.dispatch,
    "demo-media": media_demo.dispatch,
    "custom-operator": custom_operators.dispatch,
    "version-diff": delivery.database_command,
    "release-export": delivery.database_command,
    "release-reconcile": delivery.database_command,
    "data-assets": data_assets.dispatch,
    "standards": standards.dispatch,
    "quality": quality.dispatch,
    "training-quality": llm_data.dispatch,
    "import": metadata_imports.dispatch,
    "release-plan": release_plans.dispatch,
    "training": training.dispatch,
}


def _database_command(db: Database, args: argparse.Namespace) -> None:
    """Dispatch commands that share an initialized authoritative fact store."""
    handler = _MODULE_COMMANDS.get(args.command)
    if handler is not None:
        handler(db, args)
    elif args.command == "migrate":
        Console().print("Database schema is current.")
    elif args.command == "worker":
        with suppress(KeyboardInterrupt):
            run_worker(db, once=args.once, queue_name=args.queue)
    elif args.command == "export":
        _export(db, args)
    elif args.command in {"eval", "eval-evidence", "eval-ask", "eval-kg"}:
        _evaluation_command(db, args)
    elif args.command == "mcp":
        serve(db, args.transport, args.host, args.port)
    elif args.command == "rebuild-evidence":
        rebuild(db, args.expected_hash)
    elif args.command == "rebuild-catalog":
        rebuild_catalog(db, args.expected_hash)
    elif args.command == "ask":
        ask(db, args.question, args.reference_instant, args.conversation_id)


def _evaluation_command(db: Database, args: argparse.Namespace) -> None:
    """Select one isolated benchmark while preserving its distinct reporting contract."""
    if args.command == "eval":
        from datakeel.cli.evaluation import evaluate  # noqa: PLC0415

        evaluate(db, args.provider, args.golden_dir, json_output=args.json_output)
    elif args.command == "eval-evidence":
        evaluate_evidence(db, args.questions, json_output=args.json_output, mode=args.mode)
    elif args.command == "eval-kg" and args.suite == "image":
        kg_image_evaluation.evaluate(
            db,
            ImageEvaluationRequest(
                profile="replay-image-flash" if args.profile == "replay-demo" else args.profile,
                transcription_profile=args.transcription_profile,
                transcription_mode=args.transcription_mode,
                schema_id=args.schema,
                cases=args.cases,
            ),
            json_output=args.json_output,
            limits=BudgetLimits(
                conversation_tokens=args.budget_tokens, conversation_usd=args.max_cost_usd
            ),
        )
    elif args.command == "eval-kg":
        kg_evaluation.evaluate(
            db,
            args.profile,
            args.cases,
            schema=args.schema,
            json_output=args.json_output,
            limits=BudgetLimits(
                conversation_tokens=args.budget_tokens, conversation_usd=args.max_cost_usd
            ),
        )
    else:
        evaluate_ask(db, args.questions, json_output=args.json_output)
