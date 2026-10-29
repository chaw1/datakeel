# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Maintain a rebuildable public-file discovery index from immutable-version facts."""

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, delete, insert, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Session, mapped_column

from datakeel.storage.base import Base

_COLUMNS = "file_id, name, dataset_id, version_id, created_at"
_GENERATION = "public-files-v2"
_PYTHON_FILES = "public-files-python-json-v1"
_IDENTITY = String().with_variant(String(collation="C"), "postgresql")


class FileDiscoveryRow(Base):
    """Store public navigation per immutable version, never mutable file state."""

    __tablename__ = "file_discovery"
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    file_id: Mapped[str] = mapped_column(_IDENTITY)
    name: Mapped[str] = mapped_column(String)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    version_id: Mapped[str] = mapped_column(
        _IDENTITY,
        ForeignKey("versions.id", ondelete="CASCADE", onupdate="CASCADE"),
        index=True,
    )
    created_at: Mapped[float] = mapped_column(Float)


class FileDiscoveryCheckpointRow(Base):
    """Record completed migrations and a sticky need for exact Python JSON reads."""

    __tablename__ = "file_discovery_checkpoints"
    generation: Mapped[str] = mapped_column(String, primary_key=True)


def begin_file_read(session: Session) -> bool:
    """Start one stable read snapshot, or require Python fallback for an existing transaction."""
    if session.in_transaction():
        return False
    if session.get_bind().dialect.name == "sqlite":
        session.execute(text("BEGIN"))
    else:
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    return True


def requires_python_files(session: Session) -> bool:
    """Retain exact Python JSON semantics after any potentially lossy JSON text write."""
    return (
        session.scalar(
            select(FileDiscoveryCheckpointRow.generation).where(
                FileDiscoveryCheckpointRow.generation == _PYTHON_FILES
            )
        )
        is not None
    )


def _python_condition(expression: str, *, sqlite: bool) -> str:
    # Expressions are fixed internal table/column references, never user input.
    if sqlite:
        value = f"lower(CAST({expression} AS TEXT))"
        return (
            f"({value} GLOB ('*' || char(92) || 'u0000*') OR "
            f"{value} GLOB ('*' || char(92) || 'ud[89abcdef]*'))"
        )
    return f"CAST({expression} AS TEXT) ~ (chr(92) || chr(92) || 'u(0000|[dD][89a-fA-F])')"


def _marker_sql(condition: str) -> str:
    # Only the fixed generation and internally constructed conditions reach this SQL.
    return (
        "INSERT INTO file_discovery_checkpoints (generation) "
        f"SELECT '{_PYTHON_FILES}' WHERE {condition} ON CONFLICT(generation) DO NOTHING"
    )


def _python_marker_triggers(connection: Connection, *, sqlite: bool) -> None:
    for table, column in (("datasets", "files"), ("versions", "manifest")):
        statement = _marker_sql(_python_condition(f"NEW.{column}", sqlite=sqlite))
        name = f"datakeel_file_python_{table}"
        if sqlite:
            for operation in ("INSERT", "UPDATE"):
                connection.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS {name}_{operation.lower()} "
                        f"AFTER {operation} ON {table} BEGIN {statement}; END"
                    )
                )
        else:
            connection.execute(
                text(
                    f"CREATE OR REPLACE FUNCTION {name}() RETURNS trigger AS $$ "
                    f"BEGIN {statement}; RETURN NEW; END; $$ LANGUAGE plpgsql"
                )
            )
            connection.execute(text(f"DROP TRIGGER IF EXISTS {name} ON {table}"))
            connection.execute(
                text(
                    f"CREATE TRIGGER {name} AFTER INSERT OR UPDATE ON {table} "
                    f"FOR EACH ROW EXECUTE FUNCTION {name}()"
                )
            )


