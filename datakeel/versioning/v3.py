# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen 102-table SQLite target with the persisted task display rank, from typed export."""

import hashlib
from importlib.resources import files

from pydantic import TypeAdapter
from sqlalchemy.engine import Connection

from datakeel.versioning.models import BaselineDefinition, MigrationDefinition, SchemaObject
from datakeel.versioning.v1 import baseline as v1_baseline
from datakeel.versioning.v2 import CHECKSUM_SOURCES as V2_SOURCES

CHECKSUM_SOURCES = tuple(
    sorted(
        (
            *V2_SOURCES,
            "versioning/campaign_v3.py",
            "versioning/inspect_v3.py",
            "versioning/sqlite_b3.json",
            "versioning/v3.py",
        )
    )
)


def baseline() -> BaselineDefinition:
    """Load the complete frozen target without importing latest schema contributions."""
    objects = TypeAdapter(tuple[SchemaObject, ...]).validate_json(
        files("datakeel.versioning").joinpath("sqlite_b3.json").read_bytes()
    )
    return BaselineDefinition(id="sqlite-b3", objects=objects, invariants=v1_baseline().invariants)


def forward(connection: Connection) -> None:
    """Only add the nullable rank and rebuild the claim index; the campaign owns commits.

    Existing rows keep NULL ranks; the first claim per project backfills them in the
    display order, so this version adds no business facts and preserves every old field.
    """
    connection.exec_driver_sql("ALTER TABLE production_tasks ADD COLUMN display_rank INTEGER")
    connection.exec_driver_sql("DROP INDEX production_task_claim_order")
    connection.exec_driver_sql(
        "CREATE INDEX production_task_claim_order "
        "ON production_tasks (project_id, state, priority DESC, display_rank, id)"
    )


def definition() -> MigrationDefinition:
    """Bind v3's complete execution closure, target and explicit policies independently."""
    migration = MigrationDefinition(
        version=3,
        checksum="0" * 64,
        source="sqlite-b2",
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
