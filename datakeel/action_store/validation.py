# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fail startup or generation on broken owners, references and stage contracts."""

from importlib import import_module
from inspect import signature
from typing import cast, get_args, get_type_hints

from pydantic import BaseModel
from sqlalchemy.orm import Session

from datakeel.actions.authorization import AUTHORIZATION, authorization_for
from datakeel.actions.declarations import ActionFrame
from datakeel.actions.file_declarations import active_declarations
from datakeel.actions.ir import action_ir, vocabulary
from datakeel.actions.models import ActionName, ActionPlan, OperationResult
from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.actions.registry import POLICIES
from datakeel.core.errors import ValidationError
from datakeel.storage.database import Database


def validate_declarations() -> None:
    """Check complete ownership and closed structure before any surface accepts requests."""
    declarations = active_declarations()
    owners = set(POLICIES) | set(declarations)
    if (
        owners != set(PARAMETER_TYPES)
        or owners != set(AUTHORIZATION) | set(declarations)
        or not set(get_args(ActionName)) <= owners
    ):
        msg = "Action owner, parameter or authorization inventory is incomplete"
        raise ValidationError(msg)
    assets = vocabulary()
    for declaration in declarations.values():
        _immutable(declaration)
        authorization_for(declaration.id)
        if declaration.inverse and declaration.inverse not in owners:
            msg = "Dangling inverse action reference"
            raise ValidationError(msg)
        for node in (*declaration.preconditions, *declaration.effects):
            if node.asset not in (*assets.public, *assets.references):
                msg = "Unknown internal asset kind"
                raise ValidationError(msg)
        for example in declaration.examples:
            declaration.params.model_validate(example.params.model_dump())
        _handlers(declaration.handlers.module, declaration.handlers.model_dump())
    action_ir()


def _handlers(module_name: str, values: dict[str, object]) -> None:
    module = import_module(module_name)
    for phase, names in values.items():
        if phase == "module" or names is None:
            continue
        for name in cast("tuple[object, ...]", names) if isinstance(names, tuple) else (names,):
            if not isinstance(name, str):
                msg = "Invalid lifecycle handler identity"
                raise ValidationError(msg)
            handler = getattr(module, name, None)
            expected = (
                (Database, ActionPlan, str, OperationResult)
                if phase == "deferred"
                else (Session, ActionFrame, ActionFrame)
            )
            if (
                not callable(handler)
                or tuple(get_type_hints(handler).values()) != expected
                or len(signature(handler).parameters) != len(expected) - 1
            ):
                msg = "Missing or untyped declared lifecycle handler"
                raise ValidationError(msg)


def _immutable(value: object) -> None:
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            _immutable(getattr(value, name))
    elif isinstance(value, tuple):
        for item in cast("tuple[object, ...]", value):
            _immutable(item)
    if isinstance(value, list | dict | set):
        msg = "Declaration collections must be immutable tuples"
        raise ValidationError(msg)
