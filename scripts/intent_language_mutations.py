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
)
