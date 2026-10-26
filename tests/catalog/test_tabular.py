# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Local file profiles use the versioned catalog and its existing action policy."""

from pathlib import Path

import pytest
from sqlalchemy import select

from datakeel.actions.models import ActionContext, ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.catalog.importers.tabular import reflect_files
from datakeel.catalog.service import prepare_import
from datakeel.core.catalog_models import CatalogImportRequest, ColumnProperties, TableProperties
from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.operators.table.models import ColumnProfile
from datakeel.storage.action_rows import ActionAuditRow
from datakeel.storage.catalog_projection import rebuild_catalog
from datakeel.storage.catalog_queries import get_object, read_objects
from datakeel.storage.database import Database
from datakeel.storage.events import all_events


@pytest.fixture
def file_request(tmp_path: Path) -> CatalogImportRequest:
    """Generate contacts and missing measurements without using external data."""
    path = tmp_path / "sensors.csv"
    path.write_text(
        "record_id,temperature,phone\n"
        "1,20,+1-202-555-0101\n"
        "2,,+1-202-555-0102\n"
        "3,25,+1-202-555-0103\n",
        encoding="utf-8",
    )
    return CatalogImportRequest(source_id="sensors", name="Generated sensors", files=(str(path),))


def _params(request: CatalogImportRequest) -> JsonDocument:
    return JsonDocument({"request": request.model_dump(mode="json")})


def test_file_profile_when_prepared_preserves_inference_without_promoting_keys(
    file_request: CatalogImportRequest,
) -> None:
    """Retain column findings as candidates, not confirmed source constraints."""
    snapshot, report = prepare_import(file_request)
    assert report.object_count == 5
    table = next(item for item in snapshot.objects if item.asset_ref.asset_type == "table")
    properties = TableProperties.model_validate(table.properties.root)
    assert properties.table_profile is not None
    assert properties.table_profile["row_count"] == 3
    assert properties.primary_key == ()
    columns = {
        item.name: ColumnProperties.model_validate(item.properties.root)
        for item in snapshot.objects
        if item.asset_ref.asset_type == "column"
    }
    assert columns["record_id"].profile is not None
    assert columns["record_id"].profile["primary_key_candidate"] is True
    assert not columns["record_id"].primary_key
    assert columns["temperature"].nullable
    phone = columns["phone"].profile
    assert phone is not None
    assert phone["pii_kinds"] == ["phone"]
    assert "+1-202-555-0101" not in snapshot.model_dump_json()
    assert len(snapshot.links) == 4


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"connection_url": "sqlite:///:memory:"}, "either files"),
        ({"sql_files": ("unused.sql",)}, "does not accept SQL"),
        ({"schemas": ("main",)}, "schema selection"),
        ({"files": ()}, "requires files"),
    ],
)
def test_file_profile_when_source_options_conflict_rejects_before_reading(
    file_request: CatalogImportRequest, updates: dict[str, object], message: str
) -> None:
    """Keep ambiguous adapters and unsupported SQL paths explicit."""
    with pytest.raises(ValidationError, match=message):
        prepare_import(file_request.model_copy(update=updates))


def test_file_adapter_when_called_without_files_rejects_empty_source(
    file_request: CatalogImportRequest,
) -> None:
    """Direct adapter consumers cannot accidentally publish an empty source."""
    with pytest.raises(ValidationError, match="requires files"):
        reflect_files(file_request.model_copy(update={"files": ()}))


def test_file_adapter_when_stems_collide_rejects_ambiguous_table_identities(
    file_request: CatalogImportRequest,
) -> None:
    """Equal stems across folders or formats cannot overwrite each other's profiles."""
    with pytest.raises(ValidationError, match="unique table names"):
        reflect_files(file_request.model_copy(update={"files": ("one.csv", "one.parquet")}))


def test_file_profile_when_imported_uses_frozen_snapshot_audit_and_idempotency(
    db: Database,
    file_request: CatalogImportRequest,
) -> None:
    """Execution publishes only the reviewed profile even after local source bytes change."""
    plan = prepare_action(db, "import_catalog", _params(file_request))
    assert read_objects(db).total == 0
    assert plan.reversible
    assert not plan.requires_approval
    Path(file_request.files[0]).write_text(
        "record_id,temperature,phone\n1,999,\n", encoding="utf-8"
    )
    request = ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    run = execute_plan(db, plan.id, request)
    assert run.status == "SUCCEEDED"
    assert execute_plan(db, plan.id, request).id == run.id
    table = get_object(db, "sensors/main/sensors")
    profile = table.properties["table_profile"]
    assert isinstance(profile, dict)
    assert profile["row_count"] == 3
    assert rebuild_catalog(db).matches
    with db.session() as session:
        events = all_events(session)
        assert sum(event.operator == "CATALOG_IMPORT" for event in events) == 1
        audits = list(session.scalars(select(ActionAuditRow)))
        assert {(item.phase, item.status) for item in audits} == {
            ("PREPARE", "SUCCEEDED"),
            ("EXECUTE", "SUCCEEDED"),
        }
    refreshed = prepare_action(db, "import_catalog", _params(file_request))
    execute_plan(db, refreshed.id, ExecuteRequest(plan_digest=refreshed.plan_digest))
    updated = get_object(db, "sensors/main/sensors")
    assert updated.revision == 2
    updated_profile = updated.properties["table_profile"]
    assert isinstance(updated_profile, dict)
    assert updated_profile["row_count"] == 1


