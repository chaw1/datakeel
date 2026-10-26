# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""CLI plan responses preserve native source grants rather than exposing old manifests."""

import pytest

from datakeel.actions import service
from datakeel.actions.models import ActionPlan
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database
from tests.assets.action_helpers import seed_action_source, source_params
from tests.assets.entry_helpers import grant, revoke
from tests.cli.conftest import Invoke


def test_cli_revoked_plan_approval_and_execution_return_no_source_data(
    db: Database, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both mutation response commands refuse their saved source after grant revocation."""
    source = seed_action_source(db)
    grant_id = grant(db, source.asset, "valid", "query")
    assert grant_id is not None
    plan = service.prepare_action(db, "delete_files", source_params(source))
    revoke(db, grant_id)
    for command in ("approve", "execute"):
        with pytest.raises(AuthorizationError, match="apply for access"):
            invoke("data-assets", command, plan.id, "--digest", plan.plan_digest)
        assert capsys.readouterr().out == ""


def test_cli_export_plan_uses_export_scope_without_query_scope(
    db: Database, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """An export-only subject can review, approve and execute its export plan from the CLI."""
    source = seed_action_source(db)
    grant(db, source.asset, "valid", "export")
    plan = service.prepare_action(
        db, "export_dataset", JsonDocument({"dataset_id": source.dataset_id})
    )
    invoke("data-assets", "approve", plan.id, "--digest", plan.plan_digest)
    approved = ActionPlan.model_validate_json(capsys.readouterr().out)
    assert approved.status == "APPROVED"
    assert source.marker in approved.model_dump_json()
    invoke("data-assets", "execute", plan.id, "--digest", plan.plan_digest)
    assert '"SUCCEEDED"' in capsys.readouterr().out
