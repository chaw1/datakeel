# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Regression anchors for production source access and independent task namespaces."""

from scripts.mutation_models import Mutation

PRODUCTION_TOOL_MUTATIONS = (
    Mutation(
        name="production-native-source-grant",
        path="storage/data_asset_native.py",
        before="    result.extend(production_targets(session, ref))",
        after="    # Deliberately omit the production source ownership expansion.",
        case=(
            "tests/ontology/test_production_tools.py::"
            "test_production_object_reads_enforce_the_owning_dataset_grant[annotation_revision]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="production-task-reference-namespace",
        path="ontology/tool_refs.py",
        before='if key == "task_id" and production',
        after="if False",
        case=(
            "tests/ontology/test_production_tools.py::"
            "test_production_task_refs_do_not_resolve_an_unrelated_legacy_worker_task"
        ),
        runner="pytest",
    ),
)
