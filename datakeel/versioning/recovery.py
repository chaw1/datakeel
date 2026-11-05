# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Complete local SQLite recovery packages; never restore into an active home."""

import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from datakeel import __version__
from datakeel.core.errors import ValidationError
from datakeel.core.recovery import ISOLATION_MARKER
from datakeel.core.settings import Settings
from datakeel.versioning.configuration import write_configuration
from datakeel.versioning.inspect import facts_digest
from datakeel.versioning.location import readonly_engine
from datakeel.versioning.models import DatabaseStatus
from datakeel.versioning.recovery_models import RecoveryFile, RecoveryManifest
from datakeel.versioning.references import referenced_objects


def file_record(root: Path, relative: str) -> RecoveryFile:
    """Require a regular contained file and hash every byte."""
    path = contained(root, relative)
    with path.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    return RecoveryFile(path=relative, sha256=checksum, size=path.stat().st_size)


def contained(root: Path, relative: str) -> Path:
    """Reject traversal, absolute names and symlinked recovery components."""
    part = Path(relative)
    path = root / part
    if (
        part.is_absolute()
        or ".." in part.parts
        or "\\" in relative
        or any(parent.is_symlink() for parent in (path, *path.parents))
        or not path.resolve().is_relative_to(root.resolve())
    ):
        msg = "Unsafe recovery file path"
        raise ValidationError(msg)
    return path


def _snapshot_facts(path: Path) -> tuple[str, tuple[str, ...]]:
    engine = readonly_engine(path)
    try:
        with engine.connect() as connection:
            if connection.exec_driver_sql("PRAGMA integrity_check").fetchall() != [("ok",)]:
                msg = "Invalid recovery database"
                raise ValidationError(msg)
            return facts_digest(connection), referenced_objects(connection)
    finally:
        engine.dispose()


def create_package(
    database: Path,
    destination: Path,
    settings: Settings,
    source: DatabaseStatus,
    checksums: tuple[str, ...],
    identity: str,
) -> Path:
    """Back up with an independent idle source connection, then copy all snapshot objects."""
    destination.mkdir(parents=True, exist_ok=False)
    snapshot = destination / "database.sqlite"
    with (
        closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as origin,
        closing(sqlite3.connect(snapshot)) as target,
    ):
        origin.backup(target)
    facts, keys = _snapshot_facts(snapshot)
    objects: list[RecoveryFile] = []
    for key in keys:
        origin = contained(settings.home.resolve() / "objects", key)
        relative = f"objects/{key}"
        target = contained(destination, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, target)
        objects.append(file_record(destination, relative))
    references = write_configuration(settings, destination)
    manifest = RecoveryManifest(
        campaign=destination.name,
        source_identity=identity,
        source=source,
        source_facts=facts,
        target_checksums=checksums,
        program_version=__version__,
        sqlite_version=sqlite3.sqlite_version,
        database=file_record(destination, "database.sqlite"),
        objects=tuple(objects),
        config=file_record(destination, "config.json"),
        credential_references=references,
    )
    path = destination / "manifest.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(manifest.model_dump_json(indent=2) + "\n")
    temporary.replace(path)
    verify_package(path)
    return path


def verify_package(path: Path) -> RecoveryManifest:
    """Verify contents and independently re-enumerate references; a truncated list fails."""
    manifest = RecoveryManifest.model_validate_json(path.read_bytes())
    if manifest.database.path != "database.sqlite" or manifest.config.path != "config.json":
        msg = "Invalid recovery layout"
        raise ValidationError(msg)
    records = (manifest.database, manifest.config, *manifest.objects)
    if len({item.path for item in records}) != len(records):
        msg = "Duplicate recovery component"
        raise ValidationError(msg)
    for item in records:
        if file_record(path.parent, item.path) != item:
            msg = "Recovery component hash mismatch"
            raise ValidationError(msg)
    facts, keys = _snapshot_facts(path.parent / manifest.database.path)
    if facts != manifest.source_facts or {item.path for item in manifest.objects} != {
        f"objects/{key}" for key in keys
    }:
        msg = "Incomplete recovery objects or changed snapshot facts"
        raise ValidationError(msg)
    return manifest


def restore_package(manifest_path: Path, home: Path) -> Path:
    """Restore only into a new isolated directory; never automatically activate services."""
    manifest = verify_package(manifest_path)
    home.mkdir(parents=True, exist_ok=False)
    (home / ISOLATION_MARKER).write_text(json.dumps({"campaign": manifest.campaign}) + "\n")
    for item in (manifest.database, manifest.config, *manifest.objects):
        target = home / ("datakeel.db" if item == manifest.database else item.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(contained(manifest_path.parent, item.path), target)
        copied = file_record(home, str(target.relative_to(home)))
        if (copied.sha256, copied.size) != (item.sha256, item.size):
            msg = "Restored recovery component hash mismatch"
            raise ValidationError(msg)
    return home / "datakeel.db"
