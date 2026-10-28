# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Authorized source registration reaches real rule execution on both database stacks."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateSchema, DropSchema

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.catalog.importers import database as importer
from datakeel.catalog.service import prepare_import
from datakeel.core.catalog_models import CatalogImportRequest, SourceProperties
from datakeel.core.dq_models import DqParameters, DqRule, DqTarget
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.quality.dq_engine import execute_rule
from datakeel.storage.catalog_queries import get_object
from datakeel.storage.dq_reads import read_results
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from sqlalchemy.engine import Connection
    from sqlalchemy.engine.reflection import Inspector

    from datakeel.storage.database import Database


@pytest.fixture
def registered_business_request(db: Database, tmp_path: Path) -> Iterator[CatalogImportRequest]:
    """Own a generated business schema separate from every existing fact-store table."""
    schema = "main" if db.sqlite else "dq_business_" + uuid4().hex
    engine = create_engine(f"sqlite:///{tmp_path / 'business.sqlite'}") if db.sqlite else db.engine
    with engine.begin() as connection:
        if not db.sqlite:
            connection.execute(CreateSchema(schema))
            connection.execute(
                text("SELECT set_config('search_path', :schema, true)"), {"schema": schema}
            )
        connection.execute(text("CREATE TABLE dq_customers(id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE dq_orders(id INTEGER PRIMARY KEY, "
                "customer_id INTEGER REFERENCES dq_customers(id), amount NUMERIC)"
            )
        )
        connection.execute(text("INSERT INTO dq_customers VALUES (1)"))
        connection.execute(text("INSERT INTO dq_orders VALUES (1, 1, 10), (2, 1, -7)"))
        connection.execute(text("CREATE VIEW dq_order_view AS SELECT id, amount FROM dq_orders"))
    try:
        yield CatalogImportRequest(
            source_id="native-business",
            name="Generated native business source",
            connection_url=engine.url.render_as_string(hide_password=False),
            schemas=(schema,),
        )
    finally:
        if db.sqlite:
            engine.dispose()
        else:
            with engine.begin() as connection:
                # Only this fixture's newly generated UUID schema is removed.
                connection.execute(DropSchema(schema, cascade=True))


def _populate_via_action(db: Database, request: CatalogImportRequest) -> None:
    plan = prepare_action(
        db, "import_catalog", JsonDocument({"request": request.model_dump(mode="json")})
    )
    result = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert result.status == "SUCCEEDED"


def test_registered_business_source_reaches_controlled_rule_worker(
    db: Database,
    registered_business_request: CatalogImportRequest,
) -> None:
    """A native source is imported, approved and checked through the ordinary product path."""
    _, report = prepare_import(registered_business_request)
    assert report.failed_sql_count == 0
    _populate_via_action(db, registered_business_request)
    source = SourceProperties.model_validate(get_object(db, "native-business").properties.root)
    rule = DqRule(
        id="native-business-rule",
        name="Order amount is nonnegative",
        owner="quality-team",
        target=DqTarget(
            source_id="native-business",
            table="dq_orders",
            column="amount",
            schema_name=registered_business_request.schemas[0],
        ),
        kind="range",
        params=DqParameters(minimum=0),
    )
    plan = prepare_action(
        db, "create_quality_rule", JsonDocument({"rule": rule.model_dump(mode="json")})
    )
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    assert (
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest)).status
        == "SUCCEEDED"
    )
    run_plan = prepare_action(db, "run_quality_rule", JsonDocument({"rule_id": rule.id}))
    execute_plan(db, run_plan.id, ExecuteRequest(plan_digest=run_plan.plan_digest))
    run_worker(db, once=True)
    result = read_results(db, rule.id)[0]
    assert result.status == "failed"
    assert result.failed_count == 1
    reference = rule.model_copy(
        update={
            "kind": "referential_integrity",
            "target": rule.target.model_copy(update={"column": "customer_id"}),
            "params": DqParameters(reference_table="dq_customers", reference_column="id"),
        }
    )
    assert execute_rule(reference, source).passed is True


def test_native_reflection_uses_database_enforced_read_only_transaction(
    registered_business_request: CatalogImportRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first inspector operation observes real database-enforced read-only protection."""
    original = importer.inspect
    checked: list[bool] = []

    def protected_inspect(connection: Connection) -> Inspector:
        if connection.dialect.name == "postgresql":
            assert connection.execute(text("SHOW transaction_read_only")).scalar_one() == "on"
        else:
            with pytest.raises(SQLAlchemyError):
                connection.execute(text("CREATE TABLE unexpected_write(value INTEGER)"))
        checked.append(True)
        return original(connection)

    monkeypatch.setattr(importer, "inspect", protected_inspect)
    batch = importer.reflect_database(registered_business_request)
    assert checked == [True]
    assert any(item.name == "dq_orders" for item in batch.snapshot.objects)
    assert any(item.name == "dq_order_view" for item in batch.snapshot.objects)


def test_system_schema_is_rejected_without_reflecting_business_metadata(
    registered_business_request: CatalogImportRequest,
) -> None:
    """System schemas cannot become a quality business-source inventory."""
    with pytest.raises(ValidationError, match="System schemas"):
        importer.reflect_database(
            registered_business_request.model_copy(update={"schemas": ("pg_catalog",)})
        )
