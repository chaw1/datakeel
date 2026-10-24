# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Match complete identifiers and metric names without substring inference."""

import re
import unicodedata

from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.kg_product import KGEntity
from datakeel.core.link_models import LinkMatch
from datakeel.core.metric_models import MetricCard, TermDefinition

_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:[./][A-Za-z][A-Za-z0-9_]*)*")
_STOP_WORDS = frozenset({"table", "tables", "the", "表"})


def catalog_identifiers(text: str) -> tuple[str, ...]:
    """Extract whole ASCII identifiers, retaining underscores and qualified segments."""
    return tuple(
        dict.fromkeys(
            match.group().lower()
            for match in _IDENTIFIER.finditer(text)
            if match.group().lower() not in _STOP_WORDS
        )
    )


def catalog_names(item: CatalogObject) -> tuple[str, ...]:
    """Return the three allowed exact spellings of a catalog table or view."""
    return tuple(
        dict.fromkeys(
            value.lower()
            for value in (
                item.name,
                f"{item.schema_name}.{item.name}" if item.schema_name else item.name,
                item.asset_ref.asset_id,
            )
        )
    )


def normalize_metric_name(value: str) -> str:
    """Normalize a complete spelling without changing registered vocabulary semantics."""
    return unicodedata.normalize("NFKC", value).lower().strip()


def _entity_metric_names(value: str) -> set[str]:
    value = normalize_metric_name(value)
    return {
        value,
        *(
            value.removesuffix(suffix).strip()
            for suffix in ("指标", "metric")
            if value.endswith(suffix)
        ),
    } - {""}


def _table_matches(spellings: tuple[str, ...], catalog: CatalogSnapshot) -> tuple[LinkMatch, ...]:
    identifiers = {identifier for value in spellings for identifier in catalog_identifiers(value)}
    return tuple(
        LinkMatch(
            target=item,
            basis=tuple(
                f"identifier {identifier} equals catalog name {identifier}"
                for identifier in sorted(identifiers.intersection(catalog_names(item)))
            ),
        )
        for item in catalog.objects
        if item.asset_ref.asset_type == "table" and identifiers.intersection(catalog_names(item))
    )


def _metric_vocabulary(
    catalog: CatalogSnapshot,
) -> dict[str, tuple[set[str], set[str]]]:
    vocabulary: dict[str, tuple[set[str], set[str]]] = {}
    for item in catalog.objects:
        if item.asset_ref.asset_type != "metric":
            continue
        metric = MetricCard.model_validate(item.properties.root).definition
        vocabulary[metric.id] = (
            {normalize_metric_name(metric.name), normalize_metric_name(metric.id)},
            {normalize_metric_name(name) for name in metric.synonyms},
        )
    for item in catalog.objects:
        if item.asset_ref.asset_type != "term":
            continue
        term = TermDefinition.model_validate(item.properties.root)
        if term.means.kind == "metric" and term.means.id in vocabulary:
            exact, synonyms = vocabulary[term.means.id]
            exact.add(normalize_metric_name(term.term))
            synonyms.update(normalize_metric_name(name) for name in term.synonyms)
    return vocabulary


def _metric_matches(spellings: tuple[str, ...], catalog: CatalogSnapshot) -> tuple[LinkMatch, ...]:
    names = {name for value in spellings for name in _entity_metric_names(value)}
    vocabulary = _metric_vocabulary(catalog)
    matches: list[LinkMatch] = []
    for item in catalog.objects:
        if item.asset_ref.asset_id not in vocabulary:
            continue
        exact, synonyms = vocabulary[item.asset_ref.asset_id]
        strongest = names.intersection(exact) or names.intersection(synonyms)
        if strongest:
            strength = "exact" if names.intersection(exact) else "synonym"
            matches.append(
                LinkMatch(
                    target=item,
                    strength=strength,
                    basis=tuple(
                        f"metric {name} equals {strength} name" for name in sorted(strongest)
                    ),
                )
            )
    return tuple(
        match
        for match in matches
        if match.strength == "exact" or not any(item.strength == "exact" for item in matches)
    )


def match_entity(
    entity: KGEntity, mentions: tuple[str, ...], catalog: CatalogSnapshot
) -> tuple[LinkMatch, ...]:
    """Associate supported entity types using only their own names and mention spans."""
    spellings = (entity.name, *mentions)
    if entity.type == "dataset":
        return _table_matches(spellings, catalog)
    if entity.type == "metric":
        return _metric_matches(spellings, catalog)
    return ()
