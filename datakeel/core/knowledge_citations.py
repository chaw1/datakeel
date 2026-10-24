# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Extract immutable asset and assertion receipts from separated knowledge answers."""

from datakeel.core.knowledge_models import KnowledgeAnswer
from datakeel.core.models import AssetRef


def knowledge_citations(knowledge: KnowledgeAnswer | None) -> tuple[AssetRef, ...]:
    """List the system assets, graph entities, relations and link assertions actually used."""
    if knowledge is None:
        return ()
    refs = [item.asset_ref for item in knowledge.system_records]
    if knowledge.subject:
        refs.append(knowledge.subject.asset_ref)
    for claim in knowledge.claims:
        refs.extend(
            (claim.head.asset_ref, claim.tail.asset_ref, _assertion_ref(claim.assertion_id))
        )
        if claim.subject_link:
            refs.extend(
                (claim.subject_link.asset_ref, _assertion_ref(claim.subject_link.assertion_id))
            )
        if claim.other_end.asset_ref:
            refs.append(claim.other_end.asset_ref)
        if claim.other_end.assertion_id:
            refs.append(_assertion_ref(claim.other_end.assertion_id))
    return tuple(dict.fromkeys(refs))


def _assertion_ref(identity: str) -> AssetRef:
    return AssetRef(asset_type="assertion", asset_id=identity, version=identity)
