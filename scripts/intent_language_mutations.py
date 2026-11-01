# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Anchors for registry-driven Chinese and English wording on plan and result cards."""

from scripts.mutation_models import Mutation

LANGUAGE_MUTATIONS = (
    Mutation(
        name="every-registered-enum-value-has-words",
        path="intents/field_names.py",
        before='    "coco": ("COCO 数据集", "COCO dataset"),\n',
        after="",
        case="tests/intents/test_language_gate.py::test_every_registered_enum_value_has_zh_en_words",
        runner="pytest",
    ),
    Mutation(
        name="nested-registered-enum-values-have-words",
        path="intents/field_names.py",
        before='    "avg": ("平均值", "average"),\n',
        after="",
        case="tests/intents/test_language_gate.py::test_every_registered_enum_value_has_zh_en_words",
        runner="pytest",
    ),
    Mutation(
        name="nested-enum-card-renders-words",
        path="intents/field_names.py",
        before='    "day": ("按天", "daily"),\n',
        after="",
        case="tests/intents/test_language_gate.py::test_nested_metric_choices_render_in_words_on_the_real_card",
        runner="pytest",
    ),
)
