# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen 102-table SQLite target exported from typed contributions and real installers."""

import hashlib
from importlib.resources import files

from pydantic import TypeAdapter
from sqlalchemy.engine import Connection

from datakeel.versioning.models import BaselineDefinition, MigrationDefinition, SchemaObject
from datakeel.versioning.v1 import CHECKSUM_SOURCES as V1_SOURCES
from datakeel.versioning.v1 import baseline as v1_baseline

CHECKSUM_SOURCES = tuple(
    sorted(
        (
            *V1_SOURCES,
            "versioning/campaign_v2.py",
            "versioning/facts_v2.py",
            "versioning/inspect_v2.py",
            "versioning/sqlite_b2.json",
            "versioning/sqlite_b2_altered_shards.json",
            "versioning/v2.py",
        )
    )
)
VECTOR_TABLES = frozenset({"vector_cache", "vector_fake_accounts", "vector_fake_attempts"})


def baseline() -> BaselineDefinition:
    """Load the complete frozen target without importing latest schema contributions."""
    objects = TypeAdapter(tuple[SchemaObject, ...]).validate_json(
        files("datakeel.versioning").joinpath("sqlite_b2.json").read_bytes()
    )
    return BaselineDefinition(id="sqlite-b2", objects=objects, invariants=v1_baseline().invariants)


def forward(connection: Connection) -> None:
    """Only add vector objects and the nullable lease; the campaign owns all validation/commits."""
    for kind in ("table", "index", "trigger", "view"):
        for item in baseline().objects:
            if item.table in VECTOR_TABLES and item.kind == kind:
                connection.exec_driver_sql(item.sql)
    connection.exec_driver_sql("ALTER TABLE task_shards ADD COLUMN lease_expires_at FLOAT")


def definition() -> MigrationDefinition:
    """Bind v2's complete execution closure, target and explicit policies independently of v1."""
    migration = MigrationDefinition(
        version=2,
        checksum="0" * 64,
        source="sqlite-b1",
        target=baseline(),
        minimum_reader=1,
        forward=forward,
        preserve_facts=True,
        checksum_sources=CHECKSUM_SOURCES,
    )
    digest = hashlib.sha256()
    for name in CHECKSUM_SOURCES:
        content = files("datakeel").joinpath(name).read_bytes()
        digest.update(name.encode() + b"\0" + len(content).to_bytes(8, "big") + content)
    digest.update(migration.model_dump_json(exclude={"checksum", "forward"}).encode())
    return migration.model_copy(update={"checksum": digest.hexdigest()})
