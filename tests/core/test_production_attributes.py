# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Template attribute definitions, value rules and the field named in each rejection."""

import math

import pytest
from pydantic import JsonValue
from pydantic import ValidationError as SchemaError

from datakeel.core.annotation_models import (
    AnnotationBox,
    AnnotationPoint,
    AnnotationPolygon,
    AnnotationRecord,
)
from datakeel.core.errors import ValidationError
from datakeel.core.production_attributes import (
    TemplateAttribute,
    validate_attributes,
    value_problem,
)
from datakeel.core.production_catalog_models import ProductionTemplate
from tests.production_team_ops import failure

OPTIONS = [
    {"value": "car", "name_zh": "轿车", "name_en": "Car"},
    {"value": "bus", "name_zh": "公交", "name_en": "Bus"},
]


def _field(kind: str, **values: object) -> TemplateAttribute:
    choice = {"options": OPTIONS} if kind in {"enum", "multi_enum"} else {}
    return TemplateAttribute.model_validate(
        {"key": "field", "name_zh": "字段", "name_en": "Field", "type": kind, **choice, **values}
    )


@pytest.mark.parametrize(
    ("kind", "valid", "invalid"),
    [
        ("boolean", True, 1),
        ("enum", "bus", "truck"),
        ("multi_enum", ["car", "bus"], ["car", "car"]),
        ("number", 2.5, True),
        ("text", "ok", 3),
    ],
)
def test_each_attribute_type_accepts_its_values_and_names_the_rule(
    kind: str, valid: JsonValue, invalid: JsonValue
) -> None:
    """Every supported type accepts a well-typed value and explains a wrong one."""
    field = _field(kind)
    assert value_problem(field, valid) is None
    assert value_problem(field, invalid)


def test_number_range_text_length_and_finite_values_are_enforced() -> None:
    """Numbers stay finite and inside the declared range; text respects its length limit."""
    number = _field("number", minimum=0, maximum=10)
    assert value_problem(number, 0) is None
    assert value_problem(number, 10) is None
    assert value_problem(number, 10.5) == "must be a number between 0 and 10"
    assert value_problem(number, math.nan) == "must be a number between 0 and 10"
    assert value_problem(_field("number", minimum=1), 0) == "must be a number of at least 1"
    assert value_problem(_field("number", maximum=1), 2) == "must be a number of at most 1"
    text = _field("text", max_length=3)
    assert value_problem(text, "abc") is None
    assert value_problem(text, "abcd") == "must be text of at most 3 characters"
    assert value_problem(_field("multi_enum"), ["truck"])
    assert value_problem(_field("multi_enum"), "car")


@pytest.mark.parametrize(
    "definition",
    [
        {"type": "enum"},
        {"type": "multi_enum", "options": [OPTIONS[0], OPTIONS[0]]},
        {"type": "boolean", "options": OPTIONS},
        {"type": "text", "minimum": 1},
        {"type": "number", "minimum": 5, "maximum": 1},
        {"type": "enum", "options": OPTIONS, "default": "truck"},
        {"type": "number", "maximum": 3, "default": 4},
        {"type": "boolean", "key": "1bad"},
    ],
    ids=[
        "enum-without-options",
        "duplicate-options",
        "options-on-boolean",
        "range-on-text",
        "inverted-range",
        "default-outside-options",
        "default-outside-range",
        "key-not-identifier",
    ],
)
def test_inconsistent_definitions_are_rejected(definition: dict[str, object]) -> None:
    """Options, ranges and defaults must fit the declared type, and keys must be identifiers."""
    error = failure(
        lambda: TemplateAttribute.model_validate(
            {"key": "field", "name_zh": "字段", "name_en": "Field", **definition}
        )
    )
    assert isinstance(error, SchemaError)


def test_template_keys_are_distinct_per_target_and_old_templates_have_none() -> None:
    """A key is defined once per target, while record and object may reuse it."""
    base = {"id": "template", "name": "Template"}
    assert ProductionTemplate.model_validate(base).attributes == ()
    field = {"key": "k", "name_zh": "键", "name_en": "Key", "type": "boolean"}
    both = ProductionTemplate.model_validate(
        {**base, "attributes": [field, {**field, "target": "record"}]}
    )
    assert len(both.attributes) == 2
    with pytest.raises(SchemaError):
        ProductionTemplate.model_validate({**base, "attributes": [field, field]})


def _record(**values: object) -> AnnotationRecord:
    return AnnotationRecord.model_validate({"sample_id": "s", "annotator_id": "a", **values})


def _box(attributes: dict[str, JsonValue]) -> AnnotationBox:
    return AnnotationBox(category="cat", x1=0, y1=0, x2=1, y2=1, attributes=attributes)


def test_required_field_is_named_with_its_shape_position() -> None:
    """The rejection names the key and the 1-based shape that misses it."""
    fields = (_field("enum", key="kind", required=True),)
    polygon = AnnotationPolygon(
        category="cat",
        points=(AnnotationPoint(x=0, y=0), AnnotationPoint(x=1, y=0), AnnotationPoint(x=0, y=1)),
    )
    record = _record(polygons=[polygon.model_copy(update={"attributes": {"kind": "car"}}), polygon])
    with pytest.raises(ValidationError, match=r'^Attribute "kind" is required on polygon 2$'):
        validate_attributes(fields, record)
    with pytest.raises(ValidationError, match=r'^Attribute "kind" on box 1 must be one of'):
        validate_attributes(fields, _record(boxes=[_box({"kind": "truck"})]))


@pytest.mark.parametrize("empty", [None, [], "  "])
def test_empty_values_count_as_missing_for_required_fields(empty: JsonValue) -> None:
    """Null, an empty selection and blank text do not satisfy a required field."""
    kind = "text" if isinstance(empty, str) else "multi_enum"
    fields = (_field(kind, key="value", required=True),)
    with pytest.raises(ValidationError, match='"value" is required on box 1'):
        validate_attributes(fields, _record(boxes=[_box({"value": empty})]))


def test_record_fields_extra_keys_and_model_drafts() -> None:
    """Record fields check the record; extra keys stay; drafts skip only completeness."""
    fields = (
        _field("boolean", key="clear", target="record", required=True),
        _field("number", key="count", maximum=2),
    )
    complete = _record(attributes={"clear": True, "legacy": {"x": 1}}, boxes=[_box({"other": 1})])
    validate_attributes(fields, complete)
    with pytest.raises(ValidationError, match=r'^Attribute "clear" is required on the record$'):
        validate_attributes(fields, _record(labels=["cat"]))
    draft = _record(boxes=[_box({})])
    validate_attributes(fields, draft, complete=False)
    with pytest.raises(ValidationError, match='"count" on box 1 must be a number'):
        validate_attributes(fields, _record(boxes=[_box({"count": 3})]), complete=False)
