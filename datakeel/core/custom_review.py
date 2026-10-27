# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parse review declarations without importing or evaluating submitted code."""

import ast
import hashlib

from pydantic import ValidationError as ModelValidationError

from datakeel.core.custom_operators import StaticCheck, SubmitCustomOperatorParams
from datakeel.core.custom_schema import validate_custom_schema
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument

_MAX_CODE_BYTES = 65536
_RUN_ARGUMENT_COUNT = 3
_RISK_MODULES = {
    "socket",
    "subprocess",
    "ctypes",
    "os",
    "sys",
    "multiprocessing",
    "urllib",
    "http",
    "requests",
    "importlib",
    "builtins",
    "pickle",
    "marshal",
    "resource",
    "datakeel",
}
_RISK_CALLS = {"eval", "exec", "compile", "__import__", "open", "system", "popen", "fork"}


def _schema(tree: ast.Module, name: str) -> JsonDocument:
    declarations = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    ]
    if len(declarations) != 1:
        msg = f"Code must declare exactly one literal {name} object"
        raise ValidationError(msg)
    try:
        schema = JsonDocument.model_validate(ast.literal_eval(declarations[0]))
        validate_custom_schema(schema)
    except (ValueError, TypeError, ModelValidationError) as exc:
        msg = f"{name} must be a valid literal JSON Schema object"
        raise ValidationError(msg) from exc
    return schema


def _checks(tree: ast.Module) -> tuple[StaticCheck, ...]:
    findings: list[StaticCheck] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [item.name.split(".", 1)[0] for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".", 1)[0]]
        elif isinstance(node, ast.Call):
            function = node.func
            names = [function.id] if isinstance(function, ast.Name) else []
            if isinstance(function, ast.Attribute):
                names = [function.attr]
        if not isinstance(node, ast.Import | ast.ImportFrom | ast.Call):
            continue
        findings.extend(
            StaticCheck(
                line=node.lineno,
                column=node.col_offset,
                code="risky_capability",
                message=f"Review use of {name}; static checks do not provide isolation",
            )
            for name in sorted(set(names) & (_RISK_MODULES | _RISK_CALLS))
        )
    return tuple(findings)


def prepare_submission(params: SubmitCustomOperatorParams) -> SubmitCustomOperatorParams:
    """Derive complete review material from exact UTF-8 bytes, ignoring caller claims."""
    if len(params.code.encode()) > _MAX_CODE_BYTES:
        msg = "Custom operator code exceeds 65536 UTF-8 bytes"
        raise ValidationError(msg)
    try:
        tree = ast.parse(params.code)
    except (SyntaxError, ValueError, RecursionError) as exc:
        msg = "Custom operator code is not valid Python"
        raise ValidationError(msg) from exc
    runs = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run"]
    if (
        len(runs) != 1
        or len(runs[0].args.args) != _RUN_ARGUMENT_COUNT
        or runs[0].args.vararg
        or runs[0].args.kwarg
        or runs[0].args.kwonlyargs
        or runs[0].args.posonlyargs
    ):
        msg = "Code must export run(inputs, params, ctx) with exactly three arguments"
        raise ValidationError(msg)
    return params.model_copy(
        update={
            "code_hash": hashlib.sha256(params.code.encode()).hexdigest(),
            "parameter_schema": _schema(tree, "PARAMETER_SCHEMA"),
            "metadata_schema": _schema(tree, "OUTPUT_METADATA_SCHEMA"),
            "static_checks": _checks(tree),
        }
    )
