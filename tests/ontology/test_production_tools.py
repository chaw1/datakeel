# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measured production goldens share the real Agent, MCP and HTTP query boundaries."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from fastmcp import Client
from jsonschema import Draft202012Validator

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ExecuteRequest
from datakeel.actions.production_catalog_parameters import PublishLabelSetParams, RunPrelabelParams
from datakeel.actions.production_parameters import (
    AssignTasksParams,
    CreateProjectParams,
    ReviewTaskParams,
    SubmitTaskParams,
)
from datakeel.actions.production_references import production_parameter_refs
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse, ToolCall
from datakeel.core.data_asset_models import AssetMutationContext, DataAssetDefinition
from datakeel.core.errors import AuthorizationError, ConflictError
from datakeel.core.identity_models import Role, Skill, Team, User
from datakeel.core.models import AssetRef, JsonDocument, new_id
from datakeel.core.production_catalog_models import ProductionModel, ProductionTemplate
from datakeel.mcp import create_server
from datakeel.ontology.functions import invoke_function
from datakeel.ontology.registry import registry
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.data_asset_store import create_asset_in_session, set_status_in_session
from datakeel.storage.database import TaskRow
from datakeel.storage.identity_rows import RoleRow, SkillRow, TeamRow, UserRow
from datakeel.storage.production_assignments import assign_tasks
from datakeel.storage.production_catalog_rows import ProductionModelRow, ProductionTemplateRow
from datakeel.storage.production_predictions import run_prelabel
from datakeel.storage.production_queries import list_packages
from datakeel.storage.production_reviews import review_task, submit_task
from tests.production_helpers import production_fixture
from tests.storage.test_production_workflow import save

if TYPE_CHECKING:
    from jsonschema.protocols import Validator
    from pydantic import JsonValue
    from sqlalchemy.orm import Session

    from datakeel.core.production_models import Project
    from datakeel.storage.database import Database

GOLDEN = json.loads(Path("contracts/production/read-golden.json").read_text())


def _arguments(db: Database, project: Project, name: str) -> JsonDocument:
    values: dict[str, JsonValue] = {"project_id": project.id}
    if name == "package_status":
        values["package_id"] = list_packages(db, project.id)[0].id
    if name == "label_set_diff":
        values = {"label_set_id": project.label_set_id, "before_version": 1, "after_version": 1}
    return JsonDocument(values)


@pytest.mark.parametrize("name", list(GOLDEN))
def test_production_reads_match_independent_golden_for_both_tool_entries(
    db: Database, name: str
) -> None:
    """Exact observed values are checked against stored gold rather than implementation output."""
    project, _ = production_fixture(db)
    for entry in ("agent", "mcp"):
        outcome = invoke_tool(
            db, name, _arguments(db, project, name), ToolCallContext(), entry=entry
        )
        assert outcome.status == "SUCCEEDED", outcome.error
        data = outcome.content.root["data"]
        assert isinstance(data, dict)
        for key, expected in GOLDEN[name].items():
            assert data[key] == expected


def test_objects_use_registered_schema_and_next_task_read_never_assigns(db: Database) -> None:
    """Every new kind is queryable and original task identity remains distinct."""
    project, tasks = production_fixture(db)
    result = invoke_function(db, "next_task", JsonDocument({"project_id": project.id}))
    assert isinstance(result.data, dict)
    assert result.data["id"] == tasks[0].id
    schemas = {kind.id: kind.properties.root for kind in registry().object_types}
    for kind in ("project", "task_package", "production_task", "label_set", "role"):
        objects = invoke_function(db, "production_objects", JsonDocument({"kind": kind})).data
        assert isinstance(objects, list)
        assert objects
        for item in objects:
            assert isinstance(item, dict)
            validator = cast("Validator", Draft202012Validator(schemas[kind]))
            validator.validate(item["properties"])
    for kind in (
        "assignment",
        "annotation_revision",
        "review",
        "user",
        "team",
        "skill",
        "model",
        "template",
        "prelabel_run",
    ):
        assert invoke_function(db, "production_objects", JsonDocument({"kind": kind})).data == []


