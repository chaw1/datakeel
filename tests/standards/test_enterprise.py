# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Every fictional business table and view receives a clean supported recommendation."""

import sqlite3
from contextlib import closing

from datakeel.core.standard_models import ColumnProfile, StandardsContract
from datakeel.sample_enterprise.crm import build_crm
from datakeel.sample_enterprise.ecommerce import build_ecommerce
from datakeel.sample_enterprise.erp import build_erp
from datakeel.sample_enterprise.service import build_service
from datakeel.standards.checks import check_column
from datakeel.standards.mapping import suggest


def _check(profile: ColumnProfile, contract: StandardsContract) -> None:
    suggestion = suggest(profile, contract)
    if profile.name in {"id", "name", "code", "type"}:
        assert not suggestion.candidates, profile.column_id
        return
    assert suggestion.candidates, profile.column_id
    definition = next(
        item for item in contract.standards if item.code == suggestion.candidates[0].standard_code
    )
    assert check_column(profile, definition, contract.code_lists).compliant, profile.column_id


def test_all_enterprise_tables_and_views_receive_clean_explainable_recommendations(
    contract: StandardsContract,
) -> None:
    """Business columns receive clean matches while bare generic fields require manual mapping."""
    checked = 0
    for source in (build_crm(), build_ecommerce(), build_erp(), build_service()):
        types: dict[str, str] = {}
        with closing(sqlite3.connect(":memory:")) as connection:
            for table in source.tables:
                declarations = {
                    part.split()[0]: part.split()[1] for part in table.definition.split(",")
                }
                types.update(declarations)
                # Fixed generated fixture declarations.
                connection.execute(f'CREATE TABLE "{table.name}" ({table.definition})')
                placeholders = ",".join("?" for _ in table.columns)
                connection.executemany(
                    f'INSERT INTO "{table.name}" VALUES ({placeholders})',  # noqa: S608  # Authored fixture names.
                    table.rows[:30],
                )  # Authored fixture names; values are bound.
                for ordinal, name in enumerate(table.columns):
                    _check(
                        ColumnProfile(
                            column_id=f"{source.id}/{table.name}/{name}",
                            name=name,
                            data_type=declarations[name],
                            source_id=source.id,
                            table_id=table.name,
                            values=tuple(row[ordinal] for row in table.rows[:30]),
                        ),
                        contract,
                    )
                    checked += 1
            for view in source.views:
                cursor = connection.execute(view.query)
                rows = cursor.fetchall()
                for ordinal, column in enumerate(cursor.description):
                    _check(
                        ColumnProfile(
                            column_id=f"{source.id}/{view.name}/{column[0]}",
                            name=column[0],
                            data_type=types[column[0]],
                            source_id=source.id,
                            table_id=view.name,
                            values=tuple(row[ordinal] for row in rows),
                        ),
                        contract,
                    )
                    checked += 1
    assert checked >= 120