def _candidates(*, sqlite: bool, inserted: bool) -> str:
    # SQL fragments contain only fixed internal identifiers, never input values.
    row = "NEW" if inserted else "v"
    source = "" if inserted else "versions AS v, "
    if sqlite:
        array = (
            f"CASE WHEN json_valid({row}.manifest) THEN "
            f"CASE WHEN json_type({row}.manifest) = 'array' THEN {row}.manifest "
            "ELSE '[]' END ELSE '[]' END"
        )
        expand = f"json_each({array}) AS j"
        identity = "CASE WHEN j.type = 'object' THEN json_extract(j.value, '$.id') END"
        name = "CASE WHEN j.type = 'object' THEN json_extract(j.value, '$.filename') END"
        valid = (
            "CASE WHEN j.type = 'object' THEN json_type(j.value, '$.id') = 'text' "
            "AND json_type(j.value, '$.filename') = 'text' ELSE 0 END"
        )
        ordinal = "CAST(j.key AS INTEGER)"
    else:
        array = (
            f"CASE WHEN json_typeof({row}.manifest) = 'array' THEN {row}.manifest "
            "ELSE '[]'::json END"
        )
        expand = f"json_array_elements({array}) WITH ORDINALITY AS j(value, ordinal)"
        identity = "datakeel_discovery_text(j.value, 'id') COLLATE \"C\""
        name = "datakeel_discovery_text(j.value, 'filename')"
        valid = f"{identity} IS NOT NULL AND {name} IS NOT NULL"
        ordinal = "j.ordinal"
    return (
        f"SELECT {identity} AS file_id, {name} AS name, "  # noqa: S608
        f"{row}.dataset_id AS dataset_id, "
        f"{row}.id AS version_id, {row}.created_at AS created_at, {ordinal} AS ordinal "
        f"FROM {source}{expand} WHERE {valid} AND {row}.created_at IS NOT NULL "
        f"AND EXISTS (SELECT 1 FROM datasets WHERE id = {row}.dataset_id)"
    )  # All SQL expressions are fixed by the two internal boolean choices.


def _insert_sql(*, sqlite: bool) -> str:
    # Projection column names and the candidate statement are fixed internal expressions.
    candidates = _candidates(sqlite=sqlite, inserted=True)
    if sqlite:
        selected = (
            f"SELECT {_COLUMNS} FROM (SELECT c.*, row_number() OVER "  # noqa: S608
            "(PARTITION BY file_id ORDER BY ordinal) AS priority "
            f"FROM ({candidates}) AS c) AS ranked WHERE priority = 1"
        )
    else:
        selected = (
            f"SELECT DISTINCT ON (file_id) {_COLUMNS} FROM ({candidates}) AS c "  # noqa: S608
            "ORDER BY file_id, ordinal"
        )
    return f"INSERT INTO file_discovery ({_COLUMNS}) {selected}"


def _rebuild_sql(*, sqlite: bool) -> str:
    # Ranking reconstructs the first manifest occurrence per version using fixed SQL.
    candidates = _candidates(sqlite=sqlite, inserted=False)
    selected = (
        f"SELECT {_COLUMNS} FROM (SELECT c.*, row_number() OVER "  # noqa: S608
        "(PARTITION BY file_id, version_id ORDER BY ordinal) AS priority "
        f"FROM ({candidates}) AS c) AS ranked WHERE priority = 1"
    )
    return f"INSERT INTO file_discovery ({_COLUMNS}) {selected}"  # Fixed fragments.


def rebuild_file_discovery(connection: Connection, *, sqlite: bool) -> None:
    """Reconstruct discovery and recompute the sticky JSON fallback marker atomically.

    Use a fresh maintenance transaction without previously locked business rows.
    PostgreSQL blocks fact mutations during the rebuild; normal version writes need no
    added global lock. SQLite uses its normal single-writer transaction.
    """
    if not sqlite:
        connection.execute(text("LOCK TABLE datasets, versions IN SHARE MODE"))
    connection.execute(text("DELETE FROM file_discovery"))
    connection.execute(text(_rebuild_sql(sqlite=sqlite)))
    connection.execute(
        delete(FileDiscoveryCheckpointRow).where(
            FileDiscoveryCheckpointRow.generation == _PYTHON_FILES
        )
    )
    condition = (
        f"EXISTS (SELECT 1 FROM datasets WHERE {_python_condition('files', sqlite=sqlite)}) "  # noqa: S608
        f"OR EXISTS (SELECT 1 FROM versions WHERE {_python_condition('manifest', sqlite=sqlite)})"
    )
    connection.execute(text(_marker_sql(condition)))


