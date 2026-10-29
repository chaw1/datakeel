# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise controlled identity writes and role-derived server authorization."""

from collections.abc import Mapping
from typing import cast

import pytest

from datakeel.actions.approvals import approve_plan
from datakeel.actions.execution import execute_plan
from datakeel.actions.models import (
    ActionContext,
    ActionPlan,
    ActionRun,
    ApprovalDecision,
    ExecuteRequest,
)
from datakeel.actions.planning import prepare_action
from datakeel.actions.registry import POLICIES
from datakeel.agent.recovery import execute_approved
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.models import JsonDocument, new_id, utcnow
from datakeel.core.production_models import Project
from datakeel.storage.database import Database, DatasetRow
from datakeel.storage.identity_authorization import effective_scopes
from datakeel.storage.identity_store import (
    get_bindings,
    get_role,
    list_roles,
    list_skills,
    list_teams,
    list_users,
)
from datakeel.storage.production_rows import ProductionProjectRow


def _prepare(
    db: Database, action: str, values: Mapping[str, object], actor: str = "local"
) -> ActionPlan:
    return prepare_action(
        db,
        action,
        JsonDocument.model_validate({"request_id": new_id(), **values}),
        ActionContext(actor=actor),
    )


def _run(
    db: Database, action: str, values: Mapping[str, object], actor: str = "local"
) -> ActionRun:
    plan = _prepare(db, action, values, actor)
    if plan.requires_approval:
        approve_plan(
            db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest, actor=actor)
        )
    return execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor=actor))


def _bootstrap(db: Database) -> None:
    _run(db, "manage_users", {"operation": "create", "user_id": "local"})


def _role(db: Database, identifier: str, scopes: list[str], project_id: str | None = None) -> None:
    _run(
        db,
        "define_role",
        {"role_id": identifier, "name": identifier, "scopes": scopes, "project_id": project_id},
    )


def test_zero_users_preserve_all_scopes_and_callers_can_only_narrow(db: Database) -> None:
    """An empty identity registry preserves the existing local capability contract."""
    with db.session() as session:
        current = effective_scopes(session, "arbitrary")
    assert current.zero_users
    assert current.scopes == ("*",)
    _run(
        db,
        "manage_skills",
        {
            "operation": "create",
            "skill_id": "s",
            "name": "Boxes",
            "annotation_type": "box",
            "domain": "research",
        },
        "arbitrary",
    )
    with pytest.raises(AuthorizationError, match="Missing action scope"):
        prepare_action(
            db,
            "manage_skills",
            JsonDocument({"request_id": "narrow", "operation": "delete", "skill_id": "s"}),
            ActionContext(scopes=[]),
        )


def test_first_user_bootstraps_administrator_and_unregistered_becomes_read_only(
    db: Database,
) -> None:
    """The first registered account gets the administrator template and closes writes."""
    _bootstrap(db)
    assert get_bindings(db, "local")[0].role_id == "administrator"
    with db.session() as session:
        assert effective_scopes(session, "local").scopes == tuple(
            sorted({policy[0] for policy in POLICIES.values()})
        )
        assert effective_scopes(session, "unregistered").scopes == ()
    assert len(list_roles(db)) == 5
    with pytest.raises(AuthorizationError, match="server-authorized"):
        _prepare(db, "manage_users", {"operation": "create", "user_id": "intruder"}, "unregistered")


def test_acceptance_template_has_no_write_scope(db: Database) -> None:
    """The acceptance template can inspect progress and previews but grant no writes."""
    _bootstrap(db)
    _run(
        db,
        "manage_users",
        {"operation": "create", "user_id": "observer", "role_ids": ["acceptance"]},
    )
    assert get_role(db, "acceptance").scopes == ()
    assert len(list_users(db)) == 2
    with pytest.raises(AuthorizationError):
        _prepare(db, "manage_users", {"operation": "delete", "user_id": "local"}, "observer")


def test_role_only_becomes_effective_after_approval_and_execution(db: Database) -> None:
    """Preparing and approving a role never installs a permission before execution."""
    _bootstrap(db)
    plan = _prepare(
        db, "define_role", {"role_id": "lead", "name": "Lead", "scopes": ["files:write"]}
    )
    assert plan.requires_approval
    assert "quarantine_files" in cast("list[str]", plan.canonical_params["allowed_actions"])
    assert "delete_files" in cast("list[str]", plan.canonical_params["denied_actions"])
    with pytest.raises(NotFoundError):
        get_role(db, "lead")
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    with pytest.raises(NotFoundError):
        get_role(db, "lead")
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert get_role(db, "lead").scopes == ("files:write",)


