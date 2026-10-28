# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Round-trip and invalid contract tests bind YAML validation to its JSON Schema."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.standard_models import CodeEntry, CodeList, FieldStandard, StandardsContract
from datakeel.standards.loader import contract_schema, dump_contract, load_contract


def _standard() -> FieldStandard:
    return FieldStandard(
        code="x", name_zh="字段", name_en="field", description="Fixture", data_type="text"
    )


def test_example_roundtrip_matches_schema(contract: StandardsContract, tmp_path: Path) -> None:
    """The shipped enterprise contract validates and round-trips without losing metadata."""
    path = tmp_path / "roundtrip.yaml"
    path.write_text(dump_contract(contract))
    assert load_contract(path) == contract
    Draft202012Validator(contract_schema().root).validate(contract.model_dump(mode="json"))
    assert len(contract.standards) == 42
    assert len(contract.code_lists) == 6


def test_checked_in_schema_matches_current_contract() -> None:
    """The public JSON Schema is generated from the exact current boundary model."""
    schema = Path(__file__).resolve().parents[2] / "contracts/standards/standards.schema.json"
    assert json.loads(schema.read_text()) == contract_schema().root


@pytest.mark.parametrize(
    "text",
    [
        "standards: [{code: missing-fields}]",
        "standards: []\nunknown: true",
        "!!python/object/apply:builtins.print [unsafe]",
        "standards: [unclosed",
    ],
)
def test_invalid_yaml_import_fails_with_typed_error(tmp_path: Path, text: str) -> None:
    """Unsafe tags, syntax errors, unknown fields and incomplete definitions are rejected."""
    path = tmp_path / "bad.yaml"
    path.write_text(text)
    with pytest.raises(ValidationError, match="Invalid standards contract"):
        load_contract(path)


def test_missing_contract_fails_with_typed_error(tmp_path: Path) -> None:
    """Unreadable inputs do not escape as arbitrary I/O failures."""
    with pytest.raises(ValidationError):
        load_contract(tmp_path / "absent.yaml")


@pytest.mark.parametrize(
    "changes",
    [
        {"minimum": 2, "maximum": 1},
        {"precision": 2, "scale": 3},
        {"pattern": "[unclosed"},
        {"length": 0},
        {"version": 0},
        {"status": "invalid"},
        {"sensitivity": "unknown"},
    ],
)
def test_invalid_standard_constraints_are_rejected(changes: dict[str, object]) -> None:
    """Constraint contradictions fail before any import can change effective standards."""
    with pytest.raises(ModelValidationError):
        FieldStandard.model_validate({**_standard().model_dump(), **changes})


def test_duplicate_standard_codes_are_rejected() -> None:
    """Ambiguous identities cannot enter the catalog."""
    with pytest.raises(ModelValidationError, match="Duplicate"):
        StandardsContract(standards=(_standard(), _standard()))


def test_unknown_code_list_reference_is_rejected() -> None:
    """Reference data must exist in the same validated snapshot."""
    with pytest.raises(ModelValidationError, match="unknown code list"):
        StandardsContract(standards=(_standard().model_copy(update={"code_list": "missing"}),))


def test_duplicate_code_values_are_rejected() -> None:
    """Reference labels do not permit duplicate scalar identities."""
    entry = CodeEntry(value="a", label_zh="甲")
    with pytest.raises(ModelValidationError, match="Duplicate"):
        CodeList(code="a", name="A", entries=(entry, entry))


def test_duplicate_code_lists_across_files_are_rejected(tmp_path: Path) -> None:
    """Directory imports validate the merged namespace, not just individual files."""
    contract = StandardsContract(code_lists=(CodeList(code="a", name="A"),))
    for name in ("first.yaml", "second.yaml"):
        (tmp_path / name).write_text(dump_contract(contract))
    with pytest.raises(ValidationError, match="Duplicate"):
        load_contract(tmp_path)


def test_boundary_models_are_frozen_and_forbid_unknown_fields() -> None:
    """Both mutation and undeclared schema fields are blocked at boundaries."""
    definition = _standard()
    with pytest.raises(ModelValidationError):
        definition.code = "changed"
    with pytest.raises(ModelValidationError):
        FieldStandard.model_validate({**definition.model_dump(), "unrecognized": True})


def test_directory_import_resolves_references_across_files(tmp_path: Path) -> None:
    """Standard and code-list files may be maintained separately as one complete contract."""
    (tmp_path / "standard.yaml").write_text("""standards:
- code: status
  name_zh: 状态
  name_en: status
  description: Generated fixture
  data_type: string
  code_list: values
""")
    (tmp_path / "codes.yaml").write_text("code_lists: [{code: values, name: Values, entries: []}]")
    assert load_contract(tmp_path).standards[0].code_list == "values"


@pytest.mark.parametrize("status", ["draft", "deprecated"])
def test_active_standard_rejects_ineffective_reference_data(status: str) -> None:
    """An active dependency cannot silently survive the retirement of its code list."""
    codes = CodeList.model_validate({"code": "values", "name": "Values", "status": status})
    standard = _standard().model_copy(update={"status": "active", "code_list": "values"})
    with pytest.raises(ModelValidationError, match="active code list"):
        StandardsContract(standards=(standard,), code_lists=(codes,))


def test_retired_field_and_code_list_can_be_retired_in_one_contract() -> None:
    """Historical contracts retain resolvable references after their effective lifecycle ends."""
    codes = CodeList(code="values", name="Values", status="deprecated")
    standard = _standard().model_copy(update={"status": "deprecated", "code_list": "values"})
    assert StandardsContract(standards=(standard,), code_lists=(codes,)).code_lists == (codes,)


def test_duplicate_numeric_code_representations_are_rejected() -> None:
    """Equivalent numeric values cannot carry conflicting labels across SQL representations."""
    with pytest.raises(ModelValidationError, match="Duplicate"):
        CodeList(
            code="x",
            name="X",
            entries=(CodeEntry(value=1, label_zh="甲"), CodeEntry(value=1.0, label_zh="乙")),
        )


@pytest.mark.parametrize(
    "text",
    [
        "standards: []\nstandards: []\n",
        "standards:\n- code: first\n  code: replaced\n",
        "code_lists:\n- code: x\n  name: X\n  entries:\n  - value: first\n    value: replaced\n",
    ],
)
def test_duplicate_yaml_mapping_keys_are_rejected(tmp_path: Path, text: str) -> None:
    """Root, field and entry duplicates cannot silently replace validated user data."""
    path = tmp_path / "duplicates.yaml"
    path.write_text(text)
    with pytest.raises(ValidationError, match="Duplicate mapping key"):
        load_contract(path)
