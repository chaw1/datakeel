# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate paired clean and deliberately nonconforming fictional customer tables."""

import sqlite3
from contextlib import closing
from pathlib import Path

from datakeel.sample_enterprise.crm import build_crm

DEMO_MAPPINGS = {
    "customer_id": "customer_id",
    "customer_name": "customer_name",
    "customer_email": "customer_email",
    "customer_status": "customer_status",
    "customer_age": "customer_age",
    "revenue": "revenue",
    "customer_name_number": "customer_name",
    "public_note": "record_name",
}
DEMO_VIOLATIONS = {
    "customer_name": {"length": 1, "required": 1},
    "customer_email": {"pattern": 1},
    "customer_status": {"code_list": 1},
    "customer_age": {"range": 1},
    "revenue": {"precision": 1, "unit": 3},
    "customer_name_number": {"type": 3},
    "public_note": {"sensitivity": 3},
}


def generate_standards_source(directory: Path) -> Path:
    """Reuse generated enterprise customers and isolate every deliberate failure category."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "standards.sqlite"
    if path.exists():
        return path
    customers = next(item for item in build_crm().tables if item.name == "customers").rows[:3]
    with closing(sqlite3.connect(path)) as connection, connection:
        for table in ("clean_customers", "dirty_customers"):
            shape = "INTEGER" if table == "dirty_customers" else "TEXT"
            connection.execute(
                f'CREATE TABLE "{table}" ('  # Fixed authored table identifiers.
                "customer_id INTEGER, customer_name TEXT, customer_email TEXT, "
                "customer_status TEXT, customer_age INTEGER, revenue NUMERIC, "
                f"customer_name_number {shape}, public_note TEXT, opaque_blob TEXT)"
            )
            for index, customer in enumerate(customers):
                dirty = table == "dirty_customers"
                name = None if index == 0 else "X" * 81 if index == 1 else customer[1]
                connection.execute(
                    f'INSERT INTO "{table}" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',  # noqa: S608
                    (
                        customer[0],
                        name if dirty else customer[1],
                        "invalid" if dirty and index == 1 else f"customer{index}@example.org",
                        "retired" if dirty and index == 1 else "active",
                        151 if dirty and index == 1 else 25 + index,
                        20.123 if dirty and index == 1 else 10.12,
                        index if dirty else customer[1],
                        "contact@example.org" if dirty and index == 0 else "Generated note",
                        "opaque",
                    ),
                )
    return path
