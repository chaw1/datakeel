# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixed ranking ignores legacy environment overrides and retains typed internal test seams."""

from pathlib import Path

import pytest

from datakeel.assets.access import require_access
from datakeel.assets.ranking import load_ranking, ranking_path
from datakeel.assets.service import search_market
from datakeel.core.data_asset_models import (
    AccessContext,
    AssetMarketQuery,
    AssetMutationContext,
    AssetRanking,
    DataAssetDefinition,
)
from datakeel.core.errors import ValidationError
from datakeel.core.models import AssetRef, LineageEvent, new_id
from datakeel.storage.data_asset_store import create_asset_in_session, set_status_in_session
from datakeel.storage.database import Database, DatasetRow
from datakeel.storage.events import append_event


def test_fixed_ranking_contract_ignores_legacy_environment_override(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy settings cannot replace fixed defaults; typed internal overrides remain testable."""
    asset_ids: list[str] = []
    with db.session() as session:
        for name in ("first", "second"):
            session.add(DatasetRow(id=name, name=name))
        session.flush()
        for name in ("first", "second"):
            asset = create_asset_in_session(
                session,
                DataAssetDefinition(target=AssetRef(asset_id=name), name=name, owner="Owner"),
                AssetMutationContext(actor="owner", operation_id=new_id()),
            )
            set_status_in_session(
                session,
                asset.id,
                "published",
                AssetMutationContext(actor="owner", operation_id=new_id()),
            )
            asset_ids.append(asset.id)
        append_event(
            session,
            LineageEvent(
                idempotency_key="dependency",
                operator="generated",
                inputs=[AssetRef(asset_id="second")],
                outputs=[AssetRef(asset_type="report", asset_id="report")],
            ),
        )
        session.commit()
    require_access(
        db,
        (AssetRef(asset_id="first"),),
        AccessContext(actor="reader", entry="agent", scope="query"),
    )
    assert search_market(db, AssetMarketQuery()).items[0].asset.id == asset_ids[0]
    configured = tmp_path / "ranking.yaml"
    configured.write_text("usage_weight: 0\nusers_weight: 0\ndownstream_weight: 100\n")
    monkeypatch.setenv("DATAKEEL_DATA_ASSET_RANKING_FILE", str(configured))
    assert ranking_path() != configured
    assert load_ranking() == AssetRanking()
    assert search_market(db, AssetMarketQuery()).items[0].asset.id == asset_ids[0]
    page = search_market(
        db, AssetMarketQuery(), AssetRanking(usage_weight=0, users_weight=0, downstream_weight=100)
    )
    assert page.items[0].asset.id == asset_ids[1]
    assert search_market(db, AssetMarketQuery()).items[0].asset.id == asset_ids[0]


@pytest.mark.parametrize(
    "content", ["unexpected: 1", "usage_weight: -1", "[unclosed", "null", "usage_weight: .inf"]
)
def test_invalid_ranking_contract_is_rejected(tmp_path: Path, content: str) -> None:
    """Unknown keys, negative/nonfinite weights and malformed YAML cannot silently rank data."""
    path = tmp_path / "ranking.yaml"
    path.write_text(content)
    with pytest.raises(ValidationError, match="Invalid asset ranking"):
        load_ranking(path)


def test_missing_ranking_contract_is_rejected(tmp_path: Path) -> None:
    """An explicitly configured missing file does not fall back to bundled defaults."""
    with pytest.raises(ValidationError, match="Invalid asset ranking"):
        load_ranking(tmp_path / "missing.yaml")
