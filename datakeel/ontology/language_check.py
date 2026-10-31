# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Every registered action and read function must be sayable in Chinese and English.

The one-sentence entry reads only the registry, so an entry without phrases or examples
cannot be planned. Each entry needs at least one phrase and one example per language.
"""

from datakeel.ontology.models import ActionType, FunctionType, OntologyRegistry

LANGUAGES = ("zh", "en")


def _gaps(item: ActionType | FunctionType) -> list[str]:
    gaps: list[str] = []
    for language in LANGUAGES:
        if not [text for text in item.phrases.get(language, []) if text.strip()]:
            gaps.append(f"phrases.{language}")
        if not [text for text in item.examples.get(language, []) if text.strip()]:
            gaps.append(f"examples.{language}")
    return gaps


def missing_language(registry: OntologyRegistry) -> dict[str, list[str]]:
    """Map each incomplete action or function to what it lacks; empty means complete."""
    found: dict[str, list[str]] = {}
    for item in [*registry.actions, *registry.functions]:
        gaps = _gaps(item)
        if gaps:
            found[item.id] = gaps
    return found
