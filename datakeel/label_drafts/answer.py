# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read a model's draft leniently: common field-name slips are mapped, broken items listed."""

import json
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic import ValidationError as ModelValidationError

_ZH = ("name_cn", "cn_name", "zh_name", "zh", "cn", "chinese", "chinese_name", "label_zh")
_EN = ("en", "en_name", "english", "english_name", "label_en")
_NAMES = {**dict.fromkeys(_ZH, "name_zh"), **dict.fromkeys(_EN, "name_en")}
LABEL_ALIASES = {
    **_NAMES,
    **dict.fromkeys(("key", "code", "label_id", "value"), "id"),
    **dict.fromkeys(("parent", "parent_key", "parent_code", "parent_label"), "parent_id"),
    **dict.fromkeys(("attrs", "fields", "properties"), "attributes"),
}
ATTRIBUTE_ALIASES = {
    **_NAMES,
    **dict.fromkeys(("id", "code", "field", "attribute"), "key"),
    **dict.fromkeys(("data_type", "kind", "value_type"), "type"),
    **dict.fromkeys(("values", "choices", "enum", "enum_values"), "options"),
}
OPTION_ALIASES = {**_NAMES, **dict.fromkeys(("id", "key", "code"), "value")}
RULE_ALIASES = {
    **dict.fromkeys(("label", "id", "key", "label_key"), "label_id"),
    **dict.fromkeys(("rule_zh", "guideline_zh", "zh", "description_zh", "text_cn"), "text_zh"),
    **dict.fromkeys(("rule_en", "guideline_en", "en", "description_en"), "text_en"),
    **dict.fromkeys(("positives", "positive_examples", "examples_positive"), "positive"),
    **dict.fromkeys(("negatives", "negative_examples", "examples_negative"), "negative"),
}
EXAMPLE_ALIASES = {
    **dict.fromkeys(("id", "sample", "file_id"), "sample_id"),
    **dict.fromkeys(("reason", "why", "description"), "note"),
}
ANSWER_ALIASES = {
    **dict.fromkeys(("label_tree", "tags", "categories"), "labels"),
    **dict.fromkeys(("guidelines", "label_rules"), "rules"),
    **dict.fromkeys(("overview_cn", "summary_zh"), "overview_zh"),
    **dict.fromkeys(("summary_en",), "overview_en"),
}


class _Loose(BaseModel):
    """Model answers may carry extra keys; only the declared ones are read."""

    model_config = ConfigDict(extra="ignore")


class AttributeAnswer(_Loose):
    """One attribute definition as the model wrote it."""

    key: str
    name_zh: str
    name_en: str
    type: str = "text"
    options: list[dict[str, str]] = Field(default_factory=list[dict[str, str]])
    required: bool = False


class LabelAnswer(_Loose):
    """One label as the model wrote it."""

    id: str
    name_zh: str
    name_en: str = ""
    parent_id: str | None = None
    attributes: list[AttributeAnswer] = Field(default_factory=list[AttributeAnswer])


class ExampleAnswer(_Loose):
    """One cited sample."""

    sample_id: str
    note: str = ""


class RuleAnswer(_Loose):
    """One label's written rule with cited examples."""

    label_id: str
    text_zh: str = ""
    text_en: str = ""
    positive: list[ExampleAnswer] = Field(default_factory=list[ExampleAnswer])
    negative: list[ExampleAnswer] = Field(default_factory=list[ExampleAnswer])


class DraftAnswer(_Loose):
    """The usable parts of one answer and what could not be read."""

    labels: list[LabelAnswer] = Field(default_factory=list[LabelAnswer])
    overview_zh: str = ""
    overview_en: str = ""
    rules: list[RuleAnswer] = Field(default_factory=list[RuleAnswer])
    problems: list[str] = Field(default_factory=list[str])


def _renamed(data: dict[str, JsonValue], aliases: dict[str, str]) -> dict[str, JsonValue]:
    """Map a misspelt field to its schema name unless the right name is also present."""
    renamed = dict(data)
    for key, value in data.items():
        target = aliases.get(key.casefold())
        if target and target not in renamed:
            renamed[target] = value
    if isinstance(name := renamed.get("name"), str) and name:
        renamed.setdefault("name_en" if name.isascii() else "name_zh", name)
    return renamed