def test_file_profile_when_reimported_unchanged_does_not_append_events(
    db: Database,
    file_request: CatalogImportRequest,
) -> None:
    """Equivalent fresh plans do not invent catalog versions or lineage receipts."""
    for _ in range(2):
        plan = prepare_action(db, "import_catalog", _params(file_request))
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    with db.session() as session:
        assert len(all_events(session)) == 2
    assert get_object(db, "sensors/main/sensors").revision == 1


def test_file_profile_when_scope_denied_does_not_write_catalog(
    db: Database,
    file_request: CatalogImportRequest,
) -> None:
    """The existing catalog write scope also controls inferred metadata."""
    with pytest.raises(AuthorizationError, match="Missing action scope"):
        prepare_action(
            db,
            "import_catalog",
            _params(file_request),
            ActionContext(scopes=["datasets:write"]),
        )
    assert read_objects(db).total == 0


def test_file_profile_when_only_values_change_versions_distribution_and_column_metadata(
    db: Database,
    file_request: CatalogImportRequest,
) -> None:
    """A stable schema does not hide changes to profile statistics and findings."""
    for temperature in (25, 99):
        Path(file_request.files[0]).write_text(
            "record_id,temperature,phone\n"
            "1,20,+1-202-555-0101\n"
            "2,,+1-202-555-0102\n"
            f"3,{temperature},+1-202-555-0103\n",
            encoding="utf-8",
        )
        plan = prepare_action(db, "import_catalog", _params(file_request))
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    table = get_object(db, "sensors/main/sensors")
    column = get_object(db, "sensors/main/sensors/temperature")
    assert table.revision == 2
    assert column.revision == 2
    properties = ColumnProperties.model_validate(column.properties.root)
    assert properties.profile is not None
    numeric = ColumnProfile.model_validate(properties.profile.root).distribution.numeric
    assert numeric is not None
    assert numeric.maximum == 99
    assert rebuild_catalog(db).matches


def test_file_profile_when_catalog_changes_invalidates_stale_plan(
    db: Database,
    file_request: CatalogImportRequest,
) -> None:
    """An intervening import cannot be overwritten by an earlier prepared profile."""
    stale = prepare_action(db, "import_catalog", _params(file_request))
    current = prepare_action(db, "import_catalog", _params(file_request))
    execute_plan(db, current.id, ExecuteRequest(plan_digest=current.plan_digest))
    with pytest.raises(ConflictError, match="target state changed"):
        execute_plan(db, stale.id, ExecuteRequest(plan_digest=stale.plan_digest))


def test_file_profile_when_files_reordered_preserves_canonical_snapshot(
    file_request: CatalogImportRequest,
    tmp_path: Path,
) -> None:
    """Explicit containment and escaped identities are independent of input ordering."""
    second = tmp_path / "measurements %.tsv"
    second.write_text("reading\tstate\n1\ton\n", encoding="utf-8")
    request = file_request.model_copy(update={"files": (*file_request.files, str(second))})
    snapshot, _ = prepare_import(request)
    reversed_snapshot, _ = prepare_import(request.model_copy(update={"files": request.files[::-1]}))
    assert snapshot == reversed_snapshot
    assert any(
        item.asset_ref.asset_id == "sensors/main/measurements%20%25/reading"
        for item in snapshot.objects
    )


def test_file_profile_when_related_files_preserves_foreign_key_candidates(
    file_request: CatalogImportRequest,
    tmp_path: Path,
) -> None:
    """Cross-file inclusion remains a candidate in the frozen table profile."""
    children = tmp_path / "readings.csv"
    children.write_text("record_id,temperature\n1,20\n1,21\n2,22\n", encoding="utf-8")
    request = file_request.model_copy(update={"files": (*file_request.files, str(children))})
    snapshot, _ = prepare_import(request)
    table = next(item for item in snapshot.objects if item.name == "readings")
    profile = table.properties["table_profile"]
    assert isinstance(profile, dict)
    assert profile["foreign_keys"]
    assert not any(link.kind == "references" for link in snapshot.links)


def test_profile_property_defaults_preserve_existing_catalog_serialization() -> None:
    """Absent optional profiles do not change older reflection snapshot fingerprints."""
    assert "table_profile" not in TableProperties().model_dump(mode="json")
    assert "profile" not in ColumnProperties(data_type="INTEGER", ordinal=0).model_dump(mode="json")
