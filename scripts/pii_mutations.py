# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Checksum mutations must fail on independently generated invalid privacy samples."""

from scripts.mutation_models import Mutation

PII_MUTATIONS = (
    Mutation(
        name="pii-resident-id-checksum",
        path="core/pii.py",
        before="    return value[-1].upper() == _ID_CHECKS[checksum % 11]",
        after="    return True",
        case="tests/core/test_pii.py::test_id_when_checksum_invalid_never_reports_resident_identity",
        runner="pytest",
    ),
    Mutation(
        name="pii-bank-card-luhn",
        path="core/pii.py",
        before="    return checksum % 10 == 0",
        after="    return True",
        case="tests/core/test_pii.py::test_card_when_checksum_invalid_never_reports_payment_card",
        runner="pytest",
    ),
)
