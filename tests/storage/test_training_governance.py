# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise approval, fingerprints, publication, facts, quality and read-only projections."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.llm_data_models import TrainingConfig
from datakeel.core.models import JsonDocument
from datakeel.core.training_governance import (
    TrainingAnalysisRequest,
    TrainingEvaluationRequest,
    TrainingQualityQuery,
)
from datakeel.datasheets.templates import build_template
from datakeel.ontology.functions import invoke_function
from datakeel.storage.dataset_service import (
    import_paths,
    list_files,
    list_versions,
    resolve_download,
)
from datakeel.storage.datasheet_facts import extract_facts
from datakeel.storage.events import all_events
from datakeel.storage.file_state import FileStateRow
from datakeel.storage.governance_service import get_quality
from datakeel.storage.objects import object_store
from datakeel.storage.training_evaluations import list_evaluations, register_evaluation
from datakeel.storage.training_reads import read_training_quality
from datakeel.storage.training_rows import TrainingRunRow
from datakeel.storage.training_store import analyze_training, get_training_run, list_training_runs
from tests.storage.training_helpers import clean_training, seed_training

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_dry_run_approval_clean_version_preserves_originals_and_complete_lineage(
    db: Database, tmp_path: Path
) -> None:
    """Every decision survives in an immutable ledger while only approved output is published."""
    dataset, original_path, run = seed_training(db, tmp_path)
    before = original_path.read_bytes()
    assert run.report.records == 4
    assert run.report.dropped == 2
    assert run.report.redacted == 1
    assert len(list_versions(db, dataset)) == 1
    plan = prepare_action(
        db, "clean_training_data", JsonDocument({"dataset_id": dataset, "run_id": run.id})
    )
    assert plan.requires_approval
    with pytest.raises(AuthorizationError):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    approve_plan(db, plan.id, ApprovalDecision(plan_digest=plan.plan_digest, approve=True))
    completed = execute_plan(
        db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    )
    assert completed.receipt is not None
    version = completed.receipt.outputs[0].asset_id
    assert original_path.read_bytes() == before
    assert get_training_run(db, run.id).cleaned_version_id == version
    outputs = list_files(db, dataset, version)
    assert {item.filename for item in outputs} == {"training.clean.jsonl", "keep.txt"}
    cleaned = next(item for item in outputs if item.filename.endswith("jsonl"))
    content = resolve_download(db, dataset, cleaned.id, version).path.read_text()
    assert len(content.splitlines()) == 2
    assert "abc@example.test" not in content
    assert "[EMAIL]" in content
    assert list_training_runs(db, dataset, version)[0].report.dropped == 0
    with db.session() as session:
        stored = session.get(TrainingRunRow, run.id)
        assert stored is not None
        ledger = object_store().materialize(stored.ledger_key)
        decisions = [json.loads(line) for line in ledger.read_text().splitlines()]
        event = next(item for item in all_events(session) if item.operator == "text.training_clean")
    assert len(decisions) == 4
    assert {item["decision"] for item in decisions} == {"keep", "drop", "redact"}
    assert all(item["reasons"] for item in decisions)
    assert event.params["ledger_sha256"] == run.ledger_sha256
    assert any(ref.asset_type == "training_decision_ledger" for ref in event.outputs)
    assert (
        execute_plan(
            db,
            plan.id,
            ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id),
        ).id
        == completed.id
    )
    with pytest.raises(ConflictError, match="already"):
        clean_training(db, run)


