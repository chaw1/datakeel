# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The default generated demo publishes useful cards without granting hidden access."""

from pathlib import Path

from datakeel.cli.asset_demo import seed_asset_demo
from datakeel.storage.data_asset_grants import list_grants
from datakeel.storage.data_asset_store import asset_history
from datakeel.storage.database import Database
from tests.assets.entry_helpers import seed_resources


def test_demo_cards_cover_all_classifications_and_replay_without_duplicates(
    db: Database, tmp_path: Path
) -> None:
    """Six controlled publications persist history and leave application meaningful."""
    resources = seed_resources(db, tmp_path)
    cards = seed_asset_demo(db, resources.dataset_id)
    assert len(cards) == 6
    assert {card.definition.classification for card in cards} == {
        "public",
        "internal",
        "request",
        "restricted",
    }
    assert {card.definition.target.asset_type for card in cards} == {"dataset", "table", "metric"}
    assert all(card.status == "published" for card in cards)
    assert all(len(asset_history(db, card.id)) == 2 for card in cards)
    assert {card.id for card in seed_asset_demo(db, resources.dataset_id)} == {
        card.id for card in cards
    }
    assert list_grants(db) == ()
