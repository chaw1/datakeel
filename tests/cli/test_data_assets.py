# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""CLI asset management uses real controlled plans and explicit signed execution."""

from datetime import timedelta
from pathlib import Path

import pytest

from datakeel.actions.models import ActionPlan
from datakeel.core.data_asset_models import AssetApplication, AssetGrant, DataAssetCard
from datakeel.core.models import JsonDocument, utcnow
from datakeel.storage.data_asset_store import list_assets
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from tests.cli.conftest import Invoke


def _action(
    invoke: Invoke,
    capsys: pytest.CaptureFixture[str],
    path: Path,
    action: str,
    params: JsonDocument,
) -> ActionPlan:
    path.write_text(params.model_dump_json(), encoding="utf-8")
    invoke("data-assets", "prepare", action, str(path))
    return ActionPlan.model_validate_json(capsys.readouterr().out)


def _execute(invoke: Invoke, capsys: pytest.CaptureFixture[str], plan: ActionPlan) -> None:
    if plan.requires_approval:
        invoke("data-assets", "approve", plan.id, "--digest", plan.plan_digest)
        assert ActionPlan.model_validate_json(capsys.readouterr().out).status == "APPROVED"
    invoke("data-assets", "execute", plan.id, "--digest", plan.plan_digest)
    assert '"SUCCEEDED"' in capsys.readouterr().out


@pytest.fixture
def card(
    db: Database, tmp_path: Path, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> DataAssetCard:
    """Create and publish a CLI-managed generated asset with no external services."""
    source = tmp_path / "source.txt"
    source.write_text("Generated CLI fixture", encoding="utf-8")
    dataset = import_paths(db, "CLI asset fixture", [source])
    payload = tmp_path / "params.json"
    plan = _action(
        invoke,
        capsys,
        payload,
        "create_data_asset",
        JsonDocument(
            {
                "definition": {
                    "name": "Sales fixture",
                    "owner": "local",
                    "target": {"asset_id": dataset.id},
                }
            }
        ),
    )
    _execute(invoke, capsys, plan)
    asset = list_assets(db)[0]
    plan = _action(
        invoke, capsys, payload, "publish_data_asset", JsonDocument({"asset_id": asset.id})
    )
    _execute(invoke, capsys, plan)
    invoke("data-assets", "show", asset.id)
    return DataAssetCard.model_validate_json(capsys.readouterr().out)


def test_cli_asset_reads_show_market_card_history_grants_and_audit(
    card: DataAssetCard, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """The public command grammar exposes measured market cards and durable histories."""
    invoke("data-assets", "list", "--search", "Sales", "--include-unpublished", "--sort", "name")
    assert '"total":1' in capsys.readouterr().out
    invoke("data-assets", "history", card.asset.id)
    assert '"published"' in capsys.readouterr().out
    for command in ("grants", "applications", "audit"):
        invoke("data-assets", command, "--asset-id", card.asset.id)
        assert capsys.readouterr().out == ""


def test_cli_application_approval_and_revocation_preserve_subject(
    card: DataAssetCard,
    invoke: Invoke,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Apply and explicitly sign a grant before separately authorizing its revocation."""
    payload = tmp_path / "apply.json"
    payload.write_text(
        JsonDocument(
            {
                "asset_id": card.asset.id,
                "purpose": "Fixture planning",
                "scopes": ["query"],
                "expires_at": (utcnow() + timedelta(days=1)).isoformat(),
            }
        ).model_dump_json(),
        encoding="utf-8",
    )
    invoke("data-assets", "apply", str(payload), "--applicant", "reader")
    request = AssetApplication.model_validate_json(capsys.readouterr().out)
    plan = _action(
        invoke,
        capsys,
        payload,
        "decide_asset_application",
        JsonDocument({"application_id": request.id, "approve": True}),
    )
    _execute(invoke, capsys, plan)
    invoke("data-assets", "grants", "--subject", "reader")
    grant = AssetGrant.model_validate_json(capsys.readouterr().out)
    assert grant.subject == "reader"
    revoke = _action(
        invoke, capsys, payload, "revoke_asset_grant", JsonDocument({"grant_id": grant.id})
    )
    invoke("data-assets", "reject", revoke.id, "--digest", revoke.plan_digest)
    assert ActionPlan.model_validate_json(capsys.readouterr().out).status == "REJECTED"
    approved_revoke = _action(
        invoke, capsys, payload, "revoke_asset_grant", JsonDocument({"grant_id": grant.id})
    )
    _execute(invoke, capsys, approved_revoke)
