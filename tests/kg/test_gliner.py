# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise optional local extraction through injected modules only."""

from types import SimpleNamespace

import pytest

from datakeel.core.kg_errors import KGExtractionError
from datakeel.core.kg_models import TextBlock
from datakeel.kg import gliner
from datakeel.kg.assembly import assemble_extraction
from datakeel.kg.loader import get_schema
from tests.kg.helpers import graph_product


def test_optional_adapter_loads_once_and_never_produces_relationships() -> None:
    """Even hallucinated local entities go through normal mention verification."""
    calls: list[str] = []

    class Model:
        def extract_entities(self, text: str, entity_types: list[str]) -> object:
            return {"entities": {"organization": ["Acme"], "system": ["Vivo"]}}

    class Factory:
        def from_pretrained(self, model_name: str) -> Model:
            calls.append(model_name)
            return Model()

    adapter = gliner.GlinerExtractor("local-fixture", lambda: SimpleNamespace(GLiNER2=Factory()))
    _, source = graph_product()
    block = TextBlock(text=source.text, start=0, end=len(source.text))
    assert calls == []
    result = adapter.extract(block, get_schema())
    adapter.extract(block, get_schema())
    assert calls == ["local-fixture"]
    assert result.output.relations == ()
    product = assemble_extraction(result.output, get_schema(), source)
    assert any(draft.verification == "needs_review" for draft in product.drafts)


def test_missing_optional_module_has_actionable_install_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The base application remains importable without installing optional model packages."""

    def missing(name: str) -> object:
        raise ImportError

    monkeypatch.setattr(gliner, "import_module", missing)
    adapter = gliner.GlinerExtractor("local-fixture")
    with pytest.raises(KGExtractionError, match="install gliner2 separately"):
        adapter.extract(TextBlock(text="text", start=0, end=4), get_schema())
