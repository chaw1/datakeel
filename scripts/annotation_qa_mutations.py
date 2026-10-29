# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Annotation read mutations extend the corpus without weakening prior contracts."""

from scripts.mutation_models import Mutation

ANNOTATION_QA_MUTATIONS = (
    Mutation(
        name="annotation-read-erases-measurements",
        path="ontology/annotation_functions.py",
        before='data=overview.model_dump(mode="json"),',
        after="data={},",
        case="44-annotation-quality",
    ),
    Mutation(
        name="annotation-cohen-chance-correction-omitted",
        path="annotation_qa/categorical.py",
        before="value=float((observed - expected) / (1 - expected)),",
        after="value=float(observed),",
        case="tests/annotation_qa/test_categorical.py::test_cohen_author_numerical_example",
        runner="pytest",
    ),
    Mutation(
        name="annotation-minority-label-inverted",
        path="annotation_qa/findings.py",
        before="if actual != majority:",
        after="if actual == majority:",
        case="tests/annotation_qa/test_findings.py::test_all_seven_injected_rule_types_are_discovered",
        runner="pytest",
    ),
    Mutation(
        name="annotation-cluster-same-annotator-duplicate-omitted",
        path="annotation_qa/consensus.py",
        before="if annotator not in first:",
        after="if True:",
        case=(
            "tests/annotation_qa/test_consensus.py::"
            "test_chained_same_annotator_boxes_report_one_duplicate_without_false_missing"
        ),
        runner="pytest",
    ),
    Mutation(
        name="annotation-cluster-votes-count-entries",
        path="annotation_qa/consensus.py",
        before="counts = _votes(members, value)",
        after="counts = Counter(value(item) for item in members)",
        case=(
            "tests/annotation_qa/test_consensus.py::"
            "test_cluster_votes_count_people_instead_of_repeated_category_entries"
        ),
        runner="pytest",
    ),
)
