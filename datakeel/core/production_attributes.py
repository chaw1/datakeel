# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed template attribute fields and their validation against saved annotations."""

import math
from collections.abc import Iterable, Mapping
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel

AttributeType = Literal["boolean", "enum", "multi_enum", "number", "text"]
AttributeTarget = Literal["object", "record"]
_CHOICES = frozenset({"enum", "multi_enum"})


class AttributeOption(BoundaryModel):
    """Name one stored choice value of an enumerated attribute in both languages."""

    value: str = Field(min_length=1, max_length=100)
    name_zh: str = Field(min_length=1, max_length=100)
    name_en: str = Field(min_length=1, max_length=100)


class TemplateAttribute(BoundaryModel):
    """Define one typed attribute that a form renders and the server validates on save.

    ``object`` fields apply to every box, polygon and text span; ``record`` fields apply to the
    annotation record itself, which is how classification work carries attributes.
    """

    key: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    name_zh: str = Field(min_length=1, max_length=100)
    name_en: str = Field(min_length=1, max_length=100)
    type: AttributeType
    target: AttributeTarget = "object"
    required: bool = False
    default: JsonValue = None
    options: tuple[AttributeOption, ...] = Field(default=(), max_length=200)
    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    max_length: int = Field(default=200, ge=1, le=2000)

    @model_validator(mode="after")
    def consistent_definition(self) -> "TemplateAttribute":
        """Reject options, ranges or defaults that the field's type cannot use."""
        values = [option.value for option in self.options]
        if self.type in _CHOICES and (not values or len(set(values)) != len(values)):
            message = f'Attribute "{self.key}" needs distinct options'
            raise ValueError(message)
        if self.type not in _CHOICES and values:
            message = f'Attribute "{self.key}" of type {self.type} cannot have options'
            raise ValueError(message)
        ranged = self.minimum is not None or self.maximum is not None
        if ranged and self.type != "number":
            message = f'Attribute "{self.key}" can only bound a number'
            raise ValueError(message)
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            message = f'Attribute "{self.key}" minimum exceeds its maximum'
            raise ValueError(message)
        if self.default is not None and (problem := value_problem(self, self.default)):
            message = f'Attribute "{self.key}" default {problem}'
            raise ValueError(message)
        return self


def _number_problem(field: TemplateAttribute, value: JsonValue) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        number = True
    else:
        low = field.minimum is not None and value < field.minimum
        high = field.maximum is not None and value > field.maximum
        number = low or high
    if not number:
        return None
    if field.minimum is not None and field.maximum is not None:
        return f"must be a number between {field.minimum:g} and {field.maximum:g}"
    if field.minimum is not None:
        return f"must be a number of at least {field.minimum:g}"
    if field.maximum is not None:
        return f"must be a number of at most {field.maximum:g}"
    return "must be a number"


def value_problem(field: TemplateAttribute, value: JsonValue) -> str | None:
    """Explain why a present value does not fit the field, or return None when it fits."""
    choices = {option.value for option in field.options}
    if field.type == "boolean":
        return None if isinstance(value, bool) else "must be true or false"
    if field.type == "enum":
        valid = isinstance(value, str) and value in choices
        return None if valid else "must be one of " + ", ".join(sorted(choices))
    if field.type == "multi_enum":
        valid = (
            isinstance(value, list)
            and all(isinstance(item, str) and item in choices for item in value)
            and len({str(item) for item in value}) == len(value)
        )
        return None if valid else "must be distinct values of " + ", ".join(sorted(choices))
    if field.type == "number":
        return _number_problem(field, value)
    if not isinstance(value, str) or len(value) > field.max_length:
        return f"must be text of at most {field.max_length} characters"
    return None


def _missing(field: TemplateAttribute, values: Mapping[str, JsonValue]) -> bool:
    value = values.get(field.key)
    if value is None:
        return True
    if field.type == "multi_enum":
        return value == []
    return field.type == "text" and isinstance(value, str) and not value.strip()


def _check(
    fields: Iterable[TemplateAttribute],
    values: Mapping[str, JsonValue],
    place: str,
    *,
    complete: bool,
) -> None:
    for field in fields:
        if _missing(field, values):
            if complete and field.required:
                message = f'Attribute "{field.key}" is required on {place}'
                raise ValidationError(message)
            if values.get(field.key) is None:
                continue
        problem = value_problem(field, values[field.key])
        if problem is not None:
            message = f'Attribute "{field.key}" on {place} {problem}'
            raise ValidationError(message)


def validate_attributes(
    fields: Iterable[TemplateAttribute], annotation: AnnotationRecord, *, complete: bool = True
) -> None:
    """Check each defined field on the record and every shape; extra keys are left untouched.

    ``complete`` enforces required fields (human saves and submission). Model drafts are only
    type-checked, so an import never fails merely because a person has not filled a field yet.
    """
    defined = tuple(fields)
    record = [field for field in defined if field.target == "record"]
    shaped = [field for field in defined if field.target == "object"]
    _check(record, annotation.attributes, "the record", complete=complete)
    if not shaped:
        return
    for kind, shapes in (
        ("box", annotation.boxes),
        ("polygon", annotation.polygons),
        ("span", annotation.spans),
    ):
        for index, shape in enumerate(shapes or (), start=1):
            _check(shaped, shape.attributes, f"{kind} {index}", complete=complete)
