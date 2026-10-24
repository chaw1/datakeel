# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prepare the exact enterprise recordings through the production offline worker."""

from pathlib import Path

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import ExecutionError
from datakeel.core.harness_eval import CaseFixture
from datakeel.core.kg_eval_models import KGCaseSuite
from datakeel.core.models import JsonDocument
from datakeel.harness.enterprise_cases import seed_enterprise_case
from datakeel.kg.loader import contracts_path, load_contract
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_datasets
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.kg_store import list_runs
from datakeel.worker.runner import run_worker

ENTERPRISE_DOCUMENTS = "企业文档 · Enterprise documents"


def enterprise_document_path() -> Path:
    """Resolve the verbatim documents in both source checkouts and installed wheels."""
    return contracts_path() / "../../docs/p9/enterprise-docs.yaml"


def import_enterprise_documents(db: Database, directory: Path) -> CaseFixture:
    """Import six fictional passages without adding newlines or evaluation labels."""
    dataset = next((item for item in list_datasets(db) if item.name == ENTERPRISE_DOCUMENTS), None)
    if dataset is None:
        suite = load_contract(enterprise_document_path(), KGCaseSuite)
        directory.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for case in suite.cases:
            path = directory / f"{case.id}.txt"
            path.write_text(case.text, encoding="utf-8")
            paths.append(path)
        dataset = import_paths(
            db,
            ENTERPRISE_DOCUMENTS,
            paths,
            {"description": "Six synthetic enterprise documents; offline recorded extraction."},
        )
    version, files = source_manifest(db, dataset.id)
    return CaseFixture(dataset_id=dataset.id, version_id=version, file_id=files[0].id)


def schedule_enterprise_extraction(db: Database, fixture: CaseFixture) -> str:
    """Schedule a replay action with no provider configuration or credential access."""
    plan = prepare_action(
        db,
        "run_kg_extraction",
        JsonDocument(
            root={
                "dataset_id": fixture.dataset_id,
                "version_id": fixture.version_id,
                "profile_id": "replay-enterprise",
            }
        ),
    )
    if plan.requires_approval:
        msg = "Enterprise recording must remain offline"
        raise ExecutionError(msg)
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    if run.task_id is None:
        msg = f"Enterprise extraction could not be scheduled: {run.status}"
        raise ExecutionError(msg)
    return run.task_id


def check_enterprise_extraction(db: Database, fixture: CaseFixture, task_id: str) -> None:
    """Fail visibly if the six-document production replay did not complete."""
    run = next(
        (
            item
            for item in list_runs(db, fixture.dataset_id, fixture.version_id)
            if item.task_id == task_id
        ),
        None,
    )
    if run is None or run.status != "completed" or run.report.failed:
        msg = "Enterprise graph extraction did not complete"
        raise ExecutionError(msg)


def extract_enterprise_documents(db: Database, fixture: CaseFixture) -> None:
    """Drain the queued replay and require complete publication before querying."""
    task_id = schedule_enterprise_extraction(db, fixture)
    run_worker(db, once=True)
    check_enterprise_extraction(db, fixture, task_id)


def seed_enterprise_kg(db: Database, directory: Path) -> CaseFixture:
    """Combine generated catalogs and semantics with the actual recorded enterprise graph."""
    seed_enterprise_case(db, directory)
    fixture = import_enterprise_documents(db, directory / "documents")
    extract_enterprise_documents(db, fixture)
    return fixture
