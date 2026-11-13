# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read and run one-sentence action chains as the person who asked for them."""

from fastapi import APIRouter, Request

from datakeel.api.dependencies import DatabaseDependency
from datakeel.api.identity_access import http_actor
from datakeel.core.intent_models import ActionChain, ChainReplanRequest, IntentResult
from datakeel.intents.chains import advance_chain, replan_chain
from datakeel.storage.intent_chains import get_chain

router = APIRouter(prefix="/api/intents", tags=["intents"])


@router.get("/chains/{chain_id}")
def read_chain(chain_id: str, db: DatabaseDependency, request: Request) -> ActionChain:
    """Read a chain with each step's plans, runs, outputs and failure reason."""
    return get_chain(db, chain_id, actor=http_actor(request))


@router.post("/chains/{chain_id}/run")
def run_chain(chain_id: str, db: DatabaseDependency, request: Request) -> ActionChain:
    """Confirm and run, continue after a signature, or resume after a failed step.

    Every step is prepared and executed through the ordinary action services as the
    requesting person. Steps that need a signature wait in the approval queue; steps
    that already executed are never run again.
    """
    return advance_chain(db, chain_id, http_actor(request))


@router.post("/chains/{chain_id}/replan")
def replan(
    chain_id: str,
    db: DatabaseDependency,
    request: Request,
    body: ChainReplanRequest | None = None,
) -> IntentResult:
    """Plan deferred suffix steps or replan failed steps against the live database."""
    return replan_chain(
        db,
        chain_id,
        http_actor(request),
        context=body.context if body is not None else None,
    )
