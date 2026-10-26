# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Require standards goldens to reject inverted rankings and missing confirmed usage."""

from scripts.mutation_models import Mutation

STANDARD_MUTATIONS = (
    Mutation(
        name="standards-worst-table",
        path="ontology/standard_functions.py",
        before="key=lambda item: (item.compliance, item.coverage, item.key)",
        after="key=lambda item: (-item.compliance, item.coverage, item.key)",
        case="41-standard-coverage",
    ),
    Mutation(
        name="standards-confirmed-usage",
        path="ontology/standard_functions.py",
        before="if item.standard_code in codes",
        after="if False",
        case="42-standard-usage",
    ),
)