def test_agent_recovery_cannot_execute_new_role_but_can_read_human_receipt(db: Database) -> None:
    """Resuming a signed model session never substitutes for a human execution request."""
    plan = _prepare(
        db,
        "define_role",
        {"role_id": "human-only", "name": "Human only", "scopes": ["files:write"]},
    )
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    with pytest.raises(AuthorizationError, match="person"):
        execute_approved(db, plan.id)
    with pytest.raises(NotFoundError):
        get_role(db, "human-only")
    human_run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    replayed = execute_approved(db, plan.id)
    assert replayed.run is not None
    assert replayed.run.id == human_run.id


def test_role_rejects_unregistered_scopes_and_existing_identity(db: Database) -> None:
    """Neither wildcard nor invented scopes can be installed by a local administrator."""
    for scope in ("*", "imagined:write"):
        with pytest.raises(ValidationError, match="not registered"):
            _prepare(
                db, "define_role", {"role_id": "invalid", "name": "Invalid", "scopes": [scope]}
            )
    with pytest.raises(ConflictError, match="already exists"):
        _prepare(db, "define_role", {"role_id": "administrator", "name": "Other"})


def test_approver_cannot_grant_scopes_they_do_not_have(db: Database) -> None:
    """A caller with role administration still cannot mint an export capability."""
    _bootstrap(db)
    _role(db, "grantor", ["roles:manage"])
    _run(db, "manage_users", {"operation": "create", "user_id": "grantor", "role_ids": ["grantor"]})
    plan = _prepare(
        db,
        "define_role",
        {"role_id": "excess", "name": "Excess", "scopes": ["files:write"]},
        "grantor",
    )
    with pytest.raises(AuthorizationError, match="grant exceeds"):
        approve_plan(
            db,
            plan.id,
            ApprovalDecision(approve=True, actor="grantor", plan_digest=plan.plan_digest),
        )
    assert get_role(db, "grantor").scopes == ("roles:manage",)


def test_role_grant_rechecked_when_signer_loses_scope_before_execution(db: Database) -> None:
    """Revoking an already approved signer's grant prevents subsequent execution."""
    _bootstrap(db)
    _role(db, "grantor", ["roles:manage", "files:write"])
    _run(db, "manage_users", {"operation": "create", "user_id": "grantor", "role_ids": ["grantor"]})
    plan = _prepare(
        db,
        "define_role",
        {"role_id": "new-role", "name": "New", "scopes": ["files:write"]},
        "grantor",
    )
    approve_plan(
        db, plan.id, ApprovalDecision(approve=True, actor="grantor", plan_digest=plan.plan_digest)
    )
    _run(db, "update_role", {"role_id": "grantor", "name": "Grantor", "scopes": ["roles:manage"]})
    with pytest.raises(AuthorizationError, match="grant exceeds"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor="grantor"))
    with pytest.raises(NotFoundError):
        get_role(db, "new-role")


def test_another_human_administrator_can_approve_a_role_without_impersonation(db: Database) -> None:
    """Store the real approving actor while execution remains owned by the preparer."""
    _bootstrap(db)
    _role(db, "role-preparer", ["roles:manage"])
    _run(
        db,
        "manage_users",
        {"operation": "create", "user_id": "preparer", "role_ids": ["role-preparer"]},
    )
    plan = _prepare(
        db,
        "define_role",
        {"role_id": "approved-elsewhere", "name": "Approved", "scopes": ["files:write"]},
        "preparer",
    )
    approve_plan(
        db, plan.id, ApprovalDecision(approve=True, actor="local", plan_digest=plan.plan_digest)
    )
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor="preparer"))
    assert run.status == "SUCCEEDED"
    assert get_role(db, "approved-elsewhere").scopes == ("files:write",)


