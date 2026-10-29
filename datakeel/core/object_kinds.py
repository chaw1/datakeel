# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One process-local registry supplies object kinds and their property schemas."""

import re

from pydantic import BaseModel

from datakeel.core.catalog_models import CATALOG_KINDS, CatalogObject
from datakeel.core.kg_product import KGEntity
from datakeel.core.production_kinds import PRODUCTION_KINDS
from datakeel.core.question_models import QuestionProperties

ObjectKind = str
LEGACY_OBJECT_KINDS = frozenset({"dataset", "version", "file", "artifact", "task"})
_KINDS: dict[str, type[BaseModel] | None] = {
    **dict.fromkeys(sorted(LEGACY_OBJECT_KINDS)),
    **dict.fromkeys(CATALOG_KINDS, CatalogObject),
    "question": QuestionProperties,
    "kg_entity": KGEntity,
    "image_transcript": None,
    "assertion": None,
    **PRODUCTION_KINDS,
}


def register_object_kind(kind: str, model: type[BaseModel] | None = None) -> None:
    """Register a stable kind together with an optional property schema."""
    if re.fullmatch(r"[a-z][a-z0-9_]*", kind) is None:
        msg = "Object kinds must be lowercase identifiers"
        raise ValueError(msg)
    _KINDS[kind] = model or _KINDS.get(kind)


def registered_object_kinds() -> tuple[str, ...]:
    """Return the only authoritative set of currently registered kind identities."""
    return tuple(_KINDS)


def object_property_model(kind: str) -> type[BaseModel] | None:
    """Read a registered kind's property schema, if its adapter has bound one."""
    validate_object_kind(kind)
    return _KINDS[kind]


def validate_object_kind(kind: str) -> str:
    """Reject an unknown kind at each ontology loading boundary."""
    if kind not in _KINDS:
        msg = f"Unregistered object kind: {kind}"
        raise ValueError(msg)
    return kind