def _sqlite_triggers(connection: Connection) -> None:
    connection.execute(
        text(
            "CREATE TRIGGER IF NOT EXISTS datakeel_file_discovery_insert AFTER INSERT ON versions "
            f"BEGIN {_insert_sql(sqlite=True)}; END"
        )
    )
    connection.execute(
        text(
            "CREATE TRIGGER IF NOT EXISTS datakeel_file_discovery_update "  # noqa: S608
            "AFTER UPDATE ON versions "
            "BEGIN DELETE FROM file_discovery WHERE version_id IN (OLD.id, NEW.id); "
            f"{_insert_sql(sqlite=True)}; END"
        )
    )
    connection.execute(
        text(
            "CREATE TRIGGER IF NOT EXISTS datakeel_file_discovery_delete AFTER DELETE ON versions "
            "BEGIN DELETE FROM file_discovery WHERE version_id = OLD.id; END"
        )
    )


def _postgres_functions(connection: Connection) -> None:
    connection.execute(
        text("""
        CREATE OR REPLACE FUNCTION datakeel_discovery_text(value json, field text)
        RETURNS text AS $$
        BEGIN
          IF json_typeof(value->field) IS DISTINCT FROM 'string' THEN RETURN NULL; END IF;
          RETURN value->>field;
        EXCEPTION WHEN data_exception THEN RETURN NULL;
        END; $$ LANGUAGE plpgsql IMMUTABLE STRICT
    """)
    )
    # The inserted SQL comes exclusively from fixed internal expressions.
    statement = (
        "CREATE OR REPLACE FUNCTION datakeel_file_discovery_sync() "  # noqa: S608
        "RETURNS trigger AS $$ BEGIN "
        "IF TG_OP = 'DELETE' THEN DELETE FROM file_discovery WHERE version_id = OLD.id; "
        "RETURN OLD; END IF; "
        "IF TG_OP = 'UPDATE' THEN "
        "DELETE FROM file_discovery WHERE version_id IN (OLD.id, NEW.id); END IF; "
        f"{_insert_sql(sqlite=False)}; RETURN NEW; END; $$ LANGUAGE plpgsql"
    )
    connection.execute(text(statement))


def _postgres_triggers(connection: Connection) -> None:
    _postgres_functions(connection)
    connection.execute(text("DROP TRIGGER IF EXISTS datakeel_file_discovery_sync ON versions"))
    connection.execute(
        text(
            "CREATE TRIGGER datakeel_file_discovery_sync AFTER INSERT OR UPDATE OR DELETE "
            "ON versions FOR EACH ROW EXECUTE FUNCTION datakeel_file_discovery_sync()"
        )
    )


def install_file_discovery(connection: Connection, *, sqlite: bool) -> None:
    """Install transactional maintenance and backfill legacy versions exactly once."""
    checkpoint = connection.scalar(
        select(FileDiscoveryCheckpointRow.generation).where(
            FileDiscoveryCheckpointRow.generation == _GENERATION
        )
    )
    if checkpoint is not None:
        return
    if sqlite:
        _sqlite_triggers(connection)
    else:
        _postgres_triggers(connection)
    _python_marker_triggers(connection, sqlite=sqlite)
    rebuild_file_discovery(connection, sqlite=sqlite)
    connection.execute(insert(FileDiscoveryCheckpointRow).values(generation=_GENERATION))
