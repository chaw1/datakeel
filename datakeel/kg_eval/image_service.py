# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate frozen image recordings and independently persisted production candidates."""

from __future__ import annotations

import hashlib
import unicodedata
from decimal import Decimal
from time import perf_counter
from typing import TYPE_CHECKING

from datakeel.core.kg_eval_models import KGCaseSuite, KGEvalReport, ScoredRecord
from datakeel.kg.loader import contracts_path
from datakeel.kg_eval.image_execution import ImageCaseExecution, ImageCaseRunner
from datakeel.kg_eval.image_loader import image_path, load_image_cases
from datakeel.kg_eval.image_metrics import image_scores
from datakeel.kg_eval.loader import load_recording
from datakeel.kg_eval.scoring import score_views
from datakeel.storage.database import Database
from datakeel.transcription.alignment import match_box

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
    from datakeel.core.kg_eval_models import ScoredRelation
    from datakeel.core.transcription_models import TranscriptionProfile
    from datakeel.kg.extractors import ExtractorAdapter
    from datakeel.transcription.quality import TranscriberAdapter


def _recorded(
    executions: tuple[ImageCaseExecution, ...], profile: ExtractionProfile
) -> tuple[ScoredRecord, ...]:
    archive = (
        load_recording(contracts_path() / profile.recording)
        if profile.extractor == "replay" and profile.recording
        else None
    )
    originals = {record.text_hash: record.original for record in archive.records} if archive else {}
    records: list[ScoredRecord] = []
    for execution in executions:
        transcript = execution.transcript
        text = unicodedata.normalize("NFC", transcript.text)
        original = originals.get(hashlib.sha256(text.encode()).hexdigest())
        record = ScoredRecord.model_validate(original) if original is not None else execution.raw
        relations: list[ScoredRelation] = []
        for relation in record.relations:
            box = match_box(
                relation.evidence or "", transcript.lines, transcript.width, transcript.height
            )
            relations.append(relation.model_copy(update={"regions": (box,) if box else ()}))
        records.append(
            record.model_copy(update={"pid": execution.raw.pid, "relations": tuple(relations)})
        )
    return tuple(records)


def evaluate_image(
    profile: ExtractionProfile,
    schema: KGSchema,
    extractor: ExtractorAdapter,
    transcription: TranscriptionProfile,
    transcriber: TranscriberAdapter,
    cases_path: Path | None = None,
) -> KGEvalReport:
    """Score read-back assertions in a fresh local database without polluting the user's graph."""
    started = perf_counter()
    suite, digest, directory = load_image_cases(schema, cases_path)
    db = Database("sqlite://")
    try:
        db.migrate()
        runner = ImageCaseRunner(db, schema, profile, transcription, extractor, transcriber)
        executions = tuple(
            runner.execute(case, image_path(directory, case.image)) for case in suite.cases
        )
    finally:
        db.engine.dispose()
    recorded = _recorded(executions, profile)
    products = tuple(execution.product for execution in executions)
    transcripts = {execution.raw.pid: execution.transcript for execution in executions}
    labels = {relation.name for relation in schema.relations}
    text_suite = KGCaseSuite(id=suite.id, version=suite.version, cases=suite.cases)
    offline = profile.extractor in {"fake", "replay", "gliner2"} and transcription.backend in {
        "fake",
        "replay",
        "ocr",
    }
    return KGEvalReport(
        suite="image",
        transcription_profile=transcription.id,
        profile=profile.id,
        model=profile.model,
        suite_digest=digest,
        recording=score_views(recorded, text_suite, labels),
        product=score_views(products, text_suite, labels),
        image_recording=image_scores(recorded, suite, labels, transcripts),
        image_product=image_scores(products, suite, labels, transcripts),
        blocked_relations=tuple(item for execution in executions for item in execution.blocked),
        failures=tuple(item for execution in executions for item in execution.failures),
        elapsed_seconds=perf_counter() - started,
        cost_usd=Decimal(0) if offline else None,
        transcription_cost_usd=Decimal(0) if transcription.backend != "vlm" else None,
        extraction_cost_usd=Decimal(0) if profile.extractor != "llm" else None,
        metric_convention=(
            "Independent recording scores merge each quote's OCR fragments into one rectangle. "
            "Product scores read back persisted candidates and compare the enclosing rectangle "
            "of all ImageRegion rectangles with any gold box at IoU >= 0.5. Missing gold boxes "
            "are excluded from localisation denominators. Identical transcript hashes "
            "retain the smallest case ID."
        ),
    )
