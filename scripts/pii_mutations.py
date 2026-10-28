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
    Mutation(
        name="training-tool-payload-privacy",
        path="llm_data/checks.py",
        before="*_privacy(record.payload)",
        after="*_privacy(record.text)",
        case="tests/llm_data/test_checks.py::test_privacy_when_tool_arguments_and_schema_descriptions_contain_secrets_redacts_all",
        runner="pytest",
    ),
    Mutation(
        name="training-rejected-truncation",
        path="llm_data/checks.py",
        before='        ("chosen", "rejected")',
        after='        ("chosen",)',
        case="tests/llm_data/test_checks.py::test_rejected_when_code_fence_is_unclosed_always_reports_truncation",
        runner="pytest",
    ),
    Mutation(
        name="pii-credential-field-context",
        path="core/pii.py",
        before="    if finding := _labeled_secret(text, label):",
        after="    if False:",
        case="tests/core/test_pii.py::test_label_context_is_required_to_find_an_opaque_credential",
        runner="pytest",
    ),
    Mutation(
        name="pii-ipv6-label-boundary",
        path="core/pii.py",
        before="    for match in patterns.LABELED_IP.finditer(text):",
        after="    for match in ():",
        case="tests/core/test_pii.py::test_ipv6_label_boundary_requires_whole_token_validation",
        runner="pytest",
    ),
)
