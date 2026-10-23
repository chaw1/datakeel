# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check typed interpolation, deep overrides, frozen selections, and pure conditions."""

import pytest
from pydantic import JsonValue

from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.workflows.models import Comparison
from datakeel.workflows.resolver import compare, expression_errors, lookup, references, resolve


def test_references_preserve_types_and_format_embedded_values() -> None:
    """Complete references preserve JSON and templates format only explicit references."""
    inputs = JsonDocument({"name": "sample", "count": 3, "enabled": True, "nothing": None})
    outputs = JsonDocument({"read": {"rows": [[1, 2]]}})
    result = resolve(
        {
            "data": "${steps.read.rows.0}",
            "text": "${inputs.name}: ${inputs.count}/${inputs.enabled}/${inputs.nothing}",
            "values": ["${inputs.count}", 0.5],
        },
        inputs,
        outputs,
    )
    assert result == {"data": [1, 2], "text": "sample: 3/true/null", "values": [3, 0.5]}
    assert resolve("${steps.read}", inputs, outputs) == {"rows": [[1, 2]]}
    assert resolve("value=${steps.read}", inputs, outputs) == 'value={"rows": [[1, 2]]}'


def test_deep_merge_preserves_unmodified_metric_definition() -> None:
    """An override replaces one nested property while preserving the complete definition."""
    inputs = JsonDocument(
        {"override": {"measure": {"column": "list_amount"}, "caveats": ["changed"]}}
    )
    outputs = JsonDocument(
        {
            "current": {
                "definition": {
                    "id": "revenue",
                    "measure": {"table": "orders", "column": "paid_amount"},
                    "caveats": ["old"],
                }
            }
        }
    )
    result = resolve(
        {"$merge": ["${steps.current.definition}", "${inputs.override}"]}, inputs, outputs
    )
    assert result == {
        "id": "revenue",
        "measure": {"table": "orders", "column": "list_amount"},
        "caveats": ["changed"],
    }
    assert lookup(outputs.root, "current.definition.measure.column") == "paid_amount"


def test_pure_row_comparison_and_projection_do_not_evaluate_code() -> None:
    """Two row arrays and exact selected file ids remain independently inspectable."""
    inputs = JsonDocument({"rows": [[1], [2]]})
    outputs = JsonDocument(
        {"find": [{"asset_ref": {"asset_id": "a"}}, {"asset_ref": {"asset_id": "b"}}]}
    )
    assert resolve({"$rows_equal": ["${inputs.rows}", [[1], [2]]]}, inputs, outputs) is True
    assert resolve({"$equals": ["${inputs.rows}", [[2], [1]]]}, inputs, outputs) is False
    assert resolve({"$pluck": ["${steps.find}", "asset_ref.asset_id"]}, inputs, outputs) == [
        "a",
        "b",
    ]
    assert list(references({"a": ["${inputs.rows}", "before ${steps.find} after"]})) == [
        "inputs.rows",
        "steps.find",
    ]


INVALID_TEMPLATES: list[tuple[JsonValue, str]] = [
    ({"$merge": [[], {}]}, "merge requires two objects"),
    ({"$pluck": [{}, "name"]}, "pluck requires an array"),
    ({"$pluck": [[], "__import__('os')"]}, "literal property path"),
    ({"$rows_equal": [1, []]}, "two row arrays"),
    ({"$equals": []}, "exactly two arguments"),
    ({"$eval": ["x", 1]}, "unknown output function"),
    ({"$equals": [1, 1], "another": 2}, "unknown output function"),
    ("${inputs.missing}", "Unknown workflow reference"),
    ("${steps.list.7}", "Unknown workflow reference"),
    ("${inputs.name+1}", "malformed reference"),
]


@pytest.mark.parametrize(("value", "message"), INVALID_TEMPLATES)
def test_invalid_templates_fail_explicitly(value: JsonValue, message: str) -> None:
    """Malformed or unavailable expressions fail without executing arbitrary text."""
    with pytest.raises(ValidationError, match=message):
        resolve(value, JsonDocument({}), JsonDocument({"list": []}))


@pytest.mark.parametrize(
    ("left", "op", "right", "expected"),
    [
        (1, "eq", 1, True),
        (1, "ne", 1, False),
        (1, "lt", 2, True),
        (1, "lte", 1, True),
        (2, "gt", 1, True),
        (2, "gte", 2, True),
        ("a", "in", ["a", "b"], True),
    ],
)
def test_allowlisted_comparators(
    left: JsonValue, op: Comparison, right: JsonValue, *, expected: bool
) -> None:
    """Each supported comparison yields a deterministic Boolean without eval."""
    assert compare(left, op, right) is expected


@pytest.mark.parametrize(
    ("left", "op", "right"), [(1, "in", "1"), (True, "lt", 3), ("a", "gt", "b")]
)
def test_comparison_operand_errors(left: JsonValue, op: Comparison, right: JsonValue) -> None:
    """Type mistakes cannot acquire Python's bool-as-int or substring semantics."""
    with pytest.raises(ValidationError, match=r"requires?"):
        compare(left, op, right)


def test_nested_expression_validation_reports_all_errors() -> None:
    """Collect invalid nested references without touching their target values."""
    assert expression_errors(["${bad.ref}", {"value": "${inputs.wrong+1}"}]) == [
        "malformed reference",
        "malformed reference",
    ]
