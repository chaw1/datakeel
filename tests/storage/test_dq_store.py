# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned quality definitions and reviewable incident transitions."""

from datetime import UTC, datetime, timedelta

import pytest

from datakeel.core.dq_models import DqParameters, DqResult, DqRule, DqTarget
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.storage.database import Database
from datakeel.storage.dq_issues import change_issue, get_issue, list_issues, observe_result
from datakeel.storage.dq_jobs import schedule_rule
from datakeel.storage.dq_reads import (
    read_execution_inputs,
    read_history,
    read_issues,
    read_results,
    read_rules,
)
from datakeel.storage.dq_rows import DqResultRow
from datakeel.storage.dq_store import delete_rule, get_rule, rule_revision, upsert_rule


def definition(identifier: str = "orders-required") -> DqRule:
    """Build a source-independent rule without accessing business data."""
    return DqRule(
        id=identifier,
        name="Order amount required",
        owner="Data team",
        target=DqTarget(source_id="sample", table="orders", column="amount"),
        kind="not_null",
    )


def test_rule_revision_history_tombstone_and_stale_writes(db: Database) -> None:
    """Keep accepted mutations while rejecting stale plans and deleted-ID reuse."""
    rule = definition()
    with db.session() as session:
        assert rule_revision(session, rule.id) is None
        saved = upsert_rule(session, rule, None, "reviewer")
        session.commit()
    with db.session() as session, pytest.raises(ConflictError):
        upsert_rule(session, rule, None, "reviewer")
    with db.session() as session:
        changed = upsert_rule(
            session, saved.model_copy(update={"owner": "Operations"}), 1, "reviewer"
        )
        assert changed.revision == 2
        session.commit()
    assert read_rules(db, "sample")[0].owner == "Operations"
    assert read_rules(db, "other") == ()
    with db.session() as session, pytest.raises(ConflictError):
        delete_rule(session, rule.id, 1, "reviewer")
    with db.session() as session:
        assert delete_rule(session, rule.id, 2, "reviewer").revision == 3
        session.commit()
    assert [item.operation for item in read_history(db, rule.id)] == ["create", "update", "delete"]
    assert read_rules(db) == ()
    with db.session() as session:
        assert get_rule(session, rule.id, include_deleted=True).revision == 3
        assert rule_revision(session, rule.id) == 3
        with pytest.raises(NotFoundError):
            get_rule(session, rule.id)
        with pytest.raises(NotFoundError):
            delete_rule(session, rule.id, 3, "reviewer")
        with pytest.raises(ConflictError):
            upsert_rule(session, rule, 3, "reviewer")


def test_consecutive_failures_claim_recover_confirm_and_reopen(db: Database) -> None:
    """Merge a failure episode and require explicit confirmation of a recovery."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with db.session() as session:
        assert observe_result(session, DqResult(rule_id="r", status="passed"), now) is None
        assert (
            observe_result(session, DqResult(rule_id="r", status="baseline_insufficient"), now)
            is None
        )
        initial = observe_result(session, DqResult(rule_id="r", status="failed"), now)
        assert initial is not None
        again = observe_result(session, DqResult(rule_id="r", status="failed"), now)
        assert again is not None
        assert again.id == initial.id
        assert again.failures == 2
        claimed = change_issue(session, initial.id, "claimed", "on-call", 2, "reviewer")
        assert claimed.assignee == "on-call"
        recovered = observe_result(session, DqResult(rule_id="r", status="passed"), now)
        assert recovered is not None
        assert recovered.status == "recovered"
        assert observe_result(session, DqResult(rule_id="r", status="passed"), now) is None
        relapse = observe_result(session, DqResult(rule_id="r", status="error"), now)
        assert relapse is not None
        assert relapse.status == "open"
        observe_result(session, DqResult(rule_id="r", status="passed"), now)
        resolved = change_issue(session, initial.id, "resolved", None, 6, "reviewer")
        assert resolved.assignee == "on-call"
        final = observe_result(session, DqResult(rule_id="r", status="failed"), now)
        assert final is not None
        assert final.id != initial.id
        session.commit()
    assert len(read_issues(db, "r")) == 2
    assert read_results(db, "r") == ()


def test_issue_mutation_rejects_invalid_or_stale_requests(db: Database) -> None:
    """Reject missing, unassigned, stale and already resolved incident changes."""
    with db.session() as session:
        with pytest.raises(NotFoundError):
            get_issue(session, "absent")
        initial = observe_result(
            session, DqResult(rule_id="r", status="failed"), datetime(2026, 1, 1, tzinfo=UTC)
        )
        assert initial is not None
        with pytest.raises(ConflictError):
            change_issue(session, initial.id, "claimed", "owner", 0, "reviewer")
        with pytest.raises(ValidationError):
            change_issue(session, initial.id, "claimed", None, 1, "reviewer")
        with pytest.raises(ValidationError):
            change_issue(session, initial.id, "open", None, 1, "reviewer")
        with pytest.raises(ValidationError):
            change_issue(session, initial.id, "resolved", None, 1, "reviewer")
        observe_result(
            session, DqResult(rule_id="r", status="passed"), datetime(2026, 1, 1, tzinfo=UTC)
        )
        claimed = change_issue(session, initial.id, "claimed", "owner", 2, "reviewer")
        assert claimed.status == "recovered"
        change_issue(session, initial.id, "resolved", None, 3, "reviewer")
        with pytest.raises(ValidationError):
            change_issue(session, initial.id, "claimed", "owner", 4, "reviewer")
        assert len(list_issues(session)) == 1


@pytest.mark.parametrize("retirement", ["disable", "delete"])
def test_retired_rule_issue_can_be_confirmed_without_false_recovery(
    db: Database,
    retirement: str,
) -> None:
    """Retiring monitoring permits audited closure without claiming the data recovered."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        initial = observe_result(
            session, DqResult(rule_id=rule.id, status="failed"), datetime(2026, 1, 1, tzinfo=UTC)
        )
        assert initial is not None
        assert not initial.can_resolve
        if retirement == "delete":
            delete_rule(session, rule.id, 1, "reviewer")
        else:
            upsert_rule(session, rule.model_copy(update={"enabled": False}), 1, "reviewer")
        view = get_issue(session, initial.id)
        assert view.status == "open"
        assert view.can_resolve
        assert list_issues(session)[0].can_resolve
        resolved = change_issue(session, initial.id, "resolved", None, 1, "reviewer")
        assert resolved.status == "resolved"
        assert not resolved.can_resolve
        session.commit()


def test_baseline_query_filters_before_limit_after_long_failure_streak(db: Database) -> None:
    """The last successful baseline remains available after a thousand failed runs."""
    rule = definition().model_copy(
        update={
            "kind": "volume_change",
            "params": DqParameters(baseline_runs=1),
        }
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with db.session() as session:
        upsert_rule(session, rule, None, "reviewer")
        run = schedule_rule(session, rule.id, "next-observation")
        for index in range(1001):
            result = DqResult(
                id=str(index),
                rule_id=rule.id,
                rule_revision=1,
                status="failed" if index else "passed",
                started_at=now + timedelta(seconds=index),
            )
            session.add(
                DqResultRow(
                    id=result.id,
                    run_id=f"generated:{index}",
                    rule_id=rule.id,
                    rule_revision=1,
                    started_at=result.started_at.timestamp(),
                    sequence=index,
                    status=result.status,
                    payload=result.model_dump(mode="json", exclude={"passed"}),
                )
            )
        session.commit()
    _, history = read_execution_inputs(db, run.id)
    assert [result.id for result in history] == ["0"]
