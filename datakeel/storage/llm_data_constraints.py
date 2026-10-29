# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seal saved dry-run evidence, evaluation references and clean publication identities."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

_TABLES = ("training_evaluations", "training_governance_runs", "training_clean_versions")


def install_llm_data_constraints(connection: Connection, *, sqlite: bool) -> None:
    """Reject edits or removal of facts already used for approval, quality or citations."""
    if not sqlite:
        connection.execute(
            text(
                "CREATE OR REPLACE FUNCTION datakeel_immutable_llm_data() RETURNS trigger AS $$ "
                "BEGIN RAISE EXCEPTION 'training governance facts are immutable'; END; $$ "
                "LANGUAGE plpgsql"
            )
        )
    for table in _TABLES:
        if sqlite:
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} "
                        f"BEFORE {operation} ON {table} BEGIN "
                        "SELECT RAISE(ABORT, 'training governance facts are immutable'); END"
                    )
                )
        else:
            # Recreate so triggers from older branch builds also point at this function.
            connection.execute(text(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}"))
            connection.execute(
                text(
                    f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                    "FOR EACH ROW EXECUTE FUNCTION datakeel_immutable_llm_data()"
                )
            )
