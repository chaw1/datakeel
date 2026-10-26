# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Answer and replay local business questions with registered semantic evidence."""

from fastapi import APIRouter, Request

from datakeel.api.dependencies import DatabaseDependency
from datakeel.ask.access import answer_refs
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.data_asset_models import AccessContext
from datakeel.storage.ask_store import get_answer
from datakeel.storage.data_asset_access import require_access

router = APIRouter(prefix="/api/ask", tags=["ask"])


@router.post("")
def ask(body: AskRequest, db: DatabaseDependency) -> AskAnswer:
    """Resolve and execute a read-only registered metric, preserving its full evidence."""
    return ask_data(db, body)


@router.get("/{answer_id}")
def replay(answer_id: str, db: DatabaseDependency, request: Request) -> AskAnswer:
    """Replay the saved result and original metric revision without rerunning SQL."""
    answer = get_answer(db, answer_id)
    require_access(
        db,
        answer_refs(answer),
        AccessContext(
            actor=request.headers.get("X-Datakeel-Actor", "local-user"), entry="ask", scope="query"
        ),
    )
    return answer
