# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""TAILS-4 interface tails: English answer wording, the assignee read tool and task paths."""

from scripts.mutation_models import Mutation

_EN = "tests/ask/test_interpretation_en.py::"
_ASSIGNEES = "tests/mcp/test_production_assignees.py::"
_TASK_PATH = "tests/storage/test_workbench_task_path.py::"
_REASONS = "tests/ask/test_coded_reasons.py::"
_UNSUPPORTED_TIME = _REASONS + "test_unsupported_time_words_refuse_with_a_coded_time_reason"

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
    Mutation(
        name="ask-reason-carried-to-answer",
        path="ask/service.py",
        before="reason=resolution.reason,",
        after="reason=None,",
        case=_UNSUPPORTED_TIME,
        runner="pytest",
    ),
    Mutation(
        name="ask-time-century-words",
        path="ask/time_vocabulary.py",
        before=r'r"(?:上个|这个|下个|上|本|下)?\s*世纪|\d*\s*年代|同期|"',
        after=r'r"\d*\s*年代|同期|"',
        case=_UNSUPPORTED_TIME,
        runner="pytest",
    ),
    Mutation(
        name="ask-time-same-period-word",
        path="ask/time_vocabulary.py",
        before=r'\d*\s*年代|同期|"',
        after=r'\d*\s*年代|"',
        case=_UNSUPPORTED_TIME,
        runner="pytest",
    ),
    Mutation(
        name="ask-time-english-decade-words",
        path="ask/time_vocabulary.py",
        before=r'r"centur(?:y|ies)|(?:twen|thir|for|fif|six|seven|eigh|nine)ties|noughties|"',
        after=r'r"centur(?:y|ies)|"',
        case=_UNSUPPORTED_TIME,
        runner="pytest",
    ),
    Mutation(
        name="ask-reason-condition-wording",
        path="ask/reasons.py",
        before='"; ".join([*notes, *(f"未理解「{item}」" for item in fragments)])',
        after='"; ".join([*(f"未理解「{item}」" for item in fragments), *notes])',
        case=_REASONS + "test_every_code_has_a_chinese_wording_and_old_answers_still_load",
        runner="pytest",
    ),
)
