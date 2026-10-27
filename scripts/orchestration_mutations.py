# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measured regressions guard orchestration authentication, ordering and idempotency."""

from scripts.mutation_models import Mutation

ORCHESTRATION_MUTATIONS = (
    Mutation(
        name="openlineage-bearer-authentication",
        path="api/routes/openlineage.py",
        before="or not compare_digest(credentials.credentials.encode(), expected.encode())",
        after=(
            "or False and not compare_digest(credentials.credentials.encode(), expected.encode())"
        ),
        case=(
            "tests/api/test_openlineage.py::"
            "test_openlineage_wrong_bearer_cannot_append_even_when_ingestion_is_enabled"
        ),
        runner="pytest",
    ),
    Mutation(
        name="openlineage-observation-idempotency",
        path="storage/openlineage_store.py",
        before="inserted = previous is None",
        after="inserted = True",
        case=(
            "tests/storage/test_openlineage.py::"
            "test_openlineage_duplicate_replay_adds_no_facts_or_projection_events"
        ),
        runner="pytest",
    ),
    Mutation(
        name="openlineage-terminal-state-monotonicity",
        path="storage/openlineage_projection.py",
        before="terminal or progress or values,",
        after="values,",
        case=(
            "tests/storage/test_openlineage.py::"
            "test_openlineage_delayed_start_cannot_downgrade_terminal_state[COMPLETE]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="openlineage-dataset-facet-ordering",
        path="storage/openlineage_projection.py",
        before="if previous_time is None or event.eventTime >= previous_time:",
        after="if True:",
        case=(
            "tests/storage/test_openlineage.py::"
            "test_openlineage_late_old_schema_does_not_replace_newer_complete_schema"
        ),
        runner="pytest",
    ),
    Mutation(
        name="openlineage-other-metadata-only",
        path="storage/openlineage_projection.py",
        before="terminal or progress or values,",
        after="terminal or values,",
        case=(
            "tests/storage/test_openlineage_states.py::"
            "test_openlineage_other_never_changes_observed_state[START]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="airflow-success-freshness",
        path="catalog/importers/airflow.py",
        before='previous.details.root.get("last_success")',
        after="None",
        case=(
            "tests/catalog/test_airflow.py::"
            "test_airflow_dataset_freshness_uses_latest_producer_across_consumers"
        ),
        runner="pytest",
    ),
)
