# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Edits start from the current version: add, remove, rename or merge on top of what exists.

``create_label_set`` takes the complete label list of the new version. A sentence such as
"add a pedestrian label" or "rename Cat to Kitten" names only the change, so the plan reads
the latest version and applies the change to it; a label is removed only when the person
said so. Labels may be named by id, name or translation, and a migration the model wrote
with names is read the same way. The migration the new version needs (every removed or
renamed label) is then derived from the final list, so a confirmed card never fails for a
missing migration. The difference (added, removed, renamed and the annotations it affects)
is computed exactly like the ``label_set_diff`` read function, so the card shows it first.
"""

import re

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel
from datakeel.core.production_catalog_models import LabelSet
from datakeel.storage.database import Database
from datakeel.storage.intent_reads import label_change_impact, latest_label_set

_ASCII = re.compile(r"[^a-z0-9]+")
NAME_KEYS = ("id", "name", "name_zh", "name_en")
STRATEGIES = frozenset({"map", "drop", "manual"})
Labels = list[dict[str, JsonValue]]


class LabelDiff(BoundaryModel):
    """What a label set step changes compared with the version it starts from."""

    base_version: int | None = None
    added: list[str] = Field(default_factory=list[str])
    removed: list[str] = Field(default_factory=list[str])
    renamed: list[str] = Field(default_factory=list[str])
    kept: int = 0
    affected_annotations: int = 0
    affected_revisions: int = 0


class SpokenEdit(BoundaryModel):
    """One sentence's change to a label set, by the names the person used."""

    adds: list[JsonValue] = Field(default_factory=list[JsonValue])
    removes: list[str] = Field(default_factory=list[str])
    renames: list[tuple[str, str]] = Field(default_factory=list[tuple[str, str]])
    # Merges and splits keep their own decision: (operation, sources, targets, strategy).
    joins: list[tuple[str, list[str], list[str], str]] = Field(
        default_factory=list[tuple[str, list[str], list[str], str]]
    )
    strategy: str = "manual"


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


def _list(value: JsonValue) -> list[JsonValue]:
    return list(value) if isinstance(value, list) else [] if value is None else [value]


def _spoken(item: JsonValue) -> set[str]:
    """Every way a label may be named: id, name and translations, case-insensitive."""
    values = [item.get(key) for key in NAME_KEYS] if isinstance(item, dict) else [item]
    return {str(value).strip().casefold() for value in values if value}


def _find(labels: Labels, name: str) -> dict[str, JsonValue] | None:
    wanted = name.strip().casefold()
    return next((item for item in labels if wanted in _spoken(item)), None)


def _strings(value: JsonValue) -> list[str]:
    return [str(item) for item in _list(value) if isinstance(item, (str, int))]


def _rename_pairs(value: JsonValue) -> list[tuple[str, str]]:
    """``[{"from": "Cat", "to": "Kitten"}]``, ``{"Cat": "Kitten"}`` or ``[["Cat", "Kitten"]]``."""
    if isinstance(value, dict) and not {"from", "to"} & value.keys():
        return [(str(old), str(new)) for old, new in value.items() if isinstance(new, str)]
    pairs: list[tuple[str, str]] = []
    for item in _list(value):
        if isinstance(item, dict) and item.get("from") and item.get("to"):
            pairs.append((str(item["from"]), str(item["to"])))
        elif isinstance(item, list) and len(item) == 2:  # noqa: PLR2004 - an old/new pair
            pairs.append((str(item[0]), str(item[1])))
    return pairs


def _target_name(target: str, named: list[JsonValue]) -> str:
    """A target id the model also listed as a label is read by that label's name."""
    for item in named:
        if (
            isinstance(item, dict)
            and item.get("id") == target
            and isinstance(item.get("name"), str)
        ):
            return str(item["name"])
    return target


def _read_migration(edit: SpokenEdit, value: JsonValue, named: list[JsonValue]) -> None:
    """A migration the model wrote with names becomes the same spoken change."""
    for step in _list(value):
        if not isinstance(step, dict):
            continue
        operation = str(step.get("operation") or "")
        sources = _strings(step.get("source_ids"))
        targets = [_target_name(target, named) for target in _strings(step.get("target_ids"))]
        strategy = str(step.get("strategy") or "")
        if strategy in STRATEGIES - {"map"}:
            edit.strategy = strategy
        if operation == "rename" and len(sources) == len(targets) == 1:
            edit.renames.append((sources[0], targets[0]))
        elif operation == "delete":
            edit.removes.extend(sources)
        elif operation in {"merge", "split"} and sources and targets:
            mode = "manual" if operation == "split" or strategy == "manual" else "map"
            edit.joins.append((operation, sources, targets, mode))


def spoken_edit(params: dict[str, JsonValue]) -> SpokenEdit:
    """Collect add, remove, rename and migration words into one change."""
    adds = [*_list(params.pop("labels", None)), *_list(params.pop("add_labels", None))]
    edit = SpokenEdit(
        adds=adds,
        removes=_strings(params.pop("remove_labels", None)),
        renames=_rename_pairs(params.pop("rename_labels", None)),
    )
    _read_migration(edit, params.pop("migration", None), adds)
    return edit


def _renamed(item: dict[str, JsonValue], name: str) -> None:
    item["name"] = name
    language = "name_en" if name.isascii() else "name_zh"
    if language in item:
        item[language] = name


