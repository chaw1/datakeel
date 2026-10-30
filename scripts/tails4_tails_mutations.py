# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""TAILS-4 interface tails: English answer wording, the assignee read tool and task paths."""

from scripts.mutation_models import Mutation

_EN = "tests/ask/test_interpretation_en.py::"
_ASSIGNEES = "tests/mcp/test_production_assignees.py::"
_TASK_PATH = "tests/storage/test_workbench_task_path.py::"

TAILS_MUTATIONS = (
    Mutation(
        name="ask-english-interpretation-metric-name",
        path="ask/interpretation_en.py",
        before='parts = [f"Query {card.definition.english_name or card.definition.name}"]',
        after='parts = [f"Query {card.definition.name}"]',
        case=_EN + "test_english_interpretation_words_every_slot_with_registered_english_names",
        runner="pytest",
    ),
    Mutation(
        name="ask-english-interpretation-dimension-name",
        path="ask/interpretation_en.py",
        before="names = {item.id: item.english_name or item.name for item in layer.dimensions}",
        after="names = {item.id: item.name for item in layer.dimensions}",
        case=_EN + "test_english_interpretation_words_every_slot_with_registered_english_names",
        runner="pytest",
    ),
    Mutation(
        name="ask-english-interpretation-previous-period",
        path="ask/interpretation_en.py",
        before='if frame.comparison == "year_over_year"',
        after="if frame.comparison",
        case=_EN + "test_english_interpretation_of_shares_and_previous_periods",
        runner="pytest",
    ),
    Mutation(
        name="ask-subject-english-name",
        path="ask/knowledge_subjects.py",
        before="english_name=item.english_name,",
        after="english_name=None,",
        case=_EN + "test_recognized_metric_subject_carries_its_registered_english_name",
        runner="pytest",
    ),
    Mutation(
        name="mcp-assignees-registered",
        path="ontology/production_functions.py",
        before='    "assignees": AssigneesParams,\n',
        after="",
        case=_ASSIGNEES + "test_assignees_is_a_read_only_mcp_tool",
        runner="pytest",
    ),
    Mutation(
        name="mcp-assignees-stage",
        path="ontology/production_functions.py",
        before="return assignees(db, query.project_id, caller, query.stage)",
        after='return assignees(db, query.project_id, caller, "annotation")',
        case=_ASSIGNEES + "test_mcp_assignees_matches_http_for_each_stage",
        runner="pytest",
    ),
    Mutation(
        name="workbench-task-relative-path",
        path="storage/workbench_reads.py",
        before="path=relative,",
        after="path=name,",
        case=_TASK_PATH + "test_opened_task_shows_the_relative_path_listed_for_it",
        runner="pytest",
    ),
)
