# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic entity identities and cross-block evidence union."""

import hashlib
import json
from collections import defaultdict

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import EvidenceAnchor, VerificationDetail
from datakeel.core.kg_contracts import ExtractedEntity
from datakeel.core.models import AssetRef
from datakeel.kg.text import normalize_name


def entity_asset_ref(dataset_id: str, version_id: str, entity: ExtractedEntity) -> AssetRef:
    """Keep identity stable across versions while versioning each graph projection."""
    name = normalize_name(entity.name)
    digest = hashlib.sha256(json.dumps([dataset_id, entity.type, name]).encode()).hexdigest()
    return AssetRef(
        asset_type="kg_entity", asset_id=f"kg-{digest}", version=version_id, display_name=name
    )


def _canonical(draft: ObservationDraft, *, anchors: bool) -> str:
    content = draft.model_dump(mode="json", exclude={"verification", "verification_detail"})
    content["subject"].pop("display_name", None)
    if isinstance(draft.object, AssetRef):
        content["object"].pop("display_name", None)
    if anchors:
        content["anchors"] = sorted(
            content["anchors"], key=lambda item: json.dumps(item, sort_keys=True)
        )
    else:
        content.pop("anchors")
    return json.dumps(content, sort_keys=True, separators=(",", ":"))


def assertion_identity(draft: ObservationDraft) -> str:
    """Hash immutable graph content independently of run, event and timestamps."""
    return f"kg-{hashlib.sha256(_canonical(draft, anchors=True).encode()).hexdigest()}"


def _merge_group(drafts: list[ObservationDraft]) -> ObservationDraft:
    first = drafts[0]
    anchors: dict[str, EvidenceAnchor] = {}
    for draft in drafts:
        for anchor in draft.anchors:
            anchors[anchor.model_dump_json()] = anchor
    details = [
        draft.verification_detail for draft in drafts if draft.verification_detail is not None
    ]
    detail = details[0] if details else None
    if detail:
        issues = tuple(dict.fromkeys(issue for item in details for issue in item.issues))
        detail = VerificationDetail(
            issues=issues,
            evidence=detail.evidence,
            head=detail.head,
            tail=detail.tail,
            locations=tuple(
                {
                    location.model_dump_json(): location
                    for item in details
                    for location in item.locations
                }.values()
            ),
        )
    return first.model_copy(
        update={
            "anchors": tuple(anchors[key] for key in sorted(anchors)),
            "verification": "needs_review"
            if any(draft.verification == "needs_review" for draft in drafts)
            else first.verification,
            "verification_detail": detail,
        }
    )


def merge_drafts(drafts: tuple[ObservationDraft, ...]) -> tuple[ObservationDraft, ...]:
    """Merge cross-block triples while preserving each distinct entity mention."""
    groups: dict[str, list[ObservationDraft]] = defaultdict(list)
    for draft in drafts:
        groups[_canonical(draft, anchors=draft.predicate == "kg.mentions")].append(draft)
    return tuple(_merge_group(groups[key]) for key in sorted(groups))
