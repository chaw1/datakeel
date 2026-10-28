# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Probe the complete decision-ledger integrity guard and real training-tool golden counts."""

from scripts.mutation_models import Mutation

TRAINING_GOVERNANCE_MUTATIONS = (
    Mutation(
        name="training-clean-ledger-integrity",
        path="storage/training_actions.py",
        before="        or _ledger_fingerprint(row.ledger_key) != expected.ledger_sha256",
        after="        or False",
        case=(
            "tests/storage/test_training_governance.py::"
            "test_frozen_dry_run_rejects_changed_decision_ledger"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-read-measured-counts",
        path="ontology/training_functions.py",
        before='        data=report.model_dump(mode="json"),',
        after='        data={**report.model_dump(mode="json"), "issue_counts": {}},',
        case="46-training-quality",
    ),
    Mutation(
        name="training-cached-evaluation-provenance",
        path="ontology/training_functions.py",
        before="        asset_refs=list(result.asset_refs),",
        after=(
            "        asset_refs=[ref for ref in result.asset_refs "
            "if ref.asset_type == 'dataset' and ref.asset_id == query.dataset_id],"
        ),
        case=(
            "tests/storage/test_training_replay.py::"
            "test_cached_training_and_quality_tools_recheck_version_pinned_evaluation_grants"
        ),
        runner="pytest",
    ),
)
