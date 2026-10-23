# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dialect-specific guards for immutable assertion content and decision audits."""

from sqlalchemy import Connection, text


def install_evidence_constraints(connection: Connection, *, sqlite: bool) -> None:
    """Allow projection rebuilds while rejecting content edits and audit rewrites."""
    if sqlite:
        connection.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS assertion_content_immutable "
                "BEFORE UPDATE OF payload, subject_id, predicate, producer_event_id ON assertions "
                "BEGIN SELECT RAISE(ABORT, 'assertion content is immutable'); END"
            )
        )
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS decision_no_{operation.lower()} "
                    f"BEFORE {operation} ON assertion_decisions BEGIN "
                    "SELECT RAISE(ABORT, 'assertion decisions are append-only'); END"
                )
            )
        return
    connection.execute(
        text("""
        CREATE OR REPLACE FUNCTION datakeel_immutable_assertion() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'assertion content is immutable'; END;
        $$ LANGUAGE plpgsql
    """)
    )
    connection.execute(
        text("""
        DO $$ BEGIN IF NOT EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = 'datakeel_assertion_immutable'
            AND tgrelid = 'assertions'::regclass
        ) THEN CREATE TRIGGER datakeel_assertion_immutable
        BEFORE UPDATE OF payload, subject_id, predicate, producer_event_id ON assertions
        FOR EACH ROW EXECUTE FUNCTION datakeel_immutable_assertion(); END IF; END $$
    """)
    )
    connection.execute(
        text("""
        DO $$ BEGIN IF NOT EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = 'datakeel_decision_immutable'
            AND tgrelid = 'assertion_decisions'::regclass
        ) THEN CREATE TRIGGER datakeel_decision_immutable
        BEFORE UPDATE OR DELETE ON assertion_decisions FOR EACH ROW
        EXECUTE FUNCTION datakeel_immutable_assertion(); END IF; END $$
    """)
    )
