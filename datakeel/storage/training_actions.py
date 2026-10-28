# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish reproducible clean versions only inside an approved controlled transaction."""

import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.actions.training_parameters import CleanTrainingParams
from datakeel.core.errors import ConflictError
from datakeel.core.models import (
    AssetRef,
    BoundaryModel,
    FileItem,
    JsonDocument,
    LineageEvent,
    new_id,
    utcnow,
)
from datakeel.core.training_governance import TrainingAnalysisRequest, TrainingGovernanceRun
from datakeel.llm_data import analyze_sources, cleaned_filename
from datakeel.storage.database import VersionRow
from datakeel.storage.datasets import persist_file
from datakeel.storage.events import append_event
from datakeel.storage.file_state import get_file_state
from datakeel.storage.object_projection import content_digest
from datakeel.storage.objects import digest, fresh_object, object_store
from datakeel.storage.training_evaluations import evaluation_files
from datakeel.storage.training_rows import TrainingCleanRow, TrainingRunRow
from datakeel.storage.training_sources import fresh_sources, source_files, source_version
from datakeel.storage.training_store import require_training_run, save_training_run


def prepare_training(session: Session, params: BoundaryModel) -> BoundaryModel:
    """Replace caller-supplied frozen fields with the actual immutable dry-run facts."""
    if not isinstance(params, CleanTrainingParams):
        return params
    row = require_training_run(session, params.run_id)
    if row.dataset_id != params.dataset_id:
        msg = "Training report does not belong to the dataset"
        raise ConflictError(msg)
    if session.get(TrainingCleanRow, row.id) is not None:
        msg = "Training dry run already produced a clean version"
        raise ConflictError(msg)
    return params.model_copy(
        update={
            "version_id": row.version_id,
            "file_ids": tuple(row.file_ids),
            "report_digest": content_digest(row.payload),
        }
    )


def training_state(session: Session, params: CleanTrainingParams) -> str:
    """Reject changed dry-run facts or a second publication from the same report."""
    row = require_training_run(session, params.run_id)
    if row.dataset_id != params.dataset_id or content_digest(row.payload) != params.report_digest:
        msg = "Training dry-run facts changed after preparation"
        raise ConflictError(msg)
    if session.get(TrainingCleanRow, row.id) is not None:
        msg = "Training dry run already produced a clean version"
        raise ConflictError(msg)
    source = source_version(session, row.dataset_id, row.version_id)
    values = JsonDocument.model_validate(
        {
            "report": row.payload,
            "source_manifest": source.manifest,
            "source_state": {
                str(item["id"]): get_file_state(
                    session, row.dataset_id, str(item["id"])
                ).model_dump()
                for item in source.manifest
            },
        }
    )
    return content_digest(values.root)


def _cleaned_files(original: tuple[FileItem, ...], directory: Path) -> tuple[FileItem, ...]:
    return tuple(
        persist_file(
            FileItem(
                path=str(directory / cleaned_filename(item.id)),
                filename=f"{Path(item.filename).stem}.clean.jsonl",
                modality="text",
                metadata={"training_source_id": item.id},
            )
        )
        for item in original
    )


def _verify_reproduction(row: TrainingRunRow, actual: TrainingGovernanceRun, ledger: Path) -> None:
    expected = TrainingGovernanceRun.model_validate(row.payload)
    if (
        actual.report.source_sha256 != expected.report.source_sha256
        or actual.report.evaluation_sha256 != expected.report.evaluation_sha256
        or actual.report.ledger_sha256 != expected.report.ledger_sha256
        or digest(ledger) != expected.ledger_sha256
        or _ledger_fingerprint(row.ledger_key) != expected.ledger_sha256
    ):
        msg = "Training sources, evaluation bytes or decision ledger changed after dry run"
        raise ConflictError(msg)


def _ledger_fingerprint(key: str) -> str:
    with fresh_object(object_store(), key) as path:
        return digest(path)


