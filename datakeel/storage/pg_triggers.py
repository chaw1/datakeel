# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Install PostgreSQL row triggers without table DDL on already-current startups."""

from sqlalchemy import text
from sqlalchemy.engine import Connection


def ensure_pg_trigger(
    connection: Connection, *, name: str, table: str, event: str, function: str
) -> None:
    """Create a missing trigger, or re-point one that calls another function.

    Trigger DDL takes a table lock that queues behind open writers, so a startup that finds
    the trigger already calling ``function`` must issue none.
    """
    connection.execute(
        text(f"""
        DO $$ BEGIN IF NOT EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = '{name}'
            AND tgrelid = '{table}'::regclass AND tgfoid = '{function}'::regproc
        ) THEN
            DROP TRIGGER IF EXISTS {name} ON {table};
            CREATE TRIGGER {name} BEFORE {event} ON {table}
            FOR EACH ROW EXECUTE FUNCTION {function}();
        END IF; END $$
        """)  # noqa: S608  # Callers pass fixed identifiers only, never user input.
    )