def test_mcp_real_handshake_executes_production_goldens_and_prepares_only(db: Database) -> None:
    """Exercise actual SDK transport dispatch and reject approval and execution tool calls."""
    project, _ = production_fixture(db)

    async def scenario() -> None:
        async with Client(create_server(db), mode="legacy") as client:
            for name in GOLDEN:
                response = await client.call_tool(name, _arguments(db, project, name).root)
                outcome = ToolOutcome.model_validate(response.structured_content)
                assert outcome.status == "SUCCEEDED", outcome.error
                data = outcome.content.root["data"]
                assert isinstance(data, dict)
                for key, expected in GOLDEN[name].items():
                    assert data[key] == expected
            response = await client.call_tool(
                "define_role",
                {
                    "request_id": new_id(),
                    "role_id": "lead",
                    "name": "Contractor lead",
                    "scopes": ["production:assign"],
                },
            )
            prepared = ToolOutcome.model_validate(response.structured_content)
            assert prepared.plan is not None
            assert prepared.requires_approval
            for name in ("approve_plan", "execute_plan"):
                params: dict[str, JsonValue] = {
                    "plan_id": prepared.plan.id,
                    "plan_digest": prepared.plan.plan_digest,
                }
                if name == "approve_plan":
                    params["approve"] = True
                denied = await client.call_tool(name, params, raise_on_error=False)
                assert ToolOutcome.model_validate(denied.structured_content).status == "FAILED"
            assert (
                invoke_function(
                    db, "production_objects", JsonDocument({"kind": "role", "object_id": "lead"})
                ).data
                == []
            )

    asyncio.run(scenario())
    assert service.list_runs(db) == []


def _script(name: str, arguments: JsonDocument) -> list[ModelResponse]:
    return [
        ModelResponse(
            tool_calls=[ToolCall(name="tool_search", arguments=JsonDocument({"query": name}))]
        ),
        ModelResponse(tool_calls=[ToolCall(name=name, arguments=arguments)]),
        ModelResponse(content="Prepared or read with recorded evidence."),
    ]


def test_scripted_agent_prepares_bilingual_role_plan_without_granting_or_signing(
    db: Database,
) -> None:
    """The real graph wraps the fake provider in ScriptedChatModel and only prepares a role."""
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider(
        _script(
            "define_role",
            JsonDocument(
                {
                    "request_id": new_id(),
                    "role_id": "lead",
                    "name": "Contractor lead",
                    "scopes": ["production:assign"],
                }
            ),
        )
    )
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(
                content="加一个外包组长角色, 能派单和看返工率, 不能定稿",
            ),
            provider=provider,
        )
    )
    plan = next(event.outcome.plan for event in events if event.event == "plan" and event.outcome)
    assert plan is not None
    allowed, denied = (
        plan.canonical_params["allowed_actions"],
        plan.canonical_params["denied_actions"],
    )
    assert isinstance(allowed, list)
    assert isinstance(denied, list)
    assert "assign_tasks" in allowed
    assert "finalize_project" in denied
    assert plan.status == "PREPARED"
    assert plan.requires_approval
    assert service.list_runs(db) == []


def test_agent_frequent_production_write_is_prepared_without_execution(db: Database) -> None:
    """No-approval writes remain explicit human execution, preserving prior legacy behavior."""
    project, tasks = production_fixture(db)
    conversation = create_conversation(db, ConversationCreate())
    events = list(
        send_message(
            db,
            conversation.id,
            MessageInput(content="Save a revision"),
            provider=FakeProvider(
                _script(
                    "save_revision",
                    JsonDocument(
                        {
                            "request_id": new_id(),
                            "task_id": tasks[0].id,
                            "previous_revision_id": None,
                            "annotation": {
                                "sample_id": tasks[0].sample_id,
                                "annotator_id": "local",
                                "labels": ["cat"],
                            },
                        }
                    ),
                )
            ),
        )
    )
    plan = next(event.outcome.plan for event in events if event.event == "plan" and event.outcome)
    assert plan is not None
    assert not plan.requires_approval
    assert service.list_runs(db) == []
    assert (
        invoke_function(db, "project_progress", JsonDocument({"project_id": project.id})).data
        is not None
    )
    outcome = invoke_tool(
        db,
        "execute_plan",
        JsonDocument({"plan_id": plan.id, "plan_digest": plan.plan_digest}),
        ToolCallContext(),
    )
    assert outcome.status == "FAILED"
    assert "person" in (outcome.error or "")
    assert (
        service.execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest)).status
        == "SUCCEEDED"
    )


def _protect_project(db: Database, project: Project) -> None:
    with db.session() as session:
        context = AssetMutationContext(actor="steward", operation_id=new_id())
        asset = create_asset_in_session(
            session,
            DataAssetDefinition(
                target=AssetRef(asset_id=project.dataset_id, version=project.version_id),
                name="Generated protected production source",
                owner="Steward",
                classification="request",
            ),
            context,
        )
        set_status_in_session(
            session,
            asset.id,
            "published",
            AssetMutationContext(
                actor="steward",
                operation_id=new_id(),
            ),
        )
        session.commit()