def test_role_execution_rechecks_independent_signer_role_management_authority(db: Database) -> None:
    """Retaining a grant's scope does not preserve a revoked ability to approve roles."""
    _bootstrap(db)
    _role(db, "signer-role", ["roles:manage", "files:write"])
    _role(db, "preparer-role", ["roles:manage"])
    for actor, role in (("signer", "signer-role"), ("preparer", "preparer-role")):
        _run(db, "manage_users", {"operation": "create", "user_id": actor, "role_ids": [role]})
    plan = _prepare(
        db,
        "define_role",
        {"role_id": "revoked-signature", "name": "Revoked", "scopes": ["files:write"]},
        "preparer",
    )
    approve_plan(
        db, plan.id, ApprovalDecision(approve=True, actor="signer", plan_digest=plan.plan_digest)
    )
    _run(
        db,
        "update_role",
        {"role_id": "signer-role", "name": "Former approver", "scopes": ["files:write"]},
    )
    with pytest.raises(AuthorizationError, match="roles:manage"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor="preparer"))
    with pytest.raises(NotFoundError):
        get_role(db, "revoked-signature")


def test_project_bindings_and_role_scopes_cannot_authorize_other_projects(db: Database) -> None:
    """Project-local role membership cannot authorize another project or global writes."""
    _bootstrap(db)
    with db.session() as session:
        session.add(DatasetRow(id="identity-fixture", name="Identity fixture"))
        session.flush()
        for identifier in ("one", "two"):
            project = Project(
                id=identifier,
                name=identifier,
                dataset_id="identity-fixture",
                version_id="version",
                label_set_id="labels",
                label_set_version=1,
                created_at=utcnow(),
            )
            session.add(
                ProductionProjectRow(
                    id=identifier,
                    dataset_id=project.dataset_id,
                    payload=project.model_dump(mode="json"),
                )
            )
        session.commit()
    _role(db, "project-admin", ["roles:manage"], "one")
    _run(
        db,
        "manage_users",
        {
            "operation": "create",
            "user_id": "manager",
            "role_ids": ["project-admin"],
            "project_id": "one",
        },
    )
    with db.session() as session:
        assert effective_scopes(session, "manager", "one").scopes == ("roles:manage",)
        assert effective_scopes(session, "manager", "two").scopes == ()
        assert effective_scopes(session, "manager").scopes == ()
    _run(
        db,
        "define_role",
        {"role_id": "empty-one", "name": "Observer", "project_id": "one"},
        "manager",
    )
    with pytest.raises(AuthorizationError):
        _prepare(
            db,
            "define_role",
            {"role_id": "empty-two", "name": "Observer", "project_id": "two"},
            "manager",
        )
    with pytest.raises(ConflictError, match="project scope is immutable"):
        _prepare(
            db, "update_role", {"role_id": "project-admin", "name": "Moved", "project_id": "two"}
        )


def test_binding_cannot_bypass_role_grant_ceiling(db: Database) -> None:
    """A constrained user manager cannot attach the administrator template to itself."""
    _bootstrap(db)
    _role(db, "users-only", ["users:manage"])
    _run(
        db,
        "manage_users",
        {"operation": "create", "user_id": "limited", "role_ids": ["users-only"]},
    )
    with pytest.raises(AuthorizationError, match="grant exceeds"):
        _run(
            db,
            "manage_users",
            {"operation": "bind_role", "user_id": "limited", "role_id": "administrator"},
            "limited",
        )
    assert len(get_bindings(db, "limited")) == 1


def test_replaying_request_rechecks_current_permissions(db: Database) -> None:
    """A remembered successful write is not disclosed after its actor loses scope."""
    _bootstrap(db)
    _role(db, "user-manager", ["users:manage"])
    _run(
        db,
        "manage_users",
        {"operation": "create", "user_id": "manager", "role_ids": ["user-manager"]},
    )
    plan = _prepare(db, "manage_users", {"operation": "create", "user_id": "ordinary"}, "manager")
    request = ExecuteRequest(plan_digest=plan.plan_digest, actor="manager")
    first = execute_plan(db, plan.id, request)
    assert execute_plan(db, plan.id, request).id == first.id
    _run(
        db,
        "manage_users",
        {"operation": "unbind_role", "user_id": "manager", "role_id": "user-manager"},
    )
    with pytest.raises(AuthorizationError):
        execute_plan(db, plan.id, request)


def test_role_update_revision_and_template_override(db: Database) -> None:
    """An approved template override keeps its identity and requires a current revision."""
    _bootstrap(db)
    _run(
        db,
        "update_role",
        {"role_id": "acceptance", "name": "Observer", "description": "Read-only", "scopes": []},
    )
    role = get_role(db, "acceptance")
    assert role.template
    assert role.revision == 2
    assert role.asset_ref.asset_type == "role"
    with pytest.raises(ConflictError, match="revision changed"):
        _prepare(
            db, "update_role", {"role_id": "acceptance", "name": "Old", "expected_revision": 1}
        )


