# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Quarantining what is already quarantined, or lifting a quarantine that is not there.

"dock-06 那张的隔离撤了吧" while dock-06 is not quarantined changes nothing: the reply says
it is already so instead of making a card.
"""

from pydantic import JsonValue

from datakeel.storage.database import Database
from datakeel.storage.file_state import get_file_state


def _named(selection: JsonValue) -> tuple[str, list[str]] | None:
    """(dataset, file ids) of a selection that lists its files by id, else None."""
    if not isinstance(selection, dict):
        return None
    dataset, filters = selection.get("dataset_id"), selection.get("filters")
    if not isinstance(dataset, str) or not isinstance(filters, list) or len(filters) != 1:
        return None
    only = filters[0]
    if not isinstance(only, dict) or (only.get("field"), only.get("operator")) != ("id", "in"):
        return None
    ids = only.get("value")
    return (dataset, [str(item) for item in ids]) if isinstance(ids, list) and ids else None


def _all(db: Database, params: dict[str, JsonValue], *, quarantined: bool) -> bool:
    found = _named(params.get("selection"))
    if found is None:
        return False
    dataset, files = found
    with db.session() as session:
        states = [get_file_state(session, dataset, file) for file in files]
    return all(state.quarantined == quarantined for state in states)


def quarantined_already(db: Database, params: dict[str, JsonValue]) -> bool:
    """Every file the step quarantines is quarantined already."""
    return _all(db, params, quarantined=True)


def not_quarantined(db: Database, params: dict[str, JsonValue]) -> bool:
    """No file the step releases from quarantine is quarantined."""
    return _all(db, params, quarantined=False)
