# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""All-label count and prevalence assertions must detect disabled balance safeguards."""

from scripts.mutation_models import Mutation

TRAINING_MULTILABEL_MUTATIONS = (
    Mutation(
        name="training-multilabel-restarts-omitted",
        path="training/splitting.py",
        before="BALANCE_ATTEMPTS = 16",
        after="BALANCE_ATTEMPTS = 0",
        case=(
            "tests/training/test_multilabel.py::"
            "test_nonuniform_sparse_multilabel_prevalence_is_balanced[19]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-multilabel-prevalence-limit-ignored",
        path="training/proportions.py",
        before="PREVALENCE_TOLERANCE = 0.02",
        after="PREVALENCE_TOLERANCE = 1.0",
        case=(
            "tests/training/test_multilabel.py::"
            "test_nonuniform_sparse_multilabel_prevalence_is_balanced[19]"
        ),
        runner="pytest",
    ),
)
