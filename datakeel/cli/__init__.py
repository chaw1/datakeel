# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Command-line entry points for the two application roles."""

import argparse
import json
from contextlib import suppress
from pathlib import Path

import uvicorn
from rich.console import Console

from datakeel.cli import delivery, kg_evaluation, kg_image_evaluation, routing, workflow
from datakeel.cli.ask import ask
from datakeel.cli.ask_evaluation import evaluate_ask
from datakeel.cli.catalog import rebuild as rebuild_catalog
from datakeel.cli.demo import demo, seed_demo
from datakeel.cli.evaluation import evaluate
from datakeel.cli.evidence import rebuild
from datakeel.cli.evidence_evaluation import evaluate_evidence
from datakeel.cli.mcp import serve
from datakeel.core.errors import NotFoundError
from datakeel.core.harness_models import BudgetLimits
from datakeel.core.kg_image_request import ImageEvaluationRequest
from datakeel.core.logging import configure_logging
from datakeel.core.settings import get_settings
from datakeel.routing.config import load_config
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_datasets
from datakeel.storage.lineage_service import export_dataset, export_events
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
    evidence_evaluation.add_argument("--json", action="store_true", dest="json_output")
    ask_evaluation = commands.add_parser("eval-ask")
    ask_evaluation.add_argument("--questions", type=Path)
    ask_evaluation.add_argument("--json", action="store_true", dest="json_output")
    question = commands.add_parser("ask")
    question.add_argument("question")
    question.add_argument("--reference-instant")
    export = commands.add_parser("export")
    export.add_argument("--format", choices=["openlineage", "croissant"], required=True)
    export.add_argument("--dataset")
    export.add_argument("--output", type=Path)
    for module in (workflow, routing, kg_evaluation, delivery):
        module.register_parser(commands)
    return result


def _export(db: Database, args: argparse.Namespace) -> None:
    if args.format == "openlineage":
        result = [event.model_dump(mode="json") for event in export_events(db, args.dataset)]
        encoded = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        datasets = list_datasets(db)
        identifier = args.dataset or (datasets[0].id if datasets else None)
        if identifier is None:
            msg = "No dataset found; run datakeel demo first"
            raise NotFoundError(msg)
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


def _database_command(db: Database, args: argparse.Namespace) -> None:
    """Dispatch commands that share an initialized authoritative fact store."""
    if args.command in {"version-diff", "release-export", "release-reconcile"}:
        delivery.database_command(db, args)
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
        ask(db, args.question, args.reference_instant)


def _evaluation_command(db: Database, args: argparse.Namespace) -> None:
    """Select one isolated benchmark while preserving its distinct reporting contract."""
    if args.command == "eval":
        evaluate(db, args.provider, args.golden_dir, json_output=args.json_output)
    elif args.command == "eval-evidence":
        evaluate_evidence(db, args.questions, json_output=args.json_output)
    elif args.command == "eval-kg" and args.suite == "image":
        kg_image_evaluation.evaluate(
            db,
            ImageEvaluationRequest(
                profile="replay-image-flash" if args.profile == "replay-demo" else args.profile,
                transcription_profile=args.transcription_profile,
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
