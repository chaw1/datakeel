# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explainable directory, naming, and metadata compliance scores."""

import re
from pathlib import PurePosixPath
from typing import Any

from jsonschema.exceptions import ValidationError as SchemaValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.governance.models import ComplianceView
from datakeel.governance.validation import DEFAULT_TEMPLATE, template_schema, validation_errors

MAX_SCORE = 100


def compliance_score(
    dataset_name: str,
    files: list[FileItem],
    metadata: dict[str, Any],
    template: dict[str, Any] | None = None,
) -> ComplianceView:
    """Directory rules use manifest filenames, never private physical object-store paths."""
    selected = template if template is not None else DEFAULT_TEMPLATE
    schema = template_schema(selected)
    errors = validation_errors(schema.root, metadata)
    pattern = selected.get("naming_pattern", r"^[\w][\w .()-]*$")
    directory_pattern = selected.get("directory_pattern", r".*")
    try:
        naming = re.compile(pattern)
        directory = re.compile(directory_pattern)
    except (re.error, TypeError) as error:
        msg = "Invalid governance naming or directory pattern"
        raise ValidationError(msg) from error
    safe_paths: list[bool] = []
    for file in files:
        path = PurePosixPath(file.filename)
        safe_paths.append(
            bool(
                path.name
                and not path.is_absolute()
                and ".." not in path.parts
                and "\\" not in file.filename
                and directory.fullmatch(str(path.parent))
            )
        )
    directory_score = 100 * sum(safe_paths) / len(files) if files else 0
    names = [dataset_name, *(PurePosixPath(file.filename).name for file in files)]
    valid_names = sum(bool(naming.fullmatch(name)) for name in names)
    naming_score = 100 * valid_names / len(names)
    expected = set(schema.get("properties", {})) | set(schema.get("required", []))
    metadata_score = _metadata_score(schema.root, metadata, expected, errors)
    dimensions = _dimensions(
        (directory_score, naming_score, metadata_score),
        (sum(safe_paths), len(files), valid_names, len(names)),
        (directory_pattern, pattern),
        expected,
        [error.message for error in errors],
    )
    total = round(directory_score * 0.4 + naming_score * 0.3 + metadata_score * 0.3, 2)
    issues = [
        {
            "dimension": key,
            "message": f"{key} compliance is {value['score']}/100",
            "severity": "warning",
        }
        for key, value in dimensions.items()
        if value["score"] < MAX_SCORE
    ]
    return ComplianceView.model_validate(
        {"total": total, "dimensions": dimensions, "issues": issues}
    )


def _dimensions(
    scores: tuple[float, float, float],
    counts: tuple[int, int, int, int],
    patterns: tuple[str, str],
    expected: set[str],
    errors: list[str],
) -> dict[str, Any]:
    directory_score, naming_score, metadata_score = scores
    valid_paths, file_count, valid_names, name_count = counts
    directory_pattern, pattern = patterns
    return {
        "directory": {
            "score": round(directory_score, 2),
            "weight": 40,
            "details": {
                "valid_paths": valid_paths,
                "total": file_count,
                "pattern": directory_pattern,
            },
        },
        "naming": {
            "score": round(naming_score, 2),
            "weight": 30,
            "details": {"valid_names": valid_names, "total": name_count, "pattern": pattern},
        },
        "metadata": {
            "score": round(metadata_score, 2),
            "weight": 30,
            "details": {
                "expected_fields": sorted(expected),
                "errors": errors,
            },
        },
    }


def _metadata_score(
    schema: dict[str, Any],
    metadata: dict[str, Any],
    expected: set[str],
    errors: list[SchemaValidationError],
) -> float:
    if expected:
        invalid = {str(error.path[0]) for error in errors if error.path}
        absent = {field for field in schema.get("required", []) if field not in metadata}
        satisfied = {
            field
            for field in expected
            if field in metadata and field not in invalid and field not in absent
        }
        metadata_score = 100 * len(satisfied) / len(expected)
        # Whole-object constraints (oneOf, extra fields, dependentRequired, etc.) must also count.
        if any(not error.path and error.validator != "required" for error in errors):
            metadata_score = 0
    else:
        metadata_score = 0 if errors else 100
    return metadata_score
