# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Closed declarations and lifecycle contracts; no persistence implementation imports."""

from importlib.resources import files
from typing import Literal

from pydantic import Field, TypeAdapter

from datakeel.actions.models import ActionImpact, ActionPlan, OperationResult
from datakeel.core.errors import ConflictError
from datakeel.core.models import AssetRef, BoundaryModel, LineageEvent
from datakeel.ontology.models import FrozenManifest


class AuthorizationPolicy(BoundaryModel):
    """Independent entry restrictions, current server scope and bounded authority."""

    human_only: bool = False
    automatic: bool = False
    scope_resolver: Literal["server_effective_scopes"] = "server_effective_scopes"
    actor: Literal["plan_actor"] = "plan_actor"
    signer: Literal["same_actor", "role_grantor"] = "same_actor"
    disclosure: Literal["source_grants"] = "source_grants"
    budget: Literal["frozen_ceiling"] = "frozen_ceiling"
    mcp: Literal["prepare_only"] = "prepare_only"


class ApprovalPolicy(BoundaryModel):
    """A static floor; a prepare hook can only tighten the requirement."""

    mode: Literal["auto", "always"] = "auto"
    dynamic: Literal["prepare_tightens"] = "prepare_tightens"


class ActionHandlerSet(BoundaryModel):
    """Ordered ActionFrame -> ActionFrame stages in one session, except deferred work.

    All handlers propagate DatakeelError with its unchanged public text. Rollback runs
    before failure recording; receipt uses the common attribution contract. Deferred
    work receives its own Database and closes through the existing run transaction.
    """

    module: str
    prepare: tuple[str, ...]
    manifest: str
    snapshot: str
    references: str
    impact: str
    execute: str
    deferred: str | None = None
    worker: str | None = None
    completion: str
    rollback: str
    receipt: str


class ActionFrame(BoundaryModel):
    """Typed immutable transfer between ordered handlers; rows never cross this port."""

    params: BoundaryModel
    manifest: FrozenManifest | None = None
    state_digest: str = ""
    references: tuple[AssetRef, ...] = ()
    impact: ActionImpact | None = None
    reversible: bool = True
    external: bool = False
    plan: ActionPlan | None = None
    result: OperationResult | None = None
    error: str | None = None
    run_id: str = ""
    event: LineageEvent | None = None


class ActionExample(BoundaryModel):
    """A structured intent independent of historical bilingual presentation strings."""

    language: Literal["zh", "en"]
    text: str
    params: BoundaryModel


class Condition(BoundaryModel):
    """Closed, versioned file-state vocabulary; unversioned predicates stay opaque."""

    kind: Literal["file_selection.v1", "authorized_limits.v1", "frozen_revisions.v1", "opaque"]
    asset: str = "file"


class Effect(BoundaryModel):
    """A bounded state assignment on the frozen file manifest."""

    asset: Literal["file", "artifact"] = "file"
    field: Literal["quarantined"] = "quarantined"
    value: bool


class ActionDeclaration(BoundaryModel):
    """One generated owner, preserving its public compatibility metadata verbatim."""

    id: str
    compatibility: Literal["replace", "append"] = "append"
    params: type[BoundaryModel]
    auth_scope: str
    execution_target: Literal["data_plane", "control_plane", "external"]
    reversible: bool
    inverse: str | None = None
    effect_text: str
    authorization: AuthorizationPolicy
    approval: ApprovalPolicy = ApprovalPolicy()
    handlers: ActionHandlerSet
    preconditions: tuple[Condition, ...]
    effects: tuple[Effect, ...]
    examples: tuple[ActionExample, ...]
    phrases: tuple[tuple[str, tuple[str, ...]], ...]
    legacy_examples: tuple[tuple[str, tuple[str, ...]], ...]
    surfaces: tuple[str, ...] = (
        "registry",
        "http",
        "mcp_prepare",
        "agent",
        "cli",
        "intents",
        "card",
    )
    widget: Literal["generic"] = "generic"
    fixtures: tuple[str, ...] = Field(min_length=1)


def resource[T](name: str, adapter: TypeAdapter[T]) -> T:
    """Read packaged declaration data through a fully typed validator; errors fail closed."""
    return adapter.validate_json(files("datakeel.actions").joinpath(name).read_bytes())


def required[T](value: T | None) -> T:
    """Reject incomplete lifecycle values at their first consumer, preserving their type."""
    if value is None:
        msg = "Incomplete action lifecycle frame"
        raise ConflictError(msg)
    return value
