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