def test_user_team_skill_crud_and_archival_do_not_reopen_zero_user_mode(db: Database) -> None:
    """Archived identities keep audit references and never reopen anonymous write access."""
    _bootstrap(db)
    _run(
        db,
        "manage_users",
        {"operation": "create_team", "team_id": "team", "name": "Team", "leader_id": "local"},
    )
    _run(db, "manage_users", {"operation": "update_team", "team_id": "team", "name": "Renamed"})
    _run(
        db,
        "manage_skills",
        {
            "operation": "create",
            "skill_id": "box",
            "name": "Box",
            "annotation_type": "box",
            "domain": "research",
        },
    )
    _run(db, "manage_skills", {"operation": "update", "skill_id": "box", "level": 3})
    _run(
        db,
        "manage_users",
        {
            "operation": "update",
            "user_id": "local",
            "display_name": "Owner",
            "team_ids": ["team"],
            "skill_ids": ["box"],
        },
    )
    assert list_users(db)[0].display_name == "Owner"
    assert list_teams(db)[0].name == "Renamed"
    assert list_skills(db)[0].level == 3
    _run(db, "manage_skills", {"operation": "delete", "skill_id": "box"})
    _run(db, "manage_users", {"operation": "delete_team", "team_id": "team"})
    assert list_skills(db)[0].status == "deleted"
    assert list_teams(db)[0].status == "deleted"
    _run(db, "manage_users", {"operation": "delete", "user_id": "local"})
    with db.session() as session:
        assert not effective_scopes(session, "unknown").zero_users
        assert effective_scopes(session, "local").scopes == ()


def test_duplicate_identities_and_unknown_memberships_cannot_overwrite_facts(db: Database) -> None:
    """Registry writes reject duplicate identities and dangling team or skill memberships."""
    _bootstrap(db)
    _run(db, "manage_users", {"operation": "create_team", "team_id": "team", "name": "Original"})
    _run(
        db,
        "manage_skills",
        {
            "operation": "create",
            "skill_id": "skill",
            "name": "Original",
            "annotation_type": "box",
            "domain": "research",
        },
    )
    for action, values in (
        (
            "manage_users",
            {"operation": "create", "user_id": "local", "display_name": "Overwritten"},
        ),
        ("manage_users", {"operation": "create_team", "team_id": "team", "name": "Overwritten"}),
        (
            "manage_skills",
            {
                "operation": "create",
                "skill_id": "skill",
                "name": "Overwritten",
                "annotation_type": "box",
                "domain": "research",
            },
        ),
    ):
        with pytest.raises(ConflictError, match="already exists"):
            _run(db, action, values)
    for values in ({"team_ids": ["missing"]}, {"skill_ids": ["missing"]}):
        with pytest.raises(NotFoundError):
            _run(db, "manage_users", {"operation": "update", "user_id": "local", **values})
    assert list_teams(db)[0].name == "Original"
    assert list_skills(db)[0].name == "Original"


def test_disabled_actor_retains_identity_but_loses_authority(db: Database) -> None:
    """Disabling and later reactivating a registered account controls current role authority."""
    _bootstrap(db)
    _run(
        db,
        "manage_users",
        {"operation": "create", "user_id": "other", "role_ids": ["administrator"]},
    )
    _run(db, "manage_users", {"operation": "update", "user_id": "other", "status": "disabled"})
    with db.session() as session:
        assert effective_scopes(session, "other").scopes == ()
    _run(db, "manage_users", {"operation": "update", "user_id": "other", "status": "active"})
    with db.session() as session:
        assert "roles:manage" in effective_scopes(session, "other").scopes


@pytest.mark.parametrize(
    ("action", "values", "error"),
    [
        ("manage_users", {"operation": "create"}, ValidationError),
        ("manage_users", {"operation": "create_team", "team_id": "t"}, ValidationError),
        ("manage_users", {"operation": "update_team", "team_id": "absent"}, NotFoundError),
        ("manage_users", {"operation": "update", "user_id": "absent"}, NotFoundError),
        ("manage_skills", {"operation": "create", "skill_id": "s"}, ValidationError),
        ("manage_skills", {"operation": "update", "skill_id": "absent"}, NotFoundError),
    ],
)
def test_missing_identity_targets_reject_without_writes(
    db: Database, action: str, values: dict[str, object], error: type[Exception]
) -> None:
    """Malformed identity commands preserve the registry's previous facts."""
    with pytest.raises(error):
        _run(db, action, values)
    assert list_users(db) == []
