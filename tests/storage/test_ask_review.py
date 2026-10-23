# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Question reviews reuse controlled audit actions without freezing semantic catalog objects."""

import pytest
from sqlalchemy import delete

from datakeel.actions.models import ActionContext, ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import BudgetError, ConflictError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.ontology.models import ObjectSet
from datakeel.storage.ask_review import question_references
from datakeel.storage.ask_rows import AskAnswerRow
from datakeel.storage.ask_store import get_answer, store_answer
from datakeel.storage.database import Database
from datakeel.storage.evidence_decisions import list_decisions
from datakeel.storage.evidence_projection import rebuild_evidence
from tests.storage.ask_helpers import answer_case, refusal_case


def test_question_review_is_reversible_and_keeps_manifest_free_of_catalog_assets(
    db: Database,
) -> None:
    """Accept and undo exact question facts while preserving immutable response content."""
    request, draft = answer_case(db)
    saved = store_answer(db, request, draft)
    for status in ("accepted", "rejected", "candidate"):
        plan = prepare_action(
            db,
            "decide_assertions",
            JsonDocument(
                {
                    "assertion_ids": list(saved.assertion_ids),
                    "status": status,
                }
            ),
        )
        assert plan.manifest.objects == []
        assert plan.manifest.query.object_type == "file"
        run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
        assert run.status == "SUCCEEDED"
        assert run.receipt is not None
        assert {ref.asset_type for ref in run.receipt.outputs} >= {"question", "metric", "term"}
        assert {item.status for item in get_answer(db, saved.id).assertions} == {status}
    assert len(list_decisions(db)) == 6
    assert rebuild_evidence(db).matches
    assert get_answer(db, saved.id).result == saved.result


def test_question_review_detects_intervening_decision(db: Database) -> None:
    """The existing audit-sequence snapshot rejects stale question review plans."""
    request, draft = refusal_case()
    saved = store_answer(db, request, draft)
    params = JsonDocument({"assertion_ids": list(saved.assertion_ids), "status": "accepted"})
    old = prepare_action(db, "decide_assertions", params)
    current = prepare_action(db, "decide_assertions", params)
    execute_plan(db, current.id, ExecuteRequest(plan_digest=current.plan_digest))
    with pytest.raises(ConflictError, match="state changed"):
        execute_plan(db, old.id, ExecuteRequest(plan_digest=old.plan_digest))


def test_question_review_empty_manifest_does_not_bypass_action_budget(db: Database) -> None:
    """Count reviewed facts even when their question sources are outside the file ObjectSet."""
    request, draft = refusal_case()
    saved = store_answer(db, request, draft)
    params = JsonDocument({"assertion_ids": list(saved.assertion_ids), "status": "accepted"})
    with pytest.raises(BudgetError, match="impact exceeds"):
        prepare_action(db, "decide_assertions", params, ActionContext(max_objects=0))
    plan = prepare_action(db, "decide_assertions", params)
    assert plan.impact.object_count == 1
    assert not plan.manifest.objects


def test_question_review_requires_saved_answer_and_never_enables_objectset(db: Database) -> None:
    """An orphaned question assertion cannot authorize arbitrary semantic-object operations."""
    request, draft = refusal_case()
    saved = store_answer(db, request, draft)
    with db.session() as session:
        session.execute(delete(AskAnswerRow).where(AskAnswerRow.id == saved.id))
        session.commit()
    with pytest.raises(ConflictError, match="unavailable"):
        prepare_action(
            db,
            "decide_assertions",
            JsonDocument(
                {
                    "assertion_ids": list(saved.assertion_ids),
                    "status": "accepted",
                }
            ),
        )
    with pytest.raises(ValueError, match="frozen asset selections"):
        ObjectSet(object_type="question")
    with pytest.raises(ValidationError, match="versioned local"):
        question_references(saved.assertions[0].model_copy(update={"predicate": "corrupt"}))
