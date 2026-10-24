# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Optional local entity extraction without a mandatory model dependency."""

from collections.abc import Callable
from importlib import import_module
from typing import Protocol, cast

from pydantic import Field

from datakeel.core.kg_contracts import ExtractedEntity, KGSchema
from datakeel.core.kg_errors import KGExtractionError
from datakeel.core.kg_models import ExtractionResult, RawExtraction, TextBlock
from datakeel.core.models import BoundaryModel


class GlinerModel(Protocol):
    """Describe only the installed package's entity-only entry point."""

    def extract_entities(self, text: str, entity_types: list[str]) -> object:
        """Return named entity groups without extracting any relations."""
        ...


class GlinerFactory(Protocol):
    """Describe lazy loading of the separately installed local model."""

    def from_pretrained(self, model_name: str) -> GlinerModel:
        """Create an entity extractor from the requested local model configuration."""
        ...


class GlinerModule(Protocol):
    """Restrict the optional module surface to its documented model factory."""

    GLiNER2: GlinerFactory


class _Output(BoundaryModel):
    entities: dict[str, tuple[str, ...]] = Field(default_factory=dict)


def _load_module() -> GlinerModule:
    try:
        return cast("GlinerModule", import_module("gliner2"))
    except ImportError as error:
        reason = "gliner2_not_installed: install gliner2 separately to use the local entity profile"
        raise KGExtractionError(reason) from error


class GlinerExtractor:
    """Load GLiNER2 only when selected and route every mention through normal grounding."""

    def __init__(
        self, model_name: str, module_loader: Callable[[], GlinerModule] = _load_module
    ) -> None:
        """Allow an injected fake module to exercise the complete adapter without models."""
        self.model_name = model_name
        self.module_loader = module_loader
        self.model: GlinerModel | None = None

    def extract(self, block: TextBlock, schema: KGSchema) -> ExtractionResult:
        """Return entity claims only; verification remains in the graph domain pipeline."""
        if self.model is None:
            self.model = self.module_loader().GLiNER2.from_pretrained(self.model_name)
        output = _Output.model_validate(
            self.model.extract_entities(block.text, [item.name for item in schema.entity_types])
        )
        return ExtractionResult(
            output=RawExtraction(
                entities=tuple(
                    ExtractedEntity(name=name, type=category)
                    for category, names in output.entities.items()
                    for name in names
                )
            ),
            input_tokens=0,
            output_tokens=0,
        )
