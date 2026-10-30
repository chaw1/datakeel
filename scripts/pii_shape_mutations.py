# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Privacy shape mutations: bracketed North American phones and half-bracket matches."""

from scripts.mutation_models import Mutation

_PATTERNS = "core/pii_patterns.py"
_NORTH_AMERICAN = (
    "tests/core/test_pii_phone_north_american.py::test_north_american_phone_mutation_guard"
)
# The North American alternative of the bracketed-phone expression, verbatim.
_BRANCH = 'r"|(?:\\([2-9][0-9]{2}\\)|\\uff08[2-9][0-9]{2}\\uff09)[ -]*[2-9][0-9]{2}[ -]?[0-9]{4}"'

PII_SHAPE_MUTATIONS = (
    Mutation(
        name="pii-phone-north-american-branch",
        path=_PATTERNS,
        before=_BRANCH,
        after='r"|(?!)"',
        case=_NORTH_AMERICAN,
        runner="pytest",
    ),
    Mutation(
        name="pii-phone-north-american-area-digit",
        path=_PATTERNS,
        before="\\([2-9][0-9]{2}\\)|",
        after="\\([0-9]{3}\\)|",
        case=_NORTH_AMERICAN,
        runner="pytest",
    ),
    Mutation(
        name="pii-phone-north-american-exchange-digit",
        path=_PATTERNS,
        before="uff09)[ -]*[2-9][0-9]{2}[ -]?[0-9]{4}",
        after="uff09)[ -]*[0-9]{3}[ -]?[0-9]{4}",
        case=_NORTH_AMERICAN,
        runner="pytest",
    ),
)
