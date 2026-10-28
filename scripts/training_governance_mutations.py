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
)
