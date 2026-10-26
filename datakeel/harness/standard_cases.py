# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seed approved synthetic standards through production actions for demos and goldens."""

from pathlib import Path

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.catalog.service import prepare_import
from datakeel.core.catalog_identity import catalog_id
from datakeel.core.catalog_models import (
    CatalogImportRequest,
    CatalogLink,
    CatalogObject,
    CatalogQuery,
    CatalogSnapshot,
)
from datakeel.core.errors import ExecutionError
from datakeel.core.harness_eval import CaseFixture
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.standard_history_models import StandardsReport
from datakeel.core.standard_models import StandardsContract
from datakeel.harness.resources import contract_path
from datakeel.sample_standards import DEMO_MAPPINGS, generate_standards_source
from datakeel.standards.loader import load_contract
from datakeel.storage.catalog_queries import read_objects
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_files
from datakeel.storage.standard_queries import standards_report
from datakeel.storage.standard_store import get_contract, list_mappings

DEMO_SOURCE = "standards_demo"


def _approved(db: Database, action: str, params: JsonDocument) -> None:
    plan = prepare_action(db, action, params)
    if plan.requires_approval:
        approve_plan(
            db,
            plan.id,
            ApprovalDecision(
                approve=True, plan_digest=plan.plan_digest, reason="Explicit synthetic demo setup"
            ),
        )
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    if run.status != "SUCCEEDED":
        raise ExecutionError(run.error or "Synthetic standards setup failed")


def _annotate(db: Database, snapshot: CatalogSnapshot) -> None:
    objects: list[CatalogObject] = []
    owner = AssetRef(asset_type="owner", asset_id="owner:standards-demo")
    links = list(snapshot.links)
    for item in snapshot.objects:
        annotated = item
        if item.asset_ref.asset_type == "column" and item.name == "revenue":
            unit = "USD" if item.table_id and "dirty_customers" in item.table_id else "CNY"
            annotated = item.model_copy(
                update={"properties": JsonDocument(item.properties.root | {"unit": unit})}
            )
        objects.append(annotated)
        if item.asset_ref.asset_type == "table":
            links.append(CatalogLink(source=item.asset_ref, target=owner, kind="owned_by"))
    objects.append(CatalogObject(asset_ref=owner, name="Demo steward"))
    publish_snapshot(
        db, snapshot.model_copy(update={"objects": tuple(objects), "links": tuple(links)})
    )


def _install_contract(db: Database) -> None:
    example = load_contract(contract_path("standards") / "enterprise.yaml")
    existing = get_contract(db)
    known = {item.code for item in existing.standards}
    lists = {item.code: item for item in example.code_lists}
    lists.update({item.code: item for item in existing.code_lists})
    missing = tuple(item for item in example.standards if item.code not in known)
    if missing:
        contract = StandardsContract(standards=missing, code_lists=tuple(lists.values()))
        _approved(
            db, "import_standards", JsonDocument({"contract": contract.model_dump(mode="json")})
        )


def seed_standard_demo(db: Database, directory: Path) -> StandardsReport:
    """Resume generated setup and approve missing fixtures while preserving human changes."""
    path = generate_standards_source(directory)
    sources = read_objects(db, CatalogQuery(kind="source", source_id=DEMO_SOURCE, limit=1))
    if not any(item.asset_ref.asset_id == DEMO_SOURCE for item in sources.items):
        snapshot, _ = prepare_import(
            CatalogImportRequest(
                source_id=DEMO_SOURCE,
                name="Generated standards comparison",
                connection_url=f"sqlite:///{path}",
            ),
        )
        _annotate(db, snapshot)
    _install_contract(db)
    confirmed = {item.column_id for item in list_mappings(db)}
    for table in ("clean_customers", "dirty_customers"):
        for column, standard in DEMO_MAPPINGS.items():
            column_id = catalog_id(DEMO_SOURCE, "main", table, column)
            if column_id not in confirmed:
                _approved(
                    db,
                    "confirm_standard_mapping",
                    JsonDocument(
                        {
                            "mapping": {
                                "column_id": column_id,
                                "standard_code": standard,
                            }
                        }
                    ),
                )
    return standards_report(db)


def seed_standard_case(db: Database, directory: Path) -> CaseFixture:
    """Pair checked customer tables with a normal dataset for the existing conversation harness."""
    seed_standard_demo(db, directory / "standards")
    document = directory / "standards.txt"
    document.write_text("Generated standards benchmark; local fixture only.", encoding="utf-8")
    dataset = import_paths(db, "Generated standards golden", [document])
    return CaseFixture(dataset_id=dataset.id, file_id=list_files(db, dataset.id)[0].id)
