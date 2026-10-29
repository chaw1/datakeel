# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Source selection and immutable identity boundaries have independent regression anchors."""

from scripts.mutation_models import Mutation

TRAINING_SOURCE_MUTATIONS = (
    Mutation(
        name="training-stratification-default-changed",
        path="core/training_models.py",
        before='default="all",',
        after='default="classification",',
        case=(
            "tests/training/test_stratification_sources.py::"
            "test_default_all_keeps_label_only_samples_and_original_annotation_order"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-stratification-source-ignored",
        path="training/splitting.py",
        before="_canonical_labels(ordered, request.stratification_source)",
        after='_canonical_labels(ordered, "all")',
        case=(
            "tests/training/test_stratification_sources.py::"
            "test_selected_annotation_sources_match_independent_single_kind_strata"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-stratification-classification-and-detection-swapped",
        path="training/splitting.py",
        before='if source == "classification"',
        after='if source == "detection"',
        case=(
            "tests/training/test_stratification_sources.py::"
            "test_selected_annotation_sources_match_independent_single_kind_strata"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-stratification-selected-kind-only-first-label",
        path="training/splitting.py",
        before="return tuple(sorted(labels))",
        after="return tuple(sorted(labels))[:1]",
        case=(
            "tests/training/test_stratification_sources.py::"
            "test_selected_kind_retains_multiple_labels_from_all_frozen_annotators"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-stratification-erases-original-member-labels",
        path="training/splitting.py",
        before="labels=sample.labels,",
        after="labels=_stratification_labels(sample, request.stratification_source),",
        case=(
            "tests/training/test_stratification_sources.py::"
            "test_selected_annotation_sources_match_independent_single_kind_strata"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-default-stratification-changes-old-identity",
        path="storage/training_store.py",
        before='if request.stratification_source == "all":',
        after="if False:",
        case=(
            "tests/storage/test_training_stratification_policy.py::"
            "test_default_all_preserves_the_previous_split_identity"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-nondefault-stratification-omitted-from-identity",
        path="storage/training_store.py",
        before='if request.stratification_source == "all":',
        after="if True:",
        case=(
            "tests/storage/test_training_stratification_policy.py::"
            "test_nondefault_annotation_source_is_frozen_in_identity_even_with_equal_assignments"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-cli-stratification-source-ignored",
        path="cli/training.py",
        before="stratification_source=args.stratification_source,",
        after='stratification_source="all",',
        case=(
            "tests/cli/test_training_stratification.py::"
            "test_cli_forwards_each_annotation_source_to_named_split_creation"
        ),
        runner="pytest",
    ),
)
