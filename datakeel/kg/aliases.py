# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate symmetric pair candidates without making transitive identity claims."""

from itertools import combinations

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import (
    ExtractorRef,
    VerificationDetail,
    VerificationIssue,
    VerificationLocation,
)
from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_product import KGEntity
from datakeel.core.models import AssetRef
from datakeel.kg.text import normalize_name


def _related(left: KGEntity, right: KGEntity, schema: KGSchema) -> bool:
    first, second = normalize_name(left.name), normalize_name(right.name)
    if left.type != right.type or left.asset_ref.version != right.asset_ref.version:
        return False
    definition = next((item for item in schema.entity_types if item.name == left.type), None)
    if definition is None:
        return False
    if first in second or second in first:
        return True
    return any(
        {first, second} <= {normalize_name(name) for name in (canonical, *aliases)}
        for canonical, aliases in definition.aliases.items()
    )


def _locations(
    left: tuple[ObservationDraft, ...], right: tuple[ObservationDraft, ...]
) -> tuple[VerificationLocation, ...]:
    result: dict[str, VerificationLocation] = {}
    for side, drafts in (("head", left), ("tail", right)):
        for draft in drafts:
            if draft.verification_detail is None:
                continue
            for original in draft.verification_detail.locations:
                location = original
                if side == "tail":
                    location = original.model_copy(
                        update={
                            "tail": location.head,
                            "head": None,
                            "issues": tuple(
                                VerificationIssue(code="tail", role="tail") for _ in location.issues
                            ),
                        }
                    )
                result[location.model_dump_json()] = location
    return tuple(result[key] for key in sorted(result))


def _detail(locations: tuple[VerificationLocation, ...]) -> VerificationDetail:
    missing = VerificationIssue(code="evidence")
    issues = {missing.model_dump_json(): missing}
    issues.update(
        (issue.model_dump_json(), issue) for location in locations for issue in location.issues
    )
    return VerificationDetail(
        issues=tuple(sorted(issues.values(), key=lambda issue: (issue.code, issue.role or ""))),
        locations=locations,
    )


def same_as_drafts(
    entities: tuple[KGEntity, ...],
    drafts: tuple[ObservationDraft, ...],
    schema: KGSchema,
    extractor: ExtractorRef,
) -> tuple[ObservationDraft, ...]:
    """Propose only grounded cross-document pairs not already represented by a pair claim."""
    mentions = {
        entity.asset_ref.asset_id: tuple(
            draft
            for draft in drafts
            if draft.predicate == "kg.mentions"
            and draft.subject.asset_id == entity.asset_ref.asset_id
        )
        for entity in entities
    }
    existing = {
        tuple(sorted((draft.subject.asset_id, draft.object.asset_id)))
        for draft in drafts
        if draft.predicate == "kg.same_as" and isinstance(draft.object, AssetRef)
    }
    eligible = {
        entity.asset_ref.asset_id: entity
        for entity in entities
        if mentions[entity.asset_ref.asset_id]
    }
    result: list[ObservationDraft] = []
    for left_id, right_id in combinations(sorted(eligible), 2):
        left, right = eligible[left_id], eligible[right_id]
        if (left_id, right_id) in existing or not _related(left, right, schema):
            continue
        sources = [
            {anchor.asset_ref.asset_id for draft in mentions[key] for anchor in draft.anchors}
            for key in (left_id, right_id)
        ]
        if not any(first != second for first in sources[0] for second in sources[1]):
            continue
        selected = (*mentions[left_id], *mentions[right_id])
        anchors = {
            anchor.model_dump_json(): anchor for draft in selected for anchor in draft.anchors
        }
        locations = _locations(mentions[left_id], mentions[right_id])
        result.append(
            ObservationDraft(
                subject=left.asset_ref,
                predicate="kg.same_as",
                object=right.asset_ref,
                anchors=tuple(anchors[key] for key in sorted(anchors)),
                extractor=extractor,
                verification="needs_review",
                verification_detail=_detail(locations),
            )
        )
    return tuple(result)
