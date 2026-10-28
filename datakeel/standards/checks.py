# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate declared field constraints while retaining explicit missing-evidence rules."""

import math
import re
from collections.abc import Sequence
from decimal import Decimal

from datakeel.core.pii import detect_pii, redact_pii
from datakeel.core.standard_models import (
    CodeList,
    ColumnCheck,
    ColumnProfile,
    FieldStandard,
    StandardValue,
    StandardViolation,
    ViolationRule,
    standard_value_key,
)
from datakeel.standards.names import canonical_type, compatible_type

_SENSITIVITY = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
_MAX_SAMPLES = 3
_MAX_SAMPLE_LENGTH = 80


def _redact(value: StandardValue, standard: FieldStandard) -> str:
    if standard.sensitivity in {"confidential", "restricted"}:
        return "[REDACTED]"
    return redact_pii(str(value), replacement="[REDACTED]")[:_MAX_SAMPLE_LENGTH]


def _violation(
    rule: ViolationRule,
    values: Sequence[StandardValue],
    standard: FieldStandard,
    count: int | None = None,
) -> StandardViolation | None:
    total = len(values) if count is None else count
    if not total:
        return None
    samples = tuple(dict.fromkeys(_redact(value, standard) for value in values))[:_MAX_SAMPLES]
    return StandardViolation(
        rule=rule,
        count=total,
        samples=samples,
        message=f"{rule} constraint failed ({standard.code})",
    )


def _population(profile: ColumnProfile) -> int:
    return max(profile.row_count, len(profile.values), 1)


def _matches_type(value: StandardValue, expected: str) -> bool:
    if value is None:
        return True
    kind = canonical_type(expected)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return _numeric(value)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind in {"string", "date", "timestamp"}:
        return isinstance(value, str)
    return True


def _type(profile: ColumnProfile, standard: FieldStandard) -> StandardViolation | None:
    if not compatible_type(profile.data_type, standard.data_type):
        return _violation("type", [profile.data_type], standard, _population(profile))
    return _violation(
        "type",
        [value for value in profile.values if not _matches_type(value, standard.data_type)],
        standard,
    )


def _length(profile: ColumnProfile, standard: FieldStandard) -> StandardViolation | None:
    limit = standard.length
    if limit is None:
        return None
    if profile.length is not None and profile.length > limit:
        return _violation("length", [profile.length], standard, _population(profile))
    return _violation(
        "length",
        [value for value in profile.values if value is not None and len(str(value)) > limit],
        standard,
    )


def _numeric(value: StandardValue) -> bool:
    return (
        (isinstance(value, int) and not isinstance(value, bool))
        or (isinstance(value, float) and math.isfinite(value))
        or (isinstance(value, Decimal) and value.is_finite())
    )


def _too_precise(value: StandardValue, standard: FieldStandard) -> bool:
    if not _numeric(value):
        return False
    representation = Decimal(str(value)).as_tuple()
    exponent = representation.exponent
    if not isinstance(exponent, int):
        return True
    digits = representation.digits
    while digits and digits[-1] == 0:
        digits = digits[:-1]
        exponent += 1
    scale = max(-exponent, 0) if digits else 0
    integer_digits = max(len(digits) + exponent, 0) if digits else 0
    return (standard.scale is not None and scale > standard.scale) or (
        standard.precision is not None and integer_digits + scale > standard.precision
    )


def _precision(profile: ColumnProfile, standard: FieldStandard) -> StandardViolation | None:
    declared = (
        standard.precision is not None
        and profile.precision is not None
        and profile.precision > standard.precision
    ) or (
        standard.scale is not None and profile.scale is not None and profile.scale > standard.scale
    )
    if declared:
        return _violation("precision", [], standard, _population(profile))
    return _violation(
        "precision", [value for value in profile.values if _too_precise(value, standard)], standard
    )


def _value_checks(
    profile: ColumnProfile, standard: FieldStandard, code_lists: tuple[CodeList, ...]
) -> list[StandardViolation]:
    violations: list[StandardViolation] = []
    values = [value for value in profile.values if value is not None]
    code_list = next((item for item in code_lists if item.code == standard.code_list), None)
    if standard.code_list is not None:
        allowed: set[tuple[str, str]] = (
            {standard_value_key(entry.value) for entry in code_list.entries} if code_list else set()
        )
        invalid = [value for value in values if standard_value_key(value) not in allowed]
        if violation := _violation("code_list", invalid, standard):
            violations.append(violation)
    if standard.minimum is not None or standard.maximum is not None:
        invalid = [value for value in values if _outside(value, standard)]
        if violation := _violation("range", invalid, standard):
            violations.append(violation)
    if standard.pattern is not None:
        invalid = [value for value in values if re.fullmatch(standard.pattern, str(value)) is None]
        if violation := _violation("pattern", invalid, standard):
            violations.append(violation)
    return violations


