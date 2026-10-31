# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Objects a plan creates that a later step of the same plan names.

"建个质检组让 Mia 带, 刘洋也拉进去": the second step names the team the first step creates.
It does not exist yet, so it is never looked up; its name stands for the id the first step
gives it, and the steps run in order.
"""

from pydantic import JsonValue

from datakeel.intents.catalog import FIELD_KINDS, LIST_KINDS
from datakeel.intents.drafts import DraftStep
from datakeel.intents.duplicates import CREATES

# kind -> every name and id said for an object created earlier in the plan -> its id
type Created = dict[str, dict[str, str]]


def remember(created: Created, step: DraftStep, field: str | None) -> None:
    """Record the object a filled step creates under its id and the names it was given."""
    operation = step.params.get("operation")
    entry = CREATES.get((step.action, operation if isinstance(operation, str) else None))
    identity = step.params.get(field) if field else None
    if entry is None or not isinstance(identity, str):
        return
    kind, naming = entry
    known = created.setdefault(kind, {})
    for name in (identity, *(step.params.get(key) for key in (*naming, "display_name"))):
        if isinstance(name, str) and name.strip():
            known[name.strip().casefold()] = identity


def _found(known: dict[str, str], item: JsonValue) -> str | None:
    return known.get(item.strip().casefold()) if isinstance(item, str) else None


def earlier(field: str, value: JsonValue, created: Created) -> tuple[JsonValue, JsonValue]:
    """(ids of objects created earlier that the value names, the part still to look up).

    The part still to look up is None when the value names only objects created earlier.
    """
    known = created.get(FIELD_KINDS.get(field) or LIST_KINDS.get(field) or "", {})
    if field in FIELD_KINDS and isinstance(value, str):
        found = _found(known, value)
        return (found, None) if found else (None, value)
    if field in LIST_KINDS and isinstance(value, list):
        made: list[JsonValue] = [hit for item in value if (hit := _found(known, item))]
        rest: list[JsonValue] = [item for item in value if not _found(known, item)]
        return made, rest or None
    return None, value