def _reviewed_project(db: Database) -> tuple[Project, str]:
    project, tasks = production_fixture(db, "group")
    with db.session() as session:
        assign_tasks(
            session, AssignTasksParams(request_id="assign", task_ids=(tasks[0].id,), actor="a")
        )
        session.commit()
    revision = save(db, tasks[0], "a")
    with db.session() as session:
        submit_task(session, SubmitTaskParams(request_id="submit", task_id=tasks[0].id), "a")
        review_task(
            session,
            ReviewTaskParams(
                request_id="review",
                task_id=tasks[0].id,
                revision_id=revision.id,
                decision="approve",
            ),
            "q",
        )
        session.commit()
    return project, tasks[0].id


@pytest.mark.parametrize(
    "kind",
    ["project", "task_package", "production_task", "assignment", "annotation_revision", "review"],
)
def test_production_object_reads_enforce_the_owning_dataset_grant(db: Database, kind: str) -> None:
    """Native ownership protects annotations even without generated action lineage."""
    project, _ = _reviewed_project(db)
    query = JsonDocument({"kind": kind, "project_id": project.id})
    assert invoke_function(db, "production_objects", query).data
    _protect_project(db, project)
    with pytest.raises(AuthorizationError, match="active query grant"):
        invoke_function(db, "production_objects", query)


def test_source_grant_is_rechecked_when_replaying_or_executing_a_prepared_revision(
    db: Database,
) -> None:
    """Idempotency never makes a previously readable source stay readable after policy changes."""
    project, tasks = production_fixture(db)
    params = JsonDocument(
        {
            "request_id": "prepared-before-protection",
            "task_id": tasks[0].id,
            "previous_revision_id": None,
            "annotation": {
                "sample_id": tasks[0].sample_id,
                "annotator_id": "local",
                "labels": ["cat"],
            },
        }
    )
    plan = service.prepare_action(db, "save_revision", params)
    _protect_project(db, project)
    with pytest.raises(AuthorizationError, match="active query grant"):
        service.prepare_action(db, "save_revision", params)
    with pytest.raises(AuthorizationError, match="active query grant"):
        service.execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def test_production_request_cannot_replay_with_different_self_reported_scope_limits(
    db: Database,
) -> None:
    """The retry identity binds caller narrowing as well as action parameters and actor."""
    project, _ = production_fixture(db, "group")
    params = JsonDocument({"request_id": "same-claim", "project_id": project.id})
    limited = ActionContext(scopes=["production:claim"])
    first = service.prepare_action(db, "claim_task", params, limited)
    assert service.prepare_action(db, "claim_task", params, limited) == first
    with pytest.raises(ConflictError, match="different caller limits"):
        service.prepare_action(db, "claim_task", params, ActionContext())


def test_completed_projects_return_no_next_task_and_preserve_pinned_source_refs(
    db: Database,
) -> None:
    """A read of exhausted work returns explicit None and never invents an assignment."""
    project, tasks = production_fixture(db, count=1)
    save(db, tasks[0])
    with db.session() as session:
        submit_task(session, SubmitTaskParams(request_id="submit", task_id=tasks[0].id), "local")
        session.commit()
    result = invoke_function(db, "next_task", JsonDocument({"project_id": project.id}))
    assert result.data is None
    assert AssetRef(asset_id=project.dataset_id, version=project.version_id) in result.asset_refs


def test_production_label_references_keep_the_exact_vocabulary_version(db: Database) -> None:
    """Project and publication plans use the same versioned vocabulary identity as object reads."""
    project, _ = production_fixture(db)
    params = CreateProjectParams(
        request_id="project-copy",
        name="Copy",
        dataset_id=project.dataset_id,
        version_id=project.version_id,
        label_set_id=project.label_set_id,
        label_set_version=1,
    )
    expected = AssetRef(asset_type="label_set", asset_id=project.label_set_id, version="1")
    assert expected in production_parameter_refs(params)
    assert expected in production_parameter_refs(
        PublishLabelSetParams(
            request_id="publish",
            label_set_id=project.label_set_id,
            version=1,
        )
    )


