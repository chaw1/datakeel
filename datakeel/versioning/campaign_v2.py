# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Serialized, resumable SQLite upgrade campaigns, with per-version atomic commits."""

from __future__ import annotations

import hashlib
import itertools
import sqlite3
from contextlib import contextmanager
from typing import TYPE_CHECKING

from pydantic import ValidationError as ModelError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.models import utcnow
from datakeel.versioning.facts_v2 import snapshot, validate_preserved
from datakeel.versioning.inspect_v2 import (
    LEDGER_SQL,
    LEDGER_TRIGGERS,
    facts_digest,
    inspect_database,
    schema_objects,
    validate_baseline,
)
from datakeel.versioning.location import readonly_engine
from datakeel.versioning.lock import maintenance_lock, require_unisolated
from datakeel.versioning.models import DatabaseStatus, MigrationDefinition
from datakeel.versioning.recovery import create_package, verify_package

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from sqlalchemy.engine import Connection

    from datakeel.core.settings import Settings


def validate_registry(versions: tuple[MigrationDefinition, ...]) -> None:
    """Reject missing, duplicate or unordered definitions before acquiring a write connection."""
    if not versions or tuple(v.version for v in versions) != tuple(range(1, len(versions) + 1)):
        msg = "Invalid version registry order"
        raise ValidationError(msg)
    for previous, current in itertools.pairwise(versions):
        if current.source != previous.target.id:
            msg = "Invalid registry baseline chain"
            raise ValidationError(msg)


def status(
    path: Path, home: Path, versions: tuple[MigrationDefinition, ...], *, reader: int = 1
) -> DatabaseStatus:
    """Inspect with mode=ro and no generic Database/settings initializer or schema writes."""
    try:
        validate_registry(versions)
        require_unisolated(home, path)
    except ValidationError as error:
        isolated = "Recovery isolation" in str(error)
        return DatabaseStatus(
            state="isolated" if isolated else "invalid",
            error=str(error),
            exit_code=6 if isolated else 3,
        )
    if not path.exists():
        return DatabaseStatus(state="missing", pending=tuple(v.version for v in versions))
    engine = readonly_engine(path)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            return inspect_database(connection, versions, reader=reader)
    except (SQLAlchemyError, ValidationError, ValueError) as error:
        return DatabaseStatus(state="invalid", error=str(error), exit_code=3)
    finally:
        engine.dispose()


@contextmanager
def _handler_guard(connection: Connection) -> Generator[None]:
    # Deny transaction control/attachment/nontransactional pragmas while untrusted forward
    # code owns the connection. The runner alone may commit or roll back.
    raw = connection.connection.driver_connection
    if not isinstance(raw, sqlite3.Connection):
        msg = "Only SQLite is supported by this campaign"
        raise ValidationError(msg)
    denied = {
        sqlite3.SQLITE_TRANSACTION,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_PRAGMA,
        sqlite3.SQLITE_SAVEPOINT,
    }
    raw.set_authorizer(
        lambda action, _a, _b, _db, _trigger: (
            sqlite3.SQLITE_DENY if action in denied else sqlite3.SQLITE_OK
        )
    )
    try:
        yield
    finally:
        raw.set_authorizer(None)


def apply_version(connection: Connection, definition: MigrationDefinition, campaign: str) -> None:
    """Commit one complete forward version or roll back every DDL, data and ledger change."""
    connection.exec_driver_sql("BEGIN IMMEDIATE")
    try:
        existed = bool(schema_objects(connection))
        before = snapshot(connection)
        with _handler_guard(connection):
            definition.forward(connection)
        validate_baseline(connection, definition.target)
        after = facts_digest(connection)
        if existed and definition.preserve_facts:
            validate_preserved(connection, before)
        _record(connection, definition, campaign, after)
        connection.commit()
    except BaseException as error:
        connection.rollback()
        if isinstance(error, Exception):
            msg = f"Version {definition.version} failed ({type(error).__name__})"
            raise ExecutionError(msg) from error
        raise


def _record(
    connection: Connection, definition: MigrationDefinition, campaign: str, after: str
) -> None:
    if not schema_objects(connection, system=True):
        connection.exec_driver_sql(LEDGER_SQL)
        for sql in LEDGER_TRIGGERS:
            connection.exec_driver_sql(sql)
    connection.exec_driver_sql(
        "INSERT INTO datakeel_schema_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            definition.version,
            definition.checksum,
            definition.target.id,
            definition.minimum_reader,
            utcnow().isoformat(),
            campaign,
            after,
        ),
    )


