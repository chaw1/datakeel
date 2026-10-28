# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run offline dry scans and persist immutable, version-pinned training reports."""

import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.llm_data_models import TrainingReport
from datakeel.core.models import FileItem, new_id, utcnow
from datakeel.core.training_governance import TrainingAnalysisRequest, TrainingGovernanceRun
from datakeel.llm_data import analyze_sources
from datakeel.storage.database import Database
from datakeel.storage.objects import digest, object_store
from datakeel.storage.training_access import authorize_training, training_refs
from datakeel.storage.training_evaluations import evaluation_files
from datakeel.storage.training_rows import TrainingCleanRow, TrainingRunRow
from datakeel.storage.training_sources import fresh_sources, source_files, source_version
from datakeel.storage.views import DownloadView


def require_training_run(session: Session, identifier: str) -> TrainingRunRow:
    """Read one persisted dry run without crossing the storage boundary with a row."""
    row = session.get(TrainingRunRow, identifier)
    if row is None:
        msg = "Training governance report not found"
        raise NotFoundError(msg)
    return row


def run_view(
    session: Session, row: TrainingRunRow, access: AccessContext | None = None
) -> TrainingGovernanceRun:
    """Overlay the separate approval result without modifying the frozen report."""
    authorize_training(
        session,
        training_refs(row.dataset_id, row.version_id, tuple(row.file_ids)),
        tuple(row.evaluation_ids),
        access,
    )
    result = TrainingGovernanceRun.model_validate(row.payload)
    cleaned = session.get(TrainingCleanRow, row.id)
    return result.model_copy(update={"cleaned_version_id": cleaned.version_id if cleaned else None})


def save_training_run(
    session: Session,
    result: TrainingGovernanceRun,
    request: TrainingAnalysisRequest,
    ledger: Path,
) -> None:
    """Persist the complete redacted decision ledger as a content-addressed audit asset."""
    checksum = digest(ledger)
    if checksum != result.report.ledger_sha256:
        msg = "Training decision ledger fingerprint does not match the report"
        raise ValidationError(msg)
    key = f"training-ledgers/{checksum}.jsonl"
    object_store().put(ledger, key)
    session.add(
        TrainingRunRow(
            id=result.id,
            dataset_id=result.dataset_id,
            version_id=result.version_id,
            created_at=result.created_at.timestamp(),
            payload=result.model_dump(mode="json"),
            file_ids=list(request.file_ids),
            evaluation_ids=list(request.evaluation_ids),
            ledger_key=key,
        )
    )


def analyze_training(
    db: Database,
    dataset_id: str,
    request: TrainingAnalysisRequest,
    *,
    access: AccessContext | None = None,
) -> TrainingGovernanceRun:
    """Produce a dry-run report without creating a version or changing any source bytes."""
    with db.session() as session, tempfile.TemporaryDirectory(prefix="training-scan-") as temp:
        version = source_version(session, dataset_id, request.version_id)
        evaluations = evaluation_files(session, dataset_id, request.evaluation_ids)
        excluded = {item.id for item in evaluations}
        files = tuple(
            item
            for item in source_files(session, version, request.file_ids)
            if item.id not in excluded
        )
        if not files:
            msg = "Select at least one uploaded training JSONL file"
            raise ValidationError(msg)
        authorize_training(
            session,
            training_refs(dataset_id, version.id, tuple(item.id for item in files)),
            request.evaluation_ids,
            access,
        )
        ledger = Path(temp) / "decisions.jsonl"
        with fresh_sources(files) as sources, fresh_sources(evaluations) as evaluation_sources:
            report = analyze_sources(
                sources, request.config, evaluations=evaluation_sources, ledger_path=ledger
            )
        result = TrainingGovernanceRun(
            id=new_id(),
            dataset_id=dataset_id,
            version_id=version.id,
            created_at=utcnow(),
            report=report,
            ledger_sha256=report.ledger_sha256,
        )
        frozen = request.model_copy(
            update={"version_id": version.id, "file_ids": tuple(item.id for item in files)}
        )
        save_training_run(session, result, frozen, ledger)
        session.commit()
        return result


def list_training_runs(
    db: Database,
    dataset_id: str,
    version_id: str | None = None,
    *,
    access: AccessContext | None = None,
) -> tuple[TrainingGovernanceRun, ...]:
    """Read bounded analysis history for the selected version, latest first."""
    with db.session() as session:
        version = source_version(session, dataset_id, version_id)
        authorize_training(session, training_refs(dataset_id, version.id, ()), access=access)
        result = tuple(
            run_view(session, row, access)
            for row in session.scalars(
                select(TrainingRunRow)
                .where(
                    TrainingRunRow.dataset_id == dataset_id,
                    TrainingRunRow.version_id == version.id,
                )
                .order_by(TrainingRunRow.created_at.desc(), TrainingRunRow.id)
                .limit(20)
            )
        )
        session.commit()
        return result


def get_training_run(
    db: Database, run_id: str, *, access: AccessContext | None = None
) -> TrainingGovernanceRun:
    """Return one frozen report and its current clean-version publication reference."""
    with db.session() as session:
        row = require_training_run(session, run_id)
        result = run_view(session, row, access)
        session.commit()
        return result


def resolve_training_ledger(
    db: Database, run_id: str, *, access: AccessContext | None = None
) -> DownloadView:
    """Resolve an authorized, hash-verified ledger without exposing its private object key."""
    result = get_training_run(db, run_id, access=access)
    with db.session() as session:
        row = require_training_run(session, run_id)
        path = object_store().materialize(row.ledger_key)
        if digest(path) != result.ledger_sha256:
            msg = "Training decision ledger changed from the immutable report"
            raise ConflictError(msg)
        return DownloadView(path=path, filename=f"training-decisions-{run_id}.jsonl")


def training_overlay(
    session: Session, dataset_id: str, version_id: str, files: list[FileItem]
) -> list[FileItem]:
    """Project pinned per-file counts so hidden files cannot affect the visible quality score."""
    row = session.scalar(
        select(TrainingRunRow)
        .where(TrainingRunRow.dataset_id == dataset_id, TrainingRunRow.version_id == version_id)
        .order_by(TrainingRunRow.created_at.desc(), TrainingRunRow.id)
        .limit(1)
    )
    if row is None or not files:
        return files
    report = TrainingGovernanceRun.model_validate(row.payload).report
    summaries = {summary.file_id: summary for summary in report.files}
    result: list[FileItem] = []
    for item in files:
        metadata = dict(item.metadata)
        summary = summaries.get(item.id)
        if summary is not None:
            metadata["training_quality"] = TrainingReport(
                config=report.config,
                records=summary.records,
                valid_records=summary.valid_records,
                issue_counts=summary.issue_counts,
            ).model_dump(mode="json")
        result.append(item.model_copy(update={"metadata": metadata}))
    return result


def version_training_report(
    session: Session, dataset_id: str, version_id: str
) -> tuple[TrainingReport, TrainingRunRow] | None:
    """Resolve the exact fact snapshot reused by scoring and datasheet generation."""
    row = session.scalar(
        select(TrainingRunRow)
        .where(TrainingRunRow.dataset_id == dataset_id, TrainingRunRow.version_id == version_id)
        .order_by(TrainingRunRow.created_at.desc(), TrainingRunRow.id)
        .limit(1)
    )
    return (TrainingGovernanceRun.model_validate(row.payload).report, row) if row else None
