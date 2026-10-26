# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Strict YAML import/export for versioned field standards and reference data."""

from collections.abc import Hashable
from pathlib import Path
from typing import override

import yaml
from pydantic import ValidationError as ModelValidationError
from yaml.nodes import MappingNode, ScalarNode

from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.core.standard_models import (
    BusinessSynonyms,
    CodeList,
    FieldStandard,
    StandardsContract,
)


class _StrictLoader(yaml.SafeLoader):
    @override
    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Hashable, object]:
        seen: set[tuple[str, str]] = set()
        for key, _ in node.value:
            if not isinstance(key, ScalarNode):
                msg = "Contract mapping keys must be scalar values"
                raise yaml.YAMLError(msg)
            identity = (key.tag, key.value)
            if identity in seen:
                msg = "Duplicate mapping key in standards contract"
                raise yaml.YAMLError(msg)
            seen.add(identity)
        return super().construct_mapping(node, deep=deep)


class _ContractFragment(BoundaryModel):
    standards: tuple[FieldStandard, ...] = ()
    code_lists: tuple[CodeList, ...] = ()
    synonyms: tuple[BusinessSynonyms, ...] = ()


def _fragment(path: Path) -> _ContractFragment:
    loader = _StrictLoader(path.read_text())
    try:
        return _ContractFragment.model_validate(loader.get_single_data())
    finally:
        loader.dispose()


def load_contract(path: Path) -> StandardsContract:
    """Read one YAML contract or merge a directory and validate all references."""
    paths = sorted(path.glob("*.yaml")) if path.is_dir() else [path]
    contracts: list[_ContractFragment] = []
    try:
        contracts.extend(_fragment(item) for item in paths)
        return StandardsContract(
            standards=tuple(item for contract in contracts for item in contract.standards),
            code_lists=tuple(item for contract in contracts for item in contract.code_lists),
            synonyms=tuple(item for contract in contracts for item in contract.synonyms),
        )
    except (OSError, yaml.YAMLError, ModelValidationError) as exc:
        msg = f"Invalid standards contract: {exc}"
        raise ValidationError(msg) from exc


def dump_contract(contract: StandardsContract) -> str:
    """Serialize the complete validated contract to portable readable YAML."""
    return yaml.safe_dump(contract.model_dump(mode="json"), allow_unicode=True, sort_keys=False)


def contract_schema() -> JsonDocument:
    """Expose the same JSON Schema enforced by YAML import and HTTP requests."""
    return JsonDocument(StandardsContract.model_json_schema())