def _brief(error: ModelValidationError) -> str:
    parts = [
        f"{'.'.join(str(part) for part in item['loc']) or 'value'} {item['msg']}"
        for item in error.errors()[:3]
    ]
    return "; ".join(parts)


def _items[Item: _Loose](
    raw: JsonValue,
    model: type[Item],
    where: str,
    problems: list[str],
    prepare: Callable[[JsonValue, str], JsonValue],
) -> list[Item]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        problems.append(f"{where}: expected a list")
        return []
    kept: list[Item] = []
    for index, item in enumerate(raw):
        data = prepare(item, f"{where}[{index}]")
        if not isinstance(data, dict):
            problems.append(f"{where}[{index}]: expected an object")
            continue
        try:
            kept.append(model.model_validate(data))
        except ModelValidationError as error:
            problems.append(f"{where}[{index}]: {_brief(error)}")
    return kept


def _option(item: JsonValue, _where: str) -> JsonValue:
    if isinstance(item, str | int | float) and not isinstance(item, bool):
        text = str(item)
        return {"value": text, "name_zh": text, "name_en": text}
    if not isinstance(item, dict):
        return item
    option = _renamed(item, OPTION_ALIASES)
    value = str(option.get("value") or option.get("name_en") or option.get("name_zh") or "")
    return {
        "value": value,
        "name_zh": str(option.get("name_zh") or value),
        "name_en": str(option.get("name_en") or value),
    }


def _attribute(problems: list[str]) -> Callable[[JsonValue, str], JsonValue]:
    def prepare(item: JsonValue, where: str) -> JsonValue:
        if not isinstance(item, dict):
            return item
        attribute = _renamed(item, ATTRIBUTE_ALIASES)
        options = _items_raw(attribute.get("options"), where + ".options", problems, _option)
        return {**attribute, "options": options}

    return prepare


def _items_raw(
    raw: JsonValue,
    where: str,
    problems: list[str],
    prepare: Callable[[JsonValue, str], JsonValue],
) -> list[JsonValue]:
    if not isinstance(raw, list):
        if raw is not None:
            problems.append(f"{where}: expected a list")
        return []
    return [prepare(item, f"{where}[{index}]") for index, item in enumerate(raw)]


def _label(problems: list[str]) -> Callable[[JsonValue, str], JsonValue]:
    def prepare(item: JsonValue, where: str) -> JsonValue:
        if not isinstance(item, dict):
            return item
        label = _renamed(item, LABEL_ALIASES)
        attributes = _items(
            label.get("attributes"),
            AttributeAnswer,
            where + ".attributes",
            problems,
            _attribute(problems),
        )
        return {**label, "attributes": [value.model_dump() for value in attributes]}

    return prepare


def _example(item: JsonValue, _where: str) -> JsonValue:
    if isinstance(item, str):
        return {"sample_id": item}
    return _renamed(item, EXAMPLE_ALIASES) if isinstance(item, dict) else item


def _rule(problems: list[str]) -> Callable[[JsonValue, str], JsonValue]:
    def prepare(item: JsonValue, where: str) -> JsonValue:
        if not isinstance(item, dict):
            return item
        rule = _renamed(item, RULE_ALIASES)
        for kind in ("positive", "negative"):
            kept = _items(rule.get(kind), ExampleAnswer, f"{where}.{kind}", problems, _example)
            rule[kind] = [{"sample_id": value.sample_id, "note": value.note} for value in kept]
        return rule

    return prepare


def _object(text: str) -> dict[str, JsonValue] | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        value: JsonValue = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def read_answer(text: str) -> DraftAnswer:
    """Keep every readable label and rule; list what was cut off, missing or malformed."""
    found = _object(text)
    if found is None:
        return DraftAnswer(problems=["the answer is not one complete JSON object"])
    data = _renamed(found, ANSWER_ALIASES)
    problems: list[str] = []
    labels = _items(data.get("labels"), LabelAnswer, "labels", problems, _label(problems))
    rules = _items(data.get("rules"), RuleAnswer, "rules", problems, _rule(problems))
    if not labels and not rules:
        problems.append("labels: no usable label")
    return DraftAnswer(
        labels=labels,
        overview_zh=str(data.get("overview_zh") or ""),
        overview_en=str(data.get("overview_en") or ""),
        rules=rules,
        problems=problems,
    )
