# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject malformed graph vocabularies and unsafe transport configurations early."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation, ExtractionProfile
from datakeel.kg import loader


def _schema() -> dict[str, object]:
    return {
        "id": "sample",
        "version": "1",
        "entity_types": [{"name": "Company", "description": "A company"}],
        "relations": [
            {
                "name": "owns",
                "description": "Ownership",
                "domain": ["Company"],
                "range": ["Company"],
            }
        ],
        "rules": ["Extract current facts"],
        "examples": [
            {
                "text": "Acme owns Example.",
                "entities": [{"name": "Acme", "type": "Company"}],
                "relations": [
                    {
                        "head": "Acme",
                        "relation": "owns",
                        "tail": "Example",
                        "evidence": "Acme owns Example.",
                    }
                ],
            }
        ],
    }


def _write(path: Path, content: object) -> Path:
    path.write_text(yaml.safe_dump(content), encoding="utf-8")
    return path


def test_schema_load_valid_contract_preserves_types(tmp_path: Path) -> None:
    """A checked vocabulary remains frozen after loading."""
    definition = loader.load_schema(_write(tmp_path / "schema.yaml", _schema()))
    assert definition.relations[0].domain == ("Company",)


@pytest.mark.parametrize(
    ("field", "replacement", "expected"),
    [
        (
            "relations",
            [{"name": "owns", "description": "Own", "domain": ["Missing"], "range": ["Company"]}],
            "relations.0.domain",
        ),
        (
            "relations",
            [{"name": "owns", "description": "Own", "domain": ["Company"], "range": ["Missing"]}],
            "relations.0.range",
        ),
        (
            "entity_types",
            [{"name": "Company", "description": "A"}, {"name": "Company", "description": "B"}],
            "entity_types: duplicate",
        ),
        (
            "examples",
            [
                {
                    "text": "Acme",
                    "relations": [
                        {"head": "A", "relation": "owns", "tail": "B", "evidence": "Invented"}
                    ],
                }
            ],
            "examples.0.relations.evidence",
        ),
    ],
)
def test_schema_invalid_fields_are_located(
    tmp_path: Path, field: str, replacement: object, expected: str
) -> None:
    """Schema errors name both the source file and the semantic field."""
    content = _schema()
    content[field] = replacement
    with pytest.raises(ValidationError, match=rf"schema.yaml:.*{expected}"):
        loader.load_schema(_write(tmp_path / "schema.yaml", content))


@pytest.mark.parametrize(
    "settings",
    [
        {"api_key": "secret-value"},
        {"request_parameters": {"api_key": "secret-value"}},
        {"output_method": "unknown"},
        {"request_parameters": {"thinking": {"type": "disabled", "api_key": "secret-value"}}},
        {"request_parameters": {"enable_thinking": "secret-value"}},
        {"request_parameters": {"num_ctx": -1}},
        {"request_parameters": {"num_ctx": 8192}},
        {"request_parameters": {"reasoning_effort": "secret-value"}},
        {"request_parameters": {"thinking": "secret-value"}},
        {"api_key_env": "secret-value"},
        {"base_url": "https://secret@example.test/v1"},
        {"base_url": "https://example.test/v1?api_key=secret-value"},
        {"base_url": "file:///tmp/socket"},
        {"chunk_size": 20, "chunk_overlap": 20},
        {"extractor": "replay"},
        {"extractor": "llm", "provider": "ollama"},
    ],
)
def test_profile_invalid_settings_rejected_without_secret_echo(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    """Only declared parameters and environment variable identifiers cross the boundary."""
    content = {"id": "fake", "extractor": "fake", "provider": "fake", "model": "fake", **settings}
    with pytest.raises(ValidationError) as caught:
        loader.load_profile(_write(tmp_path / "profile.yaml", content))
    assert "secret-value" not in str(caught.value)


def test_profile_allowed_parameters_validated() -> None:
    """The allowlist covers explicit thinking controls accepted by the provider API."""
    profile = ExtractionProfile(
        id="local",
        extractor="llm",
        provider="openai",
        model="sample",
        base_url="http://localhost:11434/v1",
        api_key_env="EXAMPLE_MODEL_KEY",
        request_parameters={"enable_thinking": False, "reasoning_effort": "none"},
    )
    assert profile.request_parameters["enable_thinking"] is False


def test_contract_read_error_redacts_source(tmp_path: Path) -> None:
    """Unreadable and malformed YAML has a stable located error."""
    with pytest.raises(ValidationError, match="document: unable"):
        loader.load_schema(tmp_path / "absent.yaml")
    path = tmp_path / "invalid.yaml"
    path.write_text("[not: valid", encoding="utf-8")
    with pytest.raises(ValidationError, match="document: unable"):
        loader.load_schema(path)


def test_bundled_identifiers_do_not_accept_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Public lookup compares IDs against a fixed contract directory."""
    _write(tmp_path / "schema.yaml", _schema())
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    _write(
        profiles / "fake.yaml",
        {"id": "fake", "extractor": "fake", "provider": "fake", "model": "fake"},
    )
    monkeypatch.setattr(loader, "contracts_path", lambda: tmp_path)
    assert loader.get_schema("sample").id == "sample"
    assert loader.get_profile("fake").id == "fake"
    with pytest.raises(NotFoundError):
        loader.get_schema("../sample")
    with pytest.raises(NotFoundError):
        loader.get_profile("../fake")


def test_blank_entity_and_endpoint_names_are_rejected() -> None:
    """Empty normalized names cannot match arbitrary declared endpoints by containment."""
    with pytest.raises(ModelValidationError):
        ExtractedEntity(name=" \t ", type="organization")
    with pytest.raises(ModelValidationError):
        ExtractedRelation(head=" ", relation="uses", tail="Widget", evidence="quote")


def test_repeated_domain_names_are_rejected(tmp_path: Path) -> None:
    """Duplicate endpoint type options cannot make a unique type look ambiguous."""
    content = _schema()
    content["relations"] = [
        {
            "name": "owns",
            "description": "Own",
            "domain": ["Company", "Company"],
            "range": ["Company"],
        }
    ]
    with pytest.raises(ValidationError, match="duplicate entity type"):
        loader.load_schema(_write(tmp_path / "schema.yaml", content))


@pytest.mark.parametrize("name", ["mentions", "same_as"])
def test_schema_cannot_redefine_reserved_graph_predicates(tmp_path: Path, name: str) -> None:
    """Domain relations cannot overwrite built-in mention or symmetric-alias semantics."""
    content = _schema()
    content["relations"] = [
        {"name": name, "description": "Reserved", "domain": ["Company"], "range": ["Company"]}
    ]
    with pytest.raises(ValidationError, match=r"relations\.0\.name: reserved"):
        loader.load_schema(_write(tmp_path / "reserved.yaml", content))
