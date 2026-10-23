# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compare actual tool, policy, state, and context evidence with golden assertions."""

from datakeel.actions.models import ActionPlan, ActionRun
from datakeel.core.harness_eval import EvalCaseResult, ExpectedAction, GoldenExpect
from datakeel.core.models import BoundaryModel
from datakeel.harness.tool_assessment import selection_refs, tool_failures


class CaseObservation(BoundaryModel):
    """Keep assertion inputs typed instead of passing mutable response dictionaries."""

    result: EvalCaseResult
    plans: list[ActionPlan]
    runs: list[ActionRun]
    context: str
    operation_errors: list[str]
    file_count: int
    quarantined_count: int
    memory_count: int = 0
    memory_used: bool = False


def _selection_failures(
    expected: ExpectedAction, plans: list[ActionPlan], observed: CaseObservation
) -> list[str]:
    failures: list[str] = []
    if expected.selection_from_tool:
        references = {
            (ref.asset_id, ref.version)
            for tool in observed.result.tool_results
            if tool.name == expected.selection_from_tool and tool.status == "SUCCEEDED"
            for ref in selection_refs(tool)
            if ref.asset_type == "file"
        }
        if not references or any(
            {(item.asset_ref.asset_id, item.asset_ref.version) for item in plan.manifest.objects}
            != references
            for plan in plans
        ):
            failures.append(f"Frozen selection differs from tool results: {expected.action_type}")
    if expected.output_matches_selection:
        for plan in plans:
            selected = sorted(item.asset_ref.asset_id for item in plan.manifest.objects)
            outputs = [
                observed.result.output_version_files.get(ref.asset_id)
                for run in observed.runs
                if run.plan_id == plan.id and run.status == "SUCCEEDED" and run.receipt
                for ref in run.receipt.outputs
                if ref.asset_type == "version"
            ]
            if not outputs or any(files != selected for files in outputs):
                failures.append(f"Published version differs from selection: {expected.action_type}")
    return failures


def _action_failures(expect: GoldenExpect, observed: CaseObservation) -> list[str]:
    failures: list[str] = []
    if [plan.action_type for plan in observed.plans] != [
        item.action_type for item in expect.actions
    ]:
        failures.append("Action plan sequence differs from expectation")
    for expected in expect.actions:
        plans = [plan for plan in observed.plans if plan.action_type == expected.action_type]
        if not plans or any(plan.requires_approval != expected.requires_approval for plan in plans):
            failures.append(f"Approval policy mismatch: {expected.action_type}")
        executions = sum(
            run.action_type == expected.action_type and run.status == "SUCCEEDED"
            for run in observed.runs
        )
        if executions != expected.executions:
            failures.append(f"Execution count mismatch: {expected.action_type}")
        failures.extend(_selection_failures(expected, plans, observed))
    return failures


def assess(expect: GoldenExpect, observed: CaseObservation) -> EvalCaseResult:
    """Evaluate every declared assertion against measured runtime observations."""
    result = observed.result
    failures = [
        *result.failures,
        *_action_failures(expect, observed),
        *tool_failures(expect.tool_results, result.tool_results),
    ]
    equalities = [
        (expect.tool_sequence, result.tool_sequence, "Tool sequence"),
        (
            set(expect.tool_set) if expect.tool_set is not None else None,
            set(result.tool_sequence),
            "Tool set",
        ),
        (expect.operation_statuses, result.operations, "Human operation statuses"),
        (expect.file_count, observed.file_count, "Visible file count"),
        (expect.quarantined_count, observed.quarantined_count, "Quarantined file count"),
        (expect.memory_count, observed.memory_count, "Active memory count"),
        (expect.memory_used, observed.memory_used, "Memory context present"),
    ]
    for expected, actual, label in equalities:
        if expected is not None and expected != actual:
            failures.append(f"{label} differs: expected {expected}, got {actual}")
    failures.extend(
        f"Answer missing: {text}"
        for text in expect.answer_contains
        if text not in result.final_answer
    )
    failures.extend(
        f"Answer contains forbidden text: {text}"
        for text in expect.answer_not_contains
        if text in result.final_answer
    )
    failures.extend(
        f"Retained context contains forbidden text: {text}"
        for text in expect.context_not_contains
        if text in observed.context
    )
    for values, haystack, label in (
        (expect.stop_contains, "\n".join(result.stop_reasons), "Stop reason"),
        (expect.context_contains, observed.context, "Retained context"),
        (expect.operation_errors, "\n".join(observed.operation_errors), "Operation error"),
    ):
        failures.extend(f"{label} missing: {value}" for value in values if value not in haystack)
    if result.turns > expect.max_turns:
        failures.append(f"Model turns exceeded: {result.turns} > {expect.max_turns}")
    if result.tokens > expect.max_tokens:
        failures.append(f"Token ceiling exceeded: {result.tokens} > {expect.max_tokens}")
    return result.model_copy(update={"passed": not failures, "failures": failures})
