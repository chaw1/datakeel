# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze and apply datasheet changes inside the controlled action transaction."""

from sqlalchemy.orm import Session

from datakeel.actions.datasheet_parameters import GenerateDatasheetParams, PublishDatasheetParams
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.core.agent_models import ConversationCreate
from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.datasheet_execution import DatasheetPrepared
from datakeel.core.datasheet_models import DatasheetDocument
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.harness_pricing import nanos_to_usd, reservation_cost
from datakeel.core.models import AssetRef, BoundaryModel
from datakeel.datasheets.destination import is_external_destination, model_destination
from datakeel.datasheets.prompt import build_model_prompt
from datakeel.datasheets.templates import build_template
from datakeel.routing.config import price_for
from datakeel.storage.datasheet_facts import extract_facts
from datakeel.storage.datasheet_jobs import schedule_job
from datakeel.storage.datasheet_rows import DatasheetRow
from datakeel.storage.datasheet_store import publish_in_session, save_in_session
from datakeel.storage.object_projection import content_digest


def prepare_datasheet(session: Session, params: BoundaryModel) -> BoundaryModel:
    """Replace caller-supplied prepared content with actual version facts and model limits."""
    if isinstance(params, PublishDatasheetParams):
        row = session.get(DatasheetRow, params.document_id)
        if row is None or row.dataset_id != params.dataset_id:
            msg = "Datasheet draft not found in dataset"
            raise NotFoundError(msg)
        return params
    if not isinstance(params, GenerateDatasheetParams):
        return params
    facts = extract_facts(session, params.dataset_id, params.version_id)
    if params.mode == "model":
        _version, price = price_for(params.model)
        if price.provider != params.provider:
            msg = "Datasheet model belongs to another provider"
            raise ValidationError(msg)
    config = ConversationCreate(
        dataset_id=params.dataset_id,
        provider=params.provider if params.mode == "model" else "fake",
        model=params.model if params.mode == "model" else "fake-demo",
        budget=params.budget,
        max_output_tokens=params.max_output_tokens,
    )
    target = model_destination(config)
    prepared = DatasheetPrepared(
        facts=facts, config=config, target_url=target, external=is_external_destination(target)
    )
    if params.mode == "model":
        tokens = estimate_tokens(build_model_prompt(facts, params.language))
        price_version, price = price_for(params.model)
        prepared = prepared.model_copy(
            update={
                "input_tokens": tokens,
                "price": price,
                "price_version": price_version,
                "estimated_cost_usd": nanos_to_usd(
                    reservation_cost(price, tokens, params.max_output_tokens)
                ),
            }
        )
    return params.model_copy(update={"prepared": prepared})


def datasheet_state(session: Session, params: BoundaryModel) -> str:
    """Bind live source values while excluding observation timestamps from comparison."""
    if isinstance(params, GenerateDatasheetParams):
        facts = extract_facts(session, params.dataset_id, params.version_id)
        return content_digest(
            [item.model_dump(mode="json", exclude={"recorded_at"}) for item in facts]
        )
    if isinstance(params, PublishDatasheetParams):
        row = session.get(DatasheetRow, params.document_id)
        if row is None or row.dataset_id != params.dataset_id:
            msg = "Datasheet draft no longer exists"
            raise NotFoundError(msg)
        return content_digest(row.payload)
    return ""


def execute_datasheet(
    session: Session, plan: ActionPlan, params: GenerateDatasheetParams | PublishDatasheetParams
) -> OperationResult:
    """Create an immutable draft, schedule its model task, or publish the approved draft."""
    if isinstance(params, PublishDatasheetParams):
        document = publish_in_session(session, params.document_id)
    else:
        if params.prepared is None:
            msg = "Datasheet generation has no frozen fact snapshot"
            raise ConflictError(msg)
        if params.mode == "model":
            return schedule_job(session, plan, params)
        checked = build_template(params.prepared.facts, params.language)
        document = save_in_session(
            session,
            DatasheetDocument(
                id=plan.operation_id or plan.id,
                dataset_id=params.dataset_id,
                version_id=params.version_id,
                language=params.language,
                facts=params.prepared.facts,
                sections=checked.sections,
                dropped_sentences=checked.dropped_sentences,
            ),
        )
    return OperationResult(
        outputs=[
            AssetRef(asset_type="datasheet", asset_id=document.id, version=document.version_id)
        ],
        details={"document_id": document.id, "published": document.published},
    )
