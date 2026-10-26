# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compose rule suggestions and conformance reports without mutating associations."""

from datakeel.core.standard_history_models import StandardsReport
from datakeel.core.standard_models import ColumnProfile, MappingSuggestion
from datakeel.standards.checks import check_column
from datakeel.standards.coverage import summarize_coverage
from datakeel.standards.mapping import suggest
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.database import Database
from datakeel.storage.standard_profiles import profiles_from_snapshot
from datakeel.storage.standard_store import state_in_session


def list_profiles(db: Database) -> tuple[ColumnProfile, ...]:
    """Expose metadata and observation counts while keeping raw source values private."""
    with db.session() as session:
        return tuple(
            item.model_copy(update={"values": ()})
            for item in profiles_from_snapshot(read_snapshot(session))
        )


def suggestions(db: Database) -> tuple[MappingSuggestion, ...]:
    """Return explained candidates for every column, leaving all mappings unchanged."""
    with db.session() as session:
        contract = state_in_session(session).contract
        return tuple(
            suggest(profile, contract) for profile in profiles_from_snapshot(read_snapshot(session))
        )


def standards_report(db: Database, table_id: str | None = None) -> StandardsReport:
    """Check only confirmed mappings and report bounded, redacted conformance evidence."""
    with db.session() as session:
        state = state_in_session(session)
        profiles = profiles_from_snapshot(read_snapshot(session), table_id)
        columns = {item.column_id: item for item in profiles}
        definitions = {item.code: item for item in state.contract.standards}
        mappings = tuple(item for item in state.mappings if item.column_id in columns)
        checks = tuple(
            check_column(
                columns[item.column_id], definitions[item.standard_code], state.contract.code_lists
            )
            for item in mappings
            if item.standard_code in definitions
        )
        return StandardsReport(
            profiles=tuple(item.model_copy(update={"values": ()}) for item in profiles),
            mappings=mappings,
            checks=checks,
            coverage=summarize_coverage(profiles, mappings, checks),
        )
