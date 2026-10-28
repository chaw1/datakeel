# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Controlled custom-source publication binds approvals to immutable code versions."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.pipeline import Node, Pipeline
from datakeel.storage.custom_rows import CustomOperatorRow
from datakeel.storage.custom_store import (
    get_custom_operator,
    list_custom_operators,
    list_custom_runs,
    list_custom_submissions,
)
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.task_queue import DatabaseQueue
from tests.core.test_custom_review import CODE

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.custom_operators import CustomOperatorVersion
    from datakeel.storage.database import Database


def publish(db: Database, *, name: str = "filter", code: str = CODE) -> CustomOperatorVersion:
    """Approve and execute source publication through the existing signed action service."""
    plan = prepare_action(db, "submit_custom_operator", JsonDocument({"name": name, "code": code}))
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    assert (
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest)).status
        == "SUCCEEDED"
    )
    return list_custom_operators(db)[-1]


def definition(operator: str, **params: object) -> Pipeline:
    """Construct an immutable custom operator pipeline for durable task tests."""
    return Pipeline(
        nodes=[
            Node(id="custom", operator=operator, inputs={"files": "$input.files"}, params=params)
        ],
        outputs=["custom.files"],
    )


def test_submission_when_unapproved_cannot_publish_and_modified_code_requires_review(
    db: Database,
) -> None:
    """Complete source and findings remain reviewable while unapproved edits cannot run."""
    plan = prepare_action(
        db, "submit_custom_operator", JsonDocument({"name": "filter", "code": CODE})
    )
    assert plan.requires_approval
    assert plan.canonical_params["code"] == CODE
    with pytest.raises(AuthorizationError, match="approval"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert list_custom_operators(db) == []
    approved = publish(db)
    assert get_custom_operator(db, approved.code_hash) == approved
    assert get_custom_operator(db, approved.code_hash, "filter") == approved
    assert list_custom_runs(db) == []
    changed = prepare_action(
        db, "submit_custom_operator", JsonDocument({"name": "filter", "code": CODE + "\n"})
    )
    assert changed.canonical_params["code_hash"] != approved.code_hash
    assert {value.status for value in list_custom_submissions(db)} == {"PREPARED", "EXECUTED"}
    with pytest.raises(NotFoundError):
        get_custom_operator(db, str(changed.canonical_params["code_hash"]))


def test_version_when_same_digest_multiple_names_requires_explicit_name(db: Database) -> None:
    """A content digest cannot silently pick a different registered operator identity."""
    version = publish(db, name="alpha")
    publish(db, name="beta")
    with pytest.raises(ConflictError, match="multiple"):
        get_custom_operator(db, version.code_hash)
    assert get_custom_operator(db, version.code_hash, "alpha").name == "alpha"
    with pytest.raises(NotFoundError):
        get_custom_operator(db, "0" * 64)


def test_approved_source_when_database_content_modified_is_rejected(db: Database) -> None:
    """Execution never trusts a registry row whose bytes no longer match the approved hash."""
    version = publish(db)
    with db.session() as session:
        row = session.get(CustomOperatorRow, version.id)
        assert row is not None
        row.payload = {**row.payload, "code": CODE + "\n"}
        session.commit()
    with pytest.raises(ConflictError, match="modified"):
        get_custom_operator(db, version.code_hash)


@pytest.mark.parametrize("alteration", ["code_and_hash", "payload_name", "row_name", "row_hash"])
def test_approved_version_when_identity_fields_diverge_is_rejected(
    db: Database, alteration: str
) -> None:
    """A self-consistent replacement source cannot retain another approved identity."""
    version = publish(db)
    with db.session() as session:
        row = session.get(CustomOperatorRow, version.id)
        assert row is not None
        if alteration == "code_and_hash":
            changed = CODE + "\n"
            row.payload = {
                **row.payload,
                "code": changed,
                "code_hash": hashlib.sha256(changed.encode()).hexdigest(),
            }
        elif alteration == "payload_name":
            row.payload = {**row.payload, "name": "different"}
        elif alteration == "row_name":
            row.name = "different"
        else:
            row.code_hash = "0" * 64
        session.commit()
    with pytest.raises(ConflictError, match="modified"):
        list_custom_operators(db)


def test_submission_when_caller_forges_derived_material_recomputes_from_code(db: Database) -> None:
    """Client-provided hashes and findings cannot alter the signed review material."""
    plan = prepare_action(
        db,
        "submit_custom_operator",
        JsonDocument(
            {
                "name": "filter",
                "code": "import socket\n" + CODE,
                "code_hash": "claimed",
                "static_checks": [],
                "parameter_schema": {"type": "array"},
            }
        ),
    )
    assert plan.canonical_params["code_hash"] != "claimed"
    checks = plan.canonical_params["static_checks"]
    assert isinstance(checks, list)
    assert len(checks) == 1


def test_pipeline_when_unapproved_or_params_invalid_rejects_both_submission_paths(
    db: Database, tmp_path: Path
) -> None:
    """Direct queue and controlled scheduling share approved-version and schema checks."""
    source = tmp_path / "generated.txt"
    source.write_text("generated fixture")
    dataset = import_paths(db, "custom-fixture", [source])
    queue = DatabaseQueue(db)
    with pytest.raises(NotFoundError, match="approved"):
        queue.submit(dataset.id, "unapproved", definition("custom.filter@" + "0" * 64))
    version = publish(db)
    invalid = definition(version.id, unexpected=True)
    with pytest.raises(ValidationError, match="schema"):
        queue.submit(dataset.id, "invalid", invalid)
    with pytest.raises(ValidationError, match="schema"):
        prepare_action(
            db,
            "run_pipeline",
            JsonDocument({"dataset_id": dataset.id, "pipeline": invalid.model_dump(mode="json")}),
        )
    assert queue.submit(dataset.id, "valid", definition(version.id))
