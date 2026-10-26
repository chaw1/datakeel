# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate and execute reversible standard changes inside the action transaction."""

from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.actions.references import standard_refs
from datakeel.actions.standard_parameters import (
    ConfirmStandardMappingParams,
    ImportStandardsParams,
    RollbackStandardsParams,
    StandardActionParams,
    UpdateCodeListParams,
    UpdateStandardParams,
)
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import AssetRef, LineageEvent, new_id, utcnow
from datakeel.core.standard_history_models import StandardsRevision, StandardsState
from datakeel.core.standard_models import CodeList, FieldStandard, StandardsContract
from datakeel.storage.catalog_store import lock_catalog, read_snapshot
from datakeel.storage.events import append_event
from datakeel.storage.standard_store import revisions_in_session, state_in_session


def _replacement[T: FieldStandard | CodeList](
    existing: tuple[T, ...],
    incoming: tuple[T, ...],
    versions: dict[str, int],
    *,
    restoring: bool = False,
) -> tuple[T, ...]:
    current = {item.code: item for item in existing}
    result = {} if restoring else dict(current)
    for item in incoming:
        prior = current.get(item.code)
        expected = prior.version if prior else 1
        if not restoring and item.version != expected:
            msg = f"Expected {item.code} version {item.version}; current is {expected}"
            raise ConflictError(msg)
        changed = prior is not None and item != prior
        baseline = max(versions.get(item.code, 0), prior.version if prior else 0)
        version = baseline + 1 if prior is None or changed else prior.version
        result[item.code] = item.model_copy(update={"version": version})
    return tuple(result[code] for code in sorted(result))


def _contract(
    current: StandardsContract,
    incoming: StandardsContract,
    versions: tuple[dict[str, int], dict[str, int]],
    *,
    restoring: bool = False,
) -> StandardsContract:
    return StandardsContract(
        standards=_replacement(
            current.standards, incoming.standards, versions[0], restoring=restoring
        ),
        code_lists=_replacement(
            current.code_lists, incoming.code_lists, versions[1], restoring=restoring
        ),
    )


def _historical_versions(session: Session) -> tuple[dict[str, int], dict[str, int]]:
    versions: tuple[dict[str, int], dict[str, int]] = ({}, {})
    for revision in revisions_in_session(session):
        for index, items in enumerate((revision.contract.standards, revision.contract.code_lists)):
            for item in items:
                versions[index][item.code] = max(versions[index].get(item.code, 0), item.version)
    return versions


def next_state(session: Session, params: StandardActionParams) -> StandardsState:
    """Check version expectations and references without writing or changing input models."""
    lock_catalog(session)
    current = state_in_session(session)
    versions = _historical_versions(session)
    contract, mappings = current.contract, current.mappings
    if isinstance(params, RollbackStandardsParams):
        prior = state_in_session(session, params.revision)
        contract = _contract(current.contract, prior.contract, versions, restoring=True)
        mappings = prior.mappings
    elif isinstance(params, ConfirmStandardMappingParams):
        _validate_mapping(session, params, current)
        mapped = {item.column_id: item for item in mappings}
        mapped[params.mapping.column_id] = params.mapping
        mappings = tuple(mapped[key] for key in sorted(mapped))
    else:
        incoming = _incoming(params, current.contract)
        contract = _contract(current.contract, incoming, versions)
    return StandardsState(revision=current.revision + 1, contract=contract, mappings=mappings)


def _incoming(params: StandardActionParams, current: StandardsContract) -> StandardsContract:
    if isinstance(params, ImportStandardsParams):
        return params.contract
    if isinstance(params, UpdateStandardParams):
        return StandardsContract(standards=(params.definition,), code_lists=current.code_lists)
    if isinstance(params, UpdateCodeListParams):
        return StandardsContract(code_lists=(params.definition,))
    msg = "Unknown standards action parameters"
    raise ValidationError(msg)


def _validate_mapping(
    session: Session, params: ConfirmStandardMappingParams, state: StandardsState
) -> None:
    if not any(
        item.code == params.mapping.standard_code and item.status == "active"
        for item in state.contract.standards
    ):
        msg = "A mapping requires an existing active field standard"
        raise ValidationError(msg)
    if not any(
        item.asset_ref.asset_type == "column"
        and item.asset_ref.asset_id == params.mapping.column_id
        for item in read_snapshot(session).objects
    ):
        msg = "A mapping requires an existing catalog column"
        raise NotFoundError(msg)


def standard_impact(session: Session, params: StandardActionParams) -> int:
    """Count every definition and association potentially changed by a restored snapshot."""
    if isinstance(params, RollbackStandardsParams):
        current = state_in_session(session)
        target = state_in_session(session, params.revision)
        return (
            len({item.code for item in (*current.contract.standards, *target.contract.standards)})
            + len(
                {item.code for item in (*current.contract.code_lists, *target.contract.code_lists)}
            )
            + len({item.column_id for item in (*current.mappings, *target.mappings)})
        )
    return len(standard_refs(params))


def _outputs(state: StandardsState, params: StandardActionParams) -> list[AssetRef]:
    if isinstance(params, ConfirmStandardMappingParams):
        return [
            AssetRef(
                asset_type="standard_mapping",
                asset_id=params.mapping.column_id,
                version=str(state.revision),
            )
        ]
    versions = {
        **{("standard", item.code): item.version for item in state.contract.standards},
        **{("code_list", item.code): item.version for item in state.contract.code_lists},
    }
    return [
        item.model_copy(
            update={"version": str(versions.get((item.asset_type, item.asset_id), state.revision))}
        )
        for item in standard_refs(params)
    ]


def execute_standard_action(
    session: Session, plan: ActionPlan, params: StandardActionParams
) -> OperationResult:
    """Append a complete effective revision with action attribution and reversible history."""
    state = next_state(session, params)
    event_id = new_id()
    revision = StandardsRevision(
        revision=state.revision,
        contract=state.contract,
        mappings=state.mappings,
        plan_id=plan.id,
        actor=plan.actor,
        action_type=plan.action_type,
        event_id=event_id,
        created_at=utcnow(),
    )
    outputs = _outputs(state, params)
    append_event(
        session,
        LineageEvent(
            event_id=event_id,
            idempotency_key=f"standards:{plan.id}",
            operator="STANDARDS_CHANGE",
            source_module="standards",
            on_behalf_of=plan.actor,
            outputs=outputs,
            params={"standards_revision": revision.model_dump(mode="json")},
        ),
    )
    return OperationResult(
        outputs=outputs,
        details={
            "from_version": state.revision - 1,
            "to_version": state.revision,
            "event_id": event_id,
        },
    )
