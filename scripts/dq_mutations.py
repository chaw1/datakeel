# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Quality rules and tool goldens kill independent verdict, limit and projection mutants."""

from scripts.mutation_models import Mutation

DQ_MUTATIONS = (
    Mutation(
        name="dq-not-null-verdict",
        path="quality/dq_evaluation.py",
        before="        return value is None",
        after="        return False",
        case="tests/quality/test_dq_engine.py::test_not_null_guard_reports_missing_business_values",
        runner="pytest",
    ),
    Mutation(
        name="dq-scan-row-cap",
        path="quality/dq_source.py",
        before=(
            "    if result.truncated:\n"
            '        msg = "Quality rule scan row limit exceeded; '
            'no partial verdict was produced"\n'
            "        raise ExecutionError(msg)"
        ),
        after="",
        case="tests/quality/test_dq_engine.py::test_scan_row_cap_refuses_partial_success",
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
)