def test_frozen_dry_run_rejects_changed_object_bytes(db: Database, tmp_path: Path) -> None:
    """Approval cannot publish new bytes or a different per-record decision sequence."""
    dataset, _, run = seed_training(db, tmp_path)
    plan = prepare_action(
        db, "clean_training_data", JsonDocument({"dataset_id": dataset, "run_id": run.id})
    )
    approve_plan(db, plan.id, ApprovalDecision(plan_digest=plan.plan_digest, approve=True))
    file = next(item for item in list_files(db, dataset) if item.filename.endswith("jsonl"))
    key = file.metadata["object_key"]
    assert isinstance(key, str)
    object_store().materialize(key).write_text('{"instruction":"Different","output":"Changed"}')
    with pytest.raises(ConflictError, match="changed"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert len(list_versions(db, dataset)) == 1


def test_frozen_dry_run_rejects_changed_decision_ledger(db: Database, tmp_path: Path) -> None:
    """The full historical decision asset must still match the ledger reviewed for approval."""
    dataset, _, run = seed_training(db, tmp_path)
    plan = prepare_action(
        db, "clean_training_data", JsonDocument({"dataset_id": dataset, "run_id": run.id})
    )
    approve_plan(db, plan.id, ApprovalDecision(plan_digest=plan.plan_digest, approve=True))
    with db.session() as session:
        stored = session.get(TrainingRunRow, run.id)
        assert stored is not None
        object_store().materialize(stored.ledger_key).write_text("changed-decisions\n")
    message = ""
    try:
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    except ConflictError as error:
        message = str(error)
    assert "ledger changed" in message
    assert len(list_versions(db, dataset)) == 1


def test_saved_training_reports_cannot_be_edited_or_deleted(db: Database, tmp_path: Path) -> None:
    """Version facts and signed previews stay immutable even through direct SQL."""
    _, _, run = seed_training(db, tmp_path)
    for statement in (
        update(TrainingRunRow).where(TrainingRunRow.id == run.id).values(file_ids=[]),
        delete(TrainingRunRow).where(TrainingRunRow.id == run.id),
    ):
        with db.session() as session, pytest.raises(DBAPIError, match="immutable"):
            session.execute(statement)


def test_cleaning_freezes_state_of_unselected_hidden_preserved_files(
    db: Database, tmp_path: Path
) -> None:
    """A hidden source file's revision cannot change behind an already signed clean plan."""
    dataset, _, run = seed_training(db, tmp_path)
    untouched = next(item for item in list_files(db, dataset) if item.filename == "keep.txt")
    with db.session() as session:
        session.add(FileStateRow(dataset_id=dataset, file_id=untouched.id, deleted=True))
        session.commit()
    plan = prepare_action(
        db, "clean_training_data", JsonDocument({"dataset_id": dataset, "run_id": run.id})
    )
    approve_plan(db, plan.id, ApprovalDecision(plan_digest=plan.plan_digest, approve=True))
    with db.session() as session:
        state = session.get(FileStateRow, (dataset, untouched.id))
        assert state is not None
        state.revision += 1
        session.commit()
    with pytest.raises(ConflictError, match="target state changed"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert len(list_versions(db, dataset)) == 1


def test_report_facts_and_quality_share_exact_version_pinned_measurements(
    db: Database, tmp_path: Path
) -> None:
    """Old source findings remain factual after cleaning, and all new facts validate citations."""
    dataset, _, run = seed_training(db, tmp_path)
    dirty_quality = get_quality(db, dataset)
    with db.session() as session:
        facts = extract_facts(session, dataset, run.version_id)
    measured = {fact.field: fact for fact in facts if fact.field.startswith("training.")}
    assert measured["training.pii_records"].value == 1
    assert measured["training.deduplication_rate"].value == 0.25
    assert measured["training.format_error_rate"].value == 0.25
    assert measured["training.contamination_rate"].value == 0
    assert measured["training.language_distribution"].value == run.report.languages
    assert measured["training.pii_records"].kind == "count"
    assert measured["training.deduplication_rate"].kind == "ratio"
    for language in ("en", "zh"):
        document = build_template(tuple(measured.values()), language)
        assert not document.dropped_sentences
    clean_version = clean_training(db, run)
    assert get_quality(db, dataset).total > dirty_quality.total
    with db.session() as session:
        old = extract_facts(session, dataset, run.version_id)
        cleaned = {fact.field: fact for fact in extract_facts(session, dataset, clean_version)}
    assert tuple(fact for fact in old if fact.field.startswith("training.")) == tuple(
        measured.values()
    )
    assert cleaned["training.pii_records"].value == 0


def test_evaluations_are_uploaded_version_references_and_frozen_by_dry_run(
    db: Database, tmp_path: Path
) -> None:
    """Registered generated evaluation text contributes contamination without joining training."""
    dataset, _, _ = seed_training(db, tmp_path)
    path = tmp_path / "evaluation.txt"
    path.write_text("Rainforests host diverse wildlife.")
    evaluation_dataset = import_paths(db, "Generated evaluation", [path])
    evaluation_file = list_files(db, evaluation_dataset.id)[0]
    registered = register_evaluation(
        db,
        dataset,
        TrainingEvaluationRequest(
            name="Generated evaluation",
            source_dataset_id=evaluation_dataset.id,
            file_ids=(evaluation_file.id,),
        ),
    )
    assert list_evaluations(db, dataset) == (registered,)
    run = analyze_training(
        db,
        dataset,
        TrainingAnalysisRequest(
            evaluation_ids=(registered.id,), config=TrainingConfig(contamination_ngram=2)
        ),
    )
    assert run.report.issue_counts["contamination"] == 2
    assert evaluation_file.id in run.report.evaluation_sha256
    assert evaluation_file.id not in run.report.source_sha256
    cleaned_version = clean_training(db, run)
    cleaned = list_training_runs(db, dataset, cleaned_version)[0]
    assert cleaned.report.config == run.report.config
    assert cleaned.report.evaluation_sha256 == run.report.evaluation_sha256
    assert cleaned.report.issue_counts.get("contamination", 0) == 0
    with db.session() as session:
        clean_report = session.get(TrainingRunRow, cleaned.id)
        assert clean_report is not None
        assert clean_report.evaluation_ids == [registered.id]
        event = next(item for item in all_events(session) if item.operator == "text.training_clean")
    assert any(ref.asset_id == evaluation_file.id for ref in event.inputs)
    with pytest.raises(NotFoundError):
        analyze_training(db, dataset, TrainingAnalysisRequest(evaluation_ids=("missing",)))


def test_read_only_tool_computes_real_findings_without_persisting_a_run(
    db: Database, tmp_path: Path
) -> None:
    """Agent reads work before a scan and never silently write a version or action."""
    path = tmp_path / "new.jsonl"
    path.write_text('invalid-json\n{"instruction":"Hi","output":"Hello"}\n')
    dataset = import_paths(db, "Read only fixture", [path])
    query = TrainingQualityQuery(dataset_id=dataset.id)
    report = read_training_quality(db, query)
    result = invoke_function(db, "get_training_quality", JsonDocument(query.model_dump()))
    assert report.issue_counts["format_error"] == 1
    assert result.data == report.model_dump(mode="json")
    assert result.asset_refs[0].asset_id == dataset.id
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(TrainingRunRow)) == 0


def test_quality_overlay_excludes_deleted_files_from_record_penalties(
    db: Database, tmp_path: Path
) -> None:
    """Stored whole-scan counts are projected per file after the current visibility overlay."""
    bad, healthy = tmp_path / "bad.jsonl", tmp_path / "healthy.jsonl"
    bad.write_text("invalid-json\n")
    healthy.write_text(
        '{"instruction":"Describe winter snow",'
        '"output":"Snow forms from frozen water crystals high in clouds."}\n'
    )
    dataset = import_paths(db, "Visibility fixture", [bad, healthy])
    run = analyze_training(db, dataset.id, TrainingAnalysisRequest())
    assert get_quality(db, dataset.id).dimensions["completeness"].score == 50
    hidden = next(item for item in run.report.files if item.filename == "bad.jsonl")
    with db.session() as session:
        session.add(FileStateRow(dataset_id=dataset.id, file_id=hidden.file_id, deleted=True))
        session.commit()
    quality = get_quality(db, dataset.id)
    assert quality.file_count == 1
    assert quality.dimensions["completeness"].score == 100
    assert quality.dimensions["completeness"].details["training_records"] == 1
    with pytest.raises(ValidationError, match="Deleted"):
        read_training_quality(db, TrainingQualityQuery(dataset_id=dataset.id))


def test_source_ownership_type_and_state_are_validated(db: Database, tmp_path: Path) -> None:
    """Selections reject another version, unknown files, non-JSONL and unavailable file state."""
    dataset, _, run = seed_training(db, tmp_path)
    other = import_paths(db, "Other", [])
    for request in (
        TrainingAnalysisRequest(file_ids=("missing",)),
        TrainingAnalysisRequest(version_id=list_versions(db, other.id)[0].id),
    ):
        with pytest.raises(NotFoundError):
            analyze_training(db, dataset, request)
    text = next(item for item in list_files(db, dataset) if item.filename == "keep.txt")
    with pytest.raises(ValidationError, match="JSONL"):
        analyze_training(db, dataset, TrainingAnalysisRequest(file_ids=(text.id,)))
    with pytest.raises(ValidationError, match="at least"):
        analyze_training(db, other.id, TrainingAnalysisRequest())
    with pytest.raises(ValidationError, match="no training"):
        read_training_quality(db, TrainingQualityQuery(dataset_id=other.id))
    with pytest.raises(NotFoundError):
        get_training_run(db, "missing")
    with pytest.raises(ConflictError, match="belong"):
        prepare_action(
            db, "clean_training_data", JsonDocument({"dataset_id": other.id, "run_id": run.id})
        )
    source = run.report.files[0]
    with db.session() as session:
        session.add(FileStateRow(dataset_id=dataset, file_id=source.file_id, quarantined=True))
        session.commit()
    with pytest.raises(ValidationError, match="quarantined"):
        analyze_training(db, dataset, TrainingAnalysisRequest())
