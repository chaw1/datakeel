# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Strict YAML loading for the metric, dimension, and glossary contract."""

from pathlib import Path

import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import SemanticLayer


def load_layer(path: Path) -> SemanticLayer:
    """Read one YAML file or merge a directory of semantic contract files."""
    paths = sorted(path.glob("*.yaml")) if path.is_dir() else [path]
    documents: list[SemanticLayer] = []
    for item in paths:
        try:
            documents.append(SemanticLayer.model_validate(yaml.safe_load(item.read_text())))
        except (OSError, yaml.YAMLError, ModelValidationError) as exc:
            msg = f"Invalid semantic contract {item.name}: {exc}"
            raise ValidationError(msg) from exc
    layer = SemanticLayer(
        metrics=[metric for document in documents for metric in document.metrics],
        dimensions=[dimension for document in documents for dimension in document.dimensions],
        terms=[term for document in documents for term in document.terms],
        owners=[owner for document in documents for owner in document.owners],
    )
    validate_unique(layer)
    return layer


def validate_unique(layer: SemanticLayer) -> None:
    """Reject ambiguous duplicate identities across merged contract documents."""
    for kind, identities in (
        ("metric", [item.id for item in layer.metrics]),
        ("dimension", [item.id for item in layer.dimensions]),
        ("term", [item.term for item in layer.terms]),
        ("owner", [item.name for item in layer.owners]),
    ):
        if len(identities) != len(set(identities)):
            msg = f"Duplicate {kind} identity in semantic layer"
            raise ValidationError(msg)
