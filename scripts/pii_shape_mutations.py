# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Privacy shape mutations: bracketed North American and mobile phones, half brackets."""

from scripts.mutation_models import Mutation

_PATTERNS = "core/pii_patterns.py"
_NORTH_AMERICAN = (
    "tests/core/test_pii_phone_north_american.py::test_north_american_phone_mutation_guard"
)
_HALF_BRACKET = "tests/core/test_pii_phone_half_brackets.py::test_half_bracket_mutation_guard"
_BRACKETED_MOBILE = (
    "tests/core/test_pii_phone_bracketed_mobile.py::test_bracketed_mobile_mutation_guard"
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
    Mutation(
        name="pii-phone-half-bracket-rejected",
        path="core/pii.py",
        before="    if _splits_brackets(value):\n        return False\n",
        after="",
        case=_HALF_BRACKET,
        runner="pytest",
    ),
    Mutation(
        name="pii-phone-half-bracket-closing-first",
        path="core/pii.py",
        before="        if depth < 0:\n            return True\n",
        after="",
        case=_HALF_BRACKET,
        runner="pytest",
    ),
    Mutation(
        name="pii-phone-half-bracket-left-open",
        path="core/pii.py",
        before="    return depth > 0\n",
        after="    return False\n",
        case=_HALF_BRACKET,
        runner="pytest",
    ),
    Mutation(
        name="pii-phone-bracketed-mobile-branch",
        path=_PATTERNS,
        before='r"|(?:\\(1[3-9][0-9]\\)|\\uff081[3-9][0-9]\\uff09)[ -]*[0-9]{4}[ -]?[0-9]{4}"',
        after='r"|(?!)"',
        case=_BRACKETED_MOBILE,
        runner="pytest",
    ),
    Mutation(
        name="pii-phone-bracketed-mobile-prefix",
        path=_PATTERNS,
        before="\\(1[3-9][0-9]\\)|",
        after="\\(1[0-9][0-9]\\)|",
        case=_BRACKETED_MOBILE,
        runner="pytest",
    ),
    Mutation(
        name="pii-phone-bracketed-mobile-wide-prefix",
        path=_PATTERNS,
        before="\\uff081[3-9][0-9]\\uff09)",
        after="\\uff081[0-9][0-9]\\uff09)",
        case=_BRACKETED_MOBILE,
        runner="pytest",
    ),
    Mutation(
        name="pii-phone-bracketed-mobile-body",
        path=_PATTERNS,
        before="uff09)[ -]*[0-9]{4}[ -]?[0-9]{4}",
        after="uff09)[ -]*[0-9]{3,4}[ -]?[0-9]{4}",
        case=_BRACKETED_MOBILE,
        runner="pytest",
    ),
)
