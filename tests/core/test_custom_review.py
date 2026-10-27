# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Source review derives frozen schemas and warnings without executing user code."""

import hashlib

import pytest

from datakeel.core.custom_operators import SubmitCustomOperatorParams, custom_reference
from datakeel.core.custom_review import prepare_submission
from datakeel.core.errors import ValidationError

CODE = """PARAMETER_SCHEMA = {"type": "object", "additionalProperties": False}
OUTPUT_METADATA_SCHEMA = {"type": "object"}
def run(inputs, params, ctx):
    return []
"""


def test_prepare_when_valid_source_binds_exact_hash_and_schemas() -> None:
    """Whitespace edits have new identities while caller-provided review claims are replaced."""
    prepared = prepare_submission(SubmitCustomOperatorParams(name="filter", code=CODE))
    assert prepared.code_hash == hashlib.sha256(CODE.encode()).hexdigest()
    assert prepared.parameter_schema is not None
    assert prepared.metadata_schema is not None
    assert prepared.static_checks == ()
    changed = prepare_submission(SubmitCustomOperatorParams(name="filter", code=CODE + "\n"))
    assert changed.code_hash != prepared.code_hash
    assert custom_reference(f"custom.filter@{prepared.code_hash}") == ("filter", prepared.code_hash)


def test_prepare_when_risky_source_reports_lines_without_executing(tmp_path: object) -> None:
    """Top-level imports and side effects are inspected as syntax rather than imported."""
    code = 'import socket\nopen("never-created", "w")\n' + CODE
    prepared = prepare_submission(SubmitCustomOperatorParams(name="filter", code=code))
    assert [(check.line, check.code) for check in prepared.static_checks] == [
        (1, "risky_capability"),
        (2, "risky_capability"),
    ]


@pytest.mark.parametrize(
    "code",
    [
        "not valid Python:",
        CODE.replace("PARAMETER_SCHEMA =", "PARAMETER_SCHEMA = dict("),
        CODE.replace('"type": "object", "additionalProperties": False', '"type": "array"'),
        CODE.replace(
            '"type": "object", "additionalProperties": False',
            '"type": "object", "$ref": "https://example.com/schema"',
        ),
        CODE.replace(
            '"type": "object", "additionalProperties": False',
            '"type": "object", "$dynamicRef": "https://example.com/schema"',
        ),
        CODE.replace("def run(inputs, params, ctx)", "def run(inputs, params)"),
        CODE + "\nPARAMETER_SCHEMA = {}\n",
        "#" + "界" * 30000 + "\n" + CODE,
    ],
)
def test_prepare_when_invalid_source_rejects_before_publication(code: str) -> None:
    """Reject malformed code, dynamic schemas, remote references, and invalid entry points."""
    with pytest.raises(ValidationError):
        prepare_submission(SubmitCustomOperatorParams(name="filter", code=code))


@pytest.mark.parametrize(
    "reference", ["custom.filter", "custom.filter@latest", "custom.X@" + "a" * 64]
)
def test_reference_when_mutable_or_malformed_rejects(reference: str) -> None:
    """Every custom node must bind a lowercase name and a complete content hash."""
    with pytest.raises(ValidationError):
        custom_reference(reference)
