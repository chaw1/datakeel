# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated local fixtures exercise controlled asset lifecycle and immutable facts."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy.exc import DBAPIError

from datakeel.assets.access import require_access
from datakeel.assets.service import get_asset_card, search_market
from datakeel.core.data_asset_models import (
    AccessContext,
    AssetApplicationInput,
    AssetMarketQuery,
    AssetMutationContext,
    AssetRanking,
    AssetUsageQuery,
    DataAssetDefinition,
)
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.models import AssetRef, FileItem, LineageEvent, new_id
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.data_asset_grants import (
    control_history,
    decide_application_in_session,
    get_application,
    get_grant,
    list_applications,
    list_grants,
    revoke_grant_in_session,
    submit_application,
)
from datakeel.storage.data_asset_rows import (
    AssetControlRow,
    AssetUsageRow,
    DataAssetHistoryRow,
)
from datakeel.storage.data_asset_store import (
    asset_history,
    create_asset_in_session,
    get_asset,
    list_assets,
    set_status_in_session,
    update_asset_in_session,
)
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.events import append_event

if TYPE_CHECKING:
    from sqlalchemy import Table

NOW = datetime(2030, 1, 1, tzinfo=UTC)


def context(actor: str = "steward", revision: int | None = None) -> AssetMutationContext:
    """Generate a controlled operation context with a unique idempotency key."""
    return AssetMutationContext(actor=actor, operation_id=new_id(), expected_revision=revision)


def create_dataset(db: Database, identity: str = "dataset") -> AssetRef:
    """Persist an isolated generated manifest without touching object storage."""
    item = FileItem(
        id=f"file-{identity}",
        path="fixture.txt",
        filename="fixture.txt",
        size=12,
        sha256=identity,
        modality="text",
    )
    with db.session() as session:
        session.add(DatasetRow(id=identity, name="Generated fixture", files=[item.model_dump()]))
        session.flush()
        session.add(
            VersionRow(
                id=f"version-{identity}",
                dataset_id=identity,
                manifest=[item.model_dump()],
                created_at=NOW.timestamp() - 100,
            )
        )
        session.commit()
    return AssetRef(asset_id=identity)


def create_asset(db: Database, definition: DataAssetDefinition) -> str:
    """Publish one asset through the exact domain mutation functions used by actions."""
    with db.session() as session:
        asset = create_asset_in_session(session, definition, context())
        set_status_in_session(session, asset.id, "published", context())
        session.commit()
        return asset.id


def grant_access(db: Database, asset_id: str, scopes: tuple[str, ...] = ("query",)) -> str:
    """Approve one generated request using the controlled mutation contract."""
    body = AssetApplicationInput.model_validate(
        {
            "asset_id": asset_id,
            "purpose": "Generated analysis",
            "scopes": scopes,
            "expires_at": NOW + timedelta(days=1),
        }
    )
    application = submit_application(db, body, "reader", now=NOW)
    with db.session() as session:
        decided = decide_application_in_session(
            session, application.id, context(), approved=True, now=NOW
        )
        session.commit()
        assert decided.grant_id is not None
        return decided.grant_id


def test_asset_lifecycle_preserves_history_and_idempotency(db: Database) -> None:
    """Retain draft, metadata changes, publication and withdrawal as distinct facts."""
    target = create_dataset(db)
    definition = DataAssetDefinition(target=target, name="Orders", name_en="Orders", owner="Owner")
    operation = context()
    with db.session() as session:
        asset = create_asset_in_session(session, definition, operation)
        assert create_asset_in_session(session, definition, operation) == asset
        updated = update_asset_in_session(
            session,
            asset.id,
            definition.model_copy(update={"description": "Business definition"}),
            context(revision=1),
        )
        published = set_status_in_session(session, asset.id, "published", context(revision=2))
        withdrawn = set_status_in_session(session, asset.id, "withdrawn", context(revision=3))
        session.commit()
    assert [entry.asset.status for entry in asset_history(db, asset.id)] == [
        "draft",
        "draft",
        "published",
        "withdrawn",
    ]
    assert updated.revision == 2
    assert published.revision == 3
    assert withdrawn.revision == 4
    assert get_asset(db, asset.id) == withdrawn
    assert len(list_assets(db)) == 1
    assert search_market(db, AssetMarketQuery()).total == 0
    assert search_market(db, AssetMarketQuery(status=None)).total == 1


