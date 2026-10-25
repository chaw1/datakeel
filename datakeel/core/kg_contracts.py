# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen schemas and extraction profiles for text knowledge graphs."""

from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, JsonValue, field_validator, model_validator

from datakeel.core.models import BoundaryModel


class EntityType(BoundaryModel):
    """Declare an entity category and explicitly permitted spelling aliases."""

    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    description: str = Field(min_length=1)
    aliases: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    person: bool = False


class RelationType(BoundaryModel):
    """Constrain a directed relation to declared endpoint categories."""

    name: str = Field(pattern=r"^[a-z][a-z_]*$")
    description: str = Field(min_length=1)
    domain: tuple[str, ...] = Field(min_length=1)
    range: tuple[str, ...] = Field(min_length=1)


class ExtractedEntity(BoundaryModel):
    """Carry a model-provided name and category before product validation."""

    name: str = Field(min_length=1, pattern=r"\S")
    type: str = Field(min_length=1)


class ExtractedRelation(BoundaryModel):
    """Carry a directed model claim and its purported verbatim evidence."""

    head: str = Field(min_length=1, pattern=r"\S")
    relation: str = Field(min_length=1)
    tail: str = Field(min_length=1, pattern=r"\S")
    evidence: str


class SchemaExample(BoundaryModel):
    """Demonstrate extraction using evidence copied from the example text."""

    text: str = Field(min_length=1)
    entities: tuple[ExtractedEntity, ...] = ()
    relations: tuple[ExtractedRelation, ...] = ()


class KGSchema(BoundaryModel):
    """Describe a checked vocabulary without changing it during extraction."""

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    entity_types: tuple[EntityType, ...] = Field(min_length=1)
    relations: tuple[RelationType, ...] = Field(min_length=1)
    rules: tuple[str, ...] = Field(min_length=1)
    examples: tuple[SchemaExample, ...] = ()

    @model_validator(mode="after")
    def validate_vocabulary(self) -> Self:
        """Reject duplicate names, invalid endpoint categories and ungrounded examples."""
        names = tuple(item.name for item in self.entity_types)
        relations = tuple(item.name for item in self.relations)
        for field, values in (("entity_types", names), ("relations", relations)):
            if len(values) != len(set(values)):
                msg = f"{field}: duplicate names"
                raise ValueError(msg)
        for index, relation in enumerate(self.relations):
            if relation.name in {"mentions", "same_as"}:
                msg = f"relations.{index}.name: reserved graph predicate"
                raise ValueError(msg)
            for field in ("domain", "range"):
                values = getattr(relation, field)
                if len(values) != len(set(values)):
                    msg = f"relations.{index}.{field}: duplicate entity type"
                    raise ValueError(msg)
                unknown = set(values) - set(names)
                if unknown:
                    msg = f"relations.{index}.{field}: unknown entity types {sorted(unknown)}"
                    raise ValueError(msg)
        self._validate_examples(set(names), set(relations))
        return self

    def _validate_examples(self, names: set[str], relations: set[str]) -> None:
        for index, example in enumerate(self.examples):
            for entity in example.entities:
                if entity.type not in names:
                    msg = f"examples.{index}.entities: unknown entity type {entity.type}"
                    raise ValueError(msg)
            for relation in example.relations:
                if relation.relation not in relations:
                    msg = f"examples.{index}.relations: unknown relation {relation.relation}"
                    raise ValueError(msg)
                if not relation.evidence or relation.evidence not in example.text:
                    msg = f"examples.{index}.relations.evidence: not a substring of example text"
                    raise ValueError(msg)


_ALLOWED_PARAMETERS = frozenset({"enable_thinking", "thinking", "reasoning_effort"})


def _valid_parameter(name: str, value: JsonValue) -> bool:
    if name == "enable_thinking":
        return isinstance(value, bool)
    if name == "reasoning_effort":
        return isinstance(value, str) and value in {"none", "minimal", "low", "medium", "high"}
    if not isinstance(value, dict) or set(value) - {"type", "budget_tokens"}:
        return False
    budget = value.get("budget_tokens", 1)
    return (
        value.get("type") in ("enabled", "disabled")
        and isinstance(budget, int)
        and not isinstance(budget, bool)
        and budget > 0
    )


class ExtractionProfile(BoundaryModel):
    """Declare transport settings while allowing only environment variable key names."""

    id: str = Field(min_length=1)
    extractor: Literal["llm", "fake", "replay", "gliner2"]
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    base_url: str | None = None
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    output_method: Literal["json_schema", "function_calling", "json_mode"] = "json_schema"
    request_parameters: dict[str, JsonValue] = Field(default_factory=dict)
    temperature: float = Field(default=0, ge=0, le=2)
    max_output_tokens: int = Field(default=4096, gt=0)
    chunk_size: int = Field(default=12000, gt=0)
    chunk_overlap: int = Field(default=0, ge=0)
    recording: str | None = None
    prompt_version: str = Field(default="text-kg-v3", min_length=1)

    @field_validator("request_parameters")
    @classmethod
    def validate_parameters(cls, parameters: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """Validate nested values as well as names to prevent hidden transport overrides."""
        if set(parameters) - _ALLOWED_PARAMETERS:
            msg = "request_parameters: unsupported parameter name"
            raise ValueError(msg)
        if any(not _valid_parameter(name, value) for name, value in parameters.items()):
            msg = "request_parameters: unsupported parameter value"
            raise ValueError(msg)
        return parameters

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        """Reject secret-bearing endpoints, undeclared parameters and invalid chunks."""
        if self.extractor in {"fake", "replay", "gliner2"} and self.provider != self.extractor:
            msg = "provider must match the offline extractor"
            raise ValueError(msg)
        if self.extractor == "llm" and self.provider not in {"openai", "anthropic", "ollama"}:
            msg = "llm provider must be openai, anthropic or ollama"
            raise ValueError(msg)
        if self.provider == "ollama" and not self.base_url:
            msg = "ollama provider requires an explicit base_url"
            raise ValueError(msg)
        if self.chunk_overlap >= self.chunk_size:
            msg = "chunk_overlap must be less than chunk_size"
            raise ValueError(msg)
        if self.extractor == "replay" and not self.recording:
            msg = "recording is required for replay extraction"
            raise ValueError(msg)
        if self.base_url:
            url = urlsplit(self.base_url)
            if url.scheme not in {"http", "https"} or not url.hostname:
                msg = "base_url must be an absolute HTTP URL"
                raise ValueError(msg)
            if url.username or url.password or url.query or url.fragment:
                msg = "base_url must not contain credentials, query parameters or fragments"
                raise ValueError(msg)
        return self
