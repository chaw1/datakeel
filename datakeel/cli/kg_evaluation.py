# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run offline or explicitly configured graph evaluations and persist comparable reports."""

from pathlib import Path

from rich.console import Console
from rich.table import Table

from datakeel.cli.parsers import CommandGroup
from datakeel.core.kg_contracts import ExtractionProfile
from datakeel.core.kg_eval_models import KGEvalReport
from datakeel.kg.loader import get_profile, get_schema, load_profile
from datakeel.kg_eval.service import evaluate_kg
from datakeel.storage.database import Database
from datakeel.storage.kg_evaluations import save_evaluation


def register_parser(commands: CommandGroup) -> None:
    """Expose deterministic replay by default with external same-schema cases as an option."""
    command = commands.add_parser("eval-kg")
    command.add_argument("--profile", default="replay-demo", help="Bundled profile ID or YAML file")
    command.add_argument("--schema", default="business-knowledge")
    command.add_argument(
        "--cases", type=Path, help="External evaluation YAML in the documented format"
    )
    command.add_argument("--json", dest="json_output", action="store_true")


def _profile(value: str) -> ExtractionProfile:
    path = Path(value)
    if path.is_file():
        profile = load_profile(path)
        if profile.recording and not Path(profile.recording).is_absolute():
            profile = profile.model_copy(
                update={"recording": str((path.parent / profile.recording).resolve())}
            )
        return profile
    return get_profile(value)


def _display(report: KGEvalReport, console: Console) -> None:
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
    console.print(f"Saved evaluation: {report.id}", markup=False)


def evaluate(
    db: Database,
    profile: str = "replay-demo",
    cases: Path | None = None,
    *,
    schema: str = "business-knowledge",
    json_output: bool = False,
) -> KGEvalReport:
    """Build only the explicitly selected provider, score both paths, and save one report."""
    # Load vendor SDKs only when this evaluation command explicitly executes.
    from datakeel.extraction_runtime.factory import create_extractor  # noqa: PLC0415

    configuration = _profile(profile)
    vocabulary = get_schema(schema)
    with create_extractor(configuration) as adapter:
        report = evaluate_kg(configuration, vocabulary, adapter, cases)
    report = save_evaluation(db, report)
    console = Console()
    if json_output:
        console.print(
            report.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True
        )
    else:
        _display(report, console)
    return report
