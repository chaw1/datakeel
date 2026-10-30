# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""New actions and read functions are plannable only with Chinese and English wording."""

from datakeel.actions.registry import POLICIES, action_definitions
from datakeel.core.models import JsonDocument
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.language_check import missing_language
from datakeel.ontology.models import ActionType
from datakeel.ontology.registry import registry


def test_every_registered_action_and_function_has_zh_en_phrases_and_examples() -> None:
    """The gate covers every policy entry and every read function the registry exposes."""
    current = registry(action_definitions())
    assert {item.id for item in current.actions} == set(POLICIES)
    assert {item.id for item in current.functions} == set(PARAMETER_MODELS)
    assert missing_language(current) == {}


def test_gate_names_an_entry_registered_without_wording() -> None:
    """A synthetic action without phrases or examples is reported field by field."""
    bare = ActionType(
        id="synthetic_action",
        params_schema=JsonDocument({}),
        auth_scope="production:manage",
        preconditions=[],
        effects=[],
        reversible=True,
        handler="tests.synthetic",
        phrases={"zh": ["合成动作"]},
        examples={"en": ["run the synthetic action"]},
    )
    current = registry([*action_definitions(), bare])
    assert missing_language(current) == {"synthetic_action": ["examples.zh", "phrases.en"]}


def test_each_entry_has_one_example_per_language_at_least() -> None:
    """Examples are full sentences a person would type, not the bare identifier."""
    current = registry(action_definitions())
    for item in [*current.actions, *current.functions]:
        for language in ("zh", "en"):
            examples = item.examples[language]
            assert examples, item.id
            assert all(text.strip() != item.id for text in examples), item.id
