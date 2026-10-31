# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""New actions and read functions are plannable only with Chinese and English wording."""

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.actions.registry import POLICIES, action_definitions
from datakeel.core.models import JsonDocument
from datakeel.intents.field_names import ENUM_LABELS
from datakeel.intents.signatures import HIDDEN, choice_values
from datakeel.intents.wording import field_label
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


def test_every_registered_parameter_has_words_for_the_card() -> None:
    """No card line shows a raw key: every action and read parameter has a Chinese and English name.

    New parameters arrive with new releases (review sampling, tier thresholds, the template
    lock, rework handovers), so the gate reads the registry instead of a fixed list.
    """
    unnamed = sorted(
        f"{name}.{field}"
        for name, model in [*PARAMETER_TYPES.items(), *PARAMETER_MODELS.items()]
        for field in model.model_fields
        if field not in HIDDEN
        and field_label(field, "zh") == field
        and field_label(field, "en") == field.replace("_", " ")
    )
    assert unnamed == []
    assert field_label("review_sample_rate", "zh") == "审核抽检比例"
    assert field_label("template_version", "en") == "template version"


def test_tier_and_clear_choices_are_said_in_words() -> None:
    """The confidence tiers and the settings a project can clear read as words, not values."""
    for action, field in (("save_revision", "confidence_tier"), ("configure_project", "clear")):
        values = choice_values(action, field)
        assert values, (action, field)
        assert [value for value in values if value not in ENUM_LABELS] == []
