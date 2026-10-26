# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve every resource disclosed by an answer before it leaves the read boundary."""

from datakeel.core.ask_models import AskAnswer
from datakeel.core.knowledge_citations import knowledge_citations
from datakeel.core.metric_models import CompiledQuery
from datakeel.core.models import AssetRef


def query_refs(query: CompiledQuery) -> tuple[AssetRef, ...]:
    """Authorize the complete compiled table and column set before executing SQL."""
    return (
        AssetRef(asset_type="metric", asset_id=query.metric_id, version=str(query.metric_version)),
        *(AssetRef(asset_type="table", asset_id=key) for key in query.tables),
        *(AssetRef(asset_type="column", asset_id=key) for key in query.columns),
    )


def answer_refs(answer: AskAnswer) -> tuple[AssetRef, ...]:
    """Include revisions, query dependencies, knowledge sources and candidate disclosures."""
    cards = answer.candidates + ((answer.metric_card,) if answer.metric_card else ())
    refs = [
        AssetRef(
            asset_type="metric", asset_id=card.definition.id, version=str(card.definition.version)
        )
        for card in cards
    ]
    if answer.sql:
        refs.extend(AssetRef(asset_type="table", asset_id=key) for key in answer.sql.tables)
        refs.extend(AssetRef(asset_type="column", asset_id=key) for key in answer.sql.columns)
    refs.extend(knowledge_citations(answer.knowledge))
    refs.extend(candidate.asset_ref for candidate in answer.subject_candidates)
    return tuple(refs)