def test_project_filter_does_not_treat_unrelated_user_identity_as_membership(db: Database) -> None:
    """Reusing an ID across object namespaces does not make the user a project member."""
    project, _ = production_fixture(db)
    user = User(id=project.id, display_name="Same identifier in another family")
    with db.session() as session:
        session.add(UserRow(id=user.id, payload=user.model_dump(mode="json")))
        session.commit()
    result = invoke_function(
        db,
        "production_objects",
        JsonDocument(
            {
                "kind": "user",
                "project_id": project.id,
            }
        ),
    )
    assert result.data == []


def test_production_task_refs_do_not_resolve_an_unrelated_legacy_worker_task(db: Database) -> None:
    """Colliding task IDs across namespaces never require grants for the other task's dataset."""
    _, task_id = _reviewed_project(db)
    unrelated, _ = production_fixture(db)
    with db.session() as session:
        session.add(
            TaskRow(
                id=task_id,
                dataset_id=unrelated.dataset_id,
                input_version_id=unrelated.version_id,
                idempotency_key=new_id(),
            )
        )
        session.commit()
    _protect_project(db, unrelated)
    result = None
    with suppress(AuthorizationError):
        result = invoke_function(
            db,
            "production_objects",
            JsonDocument(
                {
                    "kind": "annotation_revision",
                    "task_id": task_id,
                }
            ),
        )
    assert result is not None, "Production task IDs must not inherit legacy worker policies"
    assert isinstance(result.data, list)
    assert len(result.data) == 1
    assert result.asset_refs[0].asset_type == "annotation_revision"
    assert (
        invoke_tool(
            db,
            "production_objects",
            JsonDocument(
                {
                    "kind": "annotation_revision",
                    "task_id": task_id,
                }
            ),
            ToolCallContext(),
        ).status
        == "SUCCEEDED"
    )


def test_catalog_and_identity_objects_project_nonempty_rows_with_registered_schemas(
    db: Database,
) -> None:
    """Every catalog and identity reader validates real rows rather than only empty collections."""
    project, _ = production_fixture(db)
    with db.session() as session:
        _seed_readable_catalog(session)
        run_prelabel(
            session,
            RunPrelabelParams(request_id="fake", project_id=project.id, model_id="fake"),
            "local",
        )
        session.commit()
    schemas = {kind.id: kind.properties.root for kind in registry().object_types}
    for kind in ("user", "team", "skill", "role", "template", "model", "prelabel_run"):
        result = invoke_function(db, "production_objects", JsonDocument({"kind": kind}))
        assert isinstance(result.data, list)
        assert result.data
        validator = cast("Validator", Draft202012Validator(schemas[kind]))
        for item in result.data:
            assert isinstance(item, dict)
            validator.validate(item["properties"])


def test_object_filters_keep_exact_label_versions_and_task_identities(db: Database) -> None:
    """Object filtering preserves vocabulary versions and rejects a mismatched annotation task."""
    project, tasks = production_fixture(db)
    save(db, tasks[0])
    assert (
        invoke_function(
            db,
            "production_objects",
            JsonDocument(
                {
                    "kind": "label_set",
                    "object_id": project.label_set_id,
                    "version": 2,
                }
            ),
        ).data
        == []
    )
    version_one = invoke_function(
        db,
        "production_objects",
        JsonDocument(
            {
                "kind": "label_set",
                "object_id": project.label_set_id,
                "version": 1,
            }
        ),
    )
    assert (
        invoke_function(
            db,
            "production_objects",
            JsonDocument(
                {
                    "kind": "annotation_revision",
                    "task_id": "no-match",
                }
            ),
        ).data
        == []
    )
    assert version_one.asset_refs == [
        AssetRef(asset_type="label_set", asset_id=project.label_set_id, version="1")
    ]


def _seed_readable_catalog(session: Session) -> None:
    values = (
        User(id="reader", display_name="Generated reader"),
        Team(id="team", name="Generated team"),
        Skill(id="skill", name="Boxes", annotation_type="box", domain="generated"),
        Role(id="administrator", name="Edited administrator", scopes=(), template=True),
    )
    template = ProductionTemplate(id="boxes", name="Boxes")
    model = ProductionModel(id="fake", name="Generated fake", version="1", provider="fake")
    for kind, value in zip((UserRow, TeamRow, SkillRow, RoleRow), values, strict=True):
        session.add(kind(id=value.id, payload=value.model_dump(mode="json")))
    session.add(
        ProductionTemplateRow(id=template.id, revision=1, payload=template.model_dump(mode="json"))
    )
    session.add(ProductionModelRow(id=model.id, revision=1, payload=model.model_dump(mode="json")))
    session.flush()