def _publish_lineage(
    session: Session, plan: ActionPlan, row: TrainingRunRow, version: VersionRow
) -> None:
    report = TrainingGovernanceRun.model_validate(row.payload).report
    append_event(
        session,
        LineageEvent(
            idempotency_key=f"training-clean:{row.id}",
            operator="text.training_clean",
            inputs=[
                AssetRef(asset_id=row.dataset_id, version=row.version_id),
                *(item.asset_ref for item in plan.manifest.objects),
            ],
            outputs=[
                AssetRef(asset_type="version", asset_id=version.id, version=version.id),
                AssetRef(asset_id=row.dataset_id, version=version.id),
                AssetRef(
                    asset_type="training_decision_ledger",
                    asset_id=row.id,
                    version=report.ledger_sha256,
                ),
            ],
            on_behalf_of=plan.actor,
            source_module="storage",
            source_ref=plan.id,
            params={
                "training_run_id": row.id,
                "ledger_sha256": report.ledger_sha256,
                "rule_version": report.rule_version,
                "config": report.config.model_dump(mode="json"),
                "source_sha256": report.source_sha256,
                "evaluation_sha256": report.evaluation_sha256,
                "decision_counts": {
                    "keep": report.kept,
                    "drop": report.dropped,
                    "redact": report.redacted,
                },
                "reasons": report.issue_counts,
            },
        ),
    )


def execute_training_clean(
    session: Session, plan: ActionPlan, params: CleanTrainingParams
) -> OperationResult:
    """Reproduce signed decisions on fresh objects before publishing any clean version."""
    training_state(session, params)
    row = require_training_run(session, params.run_id)
    original = TrainingGovernanceRun.model_validate(row.payload)
    source = source_version(session, row.dataset_id, row.version_id)
    files = source_files(session, source, tuple(row.file_ids))
    evaluations = evaluation_files(session, row.dataset_id, tuple(row.evaluation_ids))
    with tempfile.TemporaryDirectory(prefix="training-clean-") as temp:
        directory = Path(temp)
        ledger = directory / "decisions.jsonl"
        output = directory / "cleaned"
        with fresh_sources(files) as inputs, fresh_sources(evaluations) as evaluation_sources:
            report = analyze_sources(
                inputs,
                original.report.config,
                evaluations=evaluation_sources,
                ledger_path=ledger,
                cleaned_dir=output,
            )
        _verify_reproduction(row, original.model_copy(update={"report": report}), ledger)
        cleaned = _cleaned_files(files, output)
        version = VersionRow(
            dataset_id=row.dataset_id,
            manifest=[
                *[item for item in source.manifest if item["id"] not in set(row.file_ids)],
                *[item.model_dump(mode="json") for item in cleaned],
            ],
        )
        session.add(version)
        session.flush()
        _save_output_report(session, row, version, cleaned, directory)
        session.add(TrainingCleanRow(run_id=row.id, version_id=version.id))
        _publish_lineage(session, plan, row, version)
    return OperationResult(
        outputs=[AssetRef(asset_type="version", asset_id=version.id, version=version.id)],
        details={
            "training_run_id": row.id,
            "version_id": version.id,
            "ledger_sha256": original.ledger_sha256,
        },
    )


def _save_output_report(
    session: Session,
    original_row: TrainingRunRow,
    version: VersionRow,
    files: tuple[FileItem, ...],
    directory: Path,
) -> None:
    original = TrainingGovernanceRun.model_validate(original_row.payload)
    evaluations = evaluation_files(
        session, original_row.dataset_id, tuple(original_row.evaluation_ids)
    )
    ledger = directory / "cleaned-ledger.jsonl"
    with fresh_sources(files) as sources, fresh_sources(evaluations) as evaluation_sources:
        report = analyze_sources(
            sources, original.report.config, evaluations=evaluation_sources, ledger_path=ledger
        )
    result = TrainingGovernanceRun(
        id=new_id(),
        dataset_id=original.dataset_id,
        version_id=version.id,
        created_at=utcnow(),
        report=report,
        ledger_sha256=report.ledger_sha256,
    )
    request = TrainingAnalysisRequest(
        version_id=version.id,
        file_ids=tuple(item.id for item in files),
        evaluation_ids=tuple(original_row.evaluation_ids),
        config=report.config,
    )
    save_training_run(session, result, request, ledger)
