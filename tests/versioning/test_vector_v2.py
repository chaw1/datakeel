# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real v1/v2/v3 campaigns, exact typed export equivalence and additive fact preservation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine

from datakeel.core.errors import ValidationError
from datakeel.core.settings import Settings
from datakeel.storage.database import Database
from datakeel.versioning import initialize, require_current
from datakeel.versioning.campaign_v2 import status as status_v2
from datakeel.versioning.campaign_v2 import upgrade as upgrade_v2
from datakeel.versioning.campaign_v3 import status, upgrade
from datakeel.versioning.facts_v2 import snapshot, validate_preserved
from datakeel.versioning.inspect import facts_digest, normalize_sql, schema_objects
from datakeel.versioning.lock import require_unisolated
from datakeel.versioning.recovery import restore_package, verify_package
from datakeel.versioning.registry import registry
from datakeel.versioning.v1 import definition as v1_definition
from tests.versioning.test_baselines import legacy

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

    from datakeel.versioning.facts_v2 import TableFacts
    from datakeel.versioning.models import SchemaObject

V1_CHECKSUM = "2afd055e998abf651ff2db20124db6240f5e881b89a0067e931b9e3c2d1ec12a"


def _seed(database: Database, home: Path, *, vector: bool = False) -> None:
    (home / "objects").mkdir(parents=True, exist_ok=True)
    (home / "objects" / "fact").write_bytes(b"\x00\xffobject fact\n")
    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO datasets VALUES ('d','original',1,?, '{}',NULL,'{}','{}')",
            (json.dumps([{"object_key": "fact"}]),),
        )
        connection.exec_driver_sql(
            "INSERT INTO tasks (id,dataset_id,idempotency_key,state,queue,created_at,total_shards) "
            "VALUES ('t','d','key','RUNNING','cpu',123,1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO task_shards "
            "(id,task_id,ordinal,state,inputs,outputs,lease_owner,heartbeat_at,attempts) "
            "VALUES ('s','t',0,'RUNNING','[]','[]','owner',124,2)"
        )
        connection.exec_driver_sql("INSERT INTO production_projects VALUES ('p','d','{}')")
        connection.exec_driver_sql("INSERT INTO production_packages VALUES ('k','p','{}')")
        connection.exec_driver_sql(
            "INSERT INTO production_tasks "
            "(id,project_id,package_id,sample_id,state,round,priority) "
            "VALUES ('pt','p','k','s1','pending',0,0)"
        )
        if vector:
            connection.exec_driver_sql("UPDATE task_shards SET lease_expires_at=456")
            connection.exec_driver_sql("INSERT INTO vector_cache VALUES ('k','event','{}')")
            connection.exec_driver_sql("INSERT INTO vector_fake_accounts VALUES ('p',3,4)")
            connection.exec_driver_sql(
                "INSERT INTO vector_fake_attempts VALUES "
                "('a','p','t','n','asset','RESERVED',6,7,'{}')"
            )


def test_frozen_latest_matches_real_typed_sqlite_export(unmigrated_db: Database) -> None:
    """The complete target comes from real SQLite, including every constraint/index/trigger."""
    legacy(unmigrated_db)
    with unmigrated_db.engine.connect() as connection:
        actual = schema_objects(connection)
    expected = tuple(
        item.model_copy(update={"sql": normalize_sql(item.sql)})
        for item in registry()[-1].target.objects
    )
    assert actual == expected, "W4-v3-real-typed-export"
    assert sum(item.kind == "table" for item in actual) == 102
    assert v1_definition().checksum == V1_CHECKSUM
    assert len(v1_definition().checksum_sources) == 19


def test_frozen_v2_recognizes_real_campaign_prefix(unmigrated_db: Database, tmp_path: Path) -> None:
    """The frozen v2 baseline still recognizes its real campaign result after ORM evolution."""
    path = legacy(unmigrated_db, version=2)
    report = status(path, tmp_path, registry())
    assert (report.state, report.baseline, report.pending) == (
        "unversioned",
        "sqlite-b2",
        (1, 2, 3),
    )


def test_v2_runner_stamps_unversioned_b2_prefix(unmigrated_db: Database, tmp_path: Path) -> None:
    """The frozen v2 runner still stamps its own complete baseline without the v3 increment."""
    path = legacy(unmigrated_db, version=2)
    result = upgrade_v2(path, Settings(home=tmp_path), registry()[:2])
    assert (result.exit_code, result.state, result.applied) == (0, "current", (1, 2))
    assert status_v2(path, tmp_path, registry()[:2]).state == "current"


