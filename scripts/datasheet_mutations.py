# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent datasheet guards must each reject unsupported model output."""

from scripts.mutation_models import Mutation

DATASHEET_MUTATIONS = (
    Mutation(
        name="datasheet-role-identity-support",
        path="datasheets/matching.py",
        before="        or not names_supported(text, facts)",
        after="        or False",
        case="tests/harness/test_datasheet_mutations.py::test_datasheet_numeric_owner_name_cannot_be_published",
        runner="pytest",
    ),
    Mutation(
        name="datasheet-numeric-support",
        path="datasheets/matching.py",
        before="    if _unsupported_numbers(normalized(text), numbers):",
        after="    if False:",
        case="tests/harness/test_datasheet_mutations.py::test_datasheet_invented_number_cannot_be_published",
        runner="pytest",
    ),
    Mutation(
        name="datasheet-proper-name-support",
        path="datasheets/matching.py",
        before='        return ("unsupported_term",)',
        after="        return ()",
        case="tests/harness/test_datasheet_mutations.py::test_datasheet_unseen_proper_name_cannot_be_published",
        runner="pytest",
    ),
    Mutation(
        name="datasheet-known-reference",
        path="datasheets/validation.py",
        before='        return ("unknown_fact",)',
        after="        return ()",
        case="tests/harness/test_datasheet_mutations.py::test_datasheet_unknown_fact_cannot_be_published",
        runner="pytest",
    ),
    Mutation(
        name="datasheet-required-reference",
        path="datasheets/validation.py",
        before='        return ("missing_citation",)',
        after="        return ()",
        case="tests/harness/test_datasheet_mutations.py::test_datasheet_uncited_sentence_cannot_be_published",
        runner="pytest",
    ),
    Mutation(
        name="datasheet-date-support",
        path="datasheets/matching.py",
        before="    if _dates(normalized(text)) - dates:",
        after="    if False:",
        case="tests/harness/test_datasheet_mutations.py::test_datasheet_invented_date_cannot_be_published",
        runner="pytest",
    ),
)
