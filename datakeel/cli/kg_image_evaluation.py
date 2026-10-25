# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run independently metered image evaluation and save both score conventions."""

from decimal import Decimal
from pathlib import Path

from rich.console import Console
from rich.table import Table

from datakeel.cli.kg_evaluation import display_evaluation, load_evaluation_profile
from datakeel.core.errors import BudgetError
from datakeel.core.harness_models import BudgetLimits
from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_eval_models import KGEvalReport
from datakeel.core.kg_execution import KGEstimate, KGJob, KGMeteringConfig, KGPrepared, KGRun
from datakeel.core.kg_image_request import ImageEvaluationRequest
from datakeel.core.kg_images import TranscriptionEstimate
from datakeel.core.models import new_id, utcnow
from datakeel.core.transcription_models import TranscriptionProfile
from datakeel.extraction_runtime.factory import create_extractor
from datakeel.kg.loader import get_schema
from datakeel.kg.prompt import image_profile
from datakeel.kg_eval.image_service import evaluate_image
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_evaluations import save_evaluation
from datakeel.storage.kg_pricing import metering_config
from datakeel.storage.transcription_pricing import transcription_metering
from datakeel.transcription.factory import create_transcriber
from datakeel.transcription.loader import get_profile, load_profile
from datakeel.worker.kg_metering import MeteredExtractor
from datakeel.worker.transcription_metering import MeteredTranscriber


def _profile(value: str) -> TranscriptionProfile:
    path = Path(value)
    profile = load_profile(path) if path.is_file() else get_profile(value)
    if path.is_file() and profile.recording and not Path(profile.recording).is_absolute():
        profile = profile.model_copy(
            update={"recording": str((path.parent / profile.recording).resolve())}
        )
    return profile


def _job(config: KGMeteringConfig, schema: KGSchema, profile: TranscriptionProfile) -> KGJob:
    billing = transcription_metering(profile, config.run_id)
    prepared = KGPrepared(
        schema_definition=schema,
        profile=config.profile,
        documents=(),
        external=False,
        accounting_price=config.price,
        accounting_price_version=config.price_version,
        estimate=KGEstimate(
            target_host=None,
            model=config.profile.model,
            documents=0,
            blocks=0,
            input_tokens=0,
            max_output_tokens=config.profile.max_output_tokens,
        ),
        transcription_profile=profile,
        transcription_accounting_price=billing.price,
        transcription_accounting_version=billing.price_version,
        transcription_estimate=TranscriptionEstimate(
            target_host=None,
            model=profile.model,
            images=0,
            image_tokens=0,
            max_output_tokens=profile.max_output_tokens,
            price=billing.price if billing.known_price else None,
        ),
    )
    return KGJob(
        run=KGRun(
            id=config.run_id,
            dataset_id="image-evaluation",
            version_id="1",
            schema_id=schema.id,
            profile_id=config.profile.id,
            model=config.profile.model,
            extractor=config.profile.extractor,
            status="running",
            created_at=utcnow(),
        ),
        prepared=prepared,
        budget_tokens=config.budget_tokens,
        max_cost_usd=config.max_cost_usd,
    )


def _display(report: KGEvalReport, console: Console) -> None:
    display_evaluation(report, console)
    table = Table("Image scoring", "Group", "F1", "Box IoU hits", "CER", "Identifiers", "Failures")
    for label, view in (("Recording", report.image_recording), ("Product", report.image_product)):
        for group in view.groups if view else ():
            table.add_row(
                label,
                group.name,
                str(group.metrics.relation_strict.f1),
                str(group.box_hit_rate),
                str(group.cer),
                str(group.identifier_preservation),
                str(group.transcription_failures),
            )
    console.print(table)


def evaluate(
    db: Database,
    request: ImageEvaluationRequest,
    *,
    json_output: bool = False,
    limits: BudgetLimits | None = None,
) -> KGEvalReport:
    """Use explicit selected profiles and combine transcription and extraction budget traces."""
    profile = image_profile(load_evaluation_profile(request.profile))
    transcription, schema = _profile(request.transcription_profile), get_schema(request.schema_id)
    config = metering_config(profile, new_id())
    if limits is not None:
        config = config.model_copy(
            update={
                "budget_tokens": limits.conversation_tokens,
                "max_cost_usd": limits.conversation_usd,
            }
        )
    with create_extractor(profile) as extractor, create_transcriber(transcription) as transcriber:
        extraction = MeteredExtractor(db, config, extractor)
        measured = MeteredTranscriber(db, _job(config, schema, transcription), transcriber)
        report = evaluate_image(profile, schema, extraction, transcription, measured, request.cases)
        if extraction.exceeded or measured.exceeded:
            msg = "Image evaluation exceeded its model budget"
            raise BudgetError(msg)
    traces = list_traces(db, config.run_id)
    usage = [trace.observed_usage or trace.usage for trace in traces]
    report = report.model_copy(
        update={
            "id": config.run_id,
            "input_tokens": sum(item.input_tokens for item in usage),
            "output_tokens": sum(item.output_tokens for item in usage),
            "cost_usd": None
            if any(trace.billing_status == "unknown" for trace in traces)
            else sum((trace.cost_usd for trace in traces), start=Decimal(0)),
        }
    )
    save_evaluation(db, report)
    console = Console()
    if json_output:
        console.print(
            report.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True
        )
    else:
        _display(report, console)
    return report
