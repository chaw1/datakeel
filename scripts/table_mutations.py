# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Table privacy regression fails if contact distributions copy personal values."""

from scripts.mutation_models import Mutation

TABLE_MUTATIONS = (
    Mutation(
        name="table-contact-distribution-privacy",
        path="operators/table/statistics.py",
        before="if pii:",
        after="if False:",
        case=(
            "tests/operators/table/test_profile.py::"
            "test_phone_email_findings_never_copy_personal_values_into_profile"
        ),
        runner="pytest",
    ),
)
