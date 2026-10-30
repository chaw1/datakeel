# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated team-tier helpers shared by transaction, action and HTTP regressions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.core.models import JsonDocument
from datakeel.core.production_team_models import PackageAcceptance
from datakeel.ontology.functions import invoke_function
from datakeel.storage.production_queries import list_packages
from tests.production_flow_support import action_payload

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from datakeel.actions.models import ActionPlan
    from datakeel.storage.database import Database


class Runner(Protocol):
    """Run one controlled action through a public entry point and return receipt details."""

    def __call__(
        self, action: str, values: Mapping[str, object], actor: str = "local"
    ) -> JsonDocument:
        """Return the succeeded action receipt's typed business details."""
        ...


class ServiceRunner:
    """Prepare, approve when required and execute through the public action service."""

    def __init__(self, db: Database) -> None:
        """Bind the runner to one migrated database."""
        self.db = db

    def plan(self, action: str, values: Mapping[str, object], actor: str = "local") -> ActionPlan:
        """Prepare one plan exactly as a person or model transport would."""
        return service.prepare_action(
            self.db, action, action_payload(action, values), ActionContext(actor=actor)
        )

    def __call__(
        self, action: str, values: Mapping[str, object], actor: str = "local"
    ) -> JsonDocument:
        """Run the action as a person and return the receipt's business details."""
        plan = self.plan(action, values, actor)
        if plan.requires_approval:
            service.approve_plan(
                self.db,
                plan.id,
                ApprovalDecision(approve=True, plan_digest=plan.plan_digest, actor=actor),
            )
        run = service.execute_plan(
            self.db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor=actor)
        )
        assert run.status == "SUCCEEDED", run.error
        assert run.receipt is not None
        return JsonDocument.model_validate(run.receipt.quality["details"])


def register(runner: Runner, project_id: str, members: Mapping[str, str]) -> None:
    """Register the local administrator first, then bind each member's project role."""
    runner("manage_users", {"operation": "create", "user_id": "local"})
    for actor, role in members.items():
        runner("manage_users", {"operation": "create", "user_id": actor})
        runner(
            "manage_users",
            {"operation": "bind_role", "user_id": actor, "role_id": role, "project_id": project_id},
        )


def grant_skills(runner: Runner, levels: Mapping[str, int], domain: str = "retail") -> None:
    """Create one image-classification skill per level and bind each person to theirs."""
    for actor, level in levels.items():
        skill = f"classify-{domain}-{actor}"
        runner(
            "manage_skills",
            {
                "operation": "create",
                "skill_id": skill,
                "name": f"{domain} level {level}",
                "annotation_type": "classification",
                "domain": domain,
                "level": level,
            },
        )
        runner("manage_users", {"operation": "update", "user_id": actor, "skill_ids": [skill]})


def acceptance(
    db: Database, project_id: str, package_id: str, **sampling: object
) -> PackageAcceptance:
    """Read the package acceptance projection through the public read function."""
    result = invoke_function(
        db,
        "package_acceptance",
        JsonDocument.model_validate(
            {"project_id": project_id, "package_id": package_id, **sampling}
        ),
    )
    return PackageAcceptance.model_validate(result.data)


def accept_package(
    db: Database,
    runner: Runner,
    project_id: str,
    package_id: str,
    defective: Callable[[str], bool] = lambda _sample: False,
    actor: str = "local",
) -> JsonDocument:
    """Inspect exactly the previewed P26 sample and sign the package decision."""
    preview = acceptance(db, project_id, package_id)
    assert preview.sampling is not None, preview.status
    checks = [
        {"sample_id": sample, "defective": defective(sample), "reason": "Generated defect"}
        if defective(sample)
        else {"sample_id": sample, "defective": False}
        for sample in preview.sampling.sample_ids
    ]
    return runner("accept_package", {"package_id": package_id, "checks": checks}, actor)


def accept_all_packages(db: Database, runner: Runner, project_id: str) -> None:
    """Accept every package of a fully approved team project with no defects."""
    for package in list_packages(db, project_id):
        accept_package(db, runner, project_id, package.id)
