# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Install database-enforced immutable publication and released-version constraints."""

from sqlalchemy import text
from sqlalchemy.engine import Connection


def install_release_constraints(connection: Connection, *, sqlite: bool) -> None:
    """Reject publication edits even through direct SQL or an accidental ORM mutation."""
    if sqlite:
        _sqlite_constraints(connection)
        return
    connection.execute(
        text("""
        CREATE OR REPLACE FUNCTION datakeel_immutable_release() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'published releases are immutable'; END;
        $$ LANGUAGE plpgsql
    """)
    )
    connection.execute(
        text("""
        CREATE OR REPLACE FUNCTION datakeel_sealed_release_entries() RETURNS trigger AS $$
        BEGIN
          IF EXISTS (SELECT 1 FROM releases WHERE id = NEW.release_id) THEN
            RAISE EXCEPTION 'published releases are immutable';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql
    """)
    )
    connection.execute(
        text("""
        DO $$ BEGIN IF NOT EXISTS (
          SELECT 1 FROM pg_trigger WHERE tgname = 'datakeel_release_entries_sealed'
          AND tgrelid = 'release_entries'::regclass
        ) THEN CREATE TRIGGER datakeel_release_entries_sealed
        BEFORE INSERT ON release_entries FOR EACH ROW
        EXECUTE FUNCTION datakeel_sealed_release_entries(); END IF; END $$
    """)
    )
    _postgres_version_constraints(connection)


def _postgres_version_constraints(connection: Connection) -> None:
    connection.execute(
        text("""
        CREATE OR REPLACE FUNCTION datakeel_released_version() RETURNS trigger AS $$
        BEGIN
          IF EXISTS (SELECT 1 FROM releases WHERE version_id = OLD.id) THEN
            RAISE EXCEPTION 'released versions are immutable';
          END IF;
          RETURN COALESCE(NEW, OLD);
        END; $$ LANGUAGE plpgsql
    """)
    )
    for table in ("releases", "release_entries", "versions"):
        function = (
            "datakeel_released_version" if table == "versions" else "datakeel_immutable_release"
        )
        connection.execute(
            text(f"""
            DO $$ BEGIN IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'datakeel_{table}_immutable'
                AND tgrelid = '{table}'::regclass
            ) THEN CREATE TRIGGER datakeel_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW
            EXECUTE FUNCTION {function}(); END IF; END $$
        """)  # noqa: S608  # Names come exclusively from the fixed tuple above.
        )


def _sqlite_constraints(connection: Connection) -> None:
    connection.execute(
        text("""
        CREATE TRIGGER IF NOT EXISTS release_entries_sealed
        BEFORE INSERT ON release_entries
        WHEN EXISTS (SELECT 1 FROM releases WHERE id = NEW.release_id)
        BEGIN SELECT RAISE(ABORT, 'published releases are immutable'); END
    """)
    )
    for table in ("releases", "release_entries", "versions"):
        condition = (
            "WHEN EXISTS (SELECT 1 FROM releases WHERE version_id = OLD.id)"
            if table == "versions"
            else ""
        )
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                text(f"""
                CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                BEFORE {operation} ON {table} {condition}
                BEGIN SELECT RAISE(ABORT, 'published releases are immutable'); END
            """)
            )
