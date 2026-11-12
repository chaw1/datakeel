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
    Mutation(
        name="versioning-v2-lease-forward",
        path="versioning/v2.py",
        before=(
            'connection.exec_driver_sql("ALTER TABLE task_shards '
            'ADD COLUMN lease_expires_at FLOAT")'
        ),
        after='connection.exec_driver_sql("SELECT 1")',
        case=(
            "tests/versioning/test_vector_v2.py::"
            "test_campaign_preserves_facts_objects_restore_and_repeat[legacy99]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="versioning-v3-latest-recognition",
        path="versioning/inspect_v3.py",
        before="for definition in reversed(versions):",
        after="for definition in reversed(versions[:1]):",
        case="tests/versioning/test_vector_v2.py::test_latest_stamp_never_calls_forward",
        runner="pytest",
    ),
    Mutation(
        name="versioning-v2-preserve-facts",
        path="versioning/campaign_v2.py",
        before="if existed and definition.preserve_facts:",
        after="if False:",
        case=(
            "tests/versioning/test_vector_v2.py::"
            "test_v2_failure_rolls_back_ddl_facts_and_ledger[facts]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="versioning-v2-postcondition",
        path="versioning/campaign_v2.py",
        before="validate_baseline(connection, definition.target)",
        after="pass",
        case=(
            "tests/versioning/test_vector_v2.py::"
            "test_v2_failure_rolls_back_ddl_facts_and_ledger[ddl]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="versioning-v3-stamp-atomic",
        path="versioning/campaign_v3.py",
        before="    except BaseException:\n        connection.rollback()\n        raise",
        after="    except BaseException:\n        connection.commit()\n        raise",
        case=(
            "tests/versioning/test_vector_v2_atomic.py::"
            "test_latest_stamp_rolls_back_all_ledger_rows_without_business_ddl[ledger]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="versioning-v3-rank-forward",
        path="versioning/v3.py",
        before=(
            'connection.exec_driver_sql("ALTER TABLE production_tasks '
            'ADD COLUMN display_rank INTEGER")'
        ),
        after='connection.exec_driver_sql("SELECT 1")',
        case=(
            "tests/versioning/test_vector_v2.py::"
            "test_campaign_preserves_facts_objects_restore_and_repeat[legacy102]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="versioning-v3-preserve-facts",
        path="versioning/campaign_v3.py",
        before="if existed and definition.preserve_facts:",
        after="if False:",
        case=(
            "tests/versioning/test_vector_v2.py::test_v3_failure_rolls_back_ddl_facts_and_ledger[facts]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="versioning-v3-postcondition",
        path="versioning/campaign_v3.py",
        before="validate_baseline(connection, definition.target)",
        after="pass",
        case=(
            "tests/versioning/test_vector_v2.py::test_v3_failure_rolls_back_ddl_facts_and_ledger[ddl]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="versioning-v2-memory-all-versions",
        path="versioning/__init__.py",
        before="for definition in registry():",
        after="for definition in registry()[:1]:",
        case=(
            "tests/versioning/test_vector_v2.py::"
            "test_memory_initialization_applies_every_version[sqlite://]"
        ),
        runner="pytest",
    ),
)
