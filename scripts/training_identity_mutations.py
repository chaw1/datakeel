# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mutation anchors for training writes under role scopes and production export round trips."""

from scripts.mutation_models import Mutation

_MANAGER_CASE = (
    "tests/api/test_training_identity_access.py::"
    "test_project_manager_template_exports_training_but_cannot_clean_or_import"
)

TRAINING_IDENTITY_MUTATIONS = (
    Mutation(
        name="identity-training-split-export-scope",
        path="api/identity_access.py",
        before='): "export_dataset",',
        after='): "save_metadata",',
        case=_MANAGER_CASE,
        runner="pytest",
    ),
    Mutation(
        name="identity-text-analysis-dataset-write",
        path="api/identity_access.py",
        before='/text-governance/analyze"): "clean_training_data",',
        after='/text-governance/analyze"): "export_dataset",',
        case=_MANAGER_CASE,
        runner="pytest",
    ),
    Mutation(
        name="identity-manager-training-export",
        path="storage/identity_store.py",
        before='        "export_dataset",\n    }',
        after="    }",
        case=_MANAGER_CASE,
        runner="pytest",
    ),
    Mutation(
        name="identity-text-clean-http-actor",
        path="api/routes/llm_data.py",
        before="        http_action_context(request),\n",
        after="",
        case=(
            "tests/api/test_training_identity_access.py::"
            "test_text_governance_preparation_keeps_the_registered_http_actor"
        ),
        runner="pytest",
    ),
    Mutation(
        name="production-coco-training-sample-identity",
        path="storage/production_prediction_parsing.py",
        before="_sample(image.datakeel_sample_id or str(image.id), image.file_name, samples)",
        after="_sample(str(image.id), image.file_name, samples)",
        case=(
            "tests/actions/test_production_training_roundtrip.py::"
            "test_finalized_version_training_exports_reimport_as_identical_predictions"
        ),
        runner="pytest",
    ),
)
