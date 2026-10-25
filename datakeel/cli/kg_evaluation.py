# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run offline or explicitly configured graph evaluations and persist comparable reports."""

from decimal import Decimal
from pathlib import Path

from rich.console import Console
from rich.table import Table

from datakeel.cli.parsers import CommandGroup
from datakeel.core.errors import BudgetError
from datakeel.core.harness_models import BudgetLimits
from datakeel.core.kg_contracts import ExtractionProfile
from datakeel.core.kg_eval_models import KGEvalReport
from datakeel.core.models import new_id
from datakeel.kg.loader import get_profile, get_schema, load_profile
from datakeel.kg_eval.service import evaluate_kg
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_evaluations import save_evaluation
from datakeel.storage.kg_pricing import metering_config
from datakeel.worker.kg_metering import MeteredExtractor


def register_parser(commands: CommandGroup) -> None:
    """Expose deterministic replay by default with external same-schema cases as an option."""
    command = commands.add_parser("eval-kg")
    command.add_argument(
        "--profile", default="replay-demo", help="Bundled extraction profile ID or YAML file"
    )
    command.add_argument("--schema", default="business-knowledge")
    command.add_argument("--suite", choices=("text", "image"), default="text")
    command.add_argument("--transcription-profile", default="replay-image-demo")
    command.add_argument(
        "--cases", type=Path, help="External evaluation YAML in the documented format"
    )
    command.add_argument("--json", dest="json_output", action="store_true")
    command.add_argument("--budget-tokens", type=int, default=250_000)
    command.add_argument("--max-cost-usd", type=Decimal, default=Decimal(5))


def load_evaluation_profile(value: str) -> ExtractionProfile:
    """Resolve a bundled extraction ID or an explicit local configuration file."""
    path = Path(value)
    if path.is_file():
        profile = load_profile(path)
        if profile.recording and not Path(profile.recording).is_absolute():
            profile = profile.model_copy(
                update={"recording": str((path.parent / profile.recording).resolve())}
            )
        return profile
    return get_profile(value)


def display_evaluation(report: KGEvalReport, console: Console) -> None:
    """Display the shared recording and production score summary."""
    console.print(f"Knowledge graph: {report.profile}; model={report.model}", markup=False)
    table = Table("Scoring path", "Precision", "Recall", "F1", "Traps", "Failed blocks")
    for name, metrics in (
        ("Recording / all", report.recording.all),
        ("Recording / verified", report.recording.verified),
        ("Product / all candidates", report.product.all),
        ("Product / verified", report.product.verified),
    ):
        score = metrics.relation_strict
        table.add_row(
            name,
            f"{score.p:.3f}",
            f"{score.r:.3f}",
            f"{score.f1:.3f}",
            str(metrics.trap_hits),
            str(metrics.failed_blocks),
        )
    console.print(table)
    console.print(
        f"Product language F1: zh={report.product.zh.relation_strict.f1:.3f}; "
        f"en={report.product.en.relation_strict.f1:.3f}"
    )
    cost = str(report.cost_usd) if report.cost_usd is not None else "unknown"
    console.print(
        f"Execution: {report.elapsed_seconds:.2f}s; "
        f"tokens={report.input_tokens + report.output_tokens}; cost USD={cost}; "
        f"blocked relations={len(report.blocked_relations)}"
    )
    for failure in report.failures:
        console.print(
            f"Failed block: {failure.case_id} [{failure.start}, {failure.end}): {failure.reason}",
            markup=False,
        )
    console.print(f"Saved evaluation: {report.id}", markup=False)


def evaluate(
    db: Database,
    profile: str = "replay-demo",
    cases: Path | None = None,
    *,
    schema: str = "business-knowledge",
    json_output: bool = False,
    limits: BudgetLimits | None = None,
) -> KGEvalReport:
    """Build only the explicitly selected provider, score both paths, and save one report."""
    # Load vendor SDKs only when this evaluation command explicitly executes.
    from datakeel.extraction_runtime.factory import create_extractor  # noqa: PLC0415

    configuration = load_evaluation_profile(profile)
    vocabulary = get_schema(schema)
    identifier = new_id()
    metering = metering_config(configuration, identifier)
    if limits is not None:
        metering = metering.model_copy(
            update={
                "budget_tokens": limits.conversation_tokens,
                "max_cost_usd": limits.conversation_usd,
            }
        )
    with create_extractor(configuration) as adapter:
        measured = MeteredExtractor(db, metering, adapter)
        report = evaluate_kg(configuration, vocabulary, measured, cases)
        if measured.exceeded:
            msg = "Knowledge graph evaluation exceeded its extraction budget"
            raise BudgetError(msg)
    traces = list_traces(db, identifier)
    usages = [trace.observed_usage or trace.usage for trace in traces]
    report = report.model_copy(
        update={
            "id": identifier,
            "input_tokens": sum(usage.input_tokens for usage in usages),
            "output_tokens": sum(usage.output_tokens for usage in usages),
            "cost_usd": None
            if any(trace.billing_status == "unknown" for trace in traces)
            else sum((trace.cost_usd for trace in traces), start=Decimal(0)),
        }
    )
    report = save_evaluation(db, report)
    console = Console()
    if json_output:
        console.print(
            report.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True
        )
    else:
        display_evaluation(report, console)
    return report
