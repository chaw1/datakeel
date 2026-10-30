# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Edits start from the current version: add, remove or rename on top of what exists.

``create_label_set`` takes the complete label list of the new version. A sentence such as
"add a pedestrian label" names only the change, so the plan reads the latest version and
applies the change to it; a label is removed only when the person said so. The difference
(added, removed, renamed and the annotations it affects) is computed exactly like the
``label_set_diff`` read function, so the card shows it before anything is confirmed.
"""

import re

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel
from datakeel.core.production_catalog_models import LabelSet
from datakeel.storage.database import Database
from datakeel.storage.intent_reads import label_change_impact, latest_label_set

_ASCII = re.compile(r"[^a-z0-9]+")


class LabelDiff(BoundaryModel):
    """What a label set step changes compared with the version it starts from."""

    base_version: int | None = None
    added: list[str] = Field(default_factory=list[str])
    removed: list[str] = Field(default_factory=list[str])
    renamed: list[str] = Field(default_factory=list[str])
    kept: int = 0
    affected_annotations: int = 0
    affected_revisions: int = 0


def _label(item: JsonValue, taken: set[str]) -> dict[str, JsonValue] | None:
    raw: dict[str, JsonValue] = (
        dict(item) if isinstance(item, dict) else {"name": item} if isinstance(item, str) else {}
    )
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not identifier.strip():
        base = _ASCII.sub("_", name.casefold()).strip("_") or "label"
        identifier, index = base, 1
        while identifier in taken:
            index += 1
            identifier = f"{base}_{index}"
    raw["id"], raw["name"] = identifier, name.strip()
    taken.add(identifier)
    return raw


def with_label_ids(labels: JsonValue) -> list[JsonValue]:
    """Give spoken labels stable ids so a new label set validates."""
    taken: set[str] = set()
    found = [_label(item, taken) for item in (labels if isinstance(labels, list) else [])]
    return [item for item in found if item is not None]


def _names(values: JsonValue) -> set[str]:
    items = values if isinstance(values, list) else [values] if values else []
    found: set[str] = set()
    for item in items:
        name = item.get("name") if isinstance(item, dict) else item
        identifier = item.get("id") if isinstance(item, dict) else item
        found.update(str(value).casefold() for value in (name, identifier) if value)
    return found


def _merged(current: LabelSet, adds: JsonValue, removes: JsonValue) -> list[JsonValue]:
    labels: list[dict[str, JsonValue]] = [
        label.model_dump(mode="json", exclude_none=True) for label in current.labels
    ]
    taken = {str(item["id"]) for item in labels}
    index = {str(value).casefold(): item for item in labels for value in (item["id"], item["name"])}
    for raw in adds if isinstance(adds, list) else []:
        spoken = _names(raw)
        existing = next((index[name] for name in spoken if name in index), None)
        if existing is not None and isinstance(raw, dict):
            existing.update({key: value for key, value in raw.items() if key != "id"})
            continue
        label = _label(raw, taken) if existing is None else None
        if label is not None:
            labels.append(label)
    gone = _names(removes)
    removed = {str(item["id"]) for item in labels if _names(item) & gone}
    # A removed parent takes its children with it, as in the label tree editor.
    changed = True
    while changed:
        children = {str(item["id"]) for item in labels if item.get("parent_id") in removed}
        changed = not children <= removed
        removed |= children
    return [item for item in labels if str(item["id"]) not in removed]


def prepare_label_edit(db: Database, params: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Apply a spoken change to the latest version; new label sets only get label ids."""
    adds = params.pop("add_labels", None)
    removes = params.pop("remove_labels", None)
    identifier = params.get("label_set_id")
    current = latest_label_set(db, identifier) if isinstance(identifier, str) else None
    if current is None or params.get("target", "label_set") != "label_set":
        if "labels" in params or adds is not None:
            params["labels"] = with_label_ids([*_list(params.get("labels")), *_list(adds)])
        return params
    params["labels"] = _merged(current, [*_list(params.get("labels")), *_list(adds)], removes)
    params.setdefault("name", current.name)
    if current.published:
        params["operation"] = "create"
        params["previous_version"] = current.version
        params.pop("version", None)
    else:
        params["operation"], params["version"] = "update", current.version
    if current.guidelines is not None and "guidelines" not in params:
        kept = {str(item["id"]) for item in _list(params["labels"]) if isinstance(item, dict)}
        rules = [rule for rule in current.guidelines.rules if rule.label_id in kept]
        params["guidelines"] = current.guidelines.model_copy(
            update={"rules": tuple(rules)}
        ).model_dump(mode="json")
    return params


def _list(value: JsonValue) -> list[JsonValue]:
    return list(value) if isinstance(value, list) else [] if value is None else [value]


def label_diff(db: Database, params: dict[str, JsonValue]) -> LabelDiff | None:
    """Compare the planned labels with the version they start from, like label_set_diff."""
    identifier = params.get("label_set_id")
    labels = params.get("labels")
    if not isinstance(identifier, str) or not isinstance(labels, list):
        return None
    current = latest_label_set(db, identifier)
    if current is None:
        return None
    try:
        after = LabelSet.model_validate({**current.model_dump(mode="json"), "labels": labels})
    except ValueError:
        return None
    old = {label.id: label.name for label in current.labels}
    new = {label.id: label.name for label in after.labels}
    annotations, revisions = label_change_impact(db, current, after)
    return LabelDiff(
        base_version=current.version,
        added=[new[key] for key in new if key not in old],
        removed=[old[key] for key in old if key not in new],
        renamed=[
            f"{old[key]} → {new[key]}" for key in old.keys() & new.keys() if old[key] != new[key]
        ],
        kept=len(old.keys() & new.keys()),
        affected_annotations=annotations,
        affected_revisions=revisions,
    )