def _outside(value: StandardValue, standard: FieldStandard) -> bool:
    if not _numeric(value):
        return True
    number = Decimal(str(value))
    return (standard.minimum is not None and number < Decimal(str(standard.minimum))) or (
        standard.maximum is not None and number > Decimal(str(standard.maximum))
    )


def _required(profile: ColumnProfile, standard: FieldStandard) -> StandardViolation | None:
    if not standard.required:
        return None
    nulls = [value for value in profile.values if value is None or value == ""]
    return _violation("required", nulls, standard, max(profile.null_count, len(nulls)))


def _sensitivity(profile: ColumnProfile, standard: FieldStandard) -> StandardViolation | None:
    detected = _SENSITIVITY[profile.sensitivity] if profile.sensitivity is not None else 0
    if any(isinstance(value, str) and detect_pii(value) for value in profile.values):
        detected = max(detected, _SENSITIVITY["confidential"])
    if detected > _SENSITIVITY[standard.sensitivity]:
        return _violation("sensitivity", [], standard, _population(profile))
    return None


def _rules(standard: FieldStandard) -> tuple[ViolationRule, ...]:
    rules: list[ViolationRule] = ["type", "sensitivity"]
    configured: tuple[tuple[ViolationRule, bool], ...] = (
        ("length", standard.length is not None),
        ("precision", standard.precision is not None or standard.scale is not None),
        ("code_list", standard.code_list is not None),
        ("range", standard.minimum is not None or standard.maximum is not None),
        ("pattern", standard.pattern is not None),
        ("required", standard.required),
        ("unit", standard.unit is not None),
    )
    for rule, enabled in configured:
        if enabled:
            rules.append(rule)
    return tuple(rules)


def _unavailable(profile: ColumnProfile, rule: ViolationRule) -> bool:
    if rule == "unit":
        return profile.unit is None
    if rule == "type":
        return bool(
            not profile.data_type or canonical_type(profile.data_type) in {"unknown", "null"}
        )
    if profile.values:
        return False
    available = {
        "type": bool(profile.data_type),
        "unit": profile.unit is not None,
        "length": profile.length is not None,
        "precision": profile.precision is not None or profile.scale is not None,
        "required": profile.row_count > 0,
        "sensitivity": profile.sensitivity is not None,
    }
    return not available.get(rule, False)


def _evaluate_rules(
    profile: ColumnProfile,
    standard: FieldStandard,
    code_lists: tuple[CodeList, ...],
    checked: tuple[ViolationRule, ...],
) -> list[StandardViolation]:
    violations = [
        violation
        for violation in (
            _type(profile, standard),
            _length(profile, standard),
            _precision(profile, standard),
            _required(profile, standard),
            _sensitivity(profile, standard),
        )
        if violation is not None and violation.rule in checked
    ]
    violations.extend(_value_checks(profile, standard, code_lists))
    if "unit" in checked and profile.unit != standard.unit:
        violation = _violation("unit", [profile.unit], standard, _population(profile))
        if violation is not None:
            violations.append(violation)
    return violations


def check_column(
    profile: ColumnProfile, standard: FieldStandard, code_lists: tuple[CodeList, ...] = ()
) -> ColumnCheck:
    """Check observed rows and metadata, redact samples and state unavailable evidence."""
    if standard.status != "active":
        return ColumnCheck(
            column_id=profile.column_id,
            standard_code=standard.code,
            row_count=max(profile.row_count, len(profile.values)),
            skipped_rules=(f"standard_status: {standard.status} is ineffective",),
        )
    rules = _rules(standard)
    checked: tuple[ViolationRule, ...] = tuple(
        rule for rule in rules if not _unavailable(profile, rule)
    )
    violations = _evaluate_rules(profile, standard, code_lists, checked)
    if profile.sensitivity in {"confidential", "restricted"}:
        violations = [
            item.model_copy(update={"samples": ("[REDACTED]",) if item.samples else ()})
            for item in violations
        ]
    observed_rows = max(profile.row_count, len(profile.values))
    skipped = tuple(f"{rule}: no observed evidence" for rule in rules if rule not in checked)
    if profile.truncated:
        skipped += (f"source_population: truncated after {observed_rows} observed rows",)
    return ColumnCheck(
        column_id=profile.column_id,
        standard_code=standard.code,
        row_count=observed_rows,
        violations=tuple(violations),
        checked_rules=checked,
        skipped_rules=skipped,
    )
