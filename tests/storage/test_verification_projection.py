# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve legacy payloads while adding independent source-verification projections."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from datakeel.core.evidence_models import Assertion, TextSpan, VerificationDetail, VerificationIssue
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.evidence_store import list_assertions, record_extraction
from tests.evidence.helpers import extraction_event, fixture_bundle

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_legacy_assertion_serialization_omits_new_optional_fields() -> None:
    """Existing content digests and bundle payloads retain their exact key set."""
    original = fixture_bundle(extraction_event()).assertions[0]
    payload = original.model_dump(mode="json")
    assert "verification" not in payload
    assert "verification_detail" not in payload
    assert Assertion.model_validate(payload) == original


def test_verification_is_projected_and_survives_rebuild(db: Database) -> None:
    """Verification does not replace the independent candidate status overlay."""
    event = extraction_event()
    bundle = fixture_bundle(event)
    detail = VerificationDetail(
        issues=(VerificationIssue(code="head", role="head"),),
        evidence=TextSpan(start=1, end=10),
        tail=TextSpan(start=7, end=9),
    )
    assertion = bundle.assertions[0].model_copy(
        update={"verification": "needs_review", "verification_detail": detail}
    )
    bundle = bundle.model_copy(update={"assertions": (assertion,)})
    record_extraction(db, event, bundle)
    with db.session() as session:
        row = session.get(AssertionRow, assertion.id)
        assert row is not None
        assert row.verification == "needs_review"
        assert row.verification_detail == detail.model_dump(mode="json")
        assert row.status == "candidate"
    assert rebuild_evidence(db).matches
    assert list_assertions(db)[0].verification_detail == detail


def test_legacy_assertion_migration_adds_nullable_columns_and_index(
    unmigrated_db: Database,
) -> None:
    """Old stores gain indexed verification without assigning invented check results."""
    with unmigrated_db.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE assertions (id VARCHAR PRIMARY KEY, subject_id VARCHAR NOT NULL, "
                "predicate VARCHAR NOT NULL, producer_event_id VARCHAR NOT NULL, "
                "payload JSON NOT NULL, status VARCHAR NOT NULL, decided_by VARCHAR, "
                "decided_at VARCHAR, active BOOLEAN NOT NULL)"
            )
        )
    unmigrated_db.migrate()
    unmigrated_db.migrate()
    inspector = inspect(unmigrated_db.engine)
    columns = {column["name"]: column for column in inspector.get_columns("assertions")}
    assert columns["verification"]["nullable"]
    assert columns["verification_detail"]["nullable"]
    assert any(
        index["column_names"] == ["verification"] for index in inspector.get_indexes("assertions")
    )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE assertions SET verification='verified'",
        "UPDATE assertions SET verification_detail='{}'",
    ],
)
def test_database_guards_immutable_verification_projections(db: Database, statement: str) -> None:
    """Both SQL dialects reject direct edits even though status remains independently mutable."""
    record_extraction(db, extraction_event())
    db.migrate()
    with pytest.raises(DBAPIError, match="immutable"), db.engine.begin() as connection:
        connection.execute(text(statement))
    with db.session() as session:
        row = session.get(AssertionRow, list_assertions(db)[0].id)
        assert row is not None
        assert row.verification is None
        assert row.verification_detail is None
        row.status = "accepted"
        session.commit()
    assert list_assertions(db)[0].status == "accepted"