def test_asset_changes_reject_stale_revision_retarget_and_missing_resources(db: Database) -> None:
    """Reject stale controlled plans and references outside the local fact store."""
    target = create_dataset(db)
    other = create_dataset(db, "other")
    definition = DataAssetDefinition(target=target, name="Orders", owner="Owner")
    asset_id = create_asset(db, definition)
    with db.session() as session:
        with pytest.raises(ConflictError, match="revision"):
            update_asset_in_session(session, asset_id, definition, context(revision=1))
        with pytest.raises(ValidationError, match="retargeted"):
            update_asset_in_session(
                session, asset_id, definition.model_copy(update={"target": other}), context()
            )
        with pytest.raises(ValidationError, match="target not found"):
            create_asset_in_session(
                session,
                definition.model_copy(update={"target": AssetRef(asset_id="missing")}),
                context(),
            )
        with pytest.raises(ValidationError, match="return to draft"):
            set_status_in_session(session, asset_id, "draft", context())
    with pytest.raises(NotFoundError):
        get_asset(db, "missing")


@pytest.mark.parametrize("classification", ["request", "restricted"])
@pytest.mark.parametrize("state", ["missing", "expired", "revoked", "wrong_scope", "active"])
def test_guard_checks_exact_subject_scope_and_lifetime(
    db: Database,
    classification: str,
    state: str,
) -> None:
    """The shared policy denies all four invalid grant states and permits active grants."""
    target = create_dataset(db)
    asset_id = create_asset(
        db,
        DataAssetDefinition.model_validate(
            {
                "target": target,
                "name": "Protected",
                "owner": "Owner",
                "classification": classification,
            }
        ),
    )
    moment = NOW
    if state != "missing":
        grant_id = grant_access(db, asset_id, ("export",) if state == "wrong_scope" else ("query",))
        if state == "expired":
            moment = NOW + timedelta(days=1)
        if state == "revoked":
            with db.session() as session:
                revoke_grant_in_session(session, grant_id, context(), now=NOW)
                session.commit()
    request = AccessContext(actor="reader", entry="ask", scope="query")
    if state == "active":
        result = require_access(db, (target,), request, now=moment)
        assert len(result) == 1
        assert result[0].grant_id is not None
        with pytest.raises(AuthorizationError):
            require_access(db, (target,), request.model_copy(update={"actor": "other"}), now=moment)
    else:
        with pytest.raises(AuthorizationError, match="apply for access"):
            require_access(db, (target,), request, now=moment)
        assert list_usage(db, AssetUsageQuery(asset_id=asset_id)) == ()


def test_approval_revocation_and_rejection_remain_queryable(db: Database) -> None:
    """A repeated decision replays, but a second distinct decision cannot overwrite it."""
    target = create_dataset(db)
    asset_id = create_asset(db, DataAssetDefinition(target=target, name="Orders", owner="Owner"))
    body = AssetApplicationInput(
        asset_id=asset_id, purpose="Analysis", scopes=("query",), expires_at=NOW + timedelta(days=1)
    )
    application = submit_application(db, body, "reader", now=NOW, operation_id="apply")
    assert submit_application(db, body, "reader", now=NOW, operation_id="apply") == application
    approval = context()
    with db.session() as session:
        decided = decide_application_in_session(
            session, application.id, approval, approved=False, now=NOW
        )
        assert (
            decide_application_in_session(
                session, application.id, approval, approved=False, now=NOW
            )
            == decided
        )
        session.commit()
    with db.session() as session, pytest.raises(ConflictError):
        decide_application_in_session(session, application.id, context(), approved=True, now=NOW)
    assert get_application(db, application.id).status == "rejected"
    assert len(list_applications(db, asset_id, "reader")) == 1
    assert list_applications(db, applicant="other") == ()
    grant_id = grant_access(db, asset_id)
    revoke = context()
    with db.session() as session:
        revoked = revoke_grant_in_session(session, grant_id, revoke, now=NOW)
        assert revoke_grant_in_session(session, grant_id, revoke, now=NOW) == revoked
        session.commit()
    assert get_grant(db, grant_id).revoked_by == "steward"
    assert len(list_grants(db, asset_id, "reader")) == 1
    assert list_grants(db, subject="other") == ()
    assert {event.action for event in control_history(db, asset_id)} == {
        "apply",
        "approved",
        "rejected",
        "revoke",
    }


