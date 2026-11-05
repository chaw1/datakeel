# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Named SQLite migration guards with call-phase assertion evidence."""

from scripts.mutation_models import Mutation

VERSIONING_MUTATIONS = (
    Mutation(
        name="versioning-unknown-schema",
        path="versioning/inspect.py",
        before="if schema_objects(connection) != expected:",
        after="if False:",
        case="tests/versioning/test_campaigns.py::test_unexpected_table_rejected_at_named_anchor",
        runner="pytest",
    ),
    Mutation(
        name="versioning-preserve-facts",
        path="versioning/campaign.py",
        before="if existed and definition.preserve_facts and before != after:",
        after="if False:",
        case=(
            "tests/versioning/test_campaigns.py::"
            "test_same_structure_unauthorized_change_rejected_at_named_anchor"
        ),
        runner="pytest",
    ),
    Mutation(
        name="versioning-maintenance-lock",
        path="versioning/lock.py",
        before="fcntl.flock(stream, fcntl.LOCK_EX)",
        after="pass",
        case=(
            "tests/versioning/test_campaigns.py::"
            "test_campaign_lock_survives_first_commit_and_waiter_only_reads_final_head"
        ),
        runner="pytest",
    ),
)
