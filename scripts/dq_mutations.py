# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Quality rules and tool goldens kill independent verdict, limit and projection mutants."""

from scripts.mutation_models import Mutation

DQ_MUTATIONS = (
    Mutation(
        name="dq-stream-complete-batches",
        path="quality/dq_source.py",
        before="        yield tuple(row[0] for row in batch.rows)",
        after="        yield tuple(row[0] for row in batch.rows)\n        return",
        case="tests/quality/test_dq_streaming.py::test_regex_stream_counts_failures_after_multiple_batches",
        runner="pytest",
    ),
    Mutation(
        name="dq-result-complete-coverage",
        path="quality/dq_engine.py",
        before='"coverage": "complete",',
        after='"coverage": "unknown",',
        case="tests/quality/test_dq_streaming.py::test_constraints_cover_rows_and_reference_values_beyond_batch_size",
        runner="pytest",
    ),
    Mutation(
        name="dq-not-null-verdict",
        path="quality/dq_constraints.py",
        before="        return column.is_(exp.null())",
        after="        return exp.false()",
        case="tests/quality/test_dq_engine.py::test_not_null_guard_reports_missing_business_values",
        runner="pytest",
    ),
    Mutation(
        name="dq-scan-row-cap",
        path="quality/dq_source.py",
        before=(
            "    if result.truncated:\n"
            '        msg = "Quality assertion result row limit exceeded"\n'
            "        raise ExecutionError(msg)"
        ),
        after="",
        case=(
            "tests/quality/test_dq_streaming.py::"
            "test_assertion_limits_only_returned_violations_and_reports_source_coverage"
        ),
        runner="pytest",
    ),
    Mutation(
        name="dq-baseline-bootstrap",
        path="quality/dq_engine.py",
        before='            and item.status in {"passed", "baseline_insufficient"}',
        after='            and item.status == "passed"',
        case="tests/quality/test_dq_engine.py::test_baseline_insufficient_observations_can_warm_start",
        runner="pytest",
    ),
    Mutation(
        name="dq-failures-tool-status-filter",
        path="ontology/dq_functions.py",
        before="            if params.status is None",
        after="            if True",
        case="tests/harness/test_dq_golden.py::test_failed_quality_golden_uses_real_rule_results",
        runner="pytest",
    ),
    Mutation(
        name="dq-table-quality-score",
        path="storage/dq_views.py",
        before='            numerator += weight * int(status == "passed")',
        after="            numerator += weight",
        case="tests/harness/test_dq_golden.py::test_table_quality_golden_uses_real_history",
        runner="pytest",
    ),
    Mutation(
        name="dq-adaptive-psi-bins",
        path="quality/dq_statistics.py",
        before="    edges = tuple(sorted(boundaries))",
        after="    edges = ()",
        case="tests/quality/test_dq_engine.py::test_adaptive_psi_bins_follow_baseline_scale",
        runner="pytest",
    ),
    Mutation(
        name="dq-missed-minute-catch-up",
        path="storage/dq_jobs.py",
        before="        minute = latest_match(rule.cron, current, current - CATCH_UP_WINDOW)",
        after="        minute = latest_match(rule.cron, current, current)",
        case=(
            "tests/worker/test_dq_scheduler.py::"
            "test_missed_minutes_coalesce_into_newest_slot_within_window"
        ),
        runner="pytest",
    ),
    Mutation(
        name="dq-assertion-function-allowlist",
        path="quality/dq_source.py",
        before="    _reject_unsafe_calls(parsed, source_dialect(source))\n",
        after="",
        case=(
            "tests/quality/test_dq_sql_functions.py::"
            "test_rejected_function_never_reaches_the_business_source"
        ),
        runner="pytest",
    ),
    Mutation(
        name="dq-column-type-preparation",
        path="storage/dq_actions.py",
        before="    _check_types(snapshot, rule, table, source)\n",
        after="",
        case=(
            "tests/quality/test_dq_column_types.py::"
            "test_special_columns_run_or_are_refused_at_preparation"
        ),
        runner="pytest",
    ),
    Mutation(
        name="dq-null-check-projection",
        path="quality/dq_source.py",
        before="    if column and not reference and nulls_only(rule):",
        after="    if False:",
        case=(
            "tests/quality/test_dq_column_types.py::"
            "test_special_columns_run_or_are_refused_at_preparation"
        ),
        runner="pytest",
    ),
    Mutation(
        name="dq-aggregate-pushdown",
        path="quality/dq_engine.py",
        before='    if rule.kind in {"volume_change", "freshness"}:',
        after="    if False:",
        case=(
            "tests/quality/test_dq_aggregates.py::"
            "test_volume_and_freshness_aggregate_beyond_the_scan_cap"
        ),
        runner="pytest",
    ),
    Mutation(
        name="dq-freshness-invalid-cells",
        path="quality/dq_source.py",
        before="_latest(row[1], dialect), whole_number(row[2]))",
        after="_latest(row[1], dialect), 0)",
        case="tests/quality/test_dq_aggregates.py::test_unparsable_timestamp_cells_fail_freshness",
        runner="pytest",
    ),
    Mutation(
        name="dq-alert-on-transition-only",
        path="storage/dq_results.py",
        before="    if issue is None or issue.status == prior:",
        after="    if issue is None:",
        case=(
            "tests/worker/test_dq_scheduler.py::"
            "test_consecutive_failures_alert_once_and_state_changes_alert_again"
        ),
        runner="pytest",
    ),
)