@pytest.mark.parametrize("table", ["asset_usage", "data_asset_history", "asset_control_events"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_audit_database_constraints_reject_mutation(
    db: Database,
    table: str,
    operation: str,
) -> None:
    """Direct SQL cannot rewrite either use audit or immutable lifecycle history."""
    target = create_dataset(db)
    asset_id = create_asset(db, DataAssetDefinition(target=target, name="Orders", owner="Owner"))
    grant_access(db, asset_id)
    require_access(
        db, (target,), AccessContext(actor="reader", entry="ask", scope="query"), now=NOW
    )
    selected = cast(
        "Table",
        {
            "asset_usage": AssetUsageRow.__table__,
            "data_asset_history": DataAssetHistoryRow.__table__,
            "asset_control_events": AssetControlRow.__table__,
        }[table],
    )
    statement = (
        selected.update().values(id=selected.c.id) if operation == "UPDATE" else selected.delete()
    )
    with pytest.raises(DBAPIError, match="append-only"), db.engine.begin() as connection:
        connection.execute(statement)


def _market_fixture(db: Database) -> tuple[AssetRef, str, str]:
    target = create_dataset(db)
    first = create_asset(
        db,
        DataAssetDefinition(
            target=target,
            name="Orders",
            name_en="Orders",
            owner="Finance",
            tags=("sales",),
            synonyms=("Revenue",),
        ),
    )
    other_target = create_dataset(db, "other")
    other = create_asset(db, DataAssetDefinition(target=other_target, name="Other", owner="Owner"))
    return target, first, other


def test_market_card_measures_quality_lineage_freshness_and_real_usage(db: Database) -> None:
    """Card metrics reflect native facts and documented default/configurable ordering."""
    target, first, other = _market_fixture(db)
    with db.session() as session:
        append_event(
            session,
            LineageEvent(
                idempotency_key="lineage",
                operator="generated",
                inputs=[target],
                outputs=[AssetRef(asset_type="report", asset_id="report")],
                occurred_at=NOW - timedelta(seconds=10),
            ),
        )
        session.commit()
    for actor in ("reader", "reader", "other"):
        require_access(
            db, (target, target), AccessContext(actor=actor, entry="agent", scope="query"), now=NOW
        )
    card = get_asset_card(db, first, now=NOW)
    assert card.quality_score == 100
    assert len(card.quality_trend) == 1
    assert card.usage_count == 3
    assert card.user_count == 2
    assert card.downstream_count == 1
    assert card.downstream[0].asset_id == "report"
    assert card.freshness_seconds == 100
    assert card.standard_coverage is None
    assert card.version_release is None
    assert (
        search_market(db, AssetMarketQuery(search="revenue Finance", tag="sales"), now=NOW)
        .items[0]
        .asset.id
        == first
    )
    assert search_market(db, AssetMarketQuery(search="missing"), now=NOW).total == 0
    assert search_market(db, AssetMarketQuery(), now=NOW).items[0].asset.id == first
    assert search_market(db, AssetMarketQuery(sort="name"), now=NOW).items[0].asset.id == first
    assert (
        search_market(db, AssetMarketQuery(offset=1, limit=1), now=NOW).items[0].asset.id == other
    )
    assert (
        search_market(
            db,
            AssetMarketQuery(),
            AssetRanking(usage_weight=0, users_weight=0, downstream_weight=10),
            now=NOW,
        )
        .items[0]
        .asset.id
        == first
    )
    assert len(list_usage(db, AssetUsageQuery(actor="reader", limit=1))) == 1


def test_draft_or_invalid_applications_never_create_grants(db: Database) -> None:
    """Require an applicant, published asset and strictly future expiry at submission."""
    target = create_dataset(db)
    with db.session() as session:
        asset = create_asset_in_session(
            session, DataAssetDefinition(target=target, name="Draft", owner="Owner"), context()
        )
        session.commit()
    body = AssetApplicationInput(
        asset_id=asset.id, purpose="Analysis", scopes=("query",), expires_at=NOW + timedelta(days=1)
    )
    with pytest.raises(ValidationError, match="published"):
        submit_application(db, body, "reader", now=NOW)
    with pytest.raises(ValidationError, match="applicant"):
        submit_application(db, body, " ", now=NOW)
    with pytest.raises(ValidationError, match="future"):
        submit_application(db, body, "reader", now=NOW + timedelta(days=2))
    with pytest.raises(NotFoundError):
        get_application(db, "missing")
    with pytest.raises(NotFoundError):
        get_grant(db, "missing")


def test_idempotency_keys_bind_actor_action_and_exact_request(db: Database) -> None:
    """Reusing a successful operation for different content cannot silently return another fact."""
    target = create_dataset(db)
    definition = DataAssetDefinition(target=target, name="Orders", owner="Owner")
    operation = context()
    with db.session() as session:
        asset = create_asset_in_session(session, definition, operation)
        with pytest.raises(ConflictError, match="another actor"):
            create_asset_in_session(
                session, definition, operation.model_copy(update={"actor": "other"})
            )
        with pytest.raises(ConflictError, match="another definition"):
            create_asset_in_session(
                session, definition.model_copy(update={"name": "Changed"}), operation
            )
        with pytest.raises(ConflictError, match="another actor or action"):
            set_status_in_session(session, asset.id, "published", operation)
        set_status_in_session(session, asset.id, "published", context())
        session.commit()
    body = AssetApplicationInput(
        asset_id=asset.id, purpose="Analysis", scopes=("query",), expires_at=NOW + timedelta(days=1)
    )
    submit_application(db, body, "reader", now=NOW, operation_id="bound-application")
    with pytest.raises(ConflictError, match="another request"):
        submit_application(
            db,
            body.model_copy(update={"purpose": "Changed"}),
            "reader",
            now=NOW,
            operation_id="bound-application",
        )
    with pytest.raises(ConflictError, match="another request"):
        submit_application(db, body, "other", now=NOW, operation_id="bound-application")


def test_version_card_preserves_frozen_quality_and_freshness(db: Database) -> None:
    """A later bad version changes current quality without rewriting a pinned good version card."""
    target = create_dataset(db)
    pinned = create_asset(
        db,
        DataAssetDefinition(
            target=target.model_copy(update={"version": "version-dataset"}),
            name="Pinned",
            owner="Owner",
        ),
    )
    current = create_asset(db, DataAssetDefinition(target=target, name="Current", owner="Owner"))
    file = FileItem(
        id="bad", path="fixture.txt", filename="fixture.txt", size=0, sha256="bad", modality="text"
    )
    with db.session() as session:
        session.add(
            VersionRow(
                id="bad-version",
                dataset_id="dataset",
                manifest=[file.model_dump()],
                created_at=NOW.timestamp() - 10,
            )
        )
        session.commit()
    old = get_asset_card(db, pinned, now=NOW)
    latest = get_asset_card(db, current, now=NOW)
    assert old.quality_score == 100
    assert old.freshness_seconds == 100
    assert len(old.quality_trend) == 1
    assert latest.quality_score is not None
    assert latest.quality_score < 100
    assert latest.freshness_seconds == 10
    assert len(latest.quality_trend) == 2


def test_asset_documentation_receipt_does_not_refresh_underlying_data(db: Database) -> None:
    """Publishing documentation does not make an old dataset fresh or add data dependencies."""
    target = create_dataset(db)
    asset_id = create_asset(db, DataAssetDefinition(target=target, name="Orders", owner="Owner"))
    with db.session() as session:
        append_event(
            session,
            LineageEvent(
                idempotency_key="metadata-receipt",
                operator="publish_data_asset",
                inputs=[target],
                outputs=[target, AssetRef(asset_type="action_run", asset_id="metadata-action")],
                occurred_at=NOW,
            ),
        )
        session.commit()
    card = get_asset_card(db, asset_id, now=NOW)
    assert card.freshness_seconds == 100
    assert card.downstream_count == 0
