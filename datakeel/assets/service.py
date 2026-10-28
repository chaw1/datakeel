# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic asset market search and explicitly configured factual ranking."""

from datetime import datetime

from datakeel.assets.ranking import load_ranking
from datakeel.core.data_asset_models import (
    AssetMarketPage,
    AssetMarketQuery,
    AssetRanking,
    DataAssetCard,
)
from datakeel.storage.data_asset_cards import all_asset_cards, get_asset_card
from datakeel.storage.database import Database


def _matches(card: DataAssetCard, query: AssetMarketQuery) -> bool:
    asset = card.asset
    definition = asset.definition
    haystack = " ".join(
        (
            definition.name,
            definition.name_en,
            definition.owner,
            *definition.tags,
            *definition.synonyms,
        )
    ).casefold()
    return (
        (query.status is None or query.status == asset.status)
        and (query.classification is None or query.classification == definition.classification)
        and (
            query.tag is None or query.tag.casefold() in {tag.casefold() for tag in definition.tags}
        )
        and all(term in haystack for term in query.search.casefold().split())
    )


def _sort_value(card: DataAssetCard, query: AssetMarketQuery, ranking: AssetRanking) -> float | str:
    if query.sort == "name":
        return card.asset.definition.name.casefold()
    if query.sort == "quality":
        return -(card.quality_score if card.quality_score is not None else -1)
    if query.sort == "freshness":
        return card.freshness_seconds if card.freshness_seconds is not None else float("inf")
    if query.sort == "downstream":
        return -card.downstream_count
    return -(
        card.usage_count * ranking.usage_weight
        + card.user_count * ranking.users_weight
        + card.downstream_count * ranking.downstream_weight
    )


def search_market(
    db: Database,
    query: AssetMarketQuery,
    ranking: AssetRanking | None = None,
    *,
    now: datetime | None = None,
) -> AssetMarketPage:
    """Apply AND substring search, exact filters and documented stable score ordering."""
    configured = ranking or load_ranking()
    cards = [card for card in all_asset_cards(db, now=now) if _matches(card, query)]
    cards.sort(
        key=lambda card: (
            _sort_value(card, query, configured),
            -(card.updated_at.timestamp() if card.updated_at else 0),
            card.asset.id,
        )
    )
    return AssetMarketPage(
        items=tuple(cards[query.offset : query.offset + query.limit]),
        total=len(cards),
        offset=query.offset,
        limit=query.limit,
    )


__all__ = ["get_asset_card", "search_market"]