def stamp_baseline(
    connection: Connection, definitions: tuple[MigrationDefinition, ...], campaign: str
) -> None:
    """Stamp a recognized complete baseline atomically without replaying any forward handler."""
    connection.exec_driver_sql("BEGIN IMMEDIATE")
    try:
        validate_baseline(connection, definitions[-1].target)
        before = facts_digest(connection)
        for definition in definitions:
            _record(connection, definition, campaign, before)
        validate_baseline(connection, definitions[-1].target)
        if facts_digest(connection) != before:
            msg = "Unauthorized business fact changes while stamping"
            raise ValidationError(msg)  # noqa: TRY301  # Atomic stamp rollback.
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def _identity(path: Path) -> str:
    info = path.stat()
    return hashlib.sha256(f"{path.resolve()}:{info.st_dev}:{info.st_ino}".encode()).hexdigest()


def _backup(
    path: Path,
    settings: Settings,
    source: DatabaseStatus,
    versions: tuple[MigrationDefinition, ...],
    supplied: Path | None,
) -> Path:
    identity = _identity(path)
    checksums = tuple(v.checksum for v in versions)
    name = hashlib.sha256((identity + "".join(checksums)).encode()).hexdigest()
    destination = settings.home.resolve() / "backups" / name
    if supplied is not None or destination.exists():
        manifest_path = supplied or destination / "manifest.json"
        manifest = verify_package(manifest_path)
        if manifest.source_identity != identity or manifest.target_checksums != checksums:
            msg = "Recovery package belongs to a different source or campaign"
            raise ValidationError(msg)
        engine = readonly_engine(path)
        try:
            with engine.connect() as connection:
                digest = facts_digest(connection)
                expected = manifest.source_facts
                if source.version > manifest.source.version:
                    row = connection.exec_driver_sql(
                        "SELECT campaign, facts FROM datakeel_schema_versions WHERE version=?",
                        (source.version,),
                    ).one()
                    if row[0] != manifest.campaign:
                        msg = "Prefix belongs to a different campaign"
                        raise ValidationError(msg)
                    expected = row[1]
                if digest != expected:
                    msg = "Campaign source facts changed"
                    raise ValidationError(msg)
        finally:
            engine.dispose()
        return manifest_path
    return create_package(path, destination, settings, source, checksums, identity)


def upgrade(
    path: Path,
    settings: Settings,
    versions: tuple[MigrationDefinition, ...],
    *,
    to: int | None = None,
    manifest: Path | None = None,
) -> DatabaseStatus:
    """Hold maintenance exclusion through identification, backup, all commits and rechecks."""
    target = len(versions) if to is None else to
    if target not in {v.version for v in versions}:
        return DatabaseStatus(state="invalid", error="Unknown target version", exit_code=2)
    with maintenance_lock(path.resolve()):
        return _upgrade_locked(path.resolve(), settings, versions, target, manifest)


def _upgrade_locked(
    path: Path,
    settings: Settings,
    versions: tuple[MigrationDefinition, ...],
    target: int,
    manifest: Path | None,
) -> DatabaseStatus:
    source = status(path, settings.home, versions)
    if source.exit_code:
        return source
    baseline_version = next((v.version for v in versions if v.target.id == source.baseline), 0)
    if source.version > target or (source.state == "unversioned" and baseline_version > target):
        return source.model_copy(update={"error": "Downgrade is not supported", "exit_code": 2})
    pending = tuple(v for v in versions if source.version < v.version <= target)
    if not pending:
        return source
    if settings.s3_bucket:
        return source.model_copy(
            update={"error": "S3 recovery is outside SQLite scope", "exit_code": 4}
        )
    if not path.exists():
        with sqlite3.connect(path):
            pass
    try:
        backup = _backup(path, settings, source, versions, manifest)
        campaign = verify_package(backup).campaign
    except (
        OSError,
        SQLAlchemyError,
        sqlite3.Error,
        ValidationError,
        ModelError,
        ValueError,
    ) as error:
        return source.model_copy(update={"error": str(error), "exit_code": 4})
    engine = create_engine(f"sqlite:///{path}")
    applied: list[int] = []
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
            _apply_pending(connection, source, pending, versions, campaign, applied)
        result = status(path, settings.home, versions)
    except (SQLAlchemyError, ValidationError, RuntimeError) as error:
        result = status(path, settings.home, versions).model_copy(
            update={"error": str(error), "exit_code": 5}
        )
    finally:
        engine.dispose()
    return result.model_copy(update={"backup_manifest": str(backup), "applied": tuple(applied)})


def _apply_pending(
    connection: Connection,
    source: DatabaseStatus,
    pending: tuple[MigrationDefinition, ...],
    versions: tuple[MigrationDefinition, ...],
    campaign: str,
    applied: list[int],
) -> None:
    baseline_version = next((v.version for v in versions if v.target.id == source.baseline), 0)
    stamped = tuple(v for v in pending if v.version <= baseline_version)
    if source.state == "unversioned":
        stamp_baseline(connection, stamped, campaign)
        applied.extend(v.version for v in stamped)
    else:
        stamped = ()
    for definition in pending:
        if definition in stamped:
            continue
        apply_version(connection, definition, campaign)
        applied.append(definition.version)
        inspect_database(connection, versions)
        connection.rollback()
