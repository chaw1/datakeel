# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dataset-owned schema and the unchanged append-only lineage installer."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from datakeel.core.schema import SchemaContribution, SchemaInstaller
from datakeel.dataset_store import rows
from datakeel.dataset_store.file_discovery import install_file_discovery


def install_lineage(connection: Connection, *, sqlite: bool) -> None:
    """Protect event history in the caller's existing migration transaction."""
    if sqlite:
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS lineage_no_{operation.lower()} "
                    f"BEFORE {operation} ON lineage_events BEGIN "
                    "SELECT RAISE(ABORT, 'lineage events are append-only'); END"
                )
            )
    else:
        connection.execute(
            text("""
            CREATE OR REPLACE FUNCTION datakeel_immutable_event() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'lineage events are append-only'; END;
            $$ LANGUAGE plpgsql
        """)
        )
        connection.execute(
            text("""
            DO $$ BEGIN IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'datakeel_lineage_immutable'
                AND tgrelid = 'lineage_events'::regclass
            ) THEN CREATE TRIGGER datakeel_lineage_immutable
            BEFORE UPDATE OR DELETE ON lineage_events FOR EACH ROW
            EXECUTE FUNCTION datakeel_immutable_event(); END IF; END $$
        """)
        )


SCHEMA = SchemaContribution(
    owner="dataset_store",
    order=6,
    rows=(
        rows.DatasetRow,
        rows.VersionRow,
        rows.EventRow,
        rows.MetadataChangeRow,
        rows.FileDiscoveryRow,
        rows.FileDiscoveryCheckpointRow,
        rows.FileStateRow,
        rows.UploadRow,
    ),
    installers=(
        SchemaInstaller(key="file_discovery", order=0, install=install_file_discovery),
        SchemaInstaller(key="lineage", order=7, install=install_lineage),
    ),
)
