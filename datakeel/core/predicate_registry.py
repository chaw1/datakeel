# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Register evidence predicates once, including their declared object semantics."""

from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from datakeel.core.models import BoundaryModel


class Predicate(BoundaryModel):
    """Declare semantic relationship rules separately from lineage derivation."""

    id: str = Field(pattern=r"^[a-z_]+(?:\.[a-z_]+)*$")
    schema_version: Literal["1.0"] = "1.0"
    description: str
    object_kind: Literal["asset", "value"] = "value"
    object_asset_types: tuple[str, ...] = ()
    subject_asset_type: str | None = None
    existence: bool = True
    symmetric: bool = False
    transitive: Literal[False] = False


_PREDICATES = {
    item.id: item
    for item in (
        Predicate(id="mentions", description="Text explicitly mentions a concept"),
        Predicate(id="annotated_as", description="A sidecar explicitly labels an image region"),
        Predicate(id="label_gap", description="A mentioned concept lacks a supplied annotation"),
        Predicate(
            id="near_duplicate_of",
            description="A measured pair meets the hash-distance threshold",
            object_kind="asset",
            existence=False,
            symmetric=True,
        ),
        Predicate(id="corrupt", description="Decoding measures file corruption"),
        Predicate(
            id="ask.answers_with",
            description="A question is answered with a registered metric",
            object_kind="asset",
            object_asset_types=("metric",),
            subject_asset_type="question",
            existence=False,
        ),
        Predicate(
            id="ask.matched_term",
            description="A question matches a registered glossary term",
            object_kind="asset",
            object_asset_types=("term",),
            subject_asset_type="question",
            existence=False,
        ),
        Predicate(
            id="ask.unanswerable",
            description="No registered metric can answer the question",
            subject_asset_type="question",
        ),
        Predicate(
            id="link.maps_to",
            description="A graph entity corresponds to a catalog table or semantic metric",
            object_kind="asset",
            object_asset_types=("table", "metric"),
            subject_asset_type="kg_entity",
            existence=False,
        ),
        Predicate(
            id="ask.cites_asset",
            description="A knowledge answer cites a registered system or graph asset",
            object_kind="asset",
            object_asset_types=("metric", "table", "owner", "kg_entity"),
            subject_asset_type="question",
            existence=False,
        ),
        Predicate(
            id="ask.cites_assertion",
            description="A knowledge answer cites a relationship or association assertion",
            object_kind="asset",
            object_asset_types=("assertion",),
            subject_asset_type="question",
            existence=False,
        ),
    )
}


def register_predicate(definition: Predicate) -> None:
    """Add one stable declaration, rejecting incompatible redefinitions."""
    previous = _PREDICATES.get(definition.id)
    if previous is not None and previous != definition:
        msg = f"Predicate already has a different declaration: {definition.id}"
        raise ValueError(msg)
    _PREDICATES[definition.id] = definition


def registered_predicates() -> tuple[Predicate, ...]:
    """Return the current process-wide vocabulary in stable registration order."""
    return tuple(_PREDICATES.values())


def predicate(identifier: str) -> Predicate:
    """Look up a declaration and reject unregistered predicate identities."""
    if identifier not in _PREDICATES:
        msg = f"Unregistered evidence predicate: {identifier}"
        raise ValueError(msg)
    return _PREDICATES[identifier]


def validate_predicate(identifier: str) -> str:
    """Validate identities at every model boundary sharing PredicateId."""
    predicate(identifier)
    return identifier


PredicateId = Annotated[str, AfterValidator(validate_predicate)]