@pytest.mark.parametrize(
    "source", ["empty", "legacy99", "v1", "legacy102", "v2", "legacy103", "v3"]
)
def test_campaign_preserves_facts_objects_restore_and_repeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    """All supported sources reach 102, preserve old facts/objects and keep exact recovery bytes."""
    home, path = tmp_path / "home", tmp_path / "database.sqlite"
    monkeypatch.setenv("DATAKEEL_HOME", str(home))
    database = Database(f"sqlite:///{path}")
    settings, versions = Settings(home=home), registry()
    if source in {"legacy99", "v1"}:
        legacy(database, version=1)
    elif source in {"legacy102", "v2"}:
        legacy(database, version=2)
    elif source in {"legacy103", "v3"}:
        legacy(database)
    if source != "empty":
        _seed(database, home, vector=source not in {"legacy99", "v1"})
    if source in {"v1", "v2", "v3"}:
        assert upgrade(path, settings, versions, to=int(source[1])).exit_code == 0
    if source != "empty":
        with database.engine.connect() as connection:
            before, objects, digest = (
                snapshot(connection),
                schema_objects(connection),
                facts_digest(connection),
            )
        if source != "v3":
            with pytest.raises(ValidationError):
                initialize(database)
            with pytest.raises(ValidationError):
                require_current(database)
    else:
        before, objects, digest = (), (), ""
    result = upgrade(path, settings, versions)
    assert (result.exit_code, result.state, result.version) == (0, "current", 3), "W4-v3-upgrade"
    assert (
        result.applied
        == {
            "empty": (1, 2, 3),
            "legacy99": (1, 2, 3),
            "v1": (2, 3),
            "legacy102": (1, 2, 3),
            "v2": (3,),
            "legacy103": (1, 2, 3),
            "v3": (),
        }[source]
    )
    _assert_target(database, source, before, objects, digest)
    if result.backup_manifest and source != "empty":
        _assert_restore(Path(result.backup_manifest), tmp_path / "restore", objects, digest, home)
    _assert_repeat(database, settings)
    database.engine.dispose()


def _assert_target(
    database: Database,
    source: str,
    before: tuple[TableFacts, ...],
    objects: tuple[SchemaObject, ...],
    digest: str,
) -> None:
    with database.engine.connect() as connection:
        assert len(inspect(connection).get_table_names()) == 103
        if before:
            validate_preserved(connection, before)
        if source in {"legacy103", "v3"}:
            assert schema_objects(connection) == objects, "W4-v3-stamp-no-business-ddl"
            assert facts_digest(connection) == digest, "W4-v3-stamp-facts"
        if source in {"legacy99", "v1"}:
            assert connection.exec_driver_sql("SELECT lease_expires_at FROM task_shards").one() == (
                None,
            )
        if source not in {"empty", "legacy103", "v3"}:
            ranks = connection.exec_driver_sql(
                "SELECT DISTINCT display_rank FROM production_tasks"
            ).fetchall()
            assert ranks == [(None,)], "W4-v3-additive-rank-stays-null"


def _assert_restore(
    manifest_path: Path,
    destination: Path,
    objects: tuple[SchemaObject, ...],
    digest: str,
    home: Path,
) -> None:
    assert verify_package(manifest_path).source_facts == digest
    restored = restore_package(manifest_path, destination)
    copy = Database(f"sqlite:///{restored}", read_only=True)
    with copy.engine.connect() as connection:
        assert schema_objects(connection) == objects
        assert facts_digest(connection) == digest
    assert (restored.parent / "objects" / "fact").read_bytes() == (
        home / "objects" / "fact"
    ).read_bytes()
    with pytest.raises(ValidationError, match="isolat"):
        require_unisolated(restored.parent, restored)
    copy.engine.dispose()


