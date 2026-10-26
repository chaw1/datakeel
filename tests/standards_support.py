# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated local source and explicit human decisions shared by standards integration tests."""

import sqlite3
from pathlib import Path

from datakeel.actions.models import ActionRun, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest
from datakeel.core.models import JsonDocument
from datakeel.core.standard_models import CodeEntry, CodeList, FieldStandard, StandardsContract
from datakeel.storage.database import Database


def standard_contract() -> StandardsContract:
    """Define four business fields and one reference list using only generated values."""
    return StandardsContract(
        standards=(
            FieldStandard(
                code="customer_id",
                name_zh="客户编号",
                name_en="Customer ID",
                description="Stable customer identity",
                data_type="string",
                length=8,
                pattern=r"^C\d{3}$",
                required=True,
                status="active",
                aliases=("cust_id",),
            ),
            FieldStandard(
                code="email",
                name_zh="邮箱",
                name_en="Email",
                description="Customer mailbox",
                data_type="string",
                sensitivity="confidential",
                pattern=r"^[^@]+@[^@]+\.[^@]+$",
                status="active",
            ),
            FieldStandard(
                code="status",
                name_zh="客户状态",
                name_en="Customer status",
                description="Lifecycle state",
                data_type="string",
                code_list="states",
                status="active",
            ),
            FieldStandard(
                code="amount",
                name_zh="金额",
                name_en="Amount",
                description="Order amount",
                data_type="decimal",
                minimum=0,
                maximum=100,
                precision=6,
                scale=2,
                status="active",
            ),
        ),
        code_lists=(
            CodeList(
                code="states",
                name="States",
                status="active",
                entries=(CodeEntry(value="A", label_zh="有效", label_en="Active"),),
            ),
        ),
    )


def approved_change(db: Database, action: str, params: JsonDocument) -> ActionRun:
    """Model an explicit local user's review of the exact immutable plan."""
    plan = prepare_action(db, action, params)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    return execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def install_standards(db: Database, directory: Path) -> StandardsContract:
    """Create an isolated SQLite source and approve only its independent standard definitions."""
    source = directory / "standard-source.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute(
            "CREATE TABLE customers(cust_id VARCHAR(8), email TEXT, status TEXT, "
            "amount NUMERIC(6,2), opaque_payload TEXT)"
        )
        connection.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?)",
            (
                ("C001", "safe@example.org", "A", 10, "first"),
                (None, "personal@example.org", "X", 101, "second"),
                ("TOOLONG-ID", "invalid", "A", -1, "third"),
            ),
        )
    import_catalog(
        db,
        CatalogImportRequest(
            source_id="generated",
            name="Generated",
            connection_url=f"sqlite:///{source}",
        ),
    )
    contract = standard_contract()
    approved_change(
        db, "import_standards", JsonDocument({"contract": contract.model_dump(mode="json")})
    )
    return contract
