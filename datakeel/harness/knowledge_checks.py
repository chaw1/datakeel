# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check knowledge facts and provenance without relying on localized answer prose."""

from datakeel.ask.evaluation_checks import scalar_equal
from datakeel.core.ask_models import AskAnswer
from datakeel.core.knowledge_eval import ExpectedClaim, KnowledgeExpectation
from datakeel.core.knowledge_models import KnowledgeClaim
from datakeel.core.models import AssetRef

MAX_SUGGESTIONS = 3


def _claim_matches(expected: ExpectedClaim, actual: KnowledgeClaim) -> bool:
    required = (
        actual.head.name == expected.head,
        actual.predicate == expected.predicate,
        actual.tail.name == expected.tail,
        actual.relation_status == expected.relation_status,
        actual.verification == expected.verification,
        actual.consistency == expected.consistency,
    )
    optional = (
        expected.subject_link_status is None
        or (
            actual.subject_link is not None
            and actual.subject_link.link_status == expected.subject_link_status
        ),
        expected.subject_entity is None
        or (
            actual.subject_link is not None
            and actual.subject_link.entity.name == expected.subject_entity
        ),
        expected.other_end_status is None or actual.other_end.status == expected.other_end_status,
        expected.other_end_asset is None
        or (
            actual.other_end.asset_ref is not None
            and actual.other_end.asset_ref.asset_id == expected.other_end_asset
        ),
    )
    return all((*required, *optional))


def _provenance_failures(answer: AskAnswer) -> list[str]:
    knowledge = answer.knowledge
    if knowledge is None:
        return ["Missing knowledge payload"]
    failures: list[str] = []
    cited = {
        item.object.asset_id
        for item in answer.assertions
        if item.predicate == "ask.cites_assertion" and isinstance(item.object, AssetRef)
    }
    for claim in knowledge.claims:
        references = {claim.assertion_id}
        if claim.subject_link is not None:
            references.add(claim.subject_link.assertion_id)
        if claim.other_end.assertion_id is not None:
            references.add(claim.other_end.assertion_id)
        if not references <= cited:
            failures.append(f"Incomplete assertion citations: {claim.assertion_id}")
        if not claim.evidence or any(
            not item.text or not item.document or not item.source.version for item in claim.evidence
        ):
            failures.append(f"Missing original-source evidence: {claim.assertion_id}")
    return failures


def _knowledge_failures(expected: KnowledgeExpectation, answer: AskAnswer) -> list[str]:
    knowledge = answer.knowledge
    if knowledge is None:
        return ["Missing knowledge payload"]
    failures = _provenance_failures(answer)
    checks = {
        "subject": expected.subject is None
        or (knowledge.subject is not None and knowledge.subject.name == expected.subject),
        "system_assets": set(expected.system_assets)
        <= {item.asset_ref.asset_id for item in knowledge.system_records},
        "empty_system": not expected.empty_system or not knowledge.system_records,
        "empty_claims": not expected.empty_claims or not knowledge.claims,
        "reason_code": expected.reason_code is None
        or knowledge.reason_code == expected.reason_code,
        "pending_ambiguous_links": expected.pending_ambiguous_links is None
        or knowledge.pending_ambiguous_links == expected.pending_ambiguous_links,
        "forbidden_entities": not set(expected.forbidden_entities)
        & {name for item in knowledge.claims for name in (item.head.name, item.tail.name)},
        "forbidden_predicates": not set(expected.forbidden_predicates)
        & {item.predicate for item in knowledge.claims},
    }
    failures.extend(name for name, passed in checks.items() if not passed)
    for claim in expected.claims:
        if not any(_claim_matches(claim, actual) for actual in knowledge.claims):
            failures.append(
                f"Missing required claim or labels: {claim.head}/{claim.predicate}/{claim.tail}"
            )
    return failures


def knowledge_failures(
    expected: KnowledgeExpectation, answer: AskAnswer, expected_value: float | None
) -> tuple[str, ...]:
    """Check route, subject, system facts, individual claims, review labels and audit receipts."""
    failures: list[str] = []
    checks = {
        "answer_kind": answer.answer_kind == expected.answer_kind,
        "status": expected.status is None or answer.status == expected.status,
        "candidates": set(expected.candidates) <= {item.name for item in answer.subject_candidates},
        "suggestions": not expected.suggestions
        or 1 <= len(answer.subject_candidates) <= MAX_SUGGESTIONS,
    }
    failures.extend(name for name, passed in checks.items() if not passed)
    if expected.answer_kind == "knowledge" or expected.claims:
        failures.extend(_knowledge_failures(expected, answer))
    if expected.gold_key is not None and (
        expected_value is None
        or answer.result is None
        or len(answer.result.rows) != 1
        or len(answer.result.rows[0]) != 1
        or not scalar_equal(answer.result.rows[0][0], expected_value)
    ):
        failures.append("Independent scalar gold mismatch")
    return tuple(failures)
