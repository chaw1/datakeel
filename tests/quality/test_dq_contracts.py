# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Contract validation is shared by YAML, controlled writes and generated schema."""

import json
from pathlib import Path

import jsonschema
import pytest
import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.core.dq_models import DqContract, DqParameters, DqQueryLimits, DqRule, DqTarget
from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import QueryLimits
from datakeel.quality.dq_contracts import load_contract


def simple_rule() -> DqRule:
    """Return a minimal valid fixture independent from the engine tests."""
    return DqRule(
        id="required",
        name="Required value",
        kind="not_null",
        owner="quality-team",
        target=DqTarget(source_id="demo", table="orders", column="amount"),
    )


def test_example_contract_matches_json_schema_and_frozen_models() -> None:
    """The checked-in example is both machine-schema valid and directly executable."""
    folder = Path("contracts/quality-rules")
    payload = yaml.safe_load((folder / "example.yaml").read_text())
    schema = json.loads((folder / "schema.json").read_text())
    jsonschema.validate(payload, schema)
    assert load_contract(folder / "example.yaml").rules[0].kind == "range"
    assert schema == DqContract.model_json_schema(mode="validation")


@pytest.mark.parametrize(
    "text", ["version: [", "version: 1\nrules: []\nextra: true", "version: 2\nrules: []"]
)
def test_loader_rejects_invalid_yaml_or_unknown_fields(tmp_path: Path, text: str) -> None:
    """Parsing errors and boundary violations are clear domain validation failures."""
    path = tmp_path / "invalid.yaml"
    path.write_text(text)
    with pytest.raises(ValidationError, match="Invalid quality-rule"):
        load_contract(path)


def test_loader_missing_file_is_domain_failure(tmp_path: Path) -> None:
    """Unavailable local files cannot silently install an empty rule set."""
    with pytest.raises(ValidationError):
        load_contract(tmp_path / "missing.yaml")


def test_duplicate_contract_rule_ids_are_rejected() -> None:
    """One atomic import cannot ambiguously overwrite the same identifier twice."""
    with pytest.raises(ModelValidationError, match="unique"):
        DqContract(rules=(simple_rule(), simple_rule()))


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "range"},
        {"kind": "regex"},
        {"kind": "accepted_values"},
        {"kind": "referential_integrity"},
        {"kind": "sql_assertion"},
        {"target": DqTarget(source_id="demo", table="orders")},
        {"params": DqParameters(minimum=2, maximum=1)},
        {"params": DqParameters(reference_table="codes")},
        {"cron": "60 * * * *"},
        {"threshold": -1},
        {"timeout_ms": 0},
        {"max_rows": 100001},
        {"id": "group/range"},
        {"id": "rule with spaces"},
        {"id": "规则"},
    ],
)
def test_invalid_rule_configuration_is_rejected(changes: dict[str, object]) -> None:
    """Incomplete kind parameters and unsafe resource configuration fail at the boundary."""
    with pytest.raises(ModelValidationError):
        DqRule.model_validate(simple_rule().model_dump() | changes)


@pytest.mark.parametrize("pattern", ["(", "[", "a{99999999999999999999999999999999}"])
def test_unsafe_or_invalid_regex_is_rejected(pattern: str) -> None:
    """Malformed expressions and oversized repetition counts cannot be installed."""
    with pytest.raises(ModelValidationError):
        DqParameters(pattern=pattern)


@pytest.mark.parametrize("edges", [(), (1, 1), (2, 1)])
def test_psi_bins_require_strict_order(edges: tuple[float, ...]) -> None:
    """Historical histograms always share explicit strictly increasing bins."""
    with pytest.raises(ModelValidationError):
        DqParameters(bin_edges=edges)


def test_schedule_is_canonicalized_and_models_are_frozen() -> None:
    """Whitespace normalization does not change schedule meaning or permit later mutation."""
    rule = DqRule.model_validate(simple_rule().model_dump() | {"cron": " 0 9  * * * "})
    assert rule.cron == "0 9 * * *"
    with pytest.raises(ModelValidationError):
        rule.owner = "changed"


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("field", ["minimum", "maximum", "bin_edges", "values", "bindings"])
def test_rule_numeric_parameters_reject_nonfinite_values(number: float, field: str) -> None:
    """All numeric parameters, including nested enum values and SQL binds, remain JSON-safe."""
    value = (
        {"needle": number}
        if field == "bindings"
        else (number,)
        if field in {"bin_edges", "values"}
        else number
    )
    with pytest.raises(ModelValidationError):
        DqParameters.model_validate({field: value})


def test_explicit_quality_limits_preserve_interactive_metric_contract() -> None:
    """Large bounded quality scans never expand the existing interactive query boundary."""
    assert DqQueryLimits(max_rows=20000).max_rows == 20000
    assert DqQueryLimits().max_rows == DqRule.model_validate(simple_rule()).max_rows == 10000
    with pytest.raises(ModelValidationError):
        QueryLimits(max_rows=10001)
    with pytest.raises(ModelValidationError):
        DqQueryLimits(max_rows=100001)
