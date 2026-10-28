# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate isolated business data and exercise approved quality actions."""

import sqlite3
from pathlib import Path

from datakeel.actions.models import ActionRun, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest
from datakeel.core.dq_models import DqParameters, DqRule, DqTarget
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database


def generated_rule(db: Database, directory: Path) -> DqRule:
    """Register a generated SQLite source with a deliberately negative order amount."""
    source = directory / "orders.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE orders(id INTEGER, amount REAL)")
        connection.executemany("INSERT INTO orders VALUES (?, ?)", [(1, 20), (2, -5)])
    import_catalog(
        db,
        CatalogImportRequest(
            source_id="orders-test", name="Generated orders", connection_url=f"sqlite:///{source}"
        ),
    )
    return DqRule(
        id="orders-positive",
        name="Order amount must be nonnegative",
        owner="Operations",
        target=DqTarget(
            source_id="orders-test", schema_name="main", table="orders", column="amount"
        ),
        kind="range",
        params=DqParameters(minimum=0),
    )


def execute_action(db: Database, name: str, params: JsonDocument) -> ActionRun:
    """Review and execute a complete plan with the real approval boundary when required."""
    plan = prepare_action(db, name, params)
    if plan.requires_approval:
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    return execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def save_rule(db: Database, rule: DqRule) -> ActionRun:
    """Create a rule through its approved controlled action."""
    return execute_action(
        db, "create_quality_rule", JsonDocument({"rule": rule.model_dump(mode="json")})
    )
