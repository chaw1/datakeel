# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check a model's draft against the real sources and complete what it left out."""

from typing import Literal

from pydantic import Field
from pydantic import ValidationError as ModelValidationError

from datakeel.core.label_guidelines import GuidelineExample, LabelGuideline, LabelGuidelines
from datakeel.core.models import BoundaryModel
from datakeel.core.production_attributes import TemplateAttribute
from datakeel.core.production_catalog_models import ProductionLabel
from datakeel.label_drafts.answer import (
    DraftAnswer,
    ExampleAnswer,
    LabelAnswer,
    RuleAnswer,
    read_answer,
)
from datakeel.label_drafts.complete import Provenance, completed_labels, completed_rules, overview
from datakeel.label_drafts.models import DraftInputs, DraftOutcome
from datakeel.label_drafts.offline import build_labels, label_id

ExampleKind = Literal["positive", "negative"]


class Checked(BoundaryModel):
    """A usable outcome, if any, and the problems a repair round should fix."""

    outcome: DraftOutcome | None = None
    problems: list[str] = Field(default_factory=list[str])


def _fields(item: LabelAnswer) -> tuple[TemplateAttribute, ...]:
    fields: dict[str, TemplateAttribute] = {}
    for attribute in item.attributes:
        try:
            field = TemplateAttribute.model_validate(attribute.model_dump())
        except ModelValidationError:
            continue
        fields.setdefault(field.key, field)
    return tuple(fields.values())[:50]


def _filled(label: ProductionLabel, item: LabelAnswer) -> ProductionLabel:
    """Fill a source label's missing translation and attributes from the model's answer."""
    return label.model_copy(
        update={
            "name_zh": label.name_zh or item.name_zh or None,
            "name_en": label.name_en or item.name_en or None,
            "fields": label.fields or _fields(item),
        }
    )


def _merge(inputs: DraftInputs, answer: DraftAnswer) -> list[ProductionLabel]:
    baseline = build_labels(inputs)
    answered = {label_id(item.id): item for item in answer.labels}
    merged = [
        _filled(label, answered[label.id]) if label.id in answered else label for label in baseline
    ]
    known = {label.id for label in merged}
    names = {label.name.casefold() for label in merged}
    for item in answer.labels:
        identifier = label_id(item.id)
        name = item.name_zh if inputs.language == "zh" else (item.name_en or item.name_zh)
        if identifier in known or not name or name.casefold() in names:
            continue
        parent = label_id(item.parent_id) if item.parent_id else None
        merged.append(
            ProductionLabel(
                id=identifier,
                name=name,
                parent_id=parent if parent in known else None,
                name_zh=item.name_zh,
                name_en=item.name_en or None,
                fields=_fields(item),
            )
        )
        known.add(identifier)
        names.add(name.casefold())
    return merged


def _rule(rule: RuleAnswer, identifier: str, samples: set[str]) -> tuple[LabelGuideline, int]:
    examples: list[GuidelineExample] = []
    dropped = 0
    pairs: tuple[tuple[ExampleKind, list[ExampleAnswer]], ...] = (
        ("positive", rule.positive),
        ("negative", rule.negative),
    )
    for kind, values in pairs:
        for value in values[:5]:
            if value.sample_id in samples:
                examples.append(
                    GuidelineExample(sample_id=value.sample_id, kind=kind, note=value.note[:500])
                )
            else:
                dropped += 1
    guideline = LabelGuideline(
        label_id=identifier,
        text_zh=rule.text_zh[:4000],
        text_en=rule.text_en[:4000],
        examples=tuple(examples),
    )
    return guideline, dropped


def _unnamed(labels: list[ProductionLabel]) -> list[str]:
    return [
        f"label {label.id} ({label.name}): name_en missing" for label in labels if not label.name_en
    ]


def checked_outcome(inputs: DraftInputs, text: str, *, cut_off: bool = False) -> Checked:
    """Keep every source category, drop examples citing unknown samples, complete each label."""
    answer = read_answer(text)
    problems = list(answer.problems)
    if cut_off:
        problems.insert(0, "the answer was cut off at the output limit")
    if not answer.labels and not answer.rules:
        return Checked(problems=problems)
    labels = _merge(inputs, answer)
    problems += [item for item in _unnamed(labels) if item not in problems]
    known = {label.id for label in labels}
    samples = {sample.id for sample in inputs.samples}
    dropped = 0
    rules: dict[str, LabelGuideline] = {}
    for item in answer.rules:
        identifier = label_id(item.label_id)
        if identifier not in known or identifier in rules:
            continue
        rules[identifier], lost = _rule(item, identifier, samples)
        dropped += lost
    found = Provenance()
    labels = completed_labels(labels, found)
    completed = completed_rules(labels, rules, inputs, found)
    overview_zh, overview_en = overview(answer.overview_zh, answer.overview_en, found)
    guidelines = LabelGuidelines(overview_zh=overview_zh, overview_en=overview_en, rules=completed)
    outcome = DraftOutcome(labels=tuple(labels), guidelines=guidelines, dropped_examples=dropped)
    return Checked(outcome=outcome, problems=problems)
