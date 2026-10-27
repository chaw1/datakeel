# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate quality tool fixtures through approved actions and actual worker scans."""

import sqlite3
from pathlib import Path

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest
from datakeel.core.dq_models import DqRule, DqTarget
from datakeel.core.errors import ExecutionError
from datakeel.core.harness_eval import CaseFixture
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_files
from datakeel.storage.dq_reads import read_results
from datakeel.worker.runner import run_worker

_HISTORY_POINTS = 2


def seed_quality_case(db: Database, directory: Path) -> CaseFixture:
    """Seed a failing order amount rule and a passing required-value rule with two runs each."""
    business = directory / "quality-golden.sqlite"
    with sqlite3.connect(business) as connection:
        connection.execute("CREATE TABLE orders(order_id INTEGER, amount NUMERIC)")
        connection.executemany("INSERT INTO orders VALUES (?, ?)", [(1, 10), (2, -5)])
    import_catalog(
        db,
        CatalogImportRequest(
            source_id="quality-demo",
            name="Generated quality source",
            connection_url=f"sqlite:///{business}",
        ),
    )
    note = directory / "quality-note.txt"
    note.write_text("Generated order quality observations.", encoding="utf-8")
    dataset = import_paths(db, "Generated quality golden fixture", [note])
    for identity, column, kind, params in (
        ("orders-amount", "amount", "range", {"minimum": 0}),
        ("orders-id", "order_id", "not_null", {}),
    ):
        rule = DqRule.model_validate(
            {
                "id": identity,
                "name": identity,
                "kind": kind,
                "params": params,
                "target": DqTarget(source_id="quality-demo", table="orders", column=column),
                "dataset_id": dataset.id,
                "owner": "quality-team",
            }
        )
        _controlled(db, "create_quality_rule", JsonDocument({"rule": rule.model_dump(mode="json")}))
        for _ in range(_HISTORY_POINTS):
            _controlled(db, "run_quality_rule", JsonDocument({"rule_id": rule.id}))
            run_worker(db, once=True)
        if len(read_results(db, rule.id)) != _HISTORY_POINTS:
            msg = "Generated quality fixture did not publish two actual worker results"
            raise ExecutionError(msg)
    return CaseFixture(dataset_id=dataset.id, file_id=list_files(db, dataset.id)[0].id)


def _controlled(db: Database, name: str, params: JsonDocument) -> None:
    plan = prepare_action(db, name, params)
    if plan.requires_approval:
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    if run.status not in {"SUCCEEDED", "QUEUED"}:
        msg = "Generated quality fixture action failed"
        raise ExecutionError(msg)
