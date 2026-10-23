# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Return located definition failures before any workflow creates persistent state."""

from pydantic import JsonValue

from datakeel.actions.registry import POLICIES
from datakeel.workflows.models import (
    ApprovalStep,
    BranchStep,
    OutputStep,
    Step,
    ToolStep,
    WaitStep,
    WorkflowDefinition,
)
from datakeel.workflows.resolver import REFERENCE, expression_errors, references
from datakeel.workflows.schemas import argument_errors, output_has_path


def successors(step: Step) -> list[str]:
    """Return the explicitly declared outgoing control-flow edges."""
    if isinstance(step, BranchStep):
        return [step.then, step.otherwise]
    return [] if isinstance(step, OutputStep) else [step.next]


def _values(step: Step) -> JsonValue:
    if isinstance(step, ToolStep | ApprovalStep):
        return step.arguments.root
    if isinstance(step, WaitStep):
        return step.task_id
    if isinstance(step, BranchStep):
        return [step.ref, step.value]
    return step.value


def cycle_errors(definition: WorkflowDefinition, source: str) -> list[str]:
    """Detect directed cycles even when they are outside the entry's reachable graph."""
    steps = {step.id: step for step in definition.steps}
    visiting: set[str] = set()
    finished: set[str] = set()

    def visit(identity: str) -> str | None:
        if identity in visiting:
            return identity
        if identity in finished or identity not in steps:
            return None
        visiting.add(identity)
        for target in successors(steps[identity]):
            found = visit(target)
            if found is not None:
                return found
        visiting.remove(identity)
        finished.add(identity)
        return None

    for step in definition.steps:
        found = visit(step.id)
        if found is not None:
            return [f"{source}:steps[{found}]: cycle detected"]
    return []


def _dominators(definition: WorkflowDefinition) -> dict[str, set[str]]:
    identities = {step.id for step in definition.steps}
    parents = {identity: set[str]() for identity in identities}
    for step in definition.steps:
        for target in successors(step):
            if target in parents:
                parents[target].add(step.id)
    result = {identity: set(identities) for identity in identities}
    result[definition.entry] = {definition.entry}
    changed = True
    while changed:
        changed = False
        for identity in identities - {definition.entry}:
            previous = parents[identity]
            common = (
                set[str].intersection(*(result[parent] for parent in previous))
                if previous
                else set[str]()
            )
            value = common | {identity}
            if value != result[identity]:
                result[identity] = value
                changed = True
    return result


def _reference_errors(definition: WorkflowDefinition, step: Step) -> list[str]:
    errors = expression_errors(_values(step))
    steps = {item.id: item for item in definition.steps}
    dominators = _dominators(definition).get(step.id, set()) - {step.id}
    for reference in references(_values(step)):
        namespace, identity, *path = reference.split(".")
        if namespace == "inputs":
            if identity not in definition.inputs:
                errors.append(f"unknown input: {identity}")
        elif identity not in steps:
            errors.append(f"unknown step: {identity}")
        elif identity not in dominators:
            errors.append(f"reference must name an earlier step on every path: {identity}")
        elif not output_has_path(steps[identity], path):
            errors.append(f"unknown output reference: {reference}")
    return errors


def _step_errors(step: Step) -> list[str]:
    if isinstance(step, BranchStep):
        return [] if REFERENCE.fullmatch(step.ref) else ["branch ref must be a complete reference"]
    if not isinstance(step, ToolStep | ApprovalStep):
        return []
    name = step.tool if isinstance(step, ToolStep) else step.action
    errors = argument_errors(name, step.arguments)
    policy = POLICIES.get(name)
    if isinstance(step, ApprovalStep) and (policy is None or policy[1]):
        errors.append("approval requires an irreversible action")
    if isinstance(step, ToolStep) and policy is not None and not policy[1]:
        errors.append("irreversible action requires an approval step")
    return errors


def validate_definition(definition: WorkflowDefinition, source: str = "workflow") -> list[str]:
    """Collect deterministic errors with file and step locations for CLI and mutation tests."""
    errors: list[str] = []
    steps = {step.id: step for step in definition.steps}
    if len(steps) != len(definition.steps):
        errors.append(f"{source}:steps: duplicate step id")
    if definition.entry not in steps:
        errors.append(f"{source}:entry: unknown step: {definition.entry}")
    errors.extend(cycle_errors(definition, source))
    for step in definition.steps:
        prefix = f"{source}:steps[{step.id}]"
        errors.extend(
            f"{prefix}: unknown next step: {target}"
            for target in successors(step)
            if target not in steps
        )
        errors.extend(f"{prefix}: {error}" for error in _step_errors(step))
        errors.extend(f"{prefix}: {error}" for error in _reference_errors(definition, step))
    return errors
