# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Metadata regressions detect lost approval gates, provenance and source deletions."""

from scripts.mutation_models import Mutation

METADATA_MUTATIONS = (
    Mutation(
        name="metadata-draft-approval",
        path="actions/models.py",
        before='                "confirm_metric_draft",\n',
        after="",
        case=(
            "tests/actions/test_metric_drafts.py::"
            "test_metric_draft_when_unapproved_cannot_enter_semantic_layer"
        ),
        runner="pytest",
    ),
    Mutation(
        name="metadata-source-tombstone",
        path="storage/metadata_store.py",
        before="tuple(_tombstone(item) for item in removed)",
        after="removed",
        case=(
            "tests/catalog/test_metadata_store.py::"
            "test_metadata_when_only_source_deleted_preserves_deleted_catalog_object"
        ),
        runner="pytest",
    ),
    Mutation(
        name="metadata-physical-merge",
        path="core/metadata_projection.py",
        before="if len(contributions) == 1:",
        after="if True:",
        case=(
            "tests/catalog/test_metadata_store.py::"
            "test_metadata_when_overlapping_identity_preserves_database_and_dbt_evidence"
        ),
        runner="pytest",
    ),
)
