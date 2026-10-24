# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve and validate graph contracts from a checkout or installed wheel."""

from pathlib import Path

import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
from datakeel.core.models import BoundaryModel


def contracts_path() -> Path:
    """Locate the bundled graph schema, profiles and replay recordings."""
    package = Path(__file__).resolve().parents[1]
    source = package.parent / "contracts" / "kg"
    return source if source.exists() else package / "_contracts" / "kg"


def load_contract[Model: BoundaryModel](path: Path, model: type[Model]) -> Model:
    """Validate YAML and report file and field locations without echoing input secrets."""
    try:
        return model.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ModelValidationError as error:
        details = "; ".join(
            f"{path.name}:{'.'.join(map(str, item['loc'])) or 'document'}: {item['msg']}"
            for item in error.errors(include_input=False, include_url=False)
        )
        raise ValidationError(details) from error
    except (OSError, yaml.YAMLError) as error:
        msg = f"{path.name}:document: unable to read valid YAML"
        raise ValidationError(msg) from error


def load_schema(path: Path) -> KGSchema:
    """Load one validated schema from an explicit path."""
    return load_contract(path, KGSchema)


def load_profile(path: Path) -> ExtractionProfile:
    """Load one validated extraction profile from an explicit path."""
    return load_contract(path, ExtractionProfile)


def get_schema(identity: str = "business-knowledge") -> KGSchema:
    """Resolve a bundled schema identifier without interpreting it as a path."""
    for path in sorted(contracts_path().glob("*.yaml")):
        schema = load_schema(path)
        if schema.id == identity:
            return schema
    msg = f"Unknown graph schema: {identity}"
    raise NotFoundError(msg)


def get_profile(identity: str = "replay-demo") -> ExtractionProfile:
    """Resolve a bundled extraction profile identifier."""
    for path in sorted((contracts_path() / "profiles").glob("*.yaml")):
        profile = load_profile(path)
        if profile.id == identity:
            return profile
    msg = f"Unknown extraction profile: {identity}"
    raise NotFoundError(msg)
