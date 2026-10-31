# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compact signatures of every action and read function for the planner's stable prompt.

The model sees each registered name with its top-level parameters, required ones marked
with ``*`` and short enumerations spelled out, so it never has to guess what an action can
set (for example that ``manage_users`` can change ``status``). Full schemas for the likely
actions follow in the volatile part, and more can be requested by name.
"""

import typing
from functools import lru_cache

from pydantic import JsonValue

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.ontology.functions import PARAMETER_MODELS

HIDDEN = frozenset({"request_id", "expected_revision", "prepared"})
ENUM_LIMIT = 9


def _literal(annotation: object) -> list[object] | None:
    if typing.get_origin(annotation) is typing.Literal:
        return list(typing.get_args(annotation))
    for argument in typing.get_args(annotation):
        found = _literal(argument)
        if found:
            return found
    return None


def signature(name: str) -> str:
    """``name(field*, field=a|b, ...)`` from the action's or function's parameter model.

    Actions list every parameter. Reads list their required ones and those with a short
    choice of values; ``...`` marks that more optional filters exist.
    """
    model = PARAMETER_TYPES.get(name) or PARAMETER_MODELS.get(name)
    if model is None:
        return name
    read = name not in PARAMETER_TYPES
    parts: list[str] = []
    for field, info in model.model_fields.items():
        if field in HIDDEN:
            continue
        if read and not info.is_required() and not _literal(info.annotation):
            if not parts or parts[-1] != "...":
                parts.append("...")
            continue
        values = _literal(info.annotation)
        shown = "=" + "|".join(map(str, values)) if values and len(values) <= ENUM_LIMIT else ""
        parts.append(f"{field}{'*' if info.is_required() else ''}{shown}")
    return f"{name}({', '.join(parts)})"


@lru_cache(maxsize=1)
def all_signatures() -> dict[str, str]:
    """Every registered action and read function by name."""
    return {name: signature(name) for name in [*PARAMETER_TYPES, *PARAMETER_MODELS]}


def choice_values(name: str, field: str) -> list[str]:
    """The allowed values of one parameter with a short fixed choice; empty otherwise."""
    model = PARAMETER_TYPES.get(name) or PARAMETER_MODELS.get(name)
    info = model.model_fields.get(field) if model is not None else None
    values = _literal(info.annotation) if info is not None else None
    return [str(value) for value in values] if values and len(values) <= ENUM_LIMIT else []


@lru_cache(maxsize=1)
def choice_fields() -> frozenset[str]:
    """Every action parameter that takes one of a short fixed choice of values."""
    return frozenset(
        name
        for model in PARAMETER_TYPES.values()
        for name, info in model.model_fields.items()
        if (values := _literal(info.annotation)) and len(values) <= ENUM_LIMIT
    )


def near_choice(name: str, field: str, value: JsonValue) -> JsonValue:
    """A choice written loosely ("task" for production_task, "packages") as the one it means.

    Only a value that fits exactly one allowed choice is replaced; anything else stays as
    written and is checked (and asked about) as usual.
    """
    model = PARAMETER_TYPES.get(name) or PARAMETER_MODELS.get(name)
    info = model.model_fields.get(field) if model is not None else None
    allowed = [str(item) for item in (_literal(info.annotation) or [])] if info else []
    if not isinstance(value, str) or not allowed or value in allowed:
        return value
    word = value.strip().casefold().replace(" ", "_").removesuffix("s")
    if not word:
        return value
    # The closest kind of match wins: "task" is production_task before task_package.
    tiers = (
        [item for item in allowed if item == word],
        [item for item in allowed if item.endswith(f"_{word}")],
        [item for item in allowed if item.startswith(f"{word}_")],
    )
    empty: list[str] = []
    found = next((tier for tier in tiers if tier), empty)
    return found[0] if len(found) == 1 else value


def _takes_list(annotation: object) -> bool:
    origin = typing.get_origin(annotation)
    if origin in {list, tuple, set, frozenset}:
        return True
    arguments = typing.get_args(annotation)
    return bool(arguments) and str not in arguments and any(map(_takes_list, arguments))


def near_value(name: str, field: str, value: JsonValue) -> JsonValue:
    """A value as the parameter takes it: one item said where a list is taken becomes a list.

    "the tank label is wrong" for ``issues`` is one issue, not a type error to ask about.
    A loosely written choice is matched as in :func:`near_choice`.
    """
    model = PARAMETER_TYPES.get(name) or PARAMETER_MODELS.get(name)
    info = model.model_fields.get(field) if model is not None else None
    scalar = isinstance(value, str | int | float) and not isinstance(value, bool)
    if info is not None and scalar and value != "" and _takes_list(info.annotation):
        return [value]
    return near_choice(name, field, value)
