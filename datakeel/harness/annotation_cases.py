# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seed fictional annotation panels through the actual import and approval services."""

from pathlib import Path

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.annotation_aql import lookup_aql
from datakeel.core.annotation_models import AnnotationBatch
from datakeel.core.annotation_sampling import (
    AnnotationAcceptanceParams,
    AnnotationImportRequest,
    AnnotationQualityReport,
    InspectionCheck,
    SamplingRequest,
)
from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.harness_eval import CaseFixture
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.core.settings import get_settings
from datakeel.sample_annotation_qa import AnnotationQASamples, generate_annotation_qa_samples
from datakeel.storage.annotation_sampling import create_sampling_plan, select_sample
from datakeel.storage.annotation_store import get_annotation_quality, import_annotations
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_datasets, list_files, list_versions
from datakeel.storage.views import DatasetView

ANNOTATION_DEMO_NAME = "Aster harbor · annotation quality demo"
DEMO_AQL = 6.5
DEMO_DEFECTS = 2


class AnnotationDemoSummary(BoundaryModel):
    """Identify the generated source version, revision comparison and approved inspection."""

    dataset_id: str
    version_id: str
    file_id: str
    initial_batch_id: str
    reworked_batch_id: str
    sample_count: int
    annotation_count: int


def _bind(batch: AnnotationBatch, identifiers: dict[str, str]) -> AnnotationBatch:
    return batch.model_copy(
        update={
            "annotations": tuple(
                record.model_copy(update={"sample_id": identifiers[record.sample_id]})
                for record in batch.annotations
            ),
            "near_duplicates": tuple(
                pair.model_copy(
                    update={
                        "sample_id": identifiers[pair.sample_id],
                        "other_sample_id": identifiers[pair.other_sample_id],
                    }
                )
                for pair in batch.near_duplicates
            ),
        }
    )


def _demo_seed(population: tuple[str, ...], flagged: set[str]) -> int:
    """Pick the first seed from 26 whose AQL sample holds exactly two flagged units.

    File identities are generated at import, so a fixed seed would draw different
    units in every workspace; this keeps the demonstrated rejection reproducible.
    """
    plan = lookup_aql(len(population), DEMO_AQL)
    return next(
        seed
        for seed in range(26, 10_026)
        if len(set(select_sample(population, plan.sample_size, seed)) & flagged) == DEMO_DEFECTS
    )


def _inspect(db: Database, report: AnnotationQualityReport, population: tuple[str, ...]) -> None:
    """Draw the AQL 6.5 sample and confirm every sampled unit that has a rule finding."""
    reasons = {item.sample_id: f"{item.code}: {item.reason}" for item in report.result.findings}
    sampling = create_sampling_plan(
        db,
        report.dataset_id,
        SamplingRequest(
            batch_id=report.id, aql=DEMO_AQL, seed=_demo_seed(population, set(reasons))
        ),
    )
    params = AnnotationAcceptanceParams(
        dataset_id=sampling.dataset_id,
        version_id=sampling.version_id,
        batch_id=sampling.batch_id,
        sampling_id=sampling.id,
        checks=tuple(
            InspectionCheck(
                sample_id=sample_id,
                defective=sample_id in reasons,
                reason=f"Generated example: reviewer confirmed {reasons[sample_id]}"
                if sample_id in reasons
                else "",
            )
            for sample_id in sampling.sample_ids
        ),
    )
    plan = prepare_action(
        db, "annotation_acceptance", JsonDocument.model_validate(params.model_dump(mode="json"))
    )
    approve_plan(db, plan.id, ApprovalDecision(plan_digest=plan.plan_digest, approve=True))
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    if run.status != "SUCCEEDED":
        raise ExecutionError(run.error or "Generated annotation inspection did not complete")


def _demo_dataset(db: Database, samples: AnnotationQASamples) -> DatasetView:
    if get_settings().s3_bucket:
        message = "Generated annotation demo requires local storage; unset DATAKEEL_S3_BUCKET"
        raise ValidationError(message)
    dataset = next((item for item in list_datasets(db) if item.name == ANNOTATION_DEMO_NAME), None)
    if dataset is not None:
        return dataset
    return import_paths(
        db,
        ANNOTATION_DEMO_NAME,
        list(samples.paths),
        {
            "annotation_qa_demo": True,
            "description": "Fictional harbor images with generated notes and three reviewers.",
        },
    )


def seed_annotation_qa_demo(db: Database, directory: Path) -> AnnotationDemoSummary:
    """Import panels, record an approved AQL inspection, then import the rework revision."""
    samples = generate_annotation_qa_samples(directory)
    dataset = _demo_dataset(db, samples)
    version = list_versions(db, dataset.id)[0].id
    files = list_files(db, dataset.id, version)
    identifiers = {file.filename: file.id for file in files}

    def load(batch: AnnotationBatch, name: str, rework_of: str | None) -> AnnotationQualityReport:
        return import_annotations(
            db,
            dataset.id,
            AnnotationImportRequest(
                version_id=version,
                batch=_bind(batch, identifiers),
                idempotency_key=f"annotation-demo:{version}:{name.split(maxsplit=1)[0].lower()}",
                name=name,
                rework_of=rework_of,
            ),
        )

    initial = load(samples.initial, "Initial harbor annotations", None)
    if not get_annotation_quality(db, dataset.id, version).inspections:
        _inspect(db, initial, tuple(sorted(identifiers.values())))
    reworked = load(samples.reworked, "Reworked harbor annotations", initial.id)
    return AnnotationDemoSummary(
        dataset_id=dataset.id,
        version_id=version,
        file_id=files[0].id,
        initial_batch_id=initial.id,
        reworked_batch_id=reworked.id,
        sample_count=initial.sample_count,
        annotation_count=initial.annotation_count,
    )


def seed_annotation_case(db: Database, directory: Path) -> CaseFixture:
    """Expose only generated identities to golden assertions and scripted prompts."""
    result = seed_annotation_qa_demo(db, directory)
    return CaseFixture(
        dataset_id=result.dataset_id, version_id=result.version_id, file_id=result.file_id
    )