def _existing(labels: Labels, raw: JsonValue) -> dict[str, JsonValue] | None:
    for name in _spoken(raw):
        if (found := _find(labels, name)) is not None:
            return found
    return None


def _without(labels: Labels, gone: set[str]) -> Labels:
    removed = {str(item["id"]) for item in labels if _spoken(item) & gone}
    # A removed parent takes its children with it, as in the label tree editor.
    changed = True
    while changed:
        children = {str(item["id"]) for item in labels if item.get("parent_id") in removed}
        changed = not children <= removed
        removed |= children
    return [item for item in labels if str(item["id"]) not in removed]


def _apply(current: LabelSet, edit: SpokenEdit) -> Labels:
    labels: Labels = [label.model_dump(mode="json", exclude_none=True) for label in current.labels]
    for old, new in edit.renames:
        found = _find(labels, old)
        if found is not None:
            _renamed(found, new)
    gone = {name.casefold() for name in edit.removes}
    adds = list(edit.adds)
    for _, sources, targets, _ in edit.joins:
        gone |= {name.casefold() for name in sources if name not in targets}
        adds.extend(name for name in targets if _find(labels, name) is None)
    taken = {str(item["id"]) for item in labels}
    for raw in adds:
        existing = _existing(labels, raw)
        if existing is not None and isinstance(raw, dict):
            existing.update({key: value for key, value in raw.items() if key != "id"})
        elif existing is None and (label := _label(raw, taken)) is not None:
            labels.append(label)
    return _without(labels, gone)


def _ids(labels: Labels, names: list[str]) -> list[str]:
    found = [_find(labels, name) for name in names]
    return [str(item["id"]) for item in found if item is not None]


def needed_migration(base: LabelSet, labels: Labels, edit: SpokenEdit) -> list[JsonValue]:
    """One decision for every label the new list removes or renames, nothing more."""
    old: Labels = [label.model_dump(mode="json") for label in base.labels]
    new_names = {str(item["id"]): item.get("name") for item in labels}
    steps: list[JsonValue] = []
    decided: set[str] = set()
    for operation, sources, targets, strategy in edit.joins:
        source_ids, target_ids = _ids(old, sources), _ids(labels, targets)
        if source_ids and target_ids and not decided & set(source_ids):
            steps.append(
                {
                    "operation": operation,
                    "source_ids": list[JsonValue](source_ids),
                    "target_ids": list[JsonValue](target_ids),
                    "strategy": strategy,
                }
            )
            decided |= set(source_ids)
    for item in old:
        key = str(item["id"])
        if key in decided:
            continue
        if key not in new_names:
            steps.append({"operation": "delete", "source_ids": [key], "strategy": edit.strategy})
        elif new_names[key] != item["name"]:
            steps.append({"operation": "rename", "source_ids": [key], "target_ids": [key]})
    return steps


def _base(db: Database, current: LabelSet) -> LabelSet | None:
    """The published version a new or edited draft is compared with."""
    if current.published:
        return current
    if current.previous_version is None:
        return None
    return latest_label_set(db, current.id, current.previous_version)


def unnamed_labels(current: LabelSet, edit: SpokenEdit) -> list[str]:
    """Names the change removes or renames that the label set does not have."""
    labels: Labels = [label.model_dump(mode="json") for label in current.labels]
    named = [*edit.removes, *(old for old, _ in edit.renames)]
    named += [source for _, sources, _, _ in edit.joins for source in sources]
    return [name for name in dict.fromkeys(named) if _find(labels, name) is None]


class LabelEdit(BoundaryModel):
    """The full parameters of a label set step, or the spoken names it does not have."""

    params: dict[str, JsonValue]
    unknown: list[str] = Field(default_factory=list[str])
    existing: list[str] = Field(default_factory=list[str])


def prepare_label_edit(db: Database, params: dict[str, JsonValue]) -> LabelEdit:
    """Apply a spoken change to the latest version; new label sets only get label ids."""
    identifier = params.get("label_set_id")
    current = latest_label_set(db, identifier) if isinstance(identifier, str) else None
    if current is None or params.get("target", "label_set") != "label_set":
        adds = params.pop("add_labels", None)
        if "labels" in params or adds is not None:
            params["labels"] = with_label_ids([*_list(params.get("labels")), *_list(adds)])
        return LabelEdit(params=params)
    edit = spoken_edit(params)
    if unknown := unnamed_labels(current, edit):
        names = [label.name for label in current.labels]
        return LabelEdit(params=params, unknown=unknown, existing=names)
    labels = _apply(current, edit)
    params["labels"] = list[JsonValue](labels)
    params.setdefault("name", current.name)
    base = _base(db, current)
    params["migration"] = needed_migration(base, labels, edit) if base is not None else []
    if current.published:
        params["operation"] = "create"
        params["previous_version"] = current.version
        params.pop("version", None)
    else:
        params["operation"], params["version"] = "update", current.version
    if current.guidelines is not None and "guidelines" not in params:
        kept = {str(item["id"]) for item in labels}
        rules = [rule for rule in current.guidelines.rules if rule.label_id in kept]
        params["guidelines"] = current.guidelines.model_copy(
            update={"rules": tuple(rules)}
        ).model_dump(mode="json")
    return LabelEdit(params=params)


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
        after = LabelSet.model_validate(
            {
                **current.model_dump(mode="json"),
                "version": current.version + 1,
                "labels": labels,
                "migration": params.get("migration") or [],
            }
        )
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
