# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen SQLite b1: current semantics, with no asserted historical release provenance."""

import hashlib
from importlib.resources import files

from pydantic import TypeAdapter
from sqlalchemy.engine import Connection

from datakeel.versioning.models import (
    BaselineDefinition,
    MigrationDefinition,
    SchemaObject,
)

VERSION = 1
MINIMUM_READER = 1
SOURCE = "empty|sqlite-b1"
PRESERVE_FACTS = True
# Frozen transitive local source closure. New registrations must not extend this tuple.
# Program release provenance and entry-point wiring are not migration semantics.
CHECKSUM_SOURCES = (
    "core/catalog_identity.py",
    "core/errors.py",
    "core/models.py",
    "core/orchestration.py",
    "core/recovery.py",
    "core/routing_models.py",
    "core/settings.py",
    "routing/models.py",
    "versioning/campaign.py",
    "versioning/configuration.py",
    "versioning/inspect.py",
    "versioning/location.py",
    "versioning/lock.py",
    "versioning/models.py",
    "versioning/recovery.py",
    "versioning/recovery_models.py",
    "versioning/references.py",
    "versioning/sqlite_b1.json",
    "versioning/v1.py",
)


def definition() -> MigrationDefinition:
    """Bind explicit v1 policies and the complete frozen source bytes to its checksum."""
    migration = MigrationDefinition(
        version=VERSION,
        checksum="0" * 64,
        source=SOURCE,
        minimum_reader=MINIMUM_READER,
        target=baseline(),
        forward=initial,
        preserve_facts=PRESERVE_FACTS,
        checksum_sources=CHECKSUM_SOURCES,
    )
    digest = hashlib.sha256()
    for name in CHECKSUM_SOURCES:
        content = files("datakeel").joinpath(name).read_bytes()
        digest.update(name.encode() + b"\0" + len(content).to_bytes(8, "big") + content)
    digest.update(migration.model_dump_json(exclude={"checksum", "forward"}).encode())
    return migration.model_copy(update={"checksum": digest.hexdigest()})


def baseline() -> BaselineDefinition:
    """Load the 99-table W3-S1 structural snapshot without loading latest ORM metadata."""
    objects = TypeAdapter(tuple[SchemaObject, ...]).validate_json(
        files("datakeel.versioning").joinpath("sqlite_b1.json").read_bytes()
    )
    return BaselineDefinition(
        id="sqlite-b1",
        objects=objects,
        invariants=(
            (
                "SELECT 1 FROM tasks WHERE state NOT IN "
                "('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED') OR total_shards < 0 LIMIT 1"
            ),
            (
                "SELECT 1 FROM task_shards WHERE state NOT IN "
                "('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED') "
                "OR ordinal < 0 OR attempts < 0 LIMIT 1"
            ),
            "SELECT 1 FROM outbox WHERE delivered NOT IN (0,1) LIMIT 1",
            (
                "SELECT 1 FROM datasets WHERE json_type(files) != 'array' "
                "OR json_type(metadata_values) != 'object' LIMIT 1"
            ),
            "SELECT 1 FROM versions WHERE json_type(manifest) != 'array' LIMIT 1",
        ),
    )


def initial(connection: Connection) -> None:
    """Create only the frozen b1 target; legacy b1 data is stamped without changes."""
    if connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' LIMIT 1"
    ).fetchone():
        return  # A complete legacy baseline was validated before this transaction.
    objects = baseline().objects
    for kind in ("table", "index", "trigger", "view"):
        for item in objects:
            if item.kind == kind:
                connection.exec_driver_sql(item.sql)
    connection.exec_driver_sql("INSERT INTO file_discovery_checkpoints VALUES ('public-files-v2')")