def _assert_repeat(database: Database, settings: Settings) -> None:
    backups = tuple(sorted((settings.home / "backups").rglob("*")))
    with database.engine.connect() as connection:
        facts = snapshot(connection)
        ledger = connection.exec_driver_sql("SELECT * FROM datakeel_schema_versions").fetchall()
    for _ in range(2):
        initialize(database)
        require_current(database)
        repeat = upgrade(Path(str(database.engine.url.database)), settings, registry())
        assert repeat.applied == ()
        assert repeat.backup_manifest is None
    assert tuple(sorted((settings.home / "backups").rglob("*"))) == backups
    with database.engine.connect() as connection:
        assert snapshot(connection) == facts
        assert (
            connection.exec_driver_sql("SELECT * FROM datakeel_schema_versions").fetchall()
            == ledger
        )


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:"])
def test_memory_initialization_applies_every_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    """Both memory spellings initialize and restart with every registered version."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path))
    database = Database(url)
    initialize(database)
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version FROM datakeel_schema_versions"
        ).fetchall() == [(1,), (2,), (3,)], "W4-v3-memory-all-versions"
        assert len(inspect(connection).get_table_names()) == 103
    initialize(database)
    require_current(database)
    database.engine.dispose()


@pytest.mark.parametrize(
    "sql",
    [
        "ALTER TABLE vector_cache ADD COLUMN extra TEXT",
        "DROP INDEX ix_vector_fake_attempts_plan_id",
        "DROP TRIGGER lineage_no_update",
        "DROP TABLE vector_cache",
        "ALTER TABLE task_shards ADD COLUMN extra FLOAT",
        "ALTER TABLE production_tasks ADD COLUMN extra INTEGER",
        "DROP INDEX production_task_claim_order",
    ],
)
def test_latest_unversioned_rejects_partial_or_extra_schema(
    unmigrated_db: Database, tmp_path: Path, sql: str
) -> None:
    """The newest legacy class is still an exact full-object baseline."""
    path = legacy(unmigrated_db)
    with unmigrated_db.engine.begin() as connection:
        connection.exec_driver_sql(sql)
    result = upgrade(path, Settings(home=tmp_path), registry())
    assert result.exit_code == 3, "W4-v3-exact-recognition"
    assert not (tmp_path / "backups").exists()


def test_latest_stamp_never_calls_forward(unmigrated_db: Database, tmp_path: Path) -> None:
    """Explicit latest-baseline stamping does not replay any old or new DDL."""
    path = legacy(unmigrated_db)

    def forbidden(_connection: Connection) -> None:
        pytest.fail("W4-v3-stamp-forward-replayed")

    versions = tuple(v.model_copy(update={"forward": forbidden}) for v in registry())
    assert status(path, tmp_path, versions).baseline == "sqlite-b3", "W4-v3-latest-recognized"
    assert upgrade(path, Settings(home=tmp_path), versions, to=1).exit_code == 2
    result = upgrade(path, Settings(home=tmp_path), versions)
    assert result.exit_code == 0, "W4-v3-latest-stamped"
    assert result.applied == (1, 2, 3)


@pytest.mark.parametrize("fault", ["facts", "lease-value", "ddl", "ledger"])
def test_v2_failure_rolls_back_ddl_facts_and_ledger(
    unmigrated_db: Database, tmp_path: Path, fault: str
) -> None:
    """Actual v2 DDL, facts, postconditions and ledger insertion share one rollback boundary."""
    path = legacy(unmigrated_db, version=1)
    settings, versions = Settings(home=tmp_path / "home"), registry()
    _seed(unmigrated_db, settings.home)
    assert upgrade_v2(path, settings, versions, to=1).exit_code == 0
    with unmigrated_db.engine.connect() as connection:
        old_objects, old_facts = schema_objects(connection), snapshot(connection)
    original = versions[1].forward

    def forward(connection: Connection) -> None:
        original(connection)
        if fault == "facts":
            connection.exec_driver_sql("UPDATE datasets SET name='changed'")
        elif fault == "lease-value":
            connection.exec_driver_sql("UPDATE task_shards SET lease_expires_at=1")
        elif fault == "ddl":
            connection.exec_driver_sql("DROP INDEX ix_vector_fake_attempts_plan_id")

    def after(
        _c: object, _cur: object, sql: str, params: object, _ctx: object, _many: object
    ) -> None:
        if (
            fault == "ledger"
            and sql.startswith("INSERT INTO datakeel_schema_versions")
            and params[0] == 2
        ):
            msg = "fail after actual v2 ledger write"
            raise RuntimeError(msg)

    event.listen(Engine, "after_cursor_execute", after)
    try:
        result = upgrade_v2(
            path, settings, (versions[0], versions[1].model_copy(update={"forward": forward}))
        )
    finally:
        event.remove(Engine, "after_cursor_execute", after)
    assert result.exit_code == 5, "W4-v2-atomic-failure"
    assert result.version == 1
    assert result.applied == ()
    with unmigrated_db.engine.connect() as connection:
        assert schema_objects(connection) == old_objects, "W4-v2-ddl-rolled-back"
        assert snapshot(connection) == old_facts, "W4-v2-facts-rolled-back"
        assert connection.exec_driver_sql(
            "SELECT version FROM datakeel_schema_versions"
        ).fetchall() == [(1,)]
    resumed = upgrade(path, settings, versions)
    assert resumed.exit_code == 0
    assert resumed.applied == (2, 3)
    # The failed campaign bound a two-version checksum prefix; the full registry is a
    # different campaign identity and earns its own recovery point.
    assert len(list((settings.home / "backups").iterdir())) == 2


@pytest.mark.parametrize("fault", ["facts", "rank-value", "ddl", "ledger"])
def test_v3_failure_rolls_back_ddl_facts_and_ledger(
    unmigrated_db: Database, tmp_path: Path, fault: str
) -> None:
    """Actual v3 DDL, rank backfill guards and ledger insertion share one rollback boundary."""
    path = legacy(unmigrated_db, version=1)
    settings, versions = Settings(home=tmp_path / "home"), registry()
    _seed(unmigrated_db, settings.home)
    assert upgrade(path, settings, versions, to=2).exit_code == 0
    with unmigrated_db.engine.connect() as connection:
        old_objects, old_facts = schema_objects(connection), snapshot(connection)
    original = versions[2].forward

    def forward(connection: Connection) -> None:
        original(connection)
        if fault == "facts":
            connection.exec_driver_sql("UPDATE datasets SET name='changed'")
        elif fault == "rank-value":
            connection.exec_driver_sql("UPDATE production_tasks SET display_rank=1")
        elif fault == "ddl":
            connection.exec_driver_sql("DROP INDEX production_task_claim_order")

    def after(
        _c: object, _cur: object, sql: str, params: object, _ctx: object, _many: object
    ) -> None:
        if (
            fault == "ledger"
            and sql.startswith("INSERT INTO datakeel_schema_versions")
            and params[0] == 3
        ):
            msg = "fail after actual v3 ledger write"
            raise RuntimeError(msg)

    event.listen(Engine, "after_cursor_execute", after)
    try:
        result = upgrade(
            path, settings, (*versions[:2], versions[2].model_copy(update={"forward": forward}))
        )
    finally:
        event.remove(Engine, "after_cursor_execute", after)
    assert result.exit_code == 5, "W4-v3-atomic-failure"
    assert result.version == 2
    assert result.applied == ()
    with unmigrated_db.engine.connect() as connection:
        assert schema_objects(connection) == old_objects, "W4-v3-ddl-rolled-back"
        assert snapshot(connection) == old_facts, "W4-v3-facts-rolled-back"
        assert connection.exec_driver_sql(
            "SELECT version FROM datakeel_schema_versions"
        ).fetchall() == [(1,), (2,)]
    resumed = upgrade(path, settings, versions)
    assert resumed.exit_code == 0
    assert resumed.applied == (3,)
    assert len(list((settings.home / "backups").iterdir())) == 1


@pytest.mark.parametrize(("to", "baseline"), [(2, "sqlite-b2"), (3, "sqlite-b3")])
def test_altered_layout_without_ledger_is_a_complete_baseline(
    unmigrated_db: Database, tmp_path: Path, to: int, baseline: str
) -> None:
    """The exact ALTER layout remains recognizable after removing only its synthetic ledger."""
    path = legacy(unmigrated_db, version=1)
    settings = Settings(home=tmp_path / "home")
    assert upgrade(path, settings, registry(), to=to).exit_code == 0
    with unmigrated_db.engine.begin() as connection:
        connection.exec_driver_sql("DROP TRIGGER datakeel_ledger_no_update")
        connection.exec_driver_sql("DROP TRIGGER datakeel_ledger_no_delete")
        connection.exec_driver_sql("DROP TABLE datakeel_schema_versions")
    assert status(path, settings.home, registry()).baseline == baseline
    assert upgrade(path, Settings(home=tmp_path / "new-campaign"), registry()).exit_code == 0
