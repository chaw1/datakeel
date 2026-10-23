# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Workflow identities and storage stay independent of conversation ownership."""

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect

from datakeel.core.models import JsonDocument
from datakeel.core.workflow_models import WorkflowStart
from datakeel.storage.database import Database


def test_start_requires_explicit_idempotency_key() -> None:
    """A retry must carry an explicit durable request identity."""
    with pytest.raises(ValidationError, match="idempotency_key"):
        WorkflowStart.model_validate({"inputs": {}})
    request = WorkflowStart(inputs=JsonDocument({"dataset_id": "fixture"}), idempotency_key="key")
    assert request.model_dump() == {"inputs": {"dataset_id": "fixture"}, "idempotency_key": "key"}


def test_run_tables_have_no_conversation_foreign_keys(db: Database) -> None:
    """Workflow authorization can persist without a fabricated conversation."""
    inspector = inspect(db.engine)
    for table in ("workflow_runs", "workflow_steps", "workflow_audit", "workflow_resumes"):
        assert table in inspector.get_table_names()
        assert all(
            key["referred_table"] != "conversations" for key in inspector.get_foreign_keys(table)
        )
