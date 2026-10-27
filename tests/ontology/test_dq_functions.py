# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Quality tools remain deferred reads of actual persisted monitoring evidence."""

from pathlib import Path

import pytest
from pydantic import ValidationError as ModelValidationError

from datakeel.agent.tools import deferred_tools, resident_tools
from datakeel.core.errors import NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.ontology.functions import invoke_function
from datakeel.storage.database import Database
from datakeel.worker.runner import run_worker
from tests.dq_support import execute_action, generated_rule, save_rule


def test_quality_tools_are_deferred_and_reject_sql_parameters() -> None:
    """Monitoring adds no resident prompt schemas and exposes no arbitrary query parameter."""
    names = {"list_quality_rules", "get_table_quality"}
    assert names <= {tool.name for tool in deferred_tools()}
    assert not names.intersection(tool.name for tool in resident_tools())


def test_quality_tools_read_latest_verdict_and_history(db: Database, tmp_path: Path) -> None:
    """A real worker failure appears in both tools with exact catalog identities."""
    rule = generated_rule(db, tmp_path)
    save_rule(db, rule)
    empty = invoke_function(db, "list_quality_rules", JsonDocument({"status": "failed"}))
    assert empty.data == {"items": [], "total": 0}
    execute_action(db, "run_quality_rule", JsonDocument({"rule_id": rule.id}))
    run_worker(db, once=True)
    failed = invoke_function(db, "list_quality_rules", JsonDocument({"status": "failed"}))
    assert failed.asset_refs[0].asset_id == rule.id
    table = invoke_function(
        db, "get_table_quality", JsonDocument({"source_id": "orders-test", "table": "orders"})
    )
    assert table.asset_refs[0].asset_id == "orders-test/main/orders"
    assert isinstance(table.data, dict)
    assert isinstance(table.data["summary"], dict)
    assert table.data["summary"]["failed"] == 1
    assert isinstance(table.data["trends"], list)
    assert len(table.data["trends"]) == 1
    with pytest.raises(NotFoundError):
        invoke_function(
            db, "get_table_quality", JsonDocument({"source_id": "missing", "table": "orders"})
        )
    with pytest.raises(ModelValidationError):
        invoke_function(db, "list_quality_rules", JsonDocument({"sql": "DELETE FROM orders"}))
